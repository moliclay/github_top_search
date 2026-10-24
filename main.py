"""GitHub 每日热门项目采集器。"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from lxml import html

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from config import BASE_DIR, Config, load_config

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_STATE_PATH = LOG_DIR / "last_run.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
SYSTEM_PROMPT = (
    "你是一个中文技术编辑。用一句不超过30个汉字的大白话说明这个开源项目是干什么的。"
    "只输出这句话，不要写实现语言、技术栈、功能列表或营销词；不要描述仓库、源码或维护方式，只说明项目本身能做什么。"
    "不要加引号、编号或解释；专有名词保留英文原名，不要音译。"
)


@dataclass
class Repo:
    rank: int
    full_name: str
    url: str
    description: str
    language: str
    stars_today: str
    summary: str = ""
    summary_fallback: bool = False


def setup_logging(console: bool) -> logging.Logger:
    logger = logging.getLogger("github_daily")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if console and sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def escape_table(value: str) -> str:
    return normalize_text(value).replace("|", "｜").replace("\n", " ")


def clean_summary(text: str, max_chars: int) -> str:
    text = normalize_text(text)
    text = re.sub(r"^(一句话介绍|一句话|简介|项目介绍)[:：]\s*", "", text)
    text = re.sub(r"^[\-\*\d\.\)、\s]+", "", text)
    text = text.strip("`*_\"'“”‘’ ")
    text = text.replace("|", "｜")
    match = re.search(r"^(.+?[。！？.!?])", text)
    if match:
        text = match.group(1)
    text = text.rstrip("，,、；;：: ")
    if len(text) > max_chars:
        text = text[:max_chars].rstrip("，,、；;：: ") + "…"
    return text.strip()


def parse_trending(page: str, top_n: int) -> list[Repo]:
    document = html.fromstring(page)
    articles = document.xpath(
        '//article[contains(concat(" ", normalize-space(@class), " "), " Box-row ")]'
    )
    repos: list[Repo] = []
    for article in articles:
        if len(repos) >= top_n:
            break
        hrefs = article.xpath(".//h2//a/@href")
        if not hrefs:
            continue
        href = hrefs[0].strip()
        url = urljoin("https://github.com/", href)
        path = urlparse(url).path.strip("/")
        if "/" not in path:
            continue
        description = normalize_text(" ".join(article.xpath(".//p//text()")))
        language = normalize_text(
            " ".join(
                article.xpath(
                    './/span[@itemprop="programmingLanguage"]//text()'
                )
            )
        )
        stars_text = normalize_text(
            " ".join(
                article.xpath(
                    './/span[contains(@class, "float-sm-right")]//text()'
                )
            )
        )
        stars_match = re.search(
            r"([\d,]+)\s+stars?\s+today",
            stars_text,
            flags=re.IGNORECASE,
        )
        repos.append(
            Repo(
                rank=len(repos) + 1,
                full_name=path,
                url=url,
                description=description,
                language=language,
                stars_today=stars_match.group(1) if stars_match else "",
            )
        )
    return repos


def fetch_trending(cfg: Config, logger: logging.Logger, limit: int | None = None) -> list[Repo]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.get(
                cfg.trending_url,
                headers=headers,
                timeout=cfg.request_timeout,
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            repos = parse_trending(
                response.text,
                limit if limit is not None else cfg.top_n,
            )
            if not repos:
                raise RuntimeError("页面已返回，但没有解析到任何项目")
            return repos
        except Exception as exc:
            last_error = exc
            logger.warning(
                "采集 GitHub Trending 失败（第 %d/3 次）：%s",
                attempt,
                exc,
            )
            if attempt < 3:
                time.sleep(attempt * 2)
    raise RuntimeError(f"采集 GitHub Trending 失败：{last_error}") from last_error


def fetch_readme(repo: Repo, timeout: int = 10) -> str:
    headers = {"User-Agent": USER_AGENT}
    for filename in ("README.md", "readme.md", "README.MD", "README.rst", "README"):
        url = (
            f"https://raw.githubusercontent.com/{repo.full_name}/HEAD/{filename}"
        )
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code != 200 or not response.text.strip():
                continue
            text = re.sub(r"```.*?```", " ", response.text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = normalize_text(text)
            if text:
                return text[:1500]
        except requests.RequestException:
            continue
    return ""


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def port_is_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(
    host: str,
    port: int,
    seconds: int,
    logger: logging.Logger,
) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if port_is_open(host, port):
            return True
        time.sleep(1)
    return port_is_open(host, port)


def start_proxy(cfg: Config, logger: logging.Logger) -> bool:
    if not cfg.llm_proxy_dir:
        logger.warning("未配置 LLM_PROXY_DIR，无法自动启动本地代理")
        return False
    proxy_dir = cfg.llm_proxy_dir
    script = proxy_dir / "wb_proxy.py"
    if not script.exists():
        logger.warning("找不到代理脚本：%s", script)
        return False
    pythonw = proxy_dir / "python" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    command = [str(pythonw), str(script), "--port", str(cfg.proxy_port)]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            command,
            cwd=str(proxy_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        logger.info("已尝试启动本地大模型代理：%s", proxy_dir)
        return True
    except Exception as exc:
        logger.error("启动本地大模型代理失败：%s", exc)
        return False


def ensure_llm_ready(cfg: Config, logger: logging.Logger) -> bool:
    if OpenAI is None:
        logger.warning("未安装 openai，无法生成中文简介")
        return False
    if not cfg.llm_api_key:
        logger.warning("未配置 LLM_API_KEY，无法生成中文简介")
        return False
    host = cfg.proxy_host
    port = cfg.proxy_port
    if port_is_open(host, port):
        return True
    if is_loopback(host) and cfg.llm_proxy_autostart:
        logger.info("本地大模型代理未运行，尝试自动启动")
        if start_proxy(cfg, logger) and wait_for_port(host, port, 30, logger):
            logger.info("本地大模型代理已就绪")
            return True
        logger.warning("本地大模型代理启动后仍不可用")
    else:
        logger.warning("本地大模型代理不可用，且未启用自动启动")
    return False


def get_llm_client(cfg: Config):
    if OpenAI is None or not cfg.llm_api_key:
        return None
    return OpenAI(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        timeout=cfg.llm_timeout,
        max_retries=1,
    )


def build_user_prompt(repo: Repo) -> str:
    description = repo.description or "（GitHub 简介为空）"
    readme_part = ""
    if not repo.description:
        readme_text = fetch_readme(repo)
        if readme_text:
            readme_part = f"\nREADME 摘要：{readme_text}"
    return (
        f"项目：{repo.full_name}\n"
        f"GitHub 简介：{description}\n"
        f"主要语言：{repo.language or '未知'}"
        f"{readme_part}"
    )


def fallback_summary(repo: Repo) -> str:
    if repo.description:
        text = escape_table(repo.description)
        if len(text) > 90:
            text = text[:90].rstrip("，,、；;：: ") + "…"
        return text
    return "暂无简介（点击项目名查看详情）"


def summarize_repo(
    repo: Repo,
    client,
    cfg: Config,
    logger: logging.Logger,
) -> tuple[str, bool]:
    if client is None:
        return fallback_summary(repo), True
    prompt = build_user_prompt(repo)
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=cfg.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=2000 if attempt == 0 else 4000,
            )
            choice = response.choices[0]
            raw = (choice.message.content or "").strip()
            summary = clean_summary(raw, cfg.max_summary_chars)
            if summary and has_cjk(summary) and summary not in {"暂无简介", "暂无简介。"}:
                logger.info("AI 简介成功：%s -> %s", repo.full_name, summary)
                return summary, False
            logger.warning(
                "AI 简介为空或不是中文：%s（finish_reason=%s）",
                repo.full_name,
                getattr(choice, "finish_reason", "unknown"),
            )
        except Exception as exc:
            logger.warning(
                "调用大模型失败：%s（第 %d/2 次）：%s",
                repo.full_name,
                attempt + 1,
                exc,
            )
        if attempt == 0:
            time.sleep(1)
    return fallback_summary(repo), True


def enrich_summaries(
    repos: list[Repo],
    cfg: Config,
    logger: logging.Logger,
) -> list[int]:
    fallback_ranks: list[int] = []
    if not ensure_llm_ready(cfg, logger):
        for repo in repos:
            repo.summary = fallback_summary(repo)
            repo.summary_fallback = True
            fallback_ranks.append(repo.rank)
        return fallback_ranks
    client = get_llm_client(cfg)
    for repo in repos:
        summary, fallback = summarize_repo(repo, client, cfg, logger)
        repo.summary = summary
        repo.summary_fallback = fallback
        if fallback:
            fallback_ranks.append(repo.rank)
    return fallback_ranks


def render_markdown(
    repos: list[Repo],
    fallback_ranks: list[int],
    cfg: Config,
    started_at: dt.datetime,
    finished_at: dt.datetime,
) -> str:
    lines = [
        f"# GitHub 每日热门项目 · {started_at:%Y-%m-%d}",
        "",
        (
            f"> 数据来源：[GitHub Trending 日榜]({cfg.trending_url}) · "
            f"每日 {cfg.schedule_time} 自动更新 · 共 {len(repos)} 个"
        ),
        "",
        "| # | 项目 | 一句话介绍 | 语言 | 今日新增 |",
        "|---|------|------------|------|----------|",
    ]
    for repo in repos:
        summary = escape_table(repo.summary) or "暂无简介"
        language = escape_table(repo.language) or "—"
        stars = f"+{repo.stars_today}" if repo.stars_today else "—"
        lines.append(
            f"| {repo.rank} | [{repo.full_name}]({repo.url}) | "
            f"{summary} | {language} | {stars} |"
        )
    lines.extend(
        [
            "",
            "---",
            f"生成时间：{finished_at:%Y-%m-%d %H:%M:%S}",
        ]
    )
    if fallback_ranks:
        items = "、".join(str(rank) for rank in fallback_ranks)
        lines.append(
            f"注：第 {items} 项因 AI 摘要不可用，已使用 GitHub 原文简介。"
        )
    lines.append("")
    return "\n".join(lines)


def get_desktop_dir() -> Path | None:
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(
            None,
            0x0010,
            None,
            0,
            buffer,
        )
        if result == 0 and buffer.value:
            return Path(buffer.value)
    desktop = Path.home() / "Desktop"
    return desktop if desktop.exists() else None


def choose_output_dir(logger: logging.Logger) -> Path:
    desktop = get_desktop_dir()
    if desktop is not None:
        try:
            desktop.mkdir(parents=True, exist_ok=True)
            probe = desktop / ".github_daily_write_test.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return desktop
        except Exception as exc:
            logger.warning(
                "桌面目录不可写：%s，改用 %s",
                exc,
                BASE_DIR / "output",
            )
    output = BASE_DIR / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_markdown(path: Path, content: str, logger: logging.Logger) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    logger.info("已写入 Markdown：%s", path)


def write_run_state(
    status: str,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    output_path: Path | None,
    project_count: int | None,
    error: str | None,
    logger: logging.Logger,
) -> None:
    data = {
        "status": status,
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 1),
        "project_count": project_count,
        "output": str(output_path) if output_path else "",
        "error": (error or "")[:500],
    }
    temp_path = RUN_STATE_PATH.with_name(RUN_STATE_PATH.name + ".tmp")
    try:
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp_path, RUN_STATE_PATH)
    except OSError as exc:
        logger.warning("写入运行状态失败：%s", exc)


def run_generation(cfg: Config, logger: logging.Logger) -> Path:
    started_at = dt.datetime.now()
    logger.info("开始生成 GitHub 每日热门项目")
    repos = fetch_trending(cfg, logger)
    logger.info("采集到 %d 个项目", len(repos))
    fallback_ranks = enrich_summaries(repos, cfg, logger)
    finished_at = dt.datetime.now()
    content = render_markdown(
        repos,
        fallback_ranks,
        cfg,
        started_at,
        finished_at,
    )
    output_dir = choose_output_dir(logger)
    output_path = output_dir / f"GitHub每日热门_{started_at:%Y-%m-%d}.md"
    write_markdown(output_path, content, logger)
    write_run_state(
        "success",
        started_at,
        finished_at,
        output_path,
        len(repos),
        None,
        logger,
    )
    logger.info(
        "生成完成，耗时 %.1f 秒",
        (finished_at - started_at).total_seconds(),
    )
    return output_path


def run_check(cfg: Config, logger: logging.Logger) -> int:
    ok = True
    print("检查 GitHub Trending ...")
    try:
        repos = fetch_trending(cfg, logger, limit=1)
        print(f"  GitHub: OK（{repos[0].full_name}）")
    except Exception as exc:
        print(f"  GitHub: 失败（{exc}）")
        ok = False

    print("检查本地大模型 ...")
    if ensure_llm_ready(cfg, logger):
        client = get_llm_client(cfg)
        if client is None:
            print("  LLM: 失败（客户端未初始化）")
            ok = False
        else:
            sample = Repo(
                rank=1,
                full_name="php/php-src",
                url="https://github.com/php/php-src",
                description="The PHP Interpreter",
                language="C",
                stars_today="",
            )
            summary, fallback = summarize_repo(sample, client, cfg, logger)
            if fallback:
                print(f"  LLM: 失败（已回退：{summary}）")
                ok = False
            else:
                print(f"  LLM: OK（示例：{summary}）")
    else:
        print("  LLM: 不可用（运行时将回退英文简介）")
        ok = False

    print("检查桌面输出目录 ...")
    try:
        output_dir = choose_output_dir(logger)
        print(f"  输出目录: {output_dir}")
    except Exception as exc:
        print(f"  输出目录: 失败（{exc}）")
        ok = False
    print("检查完成：" + ("全部正常" if ok else "存在异常，请查看 logs\\app.log"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub 每日热门项目采集器")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--now", action="store_true", help="立即生成一份")
    group.add_argument("--check", action="store_true", help="检查环境")
    args = parser.parse_args(argv)

    console = sys.stdout is not None and sys.stderr is not None
    logger = setup_logging(console=console)
    run_started_at = dt.datetime.now()
    try:
        cfg = load_config()
    except Exception as exc:
        logger.exception("读取配置失败")
        write_run_state("failed", run_started_at, dt.datetime.now(), None, None, str(exc), logger)
        if console:
            print(f"读取配置失败：{exc}", file=sys.stderr)
        return 1

    try:
        if args.check:
            if not console:
                logger.warning("--check 需要在控制台运行")
                return 1
            return run_check(cfg, logger)
        path = run_generation(cfg, logger)
        if console:
            print(f"已生成：{path}")
        return 0
    except Exception as exc:
        logger.exception("执行失败")
        write_run_state("failed", run_started_at, dt.datetime.now(), None, None, str(exc), logger)
        if console:
            print(f"执行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

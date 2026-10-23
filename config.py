"""共享配置读取。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 100) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_schedule_time(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
    if not match:
        raise ValueError("SCHEDULE_TIME 必须是 HH:MM 格式，例如 09:00")
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class Config:
    top_n: int
    schedule_time: str
    task_name: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_proxy_dir: Path | None
    llm_proxy_autostart: bool
    trending_url: str
    request_timeout: int
    llm_timeout: int
    max_summary_chars: int

    @property
    def proxy_host(self) -> str:
        parsed = urlparse(self.llm_base_url)
        return parsed.hostname or "127.0.0.1"

    @property
    def proxy_port(self) -> int:
        parsed = urlparse(self.llm_base_url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)


def load_config() -> Config:
    schedule_time = os.getenv("SCHEDULE_TIME", "09:00").strip() or "09:00"
    parse_schedule_time(schedule_time)
    proxy_dir_raw = os.getenv("LLM_PROXY_DIR", "").strip()
    proxy_dir = Path(os.path.expandvars(os.path.expanduser(proxy_dir_raw))) if proxy_dir_raw else None
    return Config(
        top_n=_env_int("TOP_N", 10, 1, 50),
        schedule_time=schedule_time,
        task_name=os.getenv("TASK_NAME", "GitHubDailyTrending").strip() or "GitHubDailyTrending",
        llm_base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8788/v1").strip()
        or "http://127.0.0.1:8788/v1",
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "deepseek-v4.1-flash").strip() or "deepseek-v4.1-flash",
        llm_proxy_dir=proxy_dir,
        llm_proxy_autostart=_env_bool("LLM_PROXY_AUTOSTART", True),
        trending_url=os.getenv("GITHUB_TRENDING_URL", "https://github.com/trending?since=daily").strip()
        or "https://github.com/trending?since=daily",
        request_timeout=_env_int("REQUEST_TIMEOUT", 20, 5, 120),
        llm_timeout=_env_int("LLM_TIMEOUT", 60, 10, 300),
        max_summary_chars=_env_int("MAX_SUMMARY_CHARS", 30, 10, 100),
    )

# GitHub 每日热门项目采集器

每天 09:00 自动抓取 GitHub Trending 日榜 Top 10，用通俗中文一句话说明每个项目是干什么的，并在桌面生成一份 Markdown 文件。

仓库地址：<https://github.com/moliclay/github_top_search>

## 功能特性

- 每日定时：Windows 任务计划程序，09:00 后台执行。
- 一键控制：启动.bat 注册任务并立即生成；停止.bat 删除每日任务。
- 日榜采集：项目链接、简介、语言、今日新增 Star。
- 中文介绍：OpenAI 兼容接口，一句大白话，约 30 个汉字。
- 多重兜底：模型失败回退英文简介；简介为空时尝试读取 README。
- 稳定写入：临时文件 + 原子替换；同一天覆盖，不产生重复文件。
- 失败保护：GitHub 请求失败不覆盖已有文件。
- 日志轮转：logs/app.log。
- 隐私安全：API Key 只保存在本机 .env，不提交、不打日志。

## 输出示例

```markdown
# GitHub 每日热门项目 · 2026-10-23

> 数据来源：[GitHub Trending 日榜](https://github.com/trending?since=daily) · 每日 09:00 自动更新 · 共 10 个

| # | 项目 | 一句话介绍 | 语言 | 今日新增 |
|---|------|------------|------|----------|
| 1 | [php/php-src](https://github.com/php/php-src) | 解释执行 PHP 代码，让 PHP 程序运行起来。 | C | +287 |
| 2 | [supabase/supabase](https://github.com/supabase/supabase) | 帮你快速搭好应用后端，数据库、登录、存储都是现成的。 | TypeScript | +693 |

---
生成时间：2026-10-23 09:00:12
```

## 项目结构

```text
github_top_search/
├─ main.py              # 采集、生成简介、写 Markdown
├─ scheduler.py         # 安装/删除/查询 Windows 计划任务
├─ config.py            # .env 配置读取
├─ requirements.txt     # Python 依赖
├─ .env.example         # 配置模板（复制为 .env）
├─ .gitignore
├─ 启动.bat             # 注册每日任务并立即生成
├─ 停止.bat             # 停止并删除每日任务
├─ 状态.bat             # 查看任务状态和最近运行结果
├─ 检查环境.bat         # 检查 GitHub、模型和桌面写入权限
├─ README.md
└─ logs/                # 运行时生成
```

## 环境要求

- Windows 10 / Windows 11
- Python 3.10+（开发和验证使用 Python 3.13）
- 可访问 GitHub Trending
- 一个 OpenAI 兼容的 Chat Completions 接口
- 可选：workbuddy 本地代理（用于本地模型接口）

## 快速开始

1. 克隆仓库：`git clone https://github.com/moliclay/github_top_search.git`
2. 进入目录：`cd github_top_search`
3. 安装依赖：`python -m pip install -r requirements.txt`
4. 复制 `.env.example` 为 `.env`，填写接口地址、Key 和模型名。
5. 检查环境：`python main.py --check`
6. 启动每日任务：双击 `启动.bat`，或执行 `python scheduler.py start`
7. 停止每日任务：双击 `停止.bat`，或执行 `python scheduler.py uninstall`
8. 查看状态：双击 `状态.bat`，或执行 `python scheduler.py status`

## 配置说明

配置文件为项目根目录下的 `.env`。代码只从环境变量读取配置，`.env` 已被 `.gitignore` 忽略。

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_BASE_URL` | 否 | `http://127.0.0.1:8788/v1` | OpenAI 兼容接口地址，通常以 `/v1` 结尾 |
| `LLM_API_KEY` | 是 | 空 | 模型接口 Key；为空时使用英文简介兜底 |
| `LLM_MODEL` | 否 | `deepseek-v4.1-flash` | 模型名称 |
| `LLM_PROXY_DIR` | 否 | 空 | workbuddy 代理目录；为空则不自动拉起 |
| `LLM_PROXY_AUTOSTART` | 否 | `true` | 接口端口未监听时是否自动启动本地代理 |
| `TOP_N` | 否 | `10` | 每天采集数量，建议 1-50 |
| `SCHEDULE_TIME` | 否 | `09:00` | 每日执行时间，格式 `HH:MM` |
| `TASK_NAME` | 否 | `GitHubDailyTrending` | Windows 计划任务名称 |
| `GITHUB_TRENDING_URL` | 否 | `https://github.com/trending?since=daily` | 采集地址 |
| `REQUEST_TIMEOUT` | 否 | `20` | GitHub 请求超时秒数 |
| `LLM_TIMEOUT` | 否 | `60` | 模型请求超时秒数 |
| `MAX_SUMMARY_CHARS` | 否 | `30` | 中文简介目标长度 |

常用配置示例：

- 本地 workbuddy 代理：`LLM_BASE_URL=http://127.0.0.1:8788/v1`、`LLM_MODEL=deepseek-v4.1-flash`、`LLM_PROXY_DIR=你的代理目录`、`LLM_PROXY_AUTOSTART=true`。
- DeepSeek 官方接口：`LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_MODEL=deepseek-chat`、`LLM_PROXY_AUTOSTART=false`。

修改 `TOP_N` 或 `SCHEDULE_TIME` 后，需要重新双击 `启动.bat`，让计划任务使用新配置。

## 命令行

| 命令 | 作用 |
|------|------|
| `python main.py --now` | 立即生成一份 Markdown |
| `python main.py --check` | 检查 GitHub、模型和桌面写入 |
| `python scheduler.py start` | 注册任务并立即生成 |
| `python scheduler.py install` | 只注册任务，不立即生成 |
| `python scheduler.py status` | 查看任务状态、上次运行和下次运行时间 |
| `python scheduler.py uninstall` | 停止并删除任务 |
| `python scheduler.py stop` | `uninstall` 的别名 |

## 定时任务说明

`scheduler.py` 优先使用 PowerShell 的 `Register-ScheduledTask` 注册任务，失败时回退到 `schtasks`。

任务配置：

- 任务名：`GitHubDailyTrending`（可通过 `TASK_NAME` 修改）
- 执行时间：每天 `SCHEDULE_TIME`，默认 09:00
- 执行程序：当前 Python 对应的 `pythonw.exe`，无控制台窗口
- 执行脚本：项目根目录的 `main.py`
- 工作目录：项目根目录
- 错过时间：启用 `StartWhenAvailable`，下一次登录/开机后补跑
- 电池供电：允许运行
- 重复实例：`IgnoreNew`
- 超时：15 分钟

任务只能按当前 Windows 用户登录后运行，不是 Windows 服务。如果 9 点电脑关机或用户未登录，任务会在下次开机登录后补跑。

双击 `启动.bat` 会重新注册任务并立即生成当天文件；双击 `停止.bat` 会删除每日任务。停止后再次双击 `启动.bat` 即可恢复。

查看任务状态：

`python scheduler.py status`

正常输出示例：

```text
TASK_NAME=GitHubDailyTrending
STATE=Ready
LAST_RUN=尚未运行
LAST_RESULT=尚未运行
NEXT_RUN=2026-10-25 09:00:00
APP_LAST_RUN=2026-10-24 09:26:41
APP_LAST_STATUS=success
APP_PROJECT_COUNT=8
APP_LAST_OUTPUT=C:\Users\33051\Desktop\GitHub每日热门_2026-10-24.md
SUMMARY=每日任务已安装，下次运行 2026-10-25 09:00:00
```

重新注册任务后，Windows 的 `LAST_RUN` 可能显示“尚未运行”，这是正常的；`APP_LAST_RUN` 来自 `logs/last_run.json`，会保留最近一次实际运行结果。

## 代理自动拉起

如果 `LLM_BASE_URL` 指向本机地址（如 `http://127.0.0.1:8788/v1`），运行前会检查端口：

1. 端口已监听：直接调用模型。
2. 端口未监听且 `LLM_PROXY_AUTOSTART=true`：使用 `LLM_PROXY_DIR` 下的 `python\pythonw.exe` 启动 `wb_proxy.py --port 8788`，最多等待 30 秒。
3. 仍不可用：回退 GitHub 英文简介，不影响当天 Markdown 生成。

使用 workbuddy 代理时，将 `LLM_PROXY_DIR` 指向代理目录，并设置 `LLM_PROXY_AUTOSTART=true`。不使用本地代理时，将 `LLM_PROXY_DIR` 留空，并设置 `LLM_PROXY_AUTOSTART=false`。代理本身不在本仓库中，需要自行安装并完成账号配置。

## 日志与排错

日志文件：`logs/app.log`，按 1 MB 轮转，保留 3 份备份。最近一次程序运行结果保存在 `logs/last_run.json`，`状态.bat` 会同时显示 Windows 任务状态和程序最近一次运行结果。

### 桌面没有生成文件

1. 执行 `python main.py --check` 查看具体失败项。
2. 查看 `logs/app.log`。
3. 如果桌面不可写，文件会退回到项目目录下的 `output/`。

### 计划任务没有运行

执行 `python scheduler.py status`，确认：

- `STATE` 是否为 `Ready`；
- `NEXT_RUN` 是否为下一个 09:00；
- 当前 Windows 用户是否已登录；
- 电脑是否在 9 点处于开机状态。

### 模型调用失败

检查 `.env` 中的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。如果使用本地代理，确认端口 8788 可访问，或让 `LLM_PROXY_AUTOSTART=true` 自动拉起。

### GitHub 页面解析失败

GitHub Trending 没有官方 API，页面结构可能变化。解析逻辑在 `main.py` 的 `parse_trending()` 中，可根据新结构调整 XPath。

### Python 命令找不到

先执行 `python --version` 确认 Python 已加入 PATH。如果没有输出，请安装 Python 3.10+，或在 `启动.bat` / `停止.bat` 中把 `python` 改成完整路径。

## 安全说明

- `.env` 已加入 `.gitignore`，不要提交 API Key。
- 程序不会把 Key 写入日志。
- 建议使用单独的、有限额的 API Key。
- 程序只读取 GitHub Trending 公共页面，并将项目名称/简介发送到你配置的模型接口，不采集个人隐私数据。
- 公开仓库中只保留 `.env.example`，不包含任何真实 Key。

## 开发与验证

基础检查：

`python -m py_compile config.py main.py scheduler.py`

`python main.py --check`

`python main.py --now`

`python scheduler.py status`

验证模型兜底逻辑时，可以临时把 `LLM_BASE_URL` 指向错误端口，并设置 `LLM_PROXY_AUTOSTART=false`，然后执行 `python main.py --now`。文件应正常生成，并出现英文简介兜底说明。

验证 GitHub 请求失败保护时，可以临时把 `GITHUB_TRENDING_URL` 指向不可访问地址，再执行 `python main.py --now`。此时应退出码为 1，并且不覆盖桌面已有文件。

## 卸载

1. 双击 `停止.bat` 删除计划任务。
2. 删除项目目录。
3. 如需清理，手动删除桌面上的 `GitHub每日热门_*.md` 和项目下的 `logs/`。

## 免责声明

本项目用于个人学习与效率工具场景。GitHub Trending 的页面结构和可用性由 GitHub 控制；模型生成的项目介绍可能存在不准确之处，请以项目主页为准。

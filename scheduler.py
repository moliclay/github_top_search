"""Windows 计划任务管理。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config import BASE_DIR, Config, load_config, parse_schedule_time

PYTHONW = Path(sys.executable).with_name("pythonw.exe")
if not PYTHONW.exists():
    PYTHONW = Path(sys.executable)
MAIN_PY = BASE_DIR / "main.py"


def ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )


def print_result(result: subprocess.CompletedProcess) -> None:
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if output:
        print(output)
    if error:
        print(error, file=sys.stderr)


def install_task(cfg: Config) -> int:
    try:
        hour, minute = parse_schedule_time(cfg.schedule_time)
    except ValueError as exc:
        print(f"计划时间配置错误：{exc}", file=sys.stderr)
        return 1
    if not MAIN_PY.exists():
        print(f"找不到主程序：{MAIN_PY}", file=sys.stderr)
        return 1
    at = f"{hour:02d}:{minute:02d}"
    script = f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$taskName = {ps_quote(cfg.task_name)}
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute {ps_quote(str(PYTHONW))} -Argument {ps_quote(f'"{MAIN_PY}"')} -WorkingDirectory {ps_quote(str(BASE_DIR))}
$trigger = New-ScheduledTaskTrigger -Daily -At {ps_quote(at)}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description '每天 09:00 生成 GitHub 热门项目 Markdown 到桌面' -Force | Out-Null
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("TASK_NAME=" + $task.TaskName)
Write-Output ("STATE=" + $task.State)
Write-Output ("NEXT_RUN=" + $info.NextRunTime)
"""
    try:
        result = run_powershell(script)
        if result.returncode == 0:
            print_result(result)
            return 0
        print("PowerShell 注册计划任务失败，尝试 schtasks 回退。", file=sys.stderr)
        print_result(result)
    except Exception as exc:
        print(f"PowerShell 注册计划任务失败：{exc}", file=sys.stderr)
    return install_task_schtasks(cfg, at)


def install_task_schtasks(cfg: Config, at: str) -> int:
    task_run = f'"{PYTHONW}" "{MAIN_PY}"'
    command = [
        "schtasks",
        "/Create",
        "/TN",
        cfg.task_name,
        "/TR",
        task_run,
        "/SC",
        "DAILY",
        "/ST",
        at,
        "/F",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode == 0:
            print((result.stdout or "").strip())
            return 0
        print((result.stderr or result.stdout or "").strip(), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"schtasks 注册失败：{exc}", file=sys.stderr)
        return 1


def status_task(cfg: Config) -> int:
    script = f"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$taskName = {ps_quote(cfg.task_name)}
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {{ Write-Output 'NOT_INSTALLED'; exit 0 }}
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("TASK_NAME=" + $task.TaskName)
Write-Output ("STATE=" + $task.State)
Write-Output ("LAST_RUN=" + $info.LastRunTime)
Write-Output ("LAST_RESULT=" + $info.LastTaskResult)
Write-Output ("NEXT_RUN=" + $info.NextRunTime)
"""
    try:
        result = run_powershell(script)
        if result.returncode != 0:
            print_result(result)
            return 1
        print((result.stdout or "").strip())
        return 0
    except Exception as exc:
        print(f"查询计划任务失败：{exc}", file=sys.stderr)
        return 1


def uninstall_task(cfg: Config) -> int:
    script = f"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$taskName = {ps_quote(cfg.task_name)}
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {{ Write-Output 'STILL_EXISTS'; exit 1 }}
Write-Output 'REMOVED'
"""
    try:
        result = run_powershell(script)
        if result.returncode == 0:
            print((result.stdout or "").strip())
            return 0
        print_result(result)
    except Exception as exc:
        print(f"PowerShell 删除计划任务失败：{exc}", file=sys.stderr)
    return uninstall_task_schtasks(cfg)


def uninstall_task_schtasks(cfg: Config) -> int:
    subprocess.run(
        ["schtasks", "/End", "/TN", cfg.task_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", cfg.task_name, "/F"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    query = subprocess.run(
        ["schtasks", "/Query", "/TN", cfg.task_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if query.returncode != 0:
        print("REMOVED")
        return 0
    print((result.stderr or result.stdout or "").strip(), file=sys.stderr)
    return 1


def start(cfg: Config) -> int:
    rc = install_task(cfg)
    if rc != 0:
        print("计划任务注册失败，未执行生成。", file=sys.stderr)
        return rc
    print("正在生成今天的 GitHub 热门项目...")
    result = subprocess.run(
        [sys.executable, str(MAIN_PY), "--now"],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        print(
            "今天的生成失败，请查看 logs\\app.log；每日任务仍已注册。",
            file=sys.stderr,
        )
        return result.returncode
    print(f"启动完成：每天 {cfg.schedule_time} 自动生成，文件在桌面。")
    return 0


def stop(cfg: Config) -> int:
    rc = uninstall_task(cfg)
    if rc == 0:
        print("已停止并删除每日任务。")
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub 每日热门项目计划任务管理")
    parser.add_argument(
        "command",
        choices=["start", "stop", "install", "uninstall", "status"],
    )
    args = parser.parse_args(argv)
    try:
        cfg = load_config()
    except Exception as exc:
        print(f"读取配置失败：{exc}", file=sys.stderr)
        return 1
    if args.command == "start":
        return start(cfg)
    if args.command == "stop":
        return stop(cfg)
    if args.command == "install":
        return install_task(cfg)
    if args.command == "uninstall":
        return uninstall_task(cfg)
    return status_task(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

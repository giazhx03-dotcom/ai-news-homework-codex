#!/usr/bin/env python3
"""管理本项目唯一的用户级 LaunchAgent。"""
import argparse
import hashlib
import os
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "local.ai-news.codex." + hashlib.sha256(os.fsencode(ROOT)).hexdigest()[:12]
DOMAIN = f"gui/{os.getuid()}"
SERVICE = DOMAIN + "/" + LABEL
PLIST = ROOT / "scheduling" / (LABEL + ".plist")
AGENT = Path.home() / "Library" / "LaunchAgents" / PLIST.name
CTL = "/bin/launchctl"


def generate():
    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise SystemExit("请先运行 /usr/bin/python3 -m venv .venv")
    if not Path("/etc/localtime").resolve().as_posix().endswith("/Asia/Singapore"):
        raise SystemExit("本配置按本地日历触发，请先确认 macOS 系统时区为 Asia/Singapore")
    logs = ROOT / "outputs" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    job = plistlib.loads((ROOT / "scheduling" / "daily.plist.in").read_bytes())
    job.update(Label=LABEL, ProgramArguments=[str(python), str(ROOT / "news.py"), "--scheduled"],
               WorkingDirectory=str(ROOT), StandardOutPath=str(logs / "launchd.stdout.log"),
               StandardErrorPath=str(logs / "launchd.stderr.log"))
    content = plistlib.dumps(job)
    if not PLIST.exists() or PLIST.read_bytes() != content:
        tmp = PLIST.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(PLIST)
    print(PLIST, flush=True)


def owned():
    return AGENT.is_symlink() and AGENT.resolve() == PLIST


def loaded():
    return subprocess.run([CTL, "print", SERVICE], capture_output=True).returncode == 0


def command(*args):
    subprocess.run([CTL, *args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "install", "status", "trigger", "disable", "uninstall"])
    action = parser.parse_args().action
    if action == "generate":
        generate()
        return
    if action == "status":
        print(f"启动项 {LABEL}\n登录注册 {AGENT} -> {owned()}", flush=True)
        command("print", SERVICE)
        return
    if (AGENT.exists() or AGENT.is_symlink()) and not owned():
        raise SystemExit("同名启动项已被其他文件使用，已停止操作")
    if action == "install":
        generate()
        if loaded() and not owned():
            raise SystemExit("同名服务已注册，无法确认归属")
        AGENT.parent.mkdir(parents=True, exist_ok=True)
        if not owned():
            AGENT.symlink_to(PLIST)
        command("enable", SERVICE)
        if not loaded():
            command("bootstrap", DOMAIN, str(AGENT))
    elif not owned():
        raise SystemExit("当前项目尚未安装启动项")
    elif action == "trigger":
        command("kickstart", SERVICE)
    else:
        command("disable", SERVICE)
        if loaded():
            command("bootout", SERVICE)
        if action == "uninstall":
            AGENT.unlink()


if __name__ == "__main__":
    main()

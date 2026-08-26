from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "9.2.2"


def say(text: str = "") -> None:
    print(text, flush=True)


def main() -> int:
    say("=" * 58)
    say(f" FundScope {VERSION} - Windows 停止工具")
    say("=" * 58)
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    script = ROOT / "scripts" / "prepare_ports.ps1"
    if not ps or not script.exists():
        say("无法调用 PowerShell，未自动停止服务。")
        return 1
    completed = subprocess.run([
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Root",
        str(ROOT),
    ])
    if completed.returncode == 0:
        say("FundScope 本地服务已停止，或当前没有正在运行的服务。")
        return 0
    if completed.returncode == 2:
        say("8000 或 5173 端口由其他程序占用。为避免误杀其他程序，已停止操作。")
        return 2
    say("未能自动停止 FundScope 服务。")
    return completed.returncode or 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say("停止操作已取消。")
        raise SystemExit(130)

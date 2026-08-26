from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
SERVICE_HELPER = ROOT / "scripts" / "service_console_windows.py"
API_URL = "http://127.0.0.1:8000"
WEB_URL = "http://127.0.0.1:5173"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "9.2.2"
ROLE = os.environ.get("FUNDSCOPE_ROLE", "maintainer")
ROLE_LABEL = "研究角色" if ROLE.lower() == "analyst" else "维护角色"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass


def say(text: str = "") -> None:
    print(text, flush=True)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    say("  > " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def prepare_ports() -> None:
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    script = ROOT / "scripts" / "prepare_ports.ps1"
    if ps and script.exists():
        completed = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Root", str(ROOT)],
            text=True,
        )
        if completed.returncode == 2:
            raise RuntimeError("8000 或 5173 端口被其他程序占用。为避免误杀其他程序，启动已停止。")
        if completed.returncode != 0:
            raise RuntimeError("端口检查未完成。请运行 DIAGNOSE_WINDOWS.bat 查看详细结果。")
    elif port_open(8000) or port_open(5173):
        raise RuntimeError("8000 或 5173 端口已被占用，而且无法调用 PowerShell 自动检查。")


def ensure_backend() -> None:
    if not VENV_PY.exists():
        say("[2/6] 首次运行：正在创建 Python 运行环境...")
        run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
    check=subprocess.run([str(VENV_PY),"-c","import fastapi,uvicorn,pandas"],cwd=str(BACKEND),capture_output=True) if VENV_PY.exists() else None
    if check is None or check.returncode!=0:
        say("[2/6] 正在安装或修复 Python 依赖...")
        run([str(VENV_PY), "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")])
    else:say("[2/6] Python 运行环境已就绪。")


def ensure_frontend() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    node = shutil.which("node.exe") or shutil.which("node")
    if not node or not npm:
        raise RuntimeError("未检测到 Node.js / npm。请安装 Node.js 22 LTS。")
    try:
        version=subprocess.check_output([node,"-v"],text=True,stderr=subprocess.STDOUT).strip()
        major=int(version.lstrip("vV").split(".",1)[0])
    except Exception:
        version="unknown";major=0
    if major!=22:
        raise RuntimeError(f"FundScope v{VERSION} 需要 Node.js 22 LTS。当前版本：{version}。请安装 Node.js 22 后重新运行 START_WINDOWS.bat。")
    vite=FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.exists():
        say("[3/6] 正在安装或修复网页端依赖，首次运行可能需要几分钟...")
        run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)
    else:say("[3/6] 网页端依赖已就绪。")


def start_service_console(service: str) -> subprocess.Popen:
    if not SERVICE_HELPER.exists():
        raise RuntimeError(f"缺少 Windows 服务启动脚本：{SERVICE_HELPER}")
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    cmd = [sys.executable, str(SERVICE_HELPER), service]
    if service == "api":
        cmd.extend(["--role", ROLE])
    # Important: launch a Python helper directly. Do not wrap the command in
    # `cmd.exe /k` because nested quotes break when the project path contains
    # spaces or localized characters.
    return subprocess.Popen(cmd, cwd=str(ROOT), creationflags=flags, env=os.environ.copy())


def wait_http(url: str, timeout: float, process: subprocess.Popen | None = None) -> bool:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=4.0) as resp:
                if 200 <= resp.status < 300:
                    return True
                last_error = f"HTTP {resp.status}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.75)
    if last_error:
        say(f"就绪检查未通过：{last_error}")
    return False


def start_services() -> None:
    say("[4/6] 正在启动接口服务...")
    api_proc = start_service_console("api")
    if not wait_http(f"{API_URL}/api/health", 75.0, api_proc):
        raise RuntimeError(f'接口服务没有成功启动。请查看新打开的“FundScope 接口服务 {VERSION}”窗口；也可以运行 DIAGNOSE_WINDOWS.bat。')

    say("[5/6] 正在启动网页端...")
    web_proc = start_service_console("web")
    if not wait_http(WEB_URL, 45.0, web_proc):
        raise RuntimeError(f'网页端没有成功启动。请查看新打开的“FundScope 网页端 {VERSION}”窗口；也可以运行 DIAGNOSE_WINDOWS.bat。')

    say("[6/6] 启动完成，正在打开浏览器...")
    webbrowser.open(WEB_URL)


def main() -> int:
    say("=" * 62)
    say(f" FundScope v{VERSION}  |  {ROLE_LABEL}")
    say("=" * 62)
    say(f"项目目录：{ROOT}")
    say()

    if os.name != "nt":
        raise RuntimeError("这个启动器仅用于 Windows。")

    say("[1/6] 正在检查端口与旧进程...")
    prepare_ports()
    ensure_backend()
    ensure_frontend()
    start_services()
    say()
    say("FundScope 已正常启动。")
    say(f"网页端：{WEB_URL}")
    say(f"接口端：{API_URL}")
    say("这个启动器窗口现在可以关闭，接口服务和网页端窗口请保持运行。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say("\n启动已取消。")
        raise SystemExit(130)
    except Exception as exc:
        say()
        say("=" * 62)
        say("启动失败")
        say(str(exc))
        say("=" * 62)
        say("可以运行 DIAGNOSE_WINDOWS.bat 获取完整环境诊断。")
        raise SystemExit(1)

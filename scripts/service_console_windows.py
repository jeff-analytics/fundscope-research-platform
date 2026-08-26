from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "9.2.2"


def set_title(title: str) -> None:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def hold_on_failure(message: str, code: int = 1) -> int:
    print("", flush=True)
    print("=" * 68, flush=True)
    print(message, flush=True)
    print("请保留此窗口，错误信息也会用于启动器判断。", flush=True)
    print("=" * 68, flush=True)
    try:
        input("按 Enter 键关闭此窗口...")
    except Exception:
        pass
    return code


def run_api(role: str) -> int:
    set_title(f"FundScope 接口服务 {VERSION}")
    if not VENV_PY.exists():
        return hold_on_failure(f"未找到 Python 运行环境：{VENV_PY}")
    env = os.environ.copy()
    env["FUNDSCOPE_ROLE"] = role
    print(f"FundScope 接口服务正在启动 | 角色：{role}", flush=True)
    print(f"项目目录：{ROOT}", flush=True)
    cmd = [
        str(VENV_PY),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--no-access-log",
    ]
    try:
        result = subprocess.run(cmd, cwd=str(BACKEND), env=env)
    except Exception as exc:
        return hold_on_failure(f"接口服务启动失败：{exc}")
    if result.returncode != 0:
        return hold_on_failure(f"接口服务已退出，退出码：{result.returncode}", result.returncode)
    return 0


def run_web() -> int:
    set_title(f"FundScope 网页端 {VERSION}")
    node = shutil.which("node.exe") or shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node:
        return hold_on_failure("未检测到 Node.js。请安装 Node.js 22 LTS。")
    if not vite.exists():
        return hold_on_failure(f"未找到 Vite：{vite}。请重新运行 START_WINDOWS.bat 安装网页端依赖。")
    print("FundScope 网页端正在启动", flush=True)
    print(f"项目目录：{ROOT}", flush=True)
    cmd = [str(node), str(vite), "--host", "127.0.0.1", "--port", "5173"]
    try:
        result = subprocess.run(cmd, cwd=str(FRONTEND), env=os.environ.copy())
    except Exception as exc:
        return hold_on_failure(f"网页端启动失败：{exc}")
    if result.returncode != 0:
        return hold_on_failure(f"网页端已退出，退出码：{result.returncode}", result.returncode)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["api", "web"])
    parser.add_argument("--role", default="maintainer")
    args = parser.parse_args()
    if os.name != "nt":
        print("此服务控制台仅用于 Windows。", flush=True)
        return 2
    if args.service == "api":
        return run_api(args.role)
    return run_web()


if __name__ == "__main__":
    raise SystemExit(main())

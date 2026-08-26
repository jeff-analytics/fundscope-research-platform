from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "9.2.2"


def ok(label: str, detail: str = "") -> None:
    print(f"[通过] {label}" + (f"：{detail}" if detail else ""), flush=True)


def bad(label: str, detail: str = "") -> None:
    print(f"[异常] {label}" + (f"：{detail}" if detail else ""), flush=True)


def info(label: str, detail: str = "") -> None:
    print(f"[信息] {label}" + (f"：{detail}" if detail else ""), flush=True)


def port_owner(port: int) -> str:
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return "无法调用 PowerShell"
    script = (
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue;"
        "if($c){$p=$c[0].OwningProcess;$x=Get-CimInstance Win32_Process -Filter \"ProcessId=$p\";"
        "Write-Output ($p.ToString()+' | '+[string]$x.Name+' | '+[string]$x.CommandLine)}"
    )
    cp = subprocess.run([ps, "-NoProfile", "-Command", script], capture_output=True, text=True, errors="replace")
    return cp.stdout.strip() or "空闲"




def probe_http(label: str, url: str, timeout: float = 5.0) -> None:
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(url,timeout=timeout) as resp:
            body=resp.read(600).decode("utf-8",errors="replace").strip().replace("\n"," ")
            elapsed=(time.perf_counter()-started)*1000
            if 200 <= resp.status < 300:
                ok(label,f"HTTP {resp.status} | {elapsed:.0f} ms | {body[:260]}")
            else:
                bad(label,f"HTTP {resp.status} | {elapsed:.0f} ms | {body[:260]}")
    except Exception as exc:
        elapsed=(time.perf_counter()-started)*1000
        bad(label,f"{elapsed:.0f} ms | {exc}")

def main() -> int:
    print("=" * 68)
    print(f"FundScope {VERSION} Windows 环境诊断")
    print("=" * 68)
    info("项目目录", str(ROOT))
    info("系统", os.name)
    if os.name != "nt":
        bad("Windows", "当前系统不是 Windows")
        return 2
    ok("Windows")

    py = shutil.which("py.exe") or shutil.which("python.exe") or shutil.which("python")
    if py:
        ok("Python", py)
    else:
        bad("Python", "未找到")

    node = shutil.which("node.exe") or shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if node:
        try:
            ver = subprocess.check_output([node, "--version"], text=True, errors="replace").strip()
        except Exception:
            ver = "版本读取失败"
        ok("Node.js", f"{node} | {ver}")
    else:
        bad("Node.js", "未找到")
    if npm:
        ok("npm", npm)
    else:
        bad("npm", "未找到")

    if VENV_PY.exists():
        ok("Python 虚拟环境", str(VENV_PY))
        try:
            cp = subprocess.run(
                [str(VENV_PY), "-c", "import fastapi,uvicorn,pandas; print('FastAPI / Uvicorn / Pandas OK')"],
                cwd=str(BACKEND), capture_output=True, text=True, errors="replace", timeout=20,
            )
            if cp.returncode == 0:
                ok("后端核心依赖", cp.stdout.strip())
            else:
                bad("后端核心依赖", cp.stderr.strip() or f"退出码 {cp.returncode}")
        except Exception as exc:
            bad("后端核心依赖", str(exc))
    else:
        bad("Python 虚拟环境", "尚未创建")

    node_modules = FRONTEND / "node_modules"
    vite = node_modules / "vite" / "bin" / "vite.js"
    if node_modules.exists():
        ok("网页端依赖目录", str(node_modules))
    else:
        bad("网页端依赖目录", "尚未安装")
    if vite.exists():
        ok("Vite", str(vite))
    else:
        bad("Vite", "未找到")

    owners={}
    for port in (8000, 5173):
        owner = port_owner(port)
        owners[port]=owner
        if owner == "空闲":
            ok(f"端口 {port}", "空闲")
        else:
            info(f"端口 {port}", owner)

    if owners.get(8000) != "空闲":
        probe_http("接口就绪检查", "http://127.0.0.1:8000/api/health", 6.0)
    if owners.get(5173) != "空闲":
        probe_http("网页端就绪检查", "http://127.0.0.1:5173/", 6.0)

    helper = ROOT / "scripts" / "service_console_windows.py"
    if helper.exists():
        ok("服务启动助手", str(helper))
    else:
        bad("服务启动助手", "缺失")

    print("=" * 68)
    print("诊断结束。若仍无法启动，请把本窗口完整截图发给我。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

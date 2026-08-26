# Windows 启动修复（V9.0.1）

本修复针对 Windows `cmd.exe` 批处理文件编码兼容问题。

- 所有 `.bat` 启动/停止/测试入口改为 **纯 ASCII + CRLF**，避免中文 UTF-8 批处理被 `cmd.exe` 错误解析为命令。
- 中文启动状态与错误说明移到 Python 启动器输出。
- PowerShell 端口检查脚本改为 ASCII，兼容 Windows PowerShell 5.1。
- 新增 `scripts/stop_windows.py`，停止服务时同样避免批处理中文编码问题。
- 保留 V9.0.1 的业务功能与数据库兼容性。

## 2026-08-25 runtime fix 2

The API/Web service consoles no longer use `cmd.exe /k` with an inline command string.
That pattern could break Windows command parsing when nested quoted paths were present and
produce `The filename, directory name, or volume label syntax is incorrect.`

V9.0.1 now launches a Python service-console helper directly with `CREATE_NEW_CONSOLE`.
The helper starts Uvicorn and Vite using argument lists, so project paths containing spaces
or localized characters do not need cmd.exe quote nesting.

A new `DIAGNOSE_WINDOWS.bat` checks Python, Node.js, npm, the venv, core backend packages,
Vite, and port ownership for 8000/5173.

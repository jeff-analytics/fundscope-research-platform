# Windows Runtime Fix 3 — V9.0.1

本修复针对大体量本地数据库下的启动误判。

- `/api/health` 现在只检查 API 进程就绪状态，不执行基金持仓、Fund Master、Security Master 等全库统计。
- 详细数据状态继续由 `/api/data/health` 提供，研究功能与数据口径不变。
- Windows 启动器只等待轻量就绪接口，避免 1GB 级 SQLite 数据库导致 60 秒启动超时。
- `DIAGNOSE_WINDOWS.bat` 会直接测试 `/api/health` 并显示 HTTP 状态和耗时。
- 已有 `~/.fundscope/fundscope.db` 不迁移、不删除、不重采。

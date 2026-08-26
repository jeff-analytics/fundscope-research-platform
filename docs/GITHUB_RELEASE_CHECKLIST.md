# FundScope GitHub 发布检查

上传仓库前建议确认：

- 不提交 `.venv/`、`node_modules/`、`dist/`、`.pytest_cache/`。
- 不提交用户本地数据库或 `~/.fundscope` 目录。
- 不提交 `.env`、日志和本机运行时文件。
- 仓库根目录保留 `README.md`、`VERSION`、`RELEASE_VALIDATION.txt`。
- Windows 用户使用 `START_WINDOWS.bat`；macOS 用户使用 `START_MAC.command`。
- 发布说明以 `docs/CHANGELOG_V9_1.md` 为准。
- GitHub Release 建议附源码 ZIP，不附用户数据库。

当前版本：9.1.0。

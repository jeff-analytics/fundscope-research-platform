# FundScope V9.0.4 更新记录

V9.0.4 在 V9.0.3 研究交互基础上集中处理本地大数据库的性能和读取稳定性。

## 数据层

- SQLite 读取增加 busy retry、mmap、page cache、WAL checkpoint 和 optimize。
- 新增 `idx_holdings_quarter_stock_fund`、`idx_holdings_fund_quarter_weight`、`idx_master_eligible_rep`。
- 分析数据写入会提升进程内 data revision，研究缓存按 revision 自动失效。
- 恢复快照后同样触发 revision 更新。

## 基金详情

- 删除未被前端使用的整份 `history` 重复载荷。
- 普通基金详情只查询行业映射，Security Master 的估值/成长/市值字段改为深度分析按需读取。
- 持仓与基金解析增加有界 TTL 缓存。
- Fund Master 健康检查由每次解析改为 5 分钟窗口。

## 同类研究

- Peer Lens 采用“先选 canonical share，再读 holdings”的两阶段查询。
- Holdings Similarity 采用 overlap candidate → canonical share → candidate portfolio 的窄查询。
- 同类定位和风格参考继续缓存。

## API / 前端

- FastAPI 开启 GZip。
- 响应增加 `Server-Timing`，超过 2 秒的请求继续写入本地日志。
- 前端 GET 请求去重、短时缓存、stale fallback 与最多 3 次临时错误重试。
- 数据任务成功后清理相关基金研究缓存。

## 视觉

- Sidebar 版本标记由“第 9.0.3 版”改为 `v9.0.4`。
- Onboarding 版本标记统一为 `FundScope v9.0.4`。

## 验证

- Backend: 42 tests passed。
- Python compileall: passed。
- 40 个 TS/TSX 文件 TypeScript 语法解析: 0 errors。
- Windows BAT: ASCII + CRLF + no BOM。

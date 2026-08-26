# V8.1.0

## Task Engine

- 新增 pause_requested 持久化字段。
- 新增任务暂停、继续、取消 API。
- queued / running / paused / cooling / success / error / cancelled / interrupted 状态统一。
- 长任务中的网络请求增加 cooperative checkpoint。

## Rate Limit

- 识别 Eastmoney `514 Frequency Capped`。
- 识别 HTTP 429 与常见 rate-limit 文本。
- 514/429 触发共享 cooldown，线程池停止派发新请求。
- 冷却时间按连续限频次数递增，最高 180 秒。
- 持仓接口使用更保守的基础请求间隔。
- 数据质量中的限频失败标记为 `rate_limited`。

## Collection Policy

- 新增统一 `collection_policy.py`。
- 稳健 / 标准 / 极速对不同数据任务采用不同并发数。
- 基金持仓默认 2 / 4 / 6 路。
- Security Master 默认 4 / 8 / 12 路。

## Frontend

- 任务按钮增加暂停 / 继续 / 取消。
- 最近任务表增加任务控制。
- 冷却状态直接显示剩余时间。
- 任务轮询改为：运行中约 2.5 秒，空闲约 15 秒，后台标签约 30 秒。
- 数据健康状态改为独立低频刷新。

## Startup

- Windows 启动前检查端口。
- 自动清理旧 FundScope 监听进程。
- 不自动结束非 FundScope 程序。
- 新增一键停止脚本。
- Uvicorn 关闭 access log，控制台不再被正常轮询刷屏。

# Task Engine V8.1

## 状态

`queued` 等待执行。

`running` 正在执行。

`paused` 用户主动暂停。数据库和已完成结果保留。

`cooling` 上游数据源限频，任务自动等待。冷却结束后自动回到 running。

`cancelled` 用户取消。

`interrupted` 应用被直接关闭导致任务中断。

## 暂停语义

FundScope 使用 cooperative pause。

暂停后：

1. 已经发送到上游的请求允许结束。
2. Worker 在下一次网络请求前执行 checkpoint。
3. 新请求不会继续派发。
4. 当前缓冲区在任务恢复或安全退出时继续处理。

这比直接杀线程安全，因为 Python 网络线程无法可靠地强制中止，同时 SQLite 需要保持事务完整。

## 东方财富限频

`514 Frequency Capped` 与 `429 Too Many Requests` 会触发共享冷却。

同一个任务内所有 Worker 共享 cooldown 状态，因此一条线程发现限频后，其他 Worker 在下一次请求前也会等待。

连续触发时冷却时间逐步增加：20s、40s、80s、160s，最高 180s。

## 取消

取消采用同样的 checkpoint。已经提交到 SQLite 的数据不回滚。未完成的任务以后可以通过增量采集补齐。

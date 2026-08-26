# V9.0.0 Changelog

## Research Workspace
- 新增“我的研究”。
- 持久化收藏夹、研究对象和研究笔记。
- 收藏夹支持新建、重命名、删除。
- 移出收藏支持撤回。
- 新增最近研究与访问次数。
- 新增操作审计记录。

## Monitor
- 基金可监控风格漂移、调仓强度、前十集中度、持仓延续率。
- 证券可监控覆盖基金数、覆盖变化、共识加速度、平均持仓权重。
- 新持仓/市场数据任务完成后自动重新评估。
- 触发记录按报告期去重。

## Explorer
- 基金、证券、基金经理三个横截面入口。
- 研究视图可保存、应用、删除、重置和导出 CSV。
- 基金经理新增行为地图与风格位置图。
- 表格与图表支持对象下钻和收藏。

## Fund Research
- 新增同类定位。
- 支持全部偏股基金、同基金类型、相近风格三类比较范围。
- 展示横截面百分位、四分位区间和透明相近基金距离。

## Navigation & UX
- Ctrl+K 全局搜索基金、基金经理与证券。
- 空搜索显示最近研究。
- Alt+1 至 Alt+6 快速导航，`?` 打开快捷键面板。
- 首次运行显示一次性功能引导，可永久关闭。
- 新增移动端底部导航。
- 新增全局 Toast 与撤回操作。
- 增加点击、hover、focus-visible 和对话框反馈。

## Permissions
- 默认 Maintainer 模式。
- 新增 Research Analyst 启动模式，隐藏数据中心并禁止数据维护写操作。
- 新增 `START_ANALYST_WINDOWS.bat` 和 `START_ANALYST_MAC.command`。

## Data
- 继续复用 V8.0/V8.1/V8.2 的 `.fundscope/fundscope.db`。
- 新增 Workspace / monitor / audit 表自动迁移。
- 不需要重新采集已有基金持仓。

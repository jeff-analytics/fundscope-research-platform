# FundScope V9.1 Benchmark Study

V9.1 在开发前重新对标九个已经商业化、持续维护的研究与投资工作台。目标不是复制视觉，而是提炼成熟产品已经验证过的信息架构、探索方式和性能策略。

## 1. Koyfin

参考：
- https://www.koyfin.com/features/custom-dashboards/
- https://www.koyfin.com/features/watchlists/
- https://www.koyfin.com/help/my-views/

重点学习：可保存视图、可复用列设置、自定义 Dashboard、Watchlist 与研究页面互通。FundScope 对应保留“我的研究”“已保存视图”“监控”，避免每次从头设置筛选条件。

## 2. Morningstar Direct

参考：
- https://admainnew.morningstar.com/directhelp/General/Product_Overview.htm
- https://admainnew.morningstar.com/directhelp/Reports/Style_Consistency_Report.htm

重点学习：基于持仓的风格分析、同类比较、历史风格轨迹、可变开始/结束日期。FundScope 的同类定位因此采用 P25/P50/P75 与当前百分位，不生成黑箱综合评分；季度研究支持历史切换。

## 3. FactSet Portfolio Analytics

参考：
- https://www.factset.com/solutions/portfolio-analytics

重点学习：预计算/缓存、数据验证、可定制分析视图、暴露和归因透明。FundScope 的重型横截面分析保持缓存与窄查询，页面只请求当前研究所需的数据。

## 4. LSEG Workspace

参考：
- https://www.lseg.com/en/data-analytics/products/workspace

重点学习：组合表现、风险、行业与证券驱动因素、风格分析置于同一研究工作台。FundScope 保持“基金 → 调仓 → 深度分析 → 同类 → 相似持仓”的连续下钻路径。

## 5. TradingView

参考：
- https://www.tradingview.com/support/folders/43000593094-stock-screener/
- https://www.tradingview.com/support/solutions/43000718804-how-to-create-save-and-update-a-custom-screen/

重点学习：筛选器模板、表格/图形视图、快速筛选、保存研究设置。FundScope 的研究探索和机构共识采用 preset + filter + chart + table 的组合，不把所有维度堆在一个大图里。

## 6. Finviz

参考：
- https://finviz.com/help/screener
- https://finviz.com/map

重点学习：高信息密度、快速筛选、地图概览、快速导航。FundScope 在横截面页优先给用户“先发现异常，再进入对象研究”的操作方式。

## 7. moomoo

参考：
- https://www.moomoo.com/us/manual/categories/1406
- https://www.moomoo.com/us/manual/topic-14-82

重点学习：Heat Map、Institutional Tracker、Most Held / Most Bought / Most Sold 等多入口探索。FundScope 的机构共识由单一 Sankey 改成覆盖变化地图、历史演化、行业变化、行业历史和状态筛选。

## 8. AlphaSense

参考：
- https://help.alpha-sense.com/hc/en-us/articles/41815509396371-Maximizing-Your-Monitoring-Tools-in-AlphaSense
- https://help.alpha-sense.com/hc/en-us/articles/41815267178899-Save-Searches-and-Create-Email-Alerts-in-AlphaSense

重点学习：Dashboard、Saved Search、Alert 的持续研究机制。FundScope 继续保留收藏、研究笔记、监控和最近研究，避免研究结果只存在于一次浏览会话中。

## 9. Longbridge Pro

参考：
- https://longbridge.com/desktop/zh-CN/

重点学习：桌面端快速响应、历史导航、异动追踪、热力图和多屏工作方式。FundScope V9.1 继续减少全表扫描、按页签懒加载，并优先使用本地缓存和报告期窄查询。

## V9.1 落地决策

1. 同类定位卡片压缩视觉密度，突出当前值、百分位和 P25/P50/P75，帮助文字移入 title 提示。
2. “相似度构成”升级为真实的“相似度拆解”，展示所选相似基金的三项实际指标、进度条和共同持仓。
3. 所有新分析数值统一按两位小数展示，避免浮点尾差进入 UI。
4. 机构共识从固定最新两个季度升级为任意“当前报告期 + 基准报告期”，并提供 4/8/12/20 季历史窗口。
5. 机构共识主视图取消巨型 Sankey，改成更适合扫描和比较的散点、趋势、分歧条形图和热力图。
6. 高共识、新共识、持续增强、高位退潮、共识减弱等状态全部由公开披露覆盖变化计算并透明展示，不使用综合 Opportunity Score。
7. 本地市场共识与行业历史最多读取最近 24 个报告期，兼顾探索深度与大数据库响应速度。

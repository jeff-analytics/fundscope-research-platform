# V7.1 Advanced Analytics

## Security Master

统一证券层只维护当前研究真正需要的静态和基本面特征：行业、市值、估值和成长。Momentum 已移除。

## Style Drift

Style Drift 使用四个核心维度：

- Size：按证券市值横截面百分位聚合。
- Value / Growth：综合 PB、PE 与营收/利润增长的横截面位置。
- Sector：比较行业配置分布和行业集中度的变化。
- Concentration：比较前十大披露持仓集中度。

最终漂移评分还会参考组合结构变化，用于识别季度之间较大的持仓更替。Momentum 不参与计算。

## Return Gap

Return Gap 比较基金真实净值收益与上期披露组合的估算收益贡献。需要时按单只基金补齐净值和证券复权行情。

季度披露可能仅覆盖 Top Holdings，因此输出同时提供持仓权重覆盖与可信度。

## Institutional Migration

Sankey 根据两个报告期行业配置的增减匹配生成，用于观察整体配置重心迁移。它是披露配置变化估计，不代表逐笔真实资金流向。

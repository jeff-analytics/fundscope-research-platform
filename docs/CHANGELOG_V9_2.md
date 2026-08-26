# FundScope V9.2.0

## Research Integrity

### Comparable Disclosure Engine

新增 `backend/app/disclosure.py`，统一处理季度披露范围。

- Q1 / Q3：Top 10 disclosure
- Q2 / Q4：Full disclosure when available
- 混合范围跨期：双方统一取 Top 10
- 两个完整披露期：允许 Full Portfolio 比较

该规则已经进入基金调仓、持仓延续、风格历史、排名轨迹、证券共识和证券详情。

### Comparable Institutional Cohort

Institutional Consensus 不再直接把两个报告期的市场汇总基金数做差。当前期与比较期先取均有有效披露的 Fund Master 交集，再计算：

- 当前基金覆盖数
- 上期基金覆盖数
- 当前覆盖率
- 上期覆盖率
- 覆盖率变化 pp
- 每季度平均变化

Acceleration 只在三期等距且拥有共同基金 cohort 时计算。

### Consensus Level + Trend

证券共识分为两个独立维度。

Level：高 / 中 / 低

Trend：新形成 / 增强 / 持续增强 / 稳定 / 弱化 / 退潮

因此高共识证券也可以同时处于弱化或退潮状态。

## Product Experience

- 研究页面增加 Data Context。
- Smart Money 以覆盖率作为主要横截面指标。
- 支持 Level 与 Trend 独立筛选。
- 支持证券共识下钻与 Fund Research 跳转。
- 本地存在有效数据时默认进入 Local Research。
- 数据中心形成有效持仓后自动切换 Local Research。
- 大于 300 行的 DataTable 使用窗口渲染。
- 研究指标默认显示两位小数。

## Data Quality

Fund Master 份额后缀识别扩展：

- A / C / E / I / H / Y
- A1 / C1 等编号份额
- 前端 / 后端收费份额
- 人民币 / 美元 / 港币份额保持币种边界，降低误合并风险

## Engineering

- 新增 `backend/app/consensus.py`，缩小 services 职责。
- 关键 Smart Money / Security Detail API 增加 TypeScript 类型。
- 关键后台失败增加 warning 日志。
- 根目录增加 `pyproject.toml`，可直接运行 pytest。
- 增加前端研究逻辑与格式化测试。
- 增加 GitHub Actions。
- 增加 MIT License。
- `.gitignore` 清理 `*.tsbuildinfo` 和 coverage。
- Node 基准统一为 22，前端 direct dependencies 固定精确版本。

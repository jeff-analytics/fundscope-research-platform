# FundScope

**中国公募基金持仓与机构行为研究平台**

FundScope 将公募基金季度披露数据转化为可连续研究的组合历史，用于分析基金如何调仓、基金经理如何改变配置，以及机构资金正在形成怎样的共识。

平台聚焦 **Portfolio Evolution、Manager Behavior 和 Institutional Consensus**，提供从市场发现、基金筛选到持仓下钻的完整研究过程。

---

## What FundScope Does

### 基金组合演变

以季度为时间轴研究一只基金的真实持仓变化。

* 核心持仓与 Top 10 变化
* 新进入与退出披露
* 持仓权重及排名轨迹
* 调仓强度与持仓延续率
* 行业配置变化
* 组合集中度
* 规模、价值成长与风格漂移
* 历史组合路径回放

用户可以直接切换报告期，观察组合如何从一个季度演变到下一个季度。

### 基金经理研究

将基金经理管理的多个产品放到统一视角下分析。

* 管理基金与任职关系
* 多基金共同重仓
* 长期行业偏好
* 风格位置与历史迁移
* 集中度和调仓特征
* 管理组合之间的一致性

用于判断某种配置特征来自单只基金，还是基金经理长期稳定的投资行为。

### 机构共识

从单只基金扩展到整个基金市场。

FundScope 跟踪证券在可比基金样本中的：

* 持有基金数量
* 机构覆盖率
* 覆盖率变化
* 新进入基金
* 退出基金
* 共识水平
* 共识趋势
* 历史覆盖轨迹

因此可以区分：

`高共识 · 持续增强`
`高共识 · 正在弱化`
`低共识 · 开始形成`

并可以继续下钻到具体基金，查看哪些机构正在驱动这种变化。

### Research Explorer

用于从全市场发现值得进一步研究的基金。

支持按照以下维度筛选和定位：

* 调仓强度
* Top 10 集中度
* 持仓延续率
* 行业集中度
* 风格漂移
* 规模风格
* 价值成长特征
* 基金公司与基金类型

除表格筛选外，还提供二维行为地图，用于识别异常基金、相似基金和风格迁移。

### 基金相似度

基金之间的相似性被拆解为可解释指标：

* 持仓相似度
* 权重重合
* 证券集合重合
* 共同证券

相似度结果可以直接下钻验证，而不是停留在单一评分。

---

## Research Methodology

基金季度披露的范围并不完全一致。

| 报告期     | 主要可观察持仓        |
| ------- | -------------- |
| Q1 / Q3 | 前十大重仓股         |
| Q2 / Q4 | 更完整的半年报 / 年报持仓 |

直接比较不同披露范围可能产生错误的调仓判断。

FundScope 因此区分两种研究口径：

**Top 10 Comparable**
用于连续季度比较，所有时期统一使用前十大披露持仓。

**Full Portfolio**
用于具有完整披露数据的报告期之间进行更深入的组合研究。

机构共识分析同时建立 **Comparable Fund Cohort**，只比较两个报告期均存在有效数据的基金主体，以降低样本覆盖变化对结果的影响。

---

## Local-first Research

FundScope 采用本地优先架构。

完整研究数据库保存在用户本机，与项目源码分离：

```text
~/.fundscope/fundscope.db
```

GitHub 仓库和 Release 不包含完整基金数据库。

用户可以通过 Data Center 完成：

* 基金基础信息同步
* 基金经理同步
* 季度持仓采集
* 市场报告同步
* Security Master 更新
* 增量采集
* 数据质量检查
* 数据快照与恢复

已有数据库可以在后续版本中继续复用。

---

## Tech Stack

| Layer         | Technology                |
| ------------- | ------------------------- |
| Frontend      | React · TypeScript · Vite |
| Visualization | Apache ECharts            |
| Data Table    | TanStack Table            |
| State         | Zustand                   |
| Backend       | FastAPI · Python          |
| Analytics     | pandas · NumPy            |
| Storage       | SQLite                    |
| Testing       | Pytest · Vitest           |
| CI            | GitHub Actions            |

项目针对大型本地数据库进行了查询缓存、批量计算、single-flight、GZip、页面预热和大表渲染优化。

---

## Quick Start

### Windows

Requirements:

```text
Python 3.11+
Node.js 22 LTS
```

下载最新 Release，解压后运行：

```text
START_WINDOWS.bat
```

FundScope 会自动启动后端服务和 Web 界面。

---

## Project Structure

```text
fundscope-research-platform/
├── backend/        # API、数据服务与研究计算
├── frontend/       # Web application
├── docs/           # 数据模型、研究方法与开发文档
├── scripts/        # 启动与诊断工具
├── README.md
├── LICENSE
└── START_WINDOWS.bat
```

---

## Data Notice

FundScope 基于公开基金披露和公开市场数据进行研究。

季度持仓具有披露滞后，部分报告期仅披露前十大持仓，因此平台展示的是**公开信息能够支持的组合变化**，不会将退出前十大直接解释为基金已经清仓。

FundScope 用于研究和数据分析，不构成投资建议。

## License

MIT License

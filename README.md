# FundScope Web V9.2.2

FundScope 是面向中国公募基金季度持仓研究的本地 Research Workspace。它把基金主体、基金经理、季度披露、证券持仓、风格变化和机构共识放在同一套研究工作区中，重点支持从市场发现到基金下钻的连续研究过程。

## V9.2.2

This release closes the final interaction and rendering issues found during real local-database use.

- Similar-fund drill-down now synchronizes the fund route and state on the same page.
- Research Explorer uses a dedicated horizontal object switcher that does not wrap labels vertically.
- Market Pulse asset allocation reads the complete locally collected quarterly history and adds dynamic zoom for long histories.
- Research scatter plots reserve explicit y-axis title space so labels are not clipped by panel headers.
- Institutional Consensus uses progressive loading: a fast market snapshot can render while the exact comparable Fund Master cohort is prepared in the background. History is loaded independently and no longer blocks the core page.
- Smart Money retry now always triggers a new request and cold-query work is single-flight cached.

## V9.2.1

本版重点解决真实大数据库下“点一次等很久、切页面整屏空白”的问题。研究功能继续沿用 V9.2.0 的可比披露口径与 Institutional Consensus。

- Research Explorer 改成批量横截面计算，减少逐基金 pandas 循环。
- 后端增加 single-flight，同一重计算被多个页面同时请求时只执行一次。
- Explorer / Security Explorer / Manager Explorer 使用更长缓存。
- 基金经理目录、详情、风格时间轴与持仓查询增加复用缓存。
- 基金经理交互研究默认读取最近 24 个报告期，避免每次点击扫描全部历史。
- 页面切换或季度更新时保留上一次成功结果，只显示轻量“正在更新”提示。
- 启动后会错峰预热研究探索、默认基金经理研究和机构共识。
- 启动自动判断 Local Research 改用轻量 `EXISTS` 检查，不再自动执行完整 Data Health 大表统计。
- Windows 启动器会在 npm install 前检查 Node.js 22，避免等待后才出现 EBADENGINE。

在 1,500 个 Fund Master、2 个季度、约 75,000 条持仓的合成性能回归中，Fund Explorer 首次计算从约 22.5 秒下降到约 2.2 秒；同一会话缓存命中后基本即时返回。真实 1GB 数据库仍会受 SSD、采集任务和数据覆盖影响。

V9.2.0 已完成的研究完整性改造继续保留，包括 Top 10 Comparable / Full Portfolio、可比基金 cohort、Consensus Level + Trend、Data Context、证券共识下钻和大表窗口渲染。

完整性能变更见 `docs/CHANGELOG_V9_2_1.md`；研究口径变更见 `docs/CHANGELOG_V9_2.md`。

## 技术栈

- React 19 + TypeScript + Vite
- FastAPI + Python 3.11
- Apache ECharts
- TanStack Table
- Zustand
- SQLite
- AKShare Provider

前端发布验证基准使用 Node.js 22。

## 数据位置

代码与用户数据分离。Windows 默认数据库：

```text
C:\Users\<用户名>\.fundscope\fundscope.db
```

升级代码不会删除或迁移数据库。V8/V9 已采集的持仓、Fund Master、Security Master、市场报告、收藏和监控数据可以继续复用。

## Windows 启动

解压后双击：

```text
START_WINDOWS.bat
```

停止服务：

```text
STOP_FUNDSCOPE_WINDOWS.bat
```

环境诊断：

```text
DIAGNOSE_WINDOWS.bat
```

第一次运行会创建 Python 虚拟环境并安装前端依赖。前端依赖已经固定到明确版本，`.npmrc` 会生成并维护 `package-lock.json`。

## 测试

项目根目录可直接运行：

```text
python -m pytest
```

Windows 也可以双击：

```text
RUN_TESTS.bat
```

`RUN_TESTS.bat` 会依次执行后端测试、前端测试和 production build。

## GitHub

仓库已包含 GitHub Actions。Push 或 Pull Request 会检查：

- Python 3.11 后端测试
- Node.js 22 前端测试
- Vite production build

不要提交：

- `.fundscope/`
- `*.db`
- `.venv/`
- `node_modules/`
- `dist/`
- `__pycache__/`
- `.pytest_cache/`
- `*.tsbuildinfo`
- 日志和覆盖率输出

## 研究语义

- Q1/Q3 通常按前十大持仓披露，Q2/Q4 可包含更完整组合。跨期分析会优先保证披露范围可比。
- 权重变化不能直接解释为真实资金净流入。
- “退出前十”只表示未继续出现在可比 Top 10 中，不能确认已经清仓。
- Full Portfolio 比较只在两个报告期均具有完整披露时使用。
- Institutional Consensus 是公开基金披露中的机构覆盖变化，不代表实时机构交易。
- 机构共识的变化率基于两期共同可用的基金主体 cohort。
- 相似度组成指标分别展示，不合成为黑箱评分。

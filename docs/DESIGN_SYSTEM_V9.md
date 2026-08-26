# FundScope V9 Design System

## 视觉原则

- 页面背景使用低对比冷灰，研究内容使用白色 Surface。
- 品牌蓝只用于导航、高价值操作和数据强调。
- 绿色与红色只用于金融语义上的增加/减少与成功/失败状态。
- 不使用霓虹色、重阴影、大面积渐变或营销化装饰。

## 字体

系统 UI 字体优先：
- macOS: PingFang SC / SF 系统字体
- Windows: Microsoft YaHei / Segoe UI
- 数字启用 tabular numerals

主要字号：
- 页面标题 24px
- 对象标题 17–20px
- 模块标题 14px
- 正文与表格 12–13px
- 辅助信息 10–12px

## 组件

- Panel: 10px 圆角、低对比边框、轻阴影。
- Button: 主操作、次操作、幽灵操作、危险操作四类。
- Modal / Drawer: 页面级遮罩、焦点边界和明确关闭操作。
- Toast: 成功、失败、信息三类，支持撤回动作。
- Table: sticky header、hover、数字对齐、行点击反馈。
- Chart: 统一字体、弱网格、tooltip 边界约束，避免标签被裁切。

## 状态体系

每个异步模块需要覆盖：
- Loading
- Empty
- Error
- Permission denied
- Success toast
- Failed toast

长任务另有：
- queued
- running
- paused
- cooling
- cancelled
- success
- error

## 响应式

- Desktop 保留左侧导航和宽研究区。
- 820px 以下隐藏 Sidebar，切换为底部五项导航。
- 表格和复杂图表允许横向滚动，避免压缩到不可读。

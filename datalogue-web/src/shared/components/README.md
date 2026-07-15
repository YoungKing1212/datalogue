# 共享组件

`src/shared/components` 承载跨页面、跨功能域复用且无业务状态机归属的基础展示组件。

## 当前边界

- `icons.jsx`：项目自有的轻量 SVG 图标库，只负责按 `name` 渲染图标，不读取路由、API、会话或 AgentScope 状态；不得接入第三方图标 CDN、API 或授权素材，图标规范以根目录 `DESIGN.md` 为准。

## 兼容入口

旧 `src/components/icons.jsx` 仅保留 re-export，避免一次性迁移所有历史页面组件。新代码应直接从 `src/shared/components/icons.jsx` 导入。

# src/app 应用壳规划

> G060 规划交付。当前只建立 `src/app` 的职责文档，不移动 `src/App.jsx`、`src/components/sidebar.jsx` 或任何路由页面源码。

## 当前归属

当前前端应用壳仍集中在 `datalogue-web/src/App.jsx`：

- `App`：装配 `AuthProvider`、`BrowserRouter`、`ErrorBoundary` 和登录/鉴权入口。
- `AppInner`：装配左侧栏、顶部栏、内容区路由、发布 Drawer、编辑弹窗和 Tweaks 面板。
- `TopBar`：读取 `useLocation()`，基于 `CRUMBS_MAP` 展示面包屑、发布按钮、搜索、通知和登录用户动作。
- `RequireAuth` / `RequireSuperuser`：承载登录态和管理员路由保护。
- `ErrorBoundary`：承载应用级错误兜底。
- `TWEAK_DEFAULTS`、`ACCENT_*` 和 density effect：承载应用级主题和调试面板默认值。

当前左侧导航仍在 `datalogue-web/src/components/sidebar.jsx`：

- `Sidebar`：读取 `useLocation()`、`useNavigate()` 和 `useAuth()`，维护导航分组、active 规则、用户管理可见性和新会话入口。
- 导航分组与 `CRUMBS_MAP` 暂未共享配置，后续迁移时需要先抽取公共导航元数据，避免侧栏和顶部栏路由名称漂移。

## 目标模块

后续真正拆分时，`src/app` 只承载应用壳和路由装配，不承载业务页面实现：

| 目标文件 | 目标职责 | 当前来源 |
| --- | --- | --- |
| `app-root.jsx` | 装配 `AuthProvider`、`BrowserRouter`、应用级 `ErrorBoundary`、登录路由和包裹主壳的 `RequireAuth`。 | `src/App.jsx` 的 `App`、`RequireAuth`、`ErrorBoundary` |
| `app-shell.jsx` | 装配 `Sidebar`、`TopBar`、内容区、发布 Drawer、编辑弹窗和 Tweaks 面板。 | `src/App.jsx` 的 `AppInner` |
| `routes.jsx` | 集中维护应用路由表、管理员路由保护和页面组件映射；`RequireSuperuser` 优先跟随这里。 | `src/App.jsx` 的 `<Routes>` 与 `RequireSuperuser` |
| `topbar.jsx` | 承载顶部栏 UI、面包屑选择和应用级动作。 | `src/App.jsx` 的 `TopBar` |
| `sidebar.jsx` | 承载应用导航壳；迁移期可先从 `components/sidebar.jsx` re-export。 | `src/components/sidebar.jsx` |
| `navigation.js` | 统一维护侧栏分组、路由 path、图标、权限和面包屑配置。 | `src/App.jsx` 的 `CRUMBS_MAP` 与 `Sidebar.groups` |
| `theme.js` | 维护应用级 tweak 默认值、主题色映射和全局 density 写入规则。 | `src/App.jsx` 的 `TWEAK_DEFAULTS`、`ACCENT_*` 和 effects |

## 迁移顺序

1. 先抽取纯配置：把 `CRUMBS_MAP` 和 `Sidebar.groups` 合并为 `navigation.js`，保留现有路由 path、图标、权限和文案。
2. 再抽取展示壳：先在 `src/app/sidebar.jsx` 中从 `../components/sidebar.jsx` re-export，待调用方收口后再移动 `Sidebar` 源码；`TopBar` 也按同样方式先建薄入口，再迁实现。
3. 再抽取路由表：把页面路由和 `RequireSuperuser` 收到 `routes.jsx`，`RequireAuth` 继续由 `app-root.jsx` 包裹主壳，保持 `/login`、`/chat/:id`、`/workbench/:threadId`、`/workbench/:threadId/:artifactRef` 等路径语义不变。
4. 最后抽取 `app-shell.jsx` / `app-root.jsx`：让 `src/App.jsx` 只作为兼容入口 re-export 或薄装配层。
5. 每一步都必须单独验证 lint/build/test；涉及真实 UI 行为时，再做桌面视口 smoke，确认侧栏 active、顶部面包屑、登录跳转和 Workbench 深链没有回归。

## 禁止边界

`src/app` 不应放入以下内容：

- 后端 DTO 字段清洗、SSE 事件解析或 assistant-ui message part 投影；这些仍属于 `src/api`、`src/assistant` 或后续 `src/features`。
- BI 查询算法、ArtifactCard 清洗、Workbench 恢复来源判定或 Agent Team 任务状态机。
- 通用 UI primitive 的内部状态；可复用组件仍归 `src/components`、`src/assistant-ui` 或后续 `src/shared`。
- 页面级业务状态和表单逻辑；具体功能页面后续应进入 `src/features/<domain>`。

## 验证要求

真正拆分源码时，最小验证集为：

- `npm run lint`
- `npm run build`
- `npm run test`
- 桌面视口 smoke：登录后进入 `/chat`、`/chat/:id`、`/workbench/:threadId`、`/workbench/:threadId/:artifactRef`、`/users` 非管理员跳转和侧栏 active 状态。

本次 G060 只新增规划文档，因此只需要验证文档存在、关键锚点可检索、diff 无尾随空白。

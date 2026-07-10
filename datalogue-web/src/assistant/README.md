# Assistant 适配边界

`src/assistant` 是 Datalogue 前端对后端对话协议、Agent Team 事件流和 Workbench 事件的适配层，不承载普通 Chat UI 实现。

## 允许放入

- runtime adapter：把 assistant-ui runtime 需要的线程、会话、消息历史能力接到 Datalogue 后端协议。
- API adapter：封装 Agent Team SSE、Workbench API、Workbench mount source 等后端接口访问。
- event adapter：把 Agent Team envelope、Workbench retention event 等后端或页面事件转成前端可消费的稳定结构。

## 禁止放入

- 普通 Chat 页面组件、消息气泡、Composer、ThreadList 等可见 UI 实现；这些归 `src/features/chat`。
- assistant-ui primitives 的视觉组合、message parts 渲染、安全展示组件；这些归 `src/assistant-ui`。
- BI 查询执行语义、SQL/schema/raw rows 展示或后端私有调试字段。

## 当前迁移状态

G061 后，`chat-adapter`、`thread-list-adapter`、`Thread`、`ThreadList`、`MyComposer`、`MyMessage` 的实现已迁入 `src/features/chat`，本目录下同名文件只保留 re-export。该兼容壳只限已存在的 Chat 迁移入口，不新增同类实现逻辑。后续调用方收口完成后，可以删除这些兼容壳。

`*.test.js(x)` 文件需要随对应功能文件一并迁入 `src/features/chat/__tests__` 或同等测试目录，再删除本目录旧测试文件。

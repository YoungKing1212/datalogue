# Chat 功能域

`src/features/chat` 是普通问数对话页的前端功能域，当前承载聊天页面入口、runtime adapter、线程列表 adapter 和 Message 可见层。

## 当前边界

- `chat-adapter.js`：把 Agent Team / 后端 SSE 流收敛为 assistant-ui 可消费的消息流和 metadata。
- `chat-page.jsx`：普通问数页面入口，负责 runtime 装配、URL 同步、数据集/模型选择和 AgentPanel 事件接线。
- `thread-list-adapter.js`：把 `/api/conversation` 会话接口适配为 assistant-ui thread list，包含本地草稿到后端会话的懒创建映射。
- `ThreadList.jsx`、`MyMessage.jsx`：普通 Chat 页面使用的线程列表和唯一消息展示实现；Thread/Composer 壳统一复用 `src/assistant-ui`。

## 懒创建会话

`thread-list-adapter.js` 中 `initialize()` 只注册本地 pending 映射，不立即请求后端创建空会话；真正的后端会话创建由 `ensureConversationForThread()` 在 `chat-adapter.js` 首条消息发送时触发。这样可以避免用户点击「新对话」但未发送消息时污染后端会话列表。

## 禁止边界

- 不在本目录实现 Workbench API、Workbench 恢复来源判定或 retention event 规则；这些仍留在 `src/assistant` 的 Workbench 边界。
- 不在本目录实现通用 assistant-ui primitives；可复用壳层仍归 `src/assistant-ui`。
- 不把后端 private SQL、schema、query_plan 或 raw rows 直接展示给用户。

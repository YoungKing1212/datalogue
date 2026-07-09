# Assistant UI 视觉边界

`src/assistant-ui` 是 Datalogue 对 assistant-ui 的视觉组件和 message parts 展示层，不拥有后端会话、Agent Team task 或 Workbench API 协议。

## 允许放入

- assistant-ui primitives 的项目级视觉组合，例如 Thread、ThreadList、Message、Composer、ActionBar。
- message parts 用户可见渲染，例如 reasoning、tool-call、artifact card、markdown、chart block 展示。
- 展示层安全过滤函数，例如 Markdown 转义、长文本截断、可见 ref 白名单、chart block 字段白名单；目标是防止 raw thinking、SQL、schema、query_plan、未清洗 raw rows 进入用户可见 UI。
- 纯 UI 状态或 props 组合，不产生后端副作用。

## 禁止放入

- `/api/conversation`、`/api/agent-team/tasks/stream`、Workbench API 等 HTTP/SSE 调用。
- Agent Team envelope 到业务事件的协议转换；这些归 `src/assistant` event adapter。
- Chat 业务功能域状态机、懒创建会话映射、ThreadList 后端同步；这些归 `src/features/chat`。
- 后端 private SQL、schema debug、query_plan raw dump 或未清洗查询行。

## 与 `src/features/chat` 的关系

`src/features/chat` 可以复用本目录的视觉组件和 message parts 展示能力，但业务会话、消息流、线程列表后端同步仍由 Chat feature 自己持有。若组件需要访问后端协议，先在 `src/assistant` 或对应 feature 中建立 adapter，再把清洗后的展示数据传入本目录。

协议层清洗（例如解析 Agent Team envelope、剥离后端事件结构、映射业务 metadata）归 `src/assistant` 或对应 feature；本目录只做展示层安全过滤和视觉呈现。当前精确文件名示例包括 `DatalogueThread`、`DatalogueThreadList`、`DatalogueMessage`、`DatalogueComposer`、`DatalogueActionBar`。

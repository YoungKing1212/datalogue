# assistant-ui 组件迁移验收清单

> 生成时间：2026-07-03 23:49
> 适用范围：配合《assistant-ui 组件迁移计划》执行 P0-P6 阶段验收。本文只定义验收证据、截图点、测试命令、风险扫描项和 P6 清理条件，不替代具体实现方案。

## 1. 验收目标

本清单用于保证 assistant-ui 组件迁移只改变组件承接方式，不改变 Datalogue Chat 的业务主链、用户可见信息边界和既有工作台体验。

验收时必须同时看四类证据：

- 页面证据：欢迎态、对话态、ThreadList、Workbench、窄屏布局的截图或录屏。
- 行为证据：新建对话、历史切换、发送、停止、复制、重试、查看详情、反馈等关键动作可用。
- 自动化证据：前端 lint、build、相关组件测试和 adapter 测试通过。
- 安全证据：用户可见层不暴露 SQL、schema、raw rows、query_plan、RepairPatch 主体、control plane 细节。

## 2. 现有结构快照

当前页面入口仍在 `datalogue-web/src/components/chat-page.jsx`：

- `AssistantRuntimeProvider` 使用 `useRemoteThreadListRuntime` 和 `useLocalRuntime`，运行时暂不迁移。
- 左侧使用 `datalogue-web/src/assistant/ThreadList.jsx`，承接 `ThreadListPrimitive`、本地草稿和历史会话切换。
- 中间使用 `datalogue-web/src/assistant/Thread.jsx`，承接 `ThreadPrimitive.Root`、`ThreadPrimitive.Messages` 和 `TraceProvider`。
- 输入区使用 `datalogue-web/src/assistant/MyComposer.jsx`，承接 `ComposerPrimitive`、Dataset chip、Model chip、发送和停止。
- 消息使用 `datalogue-web/src/assistant/MyMessage.jsx`，承接 markdown、reasoning、ArtifactCard、口径卡、反馈和详情面板。
- 右侧使用 `datalogue-web/src/components/workbench-panel.jsx`，由 `chat-page.jsx` 根据 thread id 挂载为 Workbench。

P0-P5 阶段可以保留这些旧入口作为兼容壳；P6 只能在新组件主路径稳定后再清理。

## 3. 样式基线

第一阶段迁移必须保留当前样式，不把组件迁移和视觉改版混在一起：

- 浅色 SaaS 工作台风格，页面以中性色背景和内容面板为主。
- 布局为左侧紧凑 ThreadList、中间 Chat 主区、右侧可选 Workbench。
- ThreadList、消息、卡片、输入区保持细边框、小圆角和紧凑间距。
- Dataset chip、Model chip、时间范围 chip、工具 chip 保持小尺寸、高信息密度。
- 状态强调以蓝色和绿色为主；失败、警告、阻断只在局部状态中使用，不改整体主题。
- WelcomeHero、composer、message、action bar、ArtifactCard、Workbench 的信息密度和布局节奏保持稳定。
- 消息区保留最终回答、artifact 和必要动作；执行时间线优先留在 Workbench，避免和“思考过程”重复。

截图对比时以 P0 基线截图为准；如果视觉变化不是本阶段目标，必须在 PR 中回退或单独拆成视觉 PR。

## 4. 阶段验收矩阵

| 阶段 | 验收证据 | 截图点 | 测试命令 | 风险扫描项 |
| --- | --- | --- | --- | --- |
| P0：样式基线和组件盘点 | 组件映射表已列出 `MyComposer`、`MyMessage`、`Thread`、`ThreadList`、`chat-page` 到 assistant-ui 能力的对应关系；截图目录或验收记录能复用为后续视觉回归基线；明确哪些能力直接迁移，哪些能力需要 adapter 投影。 | `/chat` 欢迎态；普通问答完成态；reasoning、tool-call、ArtifactCard 同屏态；ThreadList 普通、active、archived、draft；右侧 Workbench 打开态；窄屏或移动宽度布局。 | `cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build`；`cd datalogue-web && npm run test -- src/components/chat-page.test.jsx src/assistant/MyMessage.test.jsx src/components/artifact-card.test.jsx src/components/workbench-panel.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js`。 | 确认 P0 不改 runtime、不改 stream 协议、不改配色主题；检查截图是否覆盖空态、流式态、完成态、失败态和历史回放；检查用户可见 payload 是否仍过滤 SQL、schema、raw rows、query_plan。 |
| P1：可见外壳组件迁移 | 新的 Datalogue 组件壳承接 Composer、Action Bar、ThreadList、Thread；`chat-page.jsx` 只换可见组件引用，不改变 `AssistantRuntimeProvider`、thread-list adapter 和 chat adapter；新建对话、历史切换、发送、停止、复制、重试可用。 | 欢迎态 composer；消息列表底部 composer；发送中停止按钮；ThreadList 新对话和历史切换；Action Bar hover 或常驻动作；Workbench 与 Chat 并列态。 | `cd datalogue-web && npm run test -- src/components/chat-page.test.jsx src/assistant/thread-list-adapter.test.js src/assistant/chat-adapter.test.js`；`cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build`。 | 扫描 `chat-page.jsx` 是否仍意外混用新旧同职责组件；确认数据集和模型选择仍写入发送链路；确认 `RouteThreadSync`、`UrlSync`、`DatasetSync` 未被组件迁移破坏。 |
| P2：消息渲染与 Markdown 主路径 | `DatalogueMarkdown` 或等价主路径覆盖普通文本、列表、表格、代码块、数学公式、长内容换行；历史消息和新消息渲染一致；ArtifactCard 继续只通过 refs 和 artifact API 查看详情。 | 普通 Markdown 回答；表格 markdown；代码块；数学公式；长段落换行；ArtifactCard 预览和“查看详情”面板；历史消息回放。 | `cd datalogue-web && npm run test -- src/assistant/MyMessage.test.jsx src/components/artifact-card.test.jsx src/assistant/chat-adapter.test.js`；`cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build`。 | 检查旧 markdown renderer 是否还在主路径重复执行；检查 `<think>`、SQL、schema、raw rows、query_plan 是否被剥离或阻断；检查表格宽度、代码块换行和移动端横向滚动。 |
| P3：Reason、ChainOfThought 和 Message Part Grouping | `chat-adapter` 把安全摘要投影成 reasoning 或 message parts；任务分类、handoff、工具状态、失败原因可折叠展示；消息区不重复渲染 Workbench 时间线。 | 思考过程折叠态和展开态；AgenticLeadAgent 路由摘要；BI Agent 执行摘要；失败或 blocked 状态；handoff 状态；没有 reasoning 的普通回答。 | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/assistant/agentic-shell-event-adapter.test.js src/assistant/MyMessage.test.jsx src/components/chat-page.test.jsx`；`cd datalogue-web && npm run lint`。 | 检查 reasoning parts 只包含业务级摘要；检查消息区和 Workbench 是否重复展示同一执行时间线；检查 failed、blocked、confirmation、handoff 是否都有用户可理解状态。 |
| P4：ToolUI、Tool Group 和 Message Timing | Dataset Query Skill / Toolkit 的安全工具卡可见；get_status、list_assets、compile、execute、artifact 等步骤能归组；耗时、状态、refs 展示稳定；artifact ref、checkpoint ref、run id 只提供安全入口。 | running 工具组；completed 工具组；failed 工具组；blocked 或 confirmation 工具组；Message Timing；artifact/ref 跳转入口；Workbench 对应事件。 | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/assistant/agentic-shell-event-adapter.test.js src/components/workbench-panel.test.jsx src/components/artifact-card.test.jsx`；`cd datalogue-web && npm run build`。 | 检查 ToolUI 不展示 SQL、raw rows、完整 schema、内部 query_plan、RepairPatch 主体；检查耗时缺失时的降级文案；检查同一 artifact ref 不重复渲染。 |
| P5：Multi-Agent ChatUI | 用户能区分 AgenticLeadAgent 负责路由与策略，BI Agent 负责问数执行；ReportAgent、PythonAgent、AuditAgent 若出现只能是 disabled 或未启用说明；不启用新 Agent runtime，不改变后端执行所有权。 | LeadAgent 行为行；BI Agent 行为行；handoff 摘要；未来 Agent disabled 状态；多轮追问中 Agent 归属延续；Workbench 右侧仍显示真实执行结果。 | `cd datalogue-web && npm run test -- src/assistant/chat-adapter.test.js src/assistant/agentic-shell-event-adapter.test.js src/components/chat-page.test.jsx src/components/workbench-panel.test.jsx`；`cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build`。 | 检查 UI 不暗示 Report/Python/Audit 已启用；检查 Multi-Agent 展示不替代真实 runtime；检查 handoff 文案不泄露控制面、tool whitelist 或内部策略细节。 |
| P6：清理旧封装和依赖 | 新组件目录成为 Chat UI 唯一可见组件入口；旧 `MyComposer`、`MyMessage`、`Thread`、`ThreadList` 不再被页面主路径和测试引用；旧 markdown/action row 逻辑已迁移或删除；依赖清理有引用扫描和 build 证据。 | 清理后欢迎态；清理后普通对话态；清理后 ArtifactCard 详情；清理后 Reason/ToolUI；清理后 ThreadList；清理后 Workbench。 | `cd datalogue-web && npm run test`；`cd datalogue-web && npm run lint`；`cd datalogue-web && npm run build`；`git diff --check`。 | 扫描旧入口引用、重复 markdown/action row、未使用依赖和测试 mock；确认删除不影响历史消息、artifact refs、Workbench retry、旧 conversation 回放；确认 package 依赖删除后 lockfile 和构建一致。 |

## 5. P6 清理条件

P6 不是“迁移开始时顺手删除”，而是组件主路径稳定后的最后收口。满足以下条件前，不允许删除旧入口。

### 5.1 删除旧 `MyComposer` / `MyMessage` / `Thread` / `ThreadList` 入口的条件

必须同时满足：

- `chat-page.jsx` 不再从 `datalogue-web/src/assistant/MyComposer.jsx`、`MyMessage.jsx`、`Thread.jsx`、`ThreadList.jsx` 导入可见主路径组件。
- 新组件已经覆盖欢迎态 composer、底部 composer、用户消息、助手消息、reasoning、ArtifactCard、ThreadList 普通/active/archived/draft 状态。
- `RouteThreadSync`、`UrlSync`、`DatasetSync`、`TraceProvider` 或其替代实现仍有测试覆盖。
- `chat-page.test.jsx`、`MyMessage` 对应新测试、`artifact-card.test.jsx`、`workbench-panel.test.jsx`、`thread-list-adapter.test.js` 通过。
- 真实页面截图确认左 ThreadList、中 Chat、右 Workbench 的布局和 P0 基线一致。
- `rg -n "MyComposer|MyMessage|from '../assistant/Thread'|from '../assistant/ThreadList'|<Thread\\b|<ThreadList\\b" datalogue-web/src` 只剩迁移说明、归档文档或已明确保留的兼容测试。

满足后可以删除或重命名旧文件；如果还需要兼容导出，必须在文件头注释中写明只做 deprecated bridge，并在后续 PR 中删除。

### 5.2 删除旧 markdown 和 action row 逻辑的条件

必须同时满足：

- Markdown 主路径已经统一到 `DatalogueMarkdown` 或等价组件，覆盖 GFM 表格、代码高亮、数学公式、链接、长文本和流式增量。
- 旧 `MarkdownTextPrimitive`、`react-markdown`、`remark-*`、`rehype-*` 相关路径没有双渲染同一 message part。
- Action Bar 主路径已经统一到 `DatalogueActionBar` 或 assistant-ui 官方 Action Bar 壳，复制、重试、编辑、朗读、反馈的可用性和禁用态都有测试或手工证据。
- ArtifactCard 的 `view`、retry、feedback 等业务动作仍通过受控 handler 触发，不把 action payload 直接暴露到用户可见文本。
- `rg -n "MarkdownTextPrimitive|react-markdown|remarkGfm|remarkMath|rehypeKatex|rehypeHighlight|action row|ActionRow|MessageActions" datalogue-web/src` 的剩余命中都能解释为新主路径或已删除候选。

如果 markdown 或 action row 仍承担 artifact 详情、口径卡、feedback、retry 中任一业务动作，不得删除；应先迁移业务动作再清理旧渲染。

### 5.3 删除未使用依赖的条件

必须同时满足：

- `rg -n "<依赖包名>|from '<依赖包名>'|from \"<依赖包名>\"" datalogue-web/src datalogue-web/package.json` 证明业务代码不再引用该依赖。
- `npm run build` 通过，确认 Vite 生产构建没有缺包。
- `npm run test` 通过，确认测试 mock 没有依赖旧包。
- 如果删除 markdown、highlight、math 相关依赖，必须额外截图验证 markdown 表格、代码块和数学公式仍正常。
- `package.json` 和 lockfile 同步更新；不得只删代码引用而留下过期依赖，也不得只删依赖不跑构建。

优先清理明确不再使用的渲染包、测试 mock 和旧组件局部工具；不要在 P6 混入 assistant-ui 版本升级或主题重设计。

## 6. 推荐验收命令

基础命令：

```bash
cd datalogue-web
npm run lint
npm run build
npm run test
```

迁移阶段常用定向命令：

```bash
cd datalogue-web
npm run test -- src/components/chat-page.test.jsx src/assistant/MyMessage.test.jsx src/components/artifact-card.test.jsx src/components/workbench-panel.test.jsx src/assistant/chat-adapter.test.js src/assistant/thread-list-adapter.test.js
```

P3-P5 事件投影和工具 UI 定向命令：

```bash
cd datalogue-web
npm run test -- src/assistant/chat-adapter.test.js src/assistant/agentic-shell-event-adapter.test.js src/components/workbench-panel.test.jsx src/components/artifact-card.test.jsx
```

清理扫描命令：

```bash
rg -n "MyComposer|MyMessage|from '../assistant/Thread'|from '../assistant/ThreadList'|<Thread\\b|<ThreadList\\b" datalogue-web/src
rg -n "MarkdownTextPrimitive|react-markdown|remarkGfm|remarkMath|rehypeKatex|rehypeHighlight|ActionRow|MessageActions" datalogue-web/src
rg -n "select|raw_rows|raw_result|query_plan|repair_patch|control_plane" datalogue-web/src/assistant datalogue-web/src/components
git diff --check
```

## 7. 截图命名建议

截图或录屏建议按阶段归档，便于 PR review 对比：

```text
outputs/assistant-ui-migration/P0-01-chat-empty.png
outputs/assistant-ui-migration/P0-02-chat-completed.png
outputs/assistant-ui-migration/P0-03-reasoning-tool-artifact.png
outputs/assistant-ui-migration/P0-04-thread-list-states.png
outputs/assistant-ui-migration/P0-05-workbench-open.png
outputs/assistant-ui-migration/P0-06-narrow-layout.png
```

后续阶段沿用同名编号加阶段前缀，例如 `P2-02-chat-completed.png`。截图产物只作为本地验收证据，不应混入代码提交，除非 PR 明确要求提交设计证据。

## 8. 完成判定

P0-P6 全部完成时，应满足：

- Chat 页面主要可见组件已经由 assistant-ui 官方组件、primitives 或官方推荐模式承接。
- Datalogue 组件壳只保留 dataset/model chip、artifact refs、安全裁剪、Agentic Shell 投影和 Workbench 对接等必要业务逻辑。
- 浅色 SaaS 工作台、左 ThreadList、中 Chat、右 Workbench、紧凑 chip、细边框、小圆角、中性色、蓝/绿状态强调仍与 P0 基线一致。
- 消息区不重复展示执行过程，Workbench 继续承接时间线、artifact、retry 和详情。
- 用户可见层不暴露 SQL、schema、raw rows、query_plan、RepairPatch 主体或 control plane 细节。
- `npm run lint`、`npm run build`、`npm run test` 和 `git diff --check` 均有当次通过证据。

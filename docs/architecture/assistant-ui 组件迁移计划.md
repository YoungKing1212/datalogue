# assistant-ui 组件迁移计划

> 生成时间：2026-07-03 23:16
> 当前结论：可以改造，但第一阶段只做可见组件层迁移，暂不改底层 runtime，也暂不做 headless primitives 级大重构。

## 一、背景与目标

Datalogue 当前聊天前端已经接入 `@assistant-ui/react`，但可见页面并不是直接由一套官方组件完整驱动，而是通过项目内的 `MyComposer`、`MyMessage`、`Thread`、`ThreadList`、`chat-page` 和 adapter 组合完成。也就是说，升级 assistant-ui 依赖或修改局部组件，不一定能直接反映到页面主体验上。

本计划的目标是把当前 Chat UI 逐步迁移到 assistant-ui 官方组件和能力上，同时保留 Datalogue 现有视觉样式、业务入口和安全边界：

- 先保留当前样式，不改颜色、不改整体布局节奏。
- 先迁移可见组件面，不替换底层执行 runtime。
- 保留现有 Agentic Shell / AgenticLeadAgent / BI Agent / Dataset Query Skill 链路。
- 保留当前线程、历史消息、Workbench、Artifact refs 和安全裁剪策略。
- 后续颜色和视觉风格实验必须在组件基线稳定之后再做。

## 二、当前样式基线

第一阶段迁移必须保持以下视觉基线：

- 浅色 SaaS 工作台风格。
- 左侧紧凑 ThreadList，中间 Chat 主区，右侧可选 Workbench Panel。
- 细边框、小圆角、中性色表面。
- 蓝色和绿色作为状态强调色。
- Composer、Dataset chip、Model chip、工具 chip 保持紧凑。
- Message、Action Bar、ArtifactCard、推理/工具状态保持当前信息密度。
- 欢迎态和对话态布局不能出现明显跳变。

本阶段不做主题重设计，不做配色实验，不把组件迁移和视觉改版混在同一个 PR 中。

## 三、当前适配性判断

### 1. 可以直接推进的部分

这些能力当前已经有 assistant-ui primitives 或官方模式可以承接，适合优先迁移：

| 目标能力 | 当前状态 | 迁移判断 |
| --- | --- | --- |
| Input History | `MyComposer` 已接入 `unstable_useComposerInputHistory`，欢迎态也已补齐 | 继续保留，补交互验收 |
| Composer | 当前用 `ComposerPrimitive.Root/Input/Send/Cancel` 组合 | 可收敛成统一 Composer 组件壳 |
| Thread | 当前用 `ThreadPrimitive.Root/Viewport/Messages` | 可保持结构，减少自定义分叉 |
| Action Bar | 当前已使用 `ActionBarPrimitive`，但业务反馈能力需要再接 | 可作为第一批组件固化 |
| Thread List Component | 当前用 `ThreadListPrimitive` + 自定义 adapter | 可保留 adapter，替换可见列表壳 |
| Streamdown Markdown | 依赖已引入，消息渲染已开始迁移 | 可作为消息渲染主路径 |

### 2. 需要 adapter 投影后再推进的部分

这些能力不是简单替换组件就能完成，需要把 Datalogue 后端事件投影成 assistant-ui 能理解的 message parts：

| 目标能力 | 需要补齐的投影 |
| --- | --- |
| ChainOfThought | 将 AgenticLeadAgent / BI Agent 的安全推理摘要投影为 reasoning part |
| Reason | 将任务分类、handoff、工具状态、失败原因映射为可折叠 Reason 展示 |
| ToolUI | 将 Dataset Query Skill / Toolkit 的安全摘要映射为工具卡片 |
| Tool Group | 将一次查询中的 get_status、compile、execute、artifact 等步骤分组 |
| Message Timing | 将后端 timing metadata 统一挂到 message / part metadata |
| Message Part Grouping | 将 text、reasoning、tool-call、artifact、handoff 分组渲染 |
| Multi-Agent ChatUI | 将 AgenticLeadAgent -> BI Agent -> Dataset Toolchain 的 handoff 显式呈现 |

### 3. 暂不进入本轮的部分

- 不替换 `AssistantRuntimeProvider`。
- 不把现有 `useLocalRuntime` / thread-list adapter / chat adapter 改成新 runtime。
- 不改变 `/api/agentic-shell/tasks/stream` 或 direct query stream 协议。
- 不把 SQL、schema、raw rows、query_plan、RepairPatch 主体暴露给 ToolUI。
- 不把颜色、品牌视觉、布局重设计并入组件迁移 PR。

## 四、目标组件结构

建议新增一层面向 Datalogue 的 assistant-ui 组件目录，统一承接官方组件和现有样式：

```text
datalogue-web/src/assistant-ui/
  DatalogueThread.jsx
  DatalogueComposer.jsx
  DatalogueThreadList.jsx
  DatalogueMessage.jsx
  DatalogueActionBar.jsx
  DatalogueReasoning.jsx
  DatalogueToolUI.jsx
  DatalogueToolGroup.jsx
  DatalogueMarkdown.jsx
```

这层不是重新封装一套私有 UI 框架，而是作为 Datalogue 的业务适配壳：

- 内部优先使用 assistant-ui 官方组件和 primitives。
- 外部保留当前 className、布局位置和业务 props。
- 安全裁剪、artifact 引用、dataset/model chip 等项目特有逻辑留在壳层。
- 后续如果官方组件形态升级，只改这一层，不再散落到 `chat-page` 和多个消息组件里。

## 五、迁移阶段

### P0：样式基线和组件盘点

目标：先确认页面现在长什么样，避免后续迁移时“功能变了但样式也变了”。

- [ ] 截图记录 `/chat` 欢迎态。
- [ ] 截图记录普通对话态。
- [ ] 截图记录 reasoning / tool-call / artifact 同屏态。
- [ ] 截图记录左侧 ThreadList 的普通、active、archived、draft 状态。
- [ ] 截图记录窄屏或移动宽度下的布局。
- [ ] 建立当前组件到 assistant-ui 能力的映射表。

验收：

- 截图或验收记录能作为后续视觉回归基线。
- 明确哪些组件可以直接换，哪些必须通过 adapter 投影。

### P1：可见外壳组件迁移

目标：先迁移用户最直接接触的外壳组件，不改变消息数据模型。

- [ ] 建立 `DatalogueComposer`，承接 Composer、Input History、Send/Cancel。
- [ ] 建立 `DatalogueActionBar`，承接 Copy、Reload、Speak、Edit、Feedback。
- [ ] 建立 `DatalogueThreadList`，保留当前 `DatalogueThreadListAdapter`。
- [ ] 建立 `DatalogueThread`，保留当前空态、viewport、底部 composer 布局。
- [ ] 将 `chat-page` 的直接组件引用迁移到新组件层。

验收：

- 页面样式与 P0 基线基本一致。
- 新建对话、历史切换、发送、停止、复制、重试可用。
- 执行 `npm run lint`、`npm run build` 和相关组件测试。

### P2：消息渲染与 Markdown 主路径

目标：把消息正文和 parts 渲染迁移到 assistant-ui 推荐路径。

- [ ] 建立 `DatalogueMarkdown`，以 Streamdown Markdown 作为主渲染路径。
- [ ] 验证普通文本、列表、表格、代码块、数学公式、长内容换行。
- [ ] 移除旧 markdown 渲染路径的重复逻辑。
- [ ] 建立 `DatalogueMessage`，统一 UserMessage / AssistantMessage。
- [ ] 保留 ArtifactCard 的安全引用展示，不回退到 raw payload 展示。

验收：

- 历史消息和新消息渲染一致。
- Markdown 不破坏当前信息密度。
- 用户可见层仍不暴露 SQL、schema、raw rows、query_plan。

### P3：Reason、ChainOfThought 和 Message Part Grouping

目标：把当前 Agentic Shell 事件从“文本化堆叠”升级为结构化消息部分。

- [ ] 在 `chat-adapter` 中固化 message part 投影规则。
- [ ] 将任务分类、Agent handoff、工具开始/完成/失败映射为 reasoning parts。
- [ ] 建立 `DatalogueReasoning`，展示 ChainOfThought / Reason。
- [ ] 使用 Message Part Grouping 分组 text、reasoning、tool-call、artifact。
- [ ] 支持折叠/展开，默认展示业务摘要，不展示控制面细节。

验收：

- AgenticLeadAgent、BI Agent、Dataset Query Skill 的执行过程可读。
- 推理展示只包含安全摘要，不包含 SQL、schema、raw rows。
- 对失败、blocked、confirmation、handoff 有明确状态呈现。

### P4：ToolUI、Tool Group 和 Message Timing

目标：把 Dataset 查询链路转为可识别的工具 UI，而不是普通消息文本。

- [ ] 建立 `DatalogueToolUI`，覆盖 Dataset Query Skill / Toolkit 的安全工具卡。
- [ ] 建立 `DatalogueToolGroup`，把 get_status、list_assets、compile、execute、artifact 等步骤归组。
- [ ] 接入 `Message Timing`，展示任务、Agent、工具级耗时。
- [ ] 对 running、completed、failed、blocked、confirmation 状态分别建展示分支。
- [ ] 给 artifact ref、checkpoint ref、run id 提供安全跳转或查看入口。

验收：

- 用户能看懂 BI Agent 在做什么、做到哪一步、是否产出结果。
- 工具卡只展示 summary、refs、row count、状态和耗时。
- 不展示 SQL、raw rows、完整 schema 或内部 query_plan。

### P5：Multi-Agent ChatUI

目标：把 AgenticLeadAgent 和 BI Agent 的职责分工在 UI 上表达清楚。

- [ ] 将 AgenticLeadAgent 的任务分类、策略选择和 handoff 展示为上游 Agent 行为。
- [ ] 将 BI Agent 的数据集理解、工具选择、confirmation、artifact 返回展示为下游 Agent 行为。
- [ ] 对未来 ReportAgent / PythonAgent / AuditAgent 保留 disabled 或 placeholder 呈现。
- [ ] 不启用新 Agent runtime，不改变当前后端执行所有权。

验收：

- 用户能区分“谁在路由任务”和“谁在执行问数”。
- 多 Agent 展示不会让用户误以为可用 Agent 已全部启用。
- Report/Python/Audit 默认 disabled 的事实在 UI 上不会被误导。

### P6：清理旧封装和依赖

目标：在组件主路径稳定后，再删除旧的重复实现。

- [ ] 清理旧 action row、旧 markdown renderer、重复 message wrapper。
- [ ] 收敛 `MyComposer`、`MyMessage`、`Thread`、`ThreadList` 命名或迁移到新目录。
- [ ] 删除不再使用的依赖和测试 mock。
- [ ] 更新架构文档和项目记忆。

验收：

- 前端测试、lint、build 通过。
- 旧组件没有继续作为主页面入口。
- 新组件目录成为 Chat UI 唯一可见组件入口。

## 六、建议 PR 拆分

| PR | 范围 | 不做事项 |
| --- | --- | --- |
| PR1 | P0 + P1，样式基线、Composer、Action Bar、ThreadList、Thread 外壳 | 不动消息 parts，不动 runtime |
| PR2 | P2，Streamdown Markdown 和 Message 主渲染 | 不做 ToolUI，不做 Multi-Agent |
| PR3 | P3，Reason / ChainOfThought / Message Part Grouping | 不暴露内部控制面 |
| PR4 | P4，ToolUI / Tool Group / Message Timing | 不改变后端执行协议 |
| PR5 | P5，Multi-Agent ChatUI | 不启用 Report/Python/Audit |
| PR6 | P6，旧封装清理和依赖收敛 | 不混入配色改版 |

## 七、关键风险

1. **“直接用组件”不等于不写适配层**
   assistant-ui 的能力需要和 Datalogue 的 SSE、history、artifact、安全裁剪规则对齐，因此必须保留一层很薄的 Datalogue 业务壳。

2. **Action Bar 的反馈能力需要业务接线**
   当前 Copy/Reload/Speak/Edit 可以先稳定，Feedback 是否写回后端需要单独定义契约。

3. **ToolUI 最容易误泄露控制面信息**
   工具卡只能展示安全摘要和 refs，不能因为 UI 结构化就展示 SQL、schema、raw rows 或 query_plan。

4. **Multi-Agent 展示不能越过当前真实能力**
   当前规划是 AgenticLeadAgent 和 BI Agent 为 AgentScope 2.0 ReAct Agent；Report/Python/Audit 仍是后续可选 Agent，不应在 UI 上表现为已启用。

5. **视觉基线必须先验收**
   如果一边迁移组件一边改颜色，会很难判断问题来自组件行为、样式覆盖还是视觉重设计。

## 八、完成定义

组件迁移完成时，应满足：

- 当前 Chat 页面主要可见组件都通过 assistant-ui 官方组件或官方模式承接。
- Datalogue 业务壳只保留 dataset/model、artifact refs、安全裁剪、Agentic Shell 投影等项目必要逻辑。
- 页面视觉与迁移前基线一致，颜色实验尚未开始。
- Input History、Composer、Thread、Action Bar、Thread List、Streamdown Markdown、Reason、ChainOfThought、ToolUI、Tool Group、Message Timing、Message Part Grouping、Multi-Agent ChatUI 均有明确落点。
- 前端 `npm run lint`、`npm run build` 和相关测试通过。
- 用户可见层继续不暴露 SQL、schema、raw rows、query_plan、RepairPatch 主体。

## 九、参考

- assistant-ui 总文档入口：https://www.assistant-ui.com/llms.txt
- Input History：https://www.assistant-ui.com/docs/guides/input-history
- Multi-Agent：https://www.assistant-ui.com/docs/tools/multi-agent
- Action Bar：https://www.assistant-ui.com/docs/primitives/action-bar

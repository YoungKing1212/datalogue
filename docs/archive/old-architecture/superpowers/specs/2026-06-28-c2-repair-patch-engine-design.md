# C2 RepairPatch Engine 设计规格

## 1. 背景

C1 已完成 RepairPlan 契约、repair event、Artifact refs、前端业务级承接和页面会话切换 E2E。但 C1 的真实问题最终是通过可信模板 SQL 直接成功，并没有证明 RepairPlan 能把字段级失败自动 patch 后重跑成功。

C2 的目标是补齐这个核心能力：字段不存在 / 字段漂移失败后，系统自动生成字段级 RepairPatch，经 Tool 校验、应用、重新编译并重跑成功。

## 2. 阶段定位

C2 P0 定义为：

> RepairPlan Tool Patch Engine 与字段漂移自动修复闭环。

本阶段不进入 AgentScope runner，不做独立 BI 工作台，不做管理员详情 UI，不让 LLM 生成可执行 SQL。

## 3. 已确认决策

### 3.1 修复类型

P0 只做字段不存在 / 字段漂移。

### 3.2 候选字段来源

采用语义资产优先，不足时 fallback 到当前 dataset 的 selected columns。

不读取未选字段，不跨 dataset，不跨 datasource。

### 3.3 Patch 粒度

优先 patch QueryGraph，同时允许 patch compiler binding，禁止直接 patch SQL。

### 3.4 用户确认策略

产品策略为高置信自动修、中置信用户确认、低置信阻断。

P0 实施范围只实现高置信自动修；中置信只发 `repair.confirmation_required` 协议和占位 UI，不实现点击后继续执行。

### 3.5 Confidence

采用规则打底 + LLM 业务语义裁判 + Tool merge/clamp。

LLM 只看中文业务名 / 注释和粗粒度类型，不看物理字段名、表名、SQL、schema 或 raw result。

### 3.6 Patch IR

定义统一 `RepairPatch` envelope，内部区分 `query_graph_patch` 和 `compiler_binding_patch`。

### 3.7 Trace

trace-only / Langfuse observation / 后端日志可以记录完整字段 patch 详情。

用户可见 event、ArtifactCard、final answer、Artifact API 一律脱敏。

### 3.8 Prompt

语义裁判 prompt 名为：

```text
repair_plan_field_semantic_judge
```

长期策略是本地 prompt + Langfuse prompt 同步。PR1 只定义接口、mock judge 和本地模板，不真实调用模型。

### 3.9 前端

Chat timeline 展示业务级自动修复节点，不展示字段、schema、SQL 或 patch operations。

### 3.10 验收

真实验收使用 `查询杨凯 2024 年工作日志`，通过临时上下文或 fixture 在 compiler binding 阶段注入字段漂移，不污染真实语义资产。

## 4. 架构

```text
SQL failure
  -> failure classifier
  -> RepairPlan lifecycle
  -> RepairPatch engine
      -> field candidate collector
      -> rule scorer
      -> semantic judge
      -> merge/clamp
      -> validator
      -> pure patch apply
  -> recompile SQL through Tool
  -> sql audit
  -> execute
  -> final answer + repair refs
```

## 5. RepairPatch Engine

PR1 新增 `datalogue-api/app/services/repair_patch.py`。

职责：

- RepairPatch 辅助逻辑。
- field candidate collection。
- type normalization。
- rule score。
- semantic judge interface / mock judge。
- confidence merge/clamp。
- patch validator。
- pure apply functions。
- sanitized summary builder。

C1 的 `repair_plan.py` 继续负责 failure classification、retry attempts、RepairPlan artifact 摘要和生命周期。

## 6. 数据安全

用户可见层禁止：

- 字段 ref
- 字段中文业务名
- 字段注释
- 候选字段列表
- 表名
- schema
- SQL
- patch operations
- raw result

内部 trace-only 允许：

- 原失败字段 ref
- 候选字段列表
- 选中字段
- 规则分
- LLM semantic score
- merge/clamp 结果
- validator 详情
- patch operations
- patch applied result
- recompile result
- rerun result

## 7. PR 拆分

### PR1：Patch Engine 内核

只做离线能力，不接 `/chat`。

包含：

- RepairPatch schema / helpers。
- candidate collector。
- type compatibility。
- mock semantic judge。
- merge/clamp。
- validator。
- query_graph_patch apply。
- compiler_binding_patch apply。
- sanitize summary。
- 单元和小型集成测试。

不包含：

- `/chat/stream`。
- SSE event。
- Artifact 写入。
- 页面 E2E。

### PR2：RepairPlan 协议与真实链路

接入主链。

包含：

- patch 阶段 repair events。
- RepairPlan artifact 脱敏摘要。
- query_artifact / conversation_state refs。
- Langfuse/mock observation。
- compiler binding 字段漂移真实验收。

### PR3：前端承接与页面 E2E

包含：

- chat-adapter 解析新增 repair patch events。
- timeline 展示业务级自动修复过程。
- ArtifactCard 展示 repair_plan related ref。
- 中置信确认卡占位。
- 页面 E2E 与会话切换不串台验证。

## 8. 完成标准

C2 P0 完成必须同时满足：

- 自动化测试通过。
- 页面 E2E 通过。
- 真实问题触发字段漂移。
- RepairPlan 自动生成。
- compiler_binding_patch 应用成功。
- 重新编译 SQL。
- 重跑成功。
- 五件套一致。
- 用户可见层无字段、表、schema、SQL、patch operations 泄露。

## 9. 后续阶段

C2.1：

- 中置信用户确认后继续执行。
- 恢复 checkpoint。
- 再校验 repair_plan_ref / selected_action。
- 继续同一个 task。

C3：

- AgentScope runner adapter。
- 独立 BI 工作台。
- 管理员详情 UI。
- RepairPlan 独立表和审计查询。

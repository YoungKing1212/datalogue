# C3 AgentScope Workbench P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 C3-P0 从设计推进到可合并的 stacked PR：新会话以 Datalogue 本地 AgentScope-compatible mirror 作为会话、消息、事件和 refs 的回放与审计真相源，Datalogue 主链继续负责真实 BI 执行，Chat 右侧 Workbench Panel 承接业务级工作台视图，并保留隐藏 Workbench 路由与受控 retry 能力。

**Architecture:** 新增 Datalogue 本地 AgentScope-compatible mirror 四表作为 C3 会话/消息/事件/引用层；`/chat/stream` 对新 `as_*` 线程先写入 mirror user message 和 assistant running message，再运行既有 Datalogue 主链，并把 event envelope 投影到 `agentscope_event`；Workbench View Model API 从 mirror、conversation_state、query_artifact 和 refs 聚合只读业务级视图；前端仍以 Chat 为入口，新增右侧 Panel 和隐藏 `/workbench/:threadId/:artifactRef?` 路由。

**AS-R0 Handoff Note:** 本计划是 C3 foundation 计划，不是 AgentScope Runtime ownership 完成计划。正式 AS-R0 迁移以后续 `2026-07-01-as-r0-agentic-shell-formal-pr-plan.md` 为准：P0 只做 Shell Contract 与 Tool Boundary；P1 才让 AgentScope Runtime 驱动 BI 主链；P2 再收敛 legacy runtime 和扩展业务 Agent。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, React, Vite, Vitest, Testing Library, existing SSE event envelope, existing ArtifactCard/TaskTimeline, local Langfuse/no-op observability.

---

## Scope

C3-P0 只做 C3 的最小产品化主链：

- 新会话回放与审计真相源：AgentScope-compatible mirror session/message/event/ref。
- 旧会话策略：`conv_*` 只读回放，不迁移，不伪造 AgentScope session。
- 主链策略：双主路径，本地 AgentScope-compatible mirror 管会话流和消息流，Datalogue 主链管能力路由、QueryGraph、SQL 执行、RepairPlan/RepairPatch、Artifact。
- Workbench 入口：Chat 右侧 Panel + 隐藏 route 预留。
- Workbench 数据：后端提供 View Model API，前端不拼内部 schema、SQL、raw rows、query plan。
- Action 范围：只读 + 受控 retry，不启动 ReportAgent/PythonAgent/AuditAgent。

不纳入 C3-P0：

- 独立 BI Workbench 页面正式入口。
- AgentScope runner 接管 Datalogue 主链。
- AgentScope Runtime ownership 迁移。
- Datalogue Agentic Shell 接管 `/chat/stream`。
- 旧会话迁移。
- 管理员字段级 patch UI。
- 公开 schema、SQL、raw result、QueryGraph 主体。

## PR Stack

| PR | Branch | Result | Depends On |
| --- | --- | --- | --- |
| PR1 | `c3-p0-01-agentscope-mirror-storage` | 四表、模型、schema、thread resolver、mirror service | `b-first-c` |
| PR2 | `c3-p0-02-chat-session-bridge` | `/chat/stream` 新会话写入 AgentScope mirror，event envelope 投影 | PR1 |
| PR3 | `c3-p0-03-workbench-view-api` | Workbench View Model API、artifact view、legacy read-only | PR2 |
| PR4 | `c3-p0-04-controlled-retry-lease` | 受控 retry action、running lease timeout、失败恢复 | PR3 |
| PR5 | `c3-p0-05-chat-workbench-panel` | Chat 右侧 Panel、隐藏 route、前端 View Model 渲染与测试 | PR4 |
| PR6 | `c3-p0-06-acceptance-hardening` | 双主路径验收、旧会话 smoke、文档和 project-memory | PR5 |

每个 PR 合并前必须：

- [ ] 只提交本 PR 相关文件。
- [ ] 运行本 PR 的最小测试命令。
- [ ] 运行 `git diff --check`。
- [ ] 检查用户可见 payload 不包含 `sql`、`schema`、`raw_result`、`raw_rows`、`query_plan`、`field_patch`。
- [ ] 在 `.codex/project-memory.md` 追加完成记录。

## Shared Contracts

### Thread ID

- `as_<uuid>`：C3 新会话，AgentScope-compatible mirror 是会话、消息、事件和 refs 的回放与审计真相源。
- `conv_<id>`：历史会话，只读回放。
- `/chat/:number`：继续解析成 `conv_<number>`。
- `/chat/:threadId`：当 `threadId` 已带 `as_` 或 `conv_` 前缀时直接使用。

### User-Visible Safety

用户可见 API、SSE、前端状态只能出现：

- 业务级阶段、业务摘要、候选数据集摘要。
- `artifact:<uuid>`、`checkpoint_ref`、`trace_ref`、`repair_plan_ref`。
- `task_id`、`trace_id`、`thread_id`、`message_id`。
- ArtifactCard 的 `preview_payload` 与脱敏 refs。

禁止出现：

- raw SQL、direct SQL、LLM SQL。
- schema、table name、physical field name、raw rows、raw result。
- QueryGraph 主体、RepairPatch 主体、字段级 patch。
- control plane、tool private payload、完整 semantic asset。

### Backend Failure Semantics

- AgentScope assistant message 进入 `running` 后必须有 lease。
- 主链成功时 assistant message 变成 `completed`。
- 主链失败时 assistant message 变成 `failed`，并写入业务级 error summary。
- lease 超时的 `running` message 标为 `interrupted`，Workbench 提供受控 retry。
- retry 只传 `thread_id`、`message_id`、`checkpoint_ref`、`selected_action`，不接收 SQL/schema。

## PR1: AgentScope Mirror Storage

### Task 1.1 Write failing backend tests

- [ ] 新增 [datalogue-api/tests/test_agentscope_mirror_models.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_agentscope_mirror_models.py)，覆盖四表基础写入、ref 关系写入、唯一约束和过期 running message 查询。

  必须包含这些测试函数：

  - `test_create_agentscope_session_and_messages(db_session)`
  - `test_agentscope_ref_rejects_duplicate_relation(db_session)`
  - `test_find_expired_running_messages(db_session, frozen_time)`

- [ ] 新增 [datalogue-api/tests/test_agentscope_thread_resolver.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_agentscope_thread_resolver.py)，覆盖线程 id 规则。

  必须断言：

  ```python
  assert normalize_thread_id("25") == "conv_25"
  assert normalize_thread_id("conv_25") == "conv_25"
  assert normalize_thread_id("as_01234567-89ab-cdef-0123-456789abcdef").startswith("as_")
  ```

- [ ] 运行并确认失败：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py -q
  ```

### Task 1.2 Add Alembic migration

- [ ] 新增迁移文件 [datalogue-api/alembic/versions/p1q2r3s4t5u6_add_agentscope_workbench_mirror.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/alembic/versions/p1q2r3s4t5u6_add_agentscope_workbench_mirror.py)。

  表结构：

  - `agentscope_session`
    - `id` integer primary key
    - `thread_id` string unique not null
    - `source_type` enum-like string: `agentscope`, `legacy_conversation`
    - `legacy_conversation_id` integer nullable
    - `title` string nullable
    - `status` string not null: `active`, `archived`, `read_only`
    - `created_at`, `updated_at`
    - `metadata_json` JSON not null default `{}`
  - `agentscope_message`
    - `id` integer primary key
    - `message_id` string unique not null
    - `thread_id` string indexed not null
    - `role` string not null: `user`, `assistant`, `tool`, `system`
    - `status` string not null: `created`, `running`, `completed`, `failed`, `interrupted`
    - `content_summary` text nullable
    - `business_payload_json` JSON not null default `{}`
    - `lease_expires_at` datetime nullable
    - `created_at`, `updated_at`, `completed_at`
  - `agentscope_event`
    - `id` integer primary key
    - `event_id` string unique not null
    - `thread_id` string indexed not null
    - `message_id` string indexed nullable
    - `event_type` string indexed not null
    - `task_id` string indexed nullable
    - `trace_id` string indexed nullable
    - `payload_json` JSON not null default `{}`
    - `visibility` string not null: `user`, `admin`, `trace_only`
    - `created_at`
  - `agentscope_ref`
    - `id` integer primary key
    - `thread_id` string indexed not null
    - `message_id` string indexed nullable
    - `ref_type` string indexed not null
    - `ref_value` string indexed not null
    - `relation` string not null: `primary`, `related`, `checkpoint`, `trace`
    - `created_at`

  必须增加唯一约束：

  - `agentscope_session.thread_id`
  - `agentscope_message.message_id`
  - `agentscope_event.event_id`
  - `agentscope_ref(thread_id, message_id, ref_type, ref_value, relation)`

  新表和关键列必须写中文注释，说明业务边界和用户可见性。

### Task 1.3 Add SQLAlchemy models

- [ ] 新增 [datalogue-api/app/models/agentscope_workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/models/agentscope_workbench.py)。

  文件头使用项目 Python 注释模板，Description 写明：

  ```text
  AgentScope 工作台本地镜像模型，用于把新会话、消息、事件和产物引用落到 Datalogue 可查询的持久层。
  ```

  必须提供这些模型类：

  ```python
  class AgentScopeSession(Base):
      __tablename__ = "agentscope_session"

  class AgentScopeMessage(Base):
      __tablename__ = "agentscope_message"

  class AgentScopeEvent(Base):
      __tablename__ = "agentscope_event"

  class AgentScopeRef(Base):
      __tablename__ = "agentscope_ref"
  ```

  每个模型的 `metadata_json`、`business_payload_json`、`payload_json` 使用现有项目 JSON 类型写法。

- [ ] 修改 [datalogue-api/app/models/__init__.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/models/__init__.py)，导出四个模型。

### Task 1.4 Add backend schemas and resolver service

- [ ] 新增 [datalogue-api/app/schemas/agentscope_workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/schemas/agentscope_workbench.py)，包含：

  ```python
  class AgentScopeThreadKind(str, Enum):
      AGENTSCOPE = "agentscope"
      LEGACY_CONVERSATION = "legacy_conversation"

  class AgentScopeMessageStatus(str, Enum):
      CREATED = "created"
      RUNNING = "running"
      COMPLETED = "completed"
      FAILED = "failed"
      INTERRUPTED = "interrupted"

  class ThreadRef(BaseModel):
      thread_id: str
      kind: AgentScopeThreadKind
      legacy_conversation_id: int | None = None
      read_only: bool = False
  ```

- [ ] 新增 [datalogue-api/app/services/agentscope_thread_resolver.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/agentscope_thread_resolver.py)，包含：

  - `normalize_thread_id(raw_thread_id: str | int | None) -> str | None`
  - `resolve_thread_ref(raw_thread_id: str | int | None) -> ThreadRef | None`
  - `new_agentscope_thread_id() -> str`

  规则：

  - `None` 返回 `None`，用于新会话创建。
  - 纯数字转 `conv_<number>`。
  - `conv_<number>` 原样返回。
  - `as_<uuid>` 原样返回。
  - 其他值抛出 `ValueError("INVALID_THREAD_ID")`。

### Task 1.5 Add mirror service

- [ ] 新增 [datalogue-api/app/services/agentscope_mirror.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/agentscope_mirror.py)，包含：

  - `create_agentscope_session(db: Session, *, thread_id: str | None, title: str | None) -> AgentScopeSession`
  - `append_user_message(db: Session, *, thread_id: str, content_summary: str, payload: dict) -> AgentScopeMessage`
  - `create_running_assistant_message(db: Session, *, thread_id: str, lease_seconds: int) -> AgentScopeMessage`
  - `mark_message_completed(db: Session, *, message_id: str, content_summary: str, payload: dict) -> AgentScopeMessage`
  - `mark_message_failed(db: Session, *, message_id: str, error_summary: str, payload: dict) -> AgentScopeMessage`
  - `mark_message_interrupted(db: Session, *, message_id: str, reason: str) -> AgentScopeMessage`
  - `record_agentscope_event(db: Session, *, thread_id: str, message_id: str | None, event_type: str, payload: dict, visibility: str, task_id: str | None, trace_id: str | None) -> AgentScopeEvent`
  - `record_agentscope_ref(db: Session, *, thread_id: str, message_id: str | None, ref_type: str, ref_value: str, relation: str) -> AgentScopeRef`
  - `find_expired_running_messages(db: Session, *, now: datetime) -> list[AgentScopeMessage]`

  关键分支补中文注释：

  - 创建新会话时说明 `as_*` 是本地 AgentScope-compatible mirror 的回放与审计来源，不改变 Datalogue runtime ownership。
  - 处理旧会话时说明 `conv_*` 不写 mirror session。
  - 写入用户可见 payload 前说明必须先脱敏。
  - 标记失败/中断时说明 retry 只使用 checkpoint/ref，不使用 SQL。

### Task 1.6 Verify PR1

- [ ] 运行：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_agentscope_mirror_models.py tests/test_agentscope_thread_resolver.py -q
  git diff --check
  ```

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)，记录 C3-P0 PR1 完成情况。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-01-agentscope-mirror-storage
  git add datalogue-api/alembic/versions/p1q2r3s4t5u6_add_agentscope_workbench_mirror.py datalogue-api/app/models/agentscope_workbench.py datalogue-api/app/models/__init__.py datalogue-api/app/schemas/agentscope_workbench.py datalogue-api/app/services/agentscope_thread_resolver.py datalogue-api/app/services/agentscope_mirror.py datalogue-api/tests/test_agentscope_mirror_models.py datalogue-api/tests/test_agentscope_thread_resolver.py .codex/project-memory.md
  git commit -m "feat: add agentscope workbench mirror storage"
  ```

## PR2: Chat Session Bridge

### Task 2.1 Write failing tests for new session message flow

- [ ] 新增 [datalogue-api/tests/test_agentscope_chat_bridge.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_agentscope_chat_bridge.py)。

  必须覆盖：

  - 新会话请求无 `conversation_id` 时创建 `as_*` thread。
  - 写入 user completed message。
  - 写入 assistant running message。
  - 主链成功后 assistant message 变 completed。
  - 主链失败后 assistant message 变 failed。
  - `conv_*` 旧会话 continuation 返回业务级提示，不创建 AgentScope mirror session。

- [ ] 新增 [datalogue-api/tests/test_agentscope_event_projection.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_agentscope_event_projection.py)。

  必须覆盖这些 event envelope 到 mirror event 的映射：

  - `task.started`
  - `dataset.candidates`
  - `repair.patch_applied`
  - `artifact.created`
  - `answer.completed`
  - `error`

- [ ] 运行并确认失败：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py -q
  ```

### Task 2.2 Add event projection service

- [ ] 新增 [datalogue-api/app/services/agentscope_event_projection.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/agentscope_event_projection.py)，包含：

  - `USER_VISIBLE_EVENT_TYPES` 至少包含 `task.started`、`dataset.candidates`、`repair.patch_applied`、`artifact.created`、`answer.completed` 和 `error`。
  - `sanitize_event_payload_for_workbench(event_type: str, payload: dict) -> dict`
  - `project_event_envelope_to_agentscope(db: Session, *, thread_id: str, assistant_message_id: str | None, envelope: DatalogueEventEnvelope) -> AgentScopeEvent`
  - `extract_refs_from_envelope(envelope: DatalogueEventEnvelope) -> list[tuple[str, str, str]]`

  `sanitize_event_payload_for_workbench` 必须 fail closed：

  - 检测到 forbidden keys 时抛出 `ValueError("WORKBENCH_PAYLOAD_LEAK_DETECTED")`。
  - `repair.*` 只保留业务摘要、状态、`repair_plan_ref`、`checkpoint_ref`。
  - `artifact.*` 只保留 `artifact_ref`、`artifact_card` 脱敏字段和 refs。

- [ ] 在该服务里增加中文注释说明：Workbench mirror event 是产品视图素材，不是内部调试日志。

### Task 2.3 Add chat bridge service

- [ ] 新增 [datalogue-api/app/services/agentscope_chat_bridge.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/agentscope_chat_bridge.py)，包含：

  ```python
  class AgentScopeChatBridgeContext(BaseModel):
      thread_id: str
      user_message_id: str
      assistant_message_id: str
      is_legacy_read_only: bool = False

  ```

  必须实现：

  - `begin_chat_turn(db: Session, *, raw_thread_id: str | int | None, user_text: str, metadata: dict) -> AgentScopeChatBridgeContext`
  - `record_stream_event(db: Session, *, context: AgentScopeChatBridgeContext, envelope: DatalogueEventEnvelope) -> None`
  - `complete_chat_turn(db: Session, *, context: AgentScopeChatBridgeContext, final_summary: str, final_payload: dict) -> None`
  - `fail_chat_turn(db: Session, *, context: AgentScopeChatBridgeContext, error_summary: str, error_payload: dict) -> None`

  业务规则：

  - 新会话创建 `as_*` session。
  - `as_*` 续聊复用 session。
  - `conv_*` 不写新 user/assistant message，返回 `is_legacy_read_only=True`。
  - `final_payload` 必须先脱敏再写入 mirror。

### Task 2.4 Wire `/chat/stream` narrowly

- [ ] 修改 [datalogue-api/app/api/chat.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/api/chat.py)。

  接线原则：

  - 只在 stream turn 开始处调用 `begin_chat_turn`。
  - 每次生成 `DatalogueEventEnvelope` 后调用 `record_stream_event`。
  - final payload 发出前调用 `complete_chat_turn`。
  - exception path 调用 `fail_chat_turn`。
  - 旧 `conversation_id` 行为继续保留；新增 `thread_id` 支持时兼容旧请求。

  必须补中文注释解释：本地 AgentScope-compatible mirror 只承接 C3 session/message/event/ref 的回放与审计来源；真正 AgentScope runtime ownership 从 AS-R0 P1 开始。

- [ ] 若现有请求 schema 没有 `thread_id`，修改 [datalogue-api/app/schemas/bi_workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/schemas/bi_workbench.py) 或对应 chat schema，新增可选 `thread_id: str | None`。

### Task 2.5 Verify PR2

- [ ] 运行：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_agentscope_chat_bridge.py tests/test_agentscope_event_projection.py tests/test_chat.py tests/test_event_envelope.py -q
  git diff --check
  ```

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-02-chat-session-bridge
  git add datalogue-api/app/api/chat.py datalogue-api/app/services/agentscope_chat_bridge.py datalogue-api/app/services/agentscope_event_projection.py datalogue-api/app/schemas/bi_workbench.py datalogue-api/tests/test_agentscope_chat_bridge.py datalogue-api/tests/test_agentscope_event_projection.py .codex/project-memory.md
  git commit -m "feat: bridge chat stream to agentscope sessions"
  ```

## PR3: Workbench View Model API

### Task 3.1 Write failing API tests

- [ ] 新增 [datalogue-api/tests/test_workbench_view_api.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_workbench_view_api.py)。

  必须覆盖：

  - `GET /api/workbench/thread/{thread_id}` 返回 `thread_id`、messages、timeline、artifact refs、available actions。
  - `GET /api/workbench/thread/conv_25` 返回 legacy read-only view。
  - `GET /api/workbench/thread/as_missing` 返回 404。
  - `GET /api/workbench/artifact/{artifact_ref}` 返回脱敏 artifact view。
  - artifact ref 非 `artifact:<uuid>` 时 fail closed。
  - 返回 JSON 不包含 forbidden keys。

- [ ] 运行并确认失败：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_workbench_view_api.py -q
  ```

### Task 3.2 Add View Model schemas

- [ ] 扩展 [datalogue-api/app/schemas/agentscope_workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/schemas/agentscope_workbench.py)，新增：

  - `WorkbenchTimelineItem`
  - `WorkbenchMessageView`
  - `WorkbenchArtifactView`
  - `WorkbenchActionView`
  - `WorkbenchThreadView`

  字段要求：

  - `WorkbenchThreadView.thread_id`
  - `WorkbenchThreadView.read_only`
  - `WorkbenchThreadView.messages`
  - `WorkbenchThreadView.timeline`
  - `WorkbenchThreadView.primary_artifact_ref`
  - `WorkbenchThreadView.related_refs`
  - `WorkbenchThreadView.available_actions`
  - `WorkbenchThreadView.legacy_notice`

### Task 3.3 Add View Model service

- [ ] 新增 [datalogue-api/app/services/workbench_view_model.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/workbench_view_model.py)，包含：

  - `build_workbench_thread_view(db: Session, *, thread_id: str) -> WorkbenchThreadView`
  - `build_legacy_conversation_view(db: Session, *, legacy_conversation_id: int) -> WorkbenchThreadView`
  - `build_workbench_artifact_view(db: Session, *, artifact_ref: str) -> WorkbenchArtifactView`
  - `sanitize_workbench_view_payload(payload: dict) -> dict`

  规则：

  - `as_*` 读取 AgentScope mirror。
  - `conv_*` 读取旧 conversation/message/query_artifact，但 `read_only=True`。
  - 旧会话缺 ArtifactCard 时不伪造。
  - `available_actions` 对旧会话为空或 disabled。
  - 所有输出经过 forbidden key scan。

### Task 3.4 Add API router

- [ ] 新增 [datalogue-api/app/api/workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/api/workbench.py)，包含：

  - `GET /thread/{thread_id}`，response model 为 `WorkbenchThreadView`。
  - `GET /artifact/{artifact_ref:path}`，response model 为 `WorkbenchArtifactView`。

  注释要求：

  - 说明该 API 是 C3 Workbench 的后端视图模型层。
  - 说明 artifact 只返回脱敏摘要。

- [ ] 修改 [datalogue-api/app/api/__init__.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/api/__init__.py)，注册：

  ```python
  router.include_router(workbench.router, prefix="/workbench", tags=["工作台"])
  ```

### Task 3.5 Verify PR3

- [ ] 运行：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_workbench_view_api.py tests/test_artifact_api.py tests/test_legacy_conversation_replay.py -q
  git diff --check
  ```

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-03-workbench-view-api
  git add datalogue-api/app/api/__init__.py datalogue-api/app/api/workbench.py datalogue-api/app/schemas/agentscope_workbench.py datalogue-api/app/services/workbench_view_model.py datalogue-api/tests/test_workbench_view_api.py .codex/project-memory.md
  git commit -m "feat: add workbench view model api"
  ```

## PR4: Controlled Retry And Lease Recovery

### Task 4.1 Write failing retry and lease tests

- [ ] 新增 [datalogue-api/tests/test_workbench_retry_actions.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_workbench_retry_actions.py)。

  必须覆盖：

  - `POST /api/workbench/actions/retry` 对 failed/interrupted assistant message 创建新 assistant running message。
  - retry payload 只接受 `thread_id`、`message_id`、`checkpoint_ref`、`selected_action`。
  - payload 带 `sql`、`schema`、`raw_rows` 时返回 400。
  - legacy `conv_*` retry 返回 disabled reason。
  - 没有 checkpoint 的 retry 返回 409。

- [ ] 新增 [datalogue-api/tests/test_agentscope_lease_recovery.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_agentscope_lease_recovery.py)。

  必须覆盖：

  - running message 超过 lease 后变 `interrupted`。
  - 未过 lease 的 running message 保持不变。
  - interrupted message 写入业务级恢复提示和 checkpoint ref。

### Task 4.2 Add action schemas

- [ ] 扩展 [datalogue-api/app/schemas/agentscope_workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/schemas/agentscope_workbench.py)，新增：

  ```python
  class WorkbenchRetryRequest(BaseModel):
      thread_id: str
      message_id: str
      checkpoint_ref: str
      selected_action: str = "retry_last_step"

  class WorkbenchRetryResponse(BaseModel):
      thread_id: str
      retry_message_id: str | None
      accepted: bool
      disabled_reason: str | None = None
  ```

  Pydantic validator 必须拒绝 forbidden keys。

### Task 4.3 Add action service

- [ ] 新增 [datalogue-api/app/services/workbench_actions.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/services/workbench_actions.py)，包含：

  - `run_lease_recovery(db: Session, *, now: datetime) -> list[AgentScopeMessage]`
  - `request_controlled_retry(db: Session, *, request: WorkbenchRetryRequest) -> WorkbenchRetryResponse`
  - `validate_retry_checkpoint(db: Session, *, thread_id: str, checkpoint_ref: str) -> None`

  规则：

  - retry 不直接执行 SQL。
  - retry 创建新的 assistant running message，并记录 `workbench.retry_requested` event。
  - 真实重跑继续走既有 retry checkpoint / chat stream 链路。
  - legacy thread 返回 `accepted=False`。

### Task 4.4 Add retry API

- [ ] 修改 [datalogue-api/app/api/workbench.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/app/api/workbench.py)，新增：

  - `POST /actions/retry`，request model 为 `WorkbenchRetryRequest`，response model 为 `WorkbenchRetryResponse`。

  返回码规则：

  - 非法 payload：400。
  - checkpoint 不可用：409。
  - message/thread 不存在：404。
  - legacy read-only：200 with `accepted=False` and disabled reason。

### Task 4.5 Verify PR4

- [ ] 运行：

  ```bash
  cd datalogue-api
  python3 -m pytest tests/test_workbench_retry_actions.py tests/test_agentscope_lease_recovery.py tests/test_workbench_view_api.py -q
  git diff --check
  ```

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-04-controlled-retry-lease
  git add datalogue-api/app/api/workbench.py datalogue-api/app/schemas/agentscope_workbench.py datalogue-api/app/services/workbench_actions.py datalogue-api/tests/test_workbench_retry_actions.py datalogue-api/tests/test_agentscope_lease_recovery.py .codex/project-memory.md
  git commit -m "feat: add controlled workbench retry"
  ```

## PR5: Chat Workbench Panel

### Task 5.1 Write failing frontend tests

- [ ] 新增 [datalogue-web/src/assistant/workbench-api.test.js](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/assistant/workbench-api.test.js)，覆盖 thread view、artifact view、retry action 请求。

- [ ] 新增 [datalogue-web/src/components/workbench-panel.test.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/workbench-panel.test.jsx)，覆盖：

  - Chat 页面右侧渲染 Workbench Panel。
  - legacy view 显示只读提示。
  - timeline 只显示业务级摘要。
  - artifact refs 可打开详情。
  - retry disabled reason 正常显示。
  - admin diagnostic drawer 默认关闭。

- [ ] 新增 [datalogue-web/src/components/workbench-route.test.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/workbench-route.test.jsx)，覆盖隐藏 route `/workbench/:threadId/:artifactRef?`。

### Task 5.2 Add frontend API adapter

- [ ] 新增 [datalogue-web/src/assistant/workbench-api.js](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/assistant/workbench-api.js)，包含：

  ```javascript
  export async function fetchWorkbenchThread(threadId) {}
  export async function fetchWorkbenchArtifact(artifactRef) {}
  export async function requestWorkbenchRetry(payload) {}
  export function normalizeWorkbenchThreadId(routeId) {}
  ```

  `requestWorkbenchRetry` 只发送：

  ```javascript
  {
    thread_id,
    message_id,
    checkpoint_ref,
    selected_action,
  }
  ```

### Task 5.3 Add Workbench Panel components

- [ ] 新增 [datalogue-web/src/components/workbench-panel.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/workbench-panel.jsx)，包含：

  - `WorkbenchPanel`
  - `WorkbenchTimeline`
  - `WorkbenchArtifactRefs`
  - `WorkbenchActions`
  - `WorkbenchDiagnosticDrawer`

  UI 规则：

  - Panel 是工作区侧栏，不做营销式 hero。
  - 普通用户视图只展示业务摘要、refs、状态和 action。
  - admin diagnostic drawer 默认关闭，且只显示后端返回的脱敏 diagnostic。
  - action disabled 时显示 disabled reason。

- [ ] 修改 [datalogue-web/src/components/artifact-card.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/artifact-card.jsx)，让 `related_refs` 中的 `repair_plan`、`checkpoint`、`trace` 可以被 Workbench Panel 读取，但不展示内部 patch 主体。

### Task 5.4 Wire Chat page and hidden route

- [ ] 修改 [datalogue-web/src/App.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/App.jsx)，新增隐藏路由：

  ```jsx
  <Route path="/workbench/:threadId" element={<WorkbenchRoute />} />
  <Route path="/workbench/:threadId/:artifactRef" element={<WorkbenchRoute />} />
  ```

- [ ] 新增 [datalogue-web/src/components/workbench-route.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/workbench-route.jsx)，复用 `WorkbenchPanel` 的 View Model，不新建第二套解析逻辑。

- [ ] 修改 [datalogue-web/src/components/chat-page.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/chat-page.jsx)，在 Chat 主区域右侧挂载 `WorkbenchPanel`。

  规则：

  - `as_*` 显示完整工作台视图。
  - `conv_*` 显示只读工作台视图。
  - 页面窄屏时 Panel 作为抽屉打开，避免遮挡消息流。

### Task 5.5 Update chat adapter and thread list

- [ ] 修改 [datalogue-web/src/assistant/chat-adapter.js](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/assistant/chat-adapter.js)，发送新会话时接收后端返回的 `thread_id`，并把后续 stream turn 绑定到 `as_*`。

- [ ] 修改 [datalogue-web/src/assistant/thread-list-adapter.js](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/assistant/thread-list-adapter.js)，线程列表支持：

  - `as_*` 新会话。
  - `conv_*` 旧会话。
  - `/chat/:number` 的兼容展示。

### Task 5.6 Verify PR5

- [ ] 运行：

  ```bash
  cd datalogue-web
  npm run test -- src/assistant/workbench-api.test.js src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/assistant/chat-adapter.test.js src/components/chat-page.test.jsx
  npm run lint
  npm run build
  git diff --check
  ```

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-05-chat-workbench-panel
  git add datalogue-web/src/App.jsx datalogue-web/src/assistant/workbench-api.js datalogue-web/src/assistant/workbench-api.test.js datalogue-web/src/assistant/chat-adapter.js datalogue-web/src/assistant/thread-list-adapter.js datalogue-web/src/components/workbench-panel.jsx datalogue-web/src/components/workbench-panel.test.jsx datalogue-web/src/components/workbench-route.jsx datalogue-web/src/components/workbench-route.test.jsx datalogue-web/src/components/chat-page.jsx datalogue-web/src/components/artifact-card.jsx .codex/project-memory.md
  git commit -m "feat: add chat workbench panel"
  ```

## PR6: Acceptance Hardening

### Task 6.1 Add backend acceptance tests

- [ ] 新增 [datalogue-api/tests/test_c3_workbench_acceptance.py](/Users/yangkai/code_place/study/python/Datalogue/datalogue-api/tests/test_c3_workbench_acceptance.py)，覆盖双主路径：

  路径 A，新会话成功查询：

  - 请求无 conversation id。
  - 后端返回 `as_* thread_id`。
  - mirror 有 session、user message、assistant completed message。
  - mirror event 有 `task.started` 到 `answer.completed`。
  - Workbench API 能查到 thread view 和 artifact refs。

  路径 B，失败/中断 + retry：

  - 构造 assistant running lease 过期。
  - lease recovery 标记 interrupted。
  - retry action 创建新 running message。
  - retry payload 不包含 SQL/schema/raw rows。

  路径 C，legacy 只读：

  - `/chat/25` 或 `conv_25` 可回放。
  - Workbench view `read_only=True`。
  - 不创建 AgentScope mirror session。

### Task 6.2 Add frontend acceptance tests

- [ ] 新增或扩展 [datalogue-web/src/components/chat-page.test.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/src/components/chat-page.test.jsx)，覆盖：

  - `/chat/as_<uuid>` 显示 Workbench Panel。
  - `/chat/25` 显示 legacy read-only Panel。
  - Panel 文案不包含 forbidden keys。
  - 会话切换后 Panel 跟随 thread id 刷新。

- [ ] 新增或扩展 [datalogue-web/src/assistant/thread-list-new-conversation.test.jsx](/Users/yangkai/code_place/study/python/Datalogue/datalogue-web/tests/unit/assistant/thread-list-new-conversation.test.jsx)，覆盖新建会话进入 `as_*`。

### Task 6.3 Add real acceptance record

- [ ] 新增 [docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md](/Users/yangkai/code_place/study/python/Datalogue/docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md)。

  文档必须记录：

  - 测试日期。
  - 当前分支和 commit。
  - 路径 A 的 `thread_id`、`task_id`、`trace_id`、`artifact_ref`。
  - 路径 B 的 `thread_id`、`message_id`、`checkpoint_ref`。
  - 路径 C 的 legacy conversation id。
  - 页面、SSE/event envelope、后端日志、Langfuse、query_artifact/conversation_state 或 AgentScope mirror 的一致性证据。
  - 残留风险。

### Task 6.4 Run full P0 validation

- [ ] 后端：

  ```bash
  cd datalogue-api
  python3 -m pytest \
    tests/test_agentscope_mirror_models.py \
    tests/test_agentscope_thread_resolver.py \
    tests/test_agentscope_chat_bridge.py \
    tests/test_agentscope_event_projection.py \
    tests/test_workbench_view_api.py \
    tests/test_workbench_retry_actions.py \
    tests/test_agentscope_lease_recovery.py \
    tests/test_c3_workbench_acceptance.py \
    tests/test_chat.py \
    tests/test_event_envelope.py \
    tests/test_artifact_api.py \
    tests/test_legacy_conversation_replay.py -q
  ```

- [ ] 前端：

  ```bash
  cd datalogue-web
  npm run test -- src/assistant/workbench-api.test.js src/components/workbench-panel.test.jsx src/components/workbench-route.test.jsx src/assistant/chat-adapter.test.js src/components/chat-page.test.jsx tests/unit/assistant/thread-list-new-conversation.test.jsx
  npm run lint
  npm run build
  ```

- [ ] 全仓：

  ```bash
  git diff --check
  ```

### Task 6.5 Manual E2E

- [ ] 启动 API：

  ```bash
  cd datalogue-api
  uvicorn app.main:app --reload --port 8000
  ```

- [ ] 启动前端：

  ```bash
  cd datalogue-web
  npm run dev
  ```

- [ ] 在页面验证：

  - 新建 Chat 产生 `as_*`。
  - 真实问题 `查询杨凯 2024 年工作日志` 成功返回。
  - Chat 右侧 Panel 展示 timeline、Artifact refs、可用 action。
  - SSE/event envelope 与 AgentScope mirror event 使用同一 `task_id` / `trace_id`。
  - Langfuse 能找到同一 trace。
  - legacy `/chat/25` 可回放，Panel 为只读。

### Task 6.6 Final commit

- [ ] 更新 [.codex/project-memory.md](/Users/yangkai/code_place/study/python/Datalogue/.codex/project-memory.md)。

- [ ] 提交：

  ```bash
  git checkout -b c3-p0-06-acceptance-hardening
  git add datalogue-api/tests/test_c3_workbench_acceptance.py datalogue-web/src/components/chat-page.test.jsx datalogue-web/tests/unit/assistant/thread-list-new-conversation.test.jsx docs/main-chain-acceptance-records/2026-06-30-c3-agentscope-workbench.md .codex/project-memory.md
  git commit -m "test: add c3 workbench acceptance coverage"
  ```

## Merge Plan

- [ ] PR1 merge to `b-first-c`.
- [ ] Rebase PR2 on latest `b-first-c`; run PR2 tests; merge.
- [ ] Rebase PR3 on latest `b-first-c`; run PR3 tests; merge.
- [ ] Rebase PR4 on latest `b-first-c`; run PR4 tests; merge.
- [ ] Rebase PR5 on latest `b-first-c`; run PR5 tests; merge.
- [ ] Rebase PR6 on latest `b-first-c`; run full C3-P0 validation; merge.
- [ ] 本地同步：

  ```bash
  git checkout b-first-c
  git pull origin b-first-c
  ```

## Stop Conditions

立即停止并回到设计层确认的情况：

- AgentScope mirror 需要保存 SQL/schema/raw rows 才能完成视图。
- 受控 retry 绕过 checkpoint，直接接收 SQL 或 QueryGraph 主体。
- 旧会话必须迁移才能满足前端回放。
- Workbench Panel 需要读取内部字段级 patch 才能展示普通用户视图。
- AgentScope runner 被要求接管 `/chat/stream` 主链。
- 任何实现要求把 C3 mirror 当作 AgentScope Runtime ownership 完成态。

## Review Checklist

- [ ] 新会话走 `as_*`，旧会话走 `conv_*`。
- [ ] `agentscope_session/message/event/ref` 四表存在且有迁移。
- [ ] `/chat/stream` 先写 AgentScope-compatible mirror message，再运行 Datalogue 主链。
- [ ] C3 只完成 mirror / Workbench foundation，不声明 AgentScope Runtime 已接管 Datalogue 主链。
- [ ] Workbench API 返回后端 View Model，前端不拼内部细节。
- [ ] Chat 右侧 Panel 和隐藏 route 可用。
- [ ] Legacy `/chat/25` 只读回放。
- [ ] retry 只读 + 受控 checkpoint。
- [ ] 用户可见层无 SQL/schema/raw rows/query_plan/field_patch。
- [ ] 双主路径 acceptance 通过。
- [ ] `.codex/project-memory.md` 有每个 PR 的完成记录。

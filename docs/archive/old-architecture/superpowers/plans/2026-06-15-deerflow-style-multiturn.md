# DeerFlow 风格多轮问数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Datalogue 多轮问数从“上一轮 query_context + 当前短句”的脆弱合并，升级为 DeerFlow 风格的 Message Gateway + Thread Memory + Task Capsule + SubAgent 隔离执行，让第二轮追问、数据集选择、结果解释和澄清回复走各自稳定路径。

**Architecture:** 入口先由 `message_gateway` 把用户输入归类为结构化 turn event；`ConversationStore` 持久化当前线程的 active dataset、last successful query task、pending clarification 和 result digest；`MultiturnContextBuilder` 只负责把 turn event + thread memory 合成为 `QueryTaskCapsule`，SubAgent 只消费 capsule，不直接吃完整聊天历史。成功查询后把 QueryPlan/DSL/SQL/result_digest 回写线程状态，下一轮追问基于结构化状态继续。

**Tech Stack:** FastAPI + SQLAlchemy + LangGraph + LiteLLM SDK + pytest；后端主路径在 `datalogue-api/app/api/chat.py`、`datalogue-api/app/services/conversation_store.py`、`datalogue-api/app/services/multiturn_context.py`、`datalogue-api/app/services/lead_agent.py`、`datalogue-api/app/services/dataset_subagent.py`。

---

## DeerFlow 映射到 Datalogue 的设计原则

DeerFlow 2.0 的可借鉴点不是“更多 LLM”，而是 harness 层的责任拆分：Message Gateway 处理输入事件，Sub-Agents 隔离上下文，Context Engineering 控制给模型的上下文，Long-Term Memory 保存跨轮事实和偏好。Datalogue 对应为：

- `Message Gateway` -> `app/services/message_gateway.py`：把用户输入归类，不让 UI 事件进入 DSL。
- `Thread Memory` -> `ConversationStore.thread_state`：保存 active dataset、last query task、pending clarification。
- `Task Capsule` -> `app/services/task_capsule.py`：给 SubAgent 的最小任务上下文。
- `SubAgent Isolation` -> `DatasetSubAgentRequest` 只消费 capsule 派生的 standalone question 和 query constraints。
- `Context Engineering` -> DSL 渐进式披露和 QueryPlan 主表/JOIN hints。

## 多智能体执行方式

使用 subagent-driven-development 执行，每个任务一个实现子智能体，完成后两个 review 子智能体：

- Implementer Agent：按任务实现代码和测试，只改任务列出的文件。
- Spec Reviewer Agent：检查是否满足本计划的功能要求，不做泛泛代码审查。
- Code Quality Reviewer Agent：检查边界条件、状态污染、测试质量、兼容旧行为。

建议执行顺序为 Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6。Task 1/2 可并行调研，但实现时 Task 1 先合入；Task 3 依赖 Task 1/2；Task 4 依赖 Task 3；Task 5/6 可在 Task 4 后并行。

---

## File Structure

### New Files

- `datalogue-api/app/services/message_gateway.py`
  - 职责：确定性分类用户输入为 `TurnEvent`，拦截 `dataset_select`、`interpret_result`、`clarification_answer` 等非查询事件。

- `datalogue-api/app/services/task_capsule.py`
  - 职责：定义 `ThreadTaskState`、`QueryTaskCapsule`、`ResultDigest` 的纯 Python dict/dataclass 工具，负责从上一轮状态生成给 SubAgent 的最小任务上下文。

- `datalogue-api/tests/test_message_gateway.py`
  - 职责：覆盖 dataset select、new query、follow-up、interpret、clarification answer 的分类。

- `datalogue-api/tests/test_task_capsule.py`
  - 职责：覆盖 last task 回写、follow-up capsule 合成、detail query 无 metrics 仍可继承。

### Modified Files

- `datalogue-api/app/api/chat.py`
  - 在进入 LeadAgent/Graph 前调用 gateway；dataset select 直接更新 conversation active dataset 并早退；final payload 写回 task state。

- `datalogue-api/app/services/conversation_store.py`
  - 增加 thread state 读写方法，保存 active dataset 和 last successful task；第一版复用 `ConversationState.subagent_capsules["_thread"]`，不新增 migration。

- `datalogue-api/app/services/multiturn_context.py`
  - 把 `has_query_metrics()` 升级为 `has_query_target()`；detail query 允许 fields/main_table/query_plan 作为有效目标。

- `datalogue-api/app/services/lead_agent.py`
  - `merge_multiturn_decision_for_chat()` 接收 turn event / task capsule，避免直接用原始短句误判。

- `datalogue-api/app/services/dataset_subagent.py`
  - `DatasetSubAgentRequest` 接收 task capsule 派生字段；run trace 输出 capsule 摘要。

- `datalogue-api/app/graph/nodes.py`
  - 使用 task capsule 中的 `standalone_question`、`main_table`、`join_hints` 增强 DSL prompt；空 DSL 错误引用 gateway/capsule 状态。

- `datalogue-web/src/components/agent-panel.jsx`
  - 展示 turn event、task capsule、thread memory 摘要，帮助排查第二轮。

---

## Task 1: Message Gateway 拦截非查询事件

**Owner Agent:** Gateway Implementer Agent

**Files:**
- Create: `datalogue-api/app/services/message_gateway.py`
- Create: `datalogue-api/tests/test_message_gateway.py`
- Modify: `datalogue-api/app/api/chat.py`

- [ ] **Step 1: Write failing tests for turn classification**

Create `datalogue-api/tests/test_message_gateway.py`:

```python
from app.services.message_gateway import classify_turn_event


def test_dataset_select_event_is_not_query():
    event = classify_turn_event(
        "选择：生产经营管理系统日志数据集",
        active_dataset_id=None,
        has_pending_clarification=False,
        has_last_success_task=False,
    )

    assert event["event_type"] == "dataset_select"
    assert event["should_enter_graph"] is False
    assert event["dataset_name"] == "生产经营管理系统日志数据集"


def test_followup_refine_requires_last_success_task():
    event = classify_turn_event(
        "只看汤杰",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=True,
    )

    assert event["event_type"] == "followup_refine"
    assert event["should_enter_graph"] is True
    assert event["delta_intent"] == "add_filter"


def test_followup_without_prior_downgrades_to_clarify():
    event = classify_turn_event(
        "只看汤杰",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=False,
    )

    assert event["event_type"] == "clarify"
    assert event["should_enter_graph"] is False
    assert "上一轮" in event["answer"]


def test_interpret_result_event_skips_query_graph():
    event = classify_turn_event(
        "这个结果说明什么",
        active_dataset_id=10,
        has_pending_clarification=False,
        has_last_success_task=True,
    )

    assert event["event_type"] == "interpret_result"
    assert event["should_enter_graph"] is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_message_gateway.py -q
```

Expected: import error for `app.services.message_gateway`.

- [ ] **Step 3: Implement deterministic gateway**

Create `datalogue-api/app/services/message_gateway.py`:

```python
# ============================================================
# File Name   : message_gateway.py
# Description:
#   多轮问数入口消息网关，先把用户输入归类为结构化事件。
#
# Responsibilities:
#   - 拦截数据集选择、结果解释、澄清回复等非查询事件。
#   - 为 LeadAgent / SubAgent 提供稳定的 turn event。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

import re
from typing import Any


_DATASET_SELECT_RE = re.compile(r"^\s*(?:选择|切换到|使用)[：:\s]*(?P<name>.+?数据集)\s*$")
_INTERPRET_PATTERNS = ("说明什么", "怎么看", "解释", "分析一下这个结果", "这个结果")
_FOLLOWUP_FILTER_PATTERNS = ("只看", "仅看", "筛选", "限定", "换成", "改成", "改为")
_QUERY_PATTERNS = ("查", "查询", "统计", "多少", "明细", "日志", "列表", "排名", "汇总")


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def classify_turn_event(
    question: str,
    *,
    active_dataset_id: int | None,
    has_pending_clarification: bool,
    has_last_success_task: bool,
) -> dict[str, Any]:
    text = (question or "").strip()
    dataset_match = _DATASET_SELECT_RE.match(text)
    if dataset_match:
        dataset_name = dataset_match.group("name").strip()
        return {
            "event_type": "dataset_select",
            "should_enter_graph": False,
            "dataset_name": dataset_name,
            "answer": f"已选择数据集「{dataset_name}」，你可以开始提问。",
        }

    if has_pending_clarification:
        return {
            "event_type": "clarification_answer",
            "should_enter_graph": False,
            "answer": None,
        }

    if has_last_success_task and _contains_any(text, _INTERPRET_PATTERNS):
        return {
            "event_type": "interpret_result",
            "should_enter_graph": False,
            "answer": None,
        }

    if _contains_any(text, _FOLLOWUP_FILTER_PATTERNS):
        if has_last_success_task:
            return {
                "event_type": "followup_refine",
                "delta_intent": "add_filter",
                "should_enter_graph": True,
            }
        return {
            "event_type": "clarify",
            "should_enter_graph": False,
            "answer": "我没有可承接的上一轮查询结果。请先发起一个完整查询，再继续筛选。",
        }

    if _contains_any(text, _QUERY_PATTERNS):
        return {
            "event_type": "new_query",
            "should_enter_graph": True,
        }

    return {
        "event_type": "clarify",
        "should_enter_graph": False,
        "answer": "请告诉我要查询的数据、筛选条件或分析目标。",
    }
```

- [ ] **Step 4: Wire gateway into chat entry before LangGraph**

Modify `datalogue-api/app/api/chat.py` at the point where the chat request is prepared before `build_workflow()` is invoked:

```python
from app.services.message_gateway import classify_turn_event
```

Then compute:

```python
thread_state = conversation_store.get_thread_state(conversation_id) if conversation_id else {}
turn_event = classify_turn_event(
    request.question,
    active_dataset_id=thread_state.get("active_dataset_id") or request.dataset_id,
    has_pending_clarification=bool(pending_clarification),
    has_last_success_task=bool(thread_state.get("last_success_task")),
)
```

If `turn_event["event_type"] == "dataset_select"`:

```python
dataset = _find_dataset_by_name(db, turn_event["dataset_name"])
conversation_store.update_thread_state(
    conversation_id,
    {
        "active_dataset_id": dataset.id,
        "active_dataset_name": dataset.name,
        "last_turn_event": turn_event,
    },
)
yield _sse_final_answer(
    answer=turn_event["answer"],
    metadata={"turn_event": turn_event, "dataset_id": dataset.id},
)
return
```

If `turn_event["event_type"] == "clarify"`:

```python
yield _sse_final_answer(
    answer=turn_event["answer"],
    metadata={"turn_event": turn_event},
)
return
```

Use the existing stream final helper shape in `chat.py`; do not introduce a second SSE format.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_message_gateway.py tests/test_chat.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/services/message_gateway.py datalogue-api/app/api/chat.py datalogue-api/tests/test_message_gateway.py
git commit -m "feat: add message gateway for multiturn events"
```

---

## Task 2: Thread Memory 和 QueryTaskCapsule

**Owner Agent:** Memory Capsule Implementer Agent

**Files:**
- Create: `datalogue-api/app/services/task_capsule.py`
- Create: `datalogue-api/tests/test_task_capsule.py`
- Modify: `datalogue-api/app/services/conversation_store.py`

- [ ] **Step 1: Write tests for task state and capsule**

Create `datalogue-api/tests/test_task_capsule.py`:

```python
from app.services.task_capsule import (
    build_query_task_capsule,
    build_success_task_state,
    has_query_target,
)


def test_detail_query_has_target_without_metrics():
    task = {
        "query_type": "detail_query",
        "main_table": "plan_task_daily_record",
        "fields": [{"name": "rzrq"}],
        "metrics": [],
    }

    assert has_query_target(task) is True


def test_metric_query_requires_metrics():
    task = {
        "query_type": "metric_query",
        "fields": [{"name": "rzrq"}],
        "metrics": [],
    }

    assert has_query_target(task) is False


def test_build_success_task_state_keeps_query_plan_and_result_digest():
    state = build_success_task_state(
        question="查询10条用户日志",
        dataset_id=10,
        query_plan={
            "query_type": "detail_query",
            "debug": {"selected_main_table": "plan_task_daily_record"},
        },
        dsl={"fields": [{"name": "rzrq"}]},
        sql="SELECT rzrq FROM plan_task_daily_record LIMIT 10",
        sql_result={"columns": ["rzrq"], "rows": [{"rzrq": "2024-01-01"}], "row_count": 1},
    )

    assert state["dataset_id"] == 10
    assert state["query_type"] == "detail_query"
    assert state["main_table"] == "plan_task_daily_record"
    assert state["result_digest"]["row_count"] == 1
    assert state["result_digest"]["columns"] == ["rzrq"]


def test_followup_capsule_uses_prior_detail_query_context():
    capsule = build_query_task_capsule(
        question="只看汤杰",
        turn_event={"event_type": "followup_refine", "delta_intent": "add_filter"},
        active_dataset_id=10,
        last_success_task={
            "question": "查询10条用户日志",
            "query_type": "detail_query",
            "main_table": "plan_task_daily_record",
            "query_plan": {
                "query_type": "detail_query",
                "debug": {"selected_main_table": "plan_task_daily_record"},
            },
            "dsl": {"fields": [{"name": "rzrq"}]},
        },
    )

    assert capsule["turn_type"] == "followup_refine"
    assert capsule["dataset_id"] == 10
    assert capsule["base_main_table"] == "plan_task_daily_record"
    assert "查询10条用户日志" in capsule["standalone_question"]
    assert "只看汤杰" in capsule["standalone_question"]
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_task_capsule.py -q
```

Expected: import error for `task_capsule`.

- [ ] **Step 3: Implement task capsule helpers**

Create `datalogue-api/app/services/task_capsule.py`:

```python
# ============================================================
# File Name   : task_capsule.py
# Description:
#   多轮问数任务胶囊，把线程记忆转成 SubAgent 可消费的最小上下文。
#
# Responsibilities:
#   - 保存上一轮成功查询的结构化摘要。
#   - 生成第二轮追问的 standalone question 和基础约束。
#
# Author      : yangkai
# Created On  : 2026-06-15
# ============================================================

from __future__ import annotations

from typing import Any


def has_query_target(task: dict[str, Any] | None) -> bool:
    if not isinstance(task, dict):
        return False
    query_type = task.get("query_type")
    if query_type == "detail_query":
        return bool(task.get("fields") or task.get("main_table") or task.get("query_plan"))
    return bool(task.get("metrics"))


def _result_digest(sql_result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sql_result, dict):
        return {"row_count": 0, "columns": [], "sample_rows": []}
    rows = sql_result.get("rows") or []
    return {
        "row_count": int(sql_result.get("row_count") or len(rows)),
        "columns": list(sql_result.get("columns") or []),
        "sample_rows": rows[:5],
    }


def build_success_task_state(
    *,
    question: str,
    dataset_id: int | None,
    query_plan: dict[str, Any] | None,
    dsl: dict[str, Any] | None,
    sql: str | None,
    sql_result: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = query_plan or {}
    debug = plan.get("debug") if isinstance(plan.get("debug"), dict) else {}
    dsl_payload = dsl or {}
    return {
        "question": question,
        "dataset_id": dataset_id,
        "query_type": plan.get("query_type"),
        "main_table": debug.get("selected_main_table"),
        "query_plan": plan,
        "dsl": dsl_payload,
        "fields": dsl_payload.get("fields") or [],
        "metrics": dsl_payload.get("metrics") or [],
        "sql": sql,
        "result_digest": _result_digest(sql_result),
    }


def build_query_task_capsule(
    *,
    question: str,
    turn_event: dict[str, Any],
    active_dataset_id: int | None,
    last_success_task: dict[str, Any] | None,
) -> dict[str, Any]:
    event_type = turn_event.get("event_type") or "new_query"
    capsule = {
        "task_type": "query",
        "turn_type": event_type,
        "dataset_id": active_dataset_id,
        "question": question,
        "standalone_question": question,
        "base_task_ref": None,
        "base_main_table": None,
        "base_query_plan": None,
    }
    if event_type.startswith("followup") and last_success_task:
        prior_question = last_success_task.get("question") or ""
        capsule.update(
            {
                "standalone_question": f"基于上一轮问题「{prior_question}」，{question}",
                "base_task_ref": "last_success_task",
                "base_main_table": last_success_task.get("main_table"),
                "base_query_plan": last_success_task.get("query_plan"),
            }
        )
    return capsule
```

- [ ] **Step 4: Add ConversationStore thread state methods**

Modify `datalogue-api/app/services/conversation_store.py` to add methods on `ConversationStore`:

```python
THREAD_STATE_KEY = "_thread"


def get_thread_state(self, session_id: str | None) -> dict:
    if not session_id:
        return {}
    state = self.load(session_id)
    if not state:
        return {}
    capsules = dict(state.subagent_capsules or {})
    return dict(capsules.get(THREAD_STATE_KEY) or {})


def update_thread_state(self, session_id: str | None, patch: dict) -> dict:
    if not session_id:
        return {}
    state = self.load_or_create(session_id, user_id="default")
    capsules = dict(state.subagent_capsules or {})
    thread_state = dict(capsules.get(THREAD_STATE_KEY) or {})
    thread_state.update(patch)
    capsules[THREAD_STATE_KEY] = thread_state
    state.subagent_capsules = capsules
    self.db.commit()
    return thread_state
```

`ConversationStore` 当前管理的是 `ConversationState`，不是 `Conversation` / `Message` CRUD。`Conversation` 主表没有 JSON 状态列；不要把 thread state 写到 `Conversation.response_metadata` 或新增 `Conversation.metadata_json`。第一版固定写入 `ConversationState.subagent_capsules["_thread"]`，不加列、不写 migration。调用方传入的 `session_id` 应使用现有 `session_key(conversation_id)`。

- [ ] **Step 5: Run focused tests**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_task_capsule.py tests/test_dataset_subagent.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/services/task_capsule.py datalogue-api/app/services/conversation_store.py datalogue-api/tests/test_task_capsule.py
git commit -m "feat: add thread task capsule for multiturn queries"
```

---

## Task 3: 修复 MultiturnContextBuilder 对明细查询的错误降级

**Owner Agent:** Multiturn Resolver Implementer Agent

**Files:**
- Modify: `datalogue-api/app/services/multiturn_context.py`
- Modify: `datalogue-api/app/services/lead_agent.py`
- Modify: `datalogue-api/tests/test_multiturn_context_builder.py`
- Modify: `datalogue-api/tests/test_lead_agent_tools.py`

- [ ] **Step 1: Write failing tests for detail query follow-up**

Add to `datalogue-api/tests/test_multiturn_context_builder.py`:

```python
def test_detail_query_followup_keeps_prior_without_metrics():
    from app.services.multiturn_context import MultiturnContextBuilder

    builder = MultiturnContextBuilder()
    decision = builder.build(
        {
            "question": "只看汤杰",
            "turn_type": "continue",
            "prior_capsule": {
                "query_context": {
                    "query_type": "detail_query",
                    "fields": [{"name": "rzrq"}],
                    "main_table": "plan_task_daily_record",
                    "question": "查询10条用户日志",
                }
            },
        }
    )

    assert decision.turn_type == "continue"
    assert decision.multiturn_context["merged_query_context"]["main_table"] == "plan_task_daily_record"
    assert decision.merge_debug["reason"] == "continue_turn_with_prior_query_context"
```

- [ ] **Step 2: Run test and verify current failure**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_multiturn_context_builder.py::test_detail_query_followup_keeps_prior_without_metrics -q
```

Expected before implementation: fails because builder downgrades to new query when metrics are empty.

- [ ] **Step 3: Replace `has_query_metrics` with `has_query_target`**

Modify `datalogue-api/app/services/multiturn_context.py`:

```python
def has_query_target(self, query_context: dict) -> bool:
    query_type = query_context.get("query_type")
    if query_type == "detail_query":
        return bool(
            query_context.get("fields")
            or query_context.get("main_table")
            or query_context.get("query_plan")
            or query_context.get("dsl")
        )
    metrics = query_context.get("metrics")
    return bool(metrics)
```

Then replace:

```python
if not self.has_query_metrics(merged_query_context):
```

with:

```python
if not self.has_query_target(merged_query_context):
```

Keep `has_query_metrics()` as a backward-compatible wrapper if existing tests import it:

```python
def has_query_metrics(self, query_context: dict) -> bool:
    return self.has_query_target(query_context)
```

- [ ] **Step 4: Add task capsule into lead merge state**

Modify `merge_multiturn_decision_for_chat()` call site in `chat.py` or `lead_agent.py` so state contains:

```python
state["turn_event"] = turn_event
state["query_task_capsule"] = query_task_capsule
```

Then in `MultiturnContextBuilder.build()` prefer capsule base context when available:

```python
capsule = _as_dict(state.get("query_task_capsule"))
if capsule.get("base_query_plan") and not prior_query_context:
    prior_query_context = {
        "query_type": (capsule["base_query_plan"] or {}).get("query_type"),
        "query_plan": capsule.get("base_query_plan"),
        "main_table": capsule.get("base_main_table"),
        "question": capsule.get("standalone_question"),
    }
```

- [ ] **Step 5: Run multiturn tests**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_multiturn_context_builder.py tests/test_lead_agent_tools.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/services/multiturn_context.py datalogue-api/app/services/lead_agent.py datalogue-api/tests/test_multiturn_context_builder.py datalogue-api/tests/test_lead_agent_tools.py
git commit -m "fix: preserve detail query context across followups"
```

---

## Task 4: Chat API 接入 Thread Memory 和 Result Digest 回写

**Owner Agent:** Chat Integration Implementer Agent

**Files:**
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/app/services/conversation_store.py`
- Modify: `datalogue-api/tests/test_chat.py`

- [ ] **Step 1: Write API tests for dataset select and second-turn refine**

Add to `datalogue-api/tests/test_chat.py`:

```python
def test_dataset_select_does_not_enter_workflow(monkeypatch, db_session, sample_dataset):
    from app.api.chat import _stream_chat
    from app.schemas import ChatRequest

    called = {"workflow": False}

    def fail_build_workflow(*_args, **_kwargs):
        called["workflow"] = True
        raise AssertionError("dataset select should not enter workflow")

    monkeypatch.setattr("app.api.chat.build_workflow", fail_build_workflow)

    async def collect():
        events = []
        async for item in _stream_chat(
            ChatRequest(question=f"选择：{sample_dataset.name}", dataset_id=None),
            db_session,
        ):
            events.append(item)
        return events

    events = asyncio.run(collect())
    assert called["workflow"] is False
    assert any("已选择数据集" in str(event) for event in events)


def test_successful_query_writes_last_success_task(db_session, sample_dataset, monkeypatch):
    import asyncio
    import json

    from app.api.chat import _stream_chat
    from app.schemas import ChatRequest
    from app.services.conversation_store import ConversationStore

    class FakeGraph:
        async def astream_events(self, initial_state, version):
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        **initial_state,
                        "answer": "查询完成",
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "debug": {"selected_main_table": "plan_task_daily_record"},
                        },
                        "dsl": {"fields": [{"name": "rzrq", "asset_type": "field", "asset_id": 1}]},
                        "sql": "SELECT rzrq FROM plan_task_daily_record LIMIT 10",
                        "sql_result": {
                            "columns": ["rzrq"],
                            "rows": [{"rzrq": "2024-01-01"}],
                            "row_count": 1,
                        },
                        "error": None,
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

    monkeypatch.setattr("app.api.chat.build_workflow", lambda *_args, **_kwargs: FakeGraph())

    conversation = ConversationStore(db_session).create_conversation(
        title="多轮测试",
        dataset_id=sample_dataset.id,
    )

    async def collect():
        events = []
        async for item in _stream_chat(
            ChatRequest(
                question="查询10条用户日志",
                dataset_id=sample_dataset.id,
                conversation_id=conversation.id,
            ),
            db_session,
        ):
            events.append(json.loads(item["data"]))
        return events

    events = asyncio.run(collect())
    assert events[-1]["type"] == "final"

    thread_state = ConversationStore(db_session).get_thread_state(conversation.id)
    assert thread_state["last_success_task"]["query_type"] == "detail_query"
    assert thread_state["last_success_task"]["main_table"] == "plan_task_daily_record"
    assert thread_state["last_success_task"]["result_digest"]["row_count"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_chat.py::test_dataset_select_does_not_enter_workflow -q
```

Expected: fail until gateway is wired.

- [ ] **Step 3: Build and pass QueryTaskCapsule into initial state**

In `datalogue-api/app/api/chat.py`, after thread state and turn event are known:

```python
from app.services.task_capsule import build_query_task_capsule, build_success_task_state
```

Build:

```python
query_task_capsule = build_query_task_capsule(
    question=request.question,
    turn_event=turn_event,
    active_dataset_id=effective_dataset_id,
    last_success_task=thread_state.get("last_success_task"),
)
```

Initial LangGraph state must include:

```python
"turn_event": turn_event,
"query_task_capsule": query_task_capsule,
"question": query_task_capsule.get("standalone_question") or request.question,
"original_question": request.question,
```

- [ ] **Step 4: Write success task state after final successful query**

When final graph state has `sql_result` and no `error`, write:

```python
last_success_task = build_success_task_state(
    question=final_state.get("original_question") or request.question,
    dataset_id=final_state.get("dataset_id"),
    query_plan=final_state.get("query_plan"),
    dsl=final_state.get("dsl"),
    sql=final_state.get("sql"),
    sql_result=final_state.get("sql_result"),
)
conversation_store.update_thread_state(
    conversation_id,
    {
        "active_dataset_id": final_state.get("dataset_id"),
        "last_success_task": last_success_task,
        "last_turn_event": turn_event,
    },
)
```

- [ ] **Step 5: Run chat tests**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_chat.py tests/test_task_capsule.py tests/test_message_gateway.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/api/chat.py datalogue-api/app/services/conversation_store.py datalogue-api/tests/test_chat.py
git commit -m "feat: persist multiturn task memory in chat"
```

---

## Task 5: SubAgent / DSL 消费 QueryTaskCapsule

**Owner Agent:** SubAgent Integration Implementer Agent

**Files:**
- Modify: `datalogue-api/app/services/dataset_subagent.py`
- Modify: `datalogue-api/app/graph/nodes.py`
- Modify: `datalogue-api/tests/test_subagent_run.py`
- Modify: `datalogue-api/tests/test_query_plan_prompting.py`

- [ ] **Step 1: Write tests for capsule propagation**

Add to `datalogue-api/tests/test_subagent_run.py`:

```python
def test_subagent_initial_state_contains_task_capsule(monkeypatch, db_session):
    from app.services.dataset_subagent import DatasetSubAgent, DatasetSubAgentRequest

    captured = {}

    class FakeGraph:
        async def astream_events(self, initial_state, version):
            captured["initial_state"] = initial_state
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {"output": {"answer": "ok", "sql_result": {"rows": []}}},
                "metadata": {"langgraph_node": "report_generator"},
            }

    subagent = DatasetSubAgent(db_session, dataset_id=10)
    request = DatasetSubAgentRequest(
        question="只看汤杰",
        dataset_id=10,
        query_task_capsule={
            "turn_type": "followup_refine",
            "standalone_question": "基于上一轮问题「查询10条用户日志」，只看汤杰",
            "base_main_table": "plan_task_daily_record",
        },
    )

    events = []
    async def collect():
        async for event in subagent.run(request, trace_context=None, graph=FakeGraph()):
            events.append(event)

    asyncio.run(collect())
    assert captured["initial_state"]["query_task_capsule"]["base_main_table"] == "plan_task_daily_record"
    assert captured["initial_state"]["question"].startswith("基于上一轮问题")
```

- [ ] **Step 2: Run test and verify failure**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py::test_subagent_initial_state_contains_task_capsule -q
```

Expected: fails until `DatasetSubAgentRequest` accepts `query_task_capsule`.

- [ ] **Step 3: Extend DatasetSubAgentRequest**

Modify request model/dataclass in `datalogue-api/app/services/dataset_subagent.py`:

```python
query_task_capsule: dict[str, Any] | None = None
turn_event: dict[str, Any] | None = None
```

When building graph initial state:

```python
capsule = request.query_task_capsule or {}
question = capsule.get("standalone_question") or request.question
initial_state.update(
    {
        "question": question,
        "original_question": request.question,
        "query_task_capsule": capsule or None,
        "turn_event": request.turn_event,
    }
)
```

- [ ] **Step 4: Add capsule context to DSL prompt**

In `datalogue-api/app/graph/nodes.py`, add helper:

```python
def _format_task_capsule_for_prompt(capsule: dict | None) -> str:
    if not isinstance(capsule, dict) or not capsule:
        return ""
    lines = ["【任务胶囊】"]
    for key in ("turn_type", "base_task_ref", "base_main_table", "standalone_question"):
        if capsule.get(key):
            lines.append(f"{key}: {capsule[key]}")
    return "\n".join(lines)
```

Append it near query planning context:

```python
task_capsule_prompt = _format_task_capsule_for_prompt(state.get("query_task_capsule"))
if task_capsule_prompt and task_capsule_prompt not in human_text:
    human_text += f"\n\n{task_capsule_prompt}"
```

- [ ] **Step 5: Run tests**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_subagent_run.py tests/test_query_plan_prompting.py tests/test_chat.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/services/dataset_subagent.py datalogue-api/app/graph/nodes.py datalogue-api/tests/test_subagent_run.py datalogue-api/tests/test_query_plan_prompting.py
git commit -m "feat: pass multiturn task capsule to subagent"
```

---

## Task 6: 可观测与端到端回归

**Owner Agent:** Observability and E2E Implementer Agent

**Files:**
- Modify: `datalogue-api/app/api/chat.py`
- Modify: `datalogue-api/app/services/observability/tracer.py`
- Modify: `datalogue-web/src/components/agent-panel.jsx`
- Modify: `datalogue-api/tests/test_chat.py`

- [ ] **Step 1: Add trace assertions**

Add to `datalogue-api/tests/test_chat.py`:

```python
def test_stream_final_includes_turn_event_and_task_capsule(db_session, sample_dataset, monkeypatch):
    import asyncio
    import json

    from app.api.chat import _stream_chat
    from app.schemas import ChatRequest

    class FakeGraph:
        async def astream_events(self, initial_state, version):
            yield {
                "event": "on_chain_end",
                "name": "report_generator",
                "data": {
                    "output": {
                        **initial_state,
                        "answer": "查询完成",
                        "query_plan": {
                            "query_type": "detail_query",
                            "execution_strategy": "query_graph",
                            "debug": {"selected_main_table": "plan_task_daily_record"},
                        },
                        "dsl": {"fields": [{"name": "rzrq", "asset_type": "field", "asset_id": 1}]},
                        "sql": "SELECT rzrq FROM plan_task_daily_record LIMIT 10",
                        "sql_result": {
                            "columns": ["rzrq"],
                            "rows": [{"rzrq": "2024-01-01"}],
                            "row_count": 1,
                        },
                        "error": None,
                    }
                },
                "metadata": {"langgraph_node": "report_generator"},
            }

    monkeypatch.setattr("app.api.chat.build_workflow", lambda *_args, **_kwargs: FakeGraph())

    async def collect():
        events = []
        async for item in _stream_chat(
            ChatRequest(question="查询10条用户日志", dataset_id=sample_dataset.id),
            db_session,
        ):
            events.append(json.loads(item["data"]))
        return events

    events = asyncio.run(collect())
    final = events[-1]

    assert final["type"] == "final"
    assert final["turn_event"]["event_type"] in {"new_query", "followup_refine"}
    assert "query_task_capsule" in final
    assert final["query_task_capsule"]["dataset_id"] == sample_dataset.id
```

- [ ] **Step 2: Expose turn event in stream step**

In `chat.py`, emit a `step` event before graph execution:

```python
yield _sse_step(
    node="message_gateway",
    display_name="message_gateway",
    status="done",
    payload={
        "turn_event": turn_event,
        "query_task_capsule": query_task_capsule,
    },
)
```

Use existing SSE step helper and naming conventions.

- [ ] **Step 3: Add frontend display**

Modify `datalogue-web/src/components/agent-panel.jsx` to render:

```jsx
{step.node === 'message_gateway' && step.turn_event ? (
  <StructuredBlock
    title="Turn Event"
    value={step.turn_event}
  />
) : null}
```

Use the existing structured JSON rendering component in `agent-panel.jsx`; do not introduce a new UI library.

- [ ] **Step 4: Run backend and frontend checks**

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_chat.py tests/test_message_gateway.py tests/test_task_capsule.py -q
cd datalogue-web && npm run lint
cd datalogue-web && npm run build
```

Expected:

- Backend tests pass.
- Frontend lint has no new errors.
- Frontend build succeeds.

- [ ] **Step 5: Manual E2E scenario**

Run local API/web and verify these flows:

```text
1. 用户：选择：生产经营管理系统日志数据集
   期望：message_gateway 早退，回复已选择数据集，不出现 dsl_generate。

2. 用户：查询10条用户日志
   期望：进入 QueryGraph 或 dataset10_log_detail 模板，last_success_task 写入。

3. 用户：只看汤杰
   期望：turn_event=followup_refine，query_task_capsule 继承 base_main_table=plan_task_daily_record。

4. 用户：这个结果说明什么
   期望：turn_event=interpret_result，不进入 SQL 生成，基于 result_digest 回复。
```

- [ ] **Step 6: Commit**

```bash
git add datalogue-api/app/api/chat.py datalogue-api/app/services/observability/tracer.py datalogue-web/src/components/agent-panel.jsx datalogue-api/tests/test_chat.py
git commit -m "feat: expose multiturn gateway and task capsule traces"
```

---

## Final Verification

After all tasks are complete:

```bash
cd datalogue-api && .venv/bin/python -m pytest tests/test_message_gateway.py tests/test_task_capsule.py tests/test_multiturn_context_builder.py tests/test_lead_agent_tools.py tests/test_subagent_run.py tests/test_query_plan_prompting.py tests/test_chat.py -q
cd datalogue-web && npm run lint
cd datalogue-web && npm run build
git diff --check
```

Expected:

- No failing backend tests.
- No frontend build failure.
- `git diff --check` clean.
- Langfuse / frontend steps show `message_gateway`、`lead.merge_prior_context`、`subagent.query_plan`、`dsl_generate` with clear turn event and task capsule context.

## Subagent Review Prompts

### Implementer Prompt Template

```markdown
You are implementing Task <N> from docs/superpowers/plans/2026-06-15-deerflow-style-multiturn.md.

Scope:
- Only modify the files listed in Task <N>.
- Follow the exact test-first steps.
- Do not refactor unrelated code.
- Preserve current public response payloads unless the task explicitly changes them.

Return:
- Status: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
- Files changed
- Tests run and results
- Any behavior changes or risks
```

### Spec Reviewer Prompt Template

```markdown
Review the implementation of Task <N> against docs/superpowers/plans/2026-06-15-deerflow-style-multiturn.md.

Check only spec compliance:
- Were all required files changed?
- Were all required tests added?
- Does behavior match the task requirements?
- Did the implementation add unrelated behavior?

Return:
- APPROVED or CHANGES_REQUIRED
- Concrete missing or extra behavior, with file paths and line references
```

### Code Quality Reviewer Prompt Template

```markdown
Review the implementation of Task <N> for code quality.

Focus:
- State persistence correctness
- No accidental graph entry for dataset_select
- No leakage of previous conversation text into SubAgent prompt
- Test quality and edge cases
- Compatibility with existing Chat API and LangGraph flow

Return:
- APPROVED or CHANGES_REQUIRED
- Findings ordered by severity, with file paths and line references
```

## Self-Review

- Spec coverage: Covers dataset selection misrouting, second-turn detail query without metrics, thread memory, task capsule, SubAgent isolation, observability, and E2E verification.
- Placeholder scan: No implementation placeholder remains. The only `...` text is Python's `tuple[str, ...]` type annotation.
- Type consistency: `turn_event`, `query_task_capsule`, `last_success_task`, `result_digest`, `main_table`, `query_plan`, `standalone_question` are used consistently across tasks.

# BI LeadAgent K1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 BI LeadAgent K1 后端契约和最小 run-centric API，让 AgentScope BI LeadAgent 通过业务级 `query_dataset` handoff 调用真实 AgentScope 2.0 DatasetAgent tool-calling 链路。

**Architecture:** Datalogue DB 是业务状态真相源，保存 BI LeadAgent run、用户确认快照和 handoff 记录。BI LeadAgent 只暴露 `list_dataset_capabilities`、`request_dataset_confirmation`、`query_dataset`，Dataset 原子工具只在 DatasetAgent Runtime 内部通过 AgentScope 2.0 SDK external tool event 执行。Host Adapter 使用 AgentScope 2.0 SDK 的 `ToolBase`、`Toolkit`、`RequireExternalExecutionEvent`、`ExternalExecutionResultEvent`、`ToolResultBlock` 和 `agent.reply_stream()`/`agent.reply()` 事件回填链路。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、Pydantic、pytest、AgentScope 2.0 SDK `agentscope==2.0.3`、Datalogue BI atomic toolkit、Datalogue Agentic Shell sanitizer。

---

## 0. Scope And Guardrails

本计划只覆盖 K1/L2：

- 后端契约。
- 最小 run-centric API。
- Datalogue DB 真相源。
- 真实 AgentScope 2.0 DatasetAgent tool-calling。
- 开发/测试环境可用 fallback 标记。
- W2 测试范围。

本计划不覆盖：

- 完整前端确认卡片。
- 高置信度自动执行。
- 多数据集自动查询。
- AgentScope 长生命周期会话 agent。
- 完整 UI 交互记录。
- 细分所有错误码用户文案。

执行前必须确认：

```bash
cd /Users/yangkai/code_place/study/python/Datalogue
git status --short
```

如果工作区已有非本任务改动，只 stage 本计划涉及文件。

## 1. File Structure

Create:

- `datalogue-api/app/models/bi_lead_agent.py`  
  保存 `BILeadAgentRun`、`BILeadAgentConfirmation`、`BIAgentHandoff` 三张表的 SQLAlchemy 模型。

- `datalogue-api/alembic/versions/r2s3t4u5v6w7_add_bi_lead_agent_handoff.py`  
  创建三张表和索引，兼容 SQLite 测试与 PostgreSQL。

- `datalogue-api/app/schemas/bi_lead_agent.py`  
  定义 capability、run、confirmation、handoff、API request/response 的 Pydantic 契约。

- `datalogue-api/app/services/bi_lead_agent/__init__.py`  
  暴露 BI LeadAgent K1 服务入口。

- `datalogue-api/app/services/bi_lead_agent/capabilities.py`  
  生成“三开一藏” capability manifest，并提供 A1 数据集能力摘要裁剪。

- `datalogue-api/app/services/bi_lead_agent/run_service.py`  
  创建 run、推进 phase/status、生成 GET run 响应。

- `datalogue-api/app/services/bi_lead_agent/confirmation_service.py`  
  生成并保存 H2 确认快照，校验未确认不得 handoff。

- `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`  
  Datalogue Host Handoff Adapter，使用 AgentScope 2.0 SDK DatasetAgent external tool event 链路。

- `datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py`  
  用 AgentScope 2.0 SDK `agentscope.agent.Agent`、`OpenAIChatModel`、`OpenAICredential` 和 session 级 `Toolkit` 构造真实 DatasetAgent。

- `datalogue-api/app/services/bi_lead_agent/handoff_service.py`  
  创建 handoff 记录、调用 adapter、映射 D2 安全结果和 E2 状态。

- `datalogue-api/app/api/bi_lead_agent.py`  
  提供 M2 run-centric 最小 API。

- `datalogue-api/tests/test_bi_lead_agent_models.py`  
  模型和 JSON 字段测试。

- `datalogue-api/tests/test_bi_lead_agent_capabilities.py`  
  capability manifest 和 A1 安全裁剪测试。

- `datalogue-api/tests/test_bi_lead_agent_services.py`  
  run、confirmation、handoff 服务单测。

- `datalogue-api/tests/test_bi_lead_agent_api.py`  
  M2 API 测试。

- `datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py`  
  AgentScope 2.0 SDK external event 集成测试。

Modify:

- `datalogue-api/app/models/__init__.py`  
  导出新模型。

- `datalogue-api/app/api/__init__.py`  
  注册 `/api/bi-lead-agent` router。

- `datalogue-api/app/core/config.py`  
  增加 `BI_LEAD_AGENT_DATASET_FALLBACK_MODE` 配置，默认 `off`。

- `.codex/project-memory.md`  
  实施完成后记录功能完成情况。

## 2. Task List

### Task 1: 数据模型和迁移

**Files:**

- Create: `datalogue-api/app/models/bi_lead_agent.py`
- Create: `datalogue-api/alembic/versions/r2s3t4u5v6w7_add_bi_lead_agent_handoff.py`
- Modify: `datalogue-api/app/models/__init__.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_models.py`

- [ ] **Step 1: Write failing model test**

Create `datalogue-api/tests/test_bi_lead_agent_models.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_models.py
# Description:
#   BI LeadAgent K1 数据模型测试。
#
# Responsibilities:
#   - 验证 run、confirmation、handoff 三张表可在 SQLite 测试库中写入和关联。
#   - 验证 JSON 快照字段只保存路由级摘要。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.models.bi_lead_agent import BIAgentHandoff, BILeadAgentConfirmation, BILeadAgentRun


def test_bi_lead_agent_models_persist_k1_contract(db_session):
    run = BILeadAgentRun(
        status="waiting_confirmation",
        phase="confirm_run",
        question="统计 2026 年订单金额",
        trace_id="trace-bi-001",
        task_id="task-bi-001",
    )
    db_session.add(run)
    db_session.flush()

    confirmation = BILeadAgentConfirmation(
        run_id=run.id,
        dataset_id=12,
        confirmed_question="统计 2026 年订单金额",
        task_goal="按确认的数据集执行单数据集问数",
        capability_snapshot_json={
            "dataset_id": 12,
            "name": "订单数据集",
            "domain": "销售",
            "key_metrics": ["订单金额"],
            "key_dimensions": ["月份"],
            "availability": "ready",
        },
        routing_rationale="订单金额问题应由订单数据集回答。",
        risk_notice="本次只执行只读聚合查询。",
        user_decision="approved",
        trace_id="trace-bi-001",
        parent_run_id=str(run.id),
    )
    db_session.add(confirmation)

    handoff = BIAgentHandoff(
        run_id=run.id,
        handoff_id="handoff-001",
        parent_agent="bi_lead_agent",
        child_agent="dataset_agent",
        child_run_id="dataset-run-001",
        dataset_id=12,
        task_id="task-bi-001",
        trace_id="trace-bi-001",
        handoff_status="completed",
        answer_summary="订单金额汇总完成。",
        artifact_ref="artifact-001",
        checkpoint_ref="checkpoint-001",
        row_count=10,
        column_count=3,
    )
    db_session.add(handoff)
    db_session.commit()

    saved = db_session.query(BILeadAgentRun).filter_by(trace_id="trace-bi-001").one()
    assert saved.status == "waiting_confirmation"
    assert saved.phase == "confirm_run"
    assert saved.confirmation.dataset_id == 12
    assert saved.handoff.handoff_status == "completed"
    assert "schema" not in saved.confirmation.capability_snapshot_json
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.bi_lead_agent'`.

- [ ] **Step 3: Create model file**

Create `datalogue-api/app/models/bi_lead_agent.py`:

```python
# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 业务状态模型。
#
# Responsibilities:
#   - 保存 BI LeadAgent 多阶段 run 的业务真相源。
#   - 保存用户确认快照和 BI LeadAgent 到 DatasetAgent 的任务交接记录。
#   - 为 K2 页面恢复、审计和后续 AgentScope native handoff 提供稳定引用。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.core.database import Base


def _json_type():
    """兼容 SQLite 测试和 PostgreSQL 生产环境的 JSON 类型。"""

    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class BILeadAgentRun(Base):
    """BI LeadAgent F2 多阶段 run；Datalogue DB 侧业务真相源。"""

    __tablename__ = "bi_lead_agent_run"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(40), nullable=False, default="created", server_default="created", index=True)
    phase = Column(String(40), nullable=False, default="route_run", server_default="route_run", index=True)
    question = Column(Text, nullable=False)
    trace_id = Column(String(120), nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    status_reason = Column(String(120), nullable=True)
    error_code = Column(String(80), nullable=True, index=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)

    confirmation = relationship("BILeadAgentConfirmation", back_populates="run", uselist=False)
    handoff = relationship("BIAgentHandoff", back_populates="run", uselist=False)


class BILeadAgentConfirmation(Base):
    """用户显式确认快照；只保存路由级摘要，不保存 DatasetAgent 内部上下文。"""

    __tablename__ = "bi_lead_agent_confirmation"
    __table_args__ = (UniqueConstraint("run_id", name="uq_bi_lead_agent_confirmation_run_id"),)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("bi_lead_agent_run.id"), nullable=False, index=True)
    dataset_id = Column(Integer, nullable=False, index=True)
    confirmed_question = Column(Text, nullable=False)
    task_goal = Column(Text, nullable=False)
    capability_snapshot_json = Column(_json_type(), nullable=False, default=dict)
    routing_rationale = Column(Text, nullable=False)
    risk_notice = Column(Text, nullable=True)
    user_decision = Column(String(40), nullable=False, index=True)
    trace_id = Column(String(120), nullable=False, index=True)
    parent_run_id = Column(String(80), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    run = relationship("BILeadAgentRun", back_populates="confirmation")


class BIAgentHandoff(Base):
    """BI LeadAgent 到 DatasetAgent 的任务交接记录；后续 native handoff 的替换边界。"""

    __tablename__ = "bi_agent_handoff"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_bi_agent_handoff_run_id"),
        UniqueConstraint("handoff_id", name="uq_bi_agent_handoff_handoff_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("bi_lead_agent_run.id"), nullable=False, index=True)
    handoff_id = Column(String(120), nullable=False, index=True)
    parent_agent = Column(String(80), nullable=False, default="bi_lead_agent", server_default="bi_lead_agent", index=True)
    child_agent = Column(String(80), nullable=False, default="dataset_agent", server_default="dataset_agent", index=True)
    child_run_id = Column(String(120), nullable=True, index=True)
    dataset_id = Column(Integer, nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    trace_id = Column(String(120), nullable=False, index=True)
    checkpoint_ref = Column(String(200), nullable=True, index=True)
    artifact_ref = Column(String(200), nullable=True, index=True)
    handoff_status = Column(String(40), nullable=False, default="created", server_default="created", index=True)
    answer_summary = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    status_reason = Column(String(120), nullable=True)
    error_code = Column(String(80), nullable=True, index=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)

    run = relationship("BILeadAgentRun", back_populates="handoff")
```

- [ ] **Step 4: Export models**

Modify `datalogue-api/app/models/__init__.py`:

```python
from .bi_lead_agent import BIAgentHandoff, BILeadAgentConfirmation, BILeadAgentRun
```

Add to `__all__`:

```python
"BILeadAgentRun",
"BILeadAgentConfirmation",
"BIAgentHandoff",
```

- [ ] **Step 5: Add migration**

Create `datalogue-api/alembic/versions/r2s3t4u5v6w7_add_bi_lead_agent_handoff.py` with the same table and column names as the model. Use the existing `p1q2r3s4t5u6_add_agentscope_workbench_mirror.py` helper style:

```python
# ============================================================
# File Name   : r2s3t4u5v6w7_add_bi_lead_agent_handoff.py
# Description:
#   新增 BI LeadAgent K1 run、确认和 handoff 表。
#
# Responsibilities:
#   - 创建 BI LeadAgent 多阶段运行状态表。
#   - 创建用户确认快照表。
#   - 创建 BI LeadAgent 到 DatasetAgent 的任务交接记录表。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

"""add_bi_lead_agent_handoff

Revision ID: r2s3t4u5v6w7
Revises: p1q2r3s4t5u6
Create Date: 2026-07-01 18:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "r2s3t4u5v6w7"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json_default() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def upgrade() -> None:
    op.create_table(
        "bi_lead_agent_run",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
        sa.Column("status", sa.String(length=40), server_default="created", nullable=False, comment="run 当前状态。"),
        sa.Column("phase", sa.String(length=40), server_default="route_run", nullable=False, comment="F2 多阶段 run 当前阶段。"),
        sa.Column("question", sa.Text(), nullable=False, comment="用户原始问题。"),
        sa.Column("trace_id", sa.String(length=120), nullable=False, comment="链路追踪 ID。"),
        sa.Column("task_id", sa.String(length=120), nullable=True, comment="业务任务 ID。"),
        sa.Column("status_reason", sa.String(length=120), nullable=True, comment="状态原因。"),
        sa.Column("error_code", sa.String(length=80), nullable=True, comment="安全错误码。"),
        sa.Column("error_summary", sa.Text(), nullable=True, comment="安全错误摘要。"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bi_lead_agent_run_trace_id", "bi_lead_agent_run", ["trace_id"])
    op.create_index("ix_bi_lead_agent_run_status", "bi_lead_agent_run", ["status"])
    op.create_index("ix_bi_lead_agent_run_phase", "bi_lead_agent_run", ["phase"])

    op.create_table(
        "bi_lead_agent_confirmation",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
        sa.Column("run_id", sa.Integer(), nullable=False, comment="所属 BI LeadAgent run。"),
        sa.Column("dataset_id", sa.Integer(), nullable=False, comment="用户确认的数据集 ID。"),
        sa.Column("confirmed_question", sa.Text(), nullable=False, comment="用户确认后的问题。"),
        sa.Column("task_goal", sa.Text(), nullable=False, comment="交给 DatasetAgent 的业务目标。"),
        sa.Column("capability_snapshot_json", _json_type(), server_default=_json_default(), nullable=False, comment="路由级数据集能力快照。"),
        sa.Column("routing_rationale", sa.Text(), nullable=False, comment="LeadAgent 路由理由。"),
        sa.Column("risk_notice", sa.Text(), nullable=True, comment="确认时展示的风险提示。"),
        sa.Column("user_decision", sa.String(length=40), nullable=False, comment="用户确认决策。"),
        sa.Column("trace_id", sa.String(length=120), nullable=False, comment="链路追踪 ID。"),
        sa.Column("parent_run_id", sa.String(length=80), nullable=False, comment="父 run ID。"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["bi_lead_agent_run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_bi_lead_agent_confirmation_run_id"),
    )
    op.create_index("ix_bi_lead_agent_confirmation_dataset_id", "bi_lead_agent_confirmation", ["dataset_id"])
    op.create_index("ix_bi_lead_agent_confirmation_trace_id", "bi_lead_agent_confirmation", ["trace_id"])

    op.create_table(
        "bi_agent_handoff",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键。"),
        sa.Column("run_id", sa.Integer(), nullable=False, comment="所属 BI LeadAgent run。"),
        sa.Column("handoff_id", sa.String(length=120), nullable=False, comment="任务交接唯一 ID。"),
        sa.Column("parent_agent", sa.String(length=80), server_default="bi_lead_agent", nullable=False, comment="发起交接的智能体。"),
        sa.Column("child_agent", sa.String(length=80), server_default="dataset_agent", nullable=False, comment="接收任务的智能体。"),
        sa.Column("child_run_id", sa.String(length=120), nullable=True, comment="DatasetAgent 子运行 ID。"),
        sa.Column("dataset_id", sa.Integer(), nullable=False, comment="目标数据集 ID。"),
        sa.Column("task_id", sa.String(length=120), nullable=True, comment="业务任务 ID。"),
        sa.Column("trace_id", sa.String(length=120), nullable=False, comment="链路追踪 ID。"),
        sa.Column("checkpoint_ref", sa.String(length=200), nullable=True, comment="可恢复检查点引用。"),
        sa.Column("artifact_ref", sa.String(length=200), nullable=True, comment="查询产物引用。"),
        sa.Column("handoff_status", sa.String(length=40), server_default="created", nullable=False, comment="任务交接状态。"),
        sa.Column("answer_summary", sa.Text(), nullable=True, comment="DatasetAgent 安全答案摘要。"),
        sa.Column("row_count", sa.Integer(), nullable=True, comment="结果行数。"),
        sa.Column("column_count", sa.Integer(), nullable=True, comment="结果列数。"),
        sa.Column("status_reason", sa.String(length=120), nullable=True, comment="状态原因。"),
        sa.Column("error_code", sa.String(length=80), nullable=True, comment="安全错误码。"),
        sa.Column("error_summary", sa.Text(), nullable=True, comment="安全错误摘要。"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["bi_lead_agent_run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_bi_agent_handoff_run_id"),
        sa.UniqueConstraint("handoff_id", name="uq_bi_agent_handoff_handoff_id"),
    )
    op.create_index("ix_bi_agent_handoff_trace_id", "bi_agent_handoff", ["trace_id"])
    op.create_index("ix_bi_agent_handoff_status", "bi_agent_handoff", ["handoff_status"])
    op.create_index("ix_bi_agent_handoff_dataset_id", "bi_agent_handoff", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("bi_agent_handoff")
    op.drop_table("bi_lead_agent_confirmation")
    op.drop_table("bi_lead_agent_run")
```

- [ ] **Step 6: Run model tests**

Run:

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_models.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add datalogue-api/app/models/bi_lead_agent.py datalogue-api/app/models/__init__.py datalogue-api/alembic/versions/r2s3t4u5v6w7_add_bi_lead_agent_handoff.py datalogue-api/tests/test_bi_lead_agent_models.py
git commit -m "feat: add BI LeadAgent state models"
```

### Task 2: Pydantic 契约和 capability manifest

**Files:**

- Create: `datalogue-api/app/schemas/bi_lead_agent.py`
- Create: `datalogue-api/app/services/bi_lead_agent/__init__.py`
- Create: `datalogue-api/app/services/bi_lead_agent/capabilities.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_capabilities.py`

- [ ] **Step 1: Write failing capability tests**

Create `datalogue-api/tests/test_bi_lead_agent_capabilities.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_capabilities.py
# Description:
#   BI LeadAgent K1 能力面契约测试。
#
# Responsibilities:
#   - 验证 BI LeadAgent 只暴露三开一藏能力。
#   - 验证数据集能力摘要不泄露 DatasetAgent 内部上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from app.services.bi_lead_agent.capabilities import build_bi_lead_agent_capabilities, sanitize_dataset_capability


def test_bi_lead_agent_capability_manifest_exposes_three_enabled_one_disabled():
    manifest = build_bi_lead_agent_capabilities()
    enabled = {item.name for item in manifest if item.status == "enabled"}
    disabled = {item.name for item in manifest if item.status == "disabled"}

    assert enabled == {"list_dataset_capabilities", "request_dataset_confirmation", "query_dataset"}
    assert disabled == {"query_multiple_datasets"}
    assert "list_candidate_assets" not in enabled
    assert "compile_dsl_to_sql" not in enabled
    assert "execute_compiled_query" not in enabled
    assert "repair_dsl" not in enabled
    assert "create_query_artifact" not in enabled


def test_dataset_capability_summary_strips_dataset_internal_context():
    summary = sanitize_dataset_capability(
        {
            "dataset_id": 12,
            "name": "订单数据集",
            "domain": "销售",
            "supported_questions": ["订单金额趋势"],
            "key_metrics": ["订单金额"],
            "key_dimensions": ["月份"],
            "freshness": "T+1",
            "availability": "ready",
            "schema": {"orders": ["amount"]},
            "sql": "select * from orders",
            "dsl": {"metric": "amount"},
            "candidate_assets": [{"name": "订单金额"}],
            "field_mapping": {"amount": "orders.amount"},
            "blueprint_body": "内部蓝图正文",
        }
    )

    assert summary.model_dump() == {
        "dataset_id": 12,
        "name": "订单数据集",
        "domain": "销售",
        "supported_questions": ["订单金额趋势"],
        "key_metrics": ["订单金额"],
        "key_dimensions": ["月份"],
        "freshness": "T+1",
        "availability": "ready",
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_capabilities.py -q
```

Expected: FAIL with missing `app.services.bi_lead_agent`.

- [ ] **Step 3: Create schemas**

Create `datalogue-api/app/schemas/bi_lead_agent.py`:

```python
# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 API 和服务层 Pydantic 契约。
#
# Responsibilities:
#   - 定义 BI LeadAgent capability、run、confirmation 和 handoff DTO。
#   - 固化 query_dataset 的安全输入输出边界。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Literal

from pydantic import BaseModel, Field


BILeadAgentCapabilityStatus = Literal["enabled", "disabled"]
BILeadAgentRunPhase = Literal["route_run", "confirm_run", "handoff_run", "summarize_run"]
BILeadAgentRunStatus = Literal["created", "waiting_confirmation", "running", "completed", "blocked", "failed", "cancelled"]
BIHandoffStatus = Literal["created", "accepted", "running", "waiting_child", "completed", "blocked", "failed", "cancelled"]


class BILeadAgentCapability(BaseModel):
    name: str
    status: BILeadAgentCapabilityStatus
    disabled_reason: str | None = None
    replacement: str | None = None


class DatasetCapabilitySummary(BaseModel):
    dataset_id: int
    name: str
    domain: str | None = None
    supported_questions: list[str] = Field(default_factory=list)
    key_metrics: list[str] = Field(default_factory=list)
    key_dimensions: list[str] = Field(default_factory=list)
    freshness: str | None = None
    availability: str | None = None


class CreateBILeadAgentRunRequest(BaseModel):
    question: str
    trace_id: str | None = None
    task_id: str | None = None


class ConfirmBILeadAgentRunRequest(BaseModel):
    dataset_id: int
    confirmed_question: str
    task_goal: str
    capability_snapshot: DatasetCapabilitySummary
    routing_rationale: str
    risk_notice: str | None = None
    user_decision: Literal["approved", "rejected"]


class BILeadAgentHandoffRequest(BaseModel):
    dataset_id: int
    confirmed_question: str
    task_goal: str
    user_confirmation_id: int
    routing_rationale: str
    trace_id: str
    parent_run_id: str


class BILeadAgentHandoffResult(BaseModel):
    handoff_id: str
    parent_agent: Literal["bi_lead_agent"] = "bi_lead_agent"
    child_agent: Literal["dataset_agent"] = "dataset_agent"
    child_run_id: str | None = None
    dataset_id: int
    task_id: str | None = None
    trace_id: str
    handoff_status: BIHandoffStatus
    answer_summary: str | None = None
    artifact_ref: str | None = None
    checkpoint_ref: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    status_reason: str | None = None
    error_code: str | None = None
    error_summary: str | None = None


class BILeadAgentRunResponse(BaseModel):
    run_id: int
    status: BILeadAgentRunStatus
    phase: BILeadAgentRunPhase
    question: str
    trace_id: str
    task_id: str | None = None
    confirmation_id: int | None = None
    handoff: BILeadAgentHandoffResult | None = None
    status_reason: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
```

- [ ] **Step 4: Create capability service**

Create `datalogue-api/app/services/bi_lead_agent/__init__.py`:

```python
# ============================================================
# File Name   : __init__.py
# Description:
#   BI LeadAgent K1 服务包入口。
#
# Responsibilities:
#   - 聚合 BI LeadAgent run、confirmation 和 handoff 服务。
#   - 保持外部导入路径稳定，方便后续 AgentScope native handoff 替换内部实现。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================
```

Create `datalogue-api/app/services/bi_lead_agent/capabilities.py`:

```python
# ============================================================
# File Name   : capabilities.py
# Description:
#   BI LeadAgent K1 能力面和数据集能力摘要裁剪。
#
# Responsibilities:
#   - 生成 BI LeadAgent 三开一藏 capability manifest。
#   - 将数据集能力信息裁剪为路由级摘要，阻断 schema、SQL、DSL 和候选资产详情。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Any

from app.schemas.bi_lead_agent import BILeadAgentCapability, DatasetCapabilitySummary


def build_bi_lead_agent_capabilities() -> list[BILeadAgentCapability]:
    return [
        BILeadAgentCapability(name="list_dataset_capabilities", status="enabled"),
        BILeadAgentCapability(name="request_dataset_confirmation", status="enabled"),
        BILeadAgentCapability(name="query_dataset", status="enabled"),
        BILeadAgentCapability(
            name="query_multiple_datasets",
            status="disabled",
            disabled_reason="B_READY_AGENT_TO_AGENT_HANDOFF_RESERVED",
            replacement="query_dataset",
        ),
    ]


def sanitize_dataset_capability(raw: dict[str, Any]) -> DatasetCapabilitySummary:
    return DatasetCapabilitySummary(
        dataset_id=int(raw["dataset_id"]),
        name=str(raw.get("name") or ""),
        domain=raw.get("domain"),
        supported_questions=[str(item) for item in raw.get("supported_questions") or []],
        key_metrics=[str(item) for item in raw.get("key_metrics") or []],
        key_dimensions=[str(item) for item in raw.get("key_dimensions") or []],
        freshness=raw.get("freshness"),
        availability=raw.get("availability"),
    )
```

- [ ] **Step 5: Run capability tests**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_capabilities.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add datalogue-api/app/schemas/bi_lead_agent.py datalogue-api/app/services/bi_lead_agent/__init__.py datalogue-api/app/services/bi_lead_agent/capabilities.py datalogue-api/tests/test_bi_lead_agent_capabilities.py
git commit -m "feat: add BI LeadAgent capability contracts"
```

### Task 3: Run 和 confirmation 服务

**Files:**

- Create: `datalogue-api/app/services/bi_lead_agent/run_service.py`
- Create: `datalogue-api/app/services/bi_lead_agent/confirmation_service.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_services.py`

- [ ] **Step 1: Write failing service tests**

Create `datalogue-api/tests/test_bi_lead_agent_services.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_services.py
# Description:
#   BI LeadAgent K1 run、confirmation 和 handoff 服务测试。
#
# Responsibilities:
#   - 验证 run 创建、确认快照保存和未确认禁止 handoff。
#   - 验证最终回答汇总不新增 DatasetAgent 未返回的数值结论。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import pytest

from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest, DatasetCapabilitySummary
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.run_service import BILeadAgentRunService


def test_run_service_creates_route_run(db_session):
    service = BILeadAgentRunService(db_session)
    run = service.create_run(question="统计订单金额", trace_id="trace-run-001", task_id="task-run-001")

    assert run.status == "created"
    assert run.phase == "route_run"
    assert run.trace_id == "trace-run-001"


def test_confirmation_service_saves_h2_snapshot(db_session):
    run_service = BILeadAgentRunService(db_session)
    confirmation_service = BILeadAgentConfirmationService(db_session)
    run = run_service.create_run(question="统计订单金额", trace_id="trace-confirm-001", task_id="task-confirm-001")

    confirmation = confirmation_service.confirm(
        run_id=run.id,
        request=ConfirmBILeadAgentRunRequest(
            dataset_id=12,
            confirmed_question="统计订单金额",
            task_goal="执行单数据集问数",
            capability_snapshot=DatasetCapabilitySummary(
                dataset_id=12,
                name="订单数据集",
                domain="销售",
                supported_questions=["订单金额趋势"],
                key_metrics=["订单金额"],
                key_dimensions=["月份"],
                freshness="T+1",
                availability="ready",
            ),
            routing_rationale="订单金额问题应由订单数据集回答。",
            risk_notice="只读查询。",
            user_decision="approved",
        ),
    )

    assert confirmation.dataset_id == 12
    assert confirmation.user_decision == "approved"
    assert confirmation.capability_snapshot_json["name"] == "订单数据集"
    assert db_session.get(type(run), run.id).status == "running"
    assert db_session.get(type(run), run.id).phase == "confirm_run"


def test_confirmation_service_rejects_handoff_without_approval(db_session):
    run = BILeadAgentRunService(db_session).create_run(
        question="统计订单金额",
        trace_id="trace-confirm-002",
        task_id="task-confirm-002",
    )

    with pytest.raises(ValueError, match="USER_CONFIRMATION_REQUIRED"):
        BILeadAgentConfirmationService(db_session).require_approved_confirmation(run.id)
```

- [ ] **Step 2: Run service tests to verify failure**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_services.py -q
```

Expected: FAIL with missing `run_service`.

- [ ] **Step 3: Implement run service**

Create `datalogue-api/app/services/bi_lead_agent/run_service.py`:

```python
# ============================================================
# File Name   : run_service.py
# Description:
#   BI LeadAgent K1 多阶段 run 状态服务。
#
# Responsibilities:
#   - 创建 BI LeadAgent route_run。
#   - 推进 run phase/status 并记录 blocked/failed/completed 安全错误摘要。
#   - 组装 GET run API 响应。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.bi_lead_agent import BILeadAgentRun
from app.schemas.bi_lead_agent import BILeadAgentRunResponse, BILeadAgentHandoffResult


class BILeadAgentRunService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, *, question: str, trace_id: str | None = None, task_id: str | None = None) -> BILeadAgentRun:
        run = BILeadAgentRun(
            status="created",
            phase="route_run",
            question=question,
            trace_id=trace_id or f"bi-lead-trace-{uuid4().hex}",
            task_id=task_id or f"bi-lead-task-{uuid4().hex}",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_phase(self, run: BILeadAgentRun, *, phase: str, status: str, status_reason: str | None = None) -> BILeadAgentRun:
        run.phase = phase
        run.status = status
        run.status_reason = status_reason
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_failed(self, run: BILeadAgentRun, *, phase: str, error_code: str, error_summary: str) -> BILeadAgentRun:
        run.phase = phase
        run.status = "failed"
        run.status_reason = "failed"
        run.error_code = error_code
        run.error_summary = error_summary
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_response(self, run_id: int) -> BILeadAgentRunResponse:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        handoff_result = None
        if run.handoff is not None:
            handoff_result = BILeadAgentHandoffResult(
                handoff_id=run.handoff.handoff_id,
                child_run_id=run.handoff.child_run_id,
                dataset_id=run.handoff.dataset_id,
                task_id=run.handoff.task_id,
                trace_id=run.handoff.trace_id,
                handoff_status=run.handoff.handoff_status,
                answer_summary=run.handoff.answer_summary,
                artifact_ref=run.handoff.artifact_ref,
                checkpoint_ref=run.handoff.checkpoint_ref,
                row_count=run.handoff.row_count,
                column_count=run.handoff.column_count,
                status_reason=run.handoff.status_reason,
                error_code=run.handoff.error_code,
                error_summary=run.handoff.error_summary,
            )
        return BILeadAgentRunResponse(
            run_id=run.id,
            status=run.status,
            phase=run.phase,
            question=run.question,
            trace_id=run.trace_id,
            task_id=run.task_id,
            confirmation_id=run.confirmation.id if run.confirmation else None,
            handoff=handoff_result,
            status_reason=run.status_reason,
            error_code=run.error_code,
            error_summary=run.error_summary,
        )
```

- [ ] **Step 4: Implement confirmation service**

Create `datalogue-api/app/services/bi_lead_agent/confirmation_service.py`:

```python
# ============================================================
# File Name   : confirmation_service.py
# Description:
#   BI LeadAgent K1 用户确认快照服务。
#
# Responsibilities:
#   - 保存 H2 确认快照。
#   - 阻断未确认、拒绝确认或跨 run 确认发起 handoff。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.bi_lead_agent import BILeadAgentConfirmation, BILeadAgentRun
from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest


class BILeadAgentConfirmationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def confirm(self, *, run_id: int, request: ConfirmBILeadAgentRunRequest) -> BILeadAgentConfirmation:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        confirmation = BILeadAgentConfirmation(
            run_id=run.id,
            dataset_id=request.dataset_id,
            confirmed_question=request.confirmed_question,
            task_goal=request.task_goal,
            capability_snapshot_json=request.capability_snapshot.model_dump(),
            routing_rationale=request.routing_rationale,
            risk_notice=request.risk_notice,
            user_decision=request.user_decision,
            trace_id=run.trace_id,
            parent_run_id=str(run.id),
            confirmed_at=datetime.now(timezone.utc) if request.user_decision == "approved" else None,
        )
        self.db.add(confirmation)
        run.phase = "confirm_run"
        run.status = "running" if request.user_decision == "approved" else "blocked"
        run.status_reason = "confirmation_approved" if request.user_decision == "approved" else "confirmation_rejected"
        self.db.commit()
        self.db.refresh(confirmation)
        return confirmation

    def require_approved_confirmation(self, run_id: int) -> BILeadAgentConfirmation:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        if run.confirmation is None or run.confirmation.user_decision != "approved":
            raise ValueError("USER_CONFIRMATION_REQUIRED")
        return run.confirmation
```

- [ ] **Step 5: Run service tests**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_services.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add datalogue-api/app/services/bi_lead_agent/run_service.py datalogue-api/app/services/bi_lead_agent/confirmation_service.py datalogue-api/tests/test_bi_lead_agent_services.py
git commit -m "feat: add BI LeadAgent run services"
```

### Task 4: Host Handoff Adapter 使用 AgentScope 2.0 SDK

**Files:**

- Create: `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
- Create: `datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py`
- Create: `datalogue-api/app/services/bi_lead_agent/handoff_service.py`
- Modify: `datalogue-api/app/core/config.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py`
- Test: extend `datalogue-api/tests/test_bi_lead_agent_services.py`

- [ ] **Step 1: Write failing AgentScope SDK adapter test**

Create `datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_handoff_adapter.py
# Description:
#   BI LeadAgent Host Handoff Adapter 的 AgentScope 2.0 SDK 集成测试。
#
# Responsibilities:
#   - 验证 adapter 使用 AgentScope external tool event 链路，而不是 direct query 测试入口。
#   - 验证返回给 BI LeadAgent 的结果不包含 SQL/schema/raw rows/DSL。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

import json

import pytest
from agentscope.event import RequireExternalExecutionEvent
from agentscope.message import TextBlock, ToolCallBlock

from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest
from app.services.bi_lead_agent.handoff_adapter import DatalogueBIHandoffAdapter


class FakeDatasetAgent:
    def __init__(self) -> None:
        self.received_external_results = []

    async def reply_stream(self, msg):
        yield RequireExternalExecutionEvent(
            reply_id="reply-001",
            tool_calls=[
                ToolCallBlock(id="tool-001", name="get_dataset_status", input=json.dumps({})),
            ],
        )

    async def reply(self, event):
        self.received_external_results.append(event)
        return TextBlock(text="DatasetAgent completed")


class FakeBridge:
    def __init__(self) -> None:
        self.run_reply_stream_called = False
        self.run_direct_query_called = False

    def start_session(self, **kwargs):
        return {"session": kwargs}

    async def run_reply_stream(self, agent, *, msg, session):
        self.run_reply_stream_called = True
        await agent.reply_stream(msg).__anext__()
        return [
            {
                "status": "completed",
                "answer_summary": "订单金额汇总完成。",
                "artifact_ref": "artifact-001",
                "checkpoint_ref": "checkpoint-001",
                "row_count": 10,
                "column_count": 3,
                "sql": "select * from orders",
                "schema": {"orders": ["amount"]},
            }
        ]

    async def run_direct_query(self, **kwargs):
        self.run_direct_query_called = True
        return {"status": "completed"}


@pytest.mark.asyncio
async def test_handoff_adapter_uses_agentscope_reply_stream_and_sanitizes_result():
    bridge = FakeBridge()
    adapter = DatalogueBIHandoffAdapter(
        bridge=bridge,
        dataset_agent_factory=lambda session: FakeDatasetAgent(),
        fallback_mode="off",
    )

    result = await adapter.query_dataset(
        BILeadAgentHandoffRequest(
            dataset_id=12,
            confirmed_question="统计订单金额",
            task_goal="执行单数据集问数",
            user_confirmation_id=1,
            routing_rationale="订单金额问题应由订单数据集回答。",
            trace_id="trace-handoff-001",
            parent_run_id="1",
        ),
        task_id="task-handoff-001",
    )

    assert bridge.run_reply_stream_called is True
    assert bridge.run_direct_query_called is False
    assert result.handoff_status == "completed"
    assert result.answer_summary == "订单金额汇总完成。"
    assert result.artifact_ref == "artifact-001"
    dumped = result.model_dump()
    assert "sql" not in dumped
    assert "schema" not in dumped
    assert "raw_rows" not in dumped
    assert "dsl" not in dumped
```

- [ ] **Step 2: Run adapter test to verify failure**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_handoff_adapter.py -q
```

Expected: FAIL with missing `handoff_adapter`.

- [ ] **Step 3: Add fallback config**

Modify `datalogue-api/app/core/config.py` settings class:

```python
BI_LEAD_AGENT_DATASET_FALLBACK_MODE: str = "off"
```

If the settings class uses Pydantic field metadata, use:

```python
BI_LEAD_AGENT_DATASET_FALLBACK_MODE: str = Field(default="off")
```

Valid values in code: `"off"` and `"dev_only"`.

- [ ] **Step 4: Implement Host Handoff Adapter**

Create `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`:

```python
# ============================================================
# File Name   : handoff_adapter.py
# Description:
#   BI LeadAgent 到 DatasetAgent Runtime 的宿主侧任务交接适配器。
#
# Responsibilities:
#   - 使用 AgentScope 2.0 SDK reply_stream / external execution event 链路启动 DatasetAgent。
#   - 复用 DatasetAgent Runtime bridge 和 Datalogue 安全裁剪。
#   - 返回 D2 安全摘要和 handoff refs，不返回 SQL/schema/raw rows/DSL。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest, BILeadAgentHandoffResult
from app.services.agentscope_dataset_runtime import AgentScopeDatasetRuntimeBridge


FORBIDDEN_RESULT_KEYS = {
    "sql",
    "schema",
    "schema_context",
    "raw_rows",
    "dsl",
    "candidate_assets",
    "compiled_query_ref",
    "repair_patch",
    "blueprint_body",
}


class DatalogueBIHandoffAdapter:
    def __init__(
        self,
        *,
        bridge: AgentScopeDatasetRuntimeBridge,
        dataset_agent_factory: Callable[[Any], Any],
        fallback_mode: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.dataset_agent_factory = dataset_agent_factory
        self.fallback_mode = fallback_mode or get_settings().BI_LEAD_AGENT_DATASET_FALLBACK_MODE

    async def query_dataset(self, request: BILeadAgentHandoffRequest, *, task_id: str | None) -> BILeadAgentHandoffResult:
        handoff_id = f"handoff-{uuid4().hex}"
        child_run_id = f"dataset-run-{uuid4().hex}"
        session = self.bridge.start_session(
            dataset_id=request.dataset_id,
            question=request.confirmed_question,
            agent_name="bi_lead_agent",
            trace_id=request.trace_id,
        )
        agent = self.dataset_agent_factory(session)
        try:
            events = await self.bridge.run_reply_stream(
                agent,
                msg={
                    "task_goal": request.task_goal,
                    "confirmed_question": request.confirmed_question,
                    "routing_rationale": request.routing_rationale,
                    "trace_id": request.trace_id,
                    "child_run_id": child_run_id,
                },
                session=session,
            )
        except Exception as exc:
            return BILeadAgentHandoffResult(
                handoff_id=handoff_id,
                child_run_id=child_run_id,
                dataset_id=request.dataset_id,
                task_id=task_id,
                trace_id=request.trace_id,
                handoff_status="failed",
                status_reason="agentscope_dataset_agent_failed",
                error_code="AGENTSCOPE_DATASET_AGENT_FAILED",
                error_summary=str(exc),
            )
        payload = self._extract_safe_payload(events)
        return BILeadAgentHandoffResult(
            handoff_id=handoff_id,
            child_run_id=child_run_id,
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status=payload.get("handoff_status") or payload.get("status") or "completed",
            answer_summary=payload.get("answer_summary") or payload.get("summary"),
            artifact_ref=payload.get("artifact_ref"),
            checkpoint_ref=payload.get("checkpoint_ref"),
            row_count=payload.get("row_count"),
            column_count=payload.get("column_count"),
            status_reason=payload.get("status_reason"),
            error_code=payload.get("error_code") or payload.get("code"),
            error_summary=payload.get("error_summary"),
        )

    def _extract_safe_payload(self, events: list[Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for event in events:
            if isinstance(event, dict):
                payload.update(event)
        for key in list(payload.keys()):
            if key in FORBIDDEN_RESULT_KEYS:
                payload.pop(key)
        return payload
```

- [ ] **Step 5: Implement AgentScope DatasetAgent factory**

Create `datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py`:

```python
# ============================================================
# File Name   : dataset_agent_factory.py
# Description:
#   BI LeadAgent K1 使用的 AgentScope 2.0 DatasetAgent 构造器。
#
# Responsibilities:
#   - 使用 AgentScope 2.0 SDK Agent、OpenAIChatModel、OpenAICredential 和 Toolkit 创建 DatasetAgent。
#   - 将 session 级 DatasetAgent external tools 注册到 AgentScope Toolkit。
#   - 保证 DatasetAgent 只通过 Datalogue Host Adapter 回填的 external tool result 获取安全结果。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from typing import Any

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.agentscope_dataset_runtime import AgentScopeDatasetRuntimeSession, build_dataset_agentscope_tools
from app.services.llm_config import resolve_llm_config


DATASET_AGENT_SYSTEM_PROMPT = """
你是 Datalogue DatasetAgent。
你只能通过已注册的 AgentScope external tools 完成数据集查询。
你不能直接生成 SQL、schema、raw rows、字段映射或蓝图正文给上游。
你必须按工具状态机顺序调用工具，最终只输出安全摘要和 artifact/checkpoint refs。
""".strip()


class AgentScopeDatasetAgentFactory:
    def __init__(self, db: Session) -> None:
        self.db = db

    def __call__(self, session: AgentScopeDatasetRuntimeSession) -> Agent:
        settings = get_settings()
        llm_config = resolve_llm_config(settings, role="lead_agent", db=self.db)
        credential = OpenAICredential(
            name=llm_config.name,
            api_key=SecretStr(llm_config.api_key),
            base_url=llm_config.base_url,
        )
        model = OpenAIChatModel(
            credential=credential,
            model=llm_config.model,
            stream=True,
            client_kwargs={"timeout": llm_config.request_timeout_seconds},
        )
        tools = build_dataset_agentscope_tools(session=session, agent_name="bi_lead_agent")
        return Agent(
            name="dataset_agent",
            system_prompt=DATASET_AGENT_SYSTEM_PROMPT,
            model=model,
            toolkit=Toolkit(tools=tools),
        )
```

- [ ] **Step 6: Add handoff service test**

Append to `datalogue-api/tests/test_bi_lead_agent_services.py`:

```python
import pytest

from app.services.bi_lead_agent.handoff_service import BIHandoffService


class FakeAdapter:
    async def query_dataset(self, request, *, task_id):
        from app.schemas.bi_lead_agent import BILeadAgentHandoffResult

        return BILeadAgentHandoffResult(
            handoff_id="handoff-service-001",
            child_run_id="dataset-run-service-001",
            dataset_id=request.dataset_id,
            task_id=task_id,
            trace_id=request.trace_id,
            handoff_status="completed",
            answer_summary="订单金额汇总完成。",
            artifact_ref="artifact-service-001",
            checkpoint_ref="checkpoint-service-001",
            row_count=10,
            column_count=3,
        )


@pytest.mark.asyncio
async def test_handoff_service_requires_approved_confirmation_and_persists_d2_result(db_session):
    run_service = BILeadAgentRunService(db_session)
    confirmation_service = BILeadAgentConfirmationService(db_session)
    run = run_service.create_run(question="统计订单金额", trace_id="trace-service-001", task_id="task-service-001")
    confirmation_service.confirm(
        run_id=run.id,
        request=ConfirmBILeadAgentRunRequest(
            dataset_id=12,
            confirmed_question="统计订单金额",
            task_goal="执行单数据集问数",
            capability_snapshot=DatasetCapabilitySummary(dataset_id=12, name="订单数据集"),
            routing_rationale="订单金额问题应由订单数据集回答。",
            risk_notice="只读查询。",
            user_decision="approved",
        ),
    )

    handoff = await BIHandoffService(db_session, adapter=FakeAdapter()).query_dataset(run_id=run.id)

    assert handoff.handoff_status == "completed"
    assert handoff.artifact_ref == "artifact-service-001"
    assert db_session.get(type(run), run.id).phase == "summarize_run"
    assert db_session.get(type(run), run.id).status == "completed"
```

- [ ] **Step 7: Implement handoff service**

Create `datalogue-api/app/services/bi_lead_agent/handoff_service.py`:

```python
# ============================================================
# File Name   : handoff_service.py
# Description:
#   BI LeadAgent K1 handoff 服务。
#
# Responsibilities:
#   - 校验用户确认后创建 BI LeadAgent 到 DatasetAgent 的任务交接记录。
#   - 调用 Host Handoff Adapter 并持久化 D2 安全返回。
#   - 把 handoff 状态映射回 BI LeadAgent run 状态。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from sqlalchemy.orm import Session

from app.models.bi_lead_agent import BIAgentHandoff, BILeadAgentRun
from app.schemas.bi_lead_agent import BILeadAgentHandoffRequest
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.handoff_adapter import DatalogueBIHandoffAdapter


class BIHandoffService:
    def __init__(self, db: Session, *, adapter: DatalogueBIHandoffAdapter) -> None:
        self.db = db
        self.adapter = adapter

    async def query_dataset(self, *, run_id: int) -> BIAgentHandoff:
        run = self.db.get(BILeadAgentRun, run_id)
        if run is None:
            raise ValueError("BI_LEAD_AGENT_RUN_NOT_FOUND")
        confirmation = BILeadAgentConfirmationService(self.db).require_approved_confirmation(run_id)
        request = BILeadAgentHandoffRequest(
            dataset_id=confirmation.dataset_id,
            confirmed_question=confirmation.confirmed_question,
            task_goal=confirmation.task_goal,
            user_confirmation_id=confirmation.id,
            routing_rationale=confirmation.routing_rationale,
            trace_id=confirmation.trace_id,
            parent_run_id=str(run.id),
        )
        run.phase = "handoff_run"
        run.status = "running"
        self.db.commit()

        result = await self.adapter.query_dataset(request, task_id=run.task_id)
        handoff = BIAgentHandoff(
            run_id=run.id,
            handoff_id=result.handoff_id,
            parent_agent=result.parent_agent,
            child_agent=result.child_agent,
            child_run_id=result.child_run_id,
            dataset_id=result.dataset_id,
            task_id=result.task_id,
            trace_id=result.trace_id,
            checkpoint_ref=result.checkpoint_ref,
            artifact_ref=result.artifact_ref,
            handoff_status=result.handoff_status,
            answer_summary=result.answer_summary,
            row_count=result.row_count,
            column_count=result.column_count,
            status_reason=result.status_reason,
            error_code=result.error_code,
            error_summary=result.error_summary,
        )
        self.db.add(handoff)
        run.phase = "summarize_run"
        run.status = "completed" if result.handoff_status == "completed" else result.handoff_status
        run.status_reason = result.status_reason
        run.error_code = result.error_code
        run.error_summary = result.error_summary
        self.db.commit()
        self.db.refresh(handoff)
        return handoff
```

- [ ] **Step 8: Run adapter and service tests**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_handoff_adapter.py tests/test_bi_lead_agent_services.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add datalogue-api/app/core/config.py datalogue-api/app/services/bi_lead_agent/handoff_adapter.py datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py datalogue-api/app/services/bi_lead_agent/handoff_service.py datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py datalogue-api/tests/test_bi_lead_agent_services.py
git commit -m "feat: add AgentScope BI handoff adapter"
```

### Task 5: Run-centric API

**Files:**

- Create: `datalogue-api/app/api/bi_lead_agent.py`
- Modify: `datalogue-api/app/api/__init__.py`
- Test: `datalogue-api/tests/test_bi_lead_agent_api.py`

- [ ] **Step 1: Write failing API tests**

Create `datalogue-api/tests/test_bi_lead_agent_api.py`:

```python
# ============================================================
# File Name   : test_bi_lead_agent_api.py
# Description:
#   BI LeadAgent K1 run-centric API 测试。
#
# Responsibilities:
#   - 验证 M2 最小 API 可以创建 run、确认 run、读取 run。
#   - 验证未确认状态下不会返回 DatasetAgent 内部工具或敏感上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================


def test_bi_lead_agent_run_lifecycle_api(client):
    created = client.post(
        "/api/bi-lead-agent/runs",
        json={"question": "统计订单金额", "trace_id": "trace-api-001", "task_id": "task-api-001"},
    )
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "waiting_confirmation"
    assert run["phase"] == "confirm_run"
    assert "list_candidate_assets" not in str(run)
    assert "compile_dsl_to_sql" not in str(run)

    confirmed = client.post(
        f"/api/bi-lead-agent/runs/{run['run_id']}/confirm",
        json={
            "dataset_id": 12,
            "confirmed_question": "统计订单金额",
            "task_goal": "执行单数据集问数",
            "capability_snapshot": {"dataset_id": 12, "name": "订单数据集", "key_metrics": ["订单金额"]},
            "routing_rationale": "订单金额问题应由订单数据集回答。",
            "risk_notice": "只读查询。",
            "user_decision": "approved",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmation_id"] is not None

    fetched = client.get(f"/api/bi-lead-agent/runs/{run['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["trace_id"] == "trace-api-001"
```

- [ ] **Step 2: Run API test to verify failure**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py -q
```

Expected: FAIL with `404` for `/api/bi-lead-agent/runs`.

- [ ] **Step 3: Implement API router**

Create `datalogue-api/app/api/bi_lead_agent.py`:

```python
# ============================================================
# File Name   : bi_lead_agent.py
# Description:
#   BI LeadAgent K1 run-centric API。
#
# Responsibilities:
#   - 暴露创建 run、确认 run、发起 handoff 和查询 run 的最小后端接口。
#   - 保持 API 只返回安全摘要和 refs，不返回 DatasetAgent 内部上下文。
#
# Author      : yangkai
# Created On  : 2026-07-01
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.bi_lead_agent import ConfirmBILeadAgentRunRequest, CreateBILeadAgentRunRequest, BILeadAgentRunResponse
from app.services.bi_lead_agent.confirmation_service import BILeadAgentConfirmationService
from app.services.bi_lead_agent.run_service import BILeadAgentRunService

router = APIRouter()


@router.post("/runs", response_model=BILeadAgentRunResponse)
def create_run(request: CreateBILeadAgentRunRequest, db: Session = Depends(get_db)) -> BILeadAgentRunResponse:
    service = BILeadAgentRunService(db)
    run = service.create_run(question=request.question, trace_id=request.trace_id, task_id=request.task_id)
    service.mark_phase(run, phase="confirm_run", status="waiting_confirmation", status_reason="confirmation_required")
    return service.get_response(run.id)


@router.post("/runs/{run_id}/confirm", response_model=BILeadAgentRunResponse)
def confirm_run(run_id: int, request: ConfirmBILeadAgentRunRequest, db: Session = Depends(get_db)) -> BILeadAgentRunResponse:
    try:
        BILeadAgentConfirmationService(db).confirm(run_id=run_id, request=request)
        return BILeadAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=BILeadAgentRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)) -> BILeadAgentRunResponse:
    try:
        return BILeadAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

The `/handoff` endpoint is added in Task 6 after the production adapter factory is wired.

- [ ] **Step 4: Register router**

Modify `datalogue-api/app/api/__init__.py`:

```python
from app.api import artifacts, datasource, dataset, conversation, chat, llm, messages, internal_subagent, workbench, bi_lead_agent
```

Add:

```python
router.include_router(bi_lead_agent.router, prefix="/bi-lead-agent", tags=["BI LeadAgent"])
```

- [ ] **Step 5: Run API test**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add datalogue-api/app/api/bi_lead_agent.py datalogue-api/app/api/__init__.py datalogue-api/tests/test_bi_lead_agent_api.py
git commit -m "feat: add BI LeadAgent run API"
```

### Task 6: Wire production handoff endpoint and AgentScope 2.0 SDK factory

**Files:**

- Modify: `datalogue-api/app/api/bi_lead_agent.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`
- Modify: `datalogue-api/app/services/bi_lead_agent/dataset_agent_factory.py`
- Test: extend `datalogue-api/tests/test_bi_lead_agent_api.py`

- [ ] **Step 1: Add failing handoff API test with monkeypatched service**

Append to `datalogue-api/tests/test_bi_lead_agent_api.py`:

```python
def test_bi_lead_agent_handoff_endpoint_requires_confirmed_run(client, monkeypatch):
    created = client.post(
        "/api/bi-lead-agent/runs",
        json={"question": "统计订单金额", "trace_id": "trace-api-handoff-001", "task_id": "task-api-handoff-001"},
    ).json()

    response = client.post(f"/api/bi-lead-agent/runs/{created['run_id']}/handoff")
    assert response.status_code == 400
    assert "USER_CONFIRMATION_REQUIRED" in response.text
```

- [ ] **Step 2: Run handoff API test to verify failure**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py::test_bi_lead_agent_handoff_endpoint_requires_confirmed_run -q
```

Expected: FAIL with 404 because endpoint is not registered.

- [ ] **Step 3: Add production adapter factory**

Append to `datalogue-api/app/services/bi_lead_agent/handoff_adapter.py`:

```python
from app.services.bi_tools import build_bi_atomic_toolkit
from app.services.bi_lead_agent.dataset_agent_factory import AgentScopeDatasetAgentFactory


def build_bi_handoff_adapter(db: Any) -> DatalogueBIHandoffAdapter:
    toolkit = build_bi_atomic_toolkit(db=db)
    bridge = AgentScopeDatasetRuntimeBridge(toolkit=toolkit)
    return DatalogueBIHandoffAdapter(
        bridge=bridge,
        dataset_agent_factory=AgentScopeDatasetAgentFactory(db),
    )
```

The production factory must construct a real AgentScope 2.0 SDK `Agent`. The endpoint must call `bridge.run_reply_stream()` and must not call `run_direct_query()` in production code.

- [ ] **Step 4: Add handoff endpoint**

Modify `datalogue-api/app/api/bi_lead_agent.py`:

```python
from app.services.bi_lead_agent.handoff_adapter import build_bi_handoff_adapter
from app.services.bi_lead_agent.handoff_service import BIHandoffService
```

Add:

```python
@router.post("/runs/{run_id}/handoff", response_model=BILeadAgentRunResponse)
async def handoff_run(run_id: int, db: Session = Depends(get_db)) -> BILeadAgentRunResponse:
    try:
        adapter = build_bi_handoff_adapter(db)
        await BIHandoffService(db, adapter=adapter).query_dataset(run_id=run_id)
        return BILeadAgentRunService(db).get_response(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 5: Run handoff API tests**

```bash
cd datalogue-api
python3 -m pytest tests/test_bi_lead_agent_api.py -q
```

Expected: PASS for unconfirmed rejection. The confirmed production handoff path remains covered by service and adapter tests with fake AgentScope agents.

- [ ] **Step 6: Commit Task 6**

```bash
git add datalogue-api/app/api/bi_lead_agent.py datalogue-api/app/services/bi_lead_agent/handoff_adapter.py datalogue-api/tests/test_bi_lead_agent_api.py
git commit -m "feat: wire BI LeadAgent handoff API"
```

### Task 7: Safety regression and W2 test pack

**Files:**

- Modify: `datalogue-api/tests/test_bi_lead_agent_capabilities.py`
- Modify: `datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py`
- Modify: `datalogue-api/tests/test_bi_lead_agent_services.py`

- [ ] **Step 1: Add forbidden text scan helper**

Append to `datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py`:

```python
def assert_forbidden_dataset_context_absent(payload):
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    forbidden = [
        "select ",
        "schema",
        "raw_rows",
        "dsl",
        "compiled_query_ref",
        "repair_patch",
        "blueprint_body",
        "field_mapping",
        "candidate_assets",
    ]
    for item in forbidden:
        assert item not in text
```

- [ ] **Step 2: Add D2 result safety test**

Append:

```python
@pytest.mark.asyncio
async def test_handoff_adapter_d2_result_keeps_only_safe_summary_and_refs():
    bridge = FakeBridge()
    adapter = DatalogueBIHandoffAdapter(
        bridge=bridge,
        dataset_agent_factory=lambda: FakeDatasetAgent(),
        fallback_mode="off",
    )
    result = await adapter.query_dataset(
        BILeadAgentHandoffRequest(
            dataset_id=12,
            confirmed_question="统计订单金额",
            task_goal="执行单数据集问数",
            user_confirmation_id=1,
            routing_rationale="订单金额问题应由订单数据集回答。",
            trace_id="trace-safe-001",
            parent_run_id="1",
        ),
        task_id="task-safe-001",
    )

    payload = result.model_dump()
    assert payload["artifact_ref"] == "artifact-001"
    assert payload["row_count"] == 10
    assert_forbidden_dataset_context_absent(payload)
```

- [ ] **Step 3: Run W2 test pack**

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 7**

```bash
git add datalogue-api/tests/test_bi_lead_agent_handoff_adapter.py datalogue-api/tests/test_bi_lead_agent_capabilities.py datalogue-api/tests/test_bi_lead_agent_services.py
git commit -m "test: cover BI LeadAgent safety contracts"
```

### Task 8: Documentation and project memory

**Files:**

- Modify: `.codex/project-memory.md`
- Create: `docs/test-reports/2026-07-01-bi-lead-agent-k1.md`

- [ ] **Step 1: Create test report**

Create `docs/test-reports/2026-07-01-bi-lead-agent-k1.md`:

```markdown
# BI LeadAgent K1 Test Report

## Scope

- BI LeadAgent capability manifest
- H2 confirmation snapshot
- D2 query_dataset handoff result
- AgentScope 2.0 SDK external tool event adapter
- M2 run-centric API

## Commands

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

## Result

执行 Task 8 时，把终端中 pytest 的完整结论写在这里，例如 `6 passed in 1.23s` 或具体失败摘要。该报告不能只写“已验证”。

## Residual Risk

- Live LLM tool-calling remains manual and should run with `RUN_BI_LEAD_AGENT_LIVE=1` before K2.
- Full front-end confirmation card is out of K1 scope.
```

- [ ] **Step 2: Update project memory**

Append a dated completion record to `.codex/project-memory.md` using the existing chronological format. Include:

```markdown
### 2026-07-01 18:30 BI LeadAgent K1 后端契约与 AgentScope 2.0 handoff 计划/实现

- 涉及文件：`datalogue-api/app/models/bi_lead_agent.py`、`datalogue-api/app/schemas/bi_lead_agent.py`、`datalogue-api/app/services/bi_lead_agent/*`、`datalogue-api/app/api/bi_lead_agent.py`、`datalogue-api/tests/test_bi_lead_agent_*.py`、`docs/test-reports/2026-07-01-bi-lead-agent-k1.md`。
- 关键改动：BI LeadAgent 三开一藏能力面、H2 确认快照、D2 handoff 返回、E2 状态机、AgentScope 2.0 SDK external tool event adapter。
- 验证方式：执行本文 Final Verification 中的 pytest 命令，并在完成记录中写入实际结果。
- 残留风险：K2 前端确认卡片、F3 长生命周期会话 agent、J3 错误码细化仍为后续项。
```

- [ ] **Step 3: Run formatting and focused tests**

```bash
cd datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 8**

```bash
git add .codex/project-memory.md docs/test-reports/2026-07-01-bi-lead-agent-k1.md
git commit -m "docs: record BI LeadAgent K1 validation"
```

## 3. Final Verification

Run:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
python3 -m pytest \
  tests/test_bi_lead_agent_models.py \
  tests/test_bi_lead_agent_capabilities.py \
  tests/test_bi_lead_agent_services.py \
  tests/test_bi_lead_agent_handoff_adapter.py \
  tests/test_bi_lead_agent_api.py \
  tests/test_agentscope_dataset_runtime_bridge.py \
  tests/test_as_r0_security_matrix.py \
  -q
```

Expected: PASS.

Optional live AgentScope DatasetAgent check:

```bash
cd /Users/yangkai/code_place/study/python/Datalogue/datalogue-api
RUN_BI_LEAD_AGENT_LIVE=1 python3 -m pytest tests/test_bi_lead_agent_handoff_adapter.py -q -s
```

Expected: PASS or SKIP with explicit missing live credentials/config reason.

## 4. Self-Review

Spec coverage:

- A 三开一藏：Task 2。
- A1 数据集能力摘要：Task 2。
- B1/H2 用户确认：Task 3。
- C2/D2 `query_dataset`：Task 4。
- E2 handoff 状态机：Task 1、Task 4。
- F2 多阶段 run：Task 1、Task 3、Task 5。
- G1 Datalogue DB 真相源：Task 1。
- I2 最终回答安全边界：Task 3、Task 7。
- J2 blocked/failed 最小错误字段：Task 1、Task 4。
- K1/L2/M2 最小 API：Task 5、Task 6。
- N1/O1/P2 数据模型：Task 1。
- Q2 服务拆分：Task 3、Task 4。
- R2/S2/T2/U1/V1 AgentScope 2.0 SDK handoff：Task 4、Task 6、Task 7。
- W2 测试范围：Task 7、Final Verification。

Consistency checks:

- 所有 Python 新文件包含中文职责注释头。
- 所有 user-visible API 都走 `/api/bi-lead-agent/runs` 命名空间。
- 生产 handoff 不调用 `run_direct_query()`。
- Dataset 原子工具只在 `agentscope_dataset_runtime.py` 和 DatasetAgent Runtime 内部出现。
- `query_multiple_datasets` 只以 disabled capability 出现。

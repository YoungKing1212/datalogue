# ============================================================
# File Name   : test_architecture_docs_p0_closure.py
# Description:
#   验证 P0 架构收口文档没有回退到旧主链口径。
#
# Responsibilities:
#   - 扫描当前权威文档和后端协作规则，确保唯一主链、Leader 控制面与 repair 一等链路持续可见。
#   - 防止 L4/L5 等历史分层重新成为当前主叙事，避免后续 Agent 误按旧架构实现。
#
# Author      : KenYang
# Created On  : 2026-07-07
# ============================================================

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [
    Path("docs/上下文入口.md"),
    Path("docs/architecture/系统架构.md"),
    Path("docs/architecture/执行链路.md"),
    Path("docs/architecture/AgentScope集成.md"),
    Path("docs/architecture/OpenViking-Service交接记忆.md"),
    Path("datalogue-api/AGENTS.md"),
]


def _read(relative_path: Path) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _combined_docs() -> str:
    return "\n".join(_read(path) for path in DOC_PATHS)


def test_p0_docs_define_unique_agent_team_main_chain() -> None:
    docs = _combined_docs()

    assert "POST /api/agent-team/tasks/stream" in docs
    assert "AgentScope Agent Team" in docs
    assert "BI Worker Tools" in docs or "BI Worker Agent" in docs
    assert "唯一产品主链" in docs or "当前唯一产品主链" in docs
    assert "旧 LangGraph" in docs
    assert "兼容" in docs or "历史迁移层" in docs


def test_p0_docs_keep_leader_as_non_bypassable_control_plane() -> None:
    docs = _combined_docs()

    assert "Leader Agent 是控制面" in docs
    assert "BI Worker Agent 是执行/诊断面" in docs
    assert "不得绕过 Leader" in docs or "不能绕过 Leader" in docs
    assert "direct-query" in docs
    assert "不能作为产品主入口" in docs or "不作为产品主入口" in docs


def test_p0_docs_promote_repair_to_first_class_flow() -> None:
    docs = _combined_docs()

    for stage in [
        "Failure Classifier",
        "Private Diagnosis",
        "Repair Planner",
        "User Confirmation",
        "Retry Executor",
        "Artifact Writer",
    ]:
        assert stage in docs

    assert "RepairRequest" in docs
    assert "RepairPlanCard" in docs or "checkpoint_ref" in docs
    assert "runtime/tool 私有诊断层" in docs


def test_p0_current_docs_do_not_use_legacy_l_layers_as_main_narrative() -> None:
    docs = _combined_docs()

    legacy_markers = ["L4", "L5", "L0-L4"]
    for marker in legacy_markers:
        assert marker not in docs, f"{marker} should not be used in current P0 architecture narrative"


def test_backend_agents_rule_separates_llm_boundary_from_private_diagnosis() -> None:
    agents = _read(Path("datalogue-api/AGENTS.md"))

    assert "BI Worker Agent/LLM" in agents
    assert "不得自行生成/执行 SQL" in agents
    assert "直接读取 raw rows" in agents
    assert "Datalogue runtime/tool 私有诊断层可以持有 SQL、schema、raw rows、原始数据库报错" in agents
    assert "不得进入 LLM prompt、用户可见 SSE、artifact 摘要、OpenViking 普通上下文" in agents


def test_project_memory_records_p0_architecture_closure() -> None:
    memory = _read(Path(".codex/project-memory.md"))

    assert "P0 架构收口" in memory
    assert "唯一产品主链" in memory
    assert "Leader 控制面" in memory
    assert "repair 一等可信闭环" in memory

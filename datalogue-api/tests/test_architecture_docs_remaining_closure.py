# ============================================================
# File Name   : test_architecture_docs_remaining_closure.py
# Description:
#   验证 P0 后剩余架构审计问题已经形成仓库内治理边界。
#
# Responsibilities:
#   - 扫描权威文档，防止 QueryPlan 迁移债、事件三层分流、assistant-ui runtime 守护、运行时健康检查和扩展 Worker 暂缓标准回退。
#   - 约束本轮只做架构治理收口，不把 P1/P2 债务伪装成已完成 runtime 重构。
#
# Author      : KenYang
# Created On  : 2026-07-07
# ============================================================

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [
    Path("docs/architecture/系统架构.md"),
    Path("docs/architecture/执行链路.md"),
    Path("docs/architecture/AgentScope集成.md"),
    Path("docs/api/API概览.md"),
    Path("docs/operations/运行时健康检查.md"),
    Path("docs/README.md"),
]


def _read(relative_path: Path) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _combined_docs() -> str:
    return "\n".join(_read(path) for path in DOC_PATHS)


def test_queryplan_to_legacy_dsl_is_marked_as_migration_debt() -> None:
    docs = _combined_docs()

    assert "QueryPlan 是 BI Worker Agent 与 Datalogue Tools 之间的当前 Worker 契约" in docs
    assert "legacy DSL" in docs
    assert "执行器兼容层" in docs
    assert "迁移债务" in docs
    assert "ControlledQuerySpec" in docs
    assert "未来核心路径" in docs


def test_event_complexity_is_split_into_three_lanes_and_legacy_payload_is_frozen() -> None:
    docs = _combined_docs()

    for lane in ["用户可见事件", "Workbench 事件", "Debug 事件"]:
        assert lane in docs
    assert "legacy_payload" in docs
    assert "不再扩字段" in docs or "冻结保留" in docs
    assert "SQL、schema、raw rows、原始报错" in docs
    assert "不进入用户可见 SSE" in docs


def test_assistant_ui_runtime_rewrite_is_explicitly_paused() -> None:
    docs = _combined_docs()

    assert "assistant-ui" in docs
    assert "稳定结果卡" in docs
    assert "reasoning summary" in docs
    assert "ThreadList" in docs
    assert "禁止做 headless primitives 级大重构" in docs
    assert "不重写 assistant-ui runtime" in docs


def test_runtime_health_check_covers_required_operational_dependencies() -> None:
    docs = _combined_docs()

    for item in [
        "AgentScope Service",
        "Redis",
        "Credential",
        "Leader Agent",
        "Session stream",
        "BI Tool",
        "Artifact API",
        "Frontend version",
    ]:
        assert item in docs
    assert "docs/operations/运行时健康检查.md" in docs
    assert "/api/agentscope-control/status" in docs


def test_report_python_audit_workers_are_paused_until_bi_main_chain_is_stable() -> None:
    docs = _combined_docs()

    assert "Report / Python / Audit Worker" in docs
    assert "暂停" in docs
    for criterion in [
        "BI 查询一轮成功率稳定",
        "失败能进入 repair",
        "artifact 必定可查看",
        "最终回答不泄露内部计划",
        "Workbench 能回放 checkpoint",
        "日志能区分 Leader / Worker / Tool / DB",
    ]:
        assert criterion in docs

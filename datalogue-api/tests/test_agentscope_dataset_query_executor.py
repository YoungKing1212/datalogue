# ============================================================
# File Name   : test_agentscope_dataset_query_executor.py
# Description:
#   AgentScope Service Dataset 查询执行器测试。
#
# Responsibilities:
#   - 验证 BI worker 自有 DB session 返回 artifact_ref 前已提交查询产物。
#   - 防止 SSE 已展示结果卡但详情接口查不到 artifact 的事务回归。
#
# Author      : yangkai
# Created On  : 2026-07-05
# ============================================================

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.models.conversation import QueryArtifact
from app.domains.query_execution.artifact_store import ArtifactStore


@pytest.mark.asyncio
async def test_dataset_query_executor_commits_artifact_when_it_owns_session(
    monkeypatch,
    tmp_path,
):
    from app.domains.bi.worker import dataset_query as executor

    engine = create_engine(
        f"sqlite:///{tmp_path / 'artifact_commit.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(executor, "SessionLocal", TestSessionLocal)

    async def fake_execute_dataset_query_with_db(
        *,
        db,
        dataset_id: int,
        confirmed_question: str,
        trace_id: str | None,
    ):
        assert confirmed_question == "查询杨凯2025年工作日志"
        artifact_ref = ArtifactStore(
            db,
            ttl_seconds=60,
            cleanup_interval_seconds=0,
        ).put_json(
            kind="query_result",
            payload={"columns": ["count"], "rows": [{"count": 1}]},
            dataset_id=dataset_id,
            trace_id=trace_id,
        )
        return executor.AgentTeamDatasetQueryResult(
            answer_summary=f"查询已完成，结果已生成 artifact_ref={artifact_ref}，共 1 行、1 列。",
            artifact_ref=artifact_ref,
            checkpoint_ref=None,
            row_count=1,
            column_count=1,
        )

    monkeypatch.setattr(
        executor,
        "_execute_dataset_query_with_db",
        fake_execute_dataset_query_with_db,
    )

    result = await executor.execute_dataset_query_for_agent_team_direct_fallback(
        db=None,
        dataset_id=10,
        confirmed_question="查询杨凯2025年工作日志",
        trace_id="trace-artifact-commit",
    )

    with TestSessionLocal() as verify_db:
        artifact = (
            verify_db.query(QueryArtifact)
            .filter(QueryArtifact.artifact_id == result.artifact_ref)
            .one_or_none()
        )

    assert artifact is not None
    assert artifact.dataset_id == 10
    assert artifact.trace_id == "trace-artifact-commit"

# ============================================================
# File Name   : test_report_worker_execution_state.py
# Description:
#   Report Worker 强制阶段状态机测试。
#
# Responsibilities:
#   - 验证必需、执行、成功和失败重试状态转换。
#   - 验证重复事件幂等以及非法倒退被拒绝。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

import pytest


def test_report_execution_state_requires_structured_success_evidence():
    from app.domains.agent_team.report_execution import (
        ReportExecutionState,
        ReportExecutionStatus,
    )

    state = ReportExecutionState()
    assert state.can_complete is True

    state.mark_required("artifact:query-1")
    assert state.status is ReportExecutionStatus.PENDING
    assert state.can_complete is False

    state.mark_running(worker_agent_id="report-1", worker_session_id="session-1")
    state.mark_succeeded(
        source_artifact_ref="artifact:query-1",
        report_ref="artifact:report:result-1",
        worker_agent_id="report-1",
        worker_session_id="session-1",
    )

    assert state.status is ReportExecutionStatus.SUCCEEDED
    assert state.attempt == 1
    assert state.can_complete is True


def test_report_execution_state_retries_failed_attempt_and_limits_corrections():
    from app.domains.agent_team.report_execution import ReportExecutionState

    state = ReportExecutionState()
    state.mark_required("artifact:query-1")
    state.mark_running()
    state.mark_failed("REPORT_FORMAT_INVALID")
    state.mark_running(worker_agent_id="report-2", worker_session_id="session-2")

    assert state.attempt == 2
    assert state.increment_correction() is True
    assert state.increment_correction() is True
    assert state.increment_correction() is False


def test_report_execution_state_rejects_source_switch_and_illegal_completion():
    from app.domains.agent_team.report_execution import (
        InvalidReportExecutionTransition,
        ReportExecutionState,
    )

    state = ReportExecutionState()
    state.mark_required("artifact:query-1")

    with pytest.raises(InvalidReportExecutionTransition):
        state.mark_required("artifact:query-2")

    with pytest.raises(InvalidReportExecutionTransition):
        state.mark_succeeded(
            source_artifact_ref="artifact:query-1",
            report_ref="artifact:report:result-1",
            worker_agent_id="report-1",
            worker_session_id="session-1",
        )


def test_report_execution_state_duplicate_events_are_idempotent():
    from app.domains.agent_team.report_execution import ReportExecutionState

    state = ReportExecutionState()
    state.mark_required("artifact:query-1")
    state.mark_required("artifact:query-1")
    state.mark_running(worker_agent_id="report-1", worker_session_id="session-1")
    state.mark_succeeded(
        source_artifact_ref="artifact:query-1",
        report_ref="artifact:report:result-1",
        worker_agent_id="report-1",
        worker_session_id="session-1",
    )
    state.mark_succeeded(
        source_artifact_ref="artifact:query-1",
        report_ref="artifact:report:result-1",
        worker_agent_id="report-1",
        worker_session_id="session-1",
    )

    assert state.attempt == 1


def test_report_execution_state_observes_query_and_report_payloads():
    from app.domains.agent_team.report_execution import ReportExecutionState

    state = ReportExecutionState()
    state.observe_payload(
        {
            "datalogue_event_type": "dataset_query_result",
            "status": "completed",
            "artifact_ref": "artifact:query-1",
        },
        event_type="artifact.created",
    )
    state.observe_payload(
        {
            "datalogue_event_type": "report_worker_result",
            "status": "completed",
            "source_artifact_ref": "artifact:query-1",
            "report_ref": "artifact:report:result-1",
            "report_worker_agent_id": "report-1",
            "report_worker_session_id": "session-1",
            "report_attempts": 2,
        },
        event_type="report_worker_result",
    )

    assert state.can_complete is True
    assert state.attempt == 2


def test_report_execution_state_rejects_incomplete_report_payload():
    from app.domains.agent_team.report_execution import (
        ReportExecutionState,
        ReportWorkerRequiredNotCompletedError,
    )

    state = ReportExecutionState()
    state.mark_required("artifact:query-1")

    with pytest.raises(
        ReportWorkerRequiredNotCompletedError,
        match="REPORT_WORKER_REQUIRED_NOT_COMPLETED",
    ):
        state.observe_payload(
            {
                "datalogue_event_type": "report_worker_result",
                "status": "completed",
                "source_artifact_ref": "artifact:query-1",
            },
            event_type="report_worker_result",
        )

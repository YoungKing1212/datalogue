# ============================================================
# File Name   : report_execution.py
# Description:
#   Report Worker 强制阶段的运行态状态机。
#
# Responsibilities:
#   - 记录查询产物进入报告阶段后的必要状态与执行凭证。
#   - 拒绝非法状态倒退，供 Runner 与 Runtime 完成闸门复用。
#
# Author      : yangkai
# Created On  : 2026-07-17
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReportExecutionStatus(StrEnum):
    """Report Worker 强制阶段状态。"""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvalidReportExecutionTransition(ValueError):
    """报告阶段发生非法状态转换。"""


class ReportWorkerRequiredNotCompletedError(RuntimeError):
    """必需的 Report Worker 没有提交完整完成凭证。"""

    code = "REPORT_WORKER_REQUIRED_NOT_COMPLETED"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(slots=True)
class ReportExecutionState:
    """单次任务运行中的 Report Worker 完成凭证。"""

    required: bool = False
    status: ReportExecutionStatus = ReportExecutionStatus.NOT_REQUIRED
    source_artifact_ref: str | None = None
    report_ref: str | None = None
    worker_agent_id: str | None = None
    worker_session_id: str | None = None
    attempt: int = 0
    correction_count: int = 0
    error_code: str | None = None

    def mark_required(self, source_artifact_ref: str) -> None:
        """查询产物生成后进入必需报告阶段；同一产物的重复事件保持幂等。"""

        source_ref = str(source_artifact_ref or "").strip()
        if not source_ref.startswith("artifact:"):
            raise ValueError("source_artifact_ref must be a valid artifact reference")
        if self.required:
            if self.source_artifact_ref != source_ref:
                raise InvalidReportExecutionTransition(
                    "report stage cannot switch to another source artifact"
                )
            return
        if self.status is not ReportExecutionStatus.NOT_REQUIRED:
            raise InvalidReportExecutionTransition(
                f"cannot require report from status {self.status.value}"
            )
        self.required = True
        self.status = ReportExecutionStatus.PENDING
        self.source_artifact_ref = source_ref

    def mark_running(
        self,
        *,
        worker_agent_id: str | None = None,
        worker_session_id: str | None = None,
    ) -> None:
        """记录一次 Report Worker 执行；失败后的重试允许重新进入 running。"""

        if not self.required or self.status not in {
            ReportExecutionStatus.PENDING,
            ReportExecutionStatus.FAILED,
        }:
            raise InvalidReportExecutionTransition(
                f"cannot start report from status {self.status.value}"
            )
        self.status = ReportExecutionStatus.RUNNING
        self.attempt += 1
        self.worker_agent_id = _optional_text(worker_agent_id)
        self.worker_session_id = _optional_text(worker_session_id)
        self.error_code = None

    def mark_succeeded(
        self,
        *,
        source_artifact_ref: str,
        report_ref: str,
        worker_agent_id: str,
        worker_session_id: str,
    ) -> None:
        """写入结构化提交工具返回的报告完成凭证。"""

        source_ref = str(source_artifact_ref or "").strip()
        output_ref = str(report_ref or "").strip()
        agent_id = str(worker_agent_id or "").strip()
        session_id = str(worker_session_id or "").strip()
        if self.status is ReportExecutionStatus.SUCCEEDED:
            if self.report_ref != output_ref or self.source_artifact_ref != source_ref:
                raise InvalidReportExecutionTransition("completed report evidence cannot change")
            return
        if not self.required or self.status is not ReportExecutionStatus.RUNNING:
            raise InvalidReportExecutionTransition(
                f"cannot complete report from status {self.status.value}"
            )
        if source_ref != self.source_artifact_ref:
            raise InvalidReportExecutionTransition("report source artifact does not match")
        if not output_ref.startswith("artifact:report:") or not agent_id or not session_id:
            raise ValueError("report completion evidence is incomplete")
        self.status = ReportExecutionStatus.SUCCEEDED
        self.report_ref = output_ref
        self.worker_agent_id = agent_id
        self.worker_session_id = session_id
        self.error_code = None

    def mark_failed(self, error_code: str) -> None:
        """记录当前报告尝试失败，保留源查询 Artifact 以支持安全重试。"""

        if not self.required or self.status not in {
            ReportExecutionStatus.PENDING,
            ReportExecutionStatus.RUNNING,
        }:
            raise InvalidReportExecutionTransition(
                f"cannot fail report from status {self.status.value}"
            )
        self.status = ReportExecutionStatus.FAILED
        self.error_code = str(error_code or "REPORT_WORKER_REQUIRED_NOT_COMPLETED").strip()

    def increment_correction(self, *, max_corrections: int = 2) -> bool:
        """占用一次 Leader 纠偏额度；达到上限后返回 False。"""

        if self.correction_count >= max(0, int(max_corrections)):
            return False
        self.correction_count += 1
        return True

    def observe_payload(self, payload: object, *, event_type: str) -> None:
        """吸收 Runner 收到的结构化业务事件，并更新报告阶段完成凭证。"""

        body = payload if isinstance(payload, dict) else {}
        payload_type = str(body.get("datalogue_event_type") or "")
        source_ref = str(
            body.get("source_artifact_ref") or body.get("artifact_ref") or ""
        ).strip()
        is_query_artifact = event_type == "artifact.created" or (
            payload_type == "dataset_query_result" and source_ref.startswith("artifact:")
        )
        if is_query_artifact:
            self.mark_required(source_ref)
            return

        if event_type != "report_worker_result" and payload_type != "report_worker_result":
            return
        if body.get("status") != "completed":
            if self.required and self.status in {
                ReportExecutionStatus.PENDING,
                ReportExecutionStatus.RUNNING,
            }:
                self.mark_failed(self._completion_error_code(body))
            raise ReportWorkerRequiredNotCompletedError()

        report_ref = str(body.get("report_ref") or "").strip()
        worker_agent_id = str(body.get("report_worker_agent_id") or "").strip()
        worker_session_id = str(body.get("report_worker_session_id") or "").strip()
        if not (
            source_ref.startswith("artifact:")
            and report_ref.startswith("artifact:report:")
            and worker_agent_id
            and worker_session_id
        ):
            raise ReportWorkerRequiredNotCompletedError()
        if not self.required:
            self.mark_required(source_ref)
        if self.status is ReportExecutionStatus.PENDING:
            self.mark_running(
                worker_agent_id=worker_agent_id,
                worker_session_id=worker_session_id,
            )
        attempts = _positive_int(body.get("report_attempts"))
        if attempts is not None:
            self.attempt = max(self.attempt, attempts)
        self.mark_succeeded(
            source_artifact_ref=source_ref,
            report_ref=report_ref,
            worker_agent_id=worker_agent_id,
            worker_session_id=worker_session_id,
        )

    @property
    def can_complete(self) -> bool:
        """任务是否满足最终完成闸门。"""

        if not self.required:
            return True
        return bool(
            self.status is ReportExecutionStatus.SUCCEEDED
            and self.source_artifact_ref
            and self.report_ref
            and self.worker_agent_id
            and self.worker_session_id
        )

    @staticmethod
    def _completion_error_code(payload: dict[str, object]) -> str:
        value = str(payload.get("code") or "").strip()
        return value or ReportWorkerRequiredNotCompletedError.code


def _optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


__all__ = [
    "InvalidReportExecutionTransition",
    "ReportExecutionState",
    "ReportExecutionStatus",
    "ReportWorkerRequiredNotCompletedError",
]

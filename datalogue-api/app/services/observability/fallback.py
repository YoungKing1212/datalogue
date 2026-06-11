# ============================================================
# File Name   : fallback.py
# Description:
#   Langfuse 不可用时的降级对象。
#
# Responsibilities:
#   - 提供 no-op trace/span/generation 句柄。
#   - 确保观测链路异常不会打断问数主流程。
#
# Author      : yangkai
# Created On  : 2026-06-11
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


class FallbackTraceHandle:
    """空对象句柄，兼容真实 trace/span 的常用方法。"""

    id: str | None = None

    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@dataclass
class LangfuseHealthCheck:
    """轻量熔断状态，避免持续失败时反复打外部服务。"""

    threshold: int = 10
    cooldown_seconds: int = 300
    failures: int = 0
    circuit_open_until: datetime | None = None

    def allow_request(self) -> bool:
        if self.circuit_open_until is None:
            return True
        if datetime.utcnow() >= self.circuit_open_until:
            self.circuit_open_until = None
            self.failures = 0
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.circuit_open_until = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.circuit_open_until = datetime.utcnow() + timedelta(seconds=self.cooldown_seconds)

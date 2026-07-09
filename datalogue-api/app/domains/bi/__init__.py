# ============================================================
# File Name   : __init__.py
# Description:
#   BI 业务域门面包，聚合 BI Agent / BI Worker 相关服务的兼容导出。
#
# Responsibilities:
#   - 指向 `app.agents.bi_agent` 与 `app.agentscope_service` 中的既有 BI 实现
#   - 兼容迁移中，不承载新业务逻辑
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""BI 业务域门面包。

本包仅通过子模块 re-export BI Agent 与 BI Worker 侧的既有能力，
不承载新业务逻辑；实际实现请继续在原模块中维护。
"""

__all__: list[str] = []

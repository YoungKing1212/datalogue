# ============================================================
# File Name   : __init__.py
# Description:
#   Datalogue BI 业务域根包。
#
# Responsibilities:
#   - 作为 BI Agent、BI Worker、Skill、Toolkit 与 QueryPlan 契约的领域边界。
#   - 不承载 AgentScope Service 嵌入、Workbench task 真相源或数据源适配实现。
#
# Author      : KenYang
# Created On  : 2026-07-09
# ============================================================

"""Datalogue BI 业务域根包。

子包按能力分层：agent 放 BI 应用服务，skill 放 Dataset 查询 Skill，
toolkit 放受控原子工具，worker 放 BI Worker QueryPlan 契约、运行时与上下文。
"""

__all__: list[str] = []

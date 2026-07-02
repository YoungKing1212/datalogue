# ============================================================
# File Name   : soul_contract_sync.py
# Description:
#   BI_SOUL 内部契约同步与外部入口策略渲染。
#
# Responsibilities:
#   - 读取 Datalogue BI_SOUL 内部 source of truth。
#   - 抽取并规范化外部入口同步块，校验 Hermes Skill 是否一致。
#   - 为 Agentic Shell / Hermes 外部入口提供统一边界文本。
#
# Author      : yangkai
# Created On  : 2026-06-26
# ============================================================

from __future__ import annotations

import re
from pathlib import Path


SYNC_BEGIN = "<!-- BEGIN BI_SOUL_SYNC -->"
SYNC_END = "<!-- END BI_SOUL_SYNC -->"

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent
INTERNAL_BI_SOUL_PATH = API_ROOT / "app" / "contracts" / "BI_SOUL.md"
HERMES_SKILL_SOUL_PATH = REPO_ROOT / "hermes-skills" / "datalogue" / "SOUL.md"


class SoulContractSyncError(AssertionError):
    """BI_SOUL 契约同步失败，属于发布前必须处理的边界漂移。"""


def load_internal_bi_soul(path: Path | None = None) -> str:
    """读取内部 source of truth；调用方可注入路径用于后续脚本化校验。"""

    target = path or INTERNAL_BI_SOUL_PATH
    return target.read_text(encoding="utf-8")


def load_hermes_skill_soul(path: Path | None = None) -> str:
    """读取 Hermes Skill SOUL，用于校验外部入口边界是否同步。"""

    target = path or HERMES_SKILL_SOUL_PATH
    return target.read_text(encoding="utf-8")


def extract_sync_block(content: str) -> str:
    """抽取机器同步块；缺失 marker 时直接失败，避免测试误比对全文噪声。"""

    pattern = re.compile(
        rf"{re.escape(SYNC_BEGIN)}(?P<body>.*?){re.escape(SYNC_END)}",
        re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        raise SoulContractSyncError("BI_SOUL sync block missing")
    return match.group("body")


def normalize_contract(content: str) -> str:
    """规范化同步块，去掉空行和尾随空格，保留条目顺序作为契约语义。"""

    block = extract_sync_block(content)
    lines = [line.strip() for line in block.splitlines()]
    return "\n".join(line for line in lines if line)


def assert_hermes_soul_synced(
    *,
    internal_content: str | None = None,
    hermes_content: str | None = None,
) -> None:
    """发布前同步校验：Hermes 对外边界必须等于内部 BI_SOUL 同步块。"""

    internal = internal_content if internal_content is not None else load_internal_bi_soul()
    hermes = hermes_content if hermes_content is not None else load_hermes_skill_soul()
    if normalize_contract(internal) != normalize_contract(hermes):
        raise SoulContractSyncError("Hermes SOUL is not synced with BI_SOUL")


def render_agentscope_shell_policy() -> str:
    """渲染 Agentic Shell 外部入口 policy，不创建旧 runtime/API。"""

    contract = normalize_contract(load_internal_bi_soul())
    return "\n".join(
        [
            "Agentic Shell external entry policy",
            "compatibility_mode: removed_legacy_shell_adapter",
            "runtime_owner: datalogue_agentic_shell",
            "owns_business_runtime: true",
            "不得注册 schema、SQL、preview、database、artifact body 或 control_plane 工具",
            contract,  # 关键边界直接来自内部契约，避免外部入口另起一套说法。
        ]
    )

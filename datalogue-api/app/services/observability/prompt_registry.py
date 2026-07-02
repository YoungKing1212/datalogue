# ============================================================
# File Name   : prompt_registry.py
# Description:
#   Datalogue 本地 Prompt 注册表。
#
# Responsibilities:
#   - 汇总当前代码内 Prompt 的名称、模板内容和变量声明。
#   - 为运行期 prompt 基线、测试和离线审计提供同一份本地 Prompt 清单。
#
# Author      : yangkai
# Created On  : 2026-06-12
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.prompts.annotation import ANNOTATION_SYSTEM_PROMPT, TABLE_ANNOTATION_PROMPT
from app.prompts.blueprint_analyzer import (
    BLUEPRINT_DESCRIPTION_SYSTEM,
    BLUEPRINT_SQL_ANALYSIS_SYSTEM,
)
from app.prompts.dsl_generate import (
    build_inferred_system,
    build_no_schema_system,
    build_real_schema_system,
    build_semantic_system,
)
from app.prompts.intent_router import INTENT_RECOGNITION_SYSTEM
from app.prompts.report_generate import _REPORT_BASE as REPORT_BASE
from app.prompts.sql_audit import SQL_AUDIT_SYSTEM


PROMPT_PACK_VERSION = "2026-06-12-current"


DATALOGUE_COMPACTION_PROMPT_NAME = "datalogue-compaction"
DATALOGUE_COMPACTION_FALLBACK_PROMPT = """你是 Datalogue 多轮问数会话压缩器。

请把旧对话压缩为简洁中文摘要，只保留：
1. 叙事线：用户在分析什么业务问题，以及对话进展。
2. 用户偏好：偏好的口径、表达、输出风格。
3. 未解决问题：仍挂起的澄清、待确认项或风险。

不要保留具体查询条件、指标、维度、过滤器、SQL、完整结果行或可执行查询状态；这些由 SubAgent capsule 保存。

已有摘要：
{{existing_summary}}

待压缩旧消息：
{{messages_json}}

请输出 800 字以内的中文摘要。"""


@dataclass(frozen=True)
class RegisteredPrompt:
    """本地注册表中的一条 text prompt 定义。"""

    name: str
    display_name: str
    prompt: str
    description: str
    variables: tuple[str, ...] = ()
    tags: tuple[str, ...] = ("datalogue",)
    config: dict[str, Any] = field(default_factory=dict)

    def observability_config(self) -> dict[str, Any]:
        """生成用于本地审计和版本比对的结构化配置。"""

        return {
            "display_name": self.display_name,
            "chinese_name": self.display_name,
            "chinese_description": self.description,
            "description": self.description,
            "variables": list(self.variables),
            "prompt_pack_version": PROMPT_PACK_VERSION,
            **self.config,
        }


def build_dataset_prompt_block(dataset_prompt: str | None) -> str:
    """把数据集级 LLM 约束转换成可注入 report prompt 的块。"""

    if not dataset_prompt or not dataset_prompt.strip():
        return ""
    return "【数据集级 LLM 约束（硬性要求）】\n" + dataset_prompt.strip()


def get_registered_prompts() -> list[RegisteredPrompt]:
    """返回当前代码版本的本地 Prompt 清单。"""

    return [
        RegisteredPrompt(
            name="intent_recognition",
            display_name="入口意图识别",
            prompt=INTENT_RECOGNITION_SYSTEM,
            description="入口意图识别，区分数据查询、闲聊和功能指令。",
            tags=("datalogue", "router"),
        ),
        RegisteredPrompt(
            name="dsl_generate_real_schema",
            display_name="真实 Schema SQL 生成",
            prompt=build_real_schema_system("{{query_rules}}"),
            description="基于真实数据源 Schema 直接生成 SQL。",
            variables=("query_rules",),
            tags=("datalogue", "dsl", "sql"),
        ),
        RegisteredPrompt(
            name="dsl_generate_inferred",
            display_name="语义层推断 SQL 生成",
            prompt=build_inferred_system("{{query_rules}}"),
            description="语义层缺失指标时，基于表结构推断 SQL。",
            variables=("query_rules",),
            tags=("datalogue", "dsl", "sql"),
        ),
        RegisteredPrompt(
            name="dsl_generate_semantic",
            display_name="语义层 NL2DSL 生成",
            prompt=build_semantic_system(
                "{{dsl_limit_example}}",
                "{{semantic_time_rule}}",
                "{{semantic_limit_rule}}",
            ),
            description="基于语义层生成 NL2DSL v2 JSON。",
            variables=("dsl_limit_example", "semantic_time_rule", "semantic_limit_rule"),
            tags=("datalogue", "dsl", "semantic"),
        ),
        RegisteredPrompt(
            name="dsl_generate_no_schema",
            display_name="无 Schema SQL 兜底生成",
            prompt=build_no_schema_system("{{query_rules}}"),
            description="无 Schema 兜底路径，要求模型只生成 SELECT SQL。",
            variables=("query_rules",),
            tags=("datalogue", "dsl", "fallback"),
        ),
        RegisteredPrompt(
            name="report_generate",
            display_name="查询结果报告生成",
            prompt=REPORT_BASE + "\n\n{{dataset_prompt_block}}",
            description="根据用户问题和 SQL 查询结果生成中文数据洞察。",
            variables=("dataset_prompt_block",),
            tags=("datalogue", "report"),
        ),
        RegisteredPrompt(
            name="sql_audit",
            display_name="SQL 执行失败诊断",
            prompt=SQL_AUDIT_SYSTEM,
            description="SQL 执行失败后的根因诊断和修复建议。",
            tags=("datalogue", "sql-audit"),
        ),
        RegisteredPrompt(
            name=DATALOGUE_COMPACTION_PROMPT_NAME,
            display_name="多轮会话压缩摘要",
            prompt=DATALOGUE_COMPACTION_FALLBACK_PROMPT,
            description="多轮问数旧消息压缩摘要。",
            variables=("existing_summary", "messages_json"),
            tags=("datalogue", "multiturn"),
        ),
        RegisteredPrompt(
            name="annotation_field",
            display_name="字段语义标注",
            prompt=ANNOTATION_SYSTEM_PROMPT,
            description="字段业务语义和默认聚合方式标注。",
            tags=("datalogue", "annotation"),
        ),
        RegisteredPrompt(
            name="annotation_table",
            display_name="数据表业务描述生成",
            prompt=TABLE_ANNOTATION_PROMPT,
            description="表级业务描述生成。",
            tags=("datalogue", "annotation"),
        ),
        RegisteredPrompt(
            name="blueprint_sql_analysis",
            display_name="SQL 草稿蓝图分析",
            prompt=BLUEPRINT_SQL_ANALYSIS_SYSTEM,
            description="把 SQL 草稿分析成可审核、可发布的分析蓝图。",
            tags=("datalogue", "blueprint"),
        ),
        RegisteredPrompt(
            name="blueprint_description_analysis",
            display_name="业务场景蓝图草稿生成",
            prompt=BLUEPRINT_DESCRIPTION_SYSTEM,
            description="把业务场景描述转换成分析蓝图草案。",
            tags=("datalogue", "blueprint"),
        ),
    ]


def prompt_registry_by_name() -> dict[str, RegisteredPrompt]:
    """按 prompt name 索引注册表。"""

    return {item.name: item for item in get_registered_prompts()}

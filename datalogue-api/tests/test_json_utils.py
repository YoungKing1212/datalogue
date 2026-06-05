# ============================================================
# File Name   : test_json_utils.py
# Description:
#   宽容 JSON 工具函数测试。
#
# Responsibilities:
#   - 验证从混合模型输出中提取 JSON。
#   - 覆盖异常和边界输入场景。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""safe_json_parse 容错解析测试。"""

import pytest

from app.utils.json_utils import safe_json_parse


class TestSafeJsonParse:
    """LLM 输出 JSON 解析 — 必须能处理 think 块 + 多代码块场景。"""

    def test_markdown_json_code_block(self):
        """标准 ```json ... ``` 代码块。"""
        text = '```json\n{"sql": "SELECT 1"}\n```'
        assert safe_json_parse(text) == {"sql": "SELECT 1"}

    def test_bare_json_object(self):
        """裸 JSON。"""
        text = '{"sql": "SELECT 1"}'
        assert safe_json_parse(text) == {"sql": "SELECT 1"}

    def test_json_with_surrounding_text(self):
        """JSON 夹在文字里。"""
        text = '好的，结果如下：\n{"sql": "SELECT 1"}\n请查收。'
        assert safe_json_parse(text) == {"sql": "SELECT 1"}

    def test_think_block_with_sql_example_then_json(self):
        """回归用例：<think> 里有 ```sql 示例，</think> 之后才是 ```json。"""
        text = (
            "<think>\n"
            "The user wants ...\n"
            "```sql\n"
            "SELECT r.*\n"
            "FROM t1 r\n"
            "JOIN t2 p ON r.x = p.x\n"
            "```\n"
            "Let me output JSON.\n"
            "</think>\n"
            "```json\n"
            '{"sql": "SELECT r.* FROM t1 r JOIN t2 p ON r.x = p.x"}\n'
            "```\n"
        )
        # 关键：必须拿到 ```json 里的内容，不能被 ```sql 示例短路
        result = safe_json_parse(text)
        assert result == {"sql": "SELECT r.* FROM t1 r JOIN t2 p ON r.x = p.x"}

    def test_uppercase_json_code_block(self):
        """```JSON ... ``` 大写也要认。"""
        text = '```JSON\n{"sql": "SELECT 1"}\n```'
        assert safe_json_parse(text) == {"sql": "SELECT 1"}

    def test_invalid_json_returns_empty(self):
        """解析失败返回空 dict。"""
        assert safe_json_parse("not json at all") == {}
        assert safe_json_parse("```sql\nSELECT 1\n```") == {}  # SQL 块无 JSON

    def test_empty_input(self):
        """空输入返回空 dict。"""
        assert safe_json_parse("") == {}

    def test_nested_json_in_code_block(self):
        """嵌套结构。"""
        text = '```json\n{"a": {"b": [1, 2]}}\n```'
        assert safe_json_parse(text) == {"a": {"b": [1, 2]}}

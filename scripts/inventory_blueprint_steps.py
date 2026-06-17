#!/usr/bin/env python3
# ============================================================
# File Name   : inventory_blueprint_steps.py
# Description:
#   盘点 analysis_blueprint.steps 的真实字段形态与空值比例。
#
#   数据来源：
#   1. 本地 PostgreSQL 元数据库 analysis_blueprint / blueprint_version
#   2. tests/fixtures/phase5_analysis_blueprint_fixtures.jsonl
#   3. tests/test_analysis_blueprint.py 中硬编码的示例 payload
#
#   输出：打印结构化统计，供 docs/blueprint-steps-field-inventory.md 使用。
# ============================================================

from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 项目根目录
SCRIPT_DIR = Path(__file__).resolve().parent
API_ROOT = SCRIPT_DIR.parent / "datalogue-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402


def _flatten_steps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把多条 blueprint/版本/fixture 记录里的 steps 扁平化为单个 step 列表。"""
    flat: list[dict[str, Any]] = []
    for rec in records:
        steps = rec.get("steps") or []
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except json.JSONDecodeError:
                continue
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                flat.append(step)
    return flat


def _collect_step_field_stats(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """统计 step 字段出现率、类型、空值/空集合比例。"""
    total = len(steps)
    field_counts = Counter()
    field_types: dict[str, Counter] = defaultdict(Counter)
    empty_counts = Counter()  # 字段值为"空"（None/空串/空列表）的次数

    for step in steps:
        for key, value in step.items():
            field_counts[key] += 1
            field_types[key][type(value).__name__] += 1
            if value is None or value == "" or value == [] or value == {}:
                empty_counts[key] += 1

    stats: dict[str, Any] = {}
    for key in sorted(field_counts):
        present = field_counts[key]
        empty = empty_counts[key]
        stats[key] = {
            "present_count": present,
            "present_ratio": round(present / total, 4) if total else 0,
            "empty_count": empty,
            "empty_ratio": round(empty / present, 4) if present else 0,
            "types": dict(field_types[key]),
        }
    return {"total_steps": total, "fields": stats}


def _nested_complexity(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """统计 steps 嵌套结构复杂度。"""
    total = len(steps)
    key_rules_lengths = []
    output_columns_lengths = []
    for step in steps:
        kr = step.get("key_rules")
        if isinstance(kr, list):
            key_rules_lengths.append(len(kr))
        oc = step.get("output_columns")
        if isinstance(oc, list):
            output_columns_lengths.append(len(oc))

    return {
        "total_steps": total,
        "avg_key_rules_per_step": round(sum(key_rules_lengths) / len(key_rules_lengths), 2) if key_rules_lengths else 0,
        "max_key_rules": max(key_rules_lengths) if key_rules_lengths else 0,
        "avg_output_columns_per_step": round(sum(output_columns_lengths) / len(output_columns_lengths), 2) if output_columns_lengths else 0,
        "max_output_columns": max(output_columns_lengths) if output_columns_lengths else 0,
    }


def _load_db_records() -> list[dict[str, Any]]:
    """从 PostgreSQL 读取 analysis_blueprint 和 blueprint_version 的 steps。"""
    records: list[dict[str, Any]] = []
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        rows = db.execute(text("SELECT id, name, steps FROM analysis_blueprint ORDER BY id")).mappings().all()
        for row in rows:
            records.append({"source": "db.analysis_blueprint", "id": row["id"], "name": row["name"], "steps": row["steps"]})

        version_rows = db.execute(
            text("SELECT id, blueprint_id, version, snapshot->>'steps' AS steps FROM blueprint_version ORDER BY id")
        ).mappings().all()
        for row in version_rows:
            records.append(
                {
                    "source": "db.blueprint_version",
                    "id": row["id"],
                    "blueprint_id": row["blueprint_id"],
                    "version": row["version"],
                    "steps": row["steps"],
                }
            )
        db.close()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        print(f"数据库读取失败（将忽略）: {exc}", file=sys.stderr)
    return records


def _load_phase5_fixtures() -> list[dict[str, Any]]:
    """读取 phase5 fixture 中的 blueprint_seed.steps。"""
    records: list[dict[str, Any]] = []
    path = API_ROOT / "tests" / "fixtures" / "phase5_analysis_blueprint_fixtures.jsonl"
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fx = json.loads(line)
            seed = fx.get("blueprint_seed") or {}
            records.append(
                {
                    "source": "fixture.phase5",
                    "name": fx.get("name"),
                    "steps": seed.get("steps"),
                }
            )
    return records


def _load_test_payload_steps() -> list[dict[str, Any]]:
    """从 test_analysis_blueprint.py 的 payload 函数里提取 steps 样例。"""
    records: list[dict[str, Any]] = []
    path = API_ROOT / "tests" / "test_analysis_blueprint.py"
    if not path.exists():
        return records
    source = path.read_text(encoding="utf-8")

    # 匹配 payload 里的 steps 列表字面量（支持单/双引号键）
    pattern = re.compile(r'[\"\']steps[\"\']:\s*(\[[\s\S]*?\])', re.MULTILINE)
    for match in pattern.finditer(source):
        try:
            steps = ast.literal_eval(match.group(1))
            records.append({"source": "test.payload", "steps": steps})
        except (SyntaxError, ValueError):
            continue
    return records


def main() -> None:
    db_records = _load_db_records()
    fixture_records = _load_phase5_fixtures()
    test_records = _load_test_payload_steps()

    all_records = db_records + fixture_records + test_records
    all_steps = _flatten_steps(all_records)

    print("=" * 60)
    print("blueprint.steps 盘点脚本")
    print("=" * 60)
    print(f"\n来源统计:")
    print(f"  数据库记录: {len(db_records)} 条")
    print(f"  phase5 fixtures: {len(fixture_records)} 条")
    print(f"  测试 payload 样例: {len(test_records)} 条")
    print(f"  总 step 数: {len(all_steps)}")

    print("\n" + "-" * 60)
    print("字段统计（含来源合并）")
    print("-" * 60)
    stats = _collect_step_field_stats(all_steps)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n" + "-" * 60)
    print("嵌套结构复杂度")
    print("-" * 60)
    complexity = _nested_complexity(all_steps)
    print(json.dumps(complexity, ensure_ascii=False, indent=2))

    print("\n" + "-" * 60)
    print("按来源的字段覆盖率")
    print("-" * 60)
    for label, recs in [
        ("db", db_records),
        ("fixture.phase5", fixture_records),
        ("test.payload", test_records),
    ]:
        steps = _flatten_steps(recs)
        if not steps:
            continue
        s = _collect_step_field_stats(steps)
        print(f"\n[{label}] step 数={s['total_steps']}")
        for key, info in s["fields"].items():
            print(f"  {key}: 出现 {info['present_count']} 次 ({info['present_ratio'] * 100:.1f}%), 空值 {info['empty_count']} 次")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# ============================================================
# File Name   : evaluate.py
# Description:
#   运行 NL2SQL 工作流评估用例的脚本。
#
# Responsibilities:
#   - 将基准问题送入图工作流执行。
#   - 输出评估结果，便于检查问数准确率。
#
# Author      : yangkai
# Created On  : 2026-06-05
# ============================================================

"""
Datalogue NL2DSL2SQL 准确率评估框架

用法:
    cd datalogue-api
    python scripts/evaluate.py [--dataset_id DATASET_ID] [--output OUTPUT_JSON]

评估维度:
    1. Intent Accuracy    — 意图识别是否正确（query/chitchat/function）
    2. Schema Recall      — Schema 召回是否命中正确表/指标/维度
    3. DSL Validity       — DSL JSON 是否符合 schema 规范
    4. SQL Executability  — 生成的 SQL 是否可执行
    5. SQL Correctness    — SQL 执行结果是否与预期一致
    6. Answer Relevance   — 自然语言回答是否相关（人工/LLM 评估）

输出: JSON 报告 + 控制台摘要
"""

import os
import sys
import json
import argparse
import time
import logging
from typing import List, Dict
from dataclasses import dataclass, asdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.graph.workflow import build_workflow
from app.models.dataset import SemanticDataset

# ── 评估基准集（Benchmark）─────────────────────────────

BENCHMARK_CASES = [
    {
        "id": "case_001",
        "question": "最近30天的GMV是多少？",
        "dataset_id": None,  # 运行时填充
        "expected_intent": "query",
        "expected_metrics": ["gmv"],
        "expected_dimensions": [],
        "expected_sql_contains": ["SUM", "amount"],
        "expected_result_type": "scalar",
        "description": "单指标聚合查询",
    },
    {
        "id": "case_002",
        "question": "各地区的订单数对比",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["order_count"],
        "expected_dimensions": ["region"],
        "expected_sql_contains": ["COUNT", "region", "GROUP BY"],
        "expected_result_type": "table",
        "description": "单指标 + 单维度分组",
    },
    {
        "id": "case_003",
        "question": "华东区手机和电脑的GMV分别是多少？",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["gmv"],
        "expected_dimensions": ["region", "category"],
        "expected_sql_contains": ["SUM", "region", "category", "GROUP BY"],
        "expected_result_type": "table",
        "description": "指标 + 多维度 + 过滤",
    },
    {
        "id": "case_004",
        "question": "你好",
        "dataset_id": None,
        "expected_intent": "chitchat",
        "expected_metrics": [],
        "expected_dimensions": [],
        "expected_sql_contains": [],
        "expected_result_type": "none",
        "description": "闲聊意图",
    },
    {
        "id": "case_005",
        "question": "客单价最高的5个品类",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["avg_order_value"],
        "expected_dimensions": ["category"],
        "expected_sql_contains": ["AVG", "ORDER BY", "LIMIT"],
        "expected_result_type": "table",
        "description": "排序 + LIMIT",
    },
    {
        "id": "case_006",
        "question": "已取消订单占比多少？",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["cancel_rate"],
        "expected_dimensions": [],
        "expected_sql_contains": ["CASE", "已取消"],
        "expected_result_type": "scalar",
        "description": "复杂指标（CASE表达式）",
    },
    {
        "id": "case_007",
        "question": "最近7天各地区的已完成订单数",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["completed_order_count"],
        "expected_dimensions": ["region"],
        "expected_sql_contains": ["COUNT", "已完成", "GROUP BY"],
        "expected_result_type": "table",
        "description": "带过滤条件的指标 + 维度",
    },
    {
        "id": "case_008",
        "question": "销售额排名前3的品类",
        "dataset_id": None,
        "expected_intent": "query",
        "expected_metrics": ["gmv"],
        "expected_dimensions": ["category"],
        "expected_sql_contains": ["SUM", "ORDER BY", "LIMIT 3"],
        "expected_result_type": "table",
        "description": "同义词测试：销售额=GMV",
    },
]


# ── 评估结果数据结构 ───────────────────────────────────


@dataclass
class EvalResult:
    case_id: str
    question: str
    description: str

    # 各维度得分 (0 or 1)
    intent_correct: bool = False
    schema_recall_correct: bool = False
    dsl_valid: bool = False
    sql_executable: bool = False
    sql_correct: bool = False

    # 原始输出（用于调试）
    actual_intent: str = ""
    actual_dsl: Dict = None
    actual_sql: str = ""
    actual_error: str = ""
    execution_time_ms: float = 0.0

    @property
    def overall_score(self) -> float:
        """综合得分：意图 + DSL + SQL 可执行 + SQL 正确"""
        scores = [
            self.intent_correct,
            self.dsl_valid,
            self.sql_executable,
            self.sql_correct,
        ]
        return sum(scores) / len(scores)

    def to_dict(self) -> Dict:
        return asdict(self)


# ── 评估逻辑 ───────────────────────────────────────────


def run_single_case(db: Session, case: Dict, dataset_id: int) -> EvalResult:
    """运行单个评估用例，返回结果。"""
    result = EvalResult(
        case_id=case["id"],
        question=case["question"],
        description=case["description"],
    )

    # 构建工作流
    workflow = build_workflow(db)

    initial_state = {
        "question": case["question"],
        "dataset_id": dataset_id,
        "history": [],
        "intent": None,
        "entities": None,
        "schema_context": None,
        "dsl": None,
        "dsl_valid": False,
        "sql": None,
        "sql_result": None,
        "answer": None,
        "sql_list": [],
        "error": None,
        "retry_count": 0,
        "should_retry": False,
        "token_usage": None,
    }

    start_time = time.time()
    final_state = None

    try:
        for event in workflow.stream(initial_state):
            for node_name, state_delta in event.items():
                for k, v in state_delta.items():
                    if v is not None:
                        initial_state[k] = v
            final_state = initial_state.copy()
    except Exception as e:
        result.actual_error = str(e)
        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    result.execution_time_ms = (time.time() - start_time) * 1000

    # 记录实际输出
    result.actual_intent = final_state.get("intent", "")
    result.actual_dsl = final_state.get("dsl") or {}
    result.actual_sql = final_state.get("sql", "")

    # 1. 意图识别准确率
    result.intent_correct = result.actual_intent == case["expected_intent"]

    # 2. DSL 校验
    result.dsl_valid = final_state.get("dsl_valid", False)

    # 3. SQL 可执行性
    sql_result = final_state.get("sql_result")
    result.sql_executable = sql_result is not None and "error" not in str(sql_result).lower()

    # 4. SQL 正确性（简化版：检查 SQL 包含预期关键字）
    if result.actual_sql:
        sql_lower = result.actual_sql.lower()
        expected_kws = [kw.lower() for kw in case["expected_sql_contains"]]
        result.sql_correct = all(kw in sql_lower for kw in expected_kws)
    else:
        result.sql_correct = False

    return result


def evaluate_all(db: Session, dataset_id: int, cases: List[Dict]) -> List[EvalResult]:
    """运行所有评估用例。"""
    results = []
    for case in cases:
        result = run_single_case(db, case, dataset_id)
        results.append(result)
        score_pct = int(result.overall_score * 100)
        status = (
            "✅" if result.overall_score >= 0.75 else "⚠️" if result.overall_score >= 0.5 else "❌"
        )
        logger.info(f"  {case['id']}: {case['question'][:40]}... {status} {score_pct}% ({result.execution_time_ms:.0f}ms)")
    return results


def print_report(results: List[EvalResult]):
    """打印评估报告摘要。"""
    logger.info("=" * 70)
    logger.info("NL2DSL2SQL 准确率评估报告")
    logger.info("=" * 70)

    total = len(results)
    intent_acc = sum(1 for r in results if r.intent_correct) / total
    dsl_valid_rate = sum(1 for r in results if r.dsl_valid) / total
    sql_exec_rate = sum(1 for r in results if r.sql_executable) / total
    sql_correct_rate = sum(1 for r in results if r.sql_correct) / total
    overall = sum(r.overall_score for r in results) / total

    logger.info(f"评估用例总数: {total}")
    logger.info(f"意图识别准确率:     {intent_acc * 100:.1f}%")
    logger.info(f"DSL 合法率:         {dsl_valid_rate * 100:.1f}%")
    logger.info(f"SQL 可执行率:       {sql_exec_rate * 100:.1f}%")
    logger.info(f"SQL 正确率:         {sql_correct_rate * 100:.1f}%")
    logger.info("─────────────────────────────────")
    logger.info(f"综合得分:           {overall * 100:.1f}%")

    # 失败用例详情
    failures = [r for r in results if r.overall_score < 1.0]
    if failures:
        logger.warning(f"失败用例详情 ({len(failures)} 个):")
        for r in failures:
            logger.warning(f"  [{r.case_id}] {r.question}")
            logger.warning(f"    描述: {r.description}")
            logger.warning(
                f"    意图: expected={BENCHMARK_CASES[int(r.case_id.split('_')[1])-1]['expected_intent']}, actual={r.actual_intent}"
            )
            logger.warning(f"    DSL valid: {r.dsl_valid}")
            logger.warning(f"    SQL executable: {r.sql_executable}")
            logger.warning(f"    SQL correct: {r.sql_correct}")
            if r.actual_sql:
                logger.warning(f"    生成 SQL: {r.actual_sql[:100]}...")
            if r.actual_error:
                logger.error(f"    错误: {r.actual_error}")

    avg_latency = sum(r.execution_time_ms for r in results) / total
    logger.info(f"平均延迟: {avg_latency:.0f}ms")
    logger.info("=" * 70)

    return {
        "total_cases": total,
        "intent_accuracy": intent_acc,
        "dsl_validity": dsl_valid_rate,
        "sql_executability": sql_exec_rate,
        "sql_correctness": sql_correct_rate,
        "overall_score": overall,
        "avg_latency_ms": avg_latency,
        "case_results": [r.to_dict() for r in results],
    }


# ── 主入口 ───────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Datalogue NL2DSL2SQL 准确率评估")
    parser.add_argument(
        "--dataset_id",
        type=int,
        default=None,
        help="评估用的数据集 ID（默认查找第一个 active 数据集）",
    )
    parser.add_argument("--output", type=str, default=None, help="输出 JSON 报告路径")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Datalogue NL2DSL2SQL 准确率评估框架")
    logger.info("=" * 70)

    db = SessionLocal()
    try:
        # 确定数据集
        dataset_id = args.dataset_id
        if not dataset_id:
            dataset = db.query(SemanticDataset).filter(SemanticDataset.status == "active").first()
            if not dataset:
                logger.error("未找到 active 数据集，请先运行 seed_data.py 初始化测试数据")
                return
            dataset_id = dataset.id
            logger.info(f"使用数据集: {dataset.name} (id={dataset_id})")
        else:
            dataset = db.get(SemanticDataset, dataset_id)
            if not dataset:
                logger.error(f"数据集 {dataset_id} 不存在")
                return
            logger.info(f"使用数据集: {dataset.name} (id={dataset_id})")

        # 更新 benchmark 中的 dataset_id
        for case in BENCHMARK_CASES:
            case["dataset_id"] = dataset_id

        logger.info(f"开始评估 {len(BENCHMARK_CASES)} 个用例...")
        results = evaluate_all(db, dataset_id, BENCHMARK_CASES)
        report = print_report(results)

        # 保存报告
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"报告已保存: {args.output}")

        # 返回码：overall >= 0.6 为通过
        if report["overall_score"] >= 0.6:
            logger.info("评估通过！综合得分 >= 60%")
        else:
            logger.warning("评估未通过，综合得分 < 60%，建议优化语义层或 Prompt")

    finally:
        db.close()


if __name__ == "__main__":
    main()

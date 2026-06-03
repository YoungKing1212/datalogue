# DSL 校验节点改造方案

> 状态：已批准（Plan: agile-prancing-mitten）
> 日期：2026-06-03
> 范围：`datalogue-api/app/graph/` + `app/utils/`

---

## 一、背景与目标

### 1.1 当前痛点

`dsl_validate_node`（`app/graph/nodes.py`）只做一件事：**name 集合的成员检查**。它几乎抓不到真正的 SQL 错误：

| 错误类型 | 当前能否拦截 | 实际表现 |
|---|---|---|
| `time_range.field` 瞎填 DDL 列名 | ❌ 拦不住 | SQL 执行报 `Unknown column 'create_date'` |
| `filter_sql` 写 `xxx != null` | ❌ 拦不住 | SQL 语法错（应使用 `IS NOT NULL`） |
| 表/列名拼错 | ❌ 拦不住 | 1054 / 1064 错误 |
| join 字段不匹配 | ❌ 拦不住 | SQL 执行失败 |

这些错误**绕过** dsl_validate，跑到 `sql_execute` 才在 DB 层报 1054/1064。失败后 `_sql_execution_router`（`workflow.py:45-55`）直接把原始错误字符串塞进 `state["error"]`，扔回 `dsl_generate` 让 LLM 看着一行"Unknown column 'xxx'" 猜哪里错——**没有任何业务上下文、没有 DDL、没有样例数据**。

### 1.2 改造目标

1. **第一次** dsl_generate 输出后，validate 只做**最轻量的基础校验**（name 集合 + 必填 + 格式）
2. **放行**到 sql_execute
3. **执行失败时**进入新的 `sql_audit_node`（Agent 校验），**结合指标/维度/业务术语/关联表 DDL/1-2 条样例数据**做语义级诊断
4. Agent 输出**结构化诊断 JSON**，区分 `fixable`（下次重试能改对）和 `architectural`（数据集配置错，LLM 改不了）
5. `fixable` → 走原重试链；`architectural` → 直接 END，告诉用户去修数据集

### 1.3 预期收益

- SQL 失败时 LLM 拿到的不是一行裸错误，而是「指标 X 的 time_field 是 Y，DDL 里没有 time_range.field 里的 Z 列名，应该用 Y」——**重试命中率显著提升**
- **架构性问题能早停**，不再无谓烧 token
- 审计日志可观测（保留 `sql_audit` 字段）

---

## 二、架构变更

```
                       ┌─────────────────────┐
                       │   dsl_validate      │  ← 改造：只做基础校验
                       │ (基础 name 集合检查)  │     - name ∈ valid_names
                       └──────────┬──────────┘     - metrics 非空
                                  │ pass            - filters 字段合法
                                  ▼
                       ┌─────────────────────┐
                       │   dsl_compiler      │  ← 不变
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │   sql_execute       │  ← 不变
                       └──────────┬──────────┘
                                  │ fail
                                  ▼
                       ┌─────────────────────┐
                       │   sql_audit         │  ← 新增：Agent 智能审计
                       │ (LLM + DDL + 样例)   │
                       └──────────┬──────────┘
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                fixable │                     │ architectural
                       ▼                     ▼
                ┌────────────┐         ┌──────────┐
                │increment_  │         │   END    │
                │   retry    │         │ (用户修)  │
                └─────┬──────┘         └──────────┘
                      │
                      ▼
                ┌────────────┐
                │dsl_generate│
                │(拿审计结果) │
                └────────────┘
```

**重试预算**：`retry_count` 仍共享（3 次总预算），简化不引入新计数器。`architectural` 走 END 时**不消耗** `retry_count`。

---

## 三、实施分阶段

### Phase 1：简化 `dsl_validate_node` 为"基础校验"

**文件**：`app/graph/nodes.py:508-564`

**保留**：
- `metrics 非空` 检查
- 指标/维度 name ∈ valid_names
- filter.field ∈ valid_names

**移除**（深度判断下放给 sql_audit 由 LLM 判）：
- 真实 Schema 模式的"SQL 非空"硬卡
- ~~`dsl_valid=True` 后仍要发 `should_retry=False` 走 compiler~~（保留原有逻辑）

**净效果**：现在 dsl_validate 几乎所有情况都过——**这是故意的**，深度判断交给 sql_audit。

---

### Phase 2：新增 `sql_audit_node`（核心）

**位置**：`app/graph/nodes.py`（在 dsl_compiler_node 之后）

**签名**：`sql_audit_node(db: Session)` 工厂模式（与 `schema_recall` / `sql_execute` 一致）

#### 3.2.1 输入

```python
def _node(state: AgentState) -> Dict[str, Any]:
    question = state["question"]
    dsl = state.get("dsl") or {}
    sql = state.get("sql")
    error = state.get("error", "")
    schema_context = state.get("schema_context", "")
    schema_structured = state.get("schema_structured")
    ddl_context = state.get("ddl_context", "")
    metric_resolution = state.get("metric_resolution") or {}
    dataset_id = state.get("dataset_id")
```

#### 3.2.2 取关联表 DDL + 样例数据

- `ddl_context` 已由 `schema_recall_node` 构建（包含表注释/列注释/业务描述），**直接复用**
- 样例数据：从 `source_column.sample_values` 拿（`source_column` 表已有 `sample_values` 列，类型 JSON）

工具函数 `fetch_sample_rows(db, table_names, per_table=2)` 抽到 `app/utils/sample_data.py`。

样例拼成 prompt 片段：
```
【样例数据】
表 t_order:
  - id=1, order_no='SO20250101001', order_amt=299.00, status=1, create_time=datetime(...)
  - id=2, order_no='SO20250101002', order_amt=1599.00, status=4, create_time=datetime(...)
表 t_refund:
  - id=1, refund_amt=100.00, finish_time=datetime(...), apply_time=datetime(...)
```

#### 3.2.3 Few-shot Prompt

**System prompt**（3 个真实案例 + 兜底规则）：

```text
你是 Datalogue 的 SQL 审计 Agent。当 SQL 执行失败时，
结合业务语义层、表结构、样例数据，给出结构化诊断。

输出 JSON（仅输出 JSON，不要其他说明）：
{
  "root_cause": "根因短句（中文，20 字内）",
  "wrong_field": "错填的字段名或 null",
  "suggested_fix": "建议的修正方向（中文自然语言）",
  "severity": "fixable" | "architectural"
}

severity 判定：
- fixable：下次重试能改对（字段名拼错、operator 错用、表名错、列引用错）
- architectural：LLM 无法修复（数据集没选表、指标引用的列在 DDL 里根本不存在、JOIN 关系缺失）

## Few-shot 案例

【案例 1】time_range.field 错填 DDL 列名
- DSL: { metrics: ["退款金额"], time_range: { field: "create_date", ... } }
- SQL: SELECT SUM(refund_amt) FROM t_refund WHERE `create_date` >= '2025-01-01'
- 错误: Unknown column 'create_date' in 'where clause'
- 指标 "退款金额" 在语义层中 time_field=apply_time
- 输出:
  {
    "root_cause": "time_range.field 错填 DDL 列名",
    "wrong_field": "create_date",
    "suggested_fix": "time_range.field 应改为指标 退款金额 在语义层声明的 time_field 'apply_time'",
    "severity": "fixable"
  }

【案例 2】filter_sql 用了 Python 风格 null 比较
- 指标 filter_sql: "finish_time != null"
- SQL: WHERE (finish_time != null) AND ...
- 错误: You have an error in your SQL syntax near '!= null'
- 输出:
  {
    "root_cause": "filter_sql 用了非标 null 比较",
    "wrong_field": "finish_time != null",
    "suggested_fix": "把 'finish_time != null' 改成 'finish_time IS NOT NULL'（IS NULL / IS NOT NULL 是标准 SQL）",
    "severity": "fixable"
  }

【案例 3】指标引用的列在 DDL 里不存在
- 指标 expr: "SUM(refund_amt)", table_name: "t_refund"
- DDL: t_refund (id, refund_apply_amt, apply_time, ...)  ← 没有 refund_amt
- 错误: Unknown column 'refund_amt' in 'field list'
- 输出:
  {
    "root_cause": "指标 expr 引用了 DDL 中不存在的列",
    "wrong_field": "refund_amt",
    "suggested_fix": "在数据集语义层把 退款金额 指标的 expr 改为 SUM(refund_apply_amt)，或在数据源侧为 t_refund 补充 refund_amt 列",
    "severity": "architectural"
  }
```

#### 3.2.4 关键决策

- **`architectural` 直接 `should_retry=False`** → 进 END → `chat.py` 拼出"建议检查语义层配置"给用户，不再烧 token
- **`fixable` 走原重试链** → `state["error"]` 字段被**改写**为更友好的诊断文本（"上一轮 SQL 错因: time_range.field 错填 DDL 列名 create_date，应改用指标'退款金额'的 time_field apply_time"），让 dsl_generate LLM 看得懂
- **不引入独立 retry 计数**（沿用 `retry_count` 池，3 次总预算）—— 简化，避免 3 次预算被切得太碎
- **`temperature=0`**（与 `intent_recognition` 一致）—— 审计是确定性判断
- **architectural 也保留审计日志**（写进 `sql_audit_result` 字段），便于诊断"为什么系统认为这是架构问题"

#### 3.2.5 状态写入

```python
return {
    "sql_audit_result": {  # 注意：不能用 "sql_audit"——与节点同名会被 LangGraph 拒绝
        "root_cause": result.get("root_cause"),
        "wrong_field": result.get("wrong_field"),
        "suggested_fix": result.get("suggested_fix"),
        "severity": result.get("severity"),
    },
    "should_retry": result.get("severity") == "fixable",
    # 重写 error 字段为审计友好文本（仅 fixable 时）
    "error": friendly_error_text if result.get("severity") == "fixable" else original_error,
}
```

---

### Phase 3：workflow 改造

**文件**：`app/graph/workflow.py`

```python
# 1) 注册新节点
workflow.add_node("sql_audit", sql_audit_node(db))

# 2) 改 _sql_execution_router
def _sql_execution_router(state) -> str:
    if not state.get("should_retry"):
        if state.get("sql_result") is None:
            return "end"
        return "report"
    # SQL 失败 → 进 sql_audit（不再直接 increment_retry）
    return "audit"

# 3) 改 sql_execute 边
workflow.add_conditional_edges(
    "sql_execute",
    _sql_execution_router,
    {"report": "report_generator", "audit": "sql_audit", "end": END},
)

# 4) 新增 _sql_audit_router
def _sql_audit_router(state) -> str:
    # architectural 或 retry_count 用尽 → END
    audit = state.get("sql_audit") or {}
    if audit.get("severity") == "architectural":
        return "end"
    if state.get("retry_count", 0) >= 3:
        return "end"
    return "retry"

# 5) 新增 sql_audit 边
workflow.add_conditional_edges(
    "sql_audit",
    _sql_audit_router,
    {"retry": "increment_retry", "end": END},
)
```

---

### Phase 4：清理（低风险）

- 把 `sql_audit_node` 内的 `_fetch_sample_rows` 抽到 `app/utils/sample_data.py`
- 不再消耗 `retry_count` 在 dsl_validate 上：dsl_validate 只做基础校验，几乎都过，`retry_count` 几乎都用在 SQL 层失败 + audit 上，3 次够用
- `app/utils/__init__.py` re-export `fetch_sample_rows`
- `app/graph/state.py` 加 `sql_audit: Optional[dict]` 字段

---

## 四、关键文件清单

| 文件 | 操作 | 关键改动 |
|---|---|---|
| `datalogue-api/app/graph/nodes.py` | 改 | 简化 dsl_validate；新增 sql_audit_node（含 _fetch_sample_rows） |
| `datalogue-api/app/graph/workflow.py` | 改 | 改 _sql_execution_router；新增 _sql_audit_router；注册 sql_audit 节点 |
| `datalogue-api/app/utils/sample_data.py` | 新建 | `fetch_sample_rows(db, table_names, per_table=2)` 工具函数 |
| `datalogue-api/app/utils/__init__.py` | 改 | re-export `fetch_sample_rows` |
| `datalogue-api/app/graph/state.py` | 改 | AgentState 加 `sql_audit_result: Optional[dict]` 字段（**不能用 `sql_audit`，与节点名同名会被 LangGraph 拒绝**） |
| `datalogue-api/tests/test_sql_audit.py` | 新建 | 单元测试 |

---

## 五、验证计划

### 5.1 单元层

`pytest tests/test_sql_audit.py -v`（新建）
- mock LLM 返回 `severity=fixable` → 断言 `should_retry=True`
- mock LLM 返回 `severity=architectural` → 断言 `should_retry=False`
- mock LLM 返回非 JSON → 走 fallback，severity 默认 `fixable`

### 5.2 集成层（手工 curl + 观察日志）

**场景 1：故意造"用错 time_field"场景**
- `dataset_id=4`（"退款金额"指标的 `time_field=apply_time`）
- 请求体：`{"question":"今年退款总金额","dataset_id":4}`
- 期望日志：
  - SQL 执行失败（Unknown column 'create_date'）
  - `sql_audit` 节点 running/done
  - `sql_audit` 输出：`{"root_cause":"time_range.field 错填...","severity":"fixable"}`
  - dsl_generate 重试 1 次，第二次 SQL 用 `apply_time` → 成功

**场景 2：造"architectural"场景**
- `dataset_id=4`，指标 `expr` 改成 `SUM(refund_amt)` 但 `t_refund` 没有 `refund_amt` 列
- 期望：`sql_audit` 诊断为 `architectural` → 直接 END → 前端看到"建议检查语义层配置"

### 5.3 回归

- 走完一次正常（无错误）对话，验证 happy path 不变
- 走一次"无指标无维度"空数据集，验证 dsl_validate 仍能拦下
- 走一次"直接对话闲聊"，intent=chitchat 走 END 不变

### 5.4 性能

- `sql_audit` 多一次 LLM 调用（temperature=0，平均 ~500 tokens input + ~200 tokens output）
- 样例数据查询 1-2 个表，每表 LIMIT 2，毫秒级
- 整体重试回路最多多花 1-2 秒（在失败路径上，正常路径零开销）

---

## 六、风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 把"列名拼错"误判为 architectural | prompt 明确：DDL 里**没有该列**才算 architectural；DDL 有但引用错是 fixable |
| 样例查询命中敏感数据 | `SELECT * LIMIT 2` 仅 2 行；考虑未来在 utils 里加脱敏钩子 |
| sql_audit 自己失败（LLM 异常） | try/except 兜底：异常时 `severity=fixable` + 原始 error，原路重试 |
| retry_count 在 audit 上消耗导致正常重试预算变少 | 保留现状不引入独立计数；测试验证 3 次总预算仍能覆盖典型 fixable 错误 |
| 多个表 join 场景下 DDL 上下文过长 | `ddl_context` 已经是按表分块；样例只取 metrics 引用的 table，避免冗余 |
| dsl_compiler 错误（语法/危险关键字）现在无声经过 sql_execute | sql_audit 节点**也会**捕获（因为 error 会写进 state）；少数情况让 audit 误判为 fixable，可接受 |

---

## 七、不在本 PR 范围（明确不做）

- ❌ 独立 sql_audit_retry 计数（沿用 retry_count 池）
- ❌ 前端 UI 区分"SQL 失败"和"DSL 失败"（chat.py 兜底文案不变）
- ❌ 样例数据脱敏（先跑通，再加）
- ❌ 把 dsl_validate 完全删掉（保留基础校验作为快速失败）
- ❌ pgvector 召回（独立任务）

---

## 八、相关文件链接

- 原始 Plan（已批准）：`/Users/yangkai/.claude/plans/agile-prancing-mitten.md`
- 代码规范：`docs/CODE_STYLE.md`
- 审查清单：`docs/CHECKLIST.md`

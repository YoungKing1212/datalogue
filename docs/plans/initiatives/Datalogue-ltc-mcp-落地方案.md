# Datalogue 借鉴 ltc-mcp 架构落地实施方案

- 日期：2026-07-13
- 作者：KenYang + Claude
- 依据：《ltc-mcp 对 Datalogue 的架构借鉴分析》
- 目标：把 6 项借鉴建议转化为可执行、可验证、可回滚的落地路线图

---

## 一、目标与边界

### 1.1 核心目标

在不破坏 Datalogue "无需建模、接入即用" 通用问数卖点的前提下，把 ltc-mcp 验证过的三项核心能力（查询代数、指标库、静态守卫）作为**可选增强层**接入现有 BIWorker 架构，实现：

1. **2 周内**交付可验证 MVP：澄清提示、停更表过滤、首个指标模板；
2. **1 个月内**完成指标库、唯一执行入口、静态守卫；
3. **1 个季度内**完成查询代数编译器与可选本体建模框架。

### 1.2 设计边界

- **不绑定具体业务域**：指标库/本体采用可插拔的 `domain package` 设计，便于多场景复用。
- **不破坏现有路径**：默认仍走 schema slice + describe + LLM 生成 QueryPlan；结构化增强路径作为**高置信分支**存在。
- **Fail-closed**：任何增强路径校验失败时，必须能安全降级到现有路径或直接返回受控失败。

---

## 二、现状盘点

| 层级 | 现有能力 | 与 ltc-mcp 的差距 |
|---|---|---|
| **L0-L4 渐进式上下文** | `BIWorkerQueryValidator` + `ProgressiveContextState` 已覆盖资产/关系/字段校验 | 缺少空结果时的口径澄清提示 |
| **L5 Runtime** | `BIWorkerQueryRuntime.execute_query_plan()` 将计划转 DSL 后执行 | 没有指标模板匹配层；结果为空时直接抛 `EMPTY_RESULT` |
| **编译器** | `compile_query_plan_to_sql()` 从语义计划编译 SQL，拒绝 LLM 直接 SQL | 本质已是轻量查询代数，但依赖 LLM 生成 plans，缺少预定义指标/本体资产 |
| **SQL Guard** | `guard_readonly_sql()` 静态只读校验 + 表白名单 | 属于运行时审计，不是编译期 RLS 注入；缺少 CI 静态守卫 |
| **Schema 发现** | `datalogue_describe_tables` / schema slice | 缺少停更/弃用表过滤机制 |

**关键判断**：Datalogue 的 `BIWorkerQueryPlan` 契约已经是查询代数的雏形。本方案不是从零引入"本体建模"，而是**在现有契约之上叠加指标模板层、口径澄清层、安全守卫层和可选的 YAML 本体层**。

---

## 三、总体架构设计

### 3.1 增强后的查询路径

```text
用户问题
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. 意图/指标匹配层 (Metric Template Matcher)                  │
│    - 命中指标模板 → 直接生成 BIWorkerQueryPlan（高置信路径）   │
│    - 未命中 → 继续走 LLM 规划路径（现状）                      │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. 渐进式上下文层 (L0-L4，现状增强)                            │
│    - 停更表过滤（新增）                                       │
│    - 字段/关系/资产校验（现状）                                │
│    - 缺失上下文时返回 clarifying questions（新增）             │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 编译执行层 (L5，现状增强)                                   │
│    - 指标模板 → 查询代数 → 参数化 SQL（新增）                  │
│    - 普通 QueryPlan → compiler.py（现状）                      │
│    - 统一执行入口 `execute_scoped_query()`（新增）             │
│    - SQL Guard + 权限谓词注入（增强）                          │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
结果 + 口径澄清提示（新增）
```

### 3.2 新增模块位置

| 模块 | 建议路径 | 说明 |
|---|---|---|
| 指标库定义 | `app/domains/ontology/metrics/` | 按域分包，如 `app/domains/ontology/metrics/common/` |
| 指标模板运行时 | `app/domains/bi/worker/metric_template.py` | 匹配、填充、生成 QueryPlan |
| 停更/弃用表台账 | `app/domains/data_source/rejected_tables.py` | 黑名单 + schema slice 过滤 |
| 口径澄清提示 | `app/domains/bi/worker/clarification_hint.py` | 空结果/多口径场景附提示 |
| 统一执行入口 | `app/domains/query_execution/executor.py` | 唯一 `execute_scoped_query()` |
| 静态守卫 | `tests/test_execution_entry_guard.py` | CI 门禁，禁止绕过入口直接执行 SQL |
| 可选本体层 | `app/domains/ontology/` | YAML 本体 + 查询代数编译器 |

---

## 四、分阶段实施计划

### Phase 1：2 周 MVP（可验证版本）

**目标**：上线 3 个立竿见影的能力，并为后续模块搭好脚手架。

| 序号 | 任务 | 负责人 | 交付物 | 验收标准 |
|---|---|---|---|---|
| P1-1 | **停更表台账 + schema slice 过滤** | 后端 | `RejectedTableRegistry` + 过滤逻辑 | 停更表不进入 `datalogue_describe_tables` / schema slice 返回；新增单元测试 |
| P1-2 | **空结果口径澄清提示** | 后端/提示工程 | `ClarificationHintGenerator` | `EMPTY_RESULT` 时返回带口径怀疑的提示；agent 不再把"0"当真相 |
| P1-3 | **首个通用指标模板** | 后端 | `MetricTemplate` 基类 + 1 个示例模板（如"某表按维度汇总"） | 命中模板时跳过 LLM 规划，直接生成 QueryPlan；单测覆盖 |
| P1-4 | **统一执行入口骨架** | 后端 | `execute_scoped_query()` 壳子，先透传现有逻辑 | 所有执行调用通过该入口；为 Phase 2 接入 RLS 做准备 |
| P1-5 | **MVP 集成验证** | 测试/产品 | 端到端用例 3-5 个 | 停更表被过滤、空结果带提示、指标模板命中并返回正确结果 |

**Phase 1 风险**：指标模板如果设计过窄会误伤长尾问法。建议首版只做"单表 + 聚合 + 维度分组"的通用模板，不绑定具体业务字段。

---

### Phase 2：1 个月（架构安全升级）

**目标**：完成指标库、唯一执行入口、静态守卫，使高频问法稳定可信。

| 序号 | 任务 | 交付物 | 验收标准 |
|---|---|---|---|
| P2-1 | **指标库扩展** | 20-50 个通用指标模板 + `MetricTemplateLibrary` | 覆盖常见聚合口径；支持模板版本管理 |
| P2-2 | **统一执行入口硬化** | `executor.py` 内完成 RLS 谓词注入、权限校验 | 所有 SQL 执行必经此入口；直接调用 `db.execute()` 的代码被 CI 守卫拦截 |
| P2-3 | **静态守卫测试** | `tests/test_execution_entry_guard.py` | CI 失败当任何模块绕过 `execute_scoped_query()` 直接执行 SQL |
| P2-4 | **权限谓词编译期注入** | `ScopePredicateBuilder` | 按 principal 注入 `tenant_id = ?` 等条件，fail-closed |
| P2-5 | **指标库评测门禁** | `eval/metric_regression.py` |  golden/paraphrase 用例通过率达到约定阈值 |

---

### Phase 3：1 个季度（战略级能力）

**目标**：完成查询代数编译器和可选本体建模，形成差异化护城河。

| 序号 | 任务 | 交付物 | 验收标准 |
|---|---|---|---|
| P3-1 | **查询代数编译器** | `app/domains/ontology/algebra_compiler.py` | 支持 `{field, op, value}` / `{any:[...]}` / `{combine:...}` 到参数化 SQL |
| P3-2 | **YAML 本体建模框架** | `app/domains/ontology/models/` + YAML 定义规范 | 客户可配置 object/field/relationship/metrics/scope；不配置时不影响通用路径 |
| P3-3 | **本体驱动执行路径** | 本体命中时走查询代数，未命中走 LLM 规划 | 高频建模场景准确率 95%+；攻击面为 0 |
| P3-4 | **分层评测门禁** | `eval/` 下 adversarial RLS / schema drift / replay 评测 | 越权问法 = 0 通过；schema 变化自动报警 |
| P3-5 | **客户交付文档** | 本体建模指南 + 指标库贡献指南 | 客户/实施团队能独立扩展场景包 |

---

## 五、关键模块设计

### 5.1 澄清提示模块

**位置**：`app/domains/bi/worker/clarification_hint.py`

**触发条件**：

- `row_count == 0`
- 问题中包含时间/状态/类型等多义词汇
- 查询计划中有 `assumptions` 未被用户确认

**输出示例**：

```python
{
    "hint_type": "empty_result_ambiguous_time",
    "safe_message": "查询未返回数据。'2026年'可能对应多种时间口径（签约日期/立项年度/预算年度），请勿直接下结论。",
    "recommended_action": "请与用户确认具体口径后重查。",
    "candidate_dimensions": ["签约日期", "立项年度", "预算年度"]
}
```

**接入点**：在 `BIWorkerQueryRuntime.execute_query_plan()` 的 `EMPTY_RESULT` 分支后追加 `clarification_hint` 字段，透传给 agent。

---

### 5.2 停更表台账

**位置**：`app/domains/data_source/rejected_tables.py`

**数据结构**：

```python
class RejectedTable(BaseModel):
    datasource_id: int
    schema_name: str
    table_name: str
    reason: Literal["deprecated", "empty", "stale", "manual"]
    rejected_at: datetime
    rejected_by: str | None
    replacement_ref: str | None  # 替代表
```

**接入点**：

- `datalogue_describe_tables` 工具在返回前过滤；
- schema slice 生成时过滤；
- 可扩展为自动发现：基于 `eval/profile_db.py` 画像结果自动标记空表/长期未更新表，人工复核后入库。

---

### 5.3 指标库

**位置**：`app/domains/ontology/metrics/`

**模板定义示例**：

```yaml
# app/domains/ontology/metrics/common/revenue.yaml
metric_id: common_revenue_by_dimension
name: 按维度汇总收入
domain: common
intent: metric_query
template:
  primary_entity:
    object: Contract          # 可选：绑定本体对象
  metrics:
    - op: sum
      field: amount
      display_name: 收入总额
  dimensions:
    - field: department
      display_name: 部门
  filters:
    - field: direction
      op: eq
      value: "068001"
      editable: false         # 固定口径，不可改
  time_dimension:
    field: sign_date
    default_grain: month
```

**运行时类**：

```python
class MetricTemplate:
    metric_id: str
    match_score(question: str, context: dict) -> float  # 语义匹配
    fill(parameters: dict) -> BIWorkerQueryPlan           # 生成计划
```

**接入点**：在 `BIWorkerQueryRuntime.execute_query_plan()` 之前加 `MetricTemplateMatcher`；命中则直接生成 `BIWorkerQueryPlan`。

---

### 5.4 唯一执行入口 + 静态守卫

**位置**：`app/domains/query_execution/executor.py`

```python
async def execute_scoped_query(
    *,
    db: Session,
    dataset_id: int,
    principal: Principal,
    query_plan: BIWorkerQueryPlan | dict,
    scope_predicates: list[ScopePredicate],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """唯一受控查询执行入口。

    职责：
    - 编译期注入 RLS 谓词；
    - 调用 compiler + SQL Guard；
    - 统一错误包装，禁止 SQL/raw rows 外泄。
    """
```

**静态守卫**：

```python
# tests/test_execution_entry_guard.py
import ast

def test_no_direct_sql_execution():
    """禁止任何模块直接调用 db.execute / session.execute 等绕过入口。"""
```

通过 AST 扫描 `app/` 下所有 `.py` 文件，确保除 `executor.py` 外没有裸 `execute()` 调用。

---

### 5.5 查询代数编译器

**位置**：`app/domains/ontology/algebra_compiler.py`

**代数 AST**：

```python
class AlgebraNode(BaseModel): ...
class FieldFilter(AlgebraNode):
    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "between"]
    value: Any
class AnyFilter(AlgebraNode):
    nodes: list[AlgebraNode]
class CombineFilter(AlgebraNode):
    op: Literal["and", "or"]
    nodes: list[AlgebraNode]
```

**编译流程**：

```text
AlgebraNode
  → 作用域展开（按 principal 注入 RLS）
  → 物理字段解析（本体 YAML 映射到 schema.table.column）
  → SQL AST（sqlglot 或直接字符串模板）
  → 参数化 SQL + 参数列表
```

**关键约束**：

- 所有值走参数绑定，禁止字符串拼接；
- 只能引用本体/指标库中声明的字段；
- 编译失败返回 `ALGEBRA_COMPILE_FAILED`，不暴露内部错误。

---

### 5.6 可选本体建模

**位置**：`app/domains/ontology/`

**目录结构**：

```text
app/domains/ontology/
├── __init__.py
├── models.py              # Ontology / Object / Field / Relationship / Metric
├── loader.py              # YAML 加载与校验
├── scope.py               # RLS 谓词生成
├── algebra_compiler.py    # 查询代数 → SQL
├── metrics/               # 指标库
│   ├── common/
│   └── __init__.py
└── domains/               # 场景本体包（可选）
    └── ltc/
        ├── _objects.yaml
        ├── _metrics.yaml
        └── _rejected.yaml
```

**接入策略**：

- 无本体：走现有 LLM 规划路径；
- 有本体但问题未命中：仍走 LLM 规划，但可用本体字段做 schema slice 增强；
- 有本体且命中指标/对象：走查询代数高置信路径。

---

## 六、验证与验收标准

### 6.1 单元测试

| 模块 | 测试文件 | 覆盖点 |
|---|---|---|
| 停更表过滤 | `tests/test_rejected_tables.py` | 黑名单命中/未命中、大小写、schema 限定 |
| 澄清提示 | `tests/test_clarification_hint.py` | 空结果触发、多义时间词、assumptions |
| 指标模板 | `tests/test_metric_template.py` | 匹配、填充、生成计划 |
| 统一入口 | `tests/test_scoped_executor.py` | RLS 注入、失败包装、降级 |
| 静态守卫 | `tests/test_execution_entry_guard.py` | 绕过入口即 CI 失败 |
| 查询代数 | `tests/test_algebra_compiler.py` | 参数化、RLS、不合法字段拒绝 |

### 6.2 端到端评测

| 评测类型 | 目标 | 工具 |
|---|---|---|
| Golden query | 模板命中问法 100% 通过 | `eval/metric_regression.py` |
| Paraphrase | 同义问法 90%+ 命中同一模板 | `eval/paraphrase_match.py` |
| Adversarial RLS | 越权问法 = 0 通过 | `eval/rls_e2e.py` |
| Schema drift | 表结构变化自动报警 | `eval/schema_drift.py` |

### 6.3 可观测性

- 指标：模板命中率、空结果带提示率、编译失败率、RLS 拦截次数；
- 日志：在 `execute_scoped_query()` 统一记录查询计划 hash、命中模板 ID、注入的 RLS 谓词类型；
- 告警：schema drift 超过阈值、静态守卫 CI 失败。

---

## 七、风险与回滚策略

| 风险 | 影响 | 缓解/回滚 |
|---|---|---|
| 指标模板误匹配导致错误答案 | 高 | 首版只覆盖 obvious 聚合模板；保留 LLM 路径作为 fallback；模板命中结果需经 compiler 校验 |
| 停更表台账误杀活跃表 | 中 | 台账默认空，仅由画像+人工复核入库；支持白名单覆盖 |
| 统一执行入口引入性能瓶颈 | 中 | 入口只做薄包装，不重复解析 SQL；压测基线对比 |
| 静态守卫过严阻塞合理调用 | 中 | 守卫白名单机制；误报时允许标注例外并补充测试 |
| 本体建模成本过高客户不买账 | 高 | 严格保持可选性；先以指标库形式降低门槛，再升级为本体 |
| 查询代数编译器覆盖不足 | 中 | 明确只覆盖 80% 高频问法，长尾继续走 LLM 规划 |

---

## 八、里程碑与交付物

| 时间 | 里程碑 | 交付物 |
|---|---|---|
| 2 周 | MVP 可验证 | PR 合入：停更表过滤 + 澄清提示 + 1 个通用指标模板 + 统一入口骨架；3-5 个端到端用例 |
| 1 月 | 安全升级完成 | 指标库 20-50 模板、RLS 编译期注入、静态守卫 CI、 adversarial RLS 评测 |
| 1 季度 | 战略能力成型 | 查询代数编译器、可选 YAML 本体框架、schema drift 评测、客户建模指南 |

---

## 九、一句话执行建议

> **先拿 2 周把澄清提示和停更表过滤做出来，同时跑通第一个通用指标模板；这 3 件事不依赖本体建模，却立刻提升准确率和信任感。指标库跑顺后，再逐步硬化执行入口、加静态守卫，最后才是查询代数和可选本体——这样每一步都有独立价值，不会变成一场长期的架构重构。**

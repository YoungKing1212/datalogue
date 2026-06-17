# 分析蓝图 steps 字段形态盘点

> 生成时间：2026-06-16  
> 盘点脚本：`scripts/inventory_blueprint_steps.py`  
> 数据来源：本地 PostgreSQL 元数据库、`datalogue-api/tests/fixtures/phase5_analysis_blueprint_fixtures.jsonl`、`datalogue-api/tests/test_analysis_blueprint.py` 及 `datalogue-api/app/services/blueprint_analyzer.py` 的 AI 生成逻辑。

## 1. 数据源与样本量

| 来源 | 记录数 | 含 steps 的记录数 | step 总数 |
|------|--------|-------------------|-----------|
| `analysis_blueprint` 当前表 | 2 | 2 | 10 |
| `blueprint_version` 版本快照 | 2 | 2 | 10 |
| phase5 fixture | 25 | 3 | 3 |
| 测试 payload 样例 | 3 组 | 3 组 | 4 |
| **合计（去重按 step）** | - | - | **23** |

说明：
- 数据库中仅 2 条真实 blueprint，均处于 `active` 状态，分别对应 `sql_template` 与 `semantic_plan` 两种 `implementation_type`。
- fixture 中大多数场景未设置 steps，仅有 3 个 `semantic_plan` 相关 fixture 保留了极简的 `{"name": "..."}`。
- 测试 payload 样例来自 `test_analysis_blueprint.py`，代表 AI 生成/手工创建的期望结构，未计入脚本自动统计，但在字段说明中引用。

## 2. 观测到的 step 字段

所有 step 均为对象，目前未出现非对象 step。

| 字段 | 出现次数 / 总 step 数 | 出现率 | 空/空数组比例（在出现次数中） | 类型 | 说明 |
|------|----------------------|--------|------------------------------|------|------|
| `name` | 23 / 23 | 100% | 0% | `string` | 步骤标题，唯一全必填字段 |
| `step` | 20 / 23 | 87.0% | 0% | `integer` | 步骤序号（从 1 开始） |
| `purpose` | 20 / 23 | 87.0% | 0% | `string` | 步骤业务目的/说明 |
| `key_rules` | 20 / 23 | 87.0% | 0% | `string[]` | 关键规则/约束列表 |
| `output_columns` | 20 / 23 | 87.0% | 10.0% | `string[]` | 本步骤输出的列/指标列表，可能为空数组 |
| `confidence` | 20 / 23 | 87.0% | 0% | `number` | AI 对该步骤的置信度，0~1 浮点数 |

### 2.1 字段来源差异

- **数据库真实数据（含版本快照）**：`name`、`step`、`purpose`、`key_rules`、`output_columns`、`confidence` 全部出现，覆盖率 100%。其中 `output_columns` 有 10% 为空数组（供应商分级判定步骤无输出列）。
- **phase5 fixture**：仅有 `name` 字段，用于验证 `semantic_plan` 路线下的 blueprint_context 文本格式。
- **测试 payload 样例**：
  - `_ai_blueprint_payload()` 与重分析样例包含完整 6 字段。
  - `_manual_blueprint_payload()` 包含完整 6 字段。
  - `_blueprint_payload()` 的手工创建示例只包含 `step`、`name`、`key_rules`，缺少 `purpose`、`output_columns`、`confidence`。

## 3. 嵌套结构复杂度

| 指标 | 数值 |
|------|------|
| 平均每个 blueprint 的 step 数 | 5.0（真实数据：3 ~ 7） |
| 平均每个 step 的 `key_rules` 数量 | 3.3 |
| 单个 step 最大 `key_rules` 数量 | 4 |
| 平均每个 step 的 `output_columns` 数量 | 6.2 |
| 单个 step 最大 `output_columns` 数量 | 19 |

观察：
- `key_rules` 是短文本列表，适合渲染为 bullet list。
- `output_columns` 长度差异大，从 0 到 19 个，包含数据库列名、业务指标名、中文语义标签等。JSX 视图需要做截断/折叠处理。

## 4. 空值与字段漂移

### 4.1 空值情况

- `steps` 顶层数组：当前库中 2 条 blueprint 均为非空数组；fixture 中 22 条为 `[]` 或未设置。
- step 内部：
  - `output_columns` 可能为 `[]`（如分级判定步骤）。
  - 其他核心字段（`name`、`step`、`purpose`、`key_rules`、`confidence`）在真实数据中未见空值。

### 4.2 字段漂移 / 不一致

1. **字段完整性差异大**
   - AI 生成（SQL 分析 / 业务场景描述）通常输出完整 6 字段。
   - 手工创建/测试 payload 可能只提供 `step`、`name`、`key_rules`，缺少 `purpose`、`output_columns`、`confidence`。
   - fixture 中步骤退化到只剩 `name`。

2. **`step` 字段有时缺失**
   - `_blueprint_payload()` 手工示例为 `{"step": 1, "name": "订单汇总", "key_rules": [...]}`。
   - 但 `_manual_blueprint_payload()` 中 `step` 为 `1`。
   - 后端 `_sanitize_steps` 会在 `step` 缺失时用索引 `+1` 兜底，因此前端不应依赖 `step` 一定存在或严格连续。

3. **`output_columns` 语义不一致**
   - SQL 模板类 blueprint：多为数据库原始列名（如 `id`、`xmid`、`XMMC`、`dept_name`）。
   - semantic_plan 类 blueprint：多为中文业务语义标签（如 `供应商名称`、`综合评分`、`合同规模`），甚至出现 `筛选条件汇总` 这种非列名占位。
   - 前端渲染时不应假设其为真实数据库列，仅作“本步骤关注字段/输出”展示即可。

4. **`confidence` 类型与精度**
   - 真实数据中均为 0~1 浮点数，保留 2 位小数。
   - 缺失时后端会保留 `None` 或 fallback 值，前端可做灰度/标签展示或隐藏。

5. **步骤名长度差异**
   - 短标题：如 `订单汇总`。
   - 长标题：如 `识别评估范围与筛选条件`、`供应商综合评估与分级排名`。
   - JSX 视图应做宽度自适应，避免折行混乱。

## 5. 对 JSX 视图（T1）的渲染建议

基于上述盘点，建议 JSX 步骤视图优先渲染以下字段，并按优先级分层：

### 5.1 必渲染字段

| 字段 | 渲染方式 | 理由 |
|------|----------|------|
| `name` | 步骤标题，可带序号徽章 | 唯一 100% 存在的字段，用户最关注 |
| `step` | 序号徽章（若缺失则按数组索引 +1 兜底） | 帮助用户理解流程顺序 |
| `purpose` | 折叠/展开描述或 tooltip | 解释该步骤业务含义，87% 存在 |

### 5.2 推荐渲染字段

| 字段 | 渲染方式 | 理由 |
|------|----------|------|
| `key_rules` | 规则标签或无序列表 | 业务约束高频出现，平均 3.3 条，适合快速浏览 |
| `output_columns` | 字段标签云 / 可折叠列表 | 输出字段重要，但数量差异大（0~19），需要截断/折叠 |
| `confidence` | 进度条或低置信度警告标 | 人工审核场景需要识别不确定步骤 |

### 5.3 降级与兼容性处理

- 当 `purpose` 缺失时：仅展示标题 + 规则列表，不预留空白描述区。
- 当 `key_rules` 缺失时：隐藏规则区域。
- 当 `output_columns` 为空数组 `[]` 时：显示“无输出列”占位，避免空白。
- 当 `confidence` 缺失时：不显示置信度，避免 NaN。
- 当整个 `steps` 为空数组 `[]` 时：显示“暂无业务步骤”空状态，并提供编辑入口。
- 当 step 对象缺少 `step` 序号时：使用数组索引 +1 作为展示序号。

### 5.4 不建议渲染的内容

- 不应把 `output_columns` 当作可点击的列名或用于生成 SQL，因为它可能是中文语义标签或占位文本。
- 不建议把 `key_rules` 文本做关键词高亮，除非有明确业务词表，否则容易误伤。

## 6. 典型真实数据示例

### 6.1 sql_template 蓝图步骤（3 步）

```json
[
  {
    "step": 1,
    "name": "主表筛选与状态过滤",
    "purpose": "从计划任务日报主表中按人员姓名和日志日期区间裁剪数据，并排除已作废记录",
    "key_rules": [
      "主表为 plan_task_daily_record",
      "日志日期在用户指定的起止日期区间内",
      "状态不为作废值（排除 zt = '2' 且 zt 非空）",
      "人员姓名通过 LEFT JOIN 关联员工档案后过滤"
    ],
    "output_columns": ["id", "xmid", "detailid", "cjsj", "gs", "jhgznr", "jtgznr", "shyj", "rzrq", "xgr", "xgsh", "jt", "zt", "wcbfb", "rzbz", "account", "deptcode"],
    "confidence": 0.9
  },
  {
    "step": 2,
    "name": "维度信息补全",
    "purpose": "通过三张维度表补全人员姓名、项目名称和部门名称等业务可读信息",
    "key_rules": [
      "sys_dept 通过 dept_id 关联 deptcode 获取 dept_name",
      "project_manager 通过 XMID 关联 xmid 获取 XMMC（项目名称）",
      "全部使用 LEFT JOIN，允许维度缺失时仍返回主表记录"
    ],
    "output_columns": ["XMMC", "dept_name"],
    "confidence": 0.92
  },
  {
    "step": 3,
    "name": "结果排序与裁剪",
    "purpose": "按日志日期倒序输出最近的一百条日报明细",
    "key_rules": [
      "按日志日期降序排序，最近的日报排在最前",
      "LIMIT 100 控制返回条数，防止明细过大"
    ],
    "output_columns": ["id", "xmid", "XMMC", "detailid", "cjsj", "gs", "jhgznr", "jtgznr", "shyj", "rzrq", "xgr", "xgsh", "jt", "zt", "wcbfb", "rzbz", "account", "deptcode", "dept_name"],
    "confidence": 0.88
  }
]
```

### 6.2 semantic_plan 蓝图步骤（7 步，节选）

```json
[
  {
    "step": 1,
    "name": "识别评估范围与筛选条件",
    "purpose": "从用户问句中提取时间范围、供应商类别、评分阈值等业务约束，明确评估数据集的边界",
    "key_rules": [
      "优先采用用户显式指定的时间窗口，未指定时默认最近一个完整评估周期",
      "供应商类别未指定时默认全部合格供应商",
      "支持多筛选条件组合"
    ],
    "output_columns": ["筛选条件汇总"],
    "confidence": 0.85
  },
  {
    "step": 5,
    "name": "供应商分级判定",
    "purpose": "根据综合评分划分供应商等级，例如A/B/C/D级或战略/核心/合格/观察级",
    "key_rules": [
      "分级阈值由公司采购政策或供应商管理办法规定",
      "边界值采用向上取整规则",
      "支持业务自定义临时分级",
      "同一供应商等级在统计周期内保持稳定，避免频繁变动"
    ],
    "output_columns": [],
    "confidence": 0.7
  }
]
```

## 7. 结论

- `blueprint.steps` 当前是结构相对稳定的对象数组，核心字段 6 个，以自然语言描述和字段清单为主。
- 真实数据样本虽少（2 条 blueprint / 20 个 step），但已覆盖 SQL 模板与语义计划两种类型，字段形态差异明显。
- JSX 视图应以 `name` + `step` 为骨架，`purpose` 为展开说明，`key_rules` 与 `output_columns` 为补充卡片，`confidence` 为可选置信标识，并对字段缺失/空数组/序号缺失做兼容。
- 后续随着 AI 生成与手工编辑并行，建议在前端加入 schema lint 或步骤完整性提示，减少 `purpose`、`confidence` 等字段的漂移。

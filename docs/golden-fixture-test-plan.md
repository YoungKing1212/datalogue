# LeadAgent Progressive Assets 功能开关等价性测试计划

> 目标：验证 `LEAD_AGENT_PLANNER_USE_PROJECTION` 开关在关闭状态下（默认行为）与开启状态在“非渐进式资产路径”上的可观测输出等价。
>
> 背景：Codex 外部审查指出，功能开关的 default-off 场景不仅仅是“使用原始列表”——任何内部分支（如日志字段、metadata、错误路径、字段顺序、默认列表复制）都可能产生差异。本计划定义如何通过 Golden Fixture 测试捕获这些差异。

---

## 1. Fixture 来源

### 1.1 主要来源：Phase 5 Fixture 捕获脚本

复用 `datalogue-api/scripts/capture_phase5_fixtures.py` 的 fixture 构造模式，但针对 **LeadAgent Planner** 场景重新设计：

| 来源 | 说明 | 数量建议 |
|------|------|----------|
| `capture_phase5_fixtures.py` 的 in-memory DB 构造模式 | 复用 `_make_db_and_dataset` + `_make_blueprint` 构造最小可运行环境 | 核心基础设施 |
| 手工构造的 `conversation_summary` 场景 | 覆盖多轮上下文、数据集锁定、payload 选择等状态 | 15-20 条 |
| 真实对话日志采样（脱敏后） | 从生产/测试环境抽取典型 `question` + `conversation_summary` 组合 | 5-10 条 |
| 边界条件 | 空 conversation、无锁定数据集、schema stale、fallback 触发等 | 5-8 条 |

### 1.2 Fixture 结构

每条 fixture 包含：

```json
{
  "name": "fixture_case_name",
  "description": "测试场景描述",
  "input": {
    "question": "用户问题",
    "conversation_summary": {},
    "tool_policy": {},
    "skills": []
  },
  "expected_output_shape": {
    "selected_skills": [],
    "tool_calls": [],
    "reasoning_summary": "",
    "planner_fallback": false,
    "fallback_reason": null
  }
}
```

### 1.3 Fixture 生成脚本位置

建议新建 `datalogue-api/scripts/capture_lead_agent_planner_fixtures.py`，复用 `capture_phase5_fixtures.py` 的 `_make_db_and_dataset` 模式，但调用 `plan_tool_calls_with_llm` 捕获输出。

---

## 2. 输出比较面

### 2.1 必须比较的字段（核心业务语义）

| 字段 | 比较方式 | 说明 |
|------|----------|------|
| `selected_skills` | 列表元素顺序无关比较 | Skill 选择结果必须一致 |
| `tool_calls` | 按 `tool` 名称 + `reason` 语义比较 | 工具计划必须一致 |
| `reasoning_summary` | 语义等价（非字符串精确匹配） | LLM 生成的 reasoning 可能有措辞差异，但业务结论必须一致 |
| `planner_fallback` | 布尔精确匹配 | 是否触发降级计划 |
| `fallback_reason` | 精确匹配（若不为 null） | 降级原因必须一致 |
| `planner_source` | 精确匹配 | `deterministic` / `llm` / `fallback` |
| `fast_path_hit` | 布尔精确匹配 | 是否命中确定性快路径 |
| `llm_skipped_reason` | 精确匹配 | LLM 被跳过原因 |
| `disclosed_tools` | 列表元素顺序无关比较 | 披露的工具列表 |
| `skill_selection_reasoning_summary` | 语义等价 | Skill 选择阶段 reasoning |
| `tool_planning_reasoning_summary` | 语义等价 | Tool 规划阶段 reasoning |

### 2.2 建议比较的字段（元数据一致性）

| 字段 | 比较方式 | 说明 |
|------|----------|------|
| `progressive_disclosure` | 布尔精确匹配 | 是否启用渐进式披露 |
| `disclosure_stage` | 精确匹配 | `skill_selection` / `tool_planning` |
| `projection_enabled` | 布尔精确匹配 | 投影是否启用（开关本身） |
| `projection_schema_version` | 精确匹配 | 投影契约版本 |
| `projection_metrics` | 结构比较（若启用） | 字符量指标 |

### 2.3 不比较的字段（允许差异）

| 字段 | 允许差异原因 |
|------|--------------|
| `trace_id` / `generation_id` | 每次调用独立生成 |
| `timestamp` / `created_at` | 执行时间不同 |
| `raw_response` / `raw_content` | LLM 原始输出可能有 token 级差异 |
| `usage_metadata` / `token_count` | 投影开启后 prompt 长度不同，token 消耗必然不同 |
| `prompt_version` / `prompt_source` | 可能因投影版本不同 |
| `metadata` 中的历史 Trace / 观测系统特定字段 | 观测系统内部字段，当前运行时不应作为等价性判定依据 |
| `input_payload` 的原始长度 | 投影开启后输入被截断 |

---

## 3. 比较方法

### 3.1 语义映射规则

非字节级比较，采用以下语义映射：

1. **列表比较**：`selected_skills` 和 `disclosed_tools` 使用集合比较（`set(a) == set(b)`），忽略顺序。
2. **工具调用比较**：`tool_calls` 按 `tool` 名称分组，比较每组的数量和 `reason` 的语义等价性。
3. **Reasoning 比较**：使用关键词覆盖检查——`reasoning_summary` 必须包含相同的业务决策关键词（如 `subagent_dispatch`, `manifest_router`, `clarification` 等），允许连接词和句式差异。
4. **嵌套结构比较**：`route_decision` 等嵌套对象比较其 `decision` 字段和 `effective_dataset_id`，忽略内部临时字段。
5. **空值等价**：`null`, `None`, `[]`, `""` 在语义上视为不同，必须精确匹配预期类型。

### 3.2 比较辅助函数设计

```python
# 建议提取的辅助函数（伪代码）
def assert_planner_outputs_equivalent(off_plan: dict, on_plan: dict, fixture_name: str):
    """
    比较开关关闭/开启两种模式下的 Planner 输出。

    语义等价规则：
    - selected_skills: 集合比较
    - tool_calls: 按 tool 名称分组，比较数量和 reason 语义
    - reasoning_summary: 关键词覆盖检查
    - fallback 相关字段: 精确匹配
    - 允许差异: trace_id, timestamp, token_count, raw_response
    """
    ...
```

---

## 4. 允许的差异（Tolerated Differences）

### 4.1 观测系统字段

- 历史 Trace `trace_id`, `generation_id`, `span_id`
- `timestamp`, `created_at`, `updated_at`
- `metadata` 中任何以 `_` 开头的内部字段

### 4.2 LLM 调用层字段

- `raw_response` / `raw_content` 的字符串精确值（只要解析后的结构化输出一致）
- `usage_metadata` 中的 `input_tokens`, `output_tokens`, `total_tokens`
- `model_name` 若因路由策略不同

### 4.3 投影相关字段（仅当开关开启时存在）

- `projection_metrics` 整体（开关关闭时该字段不存在）
- `projection_saved_chars`（开关关闭时无意义）
- `input_payload` 中的 `recent_context` 截断后长度

### 4.4 日志字段

- 日志消息中的时间戳
- 日志消息中的内存地址或对象 ID
- `logger.debug` 级别的详细 payload（可能因投影截断而不同）

---

## 5. 失败阈值

### 5.1 总体阈值

- **通过标准**：≥ 95% 的 fixture 通过语义等价比较。
- **警告标准**：90% - 95% 通过，需人工审查差异 fixture。
- **失败标准**：< 90% 通过，阻塞合入。

### 5.2 分类阈值

| Fixture 类别 | 最低通过要求 | 说明 |
|--------------|-------------|------|
| 确定性快路径 | 100% | 快路径不应受开关影响 |
| Fallback 触发 | 100% | 降级路径必须一致 |
| 正常 LLM 规划 | 95% | 允许少量 LLM 随机性导致的差异 |
| 边界条件 | 90% | 复杂边界可能因投影截断产生合理差异 |

### 5.3 差异审查流程

1. 自动收集所有差异 fixture 的差异字段。
2. 按差异类型分类：`skill_selection_diff`, `tool_plan_diff`, `reasoning_diff`, `fallback_diff`。
3. 人工审查差异是否在“允许差异”列表内。
4. 若差异超出允许范围，记录为 bug 并修复。

---

## 6. 测试文件位置

### 6.1 主测试文件

```
datalogue-api/tests/test_lead_agent_progressive_assets.py
```

### 6.2 核心测试函数

```python
def test_progressive_assets_flag_off_matches_legacy():
    """
    验证 LEAD_AGENT_PLANNER_USE_PROJECTION=False 时，
    plan_tool_calls_with_llm 的输出与未引入投影前的行为等价。

    测试策略：
    1. 加载 golden fixtures（JSONL 格式）
    2. 对每个 fixture，分别调用 plan_tool_calls_with_llm（mock LLM）
    3. 比较输出是否语义等价
    4. 统计通过率，应用失败阈值
    """
    ...


def test_progressive_assets_flag_on_matches_legacy_for_non_asset_paths():
    """
    验证 LEAD_AGENT_PLANNER_USE_PROJECTION=True 时，
    在"非渐进式资产路径"（无锁定数据集 / 无候选资产召回）上，
    输出与关闭状态语义等价。
    """
    ...
```

### 6.3 Fixture 文件位置

```
datalogue-api/tests/fixtures/lead_agent_planner_fixtures.jsonl
```

---

## 7. 辅助工具提取

### 7.1 `assert_planner_outputs_equivalent(off_plan, on_plan, fixture_name)`

位置：`datalogue-api/tests/helpers/planner_equivalence.py`

职责：
- 比较两个 Planner 输出的语义等价性
- 生成结构化差异报告
- 支持忽略允许差异字段

### 7.2 `load_golden_fixtures(path)`

位置：`datalogue-api/tests/helpers/golden_fixtures.py`

职责：
- 加载 JSONL fixture 文件
- 验证 fixture 结构完整性
- 支持按标签过滤（`fast_path`, `fallback`, `normal`, `boundary`）

### 7.3 `mock_llm_with_fixture_response(fixture)`

位置：`datalogue-api/tests/helpers/mock_llm.py`

职责：
- 根据 fixture 中记录的 `expected_output` 构造 mock LLM 响应
- 确保开关两种模式下 LLM 返回相同结构化输出（排除 LLM 随机性干扰）
- 支持 deterministic 快路径绕过 LLM 的场景

### 7.4 `build_projection_recent_context_for_test(conversation_summary, tool_policy)`

位置：`datalogue-api/tests/helpers/projection_context.py`

职责：
- 为测试构造标准化的 `projection_recent_context`
- 确保测试用例的 context 构造与生产代码一致

---

## 8. 实施顺序

1. **Step 1**：编写 `capture_lead_agent_planner_fixtures.py` 捕获 20-30 条 fixture。
2. **Step 2**：提取 `assert_planner_outputs_equivalent` 和 `load_golden_fixtures` 辅助函数。
3. **Step 3**：编写 `test_progressive_assets_flag_off_matches_legacy`，验证关闭状态下的自洽性。
4. **Step 4**：编写 `test_progressive_assets_flag_on_matches_legacy_for_non_asset_paths`，验证开启状态在非资产路径上的等价性。
5. **Step 5**：运行测试，统计通过率，调整阈值。
6. **Step 6**：将测试纳入 CI，作为 `lead_agent_planner_projection.py` 变更的守门测试。

---

## 9. 风险与注意事项

1. **LLM 随机性**：测试中必须 mock LLM，否则两次调用结果本身就会不同，无法归因于开关差异。
2. **Prompt 版本差异**：若开关开启后使用了不同的 prompt 版本，需在测试中固定 prompt 版本。
3. **投影截断边界**：`DEFAULT_MAX_TEXT_CHARS` 等截断参数可能导致边界 fixture 产生差异，需在允许差异中明确。
4. **新字段注入**：开关开启后可能注入 `projection_schema_version` 等新字段，比较时应忽略这些字段的存在性差异（只比较业务字段）。
5. **日志字段差异**：`logger.info` 中的 `projection_enabled` 等字段可能不同，但属于观测差异，不影响业务等价性。

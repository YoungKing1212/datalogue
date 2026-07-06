# Agentic Lead Agent + BI Worker 渐进式上下文设计规格

## 1. 背景

当前 Agent Team 链路里，`Agentic Lead Agent` 负责控制面，`BI Worker` 负责问数任务。但已确认 `dataset_id` 后，BI Worker 现在更像调用 `datalogue_query_dataset` 的工具转发器：timeline 只显示一次查询工具调用，内部资产匹配、字段口径判断、查询计划、执行修复和 artifact 生成不够可观测，也没有体现 BI Worker 的问数推理职责。

本设计把目标架构收敛为：

```text
Agentic Lead Agent
  -> BI Worker
      -> 固定骨架：L0 / L1 / L5
      -> 按需上下文：L2 / L3
      -> 强制门禁：L4
      -> TeamSay 安全结果
```

设计目标不是重新引入 DatasetAgent 作为目标架构角色，而是让 BI Worker 成为真正的问数执行智能体。

## 2. 设计目标

- 保留 `Agentic Lead Agent + BI Worker` 架构主语。
- 已确认数据集后，BI Worker 在数据集内完成受控问数推理。
- BI Worker 可以按需申请上下文切片，并生成结构化 Query Plan JSON。
- BI Worker 不生成 SQL、不执行 SQL、不读取 raw rows。
- runtime 负责 schema 切片、值域画像、强制校验、SQL 编译、执行、修复、artifact/checkpoint。
- 用户可见层只展示最终回答、结果卡和安全业务步骤，不暴露 SQL、raw rows、完整 schema、内部 query plan 或 repair patch。

## 3. 非目标

- 不引入 DatasetAgent 作为新的目标架构角色。
- 不让 Agentic Lead Agent 读取 schema、SQL、raw rows 或 Query Plan JSON。
- 不让 BI Worker 获取完整 schema 或直接写 SQL。
- 不要求用户在数据集已确认后再次确认每个 Query Plan。
- 不在本设计中实现多数据集自动 fan-out。

## 4. 角色职责

### 4.1 Agentic Lead Agent

控制面角色：

- 理解用户任务。
- 在缺少 `dataset_id` 时调度 BI Worker 生成候选数据集。
- 在用户确认数据集后，将已确认问题交给 BI Worker 执行。
- 汇总 BI Worker 的安全结果。

禁止事项：

- 不读取 schema、SQL、raw rows、Query Plan JSON。
- 不直接执行查询。
- 不把 BI Worker 内部上下文写入用户回答。

### 4.2 BI Worker

问数执行智能体：

- 使用 L0/L1 固定骨架理解数据集能力和候选资产。
- 按需申请 L2 schema/关系切片和 L3 值域画像。
- L2 中可以看到相关真实表名和真实物理字段名。
- 生成结构化 Query Plan JSON。
- 根据 runtime 返回的校验/修复请求调整 Query Plan。
- 通过 TeamSay 回传安全结果、澄清问题或不支持原因。

禁止事项：

- 不生成 SQL。
- 不执行 SQL。
- 不读取 raw rows。
- 不自由发明 join 条件。
- 不通过 TeamSay 或最终回答暴露字段名、schema、Query Plan JSON、SQL 或 raw rows。

### 4.3 BI Worker Runtime

执行面和安全边界：

- 提供 L0/L1/L2/L3 上下文工具。
- 在 L5 执行前强制运行 L4 支持度校验。
- 校验字段白名单、权限、可过滤性、join 合法性、粒度、语义依赖。
- 编译 SQL、执行查询、执行确定性修复、生成 artifact/checkpoint。
- 捕获数据库原始错误并转换为安全 repair request。

## 5. 渐进式上下文披露

### L0 数据集能力摘要

固定骨架步骤。

目的：判断当前数据集大方向是否匹配用户问题。

允许返回：

- 数据集名称。
- 业务域。
- 可回答问题类型。
- 关键指标和维度摘要。

禁止返回：

- 表名。
- 字段名。
- SQL。
- raw rows。
- 完整 schema。

### L1 候选资产摘要

固定骨架步骤。

目的：让 BI Worker 知道当前问题命中了哪些业务资产。

允许返回：

- 候选指标、维度、术语、字段、蓝图的业务名称和描述。
- asset_ref。
- 安全的业务匹配理由。

禁止返回：

- 完整 schema。
- SQL。
- raw rows。

### L2 相关 schema/关系切片

按需步骤。

目的：当 L1 不足以判断字段口径、join 路径或展示语义时，返回最小必要 schema 和关系切片。

允许返回：

- 相关表名。
- 真实物理字段名。
- 字段业务名。
- 字段类型。
- 是否可过滤、可排序、可聚合。
- join key 标记。
- relationship_ref。
- join 允许类型。
- 关系业务含义。

限制：

- 只返回与当前问题相关的最小切片。
- 不返回全量 schema。
- L2 内容只允许进入 BI Worker 工作上下文、工具入参和审计 trace，不进入 TeamSay 或用户可见回答。

### L3 值域/覆盖度画像

按需步骤。

目的：验证字段是否覆盖用户问题里的实体、年份、枚举、范围等。

允许返回：

- 某字段是否包含目标实体。
- 日期范围是否覆盖目标时间。
- 枚举值是否存在目标状态。
- 覆盖度、计数、分布摘要。

禁止返回：

- raw rows。
- 明细样例行。
- 原始查询结果。

### L4 查询支持度验证

强制门禁。

BI Worker 可以主动调用 L4 做预检，但即使没有主动调用，`datalogue_execute_query_plan` 内部也必须在执行前强制运行 L4。

支持状态：

```text
supported
needs_more_context
needs_clarification
unsupported
```

L4 必须校验：

- 字段存在性。
- 字段权限和可过滤性。
- join 路径合法性。
- 明细/聚合粒度。
- 重复行风险。
- lookup/dictionary/display 语义依赖。
- Query Plan 是否只引用 L1/L2 返回过的 asset_ref 和 relationship_ref。

### L5 受控执行与产物

固定骨架步骤。

目的：runtime 接收 Query Plan JSON，完成 SQL 编译、执行、修复、artifact/checkpoint 生成。

允许返回：

- answer_summary。
- artifact_ref。
- checkpoint_ref。
- row_count。
- column_count。
- artifact_card。
- 安全失败摘要。

禁止返回：

- SQL。
- raw rows。
- 完整 schema。
- 内部 repair patch。
- 数据库原始错误。

## 6. BI Worker 工具面

固定骨架工具：

```text
datalogue_describe_dataset_capability
datalogue_recall_query_assets
datalogue_execute_query_plan
```

按需上下文工具：

```text
datalogue_request_schema_slice
datalogue_profile_candidate_values
datalogue_validate_query_support
```

`datalogue_execute_query_plan` 必须在内部调用 `datalogue_validate_query_support` 或同等 runtime 校验逻辑。校验未通过时不得执行 SQL。

## 7. 状态机

默认骨架：

```text
START
  -> L0 describe_dataset_capability
  -> L1 recall_query_assets
  -> BI Worker draft Query Plan
  -> L5 execute_query_plan
  -> TeamSay result
  -> DONE
```

按需上下文：

```text
L2 request_schema_slice
  当 L1 资产摘要不足以判断字段口径、join 路径或展示语义时调用。

L3 profile_candidate_values
  当需要验证实体、年份、枚举、覆盖范围时调用。

L4 validate_query_support
  BI Worker 可主动预检；runtime 在 L5 前强制校验。
```

执行分支：

```text
supported
  -> 自动执行

needs_more_context
  -> BI Worker 申请 L2/L3

needs_clarification
  -> TeamSay 澄清问题给 Agentic Lead Agent / 用户

unsupported
  -> TeamSay 无法回答原因和治理缺口
```

## 8. Query Plan v1

Query Plan v1 是关系图计划，不是单表字段列表。

顶层结构：

```text
intent
question
result_shape
data_graph
join_requirements
filters
selects
metrics
group_by
ordering
assumptions
```

明细查询要求：

- `intent = detail_query`。
- 必须声明 `result_shape.grain`。
- selects 必须引用 L1/L2 中的 asset_ref。
- ordering 字段必须可排序。

指标查询要求：

- `intent = metric_query`。
- 必须声明 metrics、group_by 和 aggregation grain。
- metrics 必须来自 L1/L2 候选指标或 runtime 可验证的派生指标。

多表规则：

- BI Worker 可以表达 join requirement。
- join 必须引用 L2 返回的 relationship_ref。
- BI Worker 不能自己写 left_field = right_field。
- 所有字段必须来自 L1/L2 返回的 asset_ref。
- 多表 join 路径必须是 runtime 可解析的合法关系图。
- 明细查询必须声明 result grain，避免 join 后重复行不可控。
- 聚合查询必须声明 metrics、group_by 和 aggregation grain。

示例结构：

```json
{
  "intent": "detail_query",
  "question": "查询杨凯2025年工作日志",
  "result_shape": {
    "type": "table",
    "grain": "one_row_per_work_log",
    "limit": 100
  },
  "data_graph": {
    "primary_entity": {
      "asset_ref": "asset:work_log",
      "alias": "log",
      "role": "fact_or_primary"
    },
    "supporting_entities": [
      {
        "asset_ref": "asset:employee",
        "alias": "emp",
        "role": "dimension",
        "join_purpose": "把人员名称映射到日志记录"
      }
    ]
  },
  "join_requirements": [
    {
      "left_alias": "log",
      "right_alias": "emp",
      "relationship_ref": "rel:work_log_employee",
      "join_type": "inner",
      "required": true,
      "reason": "用户按人员姓名过滤日志"
    }
  ],
  "filters": [
    {
      "target": {
        "asset_ref": "asset:employee.name",
        "alias": "emp",
        "field": "employee_name"
      },
      "operator": "=",
      "value": "杨凯",
      "reason": "用户指定人员"
    },
    {
      "target": {
        "asset_ref": "asset:work_log.work_date",
        "alias": "log",
        "field": "work_date"
      },
      "operator": "between",
      "value": ["2025-01-01", "2025-12-31"],
      "reason": "用户指定年份"
    }
  ],
  "selects": [
    {
      "target": {
        "asset_ref": "asset:work_log.work_date",
        "alias": "log",
        "field": "work_date"
      },
      "display_name": "工作日期"
    },
    {
      "target": {
        "asset_ref": "asset:work_log.content",
        "alias": "log",
        "field": "log_content"
      },
      "display_name": "工作日志"
    }
  ],
  "ordering": [
    {
      "target": {
        "asset_ref": "asset:work_log.work_date",
        "alias": "log",
        "field": "work_date"
      },
      "direction": "asc"
    }
  ],
  "assumptions": [
    "工作日志以日志记录为结果粒度",
    "人员名称通过员工维表过滤"
  ]
}
```

## 9. 语义依赖补全

L4 必须检查三类语义依赖：

```text
lookup_dependency
  编码转名称，例如 dept_code -> department_name。

dictionary_dependency
  枚举或码表翻译，例如 status=1 -> 已完成。

semantic_display_dependency
  用户要看的业务展示字段和底层存储字段不是同一个字段。
```

规则：

- 如果依赖唯一、可信、已在 manifest/关系图里声明，runtime 可以自动补全关系和展示字段，并记录 `auto_context_expansions`。
- 如果存在多个候选依赖，runtime 返回 `needs_more_context`，让 BI Worker 申请更聚焦的 L2/L3；仍不能确定时返回 `needs_clarification`。
- 如果没有可用依赖，runtime 返回 `unsupported`，提示需要补充字段标注、关系配置或码表治理。
- BI Worker 不能自己发明 lookup join。所有 lookup、dictionary、display dependency 都必须来自 runtime 返回的关系图或校验补全结果。

示例：

```json
{
  "support_status": "needs_more_context",
  "missing_context": [
    {
      "type": "lookup_dependency",
      "code_field": "employee.dept",
      "business_meaning": "部门编码需要转换为部门名称",
      "recommended_next_tool": "datalogue_request_schema_slice",
      "focus": {
        "lookup_for": "employee.dept",
        "target_semantic": "department_name"
      }
    }
  ],
  "safe_reason": "当前计划使用部门编码字段，但用户可见结果需要部门名称。需要补充部门维表或码值字典切片。"
}
```

自动补全示例：

```json
{
  "support_status": "supported",
  "auto_context_expansions": [
    {
      "type": "lookup_dependency",
      "source_field": "employee.dept",
      "added_relationship_ref": "rel:employee_department",
      "added_display_field": "department.dept_name",
      "reason": "部门编码字段需要转换为部门名称"
    }
  ]
}
```

## 10. 修复节点

修复分两层：

```text
runtime deterministic repair
  确定性修复，由规则、编译器、字段映射、关系图完成。

BI Worker assisted repair
  LLM 辅助修复，由 BI Worker 基于安全错误摘要和上下文切片修正 Query Plan JSON。
```

边界：

- SQL 修复由 runtime 做。
- Query Plan 修复可由 BI Worker 参与。
- BI Worker 不看 SQL、不改 SQL、不看 raw rows。

修复流程：

```text
datalogue_execute_query_plan
  -> runtime validate
  -> runtime compile
  -> runtime execute

如果失败：
  -> deterministic repair 尝试一次
  -> 仍失败且错误可安全抽象
  -> 返回 repair_request 给 BI Worker
  -> BI Worker 申请 L2/L3 或修正 Query Plan JSON
  -> 再次提交 execute_query_plan
```

repair_request 示例：

```json
{
  "repair_status": "needs_plan_revision",
  "failure_stage": "validate",
  "failure_class": "ambiguous_field",
  "safe_reason": "当前计划中的人员过滤字段无法唯一匹配，需要在候选人员字段中重新选择。",
  "recommended_action": "request_schema_slice",
  "missing_context": [
    {
      "type": "ambiguous_field",
      "business_meaning": "人员",
      "candidates_ref": "context:person-field-candidates"
    }
  ]
}
```

## 11. 执行期数据库错误

数据库原始错误只进入 runtime 内部日志和审计，不直接进入 BI Worker 上下文。

当执行期出现表名缺失、字段缺失、方言错误等数据库错误时：

```text
数据库原始错误
  -> runtime 捕获
  -> error sanitizer 清洗
  -> runtime deterministic diagnosis
  -> 能自动修则自动修并重试一次
  -> 不能自动修则返回安全 repair_request
```

runtime 自诊断检查：

- SQL 中表名是否来自 L2 schema/relationship_ref 编译结果。
- 表名是否存在 schema 前缀、大小写、引号或方言问题。
- 表是否在 datasource introspection 中存在。
- manifest/schema cache 是否过期。
- relationship_ref 是否指向已删除或改名的表。
- 物理表名是否需要 `schema_name.table_name` 前缀。

安全 repair_request 示例：

```json
{
  "repair_status": "needs_plan_revision",
  "failure_stage": "execute",
  "failure_class": "table_not_found",
  "safe_reason": "执行时发现部门 lookup 依赖的物理表不可用，需要重新选择可用的部门关系或返回无法支持。",
  "affected_dependency": {
    "type": "lookup_dependency",
    "business_meaning": "部门名称",
    "relationship_ref": "rel:employee_department"
  },
  "recommended_action": "request_schema_slice",
  "missing_context": [
    {
      "type": "alternative_lookup_relation",
      "focus": "department lookup for employee.dept"
    }
  ]
}
```

处理规则：

- 可确定的物理映射问题：runtime 自动修复并重试一次。
- 不可确定但有候选上下文：返回 safe repair_request，BI Worker 申请 L2/L3 并修 Query Plan。
- 确实缺表或治理缺失：返回 unsupported 或 failed，并输出治理缺口。

## 12. 循环与重试上限

临时上限：

```text
L2 schema slice 最多 2 次。
L3 value profile 最多 2 次。
validate needs_more_context 最多 2 回合。
runtime deterministic repair 最多 1 次。
BI Worker plan repair 最多 1 次。
同一个 missing_context 不得重复申请。
超过后必须转为 needs_clarification、unsupported 或 failed。
```

这些上限用于第一阶段稳定性控制，后续可以根据真实 trace 调整。

## 13. 展示分层

聊天区：

- 最终回答。
- 结果卡。
- 必要澄清。

普通 timeline：

- 任务理解。
- 数据集确认。
- 数据资产匹配。
- 查询口径判断。
- 查询执行。
- 结果产物。

Workbench / 调试 trace：

- L1/L2/L3/L4 安全摘要。
- auto_context_expansions。
- support_status。
- repair_request 安全摘要。
- artifact_ref。

始终不展示：

- SQL。
- raw rows。
- 完整 schema。
- 内部 Query Plan JSON。
- 内部 repair patch。
- 数据库原始错误。

## 14. 验收标准

- 没有 `dataset_id` 时，BI Worker 仍先返回候选数据集确认。
- 已有 `dataset_id` 时，BI Worker 进入 L0/L1/L5 固定骨架。
- 简单查询可不申请 L2/L3，但 L5 前必须经过 L4 强制校验。
- 字段口径不充分时，BI Worker 可申请 L2。
- 实体/时间/枚举覆盖不确定时，BI Worker 可申请 L3。
- 多表查询必须通过 relationship_ref 表达 join，不允许自由 join 条件。
- 编码转名称、码表翻译、展示语义依赖必须被 L4 发现、补全或阻断。
- 执行期数据库错误必须被 sanitizer 转成安全 repair_request 或失败摘要。
- BI Worker 不输出 SQL、raw rows、完整 schema、Query Plan JSON 或数据库原始错误。
- 最终结果仍通过 artifact_ref/result_ref/artifact_card 展示。

## 15. 后续实施顺序

1. 定义 Query Plan v1、context slice、support validation、repair request 的 schema。
2. 抽象 BI Worker query runtime，保留现有 direct query 作为 fallback。
3. 实现 L0/L1 固定骨架工具。
4. 实现 L2/L3 按需上下文工具。
5. 实现 L4 强制门禁和语义依赖补全。
6. 实现 L5 execute query plan，并接入 artifact_card 输出。
7. 改造 BI Worker prompt，让它按固定骨架和按需上下文工作。
8. 补 timeline / Workbench 安全 trace 投影。
9. 补测试和真实链路验收。

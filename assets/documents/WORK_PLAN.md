# 数语 Datalogue — 开发工作计划

> 基于《数语 Datalogue AI 原生智能问数平台 设计开发方案 v1.0》生成
> 生成日期：2026/05/28

---

## 一、项目概述

**数语（Datalogue）** 是面向中大型企业的 AI 原生智能问数平台。核心能力是将自然语言问题转换为 SQL/Python 分析并生成可视化报告，让业务人员无需编写代码即可自助获取数据洞察。

### 差异化亮点
- **语义层（Semantic Layer）**：业务指标与维度建模，显著提升 NL2SQL 准确率
- **多步骤 Agent**：基于 LangGraph 的计划-执行-修正-报告完整链路
- **人工反馈机制**：关键节点支持业务人员确认和干预

### 技术栈总表

| 层次 | 选型 | 说明 |
|------|------|------|
| AI 工作流 | LangGraph (Python) | 有状态图结构，支持持久化、中断恢复、流式输出 |
| API 服务 | FastAPI (Python) | 异步高性能，自动生成 OpenAPI 文档 |
| 前端 | React 18 + Vite + TypeScript | 已完成 MVP 搭建 |
| 元数据 DB | PostgreSQL + pgvector | 语义层模型、对话历史、Schema embedding |
| LLM 接入 | Claude / GPT-4o / Qwen | 兼容 OpenAI 接口，支持运行时切换 |
| Python 执行 | Docker 沙箱 | 隔离安全，预装 Pandas/NumPy/Matplotlib |
| 可观测性 | Langfuse | Prompt 跟踪、Token 费用监控 |

---

## 二、系统架构

### 2.1 五层架构

```
展示层  →  React 18 前端 + 管理后台
API 层  →  FastAPI + SSE 流式推送
Agent 层 → LangGraph StateGraph（NL2DSL2SQL）
语义层  →  指标/维度建模、Schema embedding
数据层  →  PostgreSQL 元数据库 + 多数据源业务库
```

### 2.2 NL2DSL2SQL 核心链路

```
用户输入 → IntentRecognition → EvidenceRecall → SchemaRecall
         → Planner → DslGenerate → DslValidate → [HumanFeedback]
         → DslCompiler → SqlExecute → [PythonGenerate/PythonExecute]
         → ReportGenerator → 返回结果
```

### 2.3 DSL 结构（中间表示层）

```json
{
  "metrics": ["gmv", "order_count"],
  "dimensions": ["region", "category"],
  "filters": [
    { "field": "region", "op": "in", "values": ["华东", "华南"] }
  ],
  "time_range": { "field": "created_at", "start": "2026-04-01", "end": "2026-04-30" },
  "order_by": [{ "field": "gmv", "direction": "DESC" }],
  "limit": 100
}
```

---

## 三、数据库设计

### 3.1 语义层表

#### `datasource` — 数据源
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| name | VARCHAR(100) | 数据源名称 |
| db_type | VARCHAR(20) | mysql/postgres/oracle/hive |
| host | VARCHAR(255) | 主机地址 |
| port | INT | 端口号 |
| database_name | VARCHAR(100) | 库名 |
| username | VARCHAR(100) | 连接用户名 |
| password_enc | TEXT | AES 加密密码 |
| created_at | TIMESTAMP | 创建时间 |

#### `semantic_dataset` — 语义数据集
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| name | VARCHAR(100) | 数据集中文名 |
| datasource_id | BIGINT FK | 关联数据源 |
| tables_json | JSON | 表和表关系配置 |
| description | TEXT | 业务语义描述（用于 embedding） |
| status | VARCHAR(20) | active / draft |
| created_at | TIMESTAMP | 创建时间 |

#### `semantic_metric` — 指标
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| dataset_id | BIGINT FK | 所属数据集 |
| name | VARCHAR(100) | 指标标识符（英文） |
| display_name | VARCHAR(100) | 指标中文名 |
| expr | TEXT | SQL 表达式，如 SUM(amount) |
| filter_sql | TEXT | 默认过滤条件 |
| synonyms | JSON | 同义词列表 |
| description | TEXT | 业务语义描述 |

#### `semantic_dimension` — 维度
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| dataset_id | BIGINT FK | 所属数据集 |
| name | VARCHAR(100) | 维度标识符 |
| display_name | VARCHAR(100) | 维度中文名 |
| column_name | VARCHAR(100) | 对应数据库字段名 |
| enum_values | JSON | 枚举值列表 |
| synonyms | JSON | 同义词列表 |

### 3.2 对话与消息表

#### `conversation` — 对话
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| agent_id | BIGINT FK | 所属智能体 |
| title | VARCHAR(200) | 对话标题 |
| thread_id | VARCHAR(64) | LangGraph thread ID |
| user_id | BIGINT | 创建用户 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 最后活跃时间 |

#### `message` — 消息
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK | 自增主键 |
| conversation_id | BIGINT FK | 所属对话 |
| role | VARCHAR(20) | user / assistant / system |
| content | TEXT | Markdown 内容 |
| sql_list | JSON | 执行的 SQL 列表 |
| report_html | LONGTEXT | 生成的 HTML 报告 |
| token_usage | JSON | Token 用量 |
| created_at | TIMESTAMP | 创建时间 |

---

## 四、核心 API 设计

### 4.1 查询类
| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/chat/stream` | 流式问数（SSE） |
| POST | `/api/chat/feedback` | 人工反馈（approve/reject） |
| GET | `/api/conversation` | 对话列表（分页） |
| GET | `/api/conversation/{id}` | 对话详情 |
| DELETE | `/api/conversation/{id}` | 删除对话 |

### 4.2 语义层管理 API
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/dataset` | 数据集列表 |
| POST | `/api/dataset` | 创建数据集 |
| POST | `/api/dataset/{id}/metric` | 添加指标 |
| POST | `/api/dataset/{id}/dimension` | 添加维度 |
| POST | `/api/dataset/{id}/embed` | 触发 schema embedding |

### 4.3 数据源管理 API
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/datasource` | 数据源列表 |
| POST | `/api/datasource` | 创建数据源（密码服务端加密） |
| POST | `/api/datasource/{id}/test` | 测试连接 |
| GET | `/api/datasource/{id}/schema` | 获取 schema（表和字段元信息） |

---

## 五、三阶段开发路线图

### Phase 1 | MVP（Week 1-6）
**目标**：单数据源上正常出 SQL 结果，流式输出可用

| Week | 主要任务 | 负责模块 | 交付物 |
|------|----------|----------|--------|
| W1 | 项目初始化，FastAPI 骨架，PostgreSQL + pgvector 环境 | 后端 | 可运行的骨架服务 |
| W2 | 数据源管理模块（CRUD + 连接测试），元数据表，schema 自动提取 | 后端 | 数据源接入 API |
| W3 | LangGraph 核心工作流：IntentNode → SchemaNode → SqlGenNode → SqlExecNode | 后端/AI | 基础 NL2SQL 链路 |
| W4 | SSE 流式输出，准确率评估框架，自动修正循环 | 后端 | SSE 流式接口 |
| W5 | 前端对话界面：消息布局、DSL 展示、表格渲染、基础图表 | 前端 | 可交互对话界面 |
| W6 | MVP 联调，3 个内部用户测试，收集问题修复 | 全员 | 可演示的 MVP |

### Phase 2 | 准确率提升（Week 7-13）
**目标**：常规业务问题准确率 >= 75%，语义层可自助建模

| Week | 主要任务 | 负责模块 | 交付物 |
|------|----------|----------|--------|
| W7-8 | 语义层管理：数据集/指标/维度 CRUD，前端建模界面；DSL JSON Schema 规范 | 全员 | 语义层管理界面 + DSL 规范 |
| W9 | DslGenerateNode（LLM 生成 DSL）+ DslValidateNode（代码校验） | 后端/AI | NL2DSL 链路可用 |
| W10 | DslCompilerNode：指标展开、JOIN 路径、多方言 SQL；编译器单元测试 | 后端 | DSL 编译器稳定可测试 |
| W11 | Schema embedding 流水线，SchemaRecallNode 升级；EvidenceRecallNode RAG | 后端/AI | 向量召回 + RAG 可用 |
| W12 | 多数据库支持（Oracle/SQL Server/Hive）；多轮对话上下文优化 | 后端/AI | 多数据库 + 多轮稳定 |
| W13 | 内部用户测试、语义层建模演练、NL2DSL2SQL 准确率验收 | 全员 | 准确率验收报告 |

### Phase 3 | 企业化（Week 14-20）
**目标**：支持多租户隔离，可观测性指标可查

| Week | 主要任务 | 负责模块 | 交付物 |
|------|----------|----------|--------|
| W14-15 | Python 分析节点：Docker 沙箱执行器，自动生成分析代码 | 后端/AI | Python 执行器可用 |
| W16 | 人工反馈节点：计划暂停、前端审批界面、恢复执行流程 | 全员 | 人工反馈流程可用 |
| W17 | RBAC 权限管理：用户/角色/数据集维度绑定，API Key 生命周期 | 后端 | 多租户权限隔离 |
| W18 | Langfuse 集成：全链路质量监控，定时报表推送 | 后端 | 可观测性可用 |
| W19 | 性能测试与调优：并发压测、连接池、缓存优化 | 后端 | 性能基准达标 |
| W20 | 生产发布准备：Docker Compose 打包、部署文档、回滚方案 | 全员 | v1.0 生产发布 |

---

## 六、风险与应对

| 风险项 | 级别 | 应对策略 |
|--------|------|----------|
| NL2DSL 准确率不达预期 | 高 | 建立 DSL 评估基准集；优先保障语义层建模质量 |
| DSL 表达能力受限 | 中 | 预留 raw_sql 逃逸字段，支持复杂查询降级路径 |
| DslCompiler 维护成本 | 中 | 单元测试覆盖率 >= 80%；CI 自动回归测试 |
| LLM 响应延迟影响体验 | 中 | 流式输出降低感知延迟；缓存常见 DSL 模式 |
| Python 执行安全风险 | 中 | Docker 沙箱隔离；限制内存和超时；白名单模块 |
| 企业数据隔离要求 | 高 | 各层以 datasource_id/user_id 过滤；强制只读校验 |

---

## 七、当前会话任务清单

1. [x] 读取并解析设计文档
2. [x] 创建工作计划（WORK_PLAN.md）
3. [x] 初始化 FastAPI 后端项目结构
4. [x] 创建 SQLAlchemy 数据库模型
5. [x] 配置 Alembic 迁移
6. [x] 实现 Phase 1 核心 API（数据源、数据集、对话、流式问数）
7. [x] 实现基础 LangGraph 工作流骨架
8. [x] 修复 DSL 编译器表名解析（支持 tables_json / 数据集名推断）
9. [x] 创建测试数据初始化脚本（scripts/seed_data.py）
10. [x] 编写核心 API 单元测试和集成测试（45+ 用例）
11. [x] 实现准确率评估框架（scripts/evaluate.py，8 个 benchmark 用例）
12. [ ] Phase 2 功能开发（语义层管理界面、NL2DSL 链路、向量召回等）

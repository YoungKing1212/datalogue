# API 概览

所有 API 统一前缀 `/api`

## 一、Agent Team（主执行入口）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent-team/tasks/stream` | **主问数入口**，SSE 流式返回 |

请求体 `AgentTeamTaskRequest`:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户问题 |
| `task_type` | string | 否 | bi_query / report / python_analysis |
| `dataset_id` | int | 否 | 指定数据集 |
| `conversation_id` | int | 否 | 续聊会话 |
| `thread_id` | string | 否 | AgentScope session ID |

## 二、AgentScope 控制面

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agentscope-control/status` | AgentScope Service 健康检查；完整运行时检查项见 `docs/operations/运行时健康检查.md` |

运行时健康检查至少覆盖：AgentScope Service、Redis、Credential、Leader Agent、Session stream、BI Tool、Artifact API、Frontend version。该检查是接手部署和 OpenViking 接入前的产品化验收口径，不替代业务问数回归。

## 三、数据集治理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dataset` | 数据集列表 |
| POST | `/api/dataset` | 创建数据集 |
| GET | `/api/dataset/{id}` | 数据集详情 |
| PUT | `/api/dataset/{id}` | 更新数据集 |
| DELETE | `/api/dataset/{id}` | 删除数据集 |
| GET | `/api/dataset/{id}/capability-manifest` | 能力 Manifest |
| POST | `/api/dataset/{id}/sql/preview` | SQL 预览 |
| POST | `/api/dataset/{id}/metric` | 创建指标 |
| POST | `/api/dataset/{id}/dimension` | 创建维度 |
| POST | `/api/dataset/{id}/blueprint` | 创建分析蓝图 |
| GET | `/api/dataset/subagent-manifests/current` | 当前 Manifest |

## 四、数据源管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/datasource` | 数据源列表 |
| POST | `/api/datasource` | 创建数据源 |
| POST | `/api/datasource/{id}/test` | 测试连接 |
| GET | `/api/datasource/{id}/schemas` | Schema 列表 |
| POST | `/api/datasource/{id}/sync-tables` | 同步表结构 |

## 五、LLM 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/llm/models` | 模型列表 |
| POST | `/api/llm/models` | 创建模型配置 |
| PUT | `/api/llm/models/{id}` | 更新模型配置 |
| DELETE | `/api/llm/models/{id}` | 删除模型配置 |

## 六、对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversation` | 会话列表 |
| POST | `/api/conversation` | 创建会话 |
| GET | `/api/conversation/{id}` | 会话消息 |
| DELETE | `/api/conversation/{id}` | 删除会话 |

## 七、工作台

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workbench/thread/{thread_id}` | 工作台线程视图 |
| GET | `/api/workbench/artifact/{ref}` | 产物摘要视图 |
| POST | `/api/workbench/actions/retry` | 受控重试 |

## 八、产物

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/artifacts/{ref}` | 查询产物详情 |

## 九、消息反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/messages/{id}/feedback` | 消息反馈 |

## 十、AgentScope Service（子应用，路径前缀 /agentscope）

AgentScope Service 官方 API，通过 `create_app()` 生成。端点列表见 Swagger 文档。

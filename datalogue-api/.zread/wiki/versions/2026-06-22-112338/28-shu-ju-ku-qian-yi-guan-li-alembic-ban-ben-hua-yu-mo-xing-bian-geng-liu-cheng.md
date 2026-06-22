本文档解剖 Datalogue API 项目中基于 Alembic 的数据库迁移管理体系，涵盖 env.py 的引导机制、28 条历史迁移的版本链拓扑、三种迁移操作模式及相应的幂等性策略、以及测试层绕过迁移系统的设计决策。适合已经理解 [核心概念：数据集、指标、维度与语义层治理](3-he-xin-gai-nian-shu-ju-ji-zhi-biao-wei-du-yu-yu-yi-ceng-zhi-li) 中模型定义的读者。

Sources: [alembic/README](alembic/README#L1)

## 架构总览：Alembic 与 SQLAlchemy 元数据的耦合点

整个迁移系统围绕一个核心耦合点运转——`alembic/env.py` 将 SQLAlchemy 的 `Base.metadata`（声明式模型的总注册表）注入 Alembic 的迁移上下文。这使得 `alembic revision --autogenerate` 能够将 Python 模型定义与数据库实际状态做 diff，自动生成迁移脚本。数据库连接 URL 不走 `alembic.ini` 中的占位符 `driver://user:pass@localhost/dbname`，而是通过 Pydantic `Settings` 对象在运行时动态注入——这保证了开发、测试、生产环境使用各自的 `.env` 配置而无需修改版本控制中的配置文件。

```mermaid
flowchart TB
    subgraph Runtime["运行时引导"]
        ENV["alembic/env.py"] --> CFG["app.core.config.Settings<br/>读取 DATABASE_URL"]
        ENV --> META["app.core.database.Base.metadata<br/>声明式模型注册表"]
        ENV --> MODELS["app.models.* （通配导入）<br/>触发所有模型元数据注册"]
    end
    subgraph Operations["迁移操作"]
        ONLINE["run_migrations_online()<br/>从引擎获取连接，开始事务"]
        OFFLINE["run_migrations_offline()<br/>生成原始 SQL 脚本"]
    end
    subgraph Versions["版本链"]
        V1["20260528_0001 (根)"] --> V2["20260530_0001"]
        V2 --> V3["ab6832e0a3dd"]
        V3 --> V28["k6l7m8n9o0p1 (HEAD)"]
    end
    CFG --> ONLINE
    CFG --> OFFLINE
    META --> ONLINE
    META --> OFFLINE
    ONLINE --> Versions
    OFFLINE --> Versions
```

`env.py` 中的 `run_migrations_online()` 是生产环境的标准执行路径：它创建只连接不池化的 `NullPool` 引擎，在同一连接上开启事务后执行所有待迁移脚本。离线模式则输出原始 SQL 文本，供 DBA 审核或手工执行。两者共享同一个 `target_metadata`——这意味着无论哪种模式，Alembic 都以 SQLAlchemy 模型定义作为真理来源（Source of Truth）。

Sources: [env.py](alembic/env.py#L14-L64) | [config.py](app/core/config.py#L20-L21) | [database.py](app/core/database.py#L26-L37)

## 版本链拓扑：28 条迁移的线性演化史

项目当前包含 28 条迁移文件，构成一条严格的线性版本链——每个迁移通过 `down_revision` 指向唯一的前驱，`revision` 作为本节点的标识符。不存在分支（`branch_labels=None`）或依赖外部迁移（`depends_on=None`），这意味着整个数据库 Schema 演化是一条单链表。以下是完整的版本序列表：

| 序号 | Revision ID | 迁移说明 | 操作类型 |
|------|-----------|---------|---------|
| 1 | `20260528_0001` | 创建初始表结构（conversation, datasource, semantic_dataset, message, semantic_dimension, semantic_metric） | 建表 |
| 2 | `add_ds_status` | 为 datasource 添加 status 字段 | 加列 |
| 3 | `ab6832e0a3dd` | 扩展 metric/dimension 字段（table_name, time_field 等）；source_table/source_column 已存在 | 加列 |
| 4 | `2bc2a6cac055` | 创建 dataset_source_table 关联表 | 建表 |
| 5 | `468af34bcb43` | 为 source_table/source_column 添加 AI/人工标注字段 | 加列 |
| 6 | `add_conversation_archived` | 为 conversation 添加 archived 归档字段 | 加列+索引 |
| 7 | `e47d3004182b` | 为 message 添加 step_trace 字段 | 加列 |
| 8 | `7f1a2b3c4d5e` | 为 semantic_dataset 添加 prompt_instructions 字段 | 加列 |
| 9 | `8c4d2e6f7a90` | 创建 analysis_blueprint / blueprint_version / blueprint_usage_log | 建表 |
| 10 | `9b7c1d2e3f40` | 为 source_column 添加 review/conversion 字段 | 加列 |
| 11 | `a4d9e8f1c230` | 创建 business_term / asset_link / relation / change_log | 建表 |
| 12 | `b2c4d6e8f901` | 为 semantic_dataset 添加 query_constraints 字段 | 加列 |
| 13 | `c9d1e2f3a4b5` | 为 analysis_blueprint 添加 creation_source 字段 | 加列 |
| 14 | `d4e5f6a7b8c9` | 为 blueprint_usage_log 添加 row_count / diagnosis | 加列 |
| 15 | `f6a7b8c9d0e1` | 创建 sql_diagnosis_log 表 | 建表 |
| 16 | `0f1e2d3c4b5a` | 为 message 添加 response_metadata 字段 | 加列 |
| 17 | `a1b2c3d4e5f6` | 为 conversation 添加 dataset_id 外键 | 加列+外键+索引 |
| 18 | `b7c8d9e0f1a2` | 创建 semantic_validation_case 表 | 建表 |
| 19 | `c1d2e3f4a5b6` | 创建 pending_clarification 表 | 建表 |
| 20 | `d2e3f4a5b6c7` | 为 datasource 添加连接能力字段（dialect, driver, timeout 等） | 加列 |
| 21 | `e3f4a5b6c7d8` | 创建 llm_model_config / llm_role_binding | 建表 |
| 22 | `f1a2b3c4d5e6` | 创建 observability_trace_index / trace_annotation_candidate | 建表 |
| 23 | `g2h3i4j5k6l7` | 为 llm_model_config 添加 thinking_enabled | 加列 |
| 24 | `h3i4j5k6l7m8` | 为 source_table/source_column 添加 comment 字段 | 加列 |
| 25 | `i4j5k6l7m8n9` | 创建 dataset_subagent_manifest 表 | 建表 |
| 26 | `j5k6l7m8n9o0` | 创建 conversation_state 表 | 建表 |
| 27 | `k6l7m8n9o0p1` | 创建 query_artifact 表 | 建表 |

这个序列表反映了一个明确的演化规律：早期迁移（#1-#10）偏向于快速迭代基础模型和添加字段，中期（#11-#20）引入术语治理、待定澄清等高级语义层概念，后期（#21-#27）则集中在 LLM 基础设施、可观测性和多轮状态管理。每个迁移对应 [数据源与部署运维](#) 模型层的一次增量变更，且严格按时间顺序追加。

Sources: [20260528_0001](alembic/versions/20260528_0001_init_models.py#L28-L29) | [20260530_0001](alembic/versions/20260530_0001_add_ds_status.py#L24-L25) | [ab6832e0a3dd](alembic/versions/ab6832e0a3dd_add_source_tables_and_extend_metric_dim.py#L28-L29) | [add_conversation_archived](alembic/versions/add_conversation_archived.py#L24-L25) | [j5k6l7m8n9o0](alembic/versions/j5k6l7m8n9o0_add_conversation_state.py#L30-L31) | [k6l7m8n9o0p1](alembic/versions/k6l7m8n9o0p1_add_query_artifact.py)

## 三种核心操作模式与代码范式

纵观 28 条迁移，可以归纳为三类操作模式，每种模式在幂等性策略和代码结构上呈现明显差异：

### 模式一：建表（`op.create_table`）

完整的表创建包含列定义、主键约束、外键约束、唯一约束和索引创建。以分析蓝图迁移为例：

```python
def upgrade() -> None:
    op.create_table(
        "analysis_blueprint",
        sa.Column("id", sa.Integer(), nullable=False, comment='主键'),
        sa.Column("dataset_id", sa.Integer(), nullable=False, comment='所属数据集 ID'),
        # ... 20+ 列 ...
        sa.ForeignKeyConstraint(["dataset_id"], ["semantic_dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment='分析蓝图表',
    )
    op.create_index(op.f("ix_analysis_blueprint_id"), "analysis_blueprint", ["id"], unique=False)
```

Sources: [8c4d2e6f7a90](alembic/versions/8c4d2e6f7a90_add_analysis_blueprints.py#L33-L70)

建表模式的 `downgrade()` 严格按创建的反序执行——先删索引、再删表。这是 Alembic 的标准约定：索引依赖于表，必须先于表删除。

### 模式二：加列（`op.add_column`）

添加新列是最常见的增量变更。关键差异在于是否做幂等性检查：

| 策略 | 代表迁移 | 代码特征 |
|------|---------|---------|
| 无检查（乐观执行） | `add_conversation_archived` | 直接调用 `op.add_column()`，依赖 Alembic 版本号保证不重复执行 |
| 运行时检查（幂等安全） | `a1b2c3d4e5f6`, `g2h3i4j5k6l7` | 先用 `inspect(op.get_bind())` 检查列/表是否存在，再决定是否执行 |

无检查策略适用于单次递增的线性链，因为 Alembic 通过 `alembic_version` 表记录已应用的版本号，不会重复执行。但幂等检查策略在以下场景中提供了额外的安全性：(1) 手动修复部分失败的迁移后重新运行；(2) 多环境部署时表状态不一致的容错；(3) CI/CD 流水线中多次重试的安全性。

Source: [add_conversation_archived](alembic/versions/add_conversation_archived.py#L30-L35) | [a1b2c3d4e5f6](alembic/versions/a1b2c3d4e5f6_add_dataset_id_to_conversation.py#L35-L45) | [g2h3i4j5k6l7](alembic/versions/g2h3i4j5k6l7_add_llm_thinking_enabled.py#L42-L47)

### 模式三：加列+外键+索引（复合操作）

这是最复杂但最完整的模式，以 `a1b2c3d4e5f6_add_dataset_id_to_conversation` 为代表——它为 `conversation` 表同时添加外键列和对应索引，`downgrade()` 按反序先删索引再删列：

```python
def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("conversation")}
    indexes = {index["name"] for index in inspector.get_indexes("conversation")}
    if "dataset_id" not in columns:
        op.add_column("conversation", sa.Column("dataset_id", sa.Integer(), ...))
    if "ix_conversation_dataset_id" not in indexes:
        op.create_index("ix_conversation_dataset_id", "conversation", ["dataset_id"])

def downgrade() -> None:
    # ... 先检查索引存在再删除，再检查列存在再删除 ...
```

Sources: [a1b2c3d4e5f6](alembic/versions/a1b2c3d4e5f6_add_dataset_id_to_conversation.py#L35-L55)

这种反序删除（索引→列，或表→索引→列）是 Alembic 迁移的铁律：依赖关系在 `downgrade()` 中必须按构建顺序的逆序拆除。

## 幂等性保护的演化轨迹

通过对比早期迁移（#6 `add_conversation_archived`）与后期迁移（#26 `j5k6l7m8n9o0_add_conversation_state`）的代码结构，可以清晰观察幂等性策略的进化：

| 维度 | 早期迁移（v1 风格） | 后期迁移（v2 风格） |
|------|-------------------|-------------------|
| 表存在检查 | ❌ 无 | `inspector.has_table("conversation_state")` |
| 列存在检查 | ❌ 无 | `column["name"] for column in inspector.get_columns(...)` |
| 索引存在检查 | ❌ 无 | 已提取为辅助函数 `_create_index_if_missing()` / 内联集合比较 |
| downgrade 守卫 | ❌ 直接执行 | `if not inspector.has_table(...): return` |
| helper 函数 | ❌ 无 | `_create_index_if_missing()`, `_has_column()`, `_json_type()` |

后期模式的一个关键设计是 **downgrade 守卫**：在删除表之前先检查表是否存在，如果不存在则直接返回。这在以下场景中至关重要——当某个中间迁移只完成了一半（例如表已创建但索引更新失败）后执行降级时，可以避免 `DROP TABLE` 在已不存在的表上抛出异常。

Sources: [f1a2b3c4d5e6](alembic/versions/f1a2b3c4d5e6_add_observability_tables.py#L35-L39) | [j5k6l7m8n9o0](alembic/versions/j5k6l7m8n9o0_add_conversation_state.py#L41-L89) | [g2h3i4j5k6l7](alembic/versions/g2h3i4j5k6l7_add_llm_thinking_enabled.py#L35-L39)

## JSON 类型的跨数据库兼容策略

由于测试环境使用 SQLite 而生产环境使用 PostgreSQL，迁移中对 JSON 列的类型声明采用了 SQLAlchemy 的 `with_variant` 机制。这在 `conversation_state` 表的创建中最为典型：

```python
def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
```

这个模式确保：(1) 在 PostgreSQL 上使用 `JSONB`（支持索引、二进制存储）；(2) 在 SQLite 上回退为通用 `JSON` 类型（SQLite 将 JSON 存储为 TEXT）；(3) `downgrade()` 中无需区分数据库类型——Alembic 使用相同的 `sa.JSON()` 引用删除列。同样的模式也出现在模型定义层的 `app/models/conversation.py` 中，保证了迁移脚本与运行时代码的类型一致性。

Sources: [j5k6l7m8n9o0](alembic/versions/j5k6l7m8n9o0_add_conversation_state.py#L36-L37) | [conversation.py](app/models/conversation.py#L23-L26)

## 日常操作流程

```mermaid
flowchart LR
    A["修改 app/models/*.py<br/>调整列/表定义"] --> B["alembic revision --autogenerate<br/>-m '描述性信息'"]
    B --> C["审查生成的迁移脚本<br/>验证 upgrade/downgrade 正确性"]
    C --> D{"通过审查？"}
    D -->|否| E["手动修改迁移脚本<br/>补充幂等性检查/索引"]
    E --> C
    D -->|是| F["alembic upgrade head<br/>应用到开发数据库"]
    F --> G["git commit 提交迁移文件"]
```

关键命令对照：

| 命令 | 用途 |
|------|------|
| `alembic revision --autogenerate -m "描述"` | 从模型 diff 生成新迁移脚本 |
| `alembic upgrade head` | 将数据库升级到最新版本 |
| `alembic downgrade -1` | 回退最近一个版本 |
| `alembic current` | 查看当前数据库版本 |
| `alembic history` | 查看完整版本链 |
| `alembic upgrade head --sql` | 生成升级 SQL（不执行，供 DBA 审核） |

注意：`alembic revision --autogenerate` 只能检测以下变更——新增/删除表、新增/删除列、列类型变更、索引和约束变更。**列重命名、表重命名** 无法自动检测，需要手动编写迁移脚本使用 `op.alter_column` 或 `op.rename_table`。

## 测试层与迁移系统的解耦

测试配置采用了一种与 Alembic 完全解耦的策略。`tests/conftest.py` 中的 `engine` fixture 直接调用 `Base.metadata.create_all(bind=engine)` 在 SQLite 内存数据库中创建所有表，测试结束后执行 `Base.metadata.drop_all()` 清理。这意味着：(1) 测试不依赖任何历史迁移脚本；(2) 总是创建与当前模型定义完全一致的表结构（即 "latest state"）；(3) 单个测试函数通过 `transaction.rollback()` 实现隔离，不污染其他测试。

这种设计带来一个需要警惕的隐患：如果某个生产数据库通过 Alembic 迁移链达到的状态与 `Base.metadata.create_all()` 直接创建的状态不一致（例如某条迁移的 `upgrade()` 遗漏了索引或默认值），测试将无法暴露该问题。缓解措施是在 CI 流水线中增加一步：使用 Alembic 在真实的 PostgreSQL 容器上执行全量迁移后运行冒烟测试。

Sources: [conftest.py](tests/conftest.py#L45-L70)

## 实践指南：编写一条新迁移

当需要在模型中添加新字段或新表时，遵循以下范式可以保证迁移的健壮性：

**加列（推荐幂等模式）**：
```python
def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("target_table")}
    if "new_column" not in columns:
        op.add_column("target_table", sa.Column("new_column", sa.String(100), nullable=True, comment='新列说明'))

def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("target_table")}
    if "new_column" in columns:
        op.drop_column("target_table", "new_column")
```

**建表（推荐幂等模式）**：
```python
def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("new_table"):
        op.create_table("new_table", ...)
    # 索引独立检查
    indexes = {i["name"] for i in inspector.get_indexes("new_table")}
    if "ix_new_table_col" not in indexes:
        op.create_index("ix_new_table_col", "new_table", ["col"])

def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("new_table"):
        return
    # 先删索引再删表
    ...
```

## 后续阅读

理解数据库迁移管理之后，建议按以下路径深入：

- [Docker Compose 本地开发环境：PostgreSQL + Langfuse 全家桶](29-docker-compose-ben-di-kai-fa-huan-jing-postgresql-langfuse-quan-jia-tong) — 了解如何在实际 PostgreSQL 环境中验证迁移
- [测试体系：pytest Fixture、SQLite 隔离与会话级回滚](30-ce-shi-ti-xi-pytest-fixture-sqlite-ge-chi-yu-hui-hua-ji-hui-gun) — 深入测试层与迁移系统的解耦设计
- [核心概念：数据集、指标、维度与语义层治理](3-he-xin-gai-nian-shu-ju-ji-zhi-biao-wei-du-yu-yu-yi-ceng-zhi-li) — 回看迁移所服务的模型语义
- [代码规范与审查清单：Black、Ruff、mypy 质量保障](31-dai-ma-gui-fan-yu-shen-cha-qing-dan-black-ruff-mypy-zhi-liang-bao-zhang) — 迁移脚本同样受代码规范约束
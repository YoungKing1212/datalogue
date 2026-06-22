数据源连接引擎是 Datalogue 平台的数据面基础设施层，负责桥接平台内部语义层与外部异构数据库之间的所有物理交互。它采用 **"能力注册 — 适配器路由 — SQLAlchemy 统一抽象"** 三层架构，在保持多数据库兼容性的同时，将方言差异封装在适配器内部，向上层调用方（问数管道、Schema 召回、SQL 守卫）提供统一的连接、查询和元数据探查接口。

## 一、架构概览：三层分离与责任边界

整个引擎的核心设计原则是 **"能力声明优于运行时探测"**：每一种数据库类型在启动时即完成能力注册，运行时通过 `db_type` 查表获取适配器，避免在热路径上进行 `try-except` 式的数据库类型猜测。引擎分三层协同工作：

```mermaid
graph TD
    subgraph API 层
        R[FastAPI Router<br/>/api/datasource]
    end

    subgraph Service 层
        S[datasource service<br/>公开函数入口]
        CC[get_capabilities<br/>能力列表]
        TC[test_connection<br/>连通性诊断]
        SS[sync_source_tables<br/>表结构同步]
        SP[get_schema / get_schemas<br/>Schema 探查]
        DC[build_datasource_context<br/>上下文构建器]
    end

    subgraph Adapter 层
        BASE[DatasourceAdapter<br/>基类]
        ORACLE[OracleAdapter<br/>数据字典回退]
        HIVE[HiveAdapter<br/>SHOW 语句补充]
        GENERIC[通用 Adapter<br/>SQLAlchemy Inspector]
    end

    subgraph 基础设施
        ENG[SQLAlchemy Engine<br/>create_engine / pool]
        INSP[SQLAlchemy Inspector<br/>反射元数据]
        SQLGLOT[sqlglot AST<br/>方言解析]
    end

    R --> S
    S --> CC
    S --> TC --> BASE
    S --> SS --> BASE
    S --> SP --> BASE
    S --> DC
    BASE --> ORACLE
    BASE --> HIVE
    BASE --> GENERIC
    BASE --> ENG
    BASE --> INSP
    ENG --> DB[(外部数据库)]
```

三层责任如下：

| 层级 | 核心职责 | 关键模块 |
|------|---------|----------|
| **API 层** | CRUD 端点、连接测试、Schema 同步触发、字段标注触发 | `app/api/datasource.py` |
| **Service 层** | 能力枚举、异常分类诊断、上下文构建、适配器路由 | `app/services/datasource.py` |
| **Adapter 层** | URL 构造、方言感知的 Schema 探查、行数估算、DDL 导出 | `DatasourceAdapter` 及其子类 |

Sources: [datasource.py](app/services/datasource.py#L1-L26), [datasource.py](app/api/datasource.py#L1-L18), [datasource.py](app/models/datasource.py#L1-L13)

## 二、能力注册体系：从类型标识到完整能力描述

引擎将每种数据库类型的连接属性、方言元数据、驱动要求和扩展选项统一建模为不可变的 `DatasourceCapability` 数据类，集中维护在 `CAPABILITIES` 字典中。这使得前端创建表单可以通过 `/api/datasource/capabilities` 端点动态获取可用的数据源类型列表，无需前端硬编码适配逻辑。

### 2.1 DatasourceCapability 数据结构

```python
@dataclass(frozen=True)
class DatasourceCapability:
    db_type: str               # 内部标识（如 "mysql", "postgres"）
    label: str                 # 前端展示名称（如 "MySQL", "PostgreSQL"）
    dialect: str               # SQLGlot 方言标识（如 "mysql", "tsql"）
    driver: str | None         # 驱动名称（如 "pymysql"）
    driver_module: str | None  # 驱动导入模块（如 "pymysql"）
    sqlalchemy_driver: str     # SQLAlchemy URL 前缀（如 "mysql+pymysql"）
    default_port: int          # 默认端口
    default_schema: str | None # 默认 Schema
    stable: bool               # 是否稳定支持
    required_options: tuple    # 必填扩展选项
    optional_options: tuple    # 可选扩展选项
    supports_sqlalchemy: bool  # 是否使用 SQLAlchemy 原生支持
    test_sql: str              # 连接测试 SQL
```

### 2.2 当前已注册的数据库类型

系统目前注册了 **10 种**数据源类型，覆盖关系型、OLAP 和云数仓三大类别：

| db_type | 标签 | SQL 方言 | 驱动 | 默认端口 | 稳定版 | 特殊适配 |
|---------|------|----------|------|----------|--------|----------|
| `postgres` | PostgreSQL | `postgres` | psycopg2 | 5432 | ✅ | — |
| `mysql` | MySQL | `mysql` | pymysql | 3306 | ✅ | — |
| `sqlite` | SQLite | `sqlite` | 内置 | 0 | ✅ | check_same_thread=False |
| `oracle` | Oracle | `oracle` | oracledb | 1521 | — | `OracleAdapter`（数据字典回退） |
| `hive` | Hive | `hive` | pyhive | 10000 | — | `HiveAdapter`（SHOW 语句补充） |
| `clickhouse` | ClickHouse | `clickhouse` | clickhouse-sqlalchemy | 9000 | — | — |
| `sqlserver` | SQL Server | `tsql` | pyodbc | 1433 | — | — |
| `trino` | Trino | `trino` | trino | 8080 | — | catalog/schema 扩展选项 |
| `presto` | Presto | `presto` | pyhive | 8080 | — | catalog/schema 扩展选项 |
| `bigquery` | BigQuery | `bigquery` | sqlalchemy-bigquery | 0 | — | project/dataset 扩展选项 |

其中 `oracle` 和 `hive` 使用了专用适配器子类（下文详述），因为它们的元数据访问模式无法完全由 SQLAlchemy Inspector 覆盖。

### 2.3 类型别名归一化

用户输入 `db_type` 时可能使用非标准变体（如 `postgresql`、`pg`、`mssql`），系统通过 `ALIASES` 字典进行归一化：

```python
ALIASES = {
    "postgresql": "postgres",  # "postgresql" → "postgres"
    "pg": "postgres",          # "pg" → "postgres"
    "mssql": "sqlserver",      # "mssql" → "sqlserver"
    "sql_server": "sqlserver", # "sql_server" → "sqlserver"
}
```

`normalize_db_type()` 函数先取小写，再查别名表，未命中则原样返回，确保任何合法的变体写法都能正确路由到对应适配器。

### 2.4 驱动可用性检测

`get_capabilities()` 函数为每条能力记录实时检测驱动模块是否已安装（通过 `importlib.import_module`），返回 `driver_status` 字段，分为三种状态：

- **`builtin`**：无需额外驱动（如 SQLite）
- **`installed`**：驱动已安装，可直接创建连接
- **`missing`**：驱动未安装，返回安装指引

`install_hint` 字段指向离线部署方案——在有网构建机执行 `scripts/download_enterprise_wheels.sh` 下载 wheel 包到 `wheelhouse/` 目录，然后在内网使用 `pip install --no-index --find-links ./wheelhouse -r requirements-enterprise.txt` 安装。

Sources: [datasource.py](app/services/datasource.py#L530-L645), [datasource.py](app/services/datasource.py#L652-L688), [datasource.py](app/services/datasource.py#L636-L649), [config.py](app/core/config.py#L1-L165)

## 三、适配器模式：统一接口与方言特化

`DatasourceAdapter` 是所有数据源适配器的基类，封装了 SQLAlchemy 连接创建、元数据探查和数据预览的完整流程。对于 SQLAlchemy Inspector 无法覆盖的场景，通过子类覆写实现方言特化。

### 3.1 连接 URL 构造：`build_url()`

不同数据库的连接 URL 格式差异很大，`build_url()` 方法负责按 `db_type` 组装正确的 SQLAlchemy 连接字符串。密码在此过程通过 `decrypt_password()` 从密文还原为明文（参见 [数据库迁移管理](28-shu-ju-ku-qian-yi-guan-li-alembic-ban-ben-hua-yu-mo-xing-bian-geng-liu-cheng) 了解加密方案）。

各数据库的 URL 构造策略：

| db_type | URL 模式 | 特殊处理 |
|---------|---------|----------|
| `sqlite` | `sqlite:///数据库文件路径` | 忽略 host/port/username |
| `oracle` | `oracle+oracledb://user:pass@host:port/?service_name=xxx` 或 `?sid=xxx` | 从 `connection_options` 读取 service_name/sid |
| `hive` | `hive://user:pass@host:port/database?auth=xxx` | 从 `connection_options` 读取 auth 模式 |
| `trino/presto` | `trino://user:pass@host:port/catalog/schema` | catalog 和 schema 来自 `connection_options` |
| `bigquery` | `bigquery://project/dataset` | project 和 dataset 来自 `connection_options` |
| `mysql/postgres` | `mysql+pymysql://user:pass@host:port/database` | 标准 SQLAlchemy URL |

所有用户名和数据库名经过 `urllib.parse.quote_plus()` 编码，防止特殊字符引发 URL 解析错误。

### 3.2 Engine 创建与连接池

`create_engine()` 方法在构造 URL 后调用 SQLAlchemy 的 `create_engine()`，统一配置 `pool_pre_ping=True`（每次从池中取出连接时先 ping 验证有效性）和 `pool_recycle=3600`（连接每 3600 秒回收），并按数据库类型注入特定的 `connect_args`：

```python
if db_type == "sqlite":
    connect_args["check_same_thread"] = False   # 允许多线程访问
elif db_type == "mysql":
    connect_args["connect_timeout"] = timeout    # MySQL 连接超时
elif db_type in {"postgres", "postgresql"}:
    connect_args["connect_timeout"] = timeout    # PostgreSQL 连接超时
elif db_type == "oracle":
    connect_args["tcp_connect_timeout"] = timeout # Oracle TCP 超时
```

### 3.3 Oracle 适配器：SQLAlchemy Inspector 失败时的数据字典回退

`OracleAdapter` 覆写了 `get_schemas()` 方法。由于 Oracle 的 SQLAlchemy Inspector 在某些权限受限场景下无法正确返回 Schema 列表，适配器直接查询 Oracle 数据字典 `all_tables`，过滤掉系统 Schema（`SYS`、`SYSTEM`、`XDB` 等），返回用户可见的 Schema 列表：

```sql
SELECT DISTINCT owner FROM all_tables
WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS')
ORDER BY owner
```

同时也覆写了 `schema_readable()` 方法，通过执行轻量级查询来验证权限，而非依赖 Inspector。

### 3.4 Hive 适配器：SHOW 语句补充元数据读取

`HiveAdapter` 覆写了 `get_schemas()` 和 `get_schema()` 两个方法。因为 Hive 的 SQLAlchemy 方言对元数据反射的支持不完整，适配器使用 Hive 原生的 `SHOW DATABASES` 和 `SHOW TABLES IN` 语句获取数据库和表列表，再用 `DESCRIBE` 语句获取列信息。列描述中跳过空列名和以 `#` 开头的注释行（Hive 中常见的分隔标记）。

Sources: [datasource.py](app/services/datasource.py#L135-L198), [datasource.py](app/services/datasource.py#L430-L530), [security.py](app/core/security.py#L1-L45)

## 四、Schema 探查：全链路元数据发现

Schema 探查是数据源连接引擎的核心能力之一，负责从连接成功的外部数据库中自动提取表结构、字段信息、主键外键约束、近似行数和字段样例值。

### 4.1 探查流程

```mermaid
flowchart TD
    START([开始探查]) --> CONNECT[create_engine + inspect]
    CONNECT --> SCHEMAS{获取 Schema 列表}
    SCHEMAS --> |成功| FILTER[过滤系统 Schema<br/>information_schema, pg_catalog 等]
    SCHEMAS --> |失败| ERR_SCHEMA[抛出 SCHEMA_UNREADABLE 诊断]
    FILTER --> TABLES[get_table_names<br/>按 schema 获取表列表]
    TABLES --> FOR_EACH_TABLE[遍历每张表]
    FOR_EACH_TABLE --> GET_COLS[inspector.get_columns<br/>字段名、类型、可空、默认值、注释]
    GET_COLS --> GET_PK[inspector.get_pk_constraint<br/>主键约束]
    GET_PK --> GET_FK[inspector.get_foreign_keys<br/>外键约束]
    GET_FK --> ROW_COUNT[_row_count<br/>近似行数]
    ROW_COUNT --> DDL[_ddl<br/>DDL 语句（MySQL）]
    DDL --> SAMPLE{字段样例采集}
    SAMPLE --> |成功| NEXT_COL{下一字段?}
    SAMPLE --> |失败| SKIP[记录 SAMPLE_UNREADABLE<br/>字段结构已同步，样例稍后可重试]
    SKIP --> NEXT_COL
    NEXT_COL --> |是| SAMPLE
    NEXT_COL --> |否| NEXT_TABLE{下一张表?}
    NEXT_TABLE --> |是| FOR_EACH_TABLE
    NEXT_TABLE --> |否| DONE([返回探查结果])
```

### 4.2 系统 Schema 过滤

探查过程中自动排除以下系统级 Schema（存储在 `SYSTEM_SCHEMAS` 集合中）：

- PostgreSQL：`information_schema`、`pg_catalog`、`pg_toast`
- MySQL：`information_schema`、`mysql`、`performance_schema`、`sys`

这些系统 Schema 对业务问数无意义，提前过滤可减少前端噪音和后续上下文体积。

### 4.3 行数估算的方言差异

`_row_count()` 方法的实现因数据库而异，避免在所有场景下执行耗时的 `SELECT COUNT(*)`：

| 数据库 | 行数获取方式 | 说明 |
|--------|-------------|------|
| PostgreSQL | `SELECT reltuples::bigint FROM pg_class WHERE relname = :t` | 读取统计信息估算值，O(1) 操作 |
| MySQL | `SELECT COUNT(*) FROM \`table\`` | 实际 COUNT，大表可能较慢 |
| SQLite | `SELECT COUNT(*) FROM "table"` | 实际 COUNT |
| 其他 | 返回 `None` | 不执行行数查询 |

### 4.4 字段样例采集

`sample_column_values()` 方法从表中抽取某字段的 **非空唯一值**（`SELECT DISTINCT ... WHERE IS NOT NULL`）作为 LLM 标注的上下文参考。默认采集 5 条，Oracle 使用 `FETCH FIRST` 语法，其他数据库使用 `LIMIT` 语法。采集失败时抛出 `SAMPLE_UNREADABLE` 诊断码，但 **不阻塞整体同步流程**——字段结构信息仍然正常写入，样例字段留空，便于后续按需重试。

### 4.5 同步到持久化层

API 端点 `POST /{ds_id}/sync-tables` 将探查结果增量同步到 `source_table` 和 `source_column` 表。合并策略为：

- **新表**：直接插入 `SourceTable` 记录
- **已有表**：更新 `table_comment`、`row_count_approx`、`synced_at`
- **新字段**：插入 `SourceColumn` 记录
- **已有字段**：只更新 DDL 元数据（`data_type`、`is_nullable` 等），**保留用户标注**（`user_description`、`user_semantic_role` 等）
- **已删除字段**：从 `source_column` 中删除（数据库中已不存在的字段）
- **注释变更**：当 `column_comment` 变化且当前生效值来源为 `db_comment` 或 `unknown` 时，标记 `desc_source = "stale"` 以触发重新标注

Sources: [datasource.py](app/services/datasource.py#L266-L370), [datasource.py](app/services/datasource.py#L370-L430), [datasource.py](app/api/datasource.py#L200-L330), [datasource.py](app/services/datasource.py#L28-L52)

## 五、统一诊断体系：异常分类与可操作建议

引擎将所有连接和操作异常收敛为统一的 `DatasourceDiagnostic` 结构，确保前端和日志系统能够稳定地展示可操作的错误信息。

### 5.1 诊断码注册表

| 诊断码 | 分类 | 可重试 | 建议操作 |
|--------|------|--------|----------|
| `UNSUPPORTED_DB_TYPE` | config | ❌ | 选择当前系统已注册的数据源类型 |
| `DRIVER_MISSING` | driver | ❌ | 安装对应数据库驱动后重试 |
| `CONNECTION_FAILED` | connection | ✅ | 检查主机、端口、网络、服务状态和连接参数 |
| `AUTH_FAILED` | auth | ❌ | 检查用户名、密码和认证方式配置 |
| `PERMISSION_DENIED` | permission | ❌ | 确认当前账号具备读取库、schema、表和字段的权限 |
| `SCHEMA_UNREADABLE` | schema | ❌ | 检查元数据读取权限，或缩小 schema 范围后重试 |
| `SAMPLE_UNREADABLE` | sample | ✅ | 字段结构已同步，样例可稍后按表或字段重新采集 |
| `DIALECT_UNSUPPORTED` | dialect | ❌ | 按目标数据源方言调整 SQL 或补充方言适配规则 |
| `SQL_GUARD_BLOCKED` | security | ❌ | 仅允许执行当前数据集授权表上的单条只读查询 |
| `QUERY_TIMEOUT` | performance | ✅ | 缩小查询范围、增加过滤条件或调大超时时间 |
| `UNKNOWN_DATASOURCE_ERROR` | unknown | ✅ | 查看原始错误并按连接、权限或驱动问题继续排查 |

### 5.2 异常自动分类

`_classify_exception()` 函数通过异常类型和错误消息的关键词匹配，将底层数据库异常自动归类为上述诊断码。优先级顺序为：驱动缺失 → 权限不足 → 认证失败 → 超时 → 连接失败 → 兜底。例如 Oracle 的错误码 `ORA-01017` 被匹配为 `AUTH_FAILED`，`ORA-01013` 被匹配为 `QUERY_TIMEOUT`。

### 5.3 连接测试的完整诊断

`test_connection()` 函数执行四步渐进式诊断：

1. 验证数据源类型是否已注册（`get_adapter()`）
2. 检测驱动是否可用（`adapter.driver_available()`）
3. 尝试建立连接并执行 `test_sql`（各类型不同，如 Oracle 为 `SELECT 1 FROM DUAL`）
4. 尝试读取数据库版本号（`adapter.version()`）和 Schema 可读性（`adapter.schema_readable()`）

测试结果会回写到 `Datasource` 记录的 `last_test_result`、`status`（`"connected"` / `"disconnected"`）和错误字段中。

Sources: [datasource.py](app/services/datasource.py#L54-L133), [datasource.py](app/services/datasource.py#L730-L798)

## 六、SQL 方言适配：跨数据库的 SQL 规范化

数据源连接引擎通过 `app/utils/sql_dialect.py` 和 `app/utils/sql_guard.py` 两个模块，将为 LLM 生成的 SQL 适配到目标数据库的方言语法，并在执行前进行静态安全校验。

### 6.1 方言解析链

方言信息的来源优先级为：数据源记录的 `dialect` 字段 → `CAPABILITIES` 注册的默认方言 → 回退为 `"postgres"`。`resolve_dialect()` 函数通过 dataset_id → datasource_id → Datasource 的链路完成解析，供 SQL 生成节点在组装 prompt 时使用。

### 6.2 标识符引用规范

不同数据库使用不同的标识符引用字符，`quote_ident()` 函数按方言返回正确的引用格式：

| 方言 | 引用格式 | 示例 |
|------|---------|------|
| `postgres` / `oracle` | 双引号 | `"column_name"` |
| `mysql` / `sqlite` / `hive` / `trino` / `presto` / `bigquery` / `clickhouse` | 反引号 | `` `column_name` `` |
| `tsql` / `sqlserver` / `mssql` | 方括号 | `[column_name]` |

### 6.3 NULL 比较规范化

LLM 在生成 `filter_sql`（行级过滤条件）时常写出非标准语法如 `finsh_time != null` 或 `column = null`。`sanitize_filter_sql()` 通过正则表达式将其替换为标准 SQL：

- `column != null` / `column <> null` → `column IS NOT NULL`
- `column = null` / `column == null` → `column IS NULL`

替换顺序确保 `!=` / `<>` 先处理，避免前面的替换改变后续匹配的上下文。

### 6.4 危险关键字黑名单

引擎维护了 `FORBIDDEN_SQL_KEYWORDS` 列表（`insert`、`update`、`delete`、`drop`、`alter`、`create`、`grant`、`truncate`），供 DSL 编译器和 `direct_sql` 路径共同使用，在 SQL 执行前进行关键字扫描拦截。

Sources: [sql_dialect.py](app/utils/sql_dialect.py#L1-L103), [sql_guard.py](app/utils/sql_guard.py#L1-L103)

## 七、SQL 执行守卫：多层静态安全校验

SQL Guard（`app/utils/sql_guard.py`）在 SQL 提交到数据库引擎之前执行 **纯静态安全校验**，不连接数据库，也不尝试证明 SQL 的业务语义正确性。它与方言适配紧密协作——方言信息同时用于 SQLGlot 解析和最后的结果行数规范化。

### 7.1 校验流水线

```mermaid
flowchart TD
    SQL([原始 SQL]) --> EMPTY{是否为空?}
    EMPTY --> |空| FAIL_EMPTY[EMPTY_SQL]
    EMPTY --> |非空| STRIP[删除注释<br/>_strip_comments]
    STRIP --> SANITIZE[NULL 比较规范化<br/>sanitize_filter_sql]
    SANITIZE --> MASK[屏蔽字符串内容<br/>_mask_quoted_content]
    MASK --> MULTI{是否多语句?<br/>分号拆分检测}
    MULTI --> |是| FAIL_MULTI[MULTI_STATEMENT]
    MULTI --> |否| KW_SCAN[危险关键字扫描<br/>_contains_forbidden_keyword]
    KW_SCAN --> |命中| FAIL_KW[FORBIDDEN_KEYWORD]
    KW_SCAN --> |通过| PAT_SCAN[危险模式扫描<br/>INTO OUTFILE / COPY PROGRAM]
    PAT_SCAN --> |命中| FAIL_PAT[危险语法拦截]
    PAT_SCAN --> |通过| PARSE[SQLGlot AST 解析<br/>_parse_with_sqlglot]
    PARSE --> |解析失败| FAIL_PARSE[PARSE_ERROR]
    PARSE --> |多语句 AST| FAIL_MULTI2[MULTI_STATEMENT]
    PARSE --> |通过| AST_KW[AST 节点安全检查<br/>_forbidden_expression]
    AST_KW --> |命中 DML/DDL| FAIL_AST[FORBIDDEN_KEYWORD]
    AST_KW --> |通过| TOKEN{首 token 是否为<br/>SELECT/WITH?}
    TOKEN --> |否| FAIL_READ[NOT_READONLY]
    TOKEN --> |是| TABLE_CHECK{表级授权校验<br/>_check_allowed_tables}
    TABLE_CHECK --> |未授权表| FAIL_TABLE[SQL_GUARD_BLOCKED]
    TABLE_CHECK --> |通过| FUNC_CHECK[危险函数扫描<br/>_contains_dangerous_function]
    FUNC_CHECK --> |命中 sleep 等| FAIL_FUNC[DANGEROUS_FUNCTION]
    FUNC_CHECK --> |通过| LIMIT[行数限制规范化<br/>_normalize_limit_with_sqlglot]
    LIMIT --> PASS([返回规范化 SQL])
```

### 7.2 双层危险检测

SQL Guard 执行 **两层** 安全检测：

- **文本层（正则）**：在屏蔽字符串内容后，扫描 16 种危险语句关键字（包括 `insert`、`update`、`delete`、`drop`、`alter`、`create`、`grant`、`truncate`、`merge`、`replace`、`call`、`execute` 等）、危险函数（`sleep`、`pg_sleep`、`benchmark` 等）和危险模式（`INTO OUTFILE`、`COPY PROGRAM`）
- **AST 层（SQLGlot）**：解析为 AST 后检查是否存在 `Insert`、`Update`、`Delete`、`Drop`、`Create`、`Alter`、`Merge`、`Command` 等表达式节点，并对 CTE（Common Table Expression）中的表名做去重处理

### 7.3 表级访问控制

当调用方提供了 `allowed_tables` 参数（来自数据集已选表列表），SQL Guard 会从 AST 中提取所有物理表名（排除 CTE 别名），逐一校验是否在授权列表中。未授权的表名将被拦截并返回 `SQL_GUARD_BLOCKED` 诊断码，附带被拦截的表名列表。

### 7.4 行数限制规范化

`_normalize_limit_with_sqlglot()` 通过 SQLGlot AST 读写 `LIMIT` 子句，按数据集查询约束（`query_constraints`）进行规范化：

- 未指定 `LIMIT` → 自动补充为 `default_limit`（默认 100）
- 指定了超过 `max_limit` → 裁剪为 `max_limit`（默认 1000）
- 已指定且在范围内 → 保持不变

修改操作直接在 AST 上进行，不依赖字符串拼接，确保语法正确。最终通过 `expression.sql(dialect=dialect)` 按目标方言串行化回 SQL 文本。

Sources: [sql_guard.py](app/utils/sql_guard.py#L1-L420), [query_constraints.py](app/utils/query_constraints.py#L1-L66)

## 八、数据源上下文构建：问数链路的统一数据契约

`build_datasource_context()` 函数将 `Datasource` ORM 模型转换为不可变的 `DatasourceContext` 数据类。该上下文对象作为问数链路（DSL 生成、SQL 编译、SQL 执行）中透传的数据契约，包含以下标准化字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `datasource_id` | int | 数据源主键 |
| `db_type` | str | 归一化后的数据库类型 |
| `dialect` | str | SQL 方言标识 |
| `driver` | str | 驱动名称 |
| `default_schema` | str | 默认 Schema |
| `allowed_tables` | list[str] | 当前数据集已授权表名列表 |
| `query_timeout_seconds` | int | 查询超时秒数 |
| `schema_version` | str | Schema 版本标识（可选） |

该上下文通过 `asdict()` 序列化为字典，在 LangGraph 工作流的状态对象中随消息流转。查询执行节点（`app/services/runner.py`）使用该上下文创建 Engine 并执行 SQL；SQL Guard 使用 `dialect` 和 `allowed_tables` 进行方言解析和表级权限校验。

Sources: [datasource.py](app/services/datasource.py#L700-L730)

## 九、企业离线部署方案：wheelhouse 驱动的内网安装

针对纯内网环境无法访问 PyPI 的场景，引擎设计了基于预下载 wheel 包的离线部署方案。

### 9.1 离线依赖清单

`requirements-enterprise.txt` 列出了基础开发环境（`requirements.txt`）之外的可选企业数据源驱动，与 `CAPABILITIES` 注册表中的 `driver_module` 一一对应：

| 驱动包 | 对应数据源 | 类型 |
|--------|-----------|------|
| `oracledb==2.5.1` | Oracle | wheel |
| `PyHive[hive_pure_sasl,presto]==0.7.0` | Hive + Presto | tar.gz |
| `trino==0.333.0` | Trino | wheel |
| `pyodbc==5.2.0` | SQL Server | wheel |
| `clickhouse-sqlalchemy==0.3.2` + `clickhouse-driver==0.2.9` | ClickHouse | tar.gz + wheel |
| `sqlalchemy-bigquery==1.12.1` + `google-cloud-bigquery-storage==2.26.0` | BigQuery | wheel |

### 9.2 下载与安装流程

```mermaid
flowchart LR
    A[有网构建机] --> |download_enterprise_wheels.sh| B[wheelhouse/ 目录]
    B --> |随制品打包| C[内网运行环境]
    C --> |pip install --no-index<br/>--find-links ./wheelhouse| D[企业数据源驱动就绪]
    D --> |restart 服务| E[创建 Oracle/Hive/... 数据源]
```

下载脚本 `scripts/download_enterprise_wheels.sh` 自动检测可用的 Python 解释器，逐级尝试项目虚拟环境 → 系统 python3 → 系统 python → macOS 预装路径，确保在各种环境下都能执行 `pip download`。

安装时使用 `--no-index` 禁止访问 PyPI，`--find-links` 指向本地 wheelhouse 目录，完全离线安装。

### 9.3 按需安装原则

不是所有部署都需要全部企业驱动。运维人员可以根据实际接入的数据源类型，选择性安装对应的驱动包。例如只接入 Oracle 和 ClickHouse 的环境只需安装 `oracledb` 和 `clickhouse-sqlalchemy` 两个包，避免引入不必要的依赖。

检测脚本通过 `get_capabilities()` 返回的 `driver_status: "missing"` 字段，告知前端哪些数据源类型缺少驱动，并提供明确的安装指引。

Sources: [requirements-enterprise.txt](requirements-enterprise.txt#L1-L29), [download_enterprise_wheels.sh](scripts/download_enterprise_wheels.sh#L1-L80), [datasource.py](app/services/datasource.py#L652-L688)

## 十、创建流程中的默认值补齐

当用户通过 API 创建或更新数据源时，`enrich_datasource_defaults()` 函数在写入数据库之前补齐缺失的能力字段：

| 字段 | 默认值来源 | 说明 |
|------|-----------|------|
| `db_type` | `normalize_db_type()` | 处理别名（如 `postgresql` → `postgres`） |
| `dialect` | `CAPABILITIES[db_type].dialect` | 仅当用户未提供时补齐 |
| `driver` | `CAPABILITIES[db_type].driver` | 仅当用户未提供时补齐 |
| `port` | `CAPABILITIES[db_type].default_port` | 仅当端口为空或为 0 时补齐 |
| `default_schema` | `CAPABILITIES[db_type].default_schema` | 仅当用户未提供时补齐 |
| `connection_options` | `{}` | 空字典而非 None |
| `connect_timeout_seconds` | `10` | 默认 10 秒 |
| `query_timeout_seconds` | `30` | 默认 30 秒 |

这种 "能力驱动的默认值注入" 确保了数据源记录的完整性，减少了前端表单的必填字段数量，同时保持了用户覆盖的灵活性——用户手动填写的值始终优先于能力注册表中的默认值。

Sources: [datasource.py](app/services/datasource.py#L690-L730)

## 延伸阅读

本文档覆盖了数据源连接引擎的完整架构。以下相关页面可进一步深入：

- **[SQL 执行守卫：静态安全校验、方言适配与自动修复审计](14-sql-zhi-xing-shou-wei-jing-tai-an-quan-xiao-yan-fang-yan-gua-pei-yu-zi-dong-xiu-fu-shen-ji)** — 了解 SQL Guard 的完整安全校验流水线和 SQLGlot AST 级别的安全控制
- **[Schema 召回与数据集问数上下文组装](12-schema-zhao-hui-yu-shu-ju-ji-wen-shu-shang-xia-wen-zu-zhuang)** — 了解从 SourceTable/SourceColumn 到 LLM prompt 上下文的完整链路
- **[DSL 生成、校验与 SQL 编译的逐节点实现](13-dsl-sheng-cheng-xiao-yan-yu-sql-bian-yi-de-zhu-jie-dian-shi-xian)** — 了解方言信息如何贯穿 DSL → SQL 的编译过程
- **[数据库迁移管理：Alembic 版本化与模型变更流程](28-shu-ju-ku-qian-yi-guan-li-alembic-ban-ben-hua-yu-mo-xing-bian-geng-liu-cheng)** — 了解 `Datasource` 模型的能力字段如何通过迁移脚本演进
- **[Docker Compose 本地开发环境：PostgreSQL + Langfuse 全家桶](29-docker-compose-ben-di-kai-fa-huan-jing-postgresql-langfuse-quan-jia-tong)** — 了解本地开发时如何拉起 PostgreSQL 作为目标数据源
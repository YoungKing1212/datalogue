# Datalogue API 编码规范手册

> 本规范旨在统一代码风格、保证代码质量、便于团队协作。
> 工具强制 + 文档指导双管齐下。

---

## 1. 代码风格与格式

### 1.1 工具链

| 工具 | 用途 | 命令 |
|------|------|------|
| **Black** | 代码格式化 | `black .` |
| **Ruff** | Linting + 导入排序 | `ruff check . && ruff format .` |
| **mypy** | 静态类型检查 | `mypy app/` |

**安装依赖：**
```bash
pip install black ruff mypy
```

**格式化/Linting 检查（开发时运行）：**
```bash
# 格式化
black app/ tests/ scripts/

# Linting
ruff check . --fix
ruff format .
```

### 1.2 格式化规范

- **缩进**：4 空格（项目已配置 `line-length = 100`）
- **引号**：优先使用双引号 `""`
- **导入顺序**：
  1. 标准库
  2. 第三方库
  3. 本地导入（`app.`）
  4. 空行分隔
- **行尾空格**：禁止
- **文件末尾**：保留一个空行

### 1.3 注释规范

**基本原则：优先使用描述性命名，注释用于解释"为什么"，而非"是什么"。**

- **文件头注释**：说明文件用途、核心概念
  ```python
  # 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流
  ```
- **函数/方法注释**：说明输入、输出、副作用
  ```python
  def encrypt_password(plain: str) -> str:
      """加密明文密码，使用 AES-GCM 加密。
      
      Args:
          plain: 明文密码
      Returns:
          Base64 编码的加密串（包含 nonce）
      """
  ```
- **复杂逻辑注释**：解释业务逻辑、算法决策
  ```python
      # 节点完成后，携带该节点的关键产出
      if is_done:
          if node_name == "intent_recognition":
  ```
- **TODO/FIXME**：标注待处理问题
  ```python
  # TODO: Phase 3 接入 HumanFeedback 节点
  ```

---

## 2. 项目架构与模块划分

### 2.1 目录结构

```
app/
├── __init__.py          # 包初始化
├── main.py              # FastAPI 应用入口
├── core/                # 核心模块
│   ├── config.py        # 配置管理（环境变量）
│   ├── database.py     # 数据库连接、会话
│   └── security.py     # 加密/解密工具
├── models/              # SQLAlchemy 模型
│   ├── base.py          # 基类（时间戳混入）
│   ├── conversation.py  # 对话相关模型
│   ├── datasource.py   # 数据源模型
│   └── dataset.py       # 数据集/指标/维度模型
├── schemas/             # Pydantic 请求/响应模型
│   ├── chat.py          # 聊天相关 Schema
│   ├── conversation.py  # 对话相关 Schema
│   ├── datasource.py   # 数据源相关 Schema
│   └── dataset.py       # 数据集相关 Schema
├── api/                 # API 路由
│   ├── chat.py          # 聊天路由
│   ├── conversation.py  # 对话路由
│   ├── datasource.py   # 数据源路由
│   └── dataset.py       # 数据集路由
├── services/            # 业务逻辑层
│   └── datasource.py    # 数据源服务
├── graph/               # LangGraph 工作流
│   ├── llm.py          # LLM 配置
│   ├── nodes.py        # 节点定义
│   ├── state.py        # 状态定义
│   └── workflow.py     # 工作流构建
```

### 2.2 模块职责

| 模块 | 职责 | 依赖方向 |
|------|------|----------|
| `api/` | 接收请求、参数校验、路由分发 | 依赖 `services/`、`schemas/` |
| `services/` | 业务逻辑处理、数据转换 | 依赖 `models/`、`core/` |
| `models/` | 数据库表结构、ORM 映射 | 依赖 `core/database.py` |
| `schemas/` | 请求/响应数据验证 | 无外部依赖 |
| `graph/` | AI 工作流编排 | 依赖 `services/`、`models/` |
| `core/` | 基础设施（配置、数据库、安全） | 无外部依赖 |

### 2.3 模块导入规则

- **禁止循环导入**：通过重构或依赖注入解决
- **顶层导入**：在文件顶部完成所有导入
- **延迟导入**：仅在函数内部需要的模块，在函数内导入

---

## 3. API 设计规范

### 3.1 路由设计

```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

@router.post("/stream")                    # POST /api/chat/stream
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    ...
```

**命名规范：**
- 路由使用小写 + 下划线：`/chat/stream`、`/dataset/list`
- 资源复数形式：`/datasources`、`/datasets`
- 动作明确：`/feedback`、`/search`

### 3.2 请求/响应模型

**使用 Pydantic Schema：**

```python
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    """问数请求"""
    question: str = Field(..., min_length=1, max_length=500)
    dataset_id: int
    conversation_id: int | None = None

    model_config = {"json_schema_extra": {"example": {"question": "上周销售额是多少", "dataset_id": 1}}}
```

**响应格式统一：**

```python
# 成功响应
return {"status": "ok", "data": {...}}

# 错误响应
raise HTTPException(status_code=404, detail="对话不存在")
```

### 3.3 状态码规范

| 状态码 | 场景 |
|--------|------|
| 200 | 成功响应 |
| 201 | 资源创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

### 3.4 分页规范

```python
class PaginatedResponse(BaseModel):
    """分页响应"""
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_more: bool
```

---

## 4. 数据库与模型规范

### 4.1 SQLAlchemy 模型

**基类与混入：**

```python
from app.core.database import Base
from app.models.base import TimestampMixin

class SemanticDataset(Base, TimestampMixin):
    __tablename__ = "semantic_dataset"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
```

**表命名规范：** `snake_case` 复数形式
**列命名规范：** `snake_case`

### 4.2 字段类型选择

| 数据类型 | SQLAlchemy 类型 | 说明 |
|----------|-----------------|------|
| 字符串 | `String(length)` | 固定长度用 `String`，不确定用 `Text` |
| 整数 | `Integer` | - |
| 布尔 | `Boolean` | - |
| JSON | `JSON` | 用于存储结构化数据 |
| 时间 | `DateTime` | 使用 SQLAlchemy 的 `func.now()` |

### 4.3 关系定义

```python
from sqlalchemy.orm import relationship

class SemanticDataset(Base, TimestampMixin):
    # 一对多：父侧定义外键，子侧用 backref
    datasource = relationship("Datasource", backref="datasets")
    metrics = relationship("SemanticMetric", backref="dataset", cascade="all, delete-orphan")
```

### 4.4 Pydantic Schema

**命名规范：**
- 请求模型：`XxxRequest`（如 `ChatRequest`）
- 响应模型：`XxxResponse`（如 `ChatResponse`）
- 创建模型：`XxxCreate`（如 `DatasetCreate`）
- 更新模型：`XxxUpdate`（如 `DatasetUpdate`）

```python
class SemanticMetricCreate(BaseModel):
    """指标创建模型"""
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    expr: str = Field(..., min_length=1)
    filter_sql: str | None = None
    synonyms: list[str] | None = None
```

### 4.5 数据库迁移

使用 Alembic 进行数据库迁移：

```bash
# 创建迁移
alembic revision --autogenerate -m "描述"

# 应用迁移
alembic upgrade head
```

---

## 5. 测试要求

### 5.1 测试框架

使用 **pytest** + **pytest-asyncio**（已配置 `asyncio_mode = "auto"`）

### 5.2 测试文件结构

```
tests/
├── conftest.py              # 共享 fixtures
├── test_security.py         # 安全模块测试
├── test_chat.py            # 聊天功能测试
├── test_conversation.py    # 对话功能测试
├── test_datasource.py      # 数据源功能测试
└── test_dataset.py         # 数据集功能测试
```

### 5.3 测试规范

**Fixture 命名与作用域：**

```python
@pytest.fixture(scope="function")      # 每个测试函数独立
def db_session(engine):
    ...

@pytest.fixture(scope="session")       # 整个测试会话共享
def engine():
    ...
```

**测试函数命名：** `test_<模块>_<行为>`

```python
def test_chat_stream_returns_sse_events(client, sample_dataset):
    ...

def test_dataset_create_with_metrics(db_session, sample_datasource):
    ...
```

### 5.4 测试覆盖目标

- **核心业务逻辑**：必须有测试（chat、workflow、DSL 生成）
- **API 端点**：关键端点必须有测试
- **工具函数**：纯函数必须有测试

**覆盖率目标：**
- 新增代码覆盖率不低于 70%
- 核心模块（graph/、services/）覆盖率不低于 80%

### 5.5 测试数据库

测试使用 SQLite 内存数据库：

```python
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

---

## 6. 安全与权限控制

### 6.1 认证

- 使用 JWT Token 进行身份认证
- Token 过期时间：建议 24 小时
- 敏感操作需要重新验证

### 6.2 密码加密

**使用项目已有的 AES-GCM 加密：**

```python
from app.core.security import encrypt_password, decrypt_password

# 加密
cipher = encrypt_password("plain_password")

# 解密
plain = decrypt_password(cipher)
```

### 6.3 输入验证

- 所有外部输入必须通过 Pydantic Schema 验证
- SQL 参数使用 ORM 参数化查询（防止 SQL 注入）
- 避免使用字符串拼接 SQL

### 6.4 CORS 配置

当前配置允许所有来源（开发环境）：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 6.5 敏感信息处理

- **禁止硬编码**：所有配置通过环境变量或 `.env` 文件
- **日志脱敏**：敏感信息（密码、Token）在日志中脱敏
- **密码不回传**：API 响应中不包含密码字段

---

## 7. 日志与监控

### 7.1 日志配置

使用 Python 标准库 `logging`：

```python
import logging

logger = logging.getLogger(__name__)
```

### 7.2 日志级别

| 级别 | 场景 |
|------|------|
| DEBUG | 开发调试信息 |
| INFO | 正常流程信息（如请求入口、关键节点） |
| WARNING | 异常但不中断（如重试） |
| ERROR | 错误需要调查 |
| CRITICAL | 严重错误导致服务不可用 |

### 7.3 日志格式

```python
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
```

### 7.4 日志记录规范

**记录关键节点：**

```python
logger.info(f"[_stream_chat] 开始处理问题: {payload.question[:50]}")
logger.info(f"[_stream_chat] stream 完成，共 {event_count} 个事件")
```

**记录异常：**

```python
logger.exception(f"[_stream_chat] 工作流异常: {e}")
# logger.exception 会自动包含堆栈信息
```

### 7.5 关键监控点

- API 请求量与响应时间
- 数据库查询时间
- LLM 调用次数与 Token 用量
- 工作流节点执行时间

---

## 8. 错误处理

### 8.1 异常分类

| 类型 | 处理方式 | HTTP 状态码 |
|------|----------|-------------|
| 参数验证失败 | 422 Unprocessable Entity | 422 |
| 资源不存在 | 404 Not Found | 404 |
| 权限不足 | 403 Forbidden | 403 |
| 未认证 | 401 Unauthorized | 401 |
| 业务逻辑错误 | HTTPException | 400 或业务状态码 |
| 内部错误 | 500 Internal Server Error | 500 |

### 8.2 统一错误响应

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="对话不存在")
# 响应：{"detail": "对话不存在"}
```

### 8.3 异常处理原则

- **不暴露内部细节**：错误信息对用户友好，不泄露技术细节
- **记录完整堆栈**：使用 `logger.exception()` 记录
- **优雅降级**：工作流异常时返回友好响应

```python
if not answer:
    answer = "抱歉，暂时无法回答这个问题。请检查语义层是否已配置。"
```

---

## 9. 文档要求

### 9.1 代码注释

见第 1.3 节。

### 9.2 API 文档

FastAPI 自动生成 OpenAPI 文档。路由应包含 docstring：

```python
@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """流式问数接口，返回 SSE 事件流。"""
    ...
```

### 9.3 README

每个项目应包含 README.md，包含：
- 项目简介
- 环境要求
- 安装步骤
- 运行方式
- 主要功能说明

### 9.4 变更记录

- 代码变更应记录在 commit message
- 重要功能添加可以更新 README
- 数据库迁移需要记录迁移文件

---

## 10. 静态类型检查

### 10.1 mypy 配置

在 `pyproject.toml` 中添加：

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
disallow_incomplete_defs = false
check_untyped_defs = true
disallow_untyped_decorators = false
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
disallow_any_generics = false
strict_optional = true
```

**安装：**
```bash
pip install mypy
```

**运行：**
```bash
mypy app/
```

### 10.2 类型注解规范

**函数签名必须标注：**

```python
from typing import list, dict, Any

def process_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ...

def encrypt_password(plain: str) -> str:
    ...
```

**复杂类型使用 TypeAlias：**

```python
from typing import TypeAlias

SqlList: TypeAlias = list[str]
```

**可选参数：**

```python
def create_dataset(name: str, description: str | None = None) -> SemanticDataset:
    ...
```

### 10.3 类型检查原则

- **公共 API 必须标注**：函数签名对外暴露，必须标注
- **内部函数尽量标注**：提高代码可读性
- **避免 `Any` 滥用**：仅在无法确定类型时使用

---

## 附录：工具配置汇总

### A.1 pyproject.toml 完整配置

```toml
[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]  # 与 Black 冲突，已由 Black 处理

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
check_untyped_defs = true
strict_optional = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### A.2 pre-commit hook（可选）

创建 `.git/hooks/pre-commit`：

```bash
#!/bin/bash
echo "运行格式化检查..."
black --check app/ tests/ scripts/ || exit 1
ruff check . --fix || exit 1
echo "格式检查通过"
```

---

## 变更记录

| 日期 | 版本 | 变更说明 |
|------|------|----------|
| 2026-05-31 | 1.0.0 | 初始版本 |
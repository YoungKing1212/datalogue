# Datalogue API 项目规范

## 项目概述

- **项目名称**: Datalogue API（数语 AI 原生智能问数平台后端）
- **技术栈**: Python 3.11 + FastAPI + SQLAlchemy + LangGraph
- **代码规范**: 参见 `docs/CODE_STYLE.md`

---

## 代码风格

### 工具链

| 工具 | 用途 | 命令 |
|------|------|------|
| **Black** | 代码格式化 | `black .` |
| **Ruff** | Linting + 导入排序 | `ruff check . --fix` |
| **mypy** | 静态类型检查 | `mypy app/` |

### 格式化要求

- 缩进：4 空格
- 行长度：100 字符
- 导入顺序：stdlib → third-party → local
- 无行尾空格
- 文件末尾保留一个空行

### 注释规范

**基本原则：优先使用描述性命名，注释用于解释"为什么"，而非"是什么"。**

- **文件头注释**：说明文件用途
  ```python
  # 问数对话路由 — SSE 流式输出 + LangGraph Agent 工作流
  ```
- **函数注释**：说明输入、输出、副作用
  ```python
  def encrypt_password(plain: str) -> str:
      """加密明文密码，使用 AES-GCM 加密。
      
      Args:
          plain: 明文密码
      Returns:
          Base64 编码的加密串（包含 nonce）
      """
  ```
- **复杂逻辑注释**：解释业务决策
- **TODO/FIXME**：标注待处理问题

---

## 类型注解

### 必须标注

- 所有公共函数/方法的签名
- 类属性（如果非 Optional）

### 标注示例

```python
from typing import list, dict, Any

def process_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ...

def create_dataset(name: str, description: str | None = None) -> SemanticDataset:
    ...
```

### 类型检查

```bash
mypy app/
```

---

## 项目结构

```
app/
├── __init__.py
├── main.py              # FastAPI 应用入口
├── core/                # 核心模块（config、database、security）
├── models/              # SQLAlchemy 模型
├── schemas/             # Pydantic Schema
├── api/                 # API 路由
├── services/            # 业务逻辑
└── graph/               # LangGraph 工作流
```

---

## API 设计规范

- 路由命名：小写 + 下划线（`/chat/stream`）
- 资源复数形式（`/datasources`、`/datasets`）
- 请求/响应使用 Pydantic Schema
- 状态码：200/201/400/401/403/404/422/500

---

## 数据库规范

- 表命名：`snake_case` 复数形式
- 列命名：`snake_case`
- 外键关系明确使用 `relationship`
- 迁移使用 Alembic

---

## 测试规范

### 命名

- 文件：`test_<模块>.py`
- 函数：`test_<模块>_<行为>`

### Fixture 作用域

- `scope="function"`：每个测试函数独立
- `scope="session"`：整个会话共享

### 覆盖率目标

- 核心模块（graph/、services/）：≥80%
- 新增代码：≥70%

---

## 安全要求

- 所有外部输入通过 Pydantic Schema 验证
- 敏感信息使用 `app.core.security` 加密
- 禁止硬编码，使用环境变量
- 日志中脱敏敏感信息

---

## 日志规范

- 使用 `logging.getLogger(__name__)`
- 关键节点记录 INFO 级别
- 异常使用 `logger.exception()`
- 日志格式：`%(asctime)s - %(name)s - %(levelname)s - %(message)s`

---

## 错误处理

- 使用 `HTTPException` 处理业务异常
- 错误信息对用户友好，不暴露技术细节
- 工作流异常优雅降级

---

## 提交前检查

```bash
# 格式化
black app/ tests/ scripts/

# Linting
ruff check . --fix

# 类型检查
mypy app/

# 测试
pytest tests/ -v
```

详细规范见 `docs/CODE_STYLE.md`，审查清单见 `docs/CHECKLIST.md`。

---

## 工作流程

### 实现功能

1. 阅读 `docs/CODE_STYLE.md` 了解规范
2. 编写代码，添加类型注解
3. 运行格式化工具
4. 运行类型检查
5. 编写测试
6. 自检 `docs/CHECKLIST.md`
7. 提交代码

### 代码审查

使用 `docs/CHECKLIST.md` 进行自检，确保：
- [ ] 格式化通过（Black、Ruff）
- [ ] 类型检查通过（mypy）
- [ ] 测试通过（pytest）
- [ ] 注释完整（中文优先）
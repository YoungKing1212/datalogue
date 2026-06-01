# 代码审查检查清单

> 在提交代码前自行检查，确保符合编码规范。

---

## 1. 代码格式与风格

- [ ] Black 格式化通过：`black --check app/ tests/`
- [ ] Ruff 检查通过：`ruff check .`
- [ ] 无行尾空格
- [ ] 文件末尾保留一个空行
- [ ] 导入顺序正确（stdlib → third-party → local）

## 2. 类型注解

- [ ] 公共函数/方法有类型注解
- [ ] 可选参数正确标注（`X | None` 而非 `Optional[X]`）
- [ ] 无不必要的 `Any` 类型
- [ ] mypy 检查通过：`mypy app/`

## 3. 注释

- [ ] 文件头有用途说明注释
- [ ] 复杂业务逻辑有解释性注释
- [ ] TODO/FIXME 有标注说明
- [ ] 函数/方法有 docstring（参数、返回值说明）

## 4. API 设计

- [ ] 路由命名符合规范（小写 + 下划线）
- [ ] 请求/响应使用 Pydantic Schema 验证
- [ ] 正确使用 HTTP 状态码
- [ ] 错误信息对用户友好

## 5. 数据库

- [ ] 模型命名符合规范（snake_case）
- [ ] 外键关系明确定义
- [ ] 敏感字段加密存储（如密码）
- [ ] 数据库迁移文件已创建（如有 schema 变更）

## 6. 测试

- [ ] 新功能有对应测试
- [ ] 测试函数命名：`test_<模块>_<行为>`
- [ ] 使用合适的 fixture scope
- [ ] 测试可通过：`pytest tests/`

## 7. 安全

- [ ] 无硬编码敏感信息
- [ ] 用户输入有验证
- [ ] SQL 使用参数化查询（ORM 自动处理）
- [ ] 敏感信息日志脱敏

## 8. 日志

- [ ] 关键节点有日志记录
- [ ] 使用合适的日志级别
- [ ] 异常使用 `logger.exception()` 记录堆栈

## 9. 错误处理

- [ ] 异常有明确处理
- [ ] 不暴露内部错误细节给用户
- [ ] 工作流异常有优雅降级

## 10. 文档

- [ ] README 更新（如有新功能）
- [ ] 路由有 docstring 说明
- [ ] commit message 清晰描述变更内容

---

## 快速检查命令

```bash
# 格式化检查
black --check app/ tests/ scripts/

# Linting
ruff check . --fix

# 类型检查
mypy app/

# 运行测试
pytest tests/ -v
```

---

## 提交前自检流程

1. 运行 `black --check` 和 `ruff check`
2. 运行 `mypy app/` 检查类型
3. 运行 `pytest tests/` 确保测试通过
4. 确认所有清单项
5. 提交代码
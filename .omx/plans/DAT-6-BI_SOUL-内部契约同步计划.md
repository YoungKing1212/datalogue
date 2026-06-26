# DAT-6 BI_SOUL 内部契约同步计划

## Requirements Summary

- 新增 `datalogue-api/app/contracts/BI_SOUL.md` 作为 BI 不可越界协议的内部 source of truth。
- 新增 `datalogue-api/app/services/soul_contract_sync.py`，负责读取内部契约、规范化同步块、校验 Hermes skill SOUL，并为未来 AgentScopeShellAdapter 输出 policy 注入文本。
- 修改 `hermes-skills/datalogue/SOUL.md`，同步内部契约中对外层 Agent 的限制。
- 新增 `datalogue-api/tests/test_bi_soul_contract.py`，覆盖内部契约存在、Hermes 同步一致、AgentScope policy 仅允许 `ask_bi` 且不暴露 schema/SQL/control_plane 工具。

## Acceptance Criteria

- `BI_SOUL.md` 明确写出：LeadAgent 不看字段级 schema 明细；外层 Agent 只能调用 `ask_bi`；LLM 不直接生成可执行 SQL；raw SQL/raw result/capsule/trace 主体属于 `control_plane`。
- Hermes `SOUL.md` 包含由内部契约同步出的同一段规范化契约，避免外层 Hermes skill 绕过 BI 内核。
- `render_agentscope_shell_policy()` 返回的 policy 明确只允许 `ask_bi`，并声明 AgentScopeShellAdapter 不替代 Datalogue 真相源。
- `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_soul_contract.py -q` 通过。

## Implementation Steps

1. 先写 `datalogue-api/tests/test_bi_soul_contract.py`，验证缺失契约时失败，锁定同步目标。
2. 新建 `datalogue-api/app/contracts/BI_SOUL.md`，使用可机器抽取的同步块包住外部入口契约。
3. 新建 `datalogue-api/app/services/soul_contract_sync.py`，提供 `load_internal_bi_soul()`、`load_hermes_skill_soul()`、`normalize_contract()`、`assert_hermes_soul_synced()`、`render_agentscope_shell_policy()`。
4. 更新 `hermes-skills/datalogue/SOUL.md`，嵌入内部契约同步块，同时保留现有语义资产/只读预览说明。
5. 更新 `.codex/project-memory.md` 完成功能记录。

## Risks and Mitigations

- 风险：当前仓库没有 `AgentScopeShellAdapter` 文件，直接修改会扩大范围。缓解：本次只提供可被 adapter 注入的 policy 渲染函数，并在测试中固定其边界。
- 风险：Hermes 仍有只读 SQL preview 能力，容易被理解为外层 Agent 可直接绕过 BI。缓解：同步契约明确 SQL preview 仅是受 Guard 的语义资产预览路径，不是 Chat/BI 主链，外层问数入口只能走 `ask_bi`。

## Verification Steps

- `cd datalogue-api && .venv/bin/python -m pytest tests/test_bi_soul_contract.py -q`

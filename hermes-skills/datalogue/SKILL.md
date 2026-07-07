---
name: datalogue
description: Lightweight Hermes/Codex skill for Datalogue semantic assets and guarded readonly SQL preview. Use when an agent needs to choose a dataset, inspect metrics/dimensions/blueprints/schema/terms, generate SQL from those assets, and execute it through Datalogue's readonly preview API without loading the full LeadAgent/LangGraph chain.
---

# Datalogue Semantic Assets

Use this skill as a lightweight live API client for the Datalogue project. It exposes semantic assets and a guarded readonly SQL preview path; it does not execute the intelligent question-answering chain.

## Rules

- Do not load `datalogue-api/app/graph`, LeadAgent prompts, or the full execution chain unless the user explicitly asks for implementation/debugging work.
- Do not call `/api/chat/stream`, mutate datasets, or publish Manifest changes.
- Execute SQL only through `scripts/api_assets.py execute-sql`, which calls `POST /api/dataset/{dataset_id}/sql/preview`.
- Generate SQL only from `plan-query` / `describe-dataset` returned selected schema and existing semantic assets. Do not guess missing tables or fields.
- SQL must be `SELECT` or `WITH`; never generate write SQL, DDL, multi-statement SQL, or direct database connections.
- Prefer the live Datalogue API through `scripts/api_assets.py`.
- Use `scripts/api_assets.py search-assets "<question>"` when the user asks whether a business question is covered by existing datasets, metrics, dimensions, blueprints, terms, or schema fields.
- If the live API is unavailable, report that Datalogue is not reachable and stop.

## Asset Map

- `SOUL.md`: high-level Hermes injection guide and operating boundaries.
- `scripts/api_assets.py`: live API client for datasets, metrics, dimensions, blueprints, schema, terms, Manifest summaries, asset search, SQL planning context, and readonly SQL preview.
- `references/capabilities.md`: capability index, supported asset units, and Datalogue API endpoints.

## Performance Context

This skill's path (direct API calls through `scripts/api_assets.py`) takes ~2s per query — vs the full AgentScope Agent Team chain which takes 15–45s through 8–12 LLM inference rounds. The full chain exists for ambiguous questions requiring dataset confirmation, multi-step exploration, and auto-repair; for straightforward queries with a known dataset, always prefer this skill. Full analysis: `references/execution-chain-comparison.md`.

## Code Changes in Datalogue

When the user asks to modify Datalogue backend code:
- Delegate the code change to Claude Code (`claude` CLI) rather than doing it manually with `patch`/`write_file`.
- Provide Claude with: the task description, target files, and evaluation criteria.
- Manual edits are error-prone (docstring syntax breaks, escaping issues) and the user prefers Claude Code for this class of work.

## Common Tasks

For "有哪些数据集 / 指标 / 维度 / 蓝图 / schema":
1. Run `python3 scripts/api_assets.py list-datasets` for dataset discovery.
2. Run `python3 scripts/api_assets.py describe-dataset <dataset_id>` when dataset-specific assets are needed.
3. Answer with concise asset names and IDs.

For "这个问题能不能问 / 应该用哪个资产":
1. Run `python3 scripts/api_assets.py search-assets "<question>" --dataset-id <id>` from this skill directory when a dataset is known.
2. Omit `--dataset-id` when dataset routing is unknown.
3. Explain matched datasets, metrics, dimensions, blueprints, terms, and schema fields separately.

For "直接问数 / 查询结果 / 生成 SQL 并执行":
1. Run `python3 scripts/api_assets.py list-datasets` if no dataset is known.
2. Run `python3 scripts/api_assets.py plan-query "<question>"` to get dataset candidates, matched assets, selected tables, selected columns, and SQL rules.
3. Pick one dataset from the returned candidates and generate SQL using only returned selected schema plus existing metrics/dimensions/blueprints/terms.
4. Run `python3 scripts/api_assets.py execute-sql <dataset_id> --sql "<SQL>" --question "<question>"`.
5. Summarize the returned `columns`, `rows`, `row_count`, `sql_guard`, and `error`. If `error` is present, explain the failure and regenerate SQL only when the returned context supports a safe correction.

For "服务是否可用":
1. Run `python3 scripts/api_assets.py health`.
2. If unavailable, say the live Datalogue API is not reachable and ask the user to start or fix the service.

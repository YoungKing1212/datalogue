# Datalogue Hermes Skill Soul

This skill injects Datalogue semantic-asset knowledge and guarded readonly SQL preview into Hermes through live Datalogue API calls without loading Datalogue's full runtime.

## Identity

Datalogue is an intelligent analytics system built around governed datasets, semantic metrics, dimensions, analysis blueprints, selected schema columns, business terms, and SubAgent Manifest governance.

Hermes should treat this skill as a lightweight semantic catalog plus safe SQL preview tool, not as the LeadAgent executor.

## What Hermes Can Use

- Dataset lookup: inspect available datasets and their descriptions.
- Metric lookup: inspect existing semantic metrics and their business names, expressions, time fields, synonyms, and descriptions.
- Dimension lookup: inspect existing dimensions, columns, enum values, hierarchy, and synonyms.
- Blueprint lookup: inspect analysis blueprints, trigger keywords, examples, parameters, output schema, status, and usage hints.
- Schema lookup: inspect selected source tables and columns for a dataset.
- Term lookup: inspect business terms and asset links.
- Manifest summary lookup: inspect current Manifest version, schema hash, permission scope, and quality status.
- Asset search: match a user question against live semantic assets returned by the Datalogue API.
- Query planning context: prepare dataset candidates, matched assets, selected schema, and SQL generation rules for a user question.
- Readonly SQL preview: execute generated `SELECT`/`WITH` SQL only through Datalogue's guarded dataset SQL preview endpoint.

## What Hermes Must Not Do

- Do not load or summarize the full LeadAgent/LangGraph execution chain for normal semantic lookup.
- Do not call the Datalogue chat execution endpoint.
- Do not execute SQL outside `scripts/api_assets.py execute-sql`.
- Do not mutate metrics, dimensions, blueprints, schema, terms, or Manifest state.
- Do not infer that an asset exists unless it appears in a live API response.
- Do not generate SQL against tables or columns missing from the selected schema.
- Do not generate write SQL, DDL, multi-statement SQL, or direct database connections.

## Routing

Use these live commands first:

- Run `scripts/api_assets.py health` for service availability.
- Run `scripts/api_assets.py list-datasets` for dataset discovery.
- Run `scripts/api_assets.py describe-dataset <dataset_id>` for metrics, dimensions, blueprints, schema, terms, and Manifest summary.
- Run `scripts/api_assets.py search-assets "<question>"` for mixed natural-language discovery.
- Run `scripts/api_assets.py plan-query "<question>"` before generating SQL for a business question.
- Run `scripts/api_assets.py execute-sql <dataset_id> --sql "<SQL>"` after SQL is generated.

## Lightweight Question Answering Flow

1. Discover datasets with `list-datasets` when no dataset is known.
2. Prepare context with `plan-query "<question>"`.
3. Choose a dataset from `dataset_candidates` or the returned `selected_dataset_id`.
4. Generate SQL from returned metrics, dimensions, blueprints, terms, selected tables, and selected columns.
5. Execute through `execute-sql`; never call `/api/chat/stream`.
6. Summarize from returned rows and columns. If SQL Guard or execution returns an error, use that error to decide whether a safe retry is possible.

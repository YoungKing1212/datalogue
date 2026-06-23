# Datalogue Asset Capabilities

This reference maps the lightweight Hermes skill capabilities to Datalogue's existing semantic asset surfaces.

## Capability Units

- `dataset_lookup`: list and describe datasets.
- `metric_lookup`: list existing metrics by dataset.
- `dimension_lookup`: list existing dimensions by dataset.
- `blueprint_lookup`: list analysis blueprints by dataset.
- `schema_lookup`: list selected source tables and selected source columns by dataset.
- `term_lookup`: list business terms by dataset.
- `manifest_lookup`: inspect current SubAgent Manifest summary by dataset.
- `asset_search`: rank live API assets against a natural-language question.
- `query_plan_context`: assemble dataset candidates, matched assets, selected schema, and SQL generation constraints for Hermes.
- `readonly_sql_preview`: execute generated readonly SQL through Datalogue's guarded dataset preview endpoint.

## Source API Surfaces

These are the existing Datalogue API surfaces called by `scripts/api_assets.py`:

- `GET /api/dataset`
- `GET /api/dataset/{ds_id}`
- `GET /api/dataset/{ds_id}/metrics`
- `GET /api/dataset/{ds_id}/dimensions`
- `GET /api/dataset/{ds_id}/terms`
- `GET /api/dataset/{ds_id}/blueprints`
- `GET /api/dataset/{ds_id}/selected-tables`
- `GET /api/dataset/{ds_id}/selected-columns`
- `GET /api/dataset/{ds_id}/subagent-manifest`
- `GET /api/dataset/subagent-manifests/current`
- `POST /api/dataset/{ds_id}/sql/preview`

## Runtime Boundary

This skill intentionally does not expose:

- LeadAgent planner prompt contents.
- LangGraph node implementation details.
- Chat execution over `/api/chat/stream`.
- Direct database connections or unrestricted SQL execution.
- Any write endpoint.

Hermes should use this skill to know what Datalogue can talk about and to run guarded readonly previews, not to run the Datalogue agent.

## SQL Preview Contract

`execute-sql` calls:

```http
POST /api/dataset/{ds_id}/sql/preview
```

Request body:

```json
{
  "question": "optional original question",
  "sql": "SELECT ...",
  "limit": 100
}
```

Response body includes:

- `dataset_id`
- `sql`: normalized SQL that was executed or attempted
- `columns`
- `rows`
- `row_count`
- `sql_guard`
- `error`

The backend only allows `SELECT` / `WITH`, blocks unselected tables, applies dataset `query_constraints`, and executes through the dataset-bound datasource.

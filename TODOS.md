# Datalogue TODOs

## 后续任务：数据结果与报告产物 artifact store

- What: 将 SQL 原始结果集和完整报告 markdown 落到 artifact store，跨轮状态、消息上下文和 `last_success_task` 只保留 `result_ref` / `report_id` / `display_summary`。
- Why: 继续压缩长期上下文，避免大结果集和完整报告进入 LLM 承接态。
- Context: 当前主爆点是 `_thread.last_success_task.query_plan.selected_assets/rejected_assets/debug`，本 PR 只修 `last_success_task` 白名单、schema drift 降级和 size guard；artifact store 属于下一阶段产物边界治理。
- Depends on / blocked by: 等 `LastSuccessTask` 最小承接 schema 落地后再做，避免同一个 PR 同时改两类持久化契约。
- Suggested scope: 独立 PR，覆盖数据表/缓存 TTL、权限边界、报告摘要、结果引用读取和 trace metadata。

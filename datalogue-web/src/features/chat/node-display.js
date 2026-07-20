// Chat 用户可见节点名称的唯一前端映射；后端 display_name 为权威值，本表只处理旧历史与流式兜底。
export const NODE_DISPLAY_NAMES = Object.freeze({
  message_gateway: '任务理解',
  'message-gateway': '任务理解',
  lead_agent_tools: '能力匹配',
  manifest_route: '场景匹配',
  clarification_resolution: '澄清处理',
  intent_recognition: '意图识别',
  entry_intent_classification: '入口判断',
  analysis_blueprint_execute: '分析蓝图执行',
  candidate_assets: '数据资产匹配',
  'subagent.candidate_assets': '数据资产匹配',
  query_plan: '查询规划',
  'subagent.query_plan': '查询规划',
  schema_recall: '数据范围确认',
  term_normalize_node: '术语标准化',
  semantic_asset_resolution_node: '语义资产解析',
  metric_resolution_node: '指标解析',
  dsl_generate: '查询生成',
  dsl_validate: '查询校验',
  dsl_compiler: '执行计划生成',
  sql_execute: '查询执行',
  sql_audit: '结果诊断',
  repair_patch: '自动修复',
  report_generator: '结果整理',
  reasoning_summary: '处理摘要',
  live_thinking: '分析进度',
  multi_agent_handoff: 'Agent 协作',
  confirmation: '待确认',
  'agent-worker-thinking': '分析进度',
});

export function nodeDisplayName(node, displayName, fallback = '任务处理') {
  return NODE_DISPLAY_NAMES[node] || NODE_DISPLAY_NAMES[displayName] || fallback;
}

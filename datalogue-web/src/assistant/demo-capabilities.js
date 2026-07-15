// 演示能力等级由 Vite 构建环境决定；未配置时按前三期的收敛展示处理。
export const DEMO_CAPABILITY_LEVELS = Object.freeze({
  SINGLE_TABLE: 'single_table',
  MULTI_TABLE: 'multi_table',
  SEMANTIC_METRICS: 'semantic_metrics',
  AGENT_TEAM: 'agent_team',
});

const VALID_LEVELS = new Set(Object.values(DEMO_CAPABILITY_LEVELS));

export function resolveDemoCapabilityLevel(env = import.meta.env) {
  const configured = String(env?.VITE_DATALOGUE_DEMO_CAPABILITY_LEVEL || '').trim().toLowerCase();
  // 默认不暴露子智能体，避免未设置演示配置时提前展示第四期能力。
  return VALID_LEVELS.has(configured) ? configured : DEMO_CAPABILITY_LEVELS.SINGLE_TABLE;
}

export function exposesAgentTeam(capabilityLevel = resolveDemoCapabilityLevel()) {
  return capabilityLevel === DEMO_CAPABILITY_LEVELS.AGENT_TEAM;
}

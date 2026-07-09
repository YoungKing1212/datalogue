// Agent Team envelope 到旧 ChatModelAdapter 内部事件的迁移适配。

const INTERNAL_TEXT_PATTERN = /\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|with)\b|[`;]|hidden_table|\b\w+_col\b|raw_result|raw_rows?|schema|repairpatch|blueprint/i;
const PROGRESSIVE_EVENT_LABELS = {
  bi_worker_l0_capability: '数据集能力',
  bi_worker_l1_assets: '数据资产匹配',
  bi_worker_l2_schema_slice: '数据结构确认',
  bi_worker_l3_value_profile: '候选值覆盖',
  bi_worker_l4_validation: '查询支持度',
  bi_worker_repair_request: '查询修复',
};
const PROGRESSIVE_INTERNAL_TEXT_PATTERN = /[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]*|\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|with)\b|[`;]|raw_error|raw_rows?|schema|filters?|selects?|entities|relationships/i;
const SAFE_CONTRACT_ERROR_PATTERN = /^[a-z_]+:[A-Za-z0-9_.]+$/;

function safeText(value, fallback = '') {
  if (value == null) return fallback;
  const text = String(value).trim();
  if (!text || INTERNAL_TEXT_PATTERN.test(text)) return fallback;
  return text.slice(0, 160);
}

function safeAgentName(value) {
  return safeText(value, '').replace(/[^\w.-]+/g, '_').slice(0, 80);
}

function safeProgressiveSummary(payload = {}, label = '执行进展') {
  const repairSummary = safeRepairRequestSummary(payload);
  if (repairSummary) return repairSummary;
  const candidates = [payload.summary, payload.safe_reason, label];
  for (const value of candidates) {
    if (value == null) continue;
    const text = String(value).trim();
    if (!text || PROGRESSIVE_INTERNAL_TEXT_PATTERN.test(text)) continue;
    return text.slice(0, 160);
  }
  return label;
}

function safeRepairRequestSummary(payload = {}) {
  if (payload.datalogue_event_type !== 'bi_worker_repair_request') return '';
  const errorSummary = Array.isArray(payload.validation_error_summary)
    ? payload.validation_error_summary
    : [];
  const safeItems = errorSummary
    .map((item) => String(item || '').trim())
    // validation_error_summary 由后端生成，只包含错误类型和契约路径；这里再做一次白名单，
    // 避免把 SQL、schema、raw rows 或模型原始输入误投到用户可见 timeline。
    .filter((item) => item && SAFE_CONTRACT_ERROR_PATTERN.test(item));
  if (!safeItems.length) return '';
  const visibleItems = safeItems.slice(0, 3);
  const moreText = safeItems.length > visibleItems.length ? ` 等 ${safeItems.length} 项` : '';
  return `Query Plan 契约错误：${visibleItems.join('；')}${moreText}`.slice(0, 220);
}

function safeTiming(source = {}) {
  const timing = source?.timing && typeof source.timing === 'object' ? source.timing : source;
  if (!timing || typeof timing !== 'object') return null;
  const allowed = [
    'started_at',
    'ended_at',
    'elapsed_ms',
    'duration_ms',
    'total_ms',
    'queued_ms',
    'startedAt',
    'endedAt',
    'elapsedMs',
    'durationMs',
  ];
  const out = {};
  for (const key of allowed) {
    const value = timing[key];
    if (typeof value === 'number' && Number.isFinite(value)) out[key] = value;
    if (typeof value === 'string' && safeText(value)) out[key] = value.slice(0, 80);
  }
  return Object.keys(out).length ? out : null;
}

function safeRefs(payload = {}) {
  const refs = {
    artifactRef: safeText(payload.artifact_ref || payload.artifactRef || payload.result_ref || payload.resultRef),
    reportRef: safeText(payload.report_ref || payload.reportRef),
    checkpointRef: safeText(payload.checkpoint_ref || payload.checkpointRef),
  };
  return Object.fromEntries(Object.entries(refs).filter(([, value]) => value));
}

function artifactRefFromCard(card = {}) {
  const primary = card?.primary_ref || card?.primaryRef || null;
  if (typeof primary === 'string') return safeText(primary);
  if (primary && typeof primary === 'object') {
    return safeText(primary.ref_id || primary.ref || primary.artifact_ref || primary.artifactRef);
  }
  const refs = Array.isArray(card?.refs) ? card.refs : [];
  const first = refs[0];
  if (typeof first === 'string') return safeText(first);
  if (first && typeof first === 'object') {
    return safeText(first.ref_id || first.ref || first.artifact_ref || first.artifactRef);
  }
  return '';
}

function safeToolCalls(payload = {}) {
  const calls = Array.isArray(payload.tool_calls) ? payload.tool_calls : payload.toolCalls;
  if (!Array.isArray(calls)) return [];
  return calls.slice(0, 8).map((call = {}) => ({
    id: safeText(call.id || call.tool_call_id || call.toolCallId),
    name: safeText(call.name || call.tool_name || call.toolName),
    state: safeText(call.state || call.status),
  })).filter((call) => call.id || call.name || call.state);
}

function safeInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : null;
}

function rawThinkingDelta(payload = {}) {
  const debugRaw = payload.debug_raw === true || payload.debugRaw === true;
  if (!debugRaw) return null;
  const reasoningKind = payload.reasoning_kind || payload.reasoningKind || '';
  if (reasoningKind !== 'bi_worker_raw_thinking_delta') return null;
  const raw = payload.raw_delta ?? payload.rawDelta;
  if (raw == null) return null;
  return String(raw).slice(0, 4000);
}

function lifecycleStatus(eventType, payload = {}) {
  const explicit = safeText(payload.status);
  if (explicit) return explicit;
  if (eventType.endsWith('.started')) return 'running';
  if (eventType.endsWith('.completed') || eventType.endsWith('.created')) return 'completed';
  if (eventType.endsWith('.failed')) return 'failed';
  return 'completed';
}

function isToolLifecycle(eventType = '') {
  return /(^|\.)(tool_call|tool)\.(started|completed|failed)$/.test(eventType);
}

function isConfirmationEvent(eventType = '') {
  return eventType === 'confirmation.required' || eventType.endsWith('.confirmation_required');
}

function isHandoffEvent(eventType = '') {
  return eventType.startsWith('agent.handoff.') || eventType.startsWith('handoff.');
}

function isAgentProgressEvent(eventType = '') {
  return eventType === 'agent.progress' || eventType === 'reasoning.delta' || eventType === 'reasoning.completed';
}

function baseEvent(streamEvent, envelope) {
  return {
    task_id: streamEvent.task_id || envelope.task_id,
    trace_id: envelope.trace_id || null,
    thread_id: envelope.thread_id || null,
  };
}

export function agentTeamEnvelopeToChatEvent(streamEvent = {}) {
  if (!streamEvent.event_envelope) {
    if (typeof console !== 'undefined') {
      console.warn('[agent-team] rejected non-envelope event shape', streamEvent.type || 'unknown');
    }
    return null;
  }

  const envelope = streamEvent.event_envelope;
  const payload = envelope.payload || {};
  const legacy = streamEvent.legacy_payload || envelope.legacy_payload || {};

  if (envelope.event_type === 'message.delta') {
    return { type: 'token', content: payload.content || '' };
  }
  if (envelope.event_type === 'message.completed') {
    const progressiveLabel = PROGRESSIVE_EVENT_LABELS[payload.datalogue_event_type];
    if (progressiveLabel) {
      return {
        type: 'agent_progress',
        title: progressiveLabel,
        summary: safeProgressiveSummary(payload, progressiveLabel),
        status: payload.support_status === 'unsupported' ? 'failed' : 'completed',
        event_envelope: streamEvent.event_envelope,
      };
    }
    const artifactCard = legacy.artifact_card || payload.artifact_card || null;
    const artifactRef = legacy.result_ref
      || legacy.artifact_ref
      || payload.result_ref
      || payload.artifact_ref
      || artifactRefFromCard(artifactCard)
      || null;
    return {
      ...legacy,
      type: 'final',
      answer: legacy.answer || payload.answer || payload.summary || '',
      result_ref: artifactRef,
      artifact_ref: artifactRef,
      checkpoint_ref: legacy.checkpoint_ref || payload.checkpoint_ref || null,
      row_count: legacy.row_count ?? payload.row_count ?? null,
      column_count: legacy.column_count ?? payload.column_count ?? null,
      timing: payload.timing || legacy.timing || null,
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: legacy.trace_id || envelope.trace_id || null,
      thread_id: legacy.thread_id || envelope.thread_id || null,
      route_decision: legacy.route_decision || payload.route_decision || null,
      clarification: legacy.clarification || payload.clarification || null,
      route_payload: legacy.route_payload || payload.route_payload || null,
      original_question: legacy.original_question || payload.original_question || payload.originalQuestion || null,
      artifact_card: artifactCard,
      reasoning_summary: legacy.reasoning_summary || payload.reasoning_summary || null,
      event_envelope: envelope,
    };
  }
  if (isAgentProgressEvent(envelope.event_type)) {
    const agentRole = safeText(payload.agent_role || payload.agentRole) || 'agent';
    const agentName = safeText(payload.agent_name || payload.agentName || payload.agent || payload.worker_agent_name)
      || (agentRole === 'worker' ? 'Worker Agent' : 'Lead Agent');
    const rawDelta = rawThinkingDelta(payload);
    return {
      type: 'agent_progress',
      kind: 'agent_progress',
      status: lifecycleStatus(envelope.event_type, payload),
      title: safeText(payload.title || payload.phase) || '执行进展',
      summary: safeText(payload.summary || payload.message || payload.text) || '',
      agent: safeAgentName(agentName),
      agentRole,
      agentName,
      phase: safeText(payload.phase) || null,
      replyId: safeText(payload.reply_id || payload.replyId) || null,
      workerSessionId: safeText(payload.worker_session_id || payload.workerSessionId) || null,
      workerAgentId: safeText(payload.worker_agent_id || payload.workerAgentId) || null,
      reasoningKind: safeText(payload.reasoning_kind || payload.reasoningKind) || null,
      streamGroupId: safeText(payload.stream_group_id || payload.streamGroupId) || null,
      sequence: safeInteger(payload.sequence),
      blockId: safeText(payload.block_id || payload.blockId) || null,
      debugRaw: rawDelta != null ? true : undefined,
      rawDelta: rawDelta ?? undefined,
      timing: safeTiming(payload),
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (isHandoffEvent(envelope.event_type)) {
    const toAgent = safeAgentName(payload.to_agent || payload.toAgent || payload.agent);
    return {
      type: 'agent_handoff',
      kind: 'handoff',
      status: lifecycleStatus(envelope.event_type, payload),
      title: safeText(payload.title) || 'Agent handoff',
      summary: safeText(payload.summary || payload.reason) || '已切换处理 Agent',
      agent: toAgent,
      from_agent: safeAgentName(payload.from_agent || payload.fromAgent),
      to_agent: toAgent,
      // 阶段 4：handoff 事件也要携带 worker session/reply/角色信息，
      // 让下游 sub-agent 聚合能识别 Worker 边界，不再依赖后续 progress 事件。
      agentRole: safeText(payload.agent_role || payload.agentRole) || null,
      agentName: safeText(payload.agent_name || payload.agentName) || null,
      workerSessionId: safeText(payload.worker_session_id || payload.workerSessionId) || null,
      workerAgentId: safeText(payload.worker_agent_id || payload.workerAgentId) || null,
      replyId: safeText(payload.reply_id || payload.replyId) || null,
      timing: safeTiming(payload),
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (isToolLifecycle(envelope.event_type)) {
    const refs = safeRefs(payload);
    // agentRole/agentName/replyId/workerSessionId 是阶段 4 多 Agent 归组契约的一部分，
    // 缺失时前端要能兜底：Leader 视为 leader；Worker 明确带 role 才折叠到 Worker 分组。
    const agentRole = safeText(payload.agent_role || payload.agentRole) || null;
    const agentNameRaw = safeText(
      payload.agent_name || payload.agentName || payload.agent || payload.worker_agent_name,
    ) || null;
    return {
      type: 'tool_call',
      kind: 'tool',
      status: lifecycleStatus(envelope.event_type, payload),
      title: safeText(payload.title || payload.tool_name || payload.toolName) || '工具调用',
      summary: safeText(payload.summary || payload.message) || '',
      agent: safeAgentName(payload.agent || payload.agent_name || payload.agentName),
      agentRole,
      agentName: agentNameRaw,
      toolName: safeText(payload.tool_name || payload.toolName) || 'dataset_tool',
      toolCallId: safeText(payload.tool_call_id || payload.toolCallId || payload.call_id || payload.callId) || '',
      replyId: safeText(payload.reply_id || payload.replyId) || null,
      workerSessionId: safeText(payload.worker_session_id || payload.workerSessionId) || null,
      workerAgentId: safeText(payload.worker_agent_id || payload.workerAgentId) || null,
      timing: safeTiming(payload),
      refs,
      rowCount: payload.row_count ?? payload.rowCount ?? null,
      columnCount: payload.column_count ?? payload.columnCount ?? null,
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (isConfirmationEvent(envelope.event_type)) {
    return {
      type: 'confirmation',
      kind: 'confirmation',
      status: 'requires_action',
      title: safeText(payload.title) || '需要确认',
      summary: safeText(payload.summary || payload.message) || '需要确认后继续',
      agent: safeAgentName(payload.agent || payload.agent_name || payload.agentName),
      toolName: safeText(payload.tool_name || payload.toolName) || null,
      toolCallId: safeText(payload.tool_call_id || payload.toolCallId || payload.call_id || payload.callId) || null,
      replyId: safeText(payload.reply_id || payload.replyId) || null,
      workerSessionId: safeText(payload.worker_session_id || payload.workerSessionId) || null,
      workerAgentId: safeText(payload.worker_agent_id || payload.workerAgentId) || null,
      toolCalls: safeToolCalls(payload),
      timing: safeTiming(payload),
      refs: safeRefs(payload),
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (envelope.event_type === 'artifact.created') {
    return {
      type: 'artifact_ref',
      kind: 'artifact',
      status: 'completed',
      title: safeText(payload.title) || '结果产物',
      summary: safeText(payload.summary) || '已生成结果产物',
      refs: safeRefs(payload),
      rowCount: payload.row_count ?? payload.rowCount ?? null,
      timing: safeTiming(payload),
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (envelope.event_type === 'dataset.selected') {
    const routeDecision = payload.route_decision || {};
    return {
      type: 'route_decision',
      ...(routeDecision && typeof routeDecision === 'object' ? routeDecision : {}),
      decision: routeDecision.decision || 'selected',
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      event_envelope: envelope,
    };
  }
  if (envelope.event_type === 'clarification.required') {
    const routeDecision = payload.route_decision || {};
    return {
      type: 'route_decision',
      ...(routeDecision && typeof routeDecision === 'object' ? routeDecision : {}),
      decision: routeDecision.decision || 'ambiguous',
      clarification: payload.clarification || null,
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      event_envelope: envelope,
    };
  }
  if (envelope.event_type === 'task.failed') {
    return {
      type: 'final',
      answer: payload.error_summary || '任务执行失败，内部细节已隐藏。',
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      entry_route: 'agent_team_failed',
      event_envelope: envelope,
    };
  }
  if (envelope.event_type?.startsWith('repair.')) {
    return {
      type: 'repair',
      task_id: streamEvent.task_id || envelope.task_id,
      event_envelope: envelope,
    };
  }
  const fallbackEventType = safeText(envelope.event_type, 'agent_team') || 'agent_team';
  return {
    type: 'step',
    node: fallbackEventType,
    display_name: safeText(payload.summary) || fallbackEventType || 'Agent Team',
    status: payload.status || 'done',
    task_id: streamEvent.task_id || envelope.task_id,
    event_envelope: {
      event_type: fallbackEventType,
      task_id: envelope.task_id,
      trace_id: envelope.trace_id,
      thread_id: envelope.thread_id,
    },
  };
}

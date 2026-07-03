// Agent Team envelope 到旧 ChatModelAdapter 内部事件的迁移适配。

const INTERNAL_TEXT_PATTERN = /\b(select|insert|update|delete|from|join|where|group\s+by|order\s+by|having|union|with)\b|[`;]|hidden_table|\b\w+_col\b|raw_result|raw_rows?|schema|query_plan|repairpatch|blueprint/i;

function safeText(value, fallback = '') {
  if (value == null) return fallback;
  const text = String(value).trim();
  if (!text || INTERNAL_TEXT_PATTERN.test(text)) return fallback;
  return text.slice(0, 160);
}

function safeAgentName(value) {
  return safeText(value, '').replace(/[^\w.-]+/g, '_').slice(0, 80);
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
    const artifactRef = legacy.result_ref || legacy.artifact_ref || payload.result_ref || payload.artifact_ref || null;
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
      event_envelope: envelope,
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
      timing: safeTiming(payload),
      ...baseEvent(streamEvent, envelope),
    };
  }
  if (isToolLifecycle(envelope.event_type)) {
    const refs = safeRefs(payload);
    return {
      type: 'tool_call',
      kind: 'tool',
      status: lifecycleStatus(envelope.event_type, payload),
      title: safeText(payload.title || payload.tool_name || payload.toolName) || '工具调用',
      summary: safeText(payload.summary || payload.message) || '',
      agent: safeAgentName(payload.agent || payload.agent_name || payload.agentName),
      toolName: safeText(payload.tool_name || payload.toolName) || 'dataset_tool',
      toolCallId: safeText(payload.tool_call_id || payload.toolCallId || payload.call_id || payload.callId) || '',
      timing: safeTiming(payload),
      refs,
      rowCount: payload.row_count ?? payload.rowCount ?? null,
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

// Agentic Shell envelope 到旧 ChatModelAdapter 内部事件的迁移适配。

export function agenticEnvelopeToChatEvent(streamEvent = {}) {
  // 迁移期兼容：后端若回退到旧 chat event 形状（带顶层 type 字段），跳过 envelope 解析。
  // 迁移完成后应移除此 bypass。
  if (streamEvent.type && !streamEvent.event_envelope) {
    if (typeof console !== 'undefined') {
      console.warn('[agentic-shell] bypassing envelope parse for legacy event shape', streamEvent.type);
    }
    return streamEvent;
  }

  const envelope = streamEvent.event_envelope || {};
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
  if (envelope.event_type === 'agent.handoff.started') {
    return {
      type: 'agent_handoff',
      from_agent: payload.from_agent || '',
      to_agent: payload.to_agent || '',
      reason: payload.reason || '',
      dataset_id: payload.dataset_id || null,
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: envelope.trace_id || null,
      event_envelope: envelope,
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
  if (
    envelope.event_type === 'tool_call.started' ||
    envelope.event_type === 'tool_call.completed' ||
    envelope.event_type === 'tool_call.failed'
  ) {
    return {
      type: envelope.event_type,
      tool_name: payload.tool_name || '',
      tool_call_id: payload.tool_call_id || '',
      summary: payload.summary || '',
      status: payload.status || '',
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
      entry_route: 'agentic_shell_failed',
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
  return {
    type: 'step',
    node: envelope.event_type || 'agentic_shell',
    display_name: payload.summary || envelope.event_type || 'Agentic Shell',
    status: payload.status || 'done',
    task_id: streamEvent.task_id || envelope.task_id,
    event_envelope: envelope,
  };
}

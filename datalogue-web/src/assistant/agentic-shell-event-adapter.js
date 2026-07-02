// Agentic Shell envelope 到旧 ChatModelAdapter 内部事件的迁移适配。

export function agenticEnvelopeToChatEvent(streamEvent = {}) {
  if (streamEvent.type) return streamEvent; // 测试和过渡期兼容旧 chat event 形状，避免 UI 处理层大范围改动。

  const envelope = streamEvent.event_envelope || {};
  const payload = envelope.payload || {};
  const legacy = streamEvent.legacy_payload || envelope.legacy_payload || {};

  if (envelope.event_type === 'message.delta') {
    return { type: 'token', content: payload.content || '' };
  }
  if (envelope.event_type === 'message.completed' || envelope.event_type === 'task.completed') {
    return {
      ...legacy,
      type: 'final',
      answer: legacy.answer || payload.answer || payload.summary || '',
      task_id: streamEvent.task_id || envelope.task_id,
      trace_id: legacy.trace_id || envelope.trace_id || null,
      thread_id: legacy.thread_id || envelope.thread_id || null,
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
  return {
    type: 'step',
    node: envelope.event_type || 'agentic_shell',
    display_name: payload.summary || envelope.event_type || 'Agentic Shell',
    status: payload.status || 'done',
    task_id: streamEvent.task_id || envelope.task_id,
    event_envelope: envelope,
  };
}

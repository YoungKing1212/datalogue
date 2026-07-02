import { describe, expect, it } from 'vitest';

import { agenticEnvelopeToChatEvent } from './agentic-shell-event-adapter.js';

describe('agenticEnvelopeToChatEvent', () => {
  it('maps message.delta to token event', () => {
    const event = agenticEnvelopeToChatEvent({
      event_envelope: {
        event_type: 'message.delta',
        payload: { content: '合同总金额' },
      },
    });

    expect(event).toEqual({ type: 'token', content: '合同总金额' });
  });

  it('maps task.completed to final event', () => {
    const event = agenticEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'message.completed',
        payload: { summary: '完成' },
        legacy_payload: { type: 'final', answer: '完成' },
      },
    });

    expect(event.type).toBe('final');
    expect(event.task_id).toBe('task-1');
  });

  it('does not turn task.completed into a final answer payload', () => {
    const event = agenticEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'task.completed',
        payload: { summary: 'Agentic Shell 任务已完成。' },
      },
    });

    expect(event.type).toBe('step');
    expect(event.node).toBe('task.completed');
  });

  it('keeps repair envelopes as repair events', () => {
    const event = agenticEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'repair.plan_created',
        payload: { summary: '已生成自动修复方案。' },
      },
    });

    expect(event.type).toBe('repair');
    expect(event.event_envelope.event_type).toBe('repair.plan_created');
  });
});

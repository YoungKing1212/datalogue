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
        event_type: 'task.completed',
        payload: { summary: '完成' },
        legacy_payload: { type: 'final', answer: '完成' },
      },
    });

    expect(event.type).toBe('final');
    expect(event.task_id).toBe('task-1');
  });
});

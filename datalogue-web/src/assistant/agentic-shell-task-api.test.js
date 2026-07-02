import { afterEach, describe, expect, it, vi } from 'vitest';

import { streamAgenticShellTask } from './agentic-shell-task-api.js';

function sseStream(lines) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(lines.join('\n')));
      controller.close();
    },
  });
}

describe('streamAgenticShellTask', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts to the new Agentic Shell task stream endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"task_id":"task-1","event_envelope":{"event_type":"task.started","payload":{}}}',
        '',
      ]),
    });

    const events = [];
    for await (const event of streamAgenticShellTask({
      task_source: 'chat',
      task_type: 'bi_query',
      question: '统计合同总金额',
    })) {
      events.push(event);
    }

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/agentic-shell/tasks/stream',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(events[0].event_envelope.event_type).toBe('task.started');
  });

  it('parses the final SSE event even when the stream has no trailing newline', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: sseStream([
        'data: {"task_id":"task-1","event_envelope":{"event_type":"message.completed","payload":{}}}',
      ]),
    });

    const events = [];
    for await (const event of streamAgenticShellTask({
      task_source: 'chat',
      task_type: 'bi_query',
      question: '统计合同总金额',
    })) {
      events.push(event);
    }

    expect(events).toHaveLength(1);
    expect(events[0].event_envelope.event_type).toBe('message.completed');
  });
});

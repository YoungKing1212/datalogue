import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  fetchWorkbenchArtifact,
  fetchWorkbenchThread,
  normalizeWorkbenchThreadId,
  requestWorkbenchRetry,
} from './workbench-api.js';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('workbench-api', () => {
  it('normalizes route ids into workbench thread ids', () => {
    expect(normalizeWorkbenchThreadId('25')).toBe('conv_25');
    expect(normalizeWorkbenchThreadId('conv_25')).toBe('conv_25');
    expect(normalizeWorkbenchThreadId('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')).toBe(
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
    expect(normalizeWorkbenchThreadId(undefined)).toBeNull();
  });

  it('fetches thread and artifact views from workbench endpoints', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ thread_id: 'as_1', messages: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ artifact_ref: 'artifact:1', preview_payload: { summary: '完成' } }),
      });

    await expect(fetchWorkbenchThread('as_1')).resolves.toEqual({ thread_id: 'as_1', messages: [] });
    await expect(fetchWorkbenchArtifact('artifact:1')).resolves.toEqual({
      artifact_ref: 'artifact:1',
      preview_payload: { summary: '完成' },
    });
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/workbench/thread/as_1');
    expect(fetchSpy.mock.calls[1][0]).toBe('/api/workbench/artifact/artifact%3A1');
  });

  it('sends retry action with only allowed payload keys', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ accepted: true, retry_message_id: 'msg_retry' }),
    });

    await requestWorkbenchRetry({
      thread_id: 'as_1',
      message_id: 'msg_failed',
      checkpoint_ref: 'checkpoint://retry',
      selected_action: 'retry_last_step',
      sql: 'select * from hidden_table',
      schema: { tables: ['hidden_table'] },
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/workbench/actions/retry');
    expect(JSON.parse(options.body)).toEqual({
      thread_id: 'as_1',
      message_id: 'msg_failed',
      checkpoint_ref: 'checkpoint://retry',
      selected_action: 'retry_last_step',
    });
  });
});

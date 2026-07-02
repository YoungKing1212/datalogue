import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  confirmBILeadAgentRun,
  createBILeadAgentRun,
  getBILeadAgentRun,
  handoffBILeadAgentRun,
} from './bi-lead-agent-api.js';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('bi-lead-agent-api', () => {
  it('creates BI LeadAgent runs through the controlled POST endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 7, status: 'pending' }),
    });

    await expect(createBILeadAgentRun({ question: '统计 GMV', trace_id: 'trace-1' })).resolves.toEqual({
      run_id: 7,
      status: 'pending',
    });

    expect(fetchSpy).toHaveBeenCalledWith('/api/bi-lead-agent/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: '统计 GMV', trace_id: 'trace-1' }),
    });
  });

  it('confirms BI LeadAgent runs through the scoped confirm endpoint', async () => {
    const payload = { user_decision: 'approved', dataset_id: 10 };
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 7, status: 'confirmed' }),
    });

    await confirmBILeadAgentRun(7, payload);

    expect(fetchSpy).toHaveBeenCalledWith('/api/bi-lead-agent/runs/7/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('handoffs BI LeadAgent runs without leaking an empty JSON body', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 7, status: 'handoff' }),
    });

    await handoffBILeadAgentRun(7);

    expect(fetchSpy).toHaveBeenCalledWith('/api/bi-lead-agent/runs/7/handoff', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
  });

  it('gets BI LeadAgent run state through the scoped GET endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 7, status: 'completed' }),
    });

    await expect(getBILeadAgentRun(7)).resolves.toEqual({ run_id: 7, status: 'completed' });

    expect(fetchSpy).toHaveBeenCalledWith('/api/bi-lead-agent/runs/7');
  });

  it('normalizes API failures into safe Error messages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      url: '/internal/debug/url',
      headers: new Headers({ 'x-debug': 'secret' }),
      json: async () => ({ detail: '当前查询范围不可用' }),
    });

    await expect(getBILeadAgentRun(7)).rejects.toThrow('当前查询范围不可用');
    await expect(getBILeadAgentRun(7)).rejects.not.toThrow('/internal/debug/url');
  });
});

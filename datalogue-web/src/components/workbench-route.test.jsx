import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import WorkbenchRoute from './workbench-route.jsx';
import { fetchWorkbenchArtifact, fetchWorkbenchThread } from '../assistant/workbench-api.js';

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

vi.mock('../assistant/workbench-api.js', () => ({
  fetchWorkbenchThread: vi.fn(),
  fetchWorkbenchArtifact: vi.fn(),
  requestWorkbenchRetry: vi.fn(),
  normalizeWorkbenchThreadId: (value) => (value && /^\d+$/.test(value) ? `conv_${value}` : value || null),
}));

describe('WorkbenchRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchWorkbenchThread.mockResolvedValue({
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      read_only: false,
      messages: [],
      timeline: [],
      primary_artifact_ref: 'artifact:result-1',
      related_refs: [],
      available_actions: [],
      legacy_notice: null,
    });
    fetchWorkbenchArtifact.mockResolvedValue({
      artifact_ref: 'artifact:result-1',
      kind: 'query_result',
      title: '查询结果',
      summary: '已加载工作台产物摘要',
      preview_payload: {},
      related_refs: [],
    });
  });

  it('renders hidden route with thread and artifact params', async () => {
    render(
      <MemoryRouter initialEntries={['/workbench/as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifact:result-1']}>
        <Routes>
          <Route path="/workbench/:threadId/:artifactRef" element={<WorkbenchRoute />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText('已加载工作台产物摘要');
    expect(screen.getAllByText('artifact:result-1').length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText('已加载工作台产物摘要')).toBeInTheDocument();
    expect(fetchWorkbenchThread).toHaveBeenCalledWith('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
    expect(fetchWorkbenchArtifact).toHaveBeenCalledWith(
      'artifact:result-1',
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });
});

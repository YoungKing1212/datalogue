import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkbenchPanel } from './workbench-panel.jsx';
import { fetchWorkbenchArtifact, fetchWorkbenchThread, requestWorkbenchRetry } from '../assistant/workbench-api.js';

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

vi.mock('../assistant/workbench-api.js', () => ({
  fetchWorkbenchThread: vi.fn(),
  fetchWorkbenchArtifact: vi.fn(),
  requestWorkbenchRetry: vi.fn(),
}));

const threadView = {
  thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  read_only: false,
  messages: [
    { message_id: 'msg_user', role: 'user', status: 'completed', content_summary: '查询工作日志' },
    { message_id: 'msg_failed', role: 'assistant', status: 'interrupted', content_summary: '任务超时中断' },
  ],
  timeline: [
    { event_id: 'evt_1', event_type: 'route.started', summary: '开始理解问题' },
    { event_id: 'evt_2', event_type: 'answer.completed', summary: '已完成查询' },
  ],
  primary_artifact_ref: 'artifact:result-1',
  related_refs: [
    { ref_type: 'repair_plan', ref: 'artifact:repair-1', relation: 'related' },
    { ref_type: 'checkpoint', ref: 'checkpoint://retry', relation: 'checkpoint' },
  ],
  available_actions: [
    {
      action_id: 'retry',
      label: '重试',
      enabled: false,
      disabled_reason: '当前消息不需要重试。',
      checkpoint_ref: 'checkpoint://retry',
      message_id: 'msg_failed',
    },
  ],
  legacy_notice: null,
};

describe('WorkbenchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchWorkbenchThread.mockResolvedValue(threadView);
    fetchWorkbenchArtifact.mockResolvedValue({
      artifact_ref: 'artifact:result-1',
      kind: 'query_result',
      preview_payload: { summary: '共 10 条工作日志' },
    });
    requestWorkbenchRetry.mockResolvedValue({ accepted: true, retry_message_id: 'msg_retry' });
  });

  it('renders thread messages, timeline, refs and disabled retry reason', async () => {
    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" />);

    expect(await screen.findByText('工作台')).toBeInTheDocument();
    expect(screen.getByText('查询工作日志')).toBeInTheDocument();
    expect(screen.getByText('已完成查询')).toBeInTheDocument();
    expect(screen.getByText('artifact:result-1')).toBeInTheDocument();
    expect(screen.getByText('artifact:repair-1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeDisabled();
    expect(screen.getByText('当前消息不需要重试。')).toBeInTheDocument();
  });

  it('shows legacy read-only notice', async () => {
    fetchWorkbenchThread.mockResolvedValueOnce({
      ...threadView,
      thread_id: 'conv_25',
      read_only: true,
      legacy_notice: '旧会话以只读方式展示',
      available_actions: [],
    });

    render(<WorkbenchPanel threadId="conv_25" />);

    expect(await screen.findByText('旧会话以只读方式展示')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });

  it('opens artifact details from refs without rendering forbidden details', async () => {
    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" />);

    fireEvent.click(await screen.findByRole('button', { name: /artifact:result-1/ }));

    await waitFor(() => expect(fetchWorkbenchArtifact).toHaveBeenCalledWith('artifact:result-1'));
    expect(await screen.findByText('共 10 条工作日志')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/raw_rows|query_plan|schema|select/i);
  });

  it('keeps admin diagnostic drawer closed by default', async () => {
    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" />);

    expect(await screen.findByText('工作台')).toBeInTheDocument();
    expect(screen.queryByText('诊断详情')).not.toBeInTheDocument();
  });

  it('passes accepted retry run request to chat shell without execution details', async () => {
    const onRetryRun = vi.fn();
    fetchWorkbenchThread.mockResolvedValueOnce({
      ...threadView,
      available_actions: [
        {
          action_id: 'retry',
          label: '重试',
          enabled: true,
          checkpoint_ref: 'checkpoint://retry',
          message_id: 'msg_failed',
        },
      ],
    });
    requestWorkbenchRetry.mockResolvedValueOnce({
      accepted: true,
      retry_message_id: 'msg_retry',
      run_request: {
        question: '查询工作日志',
        conversation_id: 31,
        thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        retry_checkpoint_ref: 'checkpoint://retry',
        dataset_id: 7,
        display_text: '重试上一步',
      },
    });

    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" onRetryRun={onRetryRun} />);

    fireEvent.click(await screen.findByRole('button', { name: /重试/ }));

    await waitFor(() => expect(onRetryRun).toHaveBeenCalledWith({
      question: '查询工作日志',
      conversation_id: 31,
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      retry_checkpoint_ref: 'checkpoint://retry',
      dataset_id: 7,
      display_text: '重试上一步',
    }));
    expect(requestWorkbenchRetry).toHaveBeenCalledWith({
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      message_id: 'msg_failed',
      checkpoint_ref: 'checkpoint://retry',
      selected_action: 'retry_last_step',
    });
    expect(JSON.stringify(onRetryRun.mock.calls)).not.toMatch(/select|schema|raw_rows|query_plan/i);
  });
});

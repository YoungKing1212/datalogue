import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { hasRunningWorkbenchMessage, WorkbenchPanel } from './workbench-panel.jsx';
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
  status_summary: {
    status: 'completed',
    label: '已完成',
    tone: 'success',
    actionable: false,
    read_only: false,
    latest_message_id: 'msg_failed',
    primary_artifact_ref: 'artifact:result-1',
    retry_checkpoint_ref: null,
    trace_ref: 'trace:workbench-1',
    summary: '已完成查询，共 10 条工作日志。',
  },
};

describe('WorkbenchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchWorkbenchThread.mockResolvedValue(threadView);
    fetchWorkbenchArtifact.mockResolvedValue({
      artifact_ref: 'artifact:result-1',
      kind: 'query_result',
      preview_payload: { summary: '共 10 条工作日志' },
      related_refs: [{ ref_type: 'trace', ref: 'trace:workbench-1', relation: 'trace' }],
    });
    requestWorkbenchRetry.mockResolvedValue({ accepted: true, retry_message_id: 'msg_retry' });
  });

  it('renders thread messages, timeline, refs and disabled retry reason', async () => {
    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" />);

    expect(await screen.findByText('工作台')).toBeInTheDocument();
    expect(screen.getByText('查询工作日志')).toBeInTheDocument();
    expect(screen.getByText('已完成查询')).toBeInTheDocument();
    expect(screen.getByText('已完成查询，共 10 条工作日志。')).toBeInTheDocument();
    expect(screen.getAllByText('artifact:result-1').length).toBeGreaterThanOrEqual(2);
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

    await waitFor(() => expect(fetchWorkbenchArtifact).toHaveBeenCalledWith(
      'artifact:result-1',
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    ));
    expect(await screen.findByText('共 10 条工作日志')).toBeInTheDocument();
    expect(screen.getByTestId('workbench-artifact-drawer')).toBeInTheDocument();
    expect(screen.getByText('trace:workbench-1')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/raw_rows|query_plan|schema|select/i);
  });

  it('renders an empty state when no thread is selected', () => {
    render(<WorkbenchPanel threadId={null} />);

    expect(screen.getByText('选择一个会话后查看工作台。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });

  it('explains empty thread state without artifact or actions', async () => {
    fetchWorkbenchThread.mockResolvedValueOnce({
      ...threadView,
      messages: [],
      timeline: [],
      primary_artifact_ref: null,
      related_refs: [],
      available_actions: [],
      status_summary: null,
    });

    render(<WorkbenchPanel threadId="as_empty" />);

    expect(await screen.findByText('当前线程还没有可展示的 BI 结果。')).toBeInTheDocument();
    expect(screen.getByText('暂无可打开产物。')).toBeInTheDocument();
    expect(screen.getByText('暂无可用动作。')).toBeInTheDocument();
  });

  it('shows failed diagnostics with retry availability and disabled reason', async () => {
    fetchWorkbenchThread.mockResolvedValueOnce({
      ...threadView,
      primary_artifact_ref: null,
      related_refs: [],
      status_summary: {
        status: 'failed',
        label: '执行失败',
        tone: 'warning',
        actionable: true,
        read_only: false,
        latest_message_id: 'msg_failed',
        primary_artifact_ref: null,
        retry_checkpoint_ref: null,
        trace_ref: 'trace:failed',
        summary: '任务超时中断，缺少可恢复检查点。',
      },
      available_actions: [
        {
          action_id: 'retry',
          label: '重试',
          enabled: false,
          disabled_reason: '当前消息缺少可用检查点。',
          checkpoint_ref: null,
          message_id: 'msg_failed',
        },
      ],
    });

    render(<WorkbenchPanel threadId="as_failed" />);

    expect(await screen.findByText('诊断摘要')).toBeInTheDocument();
    expect(screen.getAllByText('任务超时中断，缺少可恢复检查点。').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('重试暂不可用')).toBeInTheDocument();
    expect(screen.getAllByText('当前消息缺少可用检查点。').length).toBeGreaterThanOrEqual(1);
  });

  it('keeps admin diagnostic drawer closed by default', async () => {
    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" />);

    expect(await screen.findByText('工作台')).toBeInTheDocument();
    expect(screen.queryByText('诊断详情')).not.toBeInTheDocument();
  });

  it('passes accepted retry task request to chat shell without execution details', async () => {
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
      status_summary: {
        status: 'failed',
        label: '执行失败',
        tone: 'warning',
        actionable: true,
        read_only: false,
        latest_message_id: 'msg_failed',
        primary_artifact_ref: null,
        retry_checkpoint_ref: 'checkpoint://retry',
        trace_ref: null,
        summary: '任务超时中断，可从检查点重试。',
      },
    });
    requestWorkbenchRetry.mockResolvedValueOnce({
      accepted: true,
      retry_message_id: 'msg_retry',
      task_request: {
        task_source: 'workbench',
        task_type: 'bi_query',
        question: '重试上一步',
        thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        retry_checkpoint_ref: 'checkpoint://retry',
        client_context: { action: 'retry_last_step' },
      },
      run_request: null,
    });

    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" onRetryRun={onRetryRun} />);

    expect(await screen.findByText('诊断摘要')).toBeInTheDocument();
    expect(screen.getAllByText('checkpoint://retry').length).toBeGreaterThanOrEqual(1);

    fireEvent.click(await screen.findByRole('button', { name: /重试/ }));

    await waitFor(() => expect(onRetryRun).toHaveBeenCalledWith(expect.objectContaining({
      task_source: 'workbench',
      task_type: 'bi_query',
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      retry_checkpoint_ref: 'checkpoint://retry',
    })));
    expect(requestWorkbenchRetry).toHaveBeenCalledWith({
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      message_id: 'msg_failed',
      checkpoint_ref: 'checkpoint://retry',
      selected_action: 'retry_last_step',
    });
    expect(JSON.stringify(onRetryRun.mock.calls)).not.toMatch(/select|schema|raw_rows|query_plan/i);
  });

  it('refreshes while a retry message is running and shows the completed snapshot', async () => {
    fetchWorkbenchThread
      .mockResolvedValueOnce({
        ...threadView,
        messages: [
          ...threadView.messages,
          { message_id: 'msg_retry', role: 'assistant', status: 'running', content_summary: '正在恢复检查点' },
        ],
        timeline: [
          { event_id: 'evt_retry', event_type: 'workbench.retry_requested', summary: '已接收重试请求' },
        ],
        primary_artifact_ref: null,
        status_summary: {
          status: 'running',
          label: '执行中',
          tone: 'pending',
          actionable: false,
          read_only: false,
          latest_message_id: 'msg_retry',
          primary_artifact_ref: null,
          retry_checkpoint_ref: null,
          trace_ref: null,
          summary: '正在恢复检查点',
        },
        available_actions: [],
      })
      .mockResolvedValueOnce({
        ...threadView,
        messages: [
          ...threadView.messages,
          { message_id: 'msg_retry', role: 'assistant', status: 'completed', content_summary: '重试已完成' },
        ],
        timeline: [
          { event_id: 'evt_restored', event_type: 'retry.checkpoint_restored', summary: '已恢复检查点' },
          { event_id: 'evt_completed', event_type: 'answer.completed', summary: '已完成回答' },
        ],
        primary_artifact_ref: 'artifact:retry-result',
        status_summary: {
          status: 'completed',
          label: '已完成',
          tone: 'success',
          actionable: false,
          read_only: false,
          latest_message_id: 'msg_retry',
          primary_artifact_ref: 'artifact:retry-result',
          retry_checkpoint_ref: null,
          trace_ref: 'trace:retry',
          summary: '重试已完成',
        },
        available_actions: [],
      });
    fetchWorkbenchArtifact.mockResolvedValueOnce({
      artifact_ref: 'artifact:retry-result',
      kind: 'query_result',
      preview_payload: { summary: '重试结果已生成' },
      related_refs: [],
    });

    render(<WorkbenchPanel threadId="as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" refreshIntervalMs={80} />);

    expect(await screen.findByText('正在轮询工作台状态')).toBeInTheDocument();
    expect(screen.getByText('运行结束后会自动刷新最新产物。')).toBeInTheDocument();
    await waitFor(() => expect(fetchWorkbenchThread).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('已恢复检查点')).toBeInTheDocument();
    expect(screen.getAllByText('重试已完成').length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText('重试结果已生成')).toBeInTheDocument();
    expect(fetchWorkbenchArtifact).toHaveBeenCalledWith(
      'artifact:retry-result',
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });

  it('only keeps polling while the latest message is running', () => {
    expect(hasRunningWorkbenchMessage({
      messages: [
        { message_id: 'msg_failed', status: 'failed' },
        { message_id: 'msg_retry', status: 'running' },
      ],
    })).toBe(true);
    expect(hasRunningWorkbenchMessage({
      messages: [
        { message_id: 'msg_failed', status: 'failed' },
        { message_id: 'msg_retry', status: 'running' },
        { message_id: 'msg_answer', status: 'completed' },
      ],
    })).toBe(false);
  });

  it('keeps artifact loading and 404 state inside the drawer', async () => {
    let resolveArtifact;
    fetchWorkbenchThread.mockResolvedValueOnce({
      ...threadView,
      primary_artifact_ref: null,
      related_refs: [{ ref_type: 'artifact', ref: 'artifact:missing', relation: 'related' }],
      status_summary: { ...threadView.status_summary, primary_artifact_ref: null },
    });
    fetchWorkbenchArtifact.mockImplementationOnce(() => new Promise((resolve) => {
      resolveArtifact = resolve;
    }));

    render(<WorkbenchPanel threadId="as_artifact" />);

    fireEvent.click(await screen.findByRole('button', { name: /artifact:missing/ }));

    expect(await screen.findByText('正在加载产物详情...')).toBeInTheDocument();

    resolveArtifact({
      artifact_ref: 'artifact:missing',
      kind: 'query_result',
      preview_payload: { summary: '补加载产物摘要' },
      related_refs: [],
    });

    expect(await screen.findByText('补加载产物摘要')).toBeInTheDocument();

    fetchWorkbenchArtifact.mockRejectedValueOnce(new Error('HTTP 404: Not Found'));
    fireEvent.click(screen.getByRole('button', { name: /artifact:missing/ }));

    expect(await screen.findByText('产物不存在或已过期。')).toBeInTheDocument();
    expect(screen.queryByText('工作台暂不可用')).not.toBeInTheDocument();
  });

  it('explains forbidden and cross-thread artifact drawer failures', async () => {
    fetchWorkbenchThread.mockResolvedValue({
      ...threadView,
      primary_artifact_ref: null,
      related_refs: [{ ref_type: 'artifact', ref: 'artifact:locked', relation: 'related' }],
      status_summary: { ...threadView.status_summary, primary_artifact_ref: null },
    });

    render(<WorkbenchPanel threadId="as_artifact" />);

    fetchWorkbenchArtifact.mockRejectedValueOnce(new Error('HTTP 403: Forbidden'));
    fireEvent.click(await screen.findByRole('button', { name: /artifact:locked/ }));

    expect(await screen.findByText('无权限查看该产物。')).toBeInTheDocument();

    fetchWorkbenchArtifact.mockRejectedValueOnce(new Error('HTTP 409: artifact does not belong to current thread'));
    fireEvent.click(screen.getByRole('button', { name: /artifact:locked/ }));

    expect(await screen.findByText('该产物不属于当前会话。')).toBeInTheDocument();
  });
});

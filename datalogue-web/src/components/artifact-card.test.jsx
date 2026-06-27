// artifact-card.test.jsx
// ArtifactCard 组件测试：同时覆盖 C-ready 产物卡片渲染和第一阶段安全 action 协议。

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ArtifactCard, { ArtifactCard as NamedArtifactCard } from './artifact-card.jsx';

vi.mock('./icons', () => ({
  Icon: ({ name, className, style }) => (
    <span data-testid={`icon-${name}`} className={className} style={style} />
  ),
}));

vi.mock('./message-content', () => ({
  default: ({ text }) => <div data-testid="message-content">{text}</div>,
}));

const basicArtifact = {
  title: '查询结果',
  status: 'completed',
  summary_for_chat: '返回 234 行数据，包含销售额、渠道等字段',
  preview_payload: {
    rows: [
      { channel: '线上', amount: '18000' },
      { channel: '线下', amount: '9500' },
    ],
    columns: ['channel', 'amount'],
  },
  primary_ref: 'artifact://abc123',
  related_refs: ['artifact://def456'],
  actions: [
    { action_type: 'view', label: '查看详情', ref: 'artifact://abc123', disabled: false },
    { action_type: 'copy', label: '复制结果', ref: '', disabled: false },
    { action_type: 'export', label: '导出', ref: '', disabled: true },
  ],
};

describe('ArtifactCard', () => {
  it('renders title, status, summary, and refs', () => {
    render(<ArtifactCard artifact={basicArtifact} />);

    expect(screen.getByText('查询结果')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('返回 234 行数据，包含销售额、渠道等字段')).toBeInTheDocument();
    expect(screen.getByText('artifact://abc123')).toBeInTheDocument();
    expect(screen.getByText('artifact://def456')).toBeInTheDocument();
  });

  it('renders preview table with rows', () => {
    render(<ArtifactCard artifact={basicArtifact} />);

    expect(screen.getByText('线上')).toBeInTheDocument();
    expect(screen.getByText('18000')).toBeInTheDocument();
    expect(screen.getByText('线下')).toBeInTheDocument();
    expect(screen.getByText('9500')).toBeInTheDocument();
  });

  it('renders enabled actions and disables export action', () => {
    render(<ArtifactCard artifact={basicArtifact} />);

    expect(screen.getByRole('button', { name: /查看详情/ })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /复制结果/ })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /导出/ })).toBeDisabled();
    expect(screen.getByText('导出能力将在后续版本开放')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /导出/ })).not.toBeInTheDocument();
  });

  it('renders continue_edit as a disabled first-phase action', () => {
    render(
      <NamedArtifactCard
        artifact={{
          ...basicArtifact,
          actions: [{ action_type: 'continue_edit', label: '继续编辑', enabled: true }],
        }}
      />,
    );

    expect(screen.getByRole('button', { name: /继续编辑/ })).toBeDisabled();
    expect(screen.getByText('继续编辑能力将在后续版本开放')).toBeInTheDocument();
  });

  it('ignores unknown actions and hides internal payload fields', () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});

    render(
      <ArtifactCard
        artifact={{
          ...basicArtifact,
          raw_sql: 'select * from orders',
          control_plane: { raw_sql: 'select * from orders' },
          capsule: { dataset_id: 1 },
          actions: [
            { action_type: 'delete_everything', label: '危险动作', enabled: true },
            { action_type: 'export', label: '导出', enabled: false },
          ],
        }}
      />,
    );

    expect(screen.queryByText('危险动作')).not.toBeInTheDocument();
    expect(screen.queryByText(/select \* from orders/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/control_plane/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/capsule/i)).not.toBeInTheDocument();
    expect(debugSpy).toHaveBeenCalledWith('ArtifactCard ignored unknown action', 'delete_everything');
    debugSpy.mockRestore();
  });

  it('dispatches retry with checkpoint_ref only', () => {
    const listener = vi.fn();
    window.addEventListener('datalogue:artifact-action', listener);

    render(
      <ArtifactCard
        artifact={{
          title: 'GMV 分析结果',
          status: 'error',
          summary_for_chat: '生成结果时失败',
          actions: [
            {
              action_type: 'retry',
              label: '重试',
              enabled: true,
              checkpoint_ref: 'checkpoint://task-1/query_context_ready',
              sql: 'SELECT * FROM orders',
              control_plane: { schema: 'orders' },
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /重试/ }));

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      actionType: 'retry',
      checkpointRef: 'checkpoint://task-1/query_context_ready',
    });
    window.removeEventListener('datalogue:artifact-action', listener);
  });

  it('renders null when artifact is null', () => {
    const { container } = render(<ArtifactCard artifact={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders markdown preview when preview_payload has markdown', () => {
    render(
      <ArtifactCard
        artifact={{
          ...basicArtifact,
          preview_payload: { markdown: '## 分析报告\n\n这是报告内容' },
        }}
      />,
    );

    expect(screen.getByTestId('message-content')).toBeInTheDocument();
  });

  it('renders chart hint when preview_payload has chartType', () => {
    render(
      <ArtifactCard
        artifact={{
          ...basicArtifact,
          preview_payload: { chartType: 'bar' },
        }}
      />,
    );

    expect(screen.getByText('图表类型：bar')).toBeInTheDocument();
  });

  it('shows generating status with pulse indicator', () => {
    render(
      <ArtifactCard
        artifact={{
          ...basicArtifact,
          status: 'generating',
          summary_for_chat: '正在查询...',
        }}
      />,
    );

    expect(screen.getByText('生成中')).toBeInTheDocument();
  });

  it('shows error status', () => {
    render(<ArtifactCard artifact={{ ...basicArtifact, status: 'error' }} />);

    expect(screen.getByText('异常')).toBeInTheDocument();
  });

  it('collapses and expands when header is clicked', () => {
    render(<ArtifactCard artifact={basicArtifact} />);

    expect(screen.getByText('线上')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查询结果/ }));
    expect(screen.queryByText('线上')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查询结果/ }));
    expect(screen.getByText('线上')).toBeInTheDocument();
  });

  it('renders card without preview payload', () => {
    render(<ArtifactCard artifact={{ title: '空产物', status: 'ready' }} />);

    expect(screen.getByText('空产物')).toBeInTheDocument();
    expect(screen.getByText('已就绪')).toBeInTheDocument();
  });
});

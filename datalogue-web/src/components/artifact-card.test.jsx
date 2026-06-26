import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ArtifactCard from './artifact-card';

describe('ArtifactCard', () => {
  it('renders disabled export without creating a download link', () => {
    render(
      <ArtifactCard
        artifact={{
          title: 'GMV 分析结果',
          status: 'ready',
          summary_for_chat: '已生成 GMV 结果摘要',
          actions: [
            {
              action_type: 'export',
              label: '导出',
              enabled: false,
              disabled_reason: '导出能力将在后续版本开放',
            },
          ],
        }}
      />,
    );

    expect(screen.getByText('导出能力将在后续版本开放')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /导出/ })).not.toBeInTheDocument();
  });

  it('dispatches retry with checkpoint_ref only', () => {
    const listener = vi.fn();
    window.addEventListener('datalogue:artifact-action', listener);

    render(
      <ArtifactCard
        artifact={{
          title: 'GMV 分析结果',
          status: 'failed',
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
});

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ArtifactCard, { ArtifactCard as NamedArtifactCard } from './artifact-card.jsx';

const artifact = {
  title: 'GMV 查询结果',
  status: 'ready',
  summary_for_chat: '完整结果，2 行，2 列',
  preview_payload: {
    columns: ['region', 'gmv'],
    rows: [
      { region: '华东', gmv: 100 },
      { region: '华南', gmv: 80 },
    ],
  },
  primary_ref: { ref_type: 'artifact', ref: 'artifact:sql_result:json' },
  related_refs: [{ ref_type: 'report', ref: 'artifact:report:text' }],
};

describe('ArtifactCard', () => {
  it('renders disabled export without creating a download link', () => {
    render(
      <NamedArtifactCard
        artifact={{
          ...artifact,
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
    expect(screen.getByRole('button', { name: /导出/ })).toBeDisabled();
  });

  it('renders continue_edit as a disabled first-phase action', () => {
    render(
      <ArtifactCard
        artifact={{
          ...artifact,
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
          ...artifact,
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

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CandidateDatasetConfirmationCard } from './MyMessage.jsx';

describe('CandidateDatasetConfirmationCard', () => {
  it('submits only candidate id and checkpoint through the caller handler', () => {
    const selected = [];

    render(
      <CandidateDatasetConfirmationCard
        confirmation={{
          checkpointRef: 'checkpoint://task-1/dataset',
          candidates: [
            {
              candidate_id: 'cand-12',
              dataset_id: 12,
              dataset_name: '工作日志',
              reason: '能回答工作日志类问题',
              schema: { tables: ['internal'] },
            },
          ],
        }}
        onSelect={(candidate, optionIndex, label) => {
          selected.push({
            candidate_id: candidate.candidate_id,
            checkpoint_ref: candidate.checkpoint_ref || 'checkpoint://task-1/dataset',
            optionIndex,
            label,
          });
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /工作日志/ }));

    expect(selected).toEqual([
      {
        candidate_id: 'cand-12',
        checkpoint_ref: 'checkpoint://task-1/dataset',
        optionIndex: 1,
        label: '工作日志',
      },
    ]);
    expect(screen.queryByText('internal')).not.toBeInTheDocument();
  });
});

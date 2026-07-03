import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import BIAgentFlow, { buildConfirmationRequest } from './bi-agent-flow.jsx';

const selectedDataset = {
  id: 10,
  name: '销售订单明细',
  domain: '零售经营',
  supported_questions: ['渠道 GMV 趋势'],
  key_metrics: ['GMV', '订单数'],
  key_dimensions: ['渠道', '月份'],
  freshness: 'T+1',
  availability: '可用',
  schema: { tables: ['secret_orders'] },
  sql: 'SELECT * FROM secret_orders',
  dsl: { query: 'hidden dsl' },
  raw_rows: [{ secret_col: 'raw row value' }],
};

describe('BIAgentFlow', () => {
  it('builds a route-level confirmation request without execution internals', () => {
    const request = buildConfirmationRequest({
      run: {
        run_id: 7,
        question: '统计 2024 年各渠道 GMV',
      },
      dataset: selectedDataset,
    });

    expect(request).toEqual({
      dataset_id: 10,
      confirmed_question: '统计 2024 年各渠道 GMV',
      task_goal: '执行单数据集问数',
      capability_snapshot: {
        dataset_id: 10,
        name: '销售订单明细',
        domain: '零售经营',
        supported_questions: ['渠道 GMV 趋势'],
        key_metrics: ['GMV', '订单数'],
        key_dimensions: ['渠道', '月份'],
        freshness: 'T+1',
        availability: '可用',
      },
      routing_rationale: '用户已选择 销售订单明细，BI Agent 将把查询任务交接给 DatasetAgent。',
      risk_notice: '本次只执行已确认数据集上的只读查询。',
    });
    expect(JSON.stringify(request)).not.toMatch(/secret_orders|SELECT|hidden dsl|raw row value/i);
  });

  it('disables run creation until a dataset is selected', () => {
    render(<BIAgentFlow initialQuestion="统计 GMV" selectedDataset={null} />);

    expect(screen.getByRole('button', { name: '创建 run' })).toBeDisabled();
    expect(screen.getByText('请选择一个数据集后再启动 BI Agent。')).toBeInTheDocument();
  });

  it('runs create -> confirm -> handoff and renders safe final refs', async () => {
    const logSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    const api = {
      createRun: vi.fn().mockResolvedValue({
        run_id: 7,
        status: 'waiting_confirmation',
        phase: 'confirm_run',
        question: '统计 2024 年各渠道 GMV',
      }),
      confirmRun: vi.fn().mockResolvedValue({
        run_id: 7,
        status: 'running',
        phase: 'handoff_run',
        question: '统计 2024 年各渠道 GMV',
      }),
      handoffRun: vi.fn().mockResolvedValue({
        run_id: 7,
        status: 'completed',
        phase: 'summarize_run',
        question: '统计 2024 年各渠道 GMV',
        handoff: {
          answer_summary: '线上渠道贡献最高。',
          artifact_ref: 'artifact:bi-agent-7',
          checkpoint_ref: 'checkpoint://bi-agent/7/summarize',
          row_count: 10,
          column_count: 3,
          sql: 'SELECT * FROM secret_orders',
          raw_rows: [{ secret_col: 'hidden' }],
        },
      }),
      getRun: vi.fn(),
    };

    render(
      <BIAgentFlow
        selectedDataset={selectedDataset}
        initialQuestion="  统计 2024 年各渠道 GMV  "
        api={api}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '创建 run' }));

    await waitFor(() => {
      expect(api.createRun).toHaveBeenCalledWith({ question: '统计 2024 年各渠道 GMV' });
    });
    expect(logSpy).toHaveBeenCalledWith('[Datalogue][BI Agent]', expect.objectContaining({
      stage: 'ui.create_run.completed',
      entry: 'BIAgentFlow',
      endpoint: '/api/bi-agent',
      run_id: 7,
    }));
    expect(await screen.findByText('确认查询范围')).toBeInTheDocument();
    expect(screen.queryByText(/secret_orders|SELECT|hidden/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '确认查询' }));

    await waitFor(() => {
      expect(api.confirmRun).toHaveBeenCalledWith(7, expect.objectContaining({
        dataset_id: 10,
        user_decision: 'approved',
        capability_snapshot: expect.not.objectContaining({
          schema: expect.anything(),
        }),
      }));
      expect(api.handoffRun).toHaveBeenCalledWith(7);
    });
    expect(logSpy).toHaveBeenCalledWith('[Datalogue][BI Agent]', expect.objectContaining({
      stage: 'ui.confirm_run.completed',
      entry: 'BIAgentFlow',
      endpoint: '/api/bi-agent',
      run_id: 7,
      dataset_id: 10,
    }));
    expect(logSpy).toHaveBeenCalledWith('[Datalogue][BI Agent]', expect.objectContaining({
      stage: 'ui.handoff_run.completed',
      entry: 'BIAgentFlow',
      endpoint: '/api/bi-agent',
      run_id: 7,
      status: 'completed',
    }));

    expect(await screen.findByText('查询完成')).toBeInTheDocument();
    expect(screen.getByText('线上渠道贡献最高。')).toBeInTheDocument();
    expect(screen.getByText('artifact:bi-agent-7')).toBeInTheDocument();
    expect(screen.getByText('checkpoint://bi-agent/7/summarize')).toBeInTheDocument();
    expect(screen.getByText('10 行 / 3 列')).toBeInTheDocument();
    expect(screen.queryByText(/secret_orders|SELECT|hidden/i)).not.toBeInTheDocument();
    expect(api.getRun).not.toHaveBeenCalled();
  });
});

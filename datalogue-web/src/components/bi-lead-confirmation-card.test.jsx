import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import BILeadConfirmationCard, {
  BILeadConfirmationCard as NamedBILeadConfirmationCard,
} from './bi-lead-confirmation-card.jsx';

const confirmationRun = {
  run_id: 7,
  confirmation_request: {
    dataset_id: 10,
    confirmed_question: '统计 2024 年各渠道 GMV',
    task_goal: '生成渠道经营概览',
    routing_rationale: '该数据集覆盖订单和渠道字段，能支撑本次路由判断。',
    risk_notice: '口径按 T+1 数据刷新，实时订单可能缺失。',
    capability_snapshot: {
      dataset_id: 10,
      name: '销售订单明细',
      domain: '零售经营',
      supported_questions: ['渠道 GMV 趋势', '地区订单贡献'],
      key_metrics: ['GMV', '订单数', '客单价'],
      key_dimensions: ['渠道', '地区', '月份'],
      freshness: 'T+1',
      availability: '可用',
      schema: { tables: ['secret_orders'] },
      sql: 'SELECT * FROM secret_orders',
      dsl: { query: 'hidden dsl' },
      raw_rows: [{ secret_col: 'raw row value' }],
    },
  },
};

describe('BILeadConfirmationCard', () => {
  it('renders route-level capability summary without sensitive fields', () => {
    render(<BILeadConfirmationCard run={confirmationRun} onConfirm={vi.fn()} />);

    expect(screen.getByText('BI LeadAgent')).toBeInTheDocument();
    expect(screen.getByText('确认查询范围')).toBeInTheDocument();
    expect(screen.getByText('销售订单明细')).toBeInTheDocument();
    expect(screen.getByText('零售经营')).toBeInTheDocument();
    expect(screen.getByText('GMV')).toBeInTheDocument();
    expect(screen.getByText('订单数')).toBeInTheDocument();
    expect(screen.getByText('渠道')).toBeInTheDocument();
    expect(screen.getByText('月份')).toBeInTheDocument();
    expect(screen.getByText('该数据集覆盖订单和渠道字段，能支撑本次路由判断。')).toBeInTheDocument();
    expect(screen.getByText('口径按 T+1 数据刷新，实时订单可能缺失。')).toBeInTheDocument();

    expect(screen.queryByText(/secret_orders/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden dsl/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw row value/i)).not.toBeInTheDocument();
  });

  it('confirms with a trimmed capability snapshot and approved decision', () => {
    const onConfirm = vi.fn();
    render(<NamedBILeadConfirmationCard run={confirmationRun} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole('button', { name: '确认查询' }));

    expect(onConfirm).toHaveBeenCalledWith({
      dataset_id: 10,
      confirmed_question: '统计 2024 年各渠道 GMV',
      task_goal: '生成渠道经营概览',
      capability_snapshot: {
        dataset_id: 10,
        name: '销售订单明细',
        domain: '零售经营',
        supported_questions: ['渠道 GMV 趋势', '地区订单贡献'],
        key_metrics: ['GMV', '订单数', '客单价'],
        key_dimensions: ['渠道', '地区', '月份'],
        freshness: 'T+1',
        availability: '可用',
      },
      routing_rationale: '该数据集覆盖订单和渠道字段，能支撑本次路由判断。',
      risk_notice: '口径按 T+1 数据刷新，实时订单可能缺失。',
      user_decision: 'approved',
    });
  });

  it('renders null when the run or dataset id is missing', () => {
    const { container, rerender } = render(<BILeadConfirmationCard run={null} />);
    expect(container.firstChild).toBeNull();

    rerender(<BILeadConfirmationCard run={{ confirmation_request: {} }} />);
    expect(container.firstChild).toBeNull();
  });
});

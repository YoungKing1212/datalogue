import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import BILeadRunPanel, { BILeadRunPanel as NamedBILeadRunPanel } from './bi-lead-run-panel.jsx';

describe('BILeadRunPanel', () => {
  it('renders completed status with safe answer summary, refs, and table shape', () => {
    render(
      <BILeadRunPanel
        run={{
          run_id: 7,
          status: 'completed',
          phase: 'summarize_run',
          handoff: {
            answer_summary: '已生成渠道 GMV 汇总，线上渠道贡献最高。',
            artifact_ref: 'artifact:bi-lead-7',
            checkpoint_ref: 'checkpoint://bi-lead/7/summarize',
            row_count: 10,
            column_count: 3,
            sql: 'SELECT * FROM secret_orders',
            schema: { tables: ['secret_orders'] },
            raw_rows: [{ secret_col: 'hidden' }],
            dsl: { query: 'hidden dsl' },
          },
        }}
      />,
    );

    expect(screen.getByText('查询完成')).toBeInTheDocument();
    expect(screen.getByText('汇总')).toBeInTheDocument();
    expect(screen.getByText('已生成渠道 GMV 汇总，线上渠道贡献最高。')).toBeInTheDocument();
    expect(screen.getByText('artifact:bi-lead-7')).toBeInTheDocument();
    expect(screen.getByText('checkpoint://bi-lead/7/summarize')).toBeInTheDocument();
    expect(screen.getByText('10 行 / 3 列')).toBeInTheDocument();
    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_orders/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden dsl/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden/i)).not.toBeInTheDocument();
  });

  it('renders blocked status with safe error summary and no traceback', () => {
    render(
      <NamedBILeadRunPanel
        run={{
          run_id: 8,
          status: 'blocked',
          phase: 'confirm_run',
          error_summary: '缺少时间范围，需要补充查询条件。\nTraceback (most recent call last):\nSELECT * FROM secret_orders',
        }}
      />,
    );

    expect(screen.getByText('需要补充条件')).toBeInTheDocument();
    expect(screen.getByText('确认')).toBeInTheDocument();
    expect(screen.getByText('缺少时间范围，需要补充查询条件。')).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
  });

  it('renders failed status with safe fallback summary', () => {
    render(
      <BILeadRunPanel
        run={{
          run_id: 9,
          status: 'failed',
          phase: 'handoff_run',
          error_summary: '执行超时，请稍后重试。\nschema: secret_schema\nraw rows: hidden rows',
        }}
      />,
    );

    expect(screen.getByText('查询失败')).toBeInTheDocument();
    expect(screen.getByText('交接执行')).toBeInTheDocument();
    expect(screen.getByText('执行超时，请稍后重试。')).toBeInTheDocument();
    expect(screen.queryByText(/secret_schema/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden rows/i)).not.toBeInTheDocument();
  });

  it('falls back for failed runs when the summary only contains SQL DDL', () => {
    render(
      <BILeadRunPanel
        run={{
          run_id: 10,
          status: 'failed',
          phase: 'handoff_run',
          error_summary: 'SQL: DROP TABLE secret_orders',
        }}
      />,
    );

    expect(screen.getByText('查询失败，请稍后重试。')).toBeInTheDocument();
    expect(screen.queryByText(/SQL/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/DROP TABLE/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_orders/i)).not.toBeInTheDocument();
  });

  it('falls back for blocked runs when every summary line is sensitive', () => {
    const { rerender } = render(
      <BILeadRunPanel
        run={{
          run_id: 11,
          status: 'blocked',
          phase: 'confirm_run',
          error_summary: 'schema: private',
        }}
      />,
    );

    expect(screen.getByText('需要补充查询条件。')).toBeInTheDocument();
    expect(screen.queryByText(/schema/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private/i)).not.toBeInTheDocument();

    rerender(
      <BILeadRunPanel
        run={{
          run_id: 12,
          status: 'blocked',
          phase: 'confirm_run',
          error_summary: 'SQL: SELECT * FROM private',
        }}
      />,
    );

    expect(screen.getByText('需要补充查询条件。')).toBeInTheDocument();
    expect(screen.queryByText(/SQL/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private/i)).not.toBeInTheDocument();
  });

  it('does not render result shape from non-contract or non-numeric fields', () => {
    const { rerender } = render(
      <BILeadRunPanel
        run={{
          run_id: 13,
          status: 'completed',
          phase: 'summarize_run',
          handoff: {
            answer_summary: '已生成安全摘要。',
            result_rows: ['secret_order'],
            result_columns: ['secret_col'],
          },
        }}
      />,
    );

    expect(screen.getByText('已生成安全摘要。')).toBeInTheDocument();
    expect(screen.queryByText(/secret_order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_order 行/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/结果规模/)).not.toBeInTheDocument();

    rerender(
      <BILeadRunPanel
        run={{
          run_id: 14,
          status: 'completed',
          phase: 'summarize_run',
          handoff: {
            answer_summary: '已生成安全摘要。',
            row_count: ['secret_order'],
            column_count: 3,
          },
        }}
      />,
    );

    expect(screen.queryByText(/secret_order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_order 行/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/3 列/)).not.toBeInTheDocument();
    expect(screen.queryByText(/结果规模/)).not.toBeInTheDocument();
  });

  it('falls back for completed runs when answer summary only contains result internals', () => {
    const { rerender } = render(
      <BILeadRunPanel
        run={{
          run_id: 15,
          status: 'completed',
          phase: 'summarize_run',
          handoff: {
            answer_summary: 'result_rows: secret_order',
          },
        }}
      />,
    );

    expect(screen.getByText('BI LeadAgent 正在处理本次查询。')).toBeInTheDocument();
    expect(screen.queryByText(/result_rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_order/i)).not.toBeInTheDocument();

    rerender(
      <BILeadRunPanel
        run={{
          run_id: 16,
          status: 'completed',
          phase: 'summarize_run',
          handoff: {
            answer_summary: 'result_columns: secret_col',
          },
        }}
      />,
    );

    expect(screen.getByText('BI LeadAgent 正在处理本次查询。')).toBeInTheDocument();
    expect(screen.queryByText(/result_columns/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
  });

  it('falls back for failed runs when error summary only contains result internals', () => {
    render(
      <BILeadRunPanel
        run={{
          run_id: 17,
          status: 'failed',
          phase: 'handoff_run',
          error_summary: 'result rows: secret_order\nresult-columns: secret_col',
        }}
      />,
    );

    expect(screen.getByText('查询失败，请稍后重试。')).toBeInTheDocument();
    expect(screen.queryByText(/result rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/result-columns/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
  });

  it('falls back for blocked runs when error summary only contains result internals', () => {
    render(
      <BILeadRunPanel
        run={{
          run_id: 18,
          status: 'blocked',
          phase: 'confirm_run',
          error_summary: 'result_rows: secret_order\nresult_columns: secret_col',
        }}
      />,
    );

    expect(screen.getByText('需要补充查询条件。')).toBeInTheDocument();
    expect(screen.queryByText(/result_rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/result_columns/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
  });

  it('renders null without a run', () => {
    const { container } = render(<BILeadRunPanel run={null} />);
    expect(container.firstChild).toBeNull();
  });
});

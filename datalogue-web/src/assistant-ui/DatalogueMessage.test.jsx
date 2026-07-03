// DatalogueMessage.test.jsx
// 覆盖 assistant-ui 消息展示壳的安全过滤、状态映射和旧 message parts 兼容。

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@assistant-ui/react', () => ({
  MessagePrimitive: {
    Root: ({ children, className, ...props }) => (
      <section className={className} {...props}>{children}</section>
    ),
    GroupedParts: ({ children }) => (
      <div data-testid="grouped-parts">{children({ part: { type: 'text' } })}</div>
    ),
  },
  groupPartByType: (mapping) => (part) => mapping[part.type] || [],
}));

vi.mock('@assistant-ui/react-streamdown', () => ({
  StreamdownTextPrimitive: ({ containerClassName, preprocess }) => (
    <div data-testid="streamdown" className={containerClassName}>
      {preprocess ? preprocess('回答 <think>内部推理</think>\n| 省份 | GMV |') : 'streamdown'}
    </div>
  ),
  normalizeMathDelimiters: (text) => text,
  escapeCurrencyDollars: (text) => text,
}));

vi.mock('@assistant-ui/react-markdown', () => ({
  MarkdownTextPrimitive: ({ className, preprocess }) => (
    <div data-testid="markdown-fallback" className={className}>
      {preprocess ? preprocess('fallback') : 'fallback'}
    </div>
  ),
}));

vi.mock('../components/artifact-card', () => ({
  default: ({ artifact }) => (
    artifact ? <div data-testid="artifact-card">{artifact.title}</div> : null
  ),
}));

import { DatalogueMarkdown } from './DatalogueMarkdown';
import { DatalogueReasoning } from './DatalogueReasoning';
import { DatalogueToolUI } from './DatalogueToolUI';
import { DatalogueMessage } from './DatalogueMessage';

describe('assistant-ui Datalogue message components', () => {
  it('uses Streamdown markdown and strips think blocks before render', () => {
    render(<DatalogueMarkdown />);

    expect(screen.getByTestId('streamdown')).toHaveClass('ai-message');
    expect(screen.getByTestId('streamdown')).toHaveTextContent('回答');
    expect(screen.queryByText(/内部推理/)).not.toBeInTheDocument();
  });

  it('renders reasoning as a collapsible business summary without control-plane fields', () => {
    render(
      <DatalogueReasoning
        part={{
          text: '已确认销售指标。SQL: select * from orders; schema=orders query_plan={}',
          metadata: {
            summary: '已确认销售指标',
            elapsed_ms: 1234,
            artifact_ref: 'artifact:safe-1',
            raw_rows: [{ id: 1 }],
          },
          status: { type: 'running' },
        }}
      />,
    );

    expect(screen.getByText('思考过程')).toBeInTheDocument();
    expect(screen.getByText('已确认销售指标')).toBeInTheDocument();
    expect(screen.getByText('1234ms')).toBeInTheDocument();
    expect(screen.getByText('artifact:safe-1')).toBeInTheDocument();
    expect(screen.queryByText(/select \*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_rows/i)).not.toBeInTheDocument();
  });

  it('renders tool status, refs and row count while hiding unsafe payload fields', () => {
    render(
      <DatalogueToolUI
        part={{
          toolName: 'dataset_query',
          args: { sql: 'select * from orders', query_plan: { steps: [] } },
          result: {
            status: 'blocked',
            summary: '字段缺失，需要确认',
            row_count: 42,
            artifact_ref: 'artifact:result-1',
            checkpoint_ref: 'checkpoint:retry-1',
            schema: { tables: ['orders'] },
          },
          status: { type: 'requires-action' },
        }}
      />,
    );

    expect(screen.getByText('需要确认')).toBeInTheDocument();
    expect(screen.getByText('字段缺失，需要确认')).toBeInTheDocument();
    expect(screen.getByText('42 行')).toBeInTheDocument();
    expect(screen.getByText('artifact:result-1')).toBeInTheDocument();
    expect(screen.getByText('checkpoint:retry-1')).toBeInTheDocument();
    expect(screen.queryByText(/select \*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/orders/)).not.toBeInTheDocument();
  });

  it('renders legacy user and assistant message parts without runtime wiring', () => {
    render(
      <DatalogueMessage
        message={{
          role: 'assistant',
          status: { type: 'complete' },
          content: [
            { type: 'reasoning', text: '已完成路由', metadata: { summary: '已完成路由' } },
            { type: 'text', text: '最终回答' },
            {
              type: 'tool-call',
              toolName: 'dataset_query',
              result: { status: 'completed', summary: '已返回结果', row_count: 3 },
            },
          ],
          metadata: { custom: { artifactCard: { title: '查询结果' } } },
        }}
      />,
    );

    expect(screen.getByText('数语')).toBeInTheDocument();
    expect(screen.getByText('已完成路由')).toBeInTheDocument();
    expect(screen.getByText('最终回答')).toBeInTheDocument();
    expect(screen.getByText('已返回结果')).toBeInTheDocument();
    expect(screen.getByTestId('artifact-card')).toHaveTextContent('查询结果');
  });
});

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

import { DatalogueDataUI } from './DatalogueDataUI';
import { DatalogueMarkdown } from './DatalogueMarkdown';
import { DatalogueReasoning } from './DatalogueReasoning';
import { DatalogueSubAgentMessages } from './DatalogueSubAgentMessages';
import { DatalogueToolGroup } from './DatalogueToolGroup';
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

  it('renders safe reasoning summary Markdown (list / link / short code) inside the collapse', () => {
    render(
      <DatalogueReasoning
        part={{
          metadata: {
            summary: '本轮已完成：\n\n- 命中术语【GMV】\n- 引用 [手册](https://example.com/doc)\n- 备注 `note`',
          },
          status: { type: 'complete' },
        }}
      />,
    );

    // 列表项
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBeGreaterThanOrEqual(3);
    // 链接
    const link = screen.getByRole('link', { name: '手册' });
    expect(link).toHaveAttribute('href', 'https://example.com/doc');
    // 短行内代码
    expect(screen.getByText('note').tagName.toLowerCase()).toBe('code');
  });

  it('surfaces model-emitted <think> as a separately-labeled block, keeping it out of the main body', () => {
    render(
      <DatalogueReasoning
        part={{
          text: '<think>internal chain</think>业务摘要正文',
          status: { type: 'complete' },
        }}
      />,
    );

    // 主体正文只保留 <think> 之外的部分。
    expect(screen.getByText('业务摘要正文')).toBeInTheDocument();
    // <think> 内容被剥离到独立块，明确标注为「模型自吐」，避免误认为安全 summary。
    expect(screen.getByText(/模型自吐/)).toBeInTheDocument();
    expect(screen.getByText('internal chain')).toBeInTheDocument();
  });

  it('rejects SQL / schema / raw rows / query plan keywords from reasoning summary rendering', () => {
    render(
      <DatalogueReasoning
        part={{
          // metadata.summary 若含 SQL 关键字，safeMarkdownText 应判为不安全并回落。
          text: 'select * from orders where amount > 100',
          metadata: {
            summary: 'schema=orders raw_rows=[{...}] query_plan={"steps": []}',
          },
          status: { type: 'complete' },
        }}
      />,
    );

    // 应回落到默认「已完成一个处理步骤」，不透出任何控制面文本。
    expect(screen.getByText('已完成一个处理步骤')).toBeInTheDocument();
    expect(screen.queryByText(/select \*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/schema=/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/query_plan/i)).not.toBeInTheDocument();
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

  it('renders each of running / complete / error / requires_action tool-call status labels', () => {
    const { container, rerender } = render(
      <DatalogueToolUI part={{ toolName: 'dataset_query', status: 'running', args: {} }} />,
    );
    expect(container.querySelector('.artifact-card-status').textContent).toBe('运行中');
    rerender(
      <DatalogueToolUI
        part={{
          toolName: 'dataset_query',
          status: 'complete',
          args: {},
          result: { summary: '返回三行结果', row_count: 3 },
        }}
      />,
    );
    expect(container.querySelector('.artifact-card-status').textContent).toBe('已完成');
    expect(screen.getByText('3 行')).toBeInTheDocument();
    rerender(
      <DatalogueToolUI
        part={{
          toolName: 'dataset_query',
          status: 'error',
          args: {},
          result: { summary: '内部依赖异常，需要重试' },
        }}
      />,
    );
    expect(container.querySelector('.artifact-card-status').textContent).toBe('执行失败');
    rerender(
      <DatalogueToolUI
        part={{
          toolName: 'dataset_query',
          status: 'requires_action',
          args: {},
          result: { summary: '需要人工确认' },
        }}
      />,
    );
    expect(container.querySelector('.artifact-card-status').textContent).toBe('需要确认');
  });

  it('DatalogueToolGroup uses agent role in title and defaults expanded on running / requires_action', () => {
    const { container, rerender } = render(
      <DatalogueToolGroup group={{ agentRole: 'worker', agentName: 'BI Worker', status: 'running' }}>
        <div data-testid="child">child</div>
      </DatalogueToolGroup>,
    );
    expect(screen.getByText(/Worker · BI Worker/)).toBeInTheDocument();
    const details = container.querySelector('details');
    expect(details).toHaveAttribute('open');
    rerender(
      <DatalogueToolGroup group={{ agentRole: 'worker', agentName: 'BI Worker', status: 'completed' }}>
        <div data-testid="child">child</div>
      </DatalogueToolGroup>,
    );
    expect(container.querySelector('details').open).toBe(false);
  });

  it('DatalogueDataUI renders artifact-card DataMessagePart via the ArtifactCard component', () => {
    render(
      <DatalogueDataUI
        part={{
          type: 'data',
          name: 'datalogue-artifact-card',
          data: { title: '查询结果', primary_ref: 'artifact:ok' },
        }}
      />,
    );
    expect(screen.getByTestId('artifact-card')).toHaveTextContent('查询结果');
  });

  it('DatalogueDataUI renders candidate datasets card with safe fields only', () => {
    render(
      <DatalogueDataUI
        part={{
          type: 'data',
          name: 'datalogue-candidate-datasets',
          data: {
            original_question: '统计销售趋势',
            candidates: [
              { dataset_id: 1, dataset_name: '销售明细', short_reason: '与销售相关' },
              { dataset_id: 2, dataset_name: '订单明细', short_reason: '包含订单数据' },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText('候选数据集')).toBeInTheDocument();
    expect(screen.getByText('销售明细')).toBeInTheDocument();
    expect(screen.getByText('订单明细')).toBeInTheDocument();
    expect(screen.getByText('与销售相关')).toBeInTheDocument();
  });

  it('DatalogueDataUI silently skips unknown data part names', () => {
    const { container } = render(
      <DatalogueDataUI part={{ type: 'data', name: 'unknown-name', data: { x: 1 } }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('DatalogueMessage renders DataMessagePart entries in message content', () => {
    render(
      <DatalogueMessage
        message={{
          role: 'assistant',
          status: { type: 'complete' },
          content: [
            { type: 'text', text: '结果如下' },
            {
              type: 'data',
              name: 'datalogue-artifact-card',
              data: { title: '安全结果', primary_ref: 'artifact:ok' },
            },
          ],
        }}
      />,
    );
    // 由 DataMessagePart 走 ArtifactCard；旧的 metadata.custom.artifactCard 兜底不应再触发。
    expect(screen.getAllByTestId('artifact-card')).toHaveLength(1);
    expect(screen.getByTestId('artifact-card')).toHaveTextContent('安全结果');
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

  it('DatalogueSubAgentMessages renders a folded Worker card with reasoning + tool-call, filtering unsafe payload', () => {
    const messages = [
      {
        id: 'subagent:worker-A',
        role: 'assistant',
        status: { type: 'complete' },
        content: [
          {
            type: 'reasoning',
            text: '正在筛选候选数据集。',
            metadata: { summary: '正在筛选候选数据集。' },
          },
          {
            type: 'tool-call',
            toolName: 'datalogue_execute_query_plan_bundle',
            toolCallId: 'call-A-1',
            status: 'complete',
            args: { agentRole: 'worker' },
            // Sub-agent tool-call 内部 result 只保留白名单字段；这里模拟 DatalogueToolUI 内部安全过滤。
            result: { status: 'completed', summary: '已完成查询。', row_count: 10 },
          },
        ],
        metadata: {
          custom: {
            workerSessionId: 'worker-session-A',
            agentRole: 'worker',
            agentName: 'BI Worker',
          },
        },
      },
    ];
    render(<DatalogueSubAgentMessages messages={messages} />);
    expect(screen.getByTestId('sub-agent-messages')).toBeInTheDocument();
    expect(screen.getByText(/Worker · BI Worker/)).toBeInTheDocument();
    expect(screen.getByText('正在筛选候选数据集。')).toBeInTheDocument();
    expect(screen.getByText('已完成查询。')).toBeInTheDocument();
  });

  it('DatalogueSubAgentMessages returns null for empty input', () => {
    const { container } = render(<DatalogueSubAgentMessages messages={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('DatalogueMessage surfaces sub-agent messages from metadata.custom.subAgentMessages', () => {
    render(
      <DatalogueMessage
        message={{
          role: 'assistant',
          status: { type: 'complete' },
          content: [
            { type: 'text', text: '销售总额为 100 万。' },
            {
              type: 'tool-call',
              toolName: 'datalogue_execute_query_plan_bundle',
              toolCallId: 'call-A-1',
              status: 'complete',
              agentRole: 'worker',
              workerSessionId: 'worker-session-A',
              result: { status: 'completed', summary: '已完成查询。', row_count: 10 },
            },
          ],
          metadata: {
            custom: {
              subAgentMessages: [
                {
                  id: 'subagent:worker-A',
                  role: 'assistant',
                  status: { type: 'complete' },
                  content: [
                    {
                      type: 'reasoning',
                      text: '正在筛选候选数据集。',
                      metadata: { summary: '正在筛选候选数据集。' },
                    },
                  ],
                  metadata: {
                    custom: {
                      workerSessionId: 'worker-session-A',
                      agentRole: 'worker',
                      agentName: 'BI Worker',
                    },
                  },
                },
              ],
            },
          },
        }}
      />,
    );
    expect(screen.getByTestId('sub-agent-messages')).toBeInTheDocument();
    expect(screen.getByText(/Worker · BI Worker/)).toBeInTheDocument();
    expect(screen.getByText('正在筛选候选数据集。')).toBeInTheDocument();
  });

  it('DatalogueMessage deduplicates sub-agent messages when both metadata and tool-call.messages carry the same workerSessionId', () => {
    const subMessage = {
      id: 'subagent:worker-A',
      role: 'assistant',
      status: { type: 'complete' },
      content: [
        {
          type: 'reasoning',
          text: '正在筛选候选数据集。',
          metadata: { summary: '正在筛选候选数据集。' },
        },
      ],
      metadata: {
        custom: {
          workerSessionId: 'worker-session-A',
          agentRole: 'worker',
          agentName: 'BI Worker',
        },
      },
    };
    render(
      <DatalogueMessage
        message={{
          role: 'assistant',
          status: { type: 'complete' },
          content: [
            { type: 'text', text: '销售总额为 100 万。' },
            {
              type: 'tool-call',
              toolName: 'datalogue_execute_query_plan_bundle',
              toolCallId: 'call-A-1',
              status: 'complete',
              agentRole: 'worker',
              workerSessionId: 'worker-session-A',
              result: { status: 'completed', summary: '已完成查询。' },
              // assistant-ui ToolCallMessagePart.messages 契约挂载，测试去重逻辑。
              messages: [subMessage],
            },
          ],
          metadata: { custom: { subAgentMessages: [subMessage] } },
        }}
      />,
    );
    // 只应出现一个 Worker 折叠头
    const headers = screen.getAllByText(/Worker · BI Worker/);
    expect(headers).toHaveLength(1);
  });

  it('sub-agent messages never expose SQL/schema/raw_rows/query_plan in reasoning summary', () => {
    // 模拟 chat-adapter 已经过滤过；这里断言即使 metadata.summary 里含 SQL 关键字，
    // DatalogueReasoning 会回落到默认文案而不把 SQL 字段直接注入 DOM。
    const messages = [
      {
        id: 'subagent:worker-unsafe',
        role: 'assistant',
        status: { type: 'complete' },
        content: [
          {
            type: 'reasoning',
            text: 'select * from orders',
            metadata: {
              summary: 'schema=orders raw_rows=[{}] query_plan={"steps": []}',
            },
          },
        ],
        metadata: {
          custom: {
            workerSessionId: 'worker-session-unsafe',
            agentRole: 'worker',
            agentName: 'Unsafe Worker',
          },
        },
      },
    ];
    render(<DatalogueSubAgentMessages messages={messages} />);
    expect(screen.getByText('已完成一个处理步骤')).toBeInTheDocument();
    expect(screen.queryByText(/select \*/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/schema=/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_rows/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/query_plan/i)).not.toBeInTheDocument();
  });
});

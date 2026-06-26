// MyMessage.test.jsx
// 测试候选数据集确认和 ArtifactCard 在消息中的渲染

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';

// Mock assistant-ui hooks — AIMessage 依赖这些
const mockMessageState = {};

vi.mock('@assistant-ui/react', () => ({
  useAuiState: (selector) => {
    if (typeof selector === 'function') {
      return selector(mockMessageState);
    }
    return mockMessageState;
  },
  useAui: () => ({
    message: () => ({ reload: vi.fn() }),
  }),
  MessagePrimitive: {
    Parts: ({ components: _components }) => <div data-testid="message-parts" />,
    Root: ({ children }) => <div>{children}</div>,
  },
  ChainOfThoughtPrimitive: {
    Root: ({ children }) => <div>{children}</div>,
    AccordionTrigger: ({ children }) => <div>{children}</div>,
    Parts: ({ components: _components }) => <div data-testid="cot-parts" />,
  },
}));

// Mock 子组件
vi.mock('../components/icons', () => ({
  Icon: ({ name, style }) => <span data-testid={`icon-${name}`} style={style} />,
}));

vi.mock('../components/charts', () => ({
  LineChart: () => <div data-testid="line-chart" />,
  Donut: () => <div data-testid="donut" />,
  GroupedBar: () => <div data-testid="grouped-bar" />,
}));

vi.mock('../components/message-content', () => ({
  default: ({ text }) => <div data-testid="message-content">{text}</div>,
}));

vi.mock('../components/task-timeline', () => ({
  default: ({ events }) =>
    events && events.length ? <div data-testid="task-timeline">{events.length} 个节点</div> : null,
}));

vi.mock('../components/artifact-card', () => ({
  default: ({ artifact }) =>
    artifact ? <div data-testid="artifact-card">{artifact.title}</div> : null,
}));

vi.mock('../api/client', () => ({
  getArtifact: vi.fn(),
  submitMessageFeedback: vi.fn().mockResolvedValue({}),
}));

// 需要在 mock 之后导入组件
import { AIMessage } from './MyMessage';

function setMockMessage(custom = {}) {
  // 重置
  Object.keys(mockMessageState).forEach((k) => delete mockMessageState[k]);

  mockMessageState.message = {
    id: 'msg-1',
    status: { type: 'complete', reason: 'stop' },
    content: [
      { type: 'text', text: '这是回答内容' },
    ],
    metadata: {
      custom: {
        ...custom,
      },
    },
  };
  mockMessageState.part = { text: '这是回答内容', status: { type: 'complete' } };
  mockMessageState.chainOfThought = { collapsed: true };
}

describe('MyMessage — C-ready 渲染', () => {
  beforeEach(() => {
    // 确保 window 对象可用
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
    window.dispatchEvent = vi.fn();
  });

  it('renders artifact card when artifactCard is provided', () => {
    setMockMessage({
      artifactCard: {
        title: '查询结果',
        status: 'completed',
        summary_for_chat: '返回 234 行',
        actions: [],
      },
    });

    render(<AIMessage />);
    expect(screen.getByTestId('artifact-card')).toBeInTheDocument();
    expect(screen.getByText('查询结果')).toBeInTheDocument();
  });

  it('renders task timeline when taskTimeline is provided', () => {
    setMockMessage({
      taskTimeline: [
        { type: 'task_understood', label: '任务理解', text: '理解需求', status: 'done' },
      ],
    });

    render(<AIMessage />);
    expect(screen.getByTestId('task-timeline')).toBeInTheDocument();
  });

  it('renders candidate dataset card when candidateDatasets is provided', () => {
    setMockMessage({
      candidateDatasets: {
        candidates: [
          { dataset_name: '销售明细', short_reason: '匹配销售查询' },
          { dataset_name: '用户日志', short_reason: '匹配用户行为' },
        ],
      },
    });

    render(<AIMessage />);

    // CandidateDatasetCard 渲染内容
    expect(screen.getByText('候选数据集确认')).toBeInTheDocument();
    expect(screen.getByText('销售明细')).toBeInTheDocument();
    expect(screen.getByText('匹配销售查询')).toBeInTheDocument();
    expect(screen.getByText('用户日志')).toBeInTheDocument();
    expect(screen.getByText('匹配用户行为')).toBeInTheDocument();
  });

  it('does not render candidate dataset card when candidateDatasets is null', () => {
    setMockMessage({ candidateDatasets: null });
    render(<AIMessage />);
    expect(screen.queryByText('候选数据集确认')).not.toBeInTheDocument();
  });

  it('candidate dataset card shows only dataset_name and short_reason, no schema details', () => {
    setMockMessage({
      candidateDatasets: {
        candidates: [
          {
            dataset_name: '销售明细',
            short_reason: '匹配销售查询',
            // 以下字段不应展示
            tables: ['sales_table'],
            fields: ['amount', 'channel'],
            schema: 'public',
            raw_sql: 'SELECT * FROM sales',
          },
        ],
      },
    });

    render(<AIMessage />);

    expect(screen.getByText('销售明细')).toBeInTheDocument();
    expect(screen.getByText('匹配销售查询')).toBeInTheDocument();

    // 不应展示字段、表、schema、SQL
    expect(screen.queryByText(/字段/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sales_table/)).not.toBeInTheDocument();
    expect(screen.queryByText(/public/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT/)).not.toBeInTheDocument();
  });

  it('submits selected candidate dataset confirmation', () => {
    setMockMessage({
      candidateDatasets: {
        clarification_id: 'clarify-1',
        candidates: [
          { dataset_id: 7, dataset_name: '销售明细', short_reason: '匹配销售查询' },
        ],
      },
    });

    render(<AIMessage />);
    fireEvent.click(screen.getByRole('button', { name: /销售明细/ }));

    expect(window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__).toEqual({
      clarification_id: 'clarify-1',
      selected_index: 1,
      selected_text: '销售明细',
      selected_dataset_id: 7,
    });
    expect(window.dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'datalogue:composer-submit',
        detail: { text: '确认使用：销售明细' },
      }),
    );
  });

  it('renders without crashing when no custom data', () => {
    setMockMessage({});
    render(<AIMessage />);

    // 基本渲染检查
    expect(screen.getByText('数语')).toBeInTheDocument();
    expect(screen.getByText('已生成')).toBeInTheDocument();
  });
});

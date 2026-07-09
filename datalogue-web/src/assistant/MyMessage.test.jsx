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
    GroupedParts: ({ children }) => {
      const parts = mockMessageState.message?.content || [];
      const hasReasoning = parts.some((part) => part.type === 'reasoning');
      return (
        <div data-testid="message-parts">
          {hasReasoning ? children({ part: { type: 'group-reasoning' }, children: null }) : null}
        </div>
      );
    },
    Parts: ({ components: _components }) => <div data-testid="message-parts" />,
    Root: ({ children }) => <div>{children}</div>,
  },
  groupPartByType: () => () => [],
  ChainOfThoughtPrimitive: {
    Root: ({ children }) => <div>{children}</div>,
    AccordionTrigger: ({ children }) => <div>{children}</div>,
    Parts: ({ components: _components }) => <div data-testid="cot-parts" />,
  },
  ActionBarPrimitive: {
    Root: ({ children }) => <div>{children}</div>,
    Copy: ({ children, ...props }) => <button data-testid="actionbar-copy" {...props}>{children}</button>,
    Reload: ({ children, ...props }) => <button data-testid="actionbar-reload" {...props}>{children}</button>,
    Speak: ({ children, ...props }) => <button data-testid="actionbar-speak" {...props}>{children}</button>,
    Edit: ({ children, ...props }) => <button data-testid="actionbar-edit" {...props}>{children}</button>,
  },
  useMessageTiming: () => null,
}));

vi.mock('../assistant-ui', () => ({
  DatalogueActionBar: ({
    visible,
    feedbackTitle,
    feedbackDisabled,
    onApprove,
    onReject,
  }) => (
    <div className={`msg-actions ${visible ? 'visible' : ''}`} data-testid="datalogue-action-bar">
      <button type="button" title="复制回答">复制</button>
      <button
        type="button"
        title={feedbackTitle || '点赞'}
        disabled={feedbackDisabled}
        onClick={onApprove}
      >
        点赞
      </button>
      <button
        type="button"
        title={feedbackTitle || '点踩'}
        disabled={feedbackDisabled}
        onClick={onReject}
      >
        点踩
      </button>
    </div>
  ),
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
  default: ({ artifact, onAction }) =>
    artifact ? (
      <div data-testid="artifact-card">
        <span>{artifact.title}</span>
        {(artifact.actions || []).map((action, index) => (
          <button
            key={`${action.action_type || action.action_id || index}`}
            type="button"
            onClick={() => onAction?.({
              ...action,
              actionType: action.action_type || action.action_id,
            })}
          >
            {action.label}
          </button>
        ))}
      </div>
    ) : null,
}));

vi.mock('../api/client', () => ({
  getArtifact: vi.fn(),
  submitMessageFeedback: vi.fn().mockResolvedValue({}),
}));

// 需要在 mock 之后导入组件
import { AIMessage } from './MyMessage';
import { getArtifact } from '../api/client';

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
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    getArtifact.mockReset();
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

  it('renders visible assistant-ui action bar icons', () => {
    setMockMessage();

    render(<AIMessage />);

    expect(screen.getByRole('button', { name: '复制回答' })).toContainElement(screen.getByTestId('icon-copy'));
    expect(screen.getByRole('button', { name: '重新生成' })).toContainElement(screen.getByTestId('icon-refresh'));
    expect(screen.getByRole('button', { name: '朗读回答' })).toContainElement(screen.getByTestId('icon-play'));
    expect(screen.getByRole('button', { name: '编辑消息' })).toContainElement(screen.getByTestId('icon-edit'));
  });

  it('uses agent name as the reasoning timeline label for realtime Agent progress', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        text: '候选数据集筛选：BI Worker 正在筛选候选数据集。',
        parentId: 'agent-worker',
        agentRole: 'worker',
        agentName: 'BI Worker',
        phase: 'tool',
        status: 'running',
      },
      { type: 'text', text: '正在处理…' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));

    expect(screen.getByText('BI Worker')).toBeInTheDocument();
    expect(screen.queryByText('任务处理')).not.toBeInTheDocument();
  });

  it('labels BI Worker thinking reasoning separately from generic Agent progress', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        text: 'BI Worker 思考中：正在分析问题与可用数据证据。',
        parentId: 'agent-worker-thinking:reply-1:think-1',
        reasoningKind: 'bi_worker_thinking_summary',
        agentRole: 'worker',
        agentName: 'BI Worker',
        phase: 'thinking',
        status: 'running',
      },
      { type: 'text', text: '正在处理…' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));

    expect(screen.getByText('BI Worker 思考')).toBeInTheDocument();
    expect(screen.queryByText('任务处理')).not.toBeInTheDocument();
  });

  it('renders BI Worker raw thinking part as a monospace pre block', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        reasoningKind: 'bi_worker_raw_thinking_delta',
        debugRaw: true,
        rawDelta: '主表：plan_task_daily_record\nLIMIT 100',
        text: 'BI Worker 调试原文：主表：plan_task_daily_record\nLIMIT 100',
        parentId: 'agent-worker-raw-thinking:reply-1:think-raw',
      },
      { type: 'text', text: '正在处理…' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));

    const pre = screen.getByLabelText('BI Worker 调试原文');
    expect(pre.tagName).toBe('PRE');
    expect(pre.textContent).toBe('主表：plan_task_daily_record\nLIMIT 100');
    expect(pre.className).toContain('cot-ant-raw');
  });

  it('strips <think>...</think> from reasoning body and surfaces it in a separate 模型自吐 block', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        text: '<think>secret plan</think>Answer',
        parentId: 'reasoning_summary',
        title: '任务思考',
        status: 'completed',
      },
      { type: 'text', text: '外部答案' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));

    // 正文里应看到 Answer（<think> 剥离后剩余的部分），不应包含 secret plan。
    expect(screen.getByText(/Answer/)).toBeInTheDocument();

    // 模型自吐 <think> 子块单独出现，且明确带上 secret plan。
    const thinkBlock = screen.getByTestId('reasoning-think-blocks');
    expect(thinkBlock).toHaveTextContent('secret plan');
    expect(thinkBlock).toHaveTextContent('模型自吐');
  });

  it('does not render 模型自吐 block when no <think> segments are present in reasoning text', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        text: '普通推理摘要，无 think 段。',
        parentId: 'reasoning_summary',
        title: '推理',
        status: 'completed',
      },
      { type: 'text', text: '答案' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));
    expect(screen.queryByTestId('reasoning-think-blocks')).not.toBeInTheDocument();
  });

  it('uses each final reasoning summary title instead of the generic fallback label', () => {
    setMockMessage();
    mockMessageState.message.content = [
      {
        type: 'reasoning',
        text: '识别任务：已识别为 BI 查询。',
        parentId: 'reasoning_summary',
        title: '识别任务',
        summary: '已识别为 BI 查询。',
        status: 'completed',
      },
      {
        type: 'reasoning',
        text: '生成结果：已生成可查看的查询结果。',
        parentId: 'reasoning_summary',
        title: '生成结果',
        summary: '已生成可查看的查询结果。',
        status: 'completed',
      },
      { type: 'text', text: '查询已完成。' },
    ];

    render(<AIMessage />);
    fireEvent.click(screen.getByText('推理摘要'));

    expect(screen.getByText('识别任务')).toBeInTheDocument();
    expect(screen.getByText('生成结果')).toBeInTheDocument();
    expect(screen.queryByText('任务处理')).not.toBeInTheDocument();
  });

  it('loads query artifact rows when artifact view action is clicked', async () => {
    getArtifact.mockResolvedValue({
      artifact_ref: 'artifact:result-1',
      kind: 'sql_result',
      content_json: {
        columns: ['channel', 'amount'],
        row_count: 2,
        rows: [
          { channel: '线上', amount: 18000 },
          { channel: '线下', amount: 9500 },
        ],
      },
    });
    setMockMessage({
      artifactCard: {
        title: '查询结果',
        status: 'completed',
        primary_ref: 'artifact:result-1',
        actions: [
          { action_type: 'view', label: '查看详情', ref: 'artifact:result-1' },
        ],
      },
    });

    render(<AIMessage />);
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }));

    expect(getArtifact).toHaveBeenCalledWith('artifact:result-1');
    expect(await screen.findByText('查询结果详情')).toBeInTheDocument();
    expect(screen.getByText('channel')).toBeInTheDocument();
    expect(screen.getByText('amount')).toBeInTheDocument();
    expect(screen.getByText('线上')).toBeInTheDocument();
    expect(screen.getByText('18000')).toBeInTheDocument();
  });

  it('does not render task timeline inside chat message when taskTimeline is provided', () => {
    setMockMessage({
      taskTimeline: [
        { type: 'task_understood', label: '任务理解', text: '理解需求', status: 'done' },
      ],
    });

    render(<AIMessage />);
    expect(screen.queryByTestId('task-timeline')).not.toBeInTheDocument();
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

  it('does not render the legacy dataset clarification card when candidateDatasets is provided', () => {
    setMockMessage({
      clarification: {
        kind: 'dataset_choice',
        clarificationId: 'clarify-dataset',
        candidates: [
          { dataset_id: 7, dataset_name: '销售明细', reason: '匹配销售查询' },
        ],
      },
      candidateDatasets: {
        clarification_id: 'clarify-dataset',
        candidates: [
          { dataset_id: 7, dataset_name: '销售明细', short_reason: '匹配销售查询' },
        ],
      },
    });

    render(<AIMessage />);

    expect(screen.getByText('候选数据集确认')).toBeInTheDocument();
    expect(screen.queryByText('请选择数据集')).not.toBeInTheDocument();
  });

  it('does not render candidate dataset card when candidateDatasets is null', () => {
    setMockMessage({ candidateDatasets: null });
    render(<AIMessage />);
    expect(screen.queryByText('候选数据集确认')).not.toBeInTheDocument();
  });

  it('renders business-level repair summary and confirmation without patch details', () => {
    setMockMessage({
      repairPlan: {
        summary: '字段口径不匹配，已生成自动修复方案。',
        status: 'confirmation_required',
        repairPlanRef: 'artifact:repair-1',
        checkpointRef: 'checkpoint://conv-1-msg-2/repair',
        requiresUserConfirmation: true,
        patch: { field: 'bad_col' },
      },
    });

    render(<AIMessage />);

    expect(screen.getByText('查询修复')).toBeInTheDocument();
    expect(screen.getByText('字段口径不匹配，已生成自动修复方案。')).toBeInTheDocument();
    expect(screen.getByText('确认修复')).toBeInTheDocument();
    expect(screen.queryByText('bad_col')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('确认修复'));
    expect(window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__).toEqual({
      repair_plan_ref: 'artifact:repair-1',
      checkpoint_ref: 'checkpoint://conv-1-msg-2/repair',
      selected_action: 'confirm',
    });
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

  it('does not render raw SQL from message custom metadata', () => {
    setMockMessage({
      sql: 'SELECT secret_col FROM hidden_table',
    });

    render(<AIMessage />);

    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
    expect(screen.queryByTitle('复制 SQL')).not.toBeInTheDocument();
  });

  it('does not render raw sqlResult rows or internal column names from custom metadata', () => {
    setMockMessage({
      sqlResult: {
        columns: ['secret_col'],
        rows: [{ secret_col: 'raw_row_value', hidden_table: 'hidden_table' }],
        rowCount: 1,
      },
    });

    render(<AIMessage />);

    expect(screen.queryByText('查询结果')).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_row_value/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden_table/i)).not.toBeInTheDocument();
  });

  it('does not render the result access button for result refs', () => {
    setMockMessage({
      resultRef: 'artifact:result-safe',
    });

    render(<AIMessage />);

    expect(screen.queryByRole('button', { name: /查看结果/ })).not.toBeInTheDocument();
    expect(screen.queryByText('查看结果')).not.toBeInTheDocument();
  });

  it('does not render artifact preview details from result refs inside the message', () => {
    setMockMessage({
      resultRef: 'artifact:result-raw',
      subagentToolResults: [
        { result_ref: 'artifact:result-raw', dataset_id: 12 },
      ],
    });

    render(<AIMessage />);

    expect(screen.queryByText(/查看结果/)).not.toBeInTheDocument();
    expect(screen.queryByText(/结果产物已生成/)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret_col/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_row_value/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden_table/i)).not.toBeInTheDocument();
  });

  it('submits selected candidate dataset confirmation', () => {
    setMockMessage({
      candidateDatasets: {
        clarification_id: 'clarify-1',
        original_question: '查询杨凯2025年工作日志',
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
      original_question: '查询杨凯2025年工作日志',
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

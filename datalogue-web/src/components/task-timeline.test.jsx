// task-timeline.test.jsx
// TaskTimeline 组件测试：覆盖五类节点渲染、禁止技术细节展示

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TaskTimeline from './task-timeline';

// Mock icons
vi.mock('./icons', () => ({
  Icon: ({ name, style }) => <span data-testid={`icon-${name}`} style={style} />,
}));

const timelineEvents = [
  {
    type: 'task_understood',
    label: '任务理解',
    text: '理解为您想查询「销售趋势分析」',
    status: 'done',
  },
  {
    type: 'dataset_matching',
    label: '数据集匹配',
    text: '已匹配数据集「销售明细」',
    status: 'done',
  },
  {
    type: 'bi_execution',
    label: 'BI 执行',
    text: '查询执行完成，返回 234 行',
    status: 'done',
  },
  {
    type: 'artifact_created',
    label: '结果产物',
    text: '已生成分析报告和图表',
    status: 'done',
  },
  {
    type: 'next_action',
    label: '下一步',
    text: '您可以查看详细结果或继续追问',
    status: 'pending',
  },
];

describe('TaskTimeline', () => {
  it('renders all five business timeline nodes', () => {
    render(<TaskTimeline events={timelineEvents} />);

    expect(screen.getByText('任务理解')).toBeInTheDocument();
    expect(screen.getByText('数据集匹配')).toBeInTheDocument();
    expect(screen.getByText('BI 执行')).toBeInTheDocument();
    expect(screen.getByText('结果产物')).toBeInTheDocument();
    expect(screen.getByText('下一步')).toBeInTheDocument();
  });

  it('renders business descriptions without technical details', () => {
    render(<TaskTimeline events={timelineEvents} />);

    expect(screen.getByText(/销售趋势分析/)).toBeInTheDocument();
    expect(screen.getByText(/销售明细/)).toBeInTheDocument();
    expect(screen.getByText(/234 行/)).toBeInTheDocument();

    // 确保不存在 SQL 关键词
    expect(screen.queryByText(/SELECT/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/FROM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/WHERE/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/JOIN/i)).not.toBeInTheDocument();
  });

  it('sanitizes forbidden technical content from text', () => {
    const eventsWithSQL = [
      {
        type: 'bi_execution',
        label: 'BI 执行',
        text: '执行完成 SELECT * FROM sales WHERE amount > 1000',
        status: 'done',
      },
    ];

    render(<TaskTimeline events={eventsWithSQL} />);

    // SQL 之前的内容应保留，SQL 及其后应被截断（trim 后不留尾部空格）
    expect(screen.getByText('执行完成…')).toBeInTheDocument();
    expect(screen.queryByText(/SELECT/)).not.toBeInTheDocument();
  });

  it('renders running status with pulse indicator', () => {
    const events = [
      { type: 'bi_execution', label: 'BI 执行', text: '正在执行查询...', status: 'running' },
    ];
    render(<TaskTimeline events={events} />);

    expect(screen.getByText('BI 执行')).toBeInTheDocument();
    expect(screen.getByText('正在执行查询...')).toBeInTheDocument();
  });

  it('renders error status', () => {
    const events = [
      { type: 'bi_execution', label: 'BI 执行', text: '执行失败', status: 'error' },
    ];
    render(<TaskTimeline events={events} />);

    expect(screen.getByText('执行失败')).toBeInTheDocument();
  });

  it('shows done count in header', () => {
    render(<TaskTimeline events={timelineEvents} />);

    // 4 done + 1 pending = 4/5
    expect(screen.getByText('4/5')).toBeInTheDocument();
  });

  it('renders null when events is empty', () => {
    const { container } = render(<TaskTimeline events={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders null when events is not array', () => {
    const { container } = render(<TaskTimeline events={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('sorts nodes by predefined order regardless of input order', () => {
    const shuffled = [
      { type: 'artifact_created', label: '结果产物', text: '产物', status: 'done' },
      { type: 'task_understood', label: '任务理解', text: '理解', status: 'done' },
      { type: 'bi_execution', label: 'BI 执行', text: '执行', status: 'done' },
      { type: 'dataset_matching', label: '数据集匹配', text: '匹配', status: 'done' },
      { type: 'next_action', label: '下一步', text: '后续', status: 'done' },
    ];

    render(<TaskTimeline events={shuffled} />);

    const labels = screen
      .getAllByText(/任务理解|数据集匹配|BI 执行|结果产物|下一步/)
      .map((el) => el.textContent);

    expect(labels).toEqual(['任务理解', '数据集匹配', 'BI 执行', '结果产物', '下一步']);
  });

  it('renders repair patch as a first-class business node between BI execution and artifact', () => {
    const events = [
      { type: 'artifact_created', text: '已生成查询结果', status: 'done' },
      { type: 'repair_patch', text: '已按业务口径自动修复字段引用', status: 'done' },
      { type: 'bi_execution', text: '正在完成查询处理', status: 'done' },
    ];

    render(<TaskTimeline events={events} />);

    const labels = [...document.querySelectorAll('.task-timeline-label span')]
      .map((el) => el.textContent)
      .filter((text) => ['BI 执行', '自动修复', '结果产物'].includes(text));

    expect(labels).toEqual(['BI 执行', '自动修复', '结果产物']);
    expect(screen.queryByText(/bad_col|work_log|select/i)).not.toBeInTheDocument();
  });
});

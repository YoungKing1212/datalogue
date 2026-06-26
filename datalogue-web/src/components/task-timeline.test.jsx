import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TaskTimeline } from './task-timeline.jsx';

describe('TaskTimeline', () => {
  it('renders business phases without technical schema details', () => {
    render(
      <TaskTimeline
        items={[
          { id: 'understand', label: '任务理解', status: 'done', detail: '已接收问题' },
          { id: 'match_dataset', label: '数据集匹配', status: 'active', detail: '工作日志' },
        ]}
      />,
    );

    expect(screen.getByLabelText('任务时间线')).toBeInTheDocument();
    expect(screen.getByText('任务理解')).toBeInTheDocument();
    expect(screen.getByText('数据集匹配')).toBeInTheDocument();
    expect(screen.queryByText(/schema/i)).not.toBeInTheDocument();
  });
});

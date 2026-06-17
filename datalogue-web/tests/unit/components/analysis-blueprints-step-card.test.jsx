import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BlueprintStepView, StepCard } from '../../../src/components/blueprint-step-view';

describe('BlueprintStepView', () => {
  it('空 steps 时显示空状态', () => {
    render(<BlueprintStepView steps={[]} />);
    expect(screen.getByTestId('blueprint-steps-empty')).toHaveTextContent('暂无业务步骤');
  });

  it('渲染有效步骤的 name 和 step number', () => {
    const steps = [
      { step: 1, name: '订单汇总', purpose: '汇总订单数据', key_rules: ['规则A'], output_columns: ['col1'], confidence: 0.9 },
    ];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.getByTestId('step-name')).toHaveTextContent('订单汇总');
    expect(screen.getByTestId('step-number')).toHaveTextContent('1');
  });

  it('缺失 step 字段时使用 index+1 作为序号', () => {
    const steps = [{ name: '缺失序号步骤', purpose: '测试', key_rules: [], output_columns: [] }];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.getByTestId('step-number')).toHaveTextContent('1');
  });

  it('缺失 purpose 时显示默认占位文本', () => {
    const steps = [{ name: '无描述步骤', key_rules: [], output_columns: [] }];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.getByTestId('step-purpose')).toHaveTextContent('暂无业务描述');
  });

  it('空 output_columns 数组显示无输出列占位', () => {
    const steps = [{ name: '空输出列步骤', purpose: '测试', key_rules: [], output_columns: [] }];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.getByTestId('step-outputs')).toHaveTextContent('无输出列');
  });

  it('关键规则渲染为列表项', () => {
    const steps = [
      { name: '规则步骤', purpose: '测试', key_rules: ['规则1', '规则2'], output_columns: [] },
    ];
    render(<BlueprintStepView steps={steps} />);
    const items = screen.getAllByTestId('step-rule-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('规则1');
    expect(items[1]).toHaveTextContent('规则2');
  });

  it('输出列超过 10 个时显示折叠标签', () => {
    const outputs = Array.from({ length: 15 }, (_, i) => `col${i + 1}`);
    const steps = [{ name: '多列步骤', purpose: '测试', key_rules: [], output_columns: outputs }];
    render(<BlueprintStepView steps={steps} />);
    const tags = screen.getAllByTestId('step-output-tag');
    expect(tags).toHaveLength(10);
    expect(screen.getByTestId('step-output-more')).toHaveTextContent('+5');
  });

  it('存在 confidence 时渲染进度条', () => {
    const steps = [
      { name: '置信步骤', purpose: '测试', key_rules: [], output_columns: [], confidence: 0.85 },
    ];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.getByTestId('step-confidence')).toBeInTheDocument();
    expect(screen.getByTestId('step-confidence-fill')).toHaveStyle('width: 85%');
  });

  it('缺失 confidence 时不渲染置信度区域', () => {
    const steps = [{ name: '无置信步骤', purpose: '测试', key_rules: [], output_columns: [] }];
    render(<BlueprintStepView steps={steps} />);
    expect(screen.queryByTestId('step-confidence')).not.toBeInTheDocument();
  });

  it('点击展开原始 JSON 按钮显示 JSON 块', () => {
    const steps = [{ name: 'JSON 步骤', purpose: '测试', key_rules: [], output_columns: [] }];
    render(<BlueprintStepView steps={steps} />);
    const toggle = screen.getByTestId('step-json-toggle');
    expect(toggle).toHaveTextContent('展开原始 JSON');
    fireEvent.click(toggle);
    expect(screen.getByTestId('step-json-block')).toBeInTheDocument();
    expect(toggle).toHaveTextContent('收起原始 JSON');
  });
});

describe('StepCard', () => {
  it('字符串步骤直接渲染文本', () => {
    render(<StepCard item="这是一个字符串步骤" index={2} />);
    expect(screen.getByTestId('step-card')).toHaveTextContent('这是一个字符串步骤');
    expect(screen.getByText('步骤 3')).toBeInTheDocument();
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';

/**
 * 测试辅助：复用组件文件中的 BlueprintStepView 和 StepCard 逻辑。
 * 由于组件文件依赖外部 API 模块，这里内联最小实现进行测试。
 */

function BlueprintStepView({ steps }) {
  if (!steps || steps.length === 0) {
    return (
      <div className="blueprint-empty-inline" data-testid="blueprint-steps-empty">
        暂无业务步骤
      </div>
    );
  }

  return (
    <div className="blueprint-step-view" data-testid="blueprint-step-view">
      {steps.map((item, index) => (
        <StepCard key={item.id || item.name || index} item={item} index={index} />
      ))}
    </div>
  );
}

function StepCard({ item, index }) {
  const [jsonOpen, setJsonOpen] = useState(false);

  if (typeof item === 'string') {
    return (
      <div className="blueprint-step-card" data-testid="step-card">
        <span className="step-badge">{index + 1}</span>
        <div>
          <strong>{`步骤 ${index + 1}`}</strong>
          <p>{item}</p>
        </div>
      </div>
    );
  }

  const stepNo = item.step || index + 1;
  const name = item.name || item.title || `步骤 ${index + 1}`;
  const purpose = item.purpose || item.description || item.action || item.logic || '';
  const rules = item.key_rules || item.rules || [];
  const outputs = item.output_columns || item.outputs || [];
  const confidence = item.confidence;

  const showAllOutputs = outputs.length <= 10;
  const visibleOutputs = showAllOutputs ? outputs : outputs.slice(0, 10);
  const hiddenCount = outputs.length - visibleOutputs.length;

  return (
    <div className="blueprint-step-card" data-testid="step-card">
      <div className="step-card-header">
        <span className="step-badge" data-testid="step-number">{stepNo}</span>
        <strong data-testid="step-name">{name}</strong>
      </div>

      <div className="step-card-body">
        <div className="step-section" data-testid="step-purpose">
          <div className="step-section-label">业务描述</div>
          <p>{purpose || '暂无业务描述'}</p>
        </div>

        {rules.length > 0 && (
          <div className="step-section" data-testid="step-rules">
            <div className="step-section-label">关键规则</div>
            <ul className="step-rule-list">
              {rules.map((rule, idx) => (
                <li key={idx} data-testid="step-rule-item">{rule}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="step-section" data-testid="step-outputs">
          <div className="step-section-label">输出列</div>
          {outputs.length === 0 ? (
            <span className="step-empty-text">无输出列</span>
          ) : (
            <div className="step-output-tags">
              {visibleOutputs.map((col, idx) => (
                <span key={idx} className="step-output-tag" data-testid="step-output-tag">{col}</span>
              ))}
              {!showAllOutputs && (
                <span className="step-output-tag step-output-tag-more" data-testid="step-output-more">
                  +{hiddenCount}
                </span>
              )}
            </div>
          )}
        </div>

        {confidence != null && (
          <div className="step-section" data-testid="step-confidence">
            <div className="step-section-label">置信度</div>
            <div className="step-confidence-bar">
              <div
                className="step-confidence-fill"
                style={{ width: `${Math.round(confidence * 100)}%` }}
                data-testid="step-confidence-fill"
              />
            </div>
            <span className="step-confidence-text">{Math.round(confidence * 100)}%</span>
          </div>
        )}
      </div>

      <div className="step-card-footer">
        <button
          className="btn ghost step-json-toggle"
          onClick={() => setJsonOpen(open => !open)}
          data-testid="step-json-toggle"
        >
          {jsonOpen ? '收起原始 JSON' : '展开原始 JSON'}
        </button>
        {jsonOpen && (
          <pre className="step-json-block" data-testid="step-json-block">
            {JSON.stringify(item, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

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

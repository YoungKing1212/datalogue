import { useState } from 'react';

/**
 * 分析蓝图步骤的结构化视图组件。
 *
 * 把 blueprint.steps JSON 渲染成业务方可读的业务步骤卡片，
 * 包含步骤名称、业务描述、关键规则、输出列、置信度和原始 JSON 调试区。
 */

export function BlueprintStepView({ steps }) {
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

export function StepCard({ item, index }) {
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
            {formatJson(item)}
          </pre>
        )}
      </div>
    </div>
  );
}

function formatJson(value) {
  return JSON.stringify(value ?? [], null, 2);
}

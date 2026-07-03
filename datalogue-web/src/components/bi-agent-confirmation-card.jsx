// bi-agent-confirmation-card.jsx
// BI Agent 查询范围确认卡片：只展示路由级能力摘要，确认时仅回传可审计的白名单字段。

import React from 'react';

const SNAPSHOT_ALLOWED_KEYS = [
  'dataset_id',
  'name',
  'domain',
  'supported_questions',
  'key_metrics',
  'key_dimensions',
  'freshness',
  'availability',
];

function normalizeSnapshot(snapshot = {}) {
  return SNAPSHOT_ALLOWED_KEYS.reduce((acc, key) => {
    if (snapshot[key] !== undefined && snapshot[key] !== null) {
      acc[key] = snapshot[key]; // capability snapshot 只保留前端确认需要的摘要字段，丢弃 schema/sql/raw rows 等内部执行细节。
    }
    return acc;
  }, {});
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  if (value === undefined || value === null || value === '') return [];
  return [String(value)];
}

function Field({ label, value }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div className="bi-agent-confirmation-card__field">
      <dt>{label}</dt>
      <dd>{String(value)}</dd>
    </div>
  );
}

function TagList({ label, items }) {
  const normalizedItems = asList(items);
  if (normalizedItems.length === 0) return null;
  return (
    <div className="bi-agent-confirmation-card__section">
      <span className="bi-agent-confirmation-card__section-label">{label}</span>
      <ul className="bi-agent-confirmation-card__tags" aria-label={label}>
        {normalizedItems.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function BIAgentConfirmationCard({ run, onCancel, onConfirm }) {
  const request = run?.confirmation_request;
  if (!request?.dataset_id) return null;

  const capabilitySnapshot = normalizeSnapshot(request.capability_snapshot || {});
  const datasetName = capabilitySnapshot.name || `数据集 ${request.dataset_id}`;
  const domain = capabilitySnapshot.domain || '未标注';

  const handleConfirm = () => {
    onConfirm?.({
      dataset_id: request.dataset_id,
      confirmed_question: request.confirmed_question,
      task_goal: request.task_goal,
      capability_snapshot: capabilitySnapshot, // 回传给后端的确认包也必须是裁剪后的快照，避免 UI 层把内部字段带回执行面。
      routing_rationale: request.routing_rationale,
      risk_notice: request.risk_notice,
      user_decision: 'approved',
    });
  };

  return (
    <section className="bi-agent-confirmation-card" aria-label="BI Agent 确认查询范围">
      <header className="bi-agent-confirmation-card__header">
        <div>
          <p className="bi-agent-confirmation-card__eyebrow">BI Agent</p>
          <h3>确认查询范围</h3>
        </div>
      </header>

      <dl className="bi-agent-confirmation-card__summary">
        <Field label="数据集" value={datasetName} />
        <Field label="业务域" value={domain} />
        <Field label="刷新" value={capabilitySnapshot.freshness} />
        <Field label="可用性" value={capabilitySnapshot.availability} />
      </dl>

      <TagList label="关键指标" items={capabilitySnapshot.key_metrics} />
      <TagList label="关键维度" items={capabilitySnapshot.key_dimensions} />
      <TagList label="支持问题" items={capabilitySnapshot.supported_questions} />

      {request.routing_rationale && (
        <div className="bi-agent-confirmation-card__notice">
          <span>选择理由</span>
          <p>{request.routing_rationale}</p>
        </div>
      )}

      {request.risk_notice && (
        <div className="bi-agent-confirmation-card__notice bi-agent-confirmation-card__notice--risk">
          <span>提示</span>
          <p>{request.risk_notice}</p>
        </div>
      )}

      <footer className="bi-agent-confirmation-card__actions">
        <button type="button" className="btn ghost" onClick={() => onCancel?.(request)}>
          取消
        </button>
        <button type="button" className="btn primary" onClick={handleConfirm}>
          确认查询
        </button>
      </footer>
    </section>
  );
}

export default BIAgentConfirmationCard;

// DatalogueDataUI.jsx
// 承载"非模型工具"的业务 payload：artifact card、候选数据集、图表 preview。
// 这些数据由后端业务决定，不应强塞成 tool-call；assistant-ui 提供的 DataMessagePart
// ({ type: 'data', name, data }) 是标准渠道。
// 组件按 part.name 分派到具体子渲染器，同时兜底 metadata.custom.artifactCard /
// custom.candidateDatasets 场景，保持渐进迁移。

import React from 'react';
import ArtifactCard from '../components/artifact-card';
import {
  firstSafeText,
  safeVisibleText,
} from './message-parts';

function safeCandidateDatasets(payload = {}) {
  if (!payload || typeof payload !== 'object') return null;
  const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
  const safe = candidates
    .map((c = {}) => {
      const datasetName = safeVisibleText(c.dataset_name || c.datasetName);
      const shortReason = safeVisibleText(c.short_reason || c.shortReason || c.reason);
      const datasetId = c.dataset_id ?? c.datasetId ?? null;
      if (!datasetName) return null;
      return {
        dataset_name: datasetName,
        dataset_id: datasetId,
        short_reason: shortReason || null,
      };
    })
    .filter(Boolean);
  if (!safe.length) return null;
  return {
    original_question: safeVisibleText(payload.original_question || payload.originalQuestion),
    candidates: safe,
  };
}

function CandidateDatasetsView({ data }) {
  const safe = safeCandidateDatasets(data);
  if (!safe) return null;
  return (
    <div className="artifact-card" data-data-ui="candidate-datasets">
      <div className="artifact-card-head">
        <span className="artifact-card-head-left">
          <strong>候选数据集</strong>
        </span>
      </div>
      <div className="artifact-card-body">
        {safe.original_question && (
          <p className="artifact-card-preview-text">
            {firstSafeText([safe.original_question], safe.original_question)}
          </p>
        )}
        <ul className="artifact-card-list">
          {safe.candidates.map((c) => (
            <li key={`${c.dataset_id || c.dataset_name}`} className="artifact-card-list-item">
              <strong>{c.dataset_name}</strong>
              {c.short_reason && <span className="artifact-card-summary">{c.short_reason}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/**
 * DatalogueDataUI —— 单个 DataMessagePart 的分派入口。
 *
 * 期望 part = { type: 'data', name: string, data: object }。
 * 目前支持：
 *   - 'datalogue-artifact-card' → 复用 ArtifactCard（业务卡）。
 *   - 'datalogue-candidate-datasets' → 候选数据集选择卡。
 * 未知 name 静默不渲染，避免把未过滤 payload 泄漏进 DOM。
 */
export function DatalogueDataUI({ part = {} }) {
  const name = String(part.name || '').trim();
  const data = part.data && typeof part.data === 'object' ? part.data : null;
  if (!name || !data) return null;
  if (name === 'datalogue-artifact-card') {
    return <ArtifactCard artifact={data} />;
  }
  if (name === 'datalogue-candidate-datasets') {
    return <CandidateDatasetsView data={data} />;
  }
  return null;
}

export default DatalogueDataUI;

// DatalogueReasoning.jsx
// 展示 ChainOfThought/Reason 的安全业务摘要，避免暴露控制面与查询细节。
// 阶段 2：升级为 Markdown 渲染。字段优先级：
//   1) metadata.summary / business_summary / reason 等安全 reasoning_summary
//   2) part.summary / part.text 兜底
//   3) 从 part.text 里剥出的模型自吐 <think> 内容（显式标注为「模型自吐」）
// 全流程走 sanitizeThinkAndMarkdown，保证 <think> 内容不进正文。

import React from 'react';
import { DatalogueMarkdownFallback } from './DatalogueMarkdown';
import {
  collectSafeRefs,
  elapsedLabel,
  firstSafeMarkdown,
  normalizeStatus,
  partMetadata,
  rowCountFrom,
  safeMarkdownText,
  sanitizeThinkAndMarkdown,
  statusLabel,
} from './message-parts';

// 从 part 中挑选安全的 Markdown 摘要，同时把可能被吞进 part.text 的
// <think> 段单独收集起来，交给折叠区二级块渲染。
function pickReasoningContent(part) {
  const metadata = partMetadata(part);
  // reasoning_summary 是治理过的“安全字段”，优先展示。
  const safeSummary = firstSafeMarkdown([
    metadata.summary,
    metadata.business_summary,
    metadata.businessSummary,
    metadata.reason,
    part?.summary,
  ]);
  if (safeSummary) {
    return { markdown: safeSummary, thinkBlocks: [], source: 'summary' };
  }
  // text 兜底：先剥离 <think> 后作为 Markdown。若 text 本身包含 SQL / schema
  // 等控制面关键字，会被 safeMarkdownText 判定为不安全而返回 null。
  const rawText = part?.text;
  if (rawText) {
    const { mainMarkdown, thinkBlocks } = sanitizeThinkAndMarkdown(rawText);
    const safeText = safeMarkdownText(mainMarkdown);
    if (safeText) {
      return { markdown: safeText, thinkBlocks, source: 'text' };
    }
    // 正文不安全或为空，但 <think> 里可能仍有可展示的自吐推理（进一步过滤 SQL 等）。
    const safeThink = thinkBlocks.map((block) => safeMarkdownText(block)).filter(Boolean);
    if (safeThink.length) {
      return { markdown: null, thinkBlocks: safeThink, source: 'think' };
    }
  }
  return { markdown: null, thinkBlocks: [], source: 'none' };
}

export function DatalogueReasoning({ part = {}, children, group }) {
  const metadata = partMetadata(part);
  const status = normalizeStatus(part);
  const running = status === 'running';
  const refs = collectSafeRefs(
    metadata.artifact_ref,
    metadata.artifactRef,
    metadata.checkpoint_ref,
    metadata.checkpointRef,
    metadata.run_id,
    metadata.runId,
    metadata.refs,
    part.refs,
  );
  const elapsed = elapsedLabel(metadata.elapsed_ms ?? metadata.elapsedMs ?? part.elapsed_ms ?? part.elapsedMs);
  const rowCount = rowCountFrom(metadata, part);
  const count = group?.indices?.length ?? part?.indices?.length ?? null;

  const { markdown, thinkBlocks } = pickReasoningContent(part);
  const fallbackText = children ? null : (markdown ? null : '已完成一个处理步骤');

  return (
    <details className="cot cot-root" open={running}>
      <summary className="cot-trigger">
        <span className="cot-trigger-inner">
          <span>思考过程</span>
          <span className={`artifact-card-status artifact-card-status-${status === 'failed' ? 'error' : status}`}>
            {statusLabel(status)}
          </span>
          {count != null && <span className="artifact-card-ref">{count} 步</span>}
          {elapsed && <span className="artifact-card-ref">{elapsed}</span>}
        </span>
      </summary>
      <div className="cot-step">
        <div className="cot-step-icon">{running ? '...' : '✓'}</div>
        <div className="cot-step-body">
          <div className="cot-step-label">业务摘要</div>
          <div className="cot-step-text">
            {children}
            {!children && markdown && (
              <DatalogueMarkdownFallback text={markdown} className="cot-step-md" />
            )}
            {!children && !markdown && fallbackText && (
              <span>{fallbackText}</span>
            )}
          </div>
          {thinkBlocks.length > 0 && (
            <div className="cot-step-think">
              <div className="cot-step-label">模型自吐 &lt;think&gt;</div>
              {thinkBlocks.map((block, index) => (
                <DatalogueMarkdownFallback
                  key={index}
                  text={block}
                  className="cot-step-md cot-step-md-think"
                />
              ))}
            </div>
          )}
          {(rowCount != null || refs.length > 0) && (
            <div className="artifact-card-refs" style={{ marginTop: 8 }}>
              {rowCount != null && <span className="artifact-card-ref">{rowCount} 行</span>}
              {refs.map((ref) => <code key={ref} className="artifact-card-ref">{ref}</code>)}
            </div>
          )}
        </div>
      </div>
    </details>
  );
}

export default DatalogueReasoning;

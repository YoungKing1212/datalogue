import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AuiIf,
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useAuiState,
  useLocalRuntime,
} from '@assistant-ui/react';
import { makeChatAdapter } from '../features/chat/chat-adapter';
import { Icon } from './icons';

const TAB_PROMPTS = {
  tables: [
    '帮我判断当前数据集应该优先选择哪些表，给出选择理由。',
    '从表资产角度检查这个数据集还缺哪些基础表。',
  ],
  fields: [
    '帮我审核当前字段标注，指出哪些字段适合做指标或维度。',
    '给我一份字段语义标注检查清单。',
  ],
  metrics: [
    '基于当前数据集，建议我应该补充哪些核心指标。',
    '帮我检查指标口径是否容易产生歧义。',
  ],
  dimensions: [
    '基于当前数据集，建议我应该补充哪些分析维度。',
    '帮我整理维度枚举值和同义词的治理建议。',
  ],
  terms: [
    '帮我设计这个数据集的业务术语库结构。',
    '列出可能需要统一的业务别名和口径解释。',
  ],
  blueprints: [
    '帮我设计一个适合当前数据集的分析蓝图。',
    '哪些高频复杂问法适合沉淀为分析蓝图？',
  ],
  scenarios: [
    '帮我整理这个数据集适合覆盖的分析场景。',
    '给我 5 个可以用于验收的业务问题。',
  ],
  validation: [
    '帮我生成 5 个语义验证问题，覆盖指标、维度和时间范围。',
    '如何判断当前语义层是否已经可发布？',
  ],
  permissions: [
    '帮我设计这个数据集的权限分层方案。',
    '哪些字段或指标可能需要敏感权限控制？',
  ],
  versions: [
    '帮我总结语义资产版本发布时需要检查的内容。',
    '给我一份数据集变更影响分析清单。',
  ],
};

function DatasetAssistantRuntime({ datasetId, children }) {
  const datasetIdRef = useRef(datasetId ?? null);

  useEffect(() => {
    datasetIdRef.current = datasetId ?? null;
  }, [datasetId]);

  const runtime = useLocalRuntime(makeChatAdapter({ datasetIdRef }));

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}

function SuggestionButton({ prompt }) {
  const api = useAui();
  return (
    <button
      type="button"
      className="dataset-ai-suggestion"
      onClick={() => api.composer().setText(prompt)}
    >
      <Icon name="sparkle" />
      <span>{prompt}</span>
    </button>
  );
}

function DatasetAssistantEmpty({ datasetName, activeTab }) {
  const prompts = TAB_PROMPTS[activeTab] || TAB_PROMPTS.blueprints;
  return (
    <div className="dataset-ai-empty">
      <div className="dataset-ai-empty-icon"><Icon name="brain" /></div>
      <h3>语义治理助手</h3>
      <p>
        当前绑定 {datasetName || '当前数据集'}，可以围绕表选择、字段标注、指标维度和分析蓝图给出建议。
      </p>
      <div className="dataset-ai-suggestions">
        {prompts.map(prompt => (
          <SuggestionButton key={prompt} prompt={prompt} />
        ))}
      </div>
    </div>
  );
}

function DatasetAssistantMessage() {
  const message = useAuiState(s => s.message);
  const role = message?.role || 'assistant';

  return (
    <MessagePrimitive.Root className={`dataset-ai-message ${role}`}>
      <MessagePrimitive.Parts>
        {({ part }) => {
          if (part.type === 'text') {
            return <div className="dataset-ai-text">{part.text}</div>;
          }
          if (part.type === 'reasoning') {
            return (
              <details className="dataset-ai-reasoning">
                <summary>执行步骤</summary>
                <div>{part.text}</div>
              </details>
            );
          }
          return null;
        }}
      </MessagePrimitive.Parts>
    </MessagePrimitive.Root>
  );
}

function DatasetAssistantComposer() {
  return (
    <ComposerPrimitive.Root className="dataset-ai-composer">
      <ComposerPrimitive.Input
        className="dataset-ai-input"
        rows={2}
        placeholder="问语义治理问题，例如：这个数据集还缺哪些核心指标？"
      />
      <div className="dataset-ai-composer-bar">
        <span><Icon name="database" />绑定当前数据集</span>
        <AuiIf condition={({ thread }) => thread.isRunning}>
          <ComposerPrimitive.Cancel className="dataset-ai-send cancel" aria-label="停止生成">
            <Icon name="x" />
          </ComposerPrimitive.Cancel>
        </AuiIf>
        <AuiIf condition={({ thread }) => !thread.isRunning}>
          <ComposerPrimitive.Send className="dataset-ai-send" aria-label="发送">
            <Icon name="send" />
          </ComposerPrimitive.Send>
        </AuiIf>
      </div>
    </ComposerPrimitive.Root>
  );
}

function DatasetAssistantSurface({ datasetName, activeTab, stats }) {
  const [collapsed, setCollapsed] = useState(false);
  const statItems = useMemo(() => [
    ['表', stats?.tables ?? 0],
    ['字段', stats?.columns ?? 0],
    ['指标', stats?.metrics ?? 0],
    ['维度', stats?.dimensions ?? 0],
  ], [stats]);

  if (collapsed) {
    return (
      <button className="dataset-ai-collapsed" onClick={() => setCollapsed(false)}>
        <Icon name="brain" />
        <span>语义治理助手</span>
        <strong>assistant-ui</strong>
      </button>
    );
  }

  return (
    <ThreadPrimitive.Root className="dataset-ai-panel">
      <div className="dataset-ai-head">
        <div>
          <div className="dataset-ai-kicker"><Icon name="sparkle" />assistant-ui copilot</div>
          <h3>语义治理助手</h3>
        </div>
        <div className="dataset-ai-head-actions">
          <div className="dataset-ai-mini-stats">
            {statItems.map(([label, value]) => (
              <span key={label}>{label}<strong>{value}</strong></span>
            ))}
          </div>
          <button className="icon-btn" title="收起助手" onClick={() => setCollapsed(true)}>
            <Icon name="chev_down" />
          </button>
        </div>
      </div>

      <ThreadPrimitive.Empty>
        <DatasetAssistantEmpty datasetName={datasetName} activeTab={activeTab} />
      </ThreadPrimitive.Empty>

      <AuiIf condition={({ thread }) => !thread.isEmpty}>
        <ThreadPrimitive.Viewport autoScroll className="dataset-ai-scroll">
          <ThreadPrimitive.Messages>
            {() => <DatasetAssistantMessage />}
          </ThreadPrimitive.Messages>
        </ThreadPrimitive.Viewport>
      </AuiIf>

      <DatasetAssistantComposer />
    </ThreadPrimitive.Root>
  );
}

export function DatasetAssistantPanel({ datasetId, datasetName, activeTab, stats }) {
  return (
    <DatasetAssistantRuntime datasetId={datasetId}>
      <DatasetAssistantSurface datasetName={datasetName} activeTab={activeTab} stats={stats} />
    </DatasetAssistantRuntime>
  );
}

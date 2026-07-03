// DatalogueComposer — Datalogue 聊天输入区的 assistant-ui 可见壳层。
// 仅承接 ComposerPrimitive 与当前 dataset/model/tool chip 视觉，不改变 runtime 与发送协议。

import React, { useState } from 'react';
import {
  ComposerPrimitive,
  unstable_useComposerInputHistory,
  useAuiState,
} from '@assistant-ui/react';
import { Icon } from '../components/icons';

/**
 * DatasetChip — 数据集选择 chip。
 * 保持旧 MyComposer 的 props 语义：null 表示全部数据集，选中对象只用于当前轮次 UI/请求上下文。
 */
export function DatasetChip({
  selectedDs,
  setSelectedDs,
  datasetList = [],
  variant = 'tool',
}) {
  const [open, setOpen] = useState(false);
  const isCe = variant === 'ce';
  const btnClass = isCe
    ? `ce-pill${selectedDs ? ' on' : ''}`
    : 'tool-chip';

  return (
    <div style={{ position: 'relative' }}>
      <button type="button" className={btnClass} onClick={() => setOpen((v) => !v)}>
        <Icon name="database" />
        <span>{selectedDs ? selectedDs.name : '全部数据集'}</span>
        {isCe ? (
          <Icon name="chev_down" className="chev" />
        ) : (
          <span className="chip-caret">▾</span>
        )}
      </button>
      {open && (
        <div className="ds-dropdown">
          <div className="ds-dropdown-head">选择数据集</div>
          <div
            className="ds-dropdown-item"
            onClick={() => {
              setSelectedDs?.(null); // null 是“不过滤数据集”的业务语义，不是未加载。
              setOpen(false);
            }}
          >
            全部数据集
          </div>
          {datasetList.map((ds) => (
            <div
              key={ds.id}
              className={`ds-dropdown-item ${selectedDs?.id === ds.id ? 'active' : ''}`}
              onClick={() => {
                setSelectedDs?.(ds);
                setOpen(false);
              }}
            >
              {ds.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * ModelChip — 当前轮模型选择 chip。
 * selectedModel 为空时沿用后端角色绑定默认模型，前端不推断真实密钥、Base URL 或 provider 配置。
 */
export function ModelChip({
  selectedModel,
  setSelectedModel = () => {},
  modelList = [],
  variant = 'tool',
}) {
  const [open, setOpen] = useState(false);
  const isCe = variant === 'ce';
  const btnClass = isCe
    ? `ce-pill${selectedModel ? ' on' : ''}`
    : `tool-chip${selectedModel ? ' on' : ''}`;
  const activeModels = modelList.filter((model) => model.status === 'active');
  const label = selectedModel ? selectedModel.name : '默认模型';

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        className={btnClass}
        onClick={() => setOpen((v) => !v)}
        title={label}
      >
        <Icon name="brain" />
        <span>{label}</span>
        {isCe ? (
          <Icon name="chev_down" className="chev" />
        ) : (
          <span className="chip-caret">▾</span>
        )}
      </button>
      {open && (
        <div className="ds-dropdown model-dropdown">
          <div className="ds-dropdown-head">选择模型</div>
          <div
            className={`ds-dropdown-item${selectedModel ? '' : ' active'}`}
            onClick={() => {
              setSelectedModel(null); // null 明确表示本轮不 override，由后端按角色绑定兜底。
              setOpen(false);
            }}
          >
            <div className="model-option-name">默认模型</div>
            <div className="model-option-meta">沿用系统角色绑定</div>
          </div>
          {activeModels.length === 0 && (
            <div className="ds-dropdown-item muted">暂无启用模型</div>
          )}
          {activeModels.map((model) => (
            <div
              key={model.id}
              className={`ds-dropdown-item ${selectedModel?.id === model.id ? 'active' : ''}`}
              onClick={() => {
                setSelectedModel(model); // 只保存配置行，发送链路继续交给现有 adapter/runtime 处理。
                setOpen(false);
              }}
            >
              <div className="model-option-name">{model.name}</div>
              <div className="model-option-meta">{model.provider} · {model.model}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SendOrCancelButton() {
  const isRunning = useAuiState((s) => s.thread?.isRunning);
  if (isRunning) {
    return (
      <ComposerPrimitive.Cancel className="composer-fab composer-fab-cancel" aria-label="停止生成">
        <Icon name="x" style={{ width: 16, height: 16 }} />
      </ComposerPrimitive.Cancel>
    );
  }

  return (
    <ComposerPrimitive.Send className="composer-fab composer-fab-send" aria-label="发送">
      <Icon name="send" style={{ width: 16, height: 16 }} />
    </ComposerPrimitive.Send>
  );
}

function ToolChips({
  selectedDs,
  setSelectedDs,
  datasetList,
  selectedModel,
  setSelectedModel,
  modelList,
}) {
  return (
    <>
      <DatasetChip
        selectedDs={selectedDs}
        setSelectedDs={setSelectedDs}
        datasetList={datasetList}
      />
      <ModelChip
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
        modelList={modelList}
      />
      <button type="button" className="tool-chip">
        <Icon name="calendar" />
        <span>近7天</span>
        <span className="chip-caret">▾</span>
      </button>
      <button type="button" className="tool-chip">
        <Icon name="brain" />
        <span>深度归因</span>
      </button>
    </>
  );
}

/**
 * DatalogueComposer — P1 独立组件层。
 * variant='hero' 用欢迎态 ask-hero；默认 composer 用底部输入区，不负责把 dataset/model 写入 runtime。
 */
export function DatalogueComposer({
  selectedDs,
  setSelectedDs,
  datasetList = [],
  selectedModel,
  setSelectedModel = () => {},
  modelList = [],
  variant = 'composer',
}) {
  const inputHistory = unstable_useComposerInputHistory();
  const chipProps = {
    selectedDs,
    setSelectedDs,
    datasetList,
    selectedModel,
    setSelectedModel,
    modelList,
  };

  if (variant === 'welcome') {
    return (
      <ComposerPrimitive.Root className="ce-composer">
        <ComposerPrimitive.Input
          className="ce-input"
          rows={2}
          placeholder="例如：上周华东区销售为什么下降？哪个品类拖累最大？"
          {...inputHistory}
        />
        <div className="ce-bar">
          <DatasetChip variant="ce" {...chipProps} />
          <ModelChip variant="ce" {...chipProps} />
          <button type="button" className="ce-pill">
            <Icon name="calendar" />
            <span>近 7 天</span>
            <Icon name="chev_down" className="chev" />
          </button>
          <button type="button" className="ce-pill">
            <Icon name="brain" />
            <span>深度归因</span>
          </button>
          <ComposerPrimitive.Send className="ce-send" aria-label="发送">
            <Icon name="send" />
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    );
  }

  if (variant === 'hero') {
    return (
      <ComposerPrimitive.Root className="ask-hero">
        <ComposerPrimitive.Input
          className="ask-input"
          rows={2}
          placeholder="例如：上周华东区销售为什么下降？"
          {...inputHistory}
        />
        <div className="toolbar">
          <ToolChips {...chipProps} />
          <div className="spacer" />
          <SendOrCancelButton />
        </div>
      </ComposerPrimitive.Root>
    );
  }

  return (
    <div className="composer-wrap">
      <ComposerPrimitive.Root className="composer">
        <div className="composer-inner">
          <ComposerPrimitive.Input
            className="composer-input"
            rows={1}
            placeholder="问个数，或者点击上面的快捷词"
            {...inputHistory}
          />
          <div className="composer-toolbar">
            <ToolChips {...chipProps} />
            <div className="spacer" />
            <SendOrCancelButton />
          </div>
        </div>
      </ComposerPrimitive.Root>
    </div>
  );
}

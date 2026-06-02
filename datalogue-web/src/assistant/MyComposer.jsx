// MyComposer — assistant-ui ComposerPrimitive 包装
// 现代设计：磨砂背景、圆角、顶部 toolbar chip（数据集 / 时间范围 / 深度归因）
// 自动响应 isRunning 状态（运行时显示 Cancel，圆形浮动按钮）
// 两种 variant：hero（欢迎屏中央）/ composer（消息列表底部固定）

import React, { useState } from 'react';
import { ComposerPrimitive, useAuiState } from '@assistant-ui/react';
import { Icon } from '../components/icons';

/**
 * DatasetChip — 数据集选择下拉（保留旧版交互）
 * variant='ce' 用新空白态 ce-pill 样式（带 chev_down 图标）
 * variant='tool' 用旧版 tool-chip 样式（默认）
 */
export function DatasetChip({
  selectedDs,
  setSelectedDs,
  datasetList,
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
              setSelectedDs(null);
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
                setSelectedDs(ds);
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
 * SendOrCancelButton — 圆形浮动按钮（运行时切 Cancel）
 */
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

/**
 * 占位组件 — 当 composer 内部还没有内容时 hint
 */
function ComposerIf({ children }) {
  // 简化：直接渲染 children（toolbar 始终显示）
  return children;
}

/**
 * MyComposer 主组件
 */
export function MyComposer({ selectedDs, setSelectedDs, datasetList, variant = 'composer' }) {
  if (variant === 'hero') {
    return (
      <ComposerPrimitive.Root className="ask-hero">
        <ComposerPrimitive.Input
          className="ask-input"
          rows={2}
          placeholder="例如：上周华东区销售为什么下降？"
        />
        <div className="toolbar">
          <DatasetChip
            selectedDs={selectedDs}
            setSelectedDs={setSelectedDs}
            datasetList={datasetList}
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
          />
          <div className="composer-toolbar">
            <DatasetChip
              selectedDs={selectedDs}
              setSelectedDs={setSelectedDs}
              datasetList={datasetList}
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
            <div className="spacer" />
            <SendOrCancelButton />
          </div>
        </div>
      </ComposerPrimitive.Root>
    </div>
  );
}

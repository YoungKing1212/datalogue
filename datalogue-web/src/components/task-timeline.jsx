// task-timeline.jsx
// 业务级任务时间线组件：展示用户能理解的"做了哪几步"。
// 只展示五类节点：任务理解、数据集匹配、BI 执行、结果产物、下一步动作。
// 绝不展示 SQL 文本、schema 明细、表名/字段名、raw result 等技术细节。

import React from 'react';
import { Icon } from './icons';

// ── 五类节点配置 ──
const NODE_CONFIG = {
  task_understood: {
    label: '任务理解',
    icon: 'brain',
    order: 1,
  },
  dataset_matching: {
    label: '数据集匹配',
    icon: 'database',
    order: 2,
  },
  bi_execution: {
    label: 'BI 执行',
    icon: 'play',
    order: 3,
  },
  repair_patch: {
    label: '自动修复',
    icon: 'branch',
    order: 3.5,
  },
  artifact_created: {
    label: '结果产物',
    icon: 'table',
    order: 4,
  },
  next_action: {
    label: '下一步',
    icon: 'arrow_up_right',
    order: 5,
  },
};

// ── 安全扫描：禁止在渲染文本中出现技术细节关键词 ──
const FORBIDDEN_PATTERNS = [
  /\bselect\b/i,
  /\bFROM\b/,
  /\bWHERE\b/,
  /\bGROUP BY\b/i,
  /\bJOIN\b/i,
  /\bschema\b/i,
  /\braw.?result\b/i,
  /\braw.?sql\b/i,
  /SELECT\b/,
];

function sanitize(text) {
  if (!text) return '';
  // 若文案意外包含被禁关键词，截断到关键词之前并追加省略号
  for (const pattern of FORBIDDEN_PATTERNS) {
    const match = pattern.exec(text);
    if (match) {
      if (typeof console !== 'undefined') {
        console.debug('[TaskTimeline] forbidden content detected, sanitized:', match[0]);
      }
      return text.slice(0, match.index).trim() + '…';
    }
  }
  return text;
}

// ── 单个时间线节点 ──
function TimelineNode({ event, isLast }) {
  const config = NODE_CONFIG[event.type] || {
    label: event.label || event.type || '步骤',
    icon: 'check',
    order: 99,
  };

  const text = sanitize(event.text || '');

  return (
    <div className={`task-timeline-node task-timeline-node-${event.status || 'done'}`}>
      {/* 连接线 */}
      {!isLast && <div className="task-timeline-connector" />}

      {/* 图标区域 */}
      <div className="task-timeline-icon">
        {event.status === 'done' ? (
          <span className="task-timeline-icon-done">
            <Icon name="check" style={{ width: 11, height: 11, color: 'var(--pos)' }} />
          </span>
        ) : event.status === 'running' ? (
          <span className="task-timeline-icon-running pulse" />
        ) : event.status === 'error' ? (
          <span className="task-timeline-icon-error">
            <Icon name="warn" style={{ width: 11, height: 11, color: 'var(--neg)' }} />
          </span>
        ) : (
          <span className="task-timeline-icon-pending" />
        )}
      </div>

      {/* 内容区 */}
      <div className="task-timeline-node-body">
        <div className="task-timeline-label">
          <Icon name={config.icon} style={{ width: 12, height: 12 }} />
          <span>{config.label}</span>
        </div>
        {text && <div className="task-timeline-text">{text}</div>}
      </div>
    </div>
  );
}

// ── TaskTimeline 对外组件 ──
/**
 * @param {object[]} events - 时间线事件数组
 * @param {string} events[].type - task_understood | dataset_matching | bi_execution | artifact_created | next_action
 * @param {string} events[].label - 展示标签（可选，优先使用内置标签）
 * @param {string} events[].text - 业务描述文本
 * @param {string} events[].status - done | running | pending | error
 * @param {boolean} collapsed - 初始是否折叠（默认展开）
 */

export default function TaskTimeline({ events, collapsed: initialCollapsed = false }) {
  const [collapsed, setCollapsed] = React.useState(initialCollapsed);

  if (!Array.isArray(events) || events.length === 0) return null;

  // 按节点 order 排序
  const sorted = [...events].sort((a, b) => {
    const orderA = NODE_CONFIG[a.type]?.order ?? 99;
    const orderB = NODE_CONFIG[b.type]?.order ?? 99;
    return orderA - orderB;
  });

  // 统计完成数
  const doneCount = sorted.filter((e) => e.status === 'done').length;

  return (
    <div className="task-timeline">
      <button
        type="button"
        className="task-timeline-head"
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
      >
        <span className="task-timeline-head-left">
          <Icon name="sparkle" style={{ width: 14, height: 14 }} />
          <strong>执行过程</strong>
          {!collapsed && (
            <span className="task-timeline-count">
              {doneCount}/{sorted.length}
            </span>
          )}
        </span>
        <Icon
          name="chev_down"
          className="task-timeline-chev"
          style={{ width: 12, height: 12 }}
        />
      </button>

      {!collapsed && (
        <div className="task-timeline-body">
          {sorted.map((event, i) => (
            <TimelineNode
              key={event.type + '-' + i}
              event={event}
              isLast={i === sorted.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

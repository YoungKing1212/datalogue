// TaskTimeline — Chat 内的 C-ready 业务任务时间线，只展示阶段状态和业务摘要。

import { Icon } from './icons';

const STATUS_ICON = {
  done: 'check',
  active: 'play',
  blocked: 'warn',
  pending: 'clock',
};

function statusLabel(status) {
  if (status === 'done') return '完成';
  if (status === 'active') return '进行中';
  if (status === 'blocked') return '阻塞';
  return '等待';
}

export function TaskTimeline({ items = [] }) {
  const visibleItems = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!visibleItems.length) return null;

  return (
    <section className="task-timeline" aria-label="任务时间线">
      {visibleItems.map((item) => {
        const status = item.status || 'pending';
        return (
          <div className={`task-timeline-item task-timeline-${status}`} key={item.id || item.label}>
            <span className="task-timeline-icon">
              <Icon name={STATUS_ICON[status] || STATUS_ICON.pending} />
            </span>
            <div className="task-timeline-body">
              <strong>{item.label}</strong>
              {item.detail && <span>{item.detail}</span>}
            </div>
            <em>{statusLabel(status)}</em>
          </div>
        );
      })}
    </section>
  );
}

export default TaskTimeline;

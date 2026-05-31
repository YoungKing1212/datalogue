import React, { Fragment, useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from './icons';
import { listConversations } from '../api/client';

// Sidebar — restructured to match design doc IA: 4 groups.

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;

  const isActive = (id) => {
    if (id === 'home') return path === '/';
    if (id === 'chat') return path === '/chat' || path.startsWith('/chat/');
    return path === '/' + id;
  };

  const go = (id) => navigate(id === 'home' ? '/' : '/' + id);

  const [recentConvs, setRecentConvs] = useState([]);

  // 拉取最近 8 条会话，监听 new-conversation 事件刷新
  useEffect(() => {
    const load = () =>
      listConversations()
        .then(data => setRecentConvs((data || []).slice(0, 8)))
        .catch(console.error);
    load();
    window.addEventListener('new-conversation', load);
    return () => window.removeEventListener('new-conversation', load);
  }, []);

  const groups = [
    {
      label: '问数中心',
      items: [
        { id: 'home',      label: '工作台',     icon: 'home' },
        { id: 'chat',      label: '对话问数',   icon: 'chat' },
        { id: 'dashboard', label: '监控大盘',   icon: 'layout', count: '6', isNew: true },
        { id: 'history',   label: '查询历史',   icon: 'history' },
        { id: 'pinned',    label: '我的收藏',   icon: 'bookmark' },
        { id: 'apis',      label: 'API 接口',   icon: 'api', count: '7' },
      ],
    },
    {
      label: '语义治理',
      items: [
        { id: 'datasets',  label: '数据集 & 指标', icon: 'database', count: '24' },
        { id: 'knowledge', label: '知识库',       icon: 'brain', count: '234', isNew: true },
        { id: 'review',    label: '审核队列',     icon: 'check', count: '5', isNew: true, dot: true },
      ],
    },
    {
      label: '数据连接',
      items: [
        { id: 'datasources', label: '数据源', icon: 'plug', count: '4' },
      ],
    },
    {
      label: '系统管理',
      items: [
        { id: 'audit-query', label: '查询审计', icon: 'log', isNew: true },
        { id: 'settings',    label: '系统设置', icon: 'cog' },
      ],
    },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark" />
        <div>
          <div className="brand-name">数语 <span className="brand-sub">Datalogue</span></div>
        </div>
      </div>

      <button className="new-thread" onClick={() => go('chat')}>
        <Icon name="plus" />
        <span>新的问数</span>
        <span className="kbd">⌘ K</span>
      </button>

      {groups.map((g, i) => (
        <Fragment key={i}>
          <div className="nav-section">{g.label}</div>
          {g.items.map(n => (
            <button
              key={n.id}
              className={'nav-item ' + (isActive(n.id) ? 'active' : '')}
              onClick={() => go(n.id)}
            >
              <Icon name={n.icon} />
              <span>{n.label}</span>
              {n.dot && <span className="nav-dot" />}
              {n.isNew && !n.count && <span className="nav-new">NEW</span>}
              {n.count && <span className="count">{n.count}</span>}
            </button>
          ))}
        </Fragment>
      ))}

      <div className="nav-section">最近会话</div>
      {recentConvs.map(r => (
        <button
          key={r.id}
          className={'recent-thread' + (path === `/chat/${r.id}` ? ' active' : '')}
          onClick={() => navigate(`/chat/${r.id}`)}
          title={r.title}
        >
          {r.title}
        </button>
      ))}
      {recentConvs.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', padding: '4px 16px' }}>
          暂无会话
        </div>
      )}

      <div className="sidebar-footer">
        <div className="avatar">YL</div>
        <div className="who">
          <span className="name">Yan Lin</span>
          <span className="role">运营 · 华东区</span>
        </div>
        <Icon name="chev" />
      </div>
    </aside>
  );
}

export { Sidebar };
import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from './icons';
import { useAuth } from '../auth/auth-context';
import { listNavigationCounts } from '../api/client';

// Sidebar — restructured to match design doc IA: 4 groups.
// "最近会话"区已迁出至 chat 页面的独立 ThreadList 左列。

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [navCounts, setNavCounts] = useState({});
  const path = location.pathname;
  const displayName = user?.full_name || user?.username || '未登录用户';
  const roleLabel = user?.is_superuser ? '超级管理员' : user?.role === 'admin' ? '管理员' : '工作区成员';
  const avatarText = displayName.trim().slice(0, 1).toUpperCase() || '?';

  useEffect(() => {
    let cancelled = false;
    listNavigationCounts()
      .then((counts) => {
        if (!cancelled) setNavCounts(counts || {}); // 真实统计缺失时保持空 badge，不回退到演示数字。
      })
      .catch((err) => {
        console.error('加载导航数量失败:', err);
        if (!cancelled) setNavCounts({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const countFor = (id) => {
    const value = navCounts?.[id];
    return Number.isFinite(value) && value >= 0 ? String(value) : null;
  };

  const isActive = (id) => {
    if (id === 'home') return path === '/';
    if (id === 'chat') return path === '/chat' || path.startsWith('/chat/');
    return path === '/' + id;
  };

  const go = (id) => navigate(id === 'home' ? '/' : '/' + id);

  const groups = [
    {
      label: '问数中心',
      items: [
        { id: 'home',      label: '工作台',     icon: 'home' },
        { id: 'chat',      label: '对话问数',   icon: 'chat' },
        { id: 'dashboard', label: '监控大盘',   icon: 'layout', count: countFor('dashboard') },
        { id: 'history',   label: '查询历史',   icon: 'history', count: countFor('history') },
        { id: 'pinned',    label: '我的收藏',   icon: 'bookmark' },
        { id: 'apis',      label: 'API 接口',   icon: 'api', count: countFor('apis') },
      ],
    },
    {
      label: '语义治理',
      items: [
        { id: 'datasets',  label: '数据集 & 指标', icon: 'database', count: countFor('datasets') },
        { id: 'knowledge', label: '知识库',       icon: 'brain', count: countFor('knowledge') },
        { id: 'review',    label: '审核队列',     icon: 'check', count: countFor('review'), dot: Number(navCounts?.review || 0) > 0 },
      ],
    },
    {
      label: '数据连接',
      items: [
        { id: 'datasources', label: '数据源', icon: 'plug', count: countFor('datasources') },
      ],
    },
    {
      label: '系统管理',
      items: [
        { id: 'audit',       label: '查询审计', icon: 'log' },
        { id: 'models',      label: 'LLM 模型', icon: 'brain' },
        { id: 'settings',    label: '系统设置', icon: 'cog' },
      ],
    },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-logo" src="/datalogue-logo.png" alt="数语 Datalogue" />
      </div>

      <button className="new-thread" onClick={() => go('chat')}>
        <Icon name="plus" />
        <span>新的问数</span>
        <span className="kbd">⌘ K</span>
      </button>

      <nav className="sidebar-nav" aria-label="主导航">
        {groups.map((g, i) => (
          <div className="nav-group" key={i}>
            <div className="nav-section">{g.label}</div>
            {g.items.map(n => {
              const active = isActive(n.id);
              return (
                <button
                  key={n.id}
                  className={'nav-item ' + (active ? 'active' : '')}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => go(n.id)}
                >
                  <Icon name={n.icon} />
                  <span>{n.label}</span>
                  {n.dot && <span className="nav-dot" />}
                  {n.isNew && !n.count && <span className="nav-new">NEW</span>}
                  {n.count && <span className="count">{n.count}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="avatar">{avatarText}</div>
        <div className="who">
          <span className="name">{displayName}</span>
          <span className="role">{roleLabel}</span>
        </div>
        <Icon name="chev" />
      </div>
    </aside>
  );
}

export { Sidebar };

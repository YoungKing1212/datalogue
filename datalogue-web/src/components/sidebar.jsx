import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from './icons';
import { useAuth } from '../auth/auth-context';

// Sidebar — restructured to match design doc IA: 4 groups.
// "最近会话"区已迁出至 chat 页面的独立 ThreadList 左列。

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const path = location.pathname;
  const query = new URLSearchParams(location.search);
  const isTemplateMode = query.get('mode') === 'template';
  const displayName = user?.full_name || user?.username || '未登录用户';
  const roleLabel = user?.is_superuser ? '超级管理员' : user?.role === 'admin' ? '管理员' : '数据演示团队';
  const avatarText = displayName.trim().slice(0, 1).toUpperCase() || '?';

  const isUsersSection = location.state?.section === 'users';

  const isActive = (id) => {
    if (id === 'chat') return (path === '/chat' || path.startsWith('/chat/')) && !isTemplateMode;
    if (id === 'templates') return (path === '/chat' || path.startsWith('/chat/')) && isTemplateMode;
    if (id === 'datasets') return path === '/datasets';
    if (id === 'knowledge') return path === '/knowledge' || path === '/review';
    if (id === 'dashboard') return path === '/dashboard' || path === '/pinned';
    if (id === 'insights') return path === '/history' || path === '/apis';
    if (id === 'users') return path === '/settings' && isUsersSection;
    if (id === 'settings') return path === '/settings' && !isUsersSection;
    return false;
  };

  const go = (id) => {
    if (id === 'chat') {
      navigate('/chat');
      return;
    }
    if (id === 'templates') {
      navigate('/chat?mode=template');
      return;
    }
    if (id === 'datasets') {
      navigate('/datasets');
      return;
    }
    if (id === 'knowledge') {
      navigate('/knowledge');
      return;
    }
    if (id === 'dashboard') {
      navigate('/dashboard');
      return;
    }
    if (id === 'insights') {
      navigate('/history');
      return;
    }
    if (id === 'users') {
      // 团队管理落在系统设置内的用户管理分区，避免新增重复路由。
      navigate('/settings', { state: { section: 'users' } });
      return;
    }
    navigate('/settings');
  };

  const groups = [
    {
      label: '问数',
      items: [
        { id: 'chat', label: '对话问数', icon: 'chat' },
        { id: 'templates', label: '模板问数', icon: 'layout' },
      ],
    },
    {
      label: '数据资产',
      items: [
        { id: 'datasets', label: '数据集', icon: 'database' },
        { id: 'knowledge', label: '指标库', icon: 'sparkle' },
      ],
    },
    {
      label: '分析洞察',
      items: [
        { id: 'dashboard', label: '我的分析', icon: 'layout' },
        { id: 'insights', label: '洞察中心', icon: 'insight' },
      ],
    },
    {
      label: '系统管理',
      items: [
        { id: 'users', label: '团队管理', icon: 'user' },
        { id: 'settings', label: '系统设置', icon: 'cog' },
      ],
    },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-wordmark">数语</span>
      </div>

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
        <Icon name="chev_down" />
      </div>
    </aside>
  );
}

export { Sidebar };

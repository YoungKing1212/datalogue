import React, { useState, useEffect, Fragment } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigate, Link } from 'react-router-dom';
import { Icon } from './components/icons';
import { Sidebar } from './components/sidebar';
import { Workspace } from './components/workspace';
import { ChatScreen } from './components/chat';
import { DatasetsScreen } from './components/datasets';
import { DashboardScreen } from './components/dashboard';
import { ApisScreen } from './components/apis';
import { HistoryScreen } from './components/history';
import { PinnedScreen } from './components/pinned';
import { SettingsScreen } from './components/settings';
import { PublishDrawer } from './components/publish-drawer';
import { NotificationsPopover, bellCount } from './components/notifications';
import { useTweaks, TweaksPanel, TweakSection, TweakColor, TweakRadio, TweakToggle, TweakSelect, TweakButton } from './components/tweaks-panel';
import { DatasourcesScreen } from './components/datasources';
import { KnowledgeScreen } from './components/knowledge';
import { AuditQueryScreen } from './components/audit-query';
import { EditorModalHost } from './components/editor-modal';

// App — main router with URL-based routing.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#3b82f6",
  "density": "regular",
  "agentVerbosity": "expanded",
  "showFollowups": true,
  "showSql": true
}/*EDITMODE-END*/;

const ACCENT_OKLCH = {
  "#3b82f6": "oklch(0.58 0.15 240)",
  "#0ea5e9": "oklch(0.62 0.14 220)",
  "#6366f1": "oklch(0.55 0.17 270)",
  "#0d9488": "oklch(0.55 0.10 195)",
};
const ACCENT_LINE = {
  "#3b82f6": "oklch(0.58 0.15 240 / 0.30)",
  "#0ea5e9": "oklch(0.62 0.14 220 / 0.30)",
  "#6366f1": "oklch(0.55 0.17 270 / 0.30)",
  "#0d9488": "oklch(0.55 0.10 195 / 0.30)",
};
const ACCENT_SOFT = {
  "#3b82f6": "oklch(0.58 0.15 240 / 0.10)",
  "#0ea5e9": "oklch(0.62 0.14 220 / 0.10)",
  "#6366f1": "oklch(0.55 0.17 270 / 0.10)",
  "#0d9488": "oklch(0.55 0.10 195 / 0.10)",
};

// 路径到面包屑的映射
const CRUMBS_MAP = {
  '/':             { crumb: ['数语', '工作台'], title: '工作台' },
  '/chat':         { crumb: ['数语', '问数中心', '对话问数'], title: '问数对话' },
  '/chat/':        { crumb: ['数语', '问数中心', '对话问数'], title: '问数对话' },
  '/datasets':     { crumb: ['数语', '语义治理', '数据集 & 指标'], title: '数据集 & 指标' },
  '/dashboard':    { crumb: ['数语', '问数中心', '监控大盘'], title: '监控大盘' },
  '/apis':         { crumb: ['数语', '问数中心', 'API 接口'], title: 'API 接口' },
  '/history':      { crumb: ['数语', '问数中心', '查询历史'], title: '查询历史' },
  '/pinned':       { crumb: ['数语', '问数中心', '我的收藏'], title: '我的收藏' },
  '/knowledge':    { crumb: ['数语', '语义治理', '知识库'], title: '知识库' },
  '/review':       { crumb: ['数语', '语义治理', '审核队列'], title: '审核队列' },
  '/datasources':  { crumb: ['数语', '数据连接', '数据源管理'], title: '数据源' },
  '/audit-query':  { crumb: ['数语', '系统管理', '查询审计'], title: '查询审计' },
  '/settings':     { crumb: ['数语', '系统管理', '设置'], title: '系统设置' },
};

function TopBar({ traceOpen, setTraceOpen, onPublish }) {
  const [notifOpen, setNotifOpen] = useState(false);
  const location = useLocation();
  const count = bellCount();
  const path = location.pathname;

  // 优先精确匹配，其次前缀匹配
  const entry = Object.entries(CRUMBS_MAP).find(([k]) => k !== '/' && path.startsWith(k));
  const c = CRUMBS_MAP[path] || (entry ? entry[1] : null) || CRUMBS_MAP['/'];

  const showTrace = path === '/chat';

  return (
    <div className="topbar">
      <div className="crumb">
        {c.crumb.map((b, i) => (
          <Fragment key={i}>
            {i === c.crumb.length - 1 ? <span>{b}</span> : <>{b} <span style={{opacity: 0.4, margin: '0 8px'}}>/</span></>}
          </Fragment>
        ))}
      </div>
      <div className="topbar-actions">
        {showTrace && (
          <button className={'btn ghost ' + (traceOpen ? 'active' : '')}
                  style={traceOpen ? {color: 'var(--accent)', background: 'var(--accent-soft)'} : {}}
                  onClick={() => setTraceOpen(!traceOpen)}>
            <Icon name="trace" />
            推理过程
          </button>
        )}
        {showTrace && (
          <>
            <Link to="/dashboard" className="btn ghost">
              <Icon name="pin" />
              保存到看板
            </Link>
            <button className="btn primary" onClick={onPublish}>
              <Icon name="api" />
              发布为接口
            </button>
          </>
        )}
        <button className="icon-btn" title="搜索"><Icon name="search" /></button>
        <button
          className={'icon-btn notif-btn ' + (notifOpen ? 'on' : '')}
          title="消息"
          onClick={() => setNotifOpen(v => !v)}>
          <Icon name="bell" />
          {count > 0 && <span className="notif-badge">{count}</span>}
        </button>
        <NotificationsPopover open={notifOpen} onClose={() => setNotifOpen(false)} />
      </div>
    </div>
  );
}

function AppInner({ traceOpen, setTraceOpen, t, setTweak }) {
  const [publishOpen, setPublishOpen] = useState(false);
  const location = useLocation();
  const path = location.pathname;

  // Apply accent CSS variable
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--accent', ACCENT_OKLCH[t.accent] || t.accent);
    root.style.setProperty('--accent-line', ACCENT_LINE[t.accent] || 'rgba(255,255,255,0.3)');
    root.style.setProperty('--accent-soft', ACCENT_SOFT[t.accent] || 'rgba(15,23,42,0.1)');
  }, [t.accent]);

  // Density
  useEffect(() => {
    document.body.style.fontSize = t.density === 'compact' ? '13px' : t.density === 'comfy' ? '15px' : '14px';
  }, [t.density]);

  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <TopBar traceOpen={traceOpen} setTraceOpen={setTraceOpen} onPublish={() => setPublishOpen(true)} />
        <div className="content">
          <Routes>
            <Route path="/" element={<Workspace />} />
            <Route path="/chat" element={<ChatScreen traceOpen={traceOpen} setTraceOpen={setTraceOpen} density={t.density} />} />
            <Route path="/chat/:id" element={<ChatScreen traceOpen={traceOpen} setTraceOpen={setTraceOpen} density={t.density} />} />
            <Route path="/datasets" element={<DatasetsScreen />} />
            <Route path="/dashboard" element={<DashboardScreen />} />
            <Route path="/apis" element={<ApisScreen />} />
            <Route path="/history" element={<HistoryScreen />} />
            <Route path="/pinned" element={<PinnedScreen />} />
            <Route path="/knowledge" element={<KnowledgeScreen key="kb-sql" initialTab="sql" />} />
            <Route path="/review" element={<KnowledgeScreen key="kb-queue" initialTab="queue" />} />
            <Route path="/datasources" element={<DatasourcesScreen />} />
            <Route path="/audit-query" element={<AuditQueryScreen />} />
            <Route path="/settings" element={<SettingsScreen />} />
          </Routes>
        </div>
      </div>

      {publishOpen && <PublishDrawer onClose={() => setPublishOpen(false)} />}
      <EditorModalHost />

      <TweaksPanel title="Tweaks">
        <TweakSection label="主题色" />
        <TweakColor label="Accent" value={t.accent}
          options={['#3b82f6', '#0ea5e9', '#6366f1', '#0d9488']}
          onChange={(v) => setTweak('accent', v)} />

        <TweakSection label="布局" />
        <TweakRadio label="密度" value={t.density} options={['compact', 'regular', 'comfy']}
          onChange={(v) => setTweak('density', v)} />

        <TweakSection label="问数体验" />
        <TweakRadio label="Agent 推理" value={t.agentVerbosity}
          options={[{value:'minimal', label:'简洁'},{value:'expanded', label:'展开'},{value:'full', label:'完整'}]}
          onChange={(v) => setTweak('agentVerbosity', v)} />
        <TweakToggle label="显示追问 chips" value={t.showFollowups}
          onChange={(v) => setTweak('showFollowups', v)} />
        <TweakToggle label="显示生成的 SQL" value={t.showSql}
          onChange={(v) => setTweak('showSql', v)} />

        <TweakSection label="调试" />
        <TweakButton label="打开发布接口 Drawer" onClick={() => setPublishOpen(true)} />
      </TweaksPanel>
    </div>
  );
}

export default function App() {
  const [traceOpen, setTraceOpen] = useState(false);
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  return (
    <BrowserRouter>
      <AppInner traceOpen={traceOpen} setTraceOpen={setTraceOpen} t={t} setTweak={setTweak} />
    </BrowserRouter>
  );
}
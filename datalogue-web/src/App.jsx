import React, { useState, useEffect, Fragment } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigate, Link, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { Icon } from './shared/components/icons';
import { Sidebar } from './components/sidebar';
import { Workspace } from './components/workspace';
import { ChatPage } from './features/chat/chat-page';
import { DatasetsScreen } from './components/datasets';
import { DashboardScreen } from './components/dashboard';
import { ApisScreen } from './components/apis';
import { HistoryScreen } from './components/history';
import { PinnedScreen } from './components/pinned';
import { AuditScreen, LLMModelsScreen, SettingsScreen } from './components/settings';
import { PublishDrawer } from './components/publish-drawer';
import { NotificationsPopover, bellCount } from './components/notifications';
import { useTweaks } from './features/app-tweaks';
import { DatasourcesScreen } from './components/datasources';
import { KnowledgeScreen } from './components/knowledge';
import WorkbenchRoute from './components/workbench-route';
import { LoginPage } from './components/login-page';
import { AuthProvider, useAuth } from './auth/auth-context';

// App — main router with URL-based routing.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#1976c9",
  "density": "regular",
  "agentVerbosity": "expanded",
  "showFollowups": true
}/*EDITMODE-END*/;

// Vite 会在生产构建时把 DEV 分支裁掉，因此调试面板及其 postMessage 协议不会进入生产产物。
const DevTweaks = import.meta.env.DEV
  ? React.lazy(() => import('./components/dev-tweaks').then((module) => ({ default: module.DevTweaks })))
  : null;

// 把默认主色重映射为更饱和的亮蓝（贴近设计稿）；保留 #1976c9 作为键，
// 使已持久化到 localStorage 的旧值也一并应用新蓝，避免老用户仍是偏灰的蓝。
const ACCENT_OKLCH = {
  "#1976c9": "#2570e0",
};
const ACCENT_LINE = {
  "#1976c9": "#bcd6f8",
};
const ACCENT_SOFT = {
  "#1976c9": "#e9f2ff",
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
  '/audit':        { crumb: ['数语', '系统管理', '查询审计'], title: '查询审计' },
  '/models':       { crumb: ['数语', '系统管理', 'LLM 模型'], title: 'LLM 模型' },
  '/settings':     { crumb: ['数语', '系统管理', '设置'], title: '系统设置' },
  '/users':        { crumb: ['数语', '系统管理', '用户管理'], title: '用户管理' },
};

const SEARCH_ROUTES = Object.entries(CRUMBS_MAP)
  .filter(([path]) => path !== '/chat/' && path !== '/users')
  .map(([path, item]) => ({ path, title: item.title, keywords: item.crumb.join(' ') }));

function GlobalSearch({ open, onClose }) {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const normalized = query.trim().toLowerCase();
  const matches = SEARCH_ROUTES.filter((item) => (
    !normalized || `${item.title} ${item.keywords}`.toLowerCase().includes(normalized)
  ));

  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  if (!open) return null;
  const selectRoute = (path) => {
    navigate(path);
    onClose();
  };

  return (
    <div className="global-search-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="global-search-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="全局搜索"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === 'Escape') onClose();
        }}
      >
        <div className="global-search-input-wrap">
          <Icon name="search" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索页面或功能"
            aria-label="搜索页面或功能"
          />
          <span className="kbd">Esc</span>
        </div>
        <div className="global-search-results">
          {matches.length ? matches.map((item) => (
            <button key={item.path} type="button" onClick={() => selectRoute(item.path)}>
              <span>{item.title}</span>
              <small>{item.keywords}</small>
            </button>
          )) : (
            <div className="global-search-empty">没有匹配的页面</div>
          )}
        </div>
      </section>
    </div>
  );
}

function NotFoundPage() {
  return (
    <div className="not-found-page">
      <span>404</span>
      <h1>页面不存在</h1>
      <p>地址可能已失效，您可以返回工作台继续使用。</p>
      <Link className="btn primary" to="/">返回工作台</Link>
    </div>
  );
}

function TopBar({ onPublish, onSearch, onMenu, currentUser, onLogout }) {
  const [notifOpen, setNotifOpen] = useState(false);
  const location = useLocation();
  const count = bellCount();
  const path = location.pathname;

  // 优先精确匹配，其次前缀匹配
  const entry = Object.entries(CRUMBS_MAP).find(([k]) => k !== '/' && path.startsWith(k));
  const c = CRUMBS_MAP[path] || (entry ? entry[1] : null) || CRUMBS_MAP['/'];

  const showTrace = path === '/chat' || path.startsWith('/chat/');

  return (
    <div className="topbar">
      <button
        type="button"
        className="icon-btn mobile-menu-btn"
        title="打开导航"
        aria-label="打开导航"
        onClick={onMenu}
      >
        <Icon name="menu" />
      </button>
      <div className="crumb">
        {c.crumb.map((b, i) => (
          <Fragment key={i}>
            {i === c.crumb.length - 1 ? <span>{b}</span> : <>{b} <span style={{opacity: 0.4, margin: '0 8px'}}>/</span></>}
          </Fragment>
        ))}
      </div>
      <div className="topbar-actions">
        {showTrace && (
          <>
            <button
              className="icon-btn"
              title="刷新"
              aria-label="刷新"
              onClick={() => window.location.reload()}
            >
              <Icon name="refresh" />
            </button>
            <button
              className="icon-btn"
              title="分享（复制会话链接）"
              aria-label="分享会话链接"
              onClick={() => {
                // 复制当前会话链接到剪贴板，贴近设计稿的“分享”入口。
                navigator.clipboard?.writeText(window.location.href).catch(console.error);
              }}
            >
              <Icon name="share" />
            </button>
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
        <button className="icon-btn" title="搜索" aria-label="全局搜索" onClick={onSearch}>
          <Icon name="search" />
        </button>
        {currentUser && (
          <>
            <span className="topbar-user">{currentUser.username}</span>
            <button className="btn ghost topbar-logout" onClick={onLogout}>退出登录</button>
          </>
        )}
        <button
          className={'icon-btn notif-btn ' + (notifOpen ? 'on' : '')}
          title="消息"
          aria-label="消息通知"
          onClick={() => setNotifOpen(v => !v)}>
          <Icon name="bell" />
          {count > 0 && <span className="notif-badge">{count}</span>}
        </button>
        <NotificationsPopover open={notifOpen} onClose={() => setNotifOpen(false)} />
      </div>
    </div>
  );
}

function AppInner({ t, setTweak }) {
  const [publishOpen, setPublishOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const { user, logout } = useAuth();
  const location = useLocation();

  // 路由切换后收起移动抽屉，避免内容页被残留遮罩覆盖。
  useEffect(() => {
    setMobileNavOpen(false);
    setSearchOpen(false);
    if (!location.pathname.startsWith('/chat')) setTraceOpen(false);
  }, [location.pathname]);

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
      <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      <button
        type="button"
        className={`sidebar-backdrop${mobileNavOpen ? ' open' : ''}`}
        aria-label="关闭导航"
        onClick={() => setMobileNavOpen(false)}
      />
      <div className="main">
        <TopBar
          onPublish={() => setPublishOpen(true)}
          onSearch={() => setSearchOpen(true)}
          onMenu={() => setMobileNavOpen(true)}
          currentUser={user}
          onLogout={logout}
        />
        <div className="content">
          <Routes>
            <Route path="/" element={<Workspace />} />
            <Route path="/chat" element={<ChatPage traceOpen={traceOpen} setTraceOpen={setTraceOpen} showFollowups={t.showFollowups} agentVerbosity={t.agentVerbosity} />} />
            <Route path="/chat/:id" element={<ChatPage traceOpen={traceOpen} setTraceOpen={setTraceOpen} showFollowups={t.showFollowups} agentVerbosity={t.agentVerbosity} />} />
            <Route path="/workbench/:threadId" element={<WorkbenchRoute />} />
            <Route path="/workbench/:threadId/:artifactRef" element={<WorkbenchRoute />} />
            <Route path="/datasets" element={<DatasetsScreen />} />
            <Route path="/dashboard" element={<DashboardScreen />} />
            <Route path="/apis" element={<ApisScreen />} />
            <Route path="/history" element={<HistoryScreen />} />
            <Route path="/pinned" element={<PinnedScreen />} />
            <Route path="/knowledge" element={<KnowledgeScreen key="kb-sql" initialTab="sql" />} />
            <Route path="/review" element={<KnowledgeScreen key="kb-queue" initialTab="queue" />} />
            <Route path="/datasources" element={<DatasourcesScreen />} />
            <Route path="/audit" element={<AuditScreen />} />
            <Route
              path="/models"
              element={(
                <RequireSuperuser>
                  <LLMModelsScreen />
                </RequireSuperuser>
              )}
            />
            <Route path="/settings" element={<SettingsScreen />} />
            <Route
              path="/users"
              element={(
                <RequireSuperuser>
                  <Navigate to="/settings" replace state={{ section: 'users' }} />
                </RequireSuperuser>
              )}
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </div>

      {publishOpen && <PublishDrawer onClose={() => setPublishOpen(false)} />}
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
      {DevTweaks && (
        <React.Suspense fallback={null}>
          <DevTweaks t={t} setTweak={setTweak} onOpenPublish={() => setPublishOpen(true)} />
        </React.Suspense>
      )}
    </div>
  );
}

function RequireAuth({ children }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="auth-loading">
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (user.must_change_password) {
    // 临时密码登录态只能停留在改密页，防止业务页面先发出必然失败的数据请求。
    return <Navigate to="/login" replace state={{ from: location, passwordChangeRequired: true }} />;
  }

  return children;
}

function RequireSuperuser({ children }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!user.is_superuser && user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return children;
}

// Error Boundary — 捕获子组件错误，防止整页白屏
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <h2>页面出现错误</h2>
          <p style={{ color: 'var(--text-3)' }}>请刷新页面重试</p>
          <button
            className="btn primary"
            onClick={() => window.location.reload()}
            style={{ marginTop: 16 }}
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  return (
    <AuthProvider>
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/*"
              element={(
                <RequireAuth>
                  <AppInner t={t} setTweak={setTweak} />
                </RequireAuth>
              )}
            />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </AuthProvider>
  );
}

import React, { useState, useEffect, Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from './icons';
import { listConversations, deleteConversation } from '../api/client';

// History — 历史会话列表，对接后端真实 API

function HistoryScreen() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  // 页面加载时拉取真实对话列表
  useEffect(() => {
    setLoading(true);
    setLoadError('');
    listConversations()
      .then((data) => {
        // 后端返回的 conversation 数据结构转换为前端需要的格式
        const mapped = data.map((c) => ({
          id: c.id,
          title: c.title,
          preview: '', // 后端暂无 preview，用第一条消息替代
          when: formatWhen(c.updated_at),
          date: formatDate(c.created_at),
          tag: '问数',
          kind: 'chat',
          msgs: 0,
          charts: 0,
          status: 'published',
          api: null,
          author: 'YL',
          fav: false,
          raw: c,
        }));
        setSessions(mapped);
      })
      .catch((err) => {
        console.error('加载历史会话失败:', err);
        setLoadError('历史会话加载失败，请检查网络后重试。');
      })
      .finally(() => setLoading(false));
  }, [reloadKey]);

  const filters = [
    { id: 'all',       label: '全部',       count: sessions.length },
    { id: 'published', label: '已发布接口',  count: sessions.filter(s=>s.status==='published').length },
    { id: 'pinned',    label: '已收藏',     count: sessions.filter(s=>s.fav).length },
    { id: 'draft',     label: '草稿',       count: sessions.filter(s=>s.status==='draft').length },
    { id: 'archived',  label: '已归档',     count: sessions.filter(s=>s.status==='archived').length },
    { id: 'mine',      label: '我创建的',   count: sessions.filter(s=>s.author==='YL').length },
    { id: 'team',      label: '团队共享',   count: 28 },
  ];

  const tagIcons = { '归因':'thunder', '对比':'chart_bar', '洞察':'insight', '漏斗':'filter', '预测':'sparkle', '排行':'chart_bar', '运营':'preset', '问数':'chat' };

  const visible = sessions.filter(s => {
    if (filter !== 'all') {
      if (filter === 'pinned' && !s.fav) return false;
      if (filter === 'mine' && s.author !== 'YL') return false;
      if (['published','draft','archived'].includes(filter) && s.status !== filter) return false;
    }
    if (query && !s.title.includes(query) && !s.preview.includes(query)) return false;
    return true;
  });

  // bucket by date
  const buckets = {};
  visible.forEach(s => { (buckets[s.date] = buckets[s.date] || []).push(s); });

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!confirm('确定删除这个会话吗？')) return;
    try {
      await deleteConversation(id);
      setSessions(prev => prev.filter(s => s.id !== id));
    } catch (err) {
      alert('删除失败: ' + err.message);
    }
  };

  return (
    <div className="hp-wrap">
      <div className="hp-head">
        <div>
          <h1>历史会话</h1>
          <p className="desc">共 {sessions.length} 个会话 · 后端实时拉取</p>
        </div>
        <div className="hp-head-actions">
          <button className="btn ghost"><Icon name="download" />导出</button>
          <button className="btn ghost"><Icon name="folder" />新建文件夹</button>
        </div>
      </div>

      <div className="hp-toolbar">
        <div className="search-bar" style={{flex: 1, marginBottom: 0}}>
          <Icon name="search" />
          <input placeholder="搜索问题、答案或SQL…" value={query} onChange={e => setQuery(e.target.value)} />
          <span className="kbd-inline">⌘ F</span>
        </div>
        <button className="btn ghost"><Icon name="calendar" />近30天</button>
        <button className="btn ghost"><Icon name="filter_alt" />标签</button>
      </div>

      <div className="hp-tabs">
        {filters.map(f => (
          <button key={f.id} className={'hp-tab ' + (filter === f.id ? 'active' : '')} onClick={() => setFilter(f.id)}>
            {f.label}
            <span className="count">{f.count}</span>
          </button>
        ))}
      </div>

      {loading && <div style={{padding: 40, textAlign: 'center', color: 'var(--text-3)'}}>加载中…</div>}
      {!loading && loadError && (
        <div role="alert" style={{padding: 40, textAlign: 'center', color: 'var(--text-2)'}}>
          <p>{loadError}</p>
          <button className="btn ghost" onClick={() => setReloadKey((value) => value + 1)}>重新加载</button>
        </div>
      )}

      <div className="hp-list">
        {Object.entries(buckets).map(([date, items]) => (
          <Fragment key={date}>
            <div className="hp-date-label">{date}</div>
            {items.map(s => (
              <div key={s.id} className="hp-row" role="button" tabIndex={0}
                onClick={() => navigate(`/chat/${s.id}`)}
                onKeyDown={e => e.key === 'Enter' && navigate(`/chat/${s.id}`)}>
                <div className="hp-row-icon">
                  <Icon name={tagIcons[s.tag] || 'chat'} />
                </div>
                <div className="hp-row-body">
                  <div className="hp-row-top">
                    <span className="hp-row-title">{s.title}</span>
                    {s.fav && <Icon name="bookmark" className="hp-fav" />}
                    {s.status === 'published' && (
                      <span className="hp-pill api"><Icon name="api" />已发布</span>
                    )}
                    {s.status === 'draft' && <span className="hp-pill draft">草稿</span>}
                    {s.status === 'archived' && <span className="hp-pill archived">归档</span>}
                  </div>
                  <div className="hp-row-preview">{s.preview || '暂无摘要'}</div>
                  <div className="hp-row-meta">
                    <span><Icon name="chat" />{s.msgs} 条消息</span>
                    <span><Icon name="chart_line" />{s.charts} 个图表</span>
                    <span><Icon name="user" />{s.author}</span>
                    {s.api && <span className="mono api-path">{s.api}</span>}
                  </div>
                </div>
                <div className="hp-row-when">{s.when}</div>
                <div className="hp-row-actions">
                  <button className="icon-btn" title="收藏" onClick={e=>e.stopPropagation()}><Icon name="bookmark" /></button>
                  <button className="icon-btn" title="发布为接口" onClick={e=>{e.stopPropagation(); navigate('/apis');}}><Icon name="api" /></button>
                  <button className="icon-btn" title="删除" onClick={e => handleDelete(s.id, e)}><Icon name="trash" /></button>
                </div>
              </div>
            ))}
          </Fragment>
        ))}
        {!loading && !loadError && visible.length === 0 && (
          <div style={{padding: 60, textAlign: 'center', color: 'var(--text-3)'}}>
            暂无会话，去 <button className="btn ghost" onClick={() => navigate('/chat')}>问数</button> 开始第一个对话吧
          </div>
        )}
      </div>
    </div>
  );
}

// 时间格式化辅助函数
function formatWhen(iso) {
  if (!iso) return '未知';
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

function formatDate(iso) {
  if (!iso) return '未知';
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) return '今天';
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

export { HistoryScreen };

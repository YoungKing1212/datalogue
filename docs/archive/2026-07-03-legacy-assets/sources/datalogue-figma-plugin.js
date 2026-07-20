/**
 * 数语 Datalogue · Figma 自动建帧插件
 *
 * 使用方法：
 * 1. 在 Figma 中打开任意文件（或新建文件）
 * 2. 菜单 → Plugins → Development → Open Console
 * 3. 将本文件全部内容粘贴进控制台，按 Enter 运行
 * 4. 片刻后自动生成"数语 Datalogue"页面，包含 S01-S06 共 6 个 1440×900 Frame
 */

(async function datalogueFigma() {

  // ─────────────────────────────────────────
  //  1. Design Tokens（与 styles.css 对齐）
  // ─────────────────────────────────────────
  const T = {
    bg:        { r: 1,     g: 1,     b: 1     },
    bg2:       { r: 0.957, g: 0.973, b: 0.988 },
    surf2:     { r: 0.953, g: 0.965, b: 0.984 },
    surf3:     { r: 0.906, g: 0.929, b: 0.961 },
    sidebar:   { r: 0.965, g: 0.976, b: 0.992 },
    accent:    { r: 0.149, g: 0.392, b: 0.831 },
    accentLt:  { r: 0.906, g: 0.929, b: 0.988 },
    pos:       { r: 0.090, g: 0.639, b: 0.416 },
    posLt:     { r: 0.882, g: 0.973, b: 0.937 },
    neg:       { r: 0.851, g: 0.267, b: 0.141 },
    negLt:     { r: 0.988, g: 0.906, b: 0.882 },
    warn:      { r: 0.761, g: 0.541, b: 0.039 },
    warnLt:    { r: 0.988, g: 0.941, b: 0.851 },
    t1:        { r: 0.059, g: 0.090, b: 0.165 },
    t2:        { r: 0.278, g: 0.337, b: 0.412 },
    t3:        { r: 0.522, g: 0.576, b: 0.659 },
    t4:        { r: 0.753, g: 0.792, b: 0.851 },
    bdr:       { r: 0.878, g: 0.906, b: 0.941 },
    white:     { r: 1,     g: 1,     b: 1     },
    metric:    { r: 0.490, g: 0.329, b: 0.831 },
    metricLt:  { r: 0.933, g: 0.918, b: 0.988 },
    dim2:      { r: 0.102, g: 0.608, b: 0.627 },
    dim2Lt:    { r: 0.882, g: 0.961, b: 0.965 },
    timeTag:   { r: 0.773, g: 0.541, b: 0.125 },
    timeLt:    { r: 0.988, g: 0.941, b: 0.851 },
  };

  function fill(c, a = 1) {
    return [{ type: 'SOLID', color: c, opacity: a }];
  }
  function noFill() { return []; }

  // ─────────────────────────────────────────
  //  2. 字体预加载
  // ─────────────────────────────────────────
  const fontStyles = ['Regular', 'Medium', 'SemiBold', 'Bold'];
  await Promise.all(fontStyles.map(s => figma.loadFontAsync({ family: 'Inter', style: s })));

  // ─────────────────────────────────────────
  //  3. 页面初始化
  // ─────────────────────────────────────────
  let pg = figma.root.children.find(p => p.name === '数语 Datalogue');
  if (pg) {
    // 清空旧内容
    for (const child of [...pg.children]) child.remove();
  } else {
    pg = figma.createPage();
    pg.name = '数语 Datalogue';
  }
  figma.currentPage = pg;

  const SW = 1440, SH = 900;
  const HGAP = 100, VGAP = 120;

  // ─────────────────────────────────────────
  //  4. 工具函数
  // ─────────────────────────────────────────
  function mkFrame(name, col, row) {
    const f = figma.createFrame();
    f.name = name;
    f.resize(SW, SH);
    f.x = col * (SW + HGAP);
    f.y = row * (SH + VGAP);
    f.fills = fill(T.bg);
    f.clipsContent = true;
    pg.appendChild(f);
    return f;
  }

  function addRect(parent, name, x, y, w, h, color, opts = {}) {
    const r = figma.createRectangle();
    r.name = name;
    r.x = x; r.y = y;
    r.resize(Math.max(w, 1), Math.max(h, 1));
    r.fills = color ? fill(color, opts.opacity || 1) : noFill();
    if (opts.radius != null) r.cornerRadius = opts.radius;
    if (opts.stroke) {
      r.strokes = fill(opts.stroke);
      r.strokeWeight = opts.strokeWeight || 1;
      r.strokeAlign = 'INSIDE';
    }
    parent.appendChild(r);
    return r;
  }

  function addText(parent, str, x, y, opts = {}) {
    const t = figma.createText();
    t.fontName = { family: 'Inter', style: opts.weight || 'Regular' };
    t.fontSize = opts.size || 13;
    t.fills = fill(opts.color || T.t1);
    t.characters = String(str);
    t.x = x; t.y = y;
    if (opts.w) {
      t.textAutoResize = 'HEIGHT';
      t.resize(opts.w, 40);
    } else {
      t.textAutoResize = 'WIDTH_AND_HEIGHT';
    }
    if (opts.align) t.textAlignHorizontal = opts.align;
    parent.appendChild(t);
    return t;
  }

  function addTag(parent, label, x, y, bg, color) {
    const r = addRect(parent, `tag-${label}`, x, y, 10, 20, bg, { radius: 4 });
    const t = addText(parent, label, x + 6, y + 4, { size: 11, weight: 'Medium', color });
    const tw = t.width + 12;
    r.resize(tw, 20);
    return x + tw + 6;
  }

  // ─────────────────────────────────────────
  //  5. 公共组件：侧边栏
  // ─────────────────────────────────────────
  const NAV_ITEMS = [
    { label: '对话问数',   idx: 0 },
    { label: '语义层管理', idx: 1 },
    { label: '知识库',     idx: 2 },
    { label: '监控大盘',   idx: 3 },
    { label: '查询审计',   idx: 4 },
    { label: '数据源',     idx: 5 },
  ];

  function buildSidebar(parent, activeIdx) {
    addRect(parent, 'sidebar-bg', 0, 0, 220, SH, T.sidebar);
    addRect(parent, 'sidebar-border', 219, 0, 1, SH, T.bdr);

    // Logo
    addRect(parent, 'logo-mark', 20, 22, 28, 28, T.accent, { radius: 8 });
    addText(parent, '数语', 58, 24, { size: 15, weight: 'SemiBold', color: T.t1 });
    addText(parent, 'Datalogue', 58, 39, { size: 10, color: T.t3 });

    // Nav items
    NAV_ITEMS.forEach((item, i) => {
      const ny = 84 + i * 48;
      const isActive = item.idx === activeIdx;
      if (isActive) {
        addRect(parent, `nav-active-bg-${i}`, 8, ny - 6, 204, 36, T.accentLt, { radius: 6 });
      }
      addRect(parent, `nav-icon-${i}`, 18, ny + 2, 20, 20,
        isActive ? T.accent : T.surf3, { radius: 4 });
      addText(parent, item.label, 46, ny + 4,
        { size: 13, weight: isActive ? 'Medium' : 'Regular', color: isActive ? T.accent : T.t2 });
    });

    // User
    addRect(parent, 'user-avatar', 18, SH - 52, 32, 32, T.accent, { radius: 16 });
    addText(parent, 'Ken Yang', 58, SH - 48, { size: 13, weight: 'Medium', color: T.t1 });
    addText(parent, 'Admin', 58, SH - 31, { size: 11, color: T.t3 });
  }

  // ─────────────────────────────────────────
  //  6. S01 · 对话问数
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S01 · 对话问数', 0, 0);
    buildSidebar(f, 0);

    const CX = 220;           // content start x
    const CW = SW - CX;      // 1220
    const RP = 380;           // right panel width
    const CP = CW - RP;      // chat panel width = 840

    // ── Top bar ──
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '新建对话', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });
    // New btn
    addRect(f, 'new-chat-btn', SW - 144, 14, 112, 28, T.accentLt, { radius: 6 });
    addText(f, '+ 新建对话', SW - 132, 20, { size: 12, weight: 'Medium', color: T.accent });

    // ── Divider ──
    addRect(f, 'panel-divider', CX + CP, 56, 1, SH - 56, T.bdr);

    // ── Chat area ──
    // User bubble
    const UBW = 340;
    addRect(f, 'user-bubble', CX + CP - UBW - 24, 76, UBW, 44, T.accentLt, { radius: 12 });
    addText(f, '各大区上个月的销售额和同比增长？',
      CX + CP - UBW - 12, 89, { size: 13, color: T.t1, w: UBW - 24 });

    // DSL Intent Card
    const ICX = CX + 24, ICW = CP - 48;
    addRect(f, 'dsl-card', ICX, 136, ICW, 88, T.surf2, { radius: 10, stroke: T.bdr });
    addText(f, '意图解析', ICX + 16, 148, { size: 11, weight: 'Medium', color: T.t3 });

    // DSL token tags
    let tagX = ICX + 16;
    const tags = [
      { label: '销售额',   bg: T.metricLt, color: T.metric  },
      { label: '大区',     bg: T.dim2Lt,   color: T.dim2    },
      { label: '上个月',   bg: T.timeLt,   color: T.timeTag },
      { label: '同比增长', bg: T.metricLt, color: T.metric  },
    ];
    tags.forEach(tag => { tagX = addTag(f, tag.label, tagX, 172, tag.bg, tag.color); });

    // Trace strip
    addText(f, '执行链路', ICX + 16, 234, { size: 11, weight: 'Medium', color: T.t3 });
    const traceSteps = [
      { label: 'LeadAgent', done: true  },
      { label: 'NL→DSL',   done: true  },
      { label: 'DSL→SQL',  done: true  },
      { label: '执行',      done: false },
      { label: '渲染',      done: false },
    ];
    traceSteps.forEach((step, i) => {
      const tx = ICX + 16 + i * 110;
      addRect(f, `trace-${step.label}`, tx, 252, 102, 22,
        step.done ? T.accent : T.surf3, { radius: 4 });
      addText(f, step.label, tx + 8, 257,
        { size: 11, weight: 'Medium', color: step.done ? T.white : T.t3 });
      if (i < traceSteps.length - 1) {
        addRect(f, `trace-arrow-${i}`, tx + 104, 260, 4, 4, step.done ? T.accent : T.t4, { radius: 2 });
      }
    });

    // Answer
    addText(f, '根据销售数据分析，上月各大区销售情况如下：',
      ICX + 16, 292, { size: 13, color: T.t1, w: ICW - 32 });

    // KPI cards
    const kpis = [
      { region: '华东', val: '¥2,840万', growth: '+12.3%', pos: true  },
      { region: '华北', val: '¥1,960万', growth: '+8.7%',  pos: true  },
      { region: '华南', val: '¥2,210万', growth: '+15.1%', pos: true  },
      { region: '西部', val: '¥980万',   growth: '-3.2%',  pos: false },
    ];
    const KW = Math.floor((ICW - 32 - 36) / 4);
    kpis.forEach((k, i) => {
      const kx = ICX + 16 + i * (KW + 12);
      addRect(f, `kpi-${k.region}`, kx, 318, KW, 76, T.surf2, { radius: 8 });
      addText(f, k.region, kx + 12, 330, { size: 11, color: T.t3 });
      addText(f, k.val, kx + 12, 346, { size: 15, weight: 'SemiBold', color: T.t1 });
      addText(f, k.growth, kx + 12, 374, { size: 12, weight: 'Medium', color: k.pos ? T.pos : T.neg });
    });

    // Bar chart placeholder
    const CHX = ICX + 16, CHY = 410, CHW = ICW - 32, CHH = 160;
    addRect(f, 'chart-bg', CHX, CHY, CHW, CHH, T.surf2, { radius: 8 });
    addText(f, '各大区销售额对比（ECharts Bar）', CHX + 16, CHY + 12,
      { size: 12, weight: 'Medium', color: T.t2 });
    // Bars
    const barH = [0.8, 0.55, 0.62, 0.28];
    const BW = 48, BY = CHY + CHH - 16;
    barH.forEach((h, i) => {
      const bx = CHX + 48 + i * 120;
      const bh = Math.floor(h * (CHH - 60));
      addRect(f, `bar-${i}`, bx, BY - bh, BW, bh, T.accent, { radius: 3 });
    });
    const regions = ['华东', '华北', '华南', '西部'];
    regions.forEach((r, i) => {
      addText(f, r, CHX + 52 + i * 120, BY + 4, { size: 11, color: T.t3 });
    });

    // Follow-up chips
    const chips = ['按月拆解趋势', '对比华东华南', '导出报告'];
    let chipX = ICX + 16;
    chips.forEach(chip => {
      const cw = chip.length * 13 + 24;
      addRect(f, `chip-${chip}`, chipX, 588, cw, 28, T.accentLt, { radius: 14 });
      addText(f, chip, chipX + 12, 595, { size: 12, weight: 'Medium', color: T.accent });
      chipX += cw + 10;
    });

    // Input bar
    addRect(f, 'input-bg', CX + 24, SH - 68, CP - 48, 48, T.surf2, { radius: 24, stroke: T.bdr });
    addText(f, '向数语提问…', CX + 48, SH - 48, { size: 14, color: T.t4 });
    addRect(f, 'send-btn', CX + CP - 68, SH - 68, 48, 48, T.accent, { radius: 24 });
    addRect(f, 'send-icon', CX + CP - 52, SH - 54, 16, 16, T.white, { radius: 2 });

    // ── Right panel ──
    const RPX = CX + CP + 16;
    addText(f, 'SQL 溯源', RPX, 68, { size: 13, weight: 'SemiBold', color: T.t1 });
    addRect(f, 'sql-bg', CX + CP + 1, 88, RP - 1, 248, T.surf2);
    addText(f,
      'SELECT\n  region,\n  SUM(sales_amount)        AS sales,\n  ROUND(\n    (SUM(sales_amount)\n      - LAG(SUM(sales_amount))\n        OVER (PARTITION BY region\n              ORDER BY month)\n    ) / LAG(SUM(sales_amount))\n      OVER (PARTITION BY region\n            ORDER BY month) * 100\n  , 2)                    AS growth_pct\nFROM dw.fact_sales\nWHERE month = DATE_TRUNC(\'month\',\n  CURRENT_DATE - INTERVAL \'1 month\')\nGROUP BY region\nORDER BY sales DESC',
      RPX, 96, { size: 11, color: T.t2, w: RP - 32 });

    addRect(f, 'sql-run-btn', RPX, 344, 72, 28, T.accent, { radius: 6 });
    addText(f, '▶ 运行', RPX + 12, 350, { size: 12, weight: 'Medium', color: T.white });
    addRect(f, 'sql-copy-btn', RPX + 84, 344, 56, 28, T.surf3, { radius: 6 });
    addText(f, '复制', RPX + 100, 350, { size: 12, color: T.t2 });

    // Result table
    addText(f, '查询结果', RPX, 388, { size: 13, weight: 'SemiBold', color: T.t1 });
    addRect(f, 'tbl-header', CX + CP + 1, 408, RP - 1, 28, T.surf3);
    const cols = ['大区', '销售额', '同比'];
    const colX = [RPX, RPX + 100, RPX + 220];
    cols.forEach((c, i) => addText(f, c, colX[i], 414, { size: 12, weight: 'Medium', color: T.t2 }));
    const rows = [
      ['华东', '2,840万', '+12.3%', true],
      ['华北', '1,960万', '+8.7%',  true],
      ['华南', '2,210万', '+15.1%', true],
      ['西部', '980万',   '-3.2%',  false],
    ];
    rows.forEach(([region, val, growth, pos], ri) => {
      addRect(f, `tbl-row-${ri}`, CX + CP + 1, 436 + ri * 28, RP - 1, 26,
        ri % 2 === 0 ? T.bg : T.surf2);
      addText(f, region, colX[0], 440 + ri * 28, { size: 12, color: T.t1 });
      addText(f, val,    colX[1], 440 + ri * 28, { size: 12, color: T.t1 });
      addText(f, growth, colX[2], 440 + ri * 28, { size: 12, color: pos ? T.pos : T.neg });
    });

    // Insight
    addRect(f, 'insight-bg', RPX, SH - 96, RP - 32, 60, T.posLt, { radius: 8 });
    addText(f,
      '💡 华南增速最快（+15.1%），建议重点关注华南区季度目标进展。',
      RPX + 12, SH - 84, { size: 12, color: T.t1, w: RP - 56 });
  }

  // ─────────────────────────────────────────
  //  7. S02 · 语义层管理
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S02 · 语义层管理', 1, 0);
    buildSidebar(f, 1);

    const CX = 220, CW = SW - CX;
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '语义层管理', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });

    // Tabs
    const tabs = ['数据集', '指标库', '维度库'];
    tabs.forEach((tab, i) => {
      const isActive = i === 1;
      const tx = CX + 16 + i * 104;
      addRect(f, `tab-${tab}`, tx, 66, 96, 30, isActive ? T.accentLt : T.bg, { radius: 6 });
      addText(f, tab, tx + 16, 73, { size: 13, weight: isActive ? 'Medium' : 'Regular',
        color: isActive ? T.accent : T.t2 });
      if (isActive) addRect(f, 'tab-underline', tx, 96, 96, 2, T.accent, { radius: 1 });
    });

    // Left list panel
    const LP = 280;
    addRect(f, 'list-bg', CX, 100, LP, SH - 100, T.surf2);
    addRect(f, 'list-border', CX + LP, 100, 1, SH - 100, T.bdr);

    addRect(f, 'search-box', CX + 12, 112, LP - 24, 34, T.bg, { radius: 6, stroke: T.bdr });
    addText(f, '搜索指标…', CX + 28, 121, { size: 13, color: T.t4 });

    const metrics = ['总销售额', '毛利率', '客单价', '同比增长率', '环比增长率', '订单量', '退款率', 'GMV'];
    metrics.forEach((m, i) => {
      const my = 158 + i * 44;
      const isActive = i === 0;
      addRect(f, `metric-row-${i}`, CX, my, LP, 40, isActive ? T.accentLt : T.bg);
      if (isActive) addRect(f, `metric-bar-${i}`, CX, my, 3, 40, T.accent);
      addText(f, m, CX + 20, my + 12,
        { size: 13, weight: isActive ? 'Medium' : 'Regular', color: isActive ? T.accent : T.t1 });
      addRect(f, `metric-badge-${i}`, CX + LP - 52, my + 12, 36, 16, T.metricLt, { radius: 3 });
      addText(f, '指标', CX + LP - 46, my + 14, { size: 10, color: T.metric });
    });

    // Detail panel
    const DX = CX + LP + 24, DW = CW - LP - 48;
    addText(f, '总销售额', DX, 72, { size: 18, weight: 'SemiBold', color: T.t1 });
    addRect(f, 'metric-type-tag', DX + 108, 76, 42, 20, T.metricLt, { radius: 4 });
    addText(f, '指标', DX + 116, 78, { size: 11, weight: 'Medium', color: T.metric });

    const fields = [
      { label: '英文名',   val: 'total_sales_amount' },
      { label: '计算公式', val: "SUM(order_amount) WHERE status = 'completed'" },
      { label: '数据类型', val: 'Decimal(18,2)' },
      { label: '业务口径', val: '已完成订单的实际到手金额，不含退款及优惠' },
      { label: '同义词',   val: '销售额 / 营收 / 收入' },
      { label: '数据负责人', val: '数据中台组 · 李明' },
    ];
    fields.forEach((field, i) => {
      const fy = 116 + i * 58;
      addText(f, field.label, DX, fy, { size: 11, weight: 'Medium', color: T.t3 });
      addRect(f, `field-box-${i}`, DX, fy + 18, DW, 30, T.surf2, { radius: 4, stroke: T.bdr });
      addText(f, field.val, DX + 12, fy + 22, { size: 12, color: T.t1, w: DW - 24 });
    });

    addRect(f, 'save-btn', DX + DW - 108, SH - 56, 96, 34, T.accent, { radius: 8 });
    addText(f, '保存指标', DX + DW - 88, SH - 46, { size: 13, weight: 'Medium', color: T.white });
    addRect(f, 'cancel-btn', DX + DW - 224, SH - 56, 104, 34, T.surf3, { radius: 8 });
    addText(f, '取消', DX + DW - 196, SH - 46, { size: 13, color: T.t2 });
  }

  // ─────────────────────────────────────────
  //  8. S03 · 知识库管理
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S03 · 知识库管理', 2, 0);
    buildSidebar(f, 2);

    const CX = 220, CW = SW - CX;
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '知识库管理', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });

    // Category tabs
    const cats = ['DDL 结构', '字段注释', 'SQL 示例', '业务规则'];
    cats.forEach((cat, i) => {
      const isActive = i === 2;
      const tx = CX + 16 + i * 128;
      addRect(f, `cat-${cat}`, tx, 66, 118, 30, isActive ? T.accentLt : T.bg, { radius: 6 });
      addText(f, cat, tx + 14, 73, { size: 13, weight: isActive ? 'Medium' : 'Regular',
        color: isActive ? T.accent : T.t2 });
      if (isActive) addRect(f, 'cat-underline', tx, 96, 118, 2, T.accent, { radius: 1 });
    });

    // Upload zone
    const UX = CX + 16, UW = CW - 32;
    addRect(f, 'upload-zone', UX, 110, UW, 96, T.surf2, { radius: 8, stroke: T.bdr });
    addText(f, '拖拽 .sql / .csv 文件到此处，或点击上传',
      UX + UW / 2 - 140, 136, { size: 14, color: T.t3 });
    addRect(f, 'upload-btn', UX + UW / 2 - 44, 160, 88, 28, T.accent, { radius: 6 });
    addText(f, '选择文件', UX + UW / 2 - 28, 166, { size: 12, weight: 'Medium', color: T.white });

    // Stats
    const stats = [
      { label: 'SQL 示例', val: '128 条' },
      { label: '已验证',   val: '104 条', color: T.pos },
      { label: '待验证',   val: '24 条',  color: T.warn },
    ];
    stats.forEach((s, i) => {
      const sx = UX + i * 180;
      addText(f, s.label, sx, 218, { size: 12, color: T.t3 });
      addText(f, s.val, sx, 234, { size: 18, weight: 'SemiBold', color: s.color || T.t1 });
    });

    // SQL list header
    addRect(f, 'list-header', CX, 268, CW, 36, T.surf3);
    ['SQL 文件名', '关联标签', '验证状态', '更新时间', '操作'].forEach((h, i) => {
      addText(f, h, CX + 16 + [0, 320, 560, 720, 920][i], 278, { size: 12, weight: 'SemiBold', color: T.t2 });
    });

    const sqlFiles = [
      { name: '各月销售汇总.sql',   tags: ['销售额', '月份'],   verified: true,  date: '2026-05-20' },
      { name: '客户留存率计算.sql', tags: ['留存率', '用户'],   verified: true,  date: '2026-05-18' },
      { name: '库存周转率.sql',     tags: ['库存', '效率'],    verified: false, date: '2026-05-15' },
      { name: '毛利率分析.sql',     tags: ['毛利', '分析'],    verified: true,  date: '2026-05-12' },
      { name: '大区对比视图.sql',   tags: ['大区', '对比'],    verified: false, date: '2026-05-10' },
      { name: '品类排名 TOP10.sql', tags: ['品类', '排名'],    verified: true,  date: '2026-05-08' },
      { name: '促销效果分析.sql',   tags: ['促销', '效果'],    verified: false, date: '2026-05-05' },
    ];
    sqlFiles.forEach((file, ri) => {
      const ry = 304 + ri * 52;
      addRect(f, `sql-row-${ri}`, CX, ry, CW, 50, ri % 2 ? T.surf2 : T.bg);
      addRect(f, `sql-row-border-${ri}`, CX, ry + 50, CW, 1, T.bdr);

      addText(f, file.name, CX + 16, ry + 16, { size: 13, weight: 'Medium', color: T.t1 });

      let tagX = CX + 320;
      file.tags.forEach(tag => { tagX = addTag(f, tag, tagX, ry + 15, T.dim2Lt, T.dim2); });

      addRect(f, `verified-badge-${ri}`, CX + 560, ry + 14, 64, 22,
        file.verified ? T.posLt : T.warnLt, { radius: 4 });
      addText(f, file.verified ? '✓ 已验证' : '⏳ 待验证', CX + 568, ry + 17,
        { size: 11, color: file.verified ? T.pos : T.warn });

      addText(f, file.date, CX + 720, ry + 16, { size: 12, color: T.t3 });
      addText(f, '验证  删除', CX + 920, ry + 16, { size: 12, color: T.accent });
    });
  }

  // ─────────────────────────────────────────
  //  9. S04 · 监控大盘
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S04 · 监控大盘', 0, 1);
    buildSidebar(f, 3);

    const CX = 220, CW = SW - CX;
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '监控大盘', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });
    // Live indicator
    addRect(f, 'live-dot', SW - 88, 24, 8, 8, T.pos, { radius: 4 });
    addText(f, '实时', SW - 76, 20, { size: 12, weight: 'Medium', color: T.pos });

    // KPI overview
    const kpiData = [
      { label: '今日查询量', val: '1,248', delta: '+23%', pos: true  },
      { label: '查询成功率', val: '96.4%', delta: '+1.2%', pos: true  },
      { label: '平均响应时间', val: '1.8s', delta: '↓0.3s', pos: true  },
      { label: '活跃用户',   val: '42',    delta: '+8',    pos: true  },
    ];
    const KW = (CW - 80) / 4;
    kpiData.forEach((k, i) => {
      const kx = CX + 24 + i * (KW + 16);
      addRect(f, `kpi-card-${i}`, kx, 72, KW, 80, T.surf2, { radius: 8 });
      addText(f, k.label, kx + 14, 84, { size: 12, color: T.t3 });
      addText(f, k.val, kx + 14, 102, { size: 22, weight: 'Bold', color: T.t1 });
      addText(f, k.delta, kx + 14, 134, { size: 12, weight: 'Medium', color: k.pos ? T.pos : T.neg });
    });

    // Trend chart
    const TCX = CX + 24, TCY = 168, TCW = 560, TCH = 260;
    addRect(f, 'trend-bg', TCX, TCY, TCW, TCH, T.surf2, { radius: 8 });
    addText(f, '查询量趋势（7天）', TCX + 16, TCY + 16,
      { size: 13, weight: 'SemiBold', color: T.t1 });
    // Simple line approximation via rects
    const pts = [40, 65, 45, 80, 58, 92, 72];
    const days = ['5/22', '5/23', '5/24', '5/25', '5/26', '5/27', '5/28'];
    pts.forEach((val, i) => {
      const bx = TCX + 40 + i * 72;
      const bh = Math.floor(val * 1.5);
      addRect(f, `trend-bar-${i}`, bx, TCY + TCH - bh - 32, 32, bh, T.accent, { radius: 3, opacity: 0.7 });
      addText(f, days[i], bx, TCY + TCH - 20, { size: 10, color: T.t3 });
      addText(f, String(val * 12), bx, TCY + TCH - bh - 48, { size: 10, color: T.t2 });
    });

    // Model dist chart
    const MCX = CX + 600, MCY = 168, MCW = CW - 624, MCH = 260;
    addRect(f, 'model-bg', MCX, MCY, MCW, MCH, T.surf2, { radius: 8 });
    addText(f, '模型调用分布', MCX + 16, MCY + 16, { size: 13, weight: 'SemiBold', color: T.t1 });
    // Donut
    addRect(f, 'donut-outer', MCX + MCW / 2 - 60, MCY + 60, 120, 120, T.surf3, { radius: 60 });
    addRect(f, 'donut-inner', MCX + MCW / 2 - 40, MCY + 80, 80, 80, T.surf2, { radius: 40 });
    const modelLegend = [
      { label: 'GPT-4o', pct: '42%', color: T.accent },
      { label: 'Claude 3.5', pct: '35%', color: T.pos },
      { label: 'Deepseek-V3', pct: '23%', color: T.warn },
    ];
    modelLegend.forEach((m, i) => {
      addRect(f, `legend-dot-${i}`, MCX + 16, MCY + 196 + i * 20, 10, 10, m.color, { radius: 5 });
      addText(f, `${m.label}  ${m.pct}`, MCX + 32, MCY + 196 + i * 20,
        { size: 12, color: T.t2 });
    });

    // Error table
    addText(f, '近期异常查询', CX + 24, 444, { size: 13, weight: 'SemiBold', color: T.t1 });
    addRect(f, 'err-header', CX, 466, CW, 32, T.surf3);
    const errCols = ['查询 ID', '用户', '问题摘要', '错误类型', '耗时', '时间'];
    const errColX = [CX + 16, CX + 112, CX + 208, CX + 620, CX + 840, CX + 940];
    errCols.forEach((c, i) => addText(f, c, errColX[i], 474, { size: 12, weight: 'SemiBold', color: T.t2 }));

    const errs = [
      { id: 'Q-2041', user: '张三', q: '华东区销售额按品类细分',  err: 'SQL 超时',   ms: '30s', time: '10:23' },
      { id: 'Q-2038', user: '李四', q: '毛利率最低的 SKU Top10', err: '字段不存在', ms: '0.8s', time: '10:18' },
      { id: 'Q-2031', user: '王五', q: '全国仓储库存周转率',       err: '权限不足',   ms: '1.2s', time: '09:55' },
    ];
    errs.forEach((e, ri) => {
      const ry = 498 + ri * 38;
      addRect(f, `err-row-${ri}`, CX, ry, CW, 36, ri % 2 ? T.surf2 : T.bg);
      [e.id, e.user, e.q, e.err, e.ms, e.time].forEach((cell, ci) => {
        addText(f, cell, errColX[ci], ry + 10,
          { size: 12, color: ci === 3 ? T.neg : T.t1, w: ci === 2 ? 380 : 120 });
      });
    });
  }

  // ─────────────────────────────────────────
  //  10. S05 · 查询审计
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S05 · 查询审计', 1, 1);
    buildSidebar(f, 4);

    const CX = 220, CW = SW - CX;
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '查询审计', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });

    // Filter bar
    addRect(f, 'filter-bar', CX, 56, CW, 52, T.surf2);
    addRect(f, 'filter-bar-border', CX, 107, CW, 1, T.bdr);

    const filters = ['全部', '成功', '失败', '超时'];
    filters.forEach((fl, i) => {
      const isA = i === 0;
      const fx = CX + 16 + i * 88;
      addRect(f, `flt-${fl}`, fx, 68, 80, 28, isA ? T.accent : T.bg, { radius: 6 });
      addText(f, fl, fx + isA ? 24 : 20, 74,
        { size: 13, weight: isA ? 'Medium' : 'Regular', color: isA ? T.white : T.t2 });
    });
    // Date picker
    addRect(f, 'date-range', SW - 212, 68, 180, 28, T.bg, { radius: 6, stroke: T.bdr });
    addText(f, '📅  2026-05-01 ~ 今日', SW - 200, 74, { size: 12, color: T.t2 });

    // Table header
    const tblColW = [88, 88, 300, 380, 60, 72, 88];
    let hx = CX;
    const tblColNames = ['查询 ID', '用户', '自然语言问题', '执行 SQL（摘要）', '耗时', '状态', '操作'];
    addRect(f, 'tbl-header', CX, 108, CW, 40, T.surf3);
    tblColNames.forEach((col, i) => {
      addText(f, col, hx + 12, 120, { size: 12, weight: 'SemiBold', color: T.t2 });
      hx += tblColW[i];
    });

    const auditRows = [
      { id: 'Q-2041', user: '张三', nl: '各大区上月销售额和同比增长',    sql: 'SELECT region, SUM(sales_amount)…', ms: '1.2s', ok: true  },
      { id: 'Q-2040', user: '李四', nl: '毛利率最低的 SKU Top10',       sql: 'SELECT sku_id, gross_margin…',      ms: '2.8s', ok: true  },
      { id: 'Q-2039', user: '王五', nl: '最近一周的库存周转率',           sql: 'SELECT stock_id, turnover_rate…',  ms: '超时', ok: false },
      { id: 'Q-2038', user: '赵六', nl: '华北区客单价趋势（按周）',       sql: 'SELECT week, AVG(order_amount)…',  ms: '0.9s', ok: true  },
      { id: 'Q-2037', user: '张三', nl: '退款率与上季度对比',             sql: 'SELECT quarter, refund_rate…',     ms: '1.5s', ok: true  },
      { id: 'Q-2035', user: '孙七', nl: '品类销售额占比分布',             sql: 'SELECT category, SUM(amount)…',    ms: '3.1s', ok: true  },
      { id: 'Q-2033', user: '李四', nl: '活跃用户数 MAU 趋势',           sql: 'SELECT month, COUNT(DISTINCT…',    ms: '1.8s', ok: true  },
    ];
    auditRows.forEach((row, ri) => {
      const ry = 148 + ri * 52;
      addRect(f, `audit-row-${ri}`, CX, ry, CW, 50, ri % 2 ? T.surf2 : T.bg);
      addRect(f, `audit-border-${ri}`, CX, ry + 50, CW, 1, T.bdr);

      let rx = CX;
      [row.id, row.user, row.nl, row.sql, row.ms,
        row.ok ? '成功' : '失败', '详情'].forEach((cell, ci) => {
        const color = ci === 5 ? (row.ok ? T.pos : T.neg) : ci === 6 ? T.accent : T.t1;
        addText(f, cell, rx + 12, ry + 16,
          { size: 12, color, w: tblColW[ci] - 16 });
        rx += tblColW[ci];
      });
    });
  }

  // ─────────────────────────────────────────
  //  11. S06 · 数据源管理
  // ─────────────────────────────────────────
  {
    const f = mkFrame('S06 · 数据源管理', 2, 1);
    buildSidebar(f, 5);

    const CX = 220, CW = SW - CX;
    addRect(f, 'topbar', CX, 0, CW, 56, T.bg);
    addRect(f, 'topbar-border', CX, 55, CW, 1, T.bdr);
    addText(f, '数据源管理', CX + 16, 18, { size: 16, weight: 'SemiBold', color: T.t1 });
    addRect(f, 'add-ds-btn', SW - 156, 14, 128, 28, T.accent, { radius: 6 });
    addText(f, '＋ 新增数据源', SW - 144, 20, { size: 12, weight: 'Medium', color: T.white });

    // DS cards grid
    const dsCards = [
      { name: '生产 MySQL',        db: 'MySQL 8.0',         tables: 128, ok: true,  schema: 'dw_prod'        },
      { name: '数仓 Hive',         db: 'Hive 3.1.0',        tables: 342, ok: true,  schema: 'data_warehouse' },
      { name: '分析 ClickHouse',   db: 'ClickHouse 23.8',   tables: 56,  ok: true,  schema: 'analytics'      },
      { name: '测试 PostgreSQL',   db: 'PostgreSQL 15',     tables: 42,  ok: false, schema: 'dw_test'        },
    ];
    const CARD_W = 560, CARD_H = 180;
    const CARD_GAP = 32;
    dsCards.forEach((ds, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const dx = CX + 24 + col * (CARD_W + CARD_GAP);
      const dy = 72 + row * (CARD_H + CARD_GAP);

      addRect(f, `ds-card-${i}`, dx, dy, CARD_W, CARD_H, T.surf2,
        { radius: 10, stroke: T.bdr });

      // DB icon
      addRect(f, `ds-icon-${i}`, dx + 16, dy + 16, 44, 44, T.accentLt, { radius: 10 });
      addText(f, '🗄️', dx + 28, dy + 26, { size: 20 });

      addText(f, ds.name, dx + 72, dy + 16, { size: 15, weight: 'SemiBold', color: T.t1 });
      addText(f, ds.db, dx + 72, dy + 38, { size: 12, color: T.t3 });

      // Status badge
      addRect(f, `ds-status-${i}`, dx + CARD_W - 88, dy + 14, 76, 22,
        ds.ok ? T.posLt : T.negLt, { radius: 4 });
      addText(f, ds.ok ? '● 正常' : '● 异常', dx + CARD_W - 80, dy + 17,
        { size: 11, weight: 'Medium', color: ds.ok ? T.pos : T.neg });

      addText(f, `Schema:  ${ds.schema}`, dx + 16, dy + 76, { size: 12, color: T.t2 });
      addText(f, `数据表:  ${ds.tables} 张`, dx + 16, dy + 96, { size: 12, color: T.t2 });

      // Progress bar (元数据覆盖率)
      addText(f, '元数据覆盖率', dx + 16, dy + 118, { size: 11, color: T.t3 });
      addRect(f, `ds-prog-bg-${i}`, dx + 96, dy + 121, 200, 8, T.surf3, { radius: 4 });
      addRect(f, `ds-prog-${i}`, dx + 96, dy + 121, ds.ok ? 168 : 80, 8,
        ds.ok ? T.pos : T.warn, { radius: 4 });
      addText(f, ds.ok ? '84%' : '40%', dx + 300, dy + 118, { size: 11, color: ds.ok ? T.pos : T.warn });

      // Actions
      addRect(f, `ds-sync-${i}`, dx + 16, dy + CARD_H - 42, 96, 28, T.surf3, { radius: 6 });
      addText(f, '同步元数据', dx + 22, dy + CARD_H - 35, { size: 11, color: T.t2 });
      addRect(f, `ds-test-${i}`, dx + 124, dy + CARD_H - 42, 72, 28, T.surf3, { radius: 6 });
      addText(f, '测试连接', dx + 132, dy + CARD_H - 35, { size: 11, color: T.t2 });
      addRect(f, `ds-edit-${i}`, dx + 208, dy + CARD_H - 42, 52, 28, T.accentLt, { radius: 6 });
      addText(f, '配置', dx + 222, dy + CARD_H - 35, { size: 11, weight: 'Medium', color: T.accent });
    });
  }

  // ─────────────────────────────────────────
  //  12. 完成
  // ─────────────────────────────────────────
  figma.viewport.scrollAndZoomIntoView(pg.children);
  figma.notify('✅ 数语 Datalogue · S01–S06 已生成，共 6 个 Frame', { timeout: 5000 });

})().catch(err => {
  figma.notify('❌ 生成失败：' + err.message, { error: true, timeout: 6000 });
  console.error(err);
});

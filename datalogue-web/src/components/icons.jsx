import React from 'react';

// Icon library — minimal line icons in line with the rest of the design.
// All icons render at 16x16 viewport by default; styled via CSS `.icon { width/height }`.

const Icon = ({ name, className = "icon", style }) => {
  const I = ICONS[name];
  if (!I) return null;
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"
         strokeLinecap="round" strokeLinejoin="round"
         className={className} style={style} aria-hidden="true">
      {I}
    </svg>
  );
};

const ICONS = {
  home: <><path d="M2.5 7.5 8 3l5.5 4.5V13a.5.5 0 0 1-.5.5h-3v-4h-4v4H3a.5.5 0 0 1-.5-.5V7.5Z" /></>,
  spark: <><path d="M8 2v3M8 11v3M2 8h3M11 8h3M3.5 3.5l2 2M10.5 10.5l2 2M3.5 12.5l2-2M10.5 5.5l2-2" /></>,
  chat: <><path d="M2.5 7.5C2.5 4.7 5 3 8 3s5.5 1.7 5.5 4.5S11 12 8 12c-.7 0-1.4-.1-2-.3L3 13l1-2.5C3 9.6 2.5 8.6 2.5 7.5Z" /></>,
  database: <><ellipse cx="8" cy="3.5" rx="5" ry="1.5" /><path d="M3 3.5v9c0 .83 2.24 1.5 5 1.5s5-.67 5-1.5v-9" /><path d="M3 8c0 .83 2.24 1.5 5 1.5s5-.67 5-1.5" /></>,
  layout: <><rect x="2" y="2.5" width="12" height="11" rx="1.5" /><path d="M2 6h12M6 6v7.5" /></>,
  send: <><path d="M2.5 8h11M8.5 3l5 5-5 5" /></>,
  plus: <><path d="M8 3v10M3 8h10" /></>,
  search: <><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></>,
  bell: <><path d="M4 7a4 4 0 1 1 8 0c0 3 1 4 1 4H3s1-1 1-4Zm2 5a2 2 0 0 0 4 0" /></>,
  cog: <><circle cx="8" cy="8" r="2" /><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8 3.4 3.4" /></>,
  user: <><circle cx="8" cy="5.5" r="2.5" /><path d="M3 13.5c.7-2.3 2.7-3.5 5-3.5s4.3 1.2 5 3.5" /></>,
  chev: <><path d="m6 4 4 4-4 4" /></>,
  chev_down: <><path d="m4 6 4 4 4-4" /></>,
  check: <><path d="m3 8 3.5 3.5L13 5" /></>,
  x: <><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></>,
  arrow_up_right: <><path d="M4.5 11.5 11.5 4.5M5.5 4.5h6v6" /></>,
  arrow_down: <><path d="M8 3v10M3.5 9 8 13.5 12.5 9" /></>,
  filter: <><path d="M2.5 3.5h11l-4 5v4l-3 1.5v-5.5l-4-5Z" /></>,
  calendar: <><rect x="2.5" y="3" width="11" height="10.5" rx="1.5" /><path d="M2.5 6.5h11M5.5 2v2.5M10.5 2v2.5" /></>,
  sql: <><path d="M3 4.5h3.5l1 1.5h5.5v6.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-8Z" /><path d="M6.5 9.5h3M6.5 11.5h3" /></>,
  sparkle: <><path d="M8 2 9 6l4 1-4 1-1 4-1-4-4-1 4-1 1-4Z" /><path d="M13 9.5 13.6 11l1.4.5-1.4.5L13 13.5l-.6-1.5-1.4-.5 1.4-.5L13 9.5Z" /></>,
  thunder: <><path d="M9 1.5 4 9h3.5L7 14.5 12 7H8.5L9 1.5Z" /></>,
  refresh: <><path d="M13.5 7.5a5.5 5.5 0 1 0-1.5 4M13.5 3v4.5h-4.5" /></>,
  share: <><circle cx="4" cy="8" r="1.5" /><circle cx="12" cy="3.5" r="1.5" /><circle cx="12" cy="12.5" r="1.5" /><path d="m5.4 7.2 5.2-3M5.4 8.8l5.2 3" /></>,
  pin: <><path d="M9.5 2 14 6.5l-2.5 1L9 10l1 4-5-5 2.5-2.5 1-2.5L9.5 2Z" /></>,
  copy: <><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" /><path d="M3 11V3.5A1 1 0 0 1 4 2.5h7" /></>,
  thumbs_up: <><path d="M9.5 2 8 6h-3a1 1 0 0 0-1 1v5.5a1 1 0 0 0 1 1h6.5a1 1 0 0 0 1-.8l1-5.5a1 1 0 0 0-1-1.2H9V3.5A1.5 1.5 0 0 0 9.5 2Z" /></>,
  thumbs_down: <><path d="M6.5 14 8 10h3a1 1 0 0 0 1-1V3.5a1 1 0 0 0-1-1H4.5a1 1 0 0 0-1 .8l-1 5.5a1 1 0 0 0 1 1.2H7v2.5A1.5 1.5 0 0 0 6.5 14Z" /></>,
  bookmark: <><path d="M4 2.5h8v11L8 11l-4 2.5v-11Z" /></>,
  attach: <><path d="M11 4.5 5.5 10A2 2 0 0 0 8.5 13l5.5-5.5a3.5 3.5 0 0 0-5-5L3.5 8A5 5 0 1 0 10.5 15" /></>,
  trace: <><circle cx="3.5" cy="3.5" r="1.5" /><circle cx="3.5" cy="12.5" r="1.5" /><circle cx="12.5" cy="8" r="1.5" /><path d="M3.5 5v6M5 4l6 3M5 12l6-3" /></>,
  chart_bar: <><path d="M3 13.5V10M7 13.5V7M11 13.5V4M2 13.5h12" /></>,
  chart_line: <><path d="M2 13.5h12M3 11l3-4 3 2 4-6" /></>,
  chart_pie: <><path d="M8 2.5v6h6A6 6 0 1 1 8 2.5Z" /><path d="M9.5 2.5a4.5 4.5 0 0 1 4 4h-4v-4Z" /></>,
  table: <><rect x="2.5" y="3" width="11" height="10" rx="1" /><path d="M2.5 6.5h11M2.5 9.5h11M6 6.5v6.5" /></>,
  globe: <><circle cx="8" cy="8" r="5.5" /><path d="M2.5 8h11M8 2.5c1.7 1.7 2.5 3.7 2.5 5.5S9.7 12.3 8 14c-1.7-1.7-2.5-3.7-2.5-5.5S6.3 4.2 8 2.5Z" /></>,
  folder: <><path d="M2.5 5v7.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H8L6.5 3.5h-3a1 1 0 0 0-1 1Z" /></>,
  flag: <><path d="M3.5 13.5V2.5h7l-1 2 1 2h-7" /></>,
  warn: <><path d="M8 2.5 14 13H2L8 2.5Z" /><path d="M8 7v3M8 11.5v.01" /></>,
  link: <><path d="M7 9a3 3 0 0 0 4.2 0L13 7.2a3 3 0 0 0-4.2-4.2L8 3.8M9 7a3 3 0 0 0-4.2 0L3 8.8A3 3 0 0 0 7.2 13l.8-.8" /></>,
  expand: <><path d="M9.5 3h3.5V6.5M6.5 13H3V9.5M13 3l-4 4M3 13l4-4" /></>,
  filter_alt: <><path d="M2 3.5h12M4 7.5h8M6 11.5h4" /></>,
  branch: <><circle cx="4" cy="3.5" r="1.5" /><circle cx="4" cy="12.5" r="1.5" /><circle cx="12" cy="8" r="1.5" /><path d="M4 5v6M5.5 8h5" /></>,
  drag: <><circle cx="6" cy="4" r="1" fill="currentColor" /><circle cx="6" cy="8" r="1" fill="currentColor" /><circle cx="6" cy="12" r="1" fill="currentColor" /><circle cx="10" cy="4" r="1" fill="currentColor" /><circle cx="10" cy="8" r="1" fill="currentColor" /><circle cx="10" cy="12" r="1" fill="currentColor" /></>,
  more: <><circle cx="3.5" cy="8" r="0.8" fill="currentColor" /><circle cx="8" cy="8" r="0.8" fill="currentColor" /><circle cx="12.5" cy="8" r="0.8" fill="currentColor" /></>,
  brain: <><path d="M5.5 4.5a2 2 0 0 1 3-1.7 2 2 0 0 1 3 1.7 2 2 0 0 1 1 3.5 2 2 0 0 1-1 3.5 2 2 0 0 1-3 1.7 2 2 0 0 1-3-1.7 2 2 0 0 1-1-3.5 2 2 0 0 1 1-3.5Z" /><path d="M8.5 5v8M5 8h2M9.5 8h2" /></>,
  formula: <><path d="M3 13.5 6 8 3 2.5M13 2.5 10 8l3 5.5M5.5 8h5" /></>,
  history: <><circle cx="8" cy="8" r="5.5" /><path d="M8 4.5V8l2 1.5M2.5 5l2-2M11.5 3 13 4.5" /></>,
  book: <><path d="M3 2.5h4a2 2 0 0 1 2 2v9a2 2 0 0 0-2-2H3v-9ZM13 2.5H9a2 2 0 0 0-2 2v9a2 2 0 0 1 2-2h4v-9Z" /></>,
  insight: <><circle cx="8" cy="7" r="3" /><path d="M6.5 12.5h3M7 14.5h2M8 4V2.5M11 5l1-1M5 5 4 4" /></>,
  preset: <><path d="M3.5 2.5h9v3h-9zM3.5 6.5h6v7h-6zM10.5 6.5h2v3h-2zM10.5 10.5h2v3h-2z" /></>,
  api: <><rect x="2" y="5" width="12" height="6" rx="1.5" /><path d="M5 8h1.5M9.5 8H11M7.5 7v2M8.5 7v2" /></>,
  key: <><circle cx="5" cy="11" r="2.5" /><path d="M7 9 13 3l1.5 1.5M11 5l1.5 1.5" /></>,
  code: <><path d="m5 5-3 3 3 3M11 5l3 3-3 3M9.5 4 7 12" /></>,
  archive: <><rect x="2" y="3" width="12" height="3" rx="0.8" /><path d="M3 6v6.5a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6M6.5 9h3" /></>,
  globe2: <><circle cx="8" cy="8" r="5.5" /><path d="M2.5 8h11" /><ellipse cx="8" cy="8" rx="2.5" ry="5.5" /></>,
  shield: <><path d="M8 2 3 4v5c0 2.5 2.2 4.5 5 5.5 2.8-1 5-3 5-5.5V4L8 2Z" /></>,
  bolt: <><path d="M9 1.5 4 9h3.5L7 14.5 12 7H8.5L9 1.5Z" /></>,
  plug: <><path d="M5 2v3M11 2v3M3.5 5h9v3a4.5 4.5 0 0 1-9 0V5ZM8 12.5V14.5" /></>,
  user_circle: <><circle cx="8" cy="8" r="5.5" /><circle cx="8" cy="6.5" r="1.8" /><path d="M4.5 12.5c.6-1.5 2-2.3 3.5-2.3s2.9.8 3.5 2.3" /></>,
  bell_dot: <><path d="M4 7a4 4 0 1 1 8 0c0 3 1 4 1 4H3s1-1 1-4Zm2 5a2 2 0 0 0 4 0" /><circle cx="12" cy="3.5" r="1.5" fill="currentColor" stroke="none" /></>,
  trash: <><path d="M3 4.5h10M6 4.5V3a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1.5M4.5 4.5V13a.5.5 0 0 0 .5.5h6a.5.5 0 0 0 .5-.5V4.5M6.5 7v4M9.5 7v4" /></>,
  pause: <><rect x="4" y="3" width="2.5" height="10" /><rect x="9.5" y="3" width="2.5" height="10" /></>,
  play: <><path d="M4.5 3 12 8l-7.5 5V3Z" /></>,
  swatch: <><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" /><circle cx="11" cy="11" r="1.5" fill="currentColor" stroke="none" /></>,
  layers: <><path d="M8 2 2 5l6 3 6-3-6-3Z" /><path d="m2 8 6 3 6-3M2 11l6 3 6-3" /></>,
  download: <><path d="M8 2v9M4.5 7.5 8 11l3.5-3.5M2.5 13.5h11" /></>,
  upload: <><path d="M8 11V2M4.5 5.5 8 2l3.5 3.5M2.5 13.5h11" /></>,
  log: <><path d="M3 2.5h10v11H3v-11ZM5 5.5h6M5 8h6M5 10.5h4" /></>,
  diff: <><path d="M5 2.5v8a2 2 0 0 0 2 2v2M11 13.5v-8a2 2 0 0 0-2-2V1.5M3 4l2-2 2 2M9 12l2 2 2-2" /></>,
  number: <><path d="M5 2.5 4 13.5M11 2.5l-1 11M2.5 6h11M2 10h11" /></>,
  string: <><path d="M3 5.5C3 4 4 3 5.5 3S8 4 8 5.5 7 8 5.5 8 3 9 3 10.5 4 13 5.5 13M13 5.5C13 4 12 3 10.5 3S8 4 8 5.5 9 8 10.5 8 13 9 13 10.5 12 13 10.5 13" /></>,
  bool: <><rect x="2" y="5" width="12" height="6" rx="3" /><circle cx="11" cy="8" r="2" fill="currentColor" stroke="none" /></>,
  enum_list: <><circle cx="4" cy="4" r="1" fill="currentColor" /><circle cx="4" cy="8" r="1" fill="currentColor" /><circle cx="4" cy="12" r="1" fill="currentColor" /><path d="M7 4h6M7 8h6M7 12h6" /></>,
  eye: <><path d="M2 8s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4ZM8 8h.01" /></>,
  edit: <><path d="M11 2.5l2.5 2.5-7 7H4v-2.5l7-7ZM3 13.5h10" /></>,
  beaker: <><path d="M5 2.5h6M6 2.5v4l-3 6h10l-3-6v-4M4.5 10.5h7" /></>,
  inbox: <><path d="M2 5.5l2-3h8l2 3v7.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5.5ZM2 8.5h4.5l1 1h2l1-1H14" /></>,
};

export { Icon, ICONS };

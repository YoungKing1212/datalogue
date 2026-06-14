// message-content.jsx
// 替换 chat.jsx 里手写的 renderAnswer() + cleanAnswer()。
// 用法: 在 chat.jsx 里 import MessageContent，把渲染答案的地方换成
//   <MessageContent text={msg.content} />                  // 历史消息
//   <MessageContent text={streamingAnswer} streaming />    // 流式中的气泡
//
// XSS: react-markdown 默认不渲染源文 HTML(没装 rehype-raw), 本身就是安全的。
//      后端答案里若混入 <think> 等标签, 会被下面的 splitThink 先剥离, 不进 Markdown。

import React, { useState, useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';          // 表格、删除线、任务列表、自动链接
import remarkMath from 'remark-math';        // 识别 $...$ / $$...$$
import rehypeKatex from 'rehype-katex';      // 渲染数学公式
import rehypeHighlight from 'rehype-highlight'; // 代码语法高亮
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github-dark.css';

/* ── 1) 把 <think>…</think> 从正文剥离(支持流式中间态: 未闭合也能切) ──
 * 原始思维链不进入对话层展示；业务化过程由 step/query_profile 承载。 */
export function splitThink(raw) {
  if (!raw) return { think: '', answer: '', thinking: false };
  const open = raw.indexOf('<think>');
  if (open === -1) return { think: '', answer: raw, thinking: false };
  const rest = raw.slice(open + 7);
  const close = rest.indexOf('</think>');
  if (close === -1) {
    // think 仍在流式输出, 正文还没开始
    return { think: rest, answer: raw.slice(0, open), thinking: true };
  }
  return {
    think: '',
    answer: (raw.slice(0, open) + rest.slice(close + 8)).trim(),
    thinking: false,
  };
}

/* ── 2) 流式容错: 未闭合的代码围栏临时补齐, 否则后续内容会被吞进代码块 ── */
function balanceFences(src) {
  if (!src) return src;
  const fences = (src.match(/```/g) || []).length;
  return fences % 2 === 1 ? src + '\n```' : src;
}

/* ── 3) 代码块外壳: 语言标签 + 复制按钮(覆盖 react-markdown 的 <pre>) ── */
function PreBlock({ children }) {
  const ref = useRef(null);
  const [copied, setCopied] = useState(false);
  const codeEl = React.Children.toArray(children)[0];
  const cls = (codeEl && codeEl.props && codeEl.props.className) || '';
  const lang = (/language-(\w+)/.exec(cls) || [])[1] || 'text';

  const copy = () => {
    const txt = ref.current ? ref.current.innerText : '';
    navigator.clipboard.writeText(txt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  };

  return (
    <div className="code-wrap">
      <div className="code-bar">
        <span className="code-lang">{lang}</span>
        <button type="button" className="code-copy" onClick={copy}>
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre ref={ref}>{children}</pre>
    </div>
  );
}

/* react-markdown 的元素映射 */
const mdComponents = {
  pre: PreBlock,                                  // 块级代码: 加壳
  code: (props) => <code className="md-inline-code" {...props} />, // 行内代码
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }) => (
    <div className="md-table-wrap"><table>{children}</table></div> // 表格可横向滚动
  ),
};

/* ── 4) 对外组件 ── */
export default function MessageContent({ text, streaming = false }) {
  const { answer } = useMemo(() => splitThink(text), [text]);
  const body = useMemo(
    () => (streaming ? balanceFences(answer) : answer),
    [answer, streaming]
  );

  return (
    <div className="ai-message">
      <div className="md-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex, rehypeHighlight]}
          components={mdComponents}
        >
          {body || ''}
        </ReactMarkdown>
        {streaming && body && <span className="stream-caret" />}
      </div>
    </div>
  );
}

// DatalogueMarkdown.jsx
// Datalogue 消息正文 Markdown 渲染壳，优先使用 assistant-ui Streamdown 主路径。

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown';
import {
  StreamdownTextPrimitive,
  escapeCurrencyDollars,
  normalizeMathDelimiters,
} from '@assistant-ui/react-streamdown';
import { code } from '@streamdown/code';
import { math } from '@streamdown/math';
import { mermaid } from '@streamdown/mermaid';
import { cjk } from '@streamdown/cjk';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import { preprocessDatalogueMarkdown } from './message-parts';

const markdownComponents = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }) => (
    <div className="md-table-wrap"><table>{children}</table></div>
  ),
  code: ({ className, children, ...props }) => (
    <code className={className || 'md-inline-code'} {...props}>{children}</code>
  ),
};

function preprocessMarkdown(text) {
  return escapeCurrencyDollars(normalizeMathDelimiters(preprocessDatalogueMarkdown(text)));
}

// Mermaid 渲染失败时的降级组件：不阻断回答，退回到源码 <pre> 展示，便于用户复制排查。
function MermaidErrorFallback({ chart, error }) {
  return (
    <pre className="streamdown-mermaid-fallback" aria-label="Mermaid 图表渲染失败">
      <div className="streamdown-mermaid-fallback-hint">
        Mermaid 图表渲染失败：{error || '未知错误'}
      </div>
      {chart}
    </pre>
  );
}

// StreamdownTextPrimitive 通用配置：插件（code + math + mermaid + cjk）+ 流式动画 + Mermaid 降级。
const STREAMDOWN_PLUGINS = { code, math, mermaid, cjk };
const STREAMDOWN_MERMAID_OPTIONS = { errorComponent: MermaidErrorFallback };
const STREAMDOWN_CONTROLS = { table: true, code: true, mermaid: true };

export function DatalogueMarkdownFallback({ text, className = 'ai-message md-body' }) {
  if (text != null) {
    return (
      <div className={className}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex, rehypeHighlight]}
          components={markdownComponents}
        >
          {preprocessMarkdown(text)}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <MarkdownTextPrimitive
      className={className}
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex, rehypeHighlight]}
      components={markdownComponents}
      preprocess={preprocessMarkdown}
    />
  );
}

export function DatalogueMarkdown({
  text,
  className = 'ai-message md-body',
  fallback = false,
}) {
  if (text != null || fallback) {
    return <DatalogueMarkdownFallback text={text} className={className} />;
  }

  return (
    <StreamdownTextPrimitive
      containerClassName={className}
      plugins={STREAMDOWN_PLUGINS}
      controls={STREAMDOWN_CONTROLS}
      mermaid={STREAMDOWN_MERMAID_OPTIONS}
      smooth={true}
      caret="block"
      defer={true}
      security={{ allowedProtocols: ['http', 'https', 'mailto'], allowDataImages: false }}
      preprocess={preprocessMarkdown}
    />
  );
}

export default DatalogueMarkdown;

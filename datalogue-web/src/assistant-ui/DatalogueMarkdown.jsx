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
      plugins={{ code, math }}
      controls={{ table: true, code: true }}
      security={{ allowedProtocols: ['http', 'https', 'mailto'], allowDataImages: false }}
      preprocess={preprocessMarkdown}
    />
  );
}

export default DatalogueMarkdown;

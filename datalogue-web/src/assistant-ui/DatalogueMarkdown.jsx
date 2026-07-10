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
import { EChartsBlock, MermaidBlock } from './DatalogueChartBlocks';

function codeText(children) {
  if (Array.isArray(children)) return children.join('');
  return typeof children === 'string' ? children : String(children || '');
}

function languageFromClassName(className = '') {
  const match = /language-([A-Za-z0-9_-]+)/.exec(className);
  return match ? match[1].toLowerCase() : '';
}

function MarkdownCode({ className, children, ...props }) {
  const language = languageFromClassName(className);
  const codeValue = codeText(children).replace(/\n$/, '');
  if (language === 'mermaid') {
    return <MermaidBlock code={codeValue} />;
  }
  if (language === 'echarts') {
    return <EChartsBlock code={codeValue} />;
  }
  return <code className={className || 'md-inline-code'} {...props}>{children}</code>;
}

function StreamdownMermaidBlock(props) {
  return <MermaidBlock {...props} />;
}

function StreamdownEChartsBlock(props) {
  return <EChartsBlock {...props} />;
}

const markdownComponents = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }) => (
    <div className="md-table-wrap"><table>{children}</table></div>
  ),
  code: MarkdownCode,
};

const streamdownComponentsByLanguage = {
  mermaid: { SyntaxHighlighter: StreamdownMermaidBlock },
  echarts: { SyntaxHighlighter: StreamdownEChartsBlock },
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
      componentsByLanguage={streamdownComponentsByLanguage}
      preprocess={preprocessMarkdown}
    />
  );
}

export default DatalogueMarkdown;

// DatalogueChartBlocks.jsx
// 渲染 Report Worker 生成的 Mermaid 与 ECharts 代码块，只接受本地安全输入。

import React from 'react';

const ECHARTS_MAX_CHARS = 20000;
const POLLUTION_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

let mermaidModulePromise;
let echartsModulePromise;

function loadMermaid() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((module) => {
      const mermaid = module.default || module;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
      });
      return mermaid;
    });
  }
  return mermaidModulePromise;
}

function loadECharts() {
  if (!echartsModulePromise) {
    echartsModulePromise = import('echarts');
  }
  return echartsModulePromise;
}

function extractCode(props) {
  if (typeof props?.code === 'string') return props.code;
  if (typeof props?.value === 'string') return props.value;
  const children = props?.children;
  if (Array.isArray(children)) return children.join('');
  return typeof children === 'string' ? children : String(children || '');
}

export function MermaidBlock(props) {
  const code = extractCode(props).trim();
  const id = React.useId().replace(/:/g, '');
  const [svg, setSvg] = React.useState('');
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    let cancelled = false;
    setSvg('');
    setError('');
    if (!code) {
      setError('Mermaid 图表内容为空。');
      return () => {
        cancelled = true;
      };
    }
    loadMermaid()
      .then((mermaid) => mermaid
      .render(`datalogue-mermaid-${id}`, code)
      .then(({ svg: renderedSvg }) => {
        if (!cancelled) setSvg(renderedSvg);
      }))
      .catch(() => {
        if (!cancelled) setError('Mermaid 图表渲染失败，已保留原始代码。');
      });
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (error) {
    return (
      <pre className="md-chart-fallback" data-chart="mermaid-error">
        <code>{code || error}</code>
      </pre>
    );
  }
  return (
    <div
      className="md-mermaid-block"
      data-testid="mermaid-block"
      dangerouslySetInnerHTML={{ __html: svg || '' }}
    />
  );
}

export function EChartsBlock(props) {
  const code = extractCode(props).trim();
  const ref = React.useRef(null);
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    if (!ref.current) return undefined;
    setError('');
    let chart;
    let disposed = false;
    try {
      const option = parseSafeEChartsOption(code);
      loadECharts()
        .then((echarts) => {
          if (!ref.current || disposed) return;
          chart = echarts.init(ref.current);
          chart.setOption(option, true);
        })
        .catch(() => {
          if (!disposed) setError('ECharts 图表渲染失败。');
        });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ECharts 图表渲染失败。');
      return undefined;
    }
    const handleResize = () => chart?.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      disposed = true;
      window.removeEventListener('resize', handleResize);
      chart?.dispose();
    };
  }, [code]);

  return (
    <>
      <div
        ref={ref}
        className="md-echarts-block"
        data-testid="echarts-block"
        role="img"
        aria-label="报告图表"
      />
      {error ? (
        <pre className="md-chart-fallback" data-chart="echarts-error">
          <code>{error}</code>
        </pre>
      ) : null}
    </>
  );
}

export function parseSafeEChartsOption(code) {
  if (!code) throw new Error('ECharts 图表内容为空。');
  if (code.length > ECHARTS_MAX_CHARS) throw new Error('ECharts option 超过大小限制。');
  const option = JSON.parse(code);
  if (!isPlainObject(option)) throw new Error('ECharts option 必须是 JSON 对象。');
  assertNoPrototypePollution(option);
  return option;
}

function isPlainObject(value) {
  if (value === null || Array.isArray(value) || typeof value !== 'object') return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function assertNoPrototypePollution(value) {
  if (Array.isArray(value)) {
    value.forEach(assertNoPrototypePollution);
    return;
  }
  if (!value || typeof value !== 'object') return;
  Object.keys(value).forEach((key) => {
    if (POLLUTION_KEYS.has(key)) {
      throw new Error('ECharts option 包含不允许的对象键。');
    }
    assertNoPrototypePollution(value[key]);
  });
}

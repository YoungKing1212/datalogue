// DataTable.jsx
// 通用分页数据表格组件，用于查询结果的详情展示。
// 默认每页展示 100 条数据，可通过 pageSize 覆盖；支持每页条数切换、页码跳转和行数统计。

import React, { useState, useMemo } from 'react';

const DEFAULT_PAGE_SIZE = 100;
const DEFAULT_PAGE_SIZE_OPTIONS = [20, 50, 100];

export default function DataTable({
  columns = [],
  rows = [],
  totalRowCount,
  truncated = false,
  className = '',
  pageSize = DEFAULT_PAGE_SIZE,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
}) {
  const [currentPage, setCurrentPage] = useState(1);

  // 每页行数交由内部 state 维护，初值来自 pageSize prop，允许用户在下拉里切换。
  const initialSize = Number.isFinite(pageSize) && pageSize > 0 ? Math.floor(pageSize) : DEFAULT_PAGE_SIZE;
  const [size, setSize] = useState(initialSize);

  // 页码跳转输入框的临时文本，避免直接绑定 currentPage 影响输入体验。
  const [jumpText, setJumpText] = useState('');

  // 下拉可选项：合并默认选项与当前初值并去重排序，保证初始每页值一定可选。
  const sizeOptions = useMemo(() => {
    const base = Array.isArray(pageSizeOptions) && pageSizeOptions.length ? pageSizeOptions : DEFAULT_PAGE_SIZE_OPTIONS;
    const merged = new Set([...base, initialSize].filter((n) => Number.isFinite(n) && n > 0).map((n) => Math.floor(n)));
    return Array.from(merged).sort((a, b) => a - b);
  }, [pageSizeOptions, initialSize]);

  const total = totalRowCount != null ? totalRowCount : rows.length;
  // 实际可分页的数据量：后端已截断时按返回行数分页，避免用总数量生成虚假页码。
  const effectiveTotal = rows.length >= total ? total : rows.length;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / size));

  // 当页数据：按实际可用行数切片，若后端未返回后续页则 effectiveTotal 会自动限制页码。
  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * size;
    return rows.slice(start, start + size);
  }, [rows, currentPage, size]);

  const safeCurrentPage = Math.min(currentPage, totalPages);
  if (safeCurrentPage !== currentPage) {
    setCurrentPage(safeCurrentPage);
  }

  // 切换每页条数：重置回第一页，避免停留在超出新总页数的空白页。
  const handleSizeChange = (nextSize) => {
    const value = Number(nextSize);
    if (!Number.isFinite(value) || value <= 0) return;
    setSize(Math.floor(value));
    setCurrentPage(1);
  };

  // 提交页码跳转：解析输入并夹取到合法区间，非法输入清空后不跳转。
  const commitJump = () => {
    const target = parseInt(jumpText, 10);
    if (Number.isFinite(target)) {
      setCurrentPage(Math.min(Math.max(target, 1), totalPages));
    }
    setJumpText('');
  };

  if (!columns.length) {
    return <div className="data-table-empty">查询结果无数据列。</div>;
  }

  // 页脚显示条件：数据量超过最小可选每页值时才有分页/切换意义。
  const showFooter = effectiveTotal > Math.min(...sizeOptions);

  return (
    <div className={`data-table-wrap ${className}`.trim()}>
      {/* 统计栏 */}
      <div className="data-table-stats">
        <span>
          共 <strong>{total.toLocaleString()}</strong> 行
          {rows.length < total && (
            <span className="data-table-stats-hint">
              （展示前 {rows.length.toLocaleString()} 行）
            </span>
          )}
          {truncated && (
            <span className="data-table-stats-warn"> · 仅展示前 10000 行</span>
          )}
        </span>
        <span>
          第 {safeCurrentPage}/{totalPages} 页
        </span>
      </div>

      {/* 表格 */}
      <div className="data-table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th className="data-table-row-num">#</th>
              {columns.map((col, i) => (
                <th key={i} title={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="data-table-empty-row">
                  当前页无数据。
                </td>
              </tr>
            ) : (
              pageRows.map((row, ri) => (
                <tr key={ri}>
                  <td className="data-table-row-num">{(safeCurrentPage - 1) * size + ri + 1}</td>
                  {columns.map((col, ci) => (
                    <td key={ci} title={formatCellValue(row[col])}>
                      {formatCellValue(row[col])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页控件 */}
      {showFooter && (
        <div className="data-table-pagination">
          {/* 每页条数选择 */}
          <div className="data-table-page-size">
            <span>每页</span>
            <select
              className="data-table-page-size-select"
              value={size}
              onChange={(e) => handleSizeChange(e.target.value)}
              title="每页显示条数"
            >
              {sizeOptions.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
            <span>条</span>
          </div>

          {/* 翻页按钮 */}
          <div className="data-table-page-nav">
            <button
              type="button"
              className="data-table-page-btn"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(1)}
              title="第一页"
            >
              «
            </button>
            <button
              type="button"
              className="data-table-page-btn"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(safeCurrentPage - 1)}
              title="上一页"
            >
              ‹
            </button>
            <span className="data-table-page-info">
              {safeCurrentPage} / {totalPages}
            </span>
            <button
              type="button"
              className="data-table-page-btn"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(safeCurrentPage + 1)}
              title="下一页"
            >
              ›
            </button>
            <button
              type="button"
              className="data-table-page-btn"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(totalPages)}
              title="最后一页"
            >
              »
            </button>
          </div>

          {/* 页码跳转 */}
          <div className="data-table-page-jump">
            <span>跳至</span>
            <input
              type="number"
              min={1}
              max={totalPages}
              className="data-table-page-jump-input"
              value={jumpText}
              placeholder={String(safeCurrentPage)}
              onChange={(e) => setJumpText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  commitJump();
                }
              }}
              onBlur={commitJump}
              title="输入页码后回车跳转"
            />
            <span>页</span>
          </div>
        </div>
      )}
    </div>
  );
}

function formatCellValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'number') return value.toLocaleString();
  return String(value);
}

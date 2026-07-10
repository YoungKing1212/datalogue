// DataTable.jsx
// 通用分页数据表格组件，用于查询结果的详情展示。
// 每页展示 100 条数据，支持页面切换和行数统计。

import React, { useState, useMemo } from 'react';

const PAGE_SIZE = 100;

export default function DataTable({ columns = [], rows = [], totalRowCount, truncated = false, className = '' }) {
  const [currentPage, setCurrentPage] = useState(1);

  const total = totalRowCount != null ? totalRowCount : rows.length;
  // 实际可分页的数据量：后端已截断时按返回行数分页，避免用总数量生成虚假页码。
  const effectiveTotal = rows.length >= total ? total : rows.length;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / PAGE_SIZE));

  // 当页数据：按实际可用行数切片，若后端未返回后续页则 effectiveTotal 会自动限制页码。
  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }, [rows, currentPage]);

  const safeCurrentPage = Math.min(currentPage, totalPages);
  if (safeCurrentPage !== currentPage) {
    setCurrentPage(safeCurrentPage);
  }

  if (!columns.length) {
    return <div className="data-table-empty">查询结果无数据列。</div>;
  }

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
                  <td className="data-table-row-num">{(safeCurrentPage - 1) * PAGE_SIZE + ri + 1}</td>
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
      {totalPages > 1 && (
        <div className="data-table-pagination">
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

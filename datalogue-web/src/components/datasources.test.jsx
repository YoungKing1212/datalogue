// datasources.test.jsx
// 数据源展示 helper 测试：覆盖 Doris 产品身份与 MySQL 执行方言分离。

import { describe, expect, it } from 'vitest';

import { datasourceDisplayInfo } from './datasources.jsx';

describe('datasourceDisplayInfo', () => {
  it('shows Doris as a first-class product while keeping mysql execution dialect visible', () => {
    const info = datasourceDisplayInfo(
      { db_type: 'doris', dialect: 'mysql', driver: 'pymysql', port: 9030 },
      { db_type: 'doris', label: 'Doris', dialect: 'mysql', driver: 'pymysql', default_port: 9030 },
    );

    expect(info.icon).toBe('🌊');
    expect(info.productLabel).toBe('Doris（MySQL 协议）');
    expect(info.dialectLabel).toBe('mysql（Doris 第一阶段执行方言）');
    expect(info.driverLabel).toBe('pymysql');
    expect(info.portLabel).toBe(9030);
  });

  it('keeps Oracle capability labels and dialect unchanged', () => {
    const info = datasourceDisplayInfo(
      { db_type: 'oracle', dialect: 'oracle', driver: 'oracledb', port: 1521 },
      { db_type: 'oracle', label: 'Oracle', dialect: 'oracle', driver: 'oracledb', default_port: 1521 },
    );

    expect(info.icon).toBe('🔶');
    expect(info.productLabel).toBe('Oracle');
    expect(info.dialectLabel).toBe('oracle');
    expect(info.driverLabel).toBe('oracledb');
    expect(info.portLabel).toBe(1521);
  });
});

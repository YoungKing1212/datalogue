import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Sidebar } from './sidebar.jsx';

vi.mock('../auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      username: 'kenyang',
      role: 'admin',
      is_superuser: true,
    },
  }),
}));

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

describe('Sidebar navigation counts', () => {
  it('renders simplified sidebar groups and entries', () => {
    render(
      <MemoryRouter initialEntries={['/datasets']}>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText('数语')).toBeInTheDocument();
    expect(screen.getByText('问数')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /对话问数/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /模板问数/ })).toBeInTheDocument();
    expect(screen.getByText('数据资产')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /数据集/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /指标库/ })).toBeInTheDocument();
    expect(screen.getByText('分析洞察')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /我的分析/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /洞察中心/ })).toBeInTheDocument();
    expect(screen.getByText('系统管理')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /团队管理/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /系统设置/ })).toBeInTheDocument();
  });

  it('renders footer identity with avatar and role', () => {
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText('kenyang')).toBeInTheDocument();
    expect(screen.getByText('超级管理员')).toBeInTheDocument();
    expect(screen.getByText('K')).toBeInTheDocument();
  });
});

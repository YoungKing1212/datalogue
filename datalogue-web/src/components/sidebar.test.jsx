import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Sidebar } from './sidebar.jsx';
import { listNavigationCounts } from '../api/client';

const { authState } = vi.hoisted(() => ({
  authState: {
    user: {
      username: 'kenyang',
      role: 'admin',
      is_superuser: true,
    },
  },
}));

vi.mock('../api/client', () => ({
  listNavigationCounts: vi.fn(),
}));

vi.mock('../auth/auth-context', () => ({
  useAuth: () => authState,
}));

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

describe('Sidebar navigation counts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      username: 'kenyang',
      role: 'admin',
      is_superuser: true,
    };
  });

  it('renders database-backed counts and removes old hardcoded badges', async () => {
    listNavigationCounts.mockResolvedValue({
      dashboard: 2,
      history: 11,
      datasets: 3,
      knowledge: 9,
      review: 1,
      datasources: 4,
      apis: null,
    });

    render(
      <MemoryRouter initialEntries={['/datasets']}>
        <Sidebar />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(listNavigationCounts).toHaveBeenCalledTimes(1);
    });

    expect(within(screen.getByRole('button', { name: /监控大盘/ })).getByText('2')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /查询历史/ })).getByText('11')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /数据集 & 指标/ })).getByText('3')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /知识库/ })).getByText('9')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /审核队列/ })).getByText('1')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /数据源/ })).getByText('4')).toBeInTheDocument();

    expect(within(screen.getByRole('button', { name: /API 接口/ })).queryByText('7')).not.toBeInTheDocument();
    expect(screen.queryByText('24')).not.toBeInTheDocument();
    expect(screen.queryByText('234')).not.toBeInTheDocument();
    expect(screen.queryByText('6')).not.toBeInTheDocument();
    expect(screen.queryByText('5')).not.toBeInTheDocument();
  });

  it('keeps badges empty when navigation count loading fails', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    listNavigationCounts.mockRejectedValue(new Error('network down'));

    try {
      render(
        <MemoryRouter initialEntries={['/datasets']}>
          <Sidebar />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(listNavigationCounts).toHaveBeenCalledTimes(1);
      });

      expect(within(screen.getByRole('button', { name: /监控大盘/ })).queryByText('6')).not.toBeInTheDocument();
      expect(within(screen.getByRole('button', { name: /API 接口/ })).queryByText('7')).not.toBeInTheDocument();
      expect(screen.queryByText('24')).not.toBeInTheDocument();
      expect(screen.queryByText('234')).not.toBeInTheDocument();
      expect(screen.queryByText('5')).not.toBeInTheDocument();
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('普通用户不展示 LLM 模型管理入口', async () => {
    authState.user = {
      username: 'member',
      role: 'user',
      is_superuser: false,
    };
    listNavigationCounts.mockResolvedValue({});

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(listNavigationCounts).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole('button', { name: /LLM 模型/ })).not.toBeInTheDocument();
  });
});

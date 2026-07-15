import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { LLMModelsScreen } from './settings.jsx';
import { resolveLLMProviderBrand } from './llm-provider-logo.jsx';
import { get, patch, post, del as apiDelete } from '../api/client';

vi.mock('../api/client', () => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}));

vi.mock('../auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      username: 'kenyang',
      full_name: 'Ken Yang',
      email: 'ken@example.test',
      role: 'admin',
      is_superuser: true,
    },
  }),
}));

vi.mock('./icons', () => ({
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

describe('LLMModelsScreen 模型配置', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue([]);
    patch.mockResolvedValue({});
    post.mockResolvedValue({});
    apiDelete.mockResolvedValue({});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('保存新增模型配置时把模型字段写入 AgentScope credential data', async () => {
    render(<MemoryRouter><LLMModelsScreen /></MemoryRouter>);
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/api/agentscope-control/credentials');
    });

    fireEvent.click(screen.getByRole('button', { name: /新增 credential/ }));

    fireEvent.change(screen.getByLabelText('接入模板'), { target: { value: 'custom' } });
    fireEvent.change(screen.getByLabelText('供应商'), { target: { value: 'openai-compatible' } });
    fireEvent.change(screen.getByPlaceholderText('MiniMax via AgentScope'), {
      target: { value: '测试 DeepSeek' },
    });
    fireEvent.change(screen.getByPlaceholderText('http://localhost:4000/v1'), {
      target: { value: 'https://api.deepseek.com/v1' },
    });
    fireEvent.change(screen.getByLabelText('模型名'), { target: { value: 'custom' } });
    fireEvent.change(screen.getByPlaceholderText('输入模型名，如 datalogue-sql'), {
      target: { value: 'deepseek-v4-pro' },
    });
    fireEvent.change(screen.getByPlaceholderText('sk-...'), {
      target: { value: 'sk-test' },
    });
    fireEvent.change(screen.getByDisplayValue('启用'), { target: { value: 'disabled' } });
    fireEvent.change(screen.getByDisplayValue('60'), { target: { value: '45' } });
    fireEvent.change(screen.getByPlaceholderText('用途、供应商或路由说明'), {
      target: { value: 'BI Worker 默认模型' },
    });

    fireEvent.click(screen.getByRole('button', { name: /保存 credential$/ }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/agentscope-control/credentials', {
        data: {
          name: '测试 DeepSeek',
          type: 'datalogue_llm_credential',
          base_url: 'https://api.deepseek.com/v1',
          api_key: 'sk-test',
          model: 'deepseek-v4-pro',
          status: 'disabled',
          description: 'BI Worker 默认模型',
          request_timeout_seconds: 45,
        },
      });
    });
  });

  it('列表启停操作更新 AgentScope credential 状态字段', async () => {
    get.mockResolvedValue([
      {
        id: 'cred-1',
        data: {
          name: '测试模型',
          type: 'datalogue_llm_credential',
          base_url: 'https://api.example.test/v1',
          model: 'datalogue-model',
          status: 'active',
          api_key_set: true,
        },
      },
    ]);

    render(<MemoryRouter><LLMModelsScreen /></MemoryRouter>);
    await screen.findByText('测试模型');

    fireEvent.click(screen.getByTitle('停用'));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith('/api/agentscope-control/credentials/cred-1', {
        data: { status: 'disabled' },
      });
    });
  });
});

describe('LLM 厂商标识识别', () => {
  it.each([
    [{ provider: 'openai', model: 'gpt-4o' }, 'openai'],
    [{ provider: 'openai-compatible', model: 'MiniMax-M3', base_url: 'https://api.minimaxi.com/v1' }, 'minimax'],
    [{ provider: 'deepseek', model: 'deepseek-chat' }, 'deepseek'],
    [{ provider: 'qwen', model: 'qwen-max' }, 'qwen'],
    [{ provider: 'anthropic', model: 'claude-sonnet-4' }, 'anthropic'],
    [{ provider: 'custom', model: 'internal-model' }, null],
  ])('根据供应商、模型和地址识别官方标识：%o', (model, expected) => {
    expect(resolveLLMProviderBrand(model)).toBe(expected);
  });
});

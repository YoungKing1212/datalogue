import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

  it('展示 AgentScope 模型列表并支持逐模型真实测试', async () => {
    get.mockImplementation(async (path) => {
      if (path === '/api/agentscope-control/credentials') {
        return [
          {
            id: 'cred-1',
            data: {
              name: 'OpenAI 主连接',
              type: 'openai_credential',
              base_url: 'https://api.openai.com/v1',
              model: 'gpt-4o',
              status: 'active',
              api_key_set: true,
            },
          },
        ];
      }
      if (path === '/api/agentscope-control/model?provider=openai_credential') {
        return [
          {
            name: 'gpt-4.1',
            label: 'GPT 4.1',
            status: 'active',
            input_types: ['text/plain', 'image/png'],
            output_types: ['text/plain'],
            context_size: 128000,
          },
        ];
      }
      return [];
    });
    post.mockResolvedValue({
      ok: true,
      message: '模型测试成功',
      detail: {
        model: 'gpt-4.1',
        latency_ms: 321,
        sample: 'OK',
      },
    });

    render(<MemoryRouter><LLMModelsScreen /></MemoryRouter>);
    await screen.findByText('OpenAI 主连接');

    fireEvent.click(screen.getByRole('button', { name: '模型列表' }));

    expect(await screen.findByText('GPT 4.1')).toBeTruthy();
    expect(screen.getByText(/图片输入 · 128K 上下文/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '测试模型 gpt-4.1' }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/api/agentscope-control/credentials/cred-1/test',
        { model: 'gpt-4.1' },
      );
    });
    expect(await screen.findByText(/测试通过 · 321ms · OK/)).toBeTruthy();
  });

  it('忽略已关闭或已切换 credential 的旧模型目录响应', async () => {
    let resolveOpenAI;
    let resolveDeepSeek;
    const openAICatalog = new Promise(resolve => { resolveOpenAI = resolve; });
    const deepSeekCatalog = new Promise(resolve => { resolveDeepSeek = resolve; });

    get.mockImplementation((path) => {
      if (path === '/api/agentscope-control/credentials') {
        return Promise.resolve([
          {
            id: 'cred-openai',
            data: {
              name: 'OpenAI 连接',
              type: 'openai_credential',
              base_url: 'https://api.openai.com/v1',
              model: 'gpt-4o',
              status: 'active',
              api_key_set: true,
            },
          },
          {
            id: 'cred-deepseek',
            data: {
              name: 'DeepSeek 连接',
              type: 'deepseek_credential',
              base_url: 'https://api.deepseek.com/v1',
              model: 'deepseek-chat',
              status: 'active',
              api_key_set: true,
            },
          },
        ]);
      }
      if (path === '/api/agentscope-control/model?provider=openai_credential') {
        return openAICatalog;
      }
      if (path === '/api/agentscope-control/model?provider=deepseek_credential') {
        return deepSeekCatalog;
      }
      return Promise.resolve([]);
    });

    render(<MemoryRouter><LLMModelsScreen /></MemoryRouter>);
    await screen.findByText('OpenAI 连接');
    const modelListButtons = screen.getAllByRole('button', { name: '模型列表' });
    fireEvent.click(modelListButtons[0]);
    fireEvent.click(screen.getByRole('button', { name: '关闭模型列表' }));
    fireEvent.click(modelListButtons[1]);

    await act(async () => {
      resolveDeepSeek([{ name: 'deepseek-v4', label: 'DeepSeek V4', status: 'active' }]);
    });
    expect(await screen.findByText('DeepSeek V4')).toBeTruthy();

    await act(async () => {
      resolveOpenAI([{ name: 'gpt-late', label: '迟到的 GPT', status: 'active' }]);
    });
    expect(screen.getByText('DeepSeek V4')).toBeTruthy();
    expect(screen.queryByText('迟到的 GPT')).not.toBeInTheDocument();
  });

  it('已下线模型不可设为当前模型', async () => {
    get.mockImplementation(async (path) => {
      if (path === '/api/agentscope-control/credentials') {
        return [
          {
            id: 'cred-1',
            data: {
              name: 'OpenAI 主连接',
              type: 'openai_credential',
              base_url: 'https://api.openai.com/v1',
              model: 'gpt-4o',
              status: 'active',
              api_key_set: true,
            },
          },
        ];
      }
      if (path === '/api/agentscope-control/model?provider=openai_credential') {
        return [{ name: 'gpt-legacy', label: 'Legacy GPT', status: 'sunset' }];
      }
      return [];
    });

    render(<MemoryRouter><LLMModelsScreen /></MemoryRouter>);
    await screen.findByText('OpenAI 主连接');
    fireEvent.click(screen.getByRole('button', { name: '模型列表' }));

    const sunsetRow = (await screen.findByText('Legacy GPT')).closest('article');
    const switchButton = within(sunsetRow).getByRole('button', { name: '已下线' });
    expect(switchButton).toBeDisabled();
    fireEvent.click(switchButton);
    expect(patch).not.toHaveBeenCalled();
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

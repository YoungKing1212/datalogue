// chat-adapter.test.js
// 验证 Chat adapter 将后端 SSE/final payload 收敛为 C-ready 消息 metadata。

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeChatAdapter, buildBusinessSessionId } from './chat-adapter';
import { buildHistoryMessageCustom } from './thread-list-adapter';

vi.mock('./agent-team-task-api', () => ({
  streamAgentTeamTask: vi.fn(),
}));

vi.mock('./thread-list-adapter', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    resolveRemoteId: vi.fn(() => null),
    resolveRecentInitializedRemoteId: vi.fn(() => null),
  };
});

const { streamAgentTeamTask } = await import('./agent-team-task-api');

async function* events(items) {
  for (const item of items) {
    yield asAgentTeamEnvelope(item);
  }
}

function asAgentTeamEnvelope(item) {
  if (item?.event_envelope) return item;
  if (item?.type === 'final') {
    return {
      task_id: item.task_id,
      legacy_payload: item,
      event_envelope: {
        event_type: 'message.completed',
        task_id: item.task_id,
        trace_id: item.trace_id,
        payload: { ...item, summary: item.answer || item.summary },
        legacy_payload: item,
      },
    };
  }
  if (item?.type === 'route_decision') {
    return {
      task_id: item.task_id,
      event_envelope: {
        event_type: item.decision === 'ambiguous' ? 'clarification.required' : 'dataset.selected',
        task_id: item.task_id,
        trace_id: item.trace_id,
        payload: {
          ...item,
          route_decision: item,
          clarification: item.clarification || null,
        },
      },
    };
  }
  if (item?.type === 'step') {
    return {
      task_id: item.task_id,
      event_envelope: {
        event_type: item.node || 'task.step',
        task_id: item.task_id,
        trace_id: item.trace_id,
        payload: {
          ...item,
          summary: item.display_name || item.summary || item.node,
          status: item.status || 'done',
        },
      },
    };
  }
  if (item?.type === 'repair') {
    return {
      task_id: item.task_id,
      event_envelope: {
        event_type: item.event_type || 'repair.plan_created',
        task_id: item.task_id,
        trace_id: item.trace_id,
        payload: item,
      },
    };
  }
  return item;
}

function runInput(options = {}) {
  return {
    messages: [
      {
        role: 'user',
        content: [{ type: 'text', text: options.question || '查询销售趋势' }],
      },
    ],
    abortSignal: options.abortSignal || new AbortController().signal,
    unstable_threadId: options.threadId,
  };
}

async function collectRun(adapter, input = runInput()) {
  const chunks = [];
  for await (const chunk of adapter.run(input)) {
    chunks.push(chunk);
  }
  return chunks;
}

describe('chat-adapter C-ready metadata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
    window.history.pushState({}, '', '/chat');
  });

  it('uses Agent Team task stream as the default chat send path', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'trace.updated',
          payload: { summary: '正在通过 AgentScope 固定智能体团队处理。' },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '双周会议共有 100 条记录。',
            artifact_ref: 'artifact:shell-1',
            checkpoint_ref: 'checkpoint:shell-1',
            row_count: 100,
            column_count: 67,
            reasoning_summary: [
              {
                title: '识别任务',
                summary: '已识别为 BI 查询，问题为统计双周会议数据记录数量。',
                status: 'completed',
              },
              {
                title: '生成结果',
                summary: '已生成可查看的查询结果。',
                status: 'completed',
                ref: 'artifact:shell-1',
                row_count: 100,
                column_count: 67,
              },
              {
                title: '内部明细',
                summary: 'select * from hidden_table',
                status: 'completed',
              },
            ],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 12 } });
    const chunks = await collectRun(adapter, runInput({
      question: '统计双周会议数据记录数量',
      threadId: 'local-thread',
    }));
    const finalChunk = chunks.at(-1);

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '统计双周会议数据记录数量',
        dataset_id: 12,
        conversation_id: null,
      }),
      expect.any(Object),
    );
    expect(chunks[0].content.some((part) => part.type === 'reasoning')).toBe(true);
    expect(finalChunk).toMatchObject({
      status: { type: 'complete', reason: 'stop' },
      content: expect.arrayContaining([{ type: 'text', text: '双周会议共有 100 条记录。' }]),
    });
    const finalReasonings = finalChunk.content.filter((part) => part.type === 'reasoning');
    expect(finalReasonings).toHaveLength(2);
    expect(finalReasonings.map((part) => part.text)).toEqual([
      '识别任务：已识别为 BI 查询，问题为统计双周会议数据记录数量。',
      '生成结果：已生成可查看的查询结果。（100 行、67 列）',
    ]);
    expect(finalChunk.metadata.custom).toMatchObject({
      resultRef: 'artifact:shell-1',
    });
    expect(JSON.stringify(finalChunk.metadata.custom)).not.toMatch(/\bSELECT\b|raw_rows|schema_context/i);
  });

  it('keeps realtime Agent progress reasoning after the final summary arrives', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-progress',
          trace_id: 'trace-progress',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'dataset_match',
            status: 'running',
            title: '候选数据集筛选',
            summary: '已识别日志查询，正在筛选候选数据集。',
            sql: 'select * from hidden_table',
            schema: { tables: ['hidden_table'] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          task_id: 'task-progress',
          trace_id: 'trace-progress',
          payload: {
            summary: '查询已完成，共 100 行。',
            artifact_ref: 'artifact:progress-1',
            reasoning_summary: [
              {
                title: '查询完成',
                summary: '已生成可查看的查询结果。',
                status: 'completed',
              },
            ],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const finalChunk = chunks.at(-1);
    const reasonings = finalChunk.content.filter((part) => part.type === 'reasoning');

    expect(reasonings).toEqual(expect.arrayContaining([
      expect.objectContaining({
        parentId: 'agent-worker',
        agentRole: 'worker',
        agentName: 'BI Worker',
        phase: 'dataset_match',
        status: 'running',
        text: '候选数据集筛选：已识别日志查询，正在筛选候选数据集。',
      }),
      expect.objectContaining({
        parentId: 'reasoning_summary',
        text: '查询完成：已生成可查看的查询结果。',
      }),
    ]));
    expect(JSON.stringify(finalChunk)).not.toMatch(/\bselect \* from\b|hidden_table|schema/i);
  });

  it('streams BI Worker thinking summary as a dedicated reasoning part and preserves it after final', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 思考中',
            summary: '正在分析问题与可用数据证据。',
            reasoning_kind: 'bi_worker_thinking_summary',
            stream_group_id: 'reply-1:think-1',
            sequence: 1,
            raw_delta: 'select * from hidden_table',
            debug_raw: false,
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          task_id: 'task-thinking',
          payload: {
            summary: '查询已完成。',
            reasoning_summary: [
              {
                title: '生成结果',
                summary: '已生成可查看的查询结果。',
                status: 'completed',
              },
            ],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const firstReasonings = chunks[0].content.filter((part) => part.type === 'reasoning');
    const finalReasonings = chunks.at(-1).content.filter((part) => part.type === 'reasoning');

    expect(firstReasonings).toEqual(expect.arrayContaining([
      expect.objectContaining({
        parentId: 'agent-worker-thinking:reply-1:think-1',
        reasoningKind: 'bi_worker_thinking_summary',
        text: 'BI Worker 思考中：正在分析问题与可用数据证据。',
      }),
    ]));
    expect(finalReasonings).toEqual(expect.arrayContaining([
      expect.objectContaining({
        parentId: 'agent-worker-thinking:reply-1:think-1',
        reasoningKind: 'bi_worker_thinking_summary',
      }),
      expect.objectContaining({
        parentId: 'reasoning_summary',
        text: '生成结果：已生成可查看的查询结果。',
      }),
    ]));
    expect(JSON.stringify(chunks)).not.toMatch(/select \* from|hidden_table|raw_delta|schema|query_plan|raw_rows/i);
  });

  it('accumulates debug raw BI Worker thinking delta in a separate marked reasoning part', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-debug',
            sequence: 1,
            debug_raw: true,
            raw_delta: '先分析',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-debug',
            sequence: 2,
            debug_raw: true,
            raw_delta: '用户问题',
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const rawReasoning = chunks.at(-1).content.find((part) => (
      part.type === 'reasoning' && part.reasoningKind === 'bi_worker_raw_thinking_delta'
    ));

    expect(rawReasoning).toMatchObject({
      parentId: 'agent-worker-raw-thinking:reply-1:think-debug',
      title: 'BI Worker 调试原文',
      debugRaw: true,
      text: 'BI Worker 调试原文：先分析用户问题',
    });
  });

  it('concatenates BI Worker raw thinking deltas without inserting spaces', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-english-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-english-debug',
            sequence: 1,
            debug_raw: true,
            raw_delta: 'The',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-english-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-english-debug',
            sequence: 2,
            debug_raw: true,
            raw_delta: 'user',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-english-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-english-debug',
            sequence: 3,
            debug_raw: true,
            raw_delta: ' wants',
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const rawReasoning = chunks.at(-1).content.find((part) => (
      part.type === 'reasoning' && part.reasoningKind === 'bi_worker_raw_thinking_delta'
    ));

    // 前端不再补空格：'The' + 'user' 之间不插入空格；第 3 段自带前导空格予以保留。
    expect(rawReasoning).toMatchObject({
      parentId: 'agent-worker-raw-thinking:reply-1:think-english-debug',
      debugRaw: true,
      text: 'BI Worker 调试原文：Theuser wants',
    });
  });

  it('preserves identifiers and numbers across raw thinking delta boundaries', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-ident-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-ident-debug',
            sequence: 1,
            debug_raw: true,
            raw_delta: 'plan_task_d',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-ident-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-ident-debug',
            sequence: 2,
            debug_raw: true,
            raw_delta: 'aily_record 202',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-thinking-ident-debug',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 调试原文',
            summary: '调试原文流式片段。',
            reasoning_kind: 'bi_worker_raw_thinking_delta',
            stream_group_id: 'reply-1:think-ident-debug',
            sequence: 3,
            debug_raw: true,
            raw_delta: '5 LIMIT',
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const rawReasoning = chunks.at(-1).content.find((part) => (
      part.type === 'reasoning' && part.reasoningKind === 'bi_worker_raw_thinking_delta'
    ));

    // 标识符 plan_task_daily_record、数字 2025、SQL 关键字 LIMIT 都不能被中间空格破坏；
    // 段内自带的空格（"_record " / "2025 "）保留。
    expect(rawReasoning).toMatchObject({
      parentId: 'agent-worker-raw-thinking:reply-1:think-ident-debug',
      debugRaw: true,
      text: 'BI Worker 调试原文：plan_task_daily_record 2025 LIMIT',
    });
  });

  it('keeps BI Worker schema slice progressive payload out of chat content', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          task_id: 'task-schema-slice',
          trace_id: 'trace-schema-slice',
          payload: {
            datalogue_event_type: 'bi_worker_l2_schema_slice',
            summary: 'employee_name 字段已进入结构切片。',
            safe_reason: '已确认相关数据结构。',
            entities: [{ name: 'employee_name' }],
            relationships: [{ from: 'employee_name', to: 'department_id' }],
            selects: ['employee_name'],
            filters: [{ field: 'employee_name', op: 'like', value: '杨凯' }],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询员工姓名' }));
    const finalChunk = chunks.at(-1);
    const encodedContent = JSON.stringify(finalChunk.content);

    expect(encodedContent).toContain('数据结构确认');
    expect(encodedContent).not.toMatch(/employee_name|department_id|entities|relationships|selects|filters/i);
    expect(JSON.stringify(finalChunk.metadata?.custom || {})).not.toMatch(/employee_name|department_id/i);
  });

  it('renders an artifact card when Agent Team final returns only artifact_card', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '查询已完成，共 100 行、48 列。',
            artifact_card: {
              title: '查询结果',
              status: 'completed',
              summary_for_chat: '查询已完成，共 100 行、48 列。',
              primary_ref: {
                ref_id: 'artifact:worker-1',
                ref_type: 'result',
                label: '查询结果',
              },
              actions: [
                {
                  action_type: 'view',
                  label: '查看详情',
                  ref: 'artifact:worker-1',
                  disabled: false,
                },
              ],
            },
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 10 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯2025年日志' }));
    const finalChunk = chunks.at(-1);

    expect(finalChunk.metadata.custom.resultRef).toBe('artifact:worker-1');
    expect(finalChunk.metadata.custom.artifactCard).toMatchObject({
      title: '查询结果',
      status: 'completed',
      primary_ref: {
        ref_id: 'artifact:worker-1',
        ref_type: 'result',
        label: '查询结果',
      },
      actions: [
        {
          action_type: 'view',
          label: '查看详情',
          ref: 'artifact:worker-1',
          disabled: false,
        },
      ],
    });
  });

  it('ignores legacy numeric model config ids when the composer has no AgentScope model resource', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '已使用默认 AgentScope 模型查询。' },
        },
      },
    ]));

    const adapter = makeChatAdapter({
      datasetIdRef: { current: 12 },
      modelConfigIdRef: { current: 8 },
      transport: 'stream',
    });
    await collectRun(adapter, runInput({
      question: '用默认模型查询销售趋势',
      threadId: 'local-thread',
    }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '用默认模型查询销售趋势',
        dataset_id: 12,
        model_credential_id: null,
        model_name: null,
        model_parameters: {},
      }),
      expect.any(Object),
    );
    expect(Object.keys(streamAgentTeamTask.mock.calls[0][0])).not.toContain('model' + '_config_id');
  });

  it('passes AgentScope credential and model to Agent Team when available', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '已完成 AgentScope 模型指定查询。' },
        },
      },
    ]));

    const adapter = makeChatAdapter({
      datasetIdRef: { current: 12 },
      modelConfigIdRef: {
        current: {
          id: 8,
          credential_id: 'openai_credential:prod-main',
          model: 'gpt-4.1-mini',
          model_parameters: {
            thinking_enable: true,
            api_key: 'must-not-pass',
          },
        },
      },
      transport: 'stream',
    });
    await collectRun(adapter, runInput({
      question: '用 AgentScope 模型查询销售趋势',
      threadId: 'local-thread',
    }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '用 AgentScope 模型查询销售趋势',
        dataset_id: 12,
        model_credential_id: 'openai_credential:prod-main',
        model_name: 'gpt-4.1-mini',
        model_parameters: {
          thinking_enable: true,
        },
      }),
      expect.any(Object),
    );
  });

  it('maps Agent Team final conversation id back to the current local thread', async () => {
    const resolvedListener = vi.fn();
    const renameListener = vi.fn();
    window.addEventListener('datalogue:conv-resolved', resolvedListener);
    window.addEventListener('datalogue:thread-rename', renameListener);
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'final',
        answer: '合同总金额为 100 万元。',
        conversation_id: 88,
        result_ref: 'artifact:result-88',
        title: '统计合同总金额',
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 12 } });
    await collectRun(adapter, runInput({
      question: '统计合同总金额',
      threadId: 'local-thread',
    }));

    expect(resolvedListener).toHaveBeenCalledWith(expect.objectContaining({
      detail: { localThreadId: 'local-thread', actualConvId: 88 },
    }));
    expect(renameListener).toHaveBeenCalledWith(expect.objectContaining({
      detail: { remoteId: '88', title: '统计合同总金额' },
    }));
    window.removeEventListener('datalogue:conv-resolved', resolvedListener);
    window.removeEventListener('datalogue:thread-rename', renameListener);
  });

  it('routes missing dataset through Agent Team so BI Agent can choose it', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '请选择数据集',
            route_decision: {
              decision: 'no_match',
              candidates: [
                {
                  dataset_id: 1,
                  dataset_name: '销售明细',
                  reason: '匹配销售分析问题',
                  confidence: 0.42,
                  requires_confirmation: true,
                },
              ],
            },
            clarification: {
              kind: 'dataset_missing',
              candidates: [
                {
                  dataset_id: 1,
                  dataset_name: '销售明细',
                  reason: '匹配销售分析问题',
                },
              ],
            },
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: null } });
    const chunks = await collectRun(adapter, runInput({
      question: '查询销售趋势',
      threadId: 'local-thread',
    }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '查询销售趋势',
        dataset_id: null,
      }),
      expect.any(Object),
    );
    expect(chunks.at(-1).metadata.custom.candidateDatasets).toEqual({
      candidates: [
        {
          dataset_id: 1,
          dataset_name: '销售明细',
          short_reason: '匹配销售分析问题',
        },
      ],
    });
  });

  it('hides internal planning text when final answer asks for dataset confirmation', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: (
              "TheuserwantstoqueryYangKai's2025worklogs(工作日志)."
              + 'ThisisaBI(BusinessIntelligence)querytask.'
              + 'Letmebreakthisdown:1.ThetaskisaBIquery-查询杨凯2025年的工作日志'
              + '2.IneedtocreateateamwithaBIworkertohandlethisquery.'
            ),
            route_decision: {
              decision: 'ambiguous',
              candidates: [
                {
                  dataset_id: 12,
                  dataset_name: '运营双周会议数据集',
                  reason: '名称或描述与「工作日志」匹配',
                },
                {
                  dataset_id: 10,
                  dataset_name: '生产经营管理系统日志数据集',
                  reason: '名称或描述与「工作日志」匹配',
                },
              ],
            },
            clarification: {
              kind: 'dataset_choice',
              candidates: [
                {
                  dataset_id: 12,
                  dataset_name: '运营双周会议数据集',
                  reason: '名称或描述与「工作日志」匹配',
                },
                {
                  dataset_id: 10,
                  dataset_name: '生产经营管理系统日志数据集',
                  reason: '名称或描述与「工作日志」匹配',
                },
              ],
            },
            reasoning_summary: [
              {
                title: '整理回答',
                summary: 'TheuserwantstoqueryYangKai and Ineedtocreateateam',
                status: 'completed',
              },
            ],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: null } });
    const chunks = await collectRun(adapter, runInput({
      question: '查询杨凯2025年日志',
      threadId: 'local-thread',
    }));
    const finalChunk = chunks.at(-1);
    const finalText = finalChunk.content.find((part) => part.type === 'text').text;

    expect(finalText).toContain('已筛选出可能匹配的候选数据集');
    expect(finalText).toContain('数据集 10：生产经营管理系统日志数据集');
    expect(finalText).not.toMatch(/Theuserwantstoquery|Ineedtocreate/);
    expect(finalChunk.content.filter((part) => part.type === 'reasoning')).toHaveLength(0);
  });

  it('does not pass legacy model config ids through Agent Team when dataset selection is needed', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '请选择数据集' },
        },
      },
    ]));

    const adapter = makeChatAdapter({
      datasetIdRef: { current: null },
      modelConfigIdRef: { current: 8 },
    });
    await collectRun(adapter, runInput({
      question: '查询销售趋势',
      threadId: 'local-thread',
    }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '查询销售趋势',
        dataset_id: null,
        model_credential_id: null,
        model_name: null,
        model_parameters: {},
      }),
      expect.any(Object),
    );
    expect(Object.keys(streamAgentTeamTask.mock.calls[0][0])).not.toContain('model' + '_config_id');
  });

  it('builds stable business session ids from conversation or thread context', () => {
    expect(buildBusinessSessionId({ conversationId: 12, threadId: 'local', fallbackSessionId: 'fallback' }))
      .toBe('conversation-12');
    expect(buildBusinessSessionId({ conversationId: null, threadId: 'thread/abc', fallbackSessionId: 'fallback' }))
      .toBe('assistant-thread-thread-abc');
    expect(buildBusinessSessionId({ conversationId: null, threadId: '', fallbackSessionId: 'fallback' }))
      .toBe('fallback');
  });

  it('collapses repeated streaming reasoning and routes leader monologue into the thinking chain', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      { event_envelope: { event_type: 'message.delta', payload: { content: '用户想查询工作日志，' } } },
      { event_envelope: { event_type: 'message.delta', payload: { content: '我需要创建团队来处理。' } } },
      { type: 'step', node: 'task.step', status: 'done', display_name: '处理中' },
      { type: 'step', node: 'task.step', status: 'done', display_name: '处理中' },
      { type: 'step', node: 'task.step', status: 'done', display_name: '处理中' },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '查询已完成，共 3 行。',
            reasoning_summary: [
              { title: '识别任务', summary: '已识别为 BI 查询。', status: 'completed' },
            ],
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 5 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询工作日志', threadId: 'local-thread' }));

    // 流式阶段：正文不铺 Leader 规划，改由思考链承载
    const streamingChunks = chunks.filter((c) =>
      c.content.some((p) => p.type === 'reasoning' && p.parentId === 'live_thinking'),
    );
    expect(streamingChunks.length).toBeGreaterThan(0);
    expect(streamingChunks[0].content.find((p) => p.type === 'text').text).toBe('');
    // live_thinking 按分组键 upsert，多条 delta 累积到同一条，不再逐条堆叠
    const lastStreaming = streamingChunks[streamingChunks.length - 1];
    const liveThinking = lastStreaming.content.find((p) => p.parentId === 'live_thinking');
    expect(liveThinking.text).toContain('我需要创建团队');

    // 重复 step 折叠为一条，不再堆出几百条
    const beforeFinal = chunks[chunks.length - 2];
    const repeatedStep = beforeFinal.content.filter(
      (p) => p.type === 'reasoning' && p.parentId === 'task.step',
    );
    expect(repeatedStep).toHaveLength(1);

    // final：正文收敛为干净答案，思考过程（live_thinking）保留不消失
    const finalChunk = chunks.at(-1);
    expect(finalChunk.content.find((p) => p.type === 'text').text).toBe('查询已完成，共 3 行。');
    expect(finalChunk.content.some((p) => p.type === 'reasoning' && p.parentId === 'live_thinking')).toBe(true);
  });

  it('converts route, step and final events into timeline and artifact metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'route_decision',
        decision: 'selected',
        dataset_name: '销售明细',
        dataset_id: 7,
        score: 0.91,
      },
      {
        type: 'step',
        node: 'intent_recognition',
        status: 'done',
        intent: '销售趋势分析',
      },
      {
        type: 'step',
        node: 'dsl_compiler',
        status: 'done',
        sql: 'SELECT secret_col FROM hidden_table',
      },
      {
        type: 'step',
        node: 'sql_execute',
        status: 'done',
        rows: 2,
        columns: ['date', 'gmv'],
      },
      {
        type: 'final',
        answer: '销售趋势整体上升',
        conversation_id: 42,
        message_id: 99,
        result_ref: 'artifact:result:42',
        sql_result: {
          columns: ['secret_col', 'gmv'],
          rows: [{ secret_col: 'hidden_table_row', gmv: 100 }],
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const finalChunk = chunks.at(-1);

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '查询销售趋势',
        session_id: 'assistant-thread-local-thread',
        conversation_id: null,
        dataset_id: 7,
        clarification_response: null,
      }),
      expect.any(Object),
    );
    expect(finalChunk.status).toEqual({ type: 'complete', reason: 'stop' });
    expect(finalChunk.metadata.custom.taskTimeline.map((item) => item.type)).toEqual([
      'dataset_matching',
      'task_understood',
      'bi_execution',
      'artifact_created',
      'next_action',
    ]);
    expect(finalChunk.metadata.custom.artifactCard).toMatchObject({
      title: '查询结果',
      primary_ref: 'artifact:result:42',
    });
    expect(finalChunk.metadata.custom.artifactCard.preview_payload).toBeNull();
    expect(finalChunk.metadata.custom.stepTrace).toHaveLength(3);
    expect(JSON.stringify(finalChunk.content)).not.toMatch(/SELECT|secret_col|hidden_table/i);
  });

  it('maps final SSE artifact refs without internal planning, observability or raw result metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'step',
        node: 'query_plan',
        status: 'done',
        query_plan: { query_type: 'metric_query', execution_strategy: 'query_graph' },
      },
      {
        type: 'final',
        answer: '最近30日 GMV 为 100。',
        sql: 'SELECT 100 AS gmv',
        sql_result: {
          columns: ['secret_col'],
          rows: [{ secret_col: 'raw_row_value', hidden_table: 'hidden_table' }],
        },
        sql_diagnosis: { root_cause: 'hidden_table.secret_col 缺失' },
        sql_audit_result: { rewritten_sql: 'SELECT secret_col FROM hidden_table' },
        query_plan: { query_type: 'metric_query', internal_field: 'secret_col' },
        candidate_assets: { tables: ['hidden_table'], fields: ['secret_col'] },
        query_plan_debug: { prompt: 'SELECT secret_col FROM hidden_table' },
        dsl: { metrics: ['gmv'], dimensions: ['secret_col'] },
        route_payload: {
          kind: 'term_conflict_clarification',
          clarification_id: 'clarify-raw',
          candidates: [
            {
              name: 'secret_col',
              definition: 'SELECT secret_col FROM hidden_table',
              fields: ['secret_col'],
            },
          ],
        },
        result_ref: 'artifact:result-1',
        report_ref: 'artifact:report-1',
        message_id: 42,
        conversation_id: 7,
        trace_id: 'trace-1',
        trace_session_id: 'session-1',
        observability: { trace_id: 'trace-1', session_id: 'session-1' },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 3 } });
    const chunks = await collectRun(adapter, runInput({
      question: '最近30日GMV趋势如何',
      threadId: 'local-thread',
    }));

    const final = chunks.at(-1);
    expect(final.status).toEqual({ type: 'complete', reason: 'stop' });
    expect(final.metadata.custom.resultRef).toBe('artifact:result-1');
    expect(final.metadata.custom.reportRef).toBe('artifact:report-1');
    expect(final.metadata.custom.observabilityTraceId).toBeUndefined();
    expect(final.metadata.custom.observability).toBeUndefined();
    expect(final.metadata.custom.stepTrace).toHaveLength(1);
    expect(JSON.stringify(final.metadata.custom)).not.toMatch(
      /SELECT|secret_col|hidden_table|raw_row_value|query_plan|queryPlan|candidate_assets|candidateAssets|query_plan_debug|queryPlanDebug|dsl|sqlResult|sqlDiagnosis|sqlAuditResult/i,
    );
  });

  it('maps Agent Team artifact refs from message completed envelopes into result metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'artifact.created',
          task_id: 'task-agentic-1',
          trace_id: 'trace-agentic-1',
          thread_id: 'as_thread_1',
          payload: {
            summary: 'BI 查询产物已生成。',
            artifact_ref: 'artifact:safe',
            checkpoint_ref: 'checkpoint:safe',
            row_count: 1,
            column_count: 2,
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          task_id: 'task-agentic-1',
          trace_id: 'trace-agentic-1',
          thread_id: 'as_thread_1',
          payload: {
            summary: 'DatasetAgent 查询完成，已生成安全结果引用。',
            artifact_ref: 'artifact:safe',
            checkpoint_ref: 'checkpoint:safe',
            row_count: 1,
            column_count: 2,
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const final = chunks.at(-1);

    expect(final.metadata.custom.resultRef).toBe('artifact:safe');
    expect(final.metadata.custom.artifactCard).toMatchObject({
      title: '查询结果',
      status: 'completed',
      primary_ref: 'artifact:safe',
    });
    expect(final.metadata.custom.taskTimeline.map((item) => item.type)).toContain('artifact_created');
    // artifact card 走 DataMessagePart（type: 'data'），primary_ref 会随卡片进入 final.content，
    // 这是 Data UI 的预期行为；只需保证控制面 refs（checkpoint / raw / repair）不泄漏。
    expect(JSON.stringify(final.content)).not.toMatch(/checkpoint:safe|raw_rows|raw_sql|repair_patch/i);
    // artifact card 的 primary_ref 允许出现在 DataMessagePart 里，但不能出现在 text part 里。
    const artifactCardPart = final.content.find(
      (part) => part && part.type === 'data' && part.name === 'datalogue-artifact-card',
    );
    expect(artifactCardPart).toBeTruthy();
    expect(artifactCardPart.data.primary_ref).toBe('artifact:safe');
    const textPart = final.content.find((part) => part && part.type === 'text');
    expect(JSON.stringify(textPart)).not.toMatch(/artifact:safe|checkpoint:safe/i);
  });

  it('exposes only business-level candidate dataset confirmation metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'final',
        answer: '请选择数据集',
        route_decision: {
          decision: 'ambiguous',
          candidates: [
            {
              dataset_id: 1,
              dataset_name: '销售明细',
              reason: '匹配销售分析问题',
              fields: ['raw_field'],
              raw_sql: 'SELECT * FROM t',
            },
          ],
        },
        original_question: '查询杨凯2025年工作日志',
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    const chunks = await collectRun(adapter);
    const candidateDatasets = chunks.at(-1).metadata.custom.candidateDatasets;

    expect(candidateDatasets).toEqual({
      original_question: '查询杨凯2025年工作日志',
      candidates: [
        {
          dataset_id: 1,
          dataset_name: '销售明细',
          short_reason: '匹配销售分析问题',
        },
      ],
    });
    expect(JSON.stringify(candidateDatasets)).not.toMatch(/raw_field|SELECT/i);
  });

  it('passes pending clarification response once and then clears it', async () => {
    streamAgentTeamTask.mockReturnValue(events([{ type: 'final', answer: '已确认' }]));
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = {
      selected_dataset_id: 7,
      selected_text: '销售明细',
      original_question: '查询杨凯2025年工作日志',
    };

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    await collectRun(adapter, runInput({ question: '确认使用：销售明细' }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '查询杨凯2025年工作日志',
        dataset_id: 7,
        clarification_response: {
          selected_dataset_id: 7,
          selected_text: '销售明细',
          original_question: '查询杨凯2025年工作日志',
        },
      }),
      expect.any(Object),
    );
    expect(window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__).toBeNull();
  });

  it('passes pending workbench retry request to chat stream once and clears it', async () => {
    streamAgentTeamTask.mockReturnValue(events([{ type: 'final', answer: '已从检查点恢复' }]));
    window.__DATALOGUE_PENDING_WORKBENCH_RETRY__ = {
      question: '查询杨凯 2024 年工作日志',
      conversation_id: 31,
      thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      retry_checkpoint_ref: 'checkpoint://conv-31-msg-74/query_context_ready',
      dataset_id: 7,
      display_text: '重试上一步',
    };

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    await collectRun(adapter, runInput({ question: '重试上一步', threadId: 'local-thread' }));

    expect(streamAgentTeamTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '查询杨凯 2024 年工作日志',
        session_id: 'conversation-31',
        conversation_id: 31,
        thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        retry_checkpoint_ref: 'checkpoint://conv-31-msg-74/query_context_ready',
        dataset_id: 7,
        clarification_response: null,
      }),
      expect.any(Object),
    );
    expect(window.__DATALOGUE_PENDING_WORKBENCH_RETRY__).toBeNull();
  });

  it('emits resolved AgentScope thread id from final payload', async () => {
    const listener = vi.fn();
    window.addEventListener('datalogue:thread-resolved', listener);
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'final',
        answer: '已完成',
        thread_id: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    await collectRun(adapter, runInput({ threadId: 'local-thread' }));

    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      detail: {
        localThreadId: 'local-thread',
        threadId: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      },
    }));
    window.removeEventListener('datalogue:thread-resolved', listener);
  });

  it('does not fabricate ArtifactCard refs when replaying old history metadata', () => {
    const custom = buildHistoryMessageCustom({
      id: 99,
      response_metadata: {
        query_plan: { query_type: 'metric_query' },
        observability: { trace_id: 'trace-old', session_id: 'session-old' },
      },
    });

    expect(custom.resultRef).toBeNull();
    expect(custom.reportRef).toBeNull();
    expect(custom.subagentToolResults).toBeNull();
    expect(custom.observabilityTraceId).toBeUndefined();
  });

  it('does not restore internal SQL, planning, DSL or raw rows into history message custom metadata', () => {
    const custom = buildHistoryMessageCustom({
      id: 100,
      response_metadata: {
        sql: 'SELECT secret_col FROM hidden_table',
        sql_result: {
          columns: ['secret_col'],
          rows: [{ secret_col: 'raw_row_value' }],
        },
        sql_diagnosis: { root_cause: 'hidden_table.secret_col 缺失' },
        sql_audit_result: { rewritten_sql: 'SELECT secret_col FROM hidden_table' },
        query_plan: { query_type: 'metric_query', internal_field: 'secret_col' },
        candidate_assets: { tables: ['hidden_table'], fields: ['secret_col'] },
        query_plan_debug: { prompt: 'SELECT secret_col FROM hidden_table' },
        dsl: { metrics: ['gmv'], dimensions: ['secret_col'] },
        route_payload: {
          kind: 'term_conflict_clarification',
          clarification_id: 'clarify-raw',
          candidates: [
            {
              name: 'secret_col',
              definition: 'SELECT secret_col FROM hidden_table',
              fields: ['secret_col'],
            },
          ],
        },
      },
    }, [
      {
        node: 'dsl_compiler',
        status: 'done',
        sql: 'SELECT other_secret FROM other_hidden_table',
        dsl: { dimensions: ['secret_col'] },
      },
      {
        node: 'sql_execute',
        status: 'done',
        columns: ['secret_col'],
        rows: [{ secret_col: 'trace_raw_row' }],
      },
    ]);

    expect(JSON.stringify(custom)).not.toMatch(
      /SELECT|secret_col|hidden_table|other_secret|raw_row_value|trace_raw_row|query_plan|queryPlan|candidate_assets|candidateAssets|query_plan_debug|queryPlanDebug|dsl|sqlResult|sqlDiagnosis|sqlAuditResult/i,
    );
  });

  it('maps repair event envelopes into business-level metadata without leaking patch details', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.evaluated',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，正在评估自动修复方案。',
            status: 'evaluated',
            repair_plan_ref: 'artifact:repair-plan-1',
          },
        },
      },
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.plan_created',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，已生成自动修复方案。',
            status: 'plan_created',
            repair_plan_ref: 'artifact:repair-1',
            checkpoint_ref: 'checkpoint://conv-1-msg-2/repair',
            patch: { field: 'bad_col' },
            raw_sql: 'select bad_col from work_log',
          },
        },
      },
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.rerun_completed',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，已生成自动修复方案。',
            status: 'rerun_completed',
            repair_plan_ref: 'artifact:repair-1',
          },
        },
      },
      {
        type: 'final',
        answer: '杨凯 2024 年共有 2 条工作日志。',
        conversation_id: 42,
        message_id: 99,
        result_ref: 'artifact:result-1',
        repair_plan_ref: 'artifact:repair-1',
        repair_status: 'rerun_completed',
        repair_failure_class: 'FIELD_NOT_FOUND',
        repair_plan: {
          business_summary: '字段口径不匹配，已生成自动修复方案。',
          repair_plan_ref: 'artifact:repair-1',
          patch: { field: 'bad_col' },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯 2024 年工作日志' }));
    const custom = chunks.at(-1).metadata.custom;

    expect(custom.repairPlan).toMatchObject({
      summary: '字段口径不匹配，已生成自动修复方案。',
      status: 'rerun_completed',
      repairPlanRef: 'artifact:repair-1',
      failureClass: 'FIELD_NOT_FOUND',
    });
    expect(custom.repairTimeline.map((item) => item.eventType)).toEqual([
      'repair.evaluated',
      'repair.plan_created',
      'repair.rerun_completed',
    ]);
    expect(JSON.stringify(custom.repairPlan)).not.toMatch(/bad_col|work_log|select/i);
  });

  it('maps C2 repair patch summary into timeline, artifact refs, and safe metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.evaluated',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，正在评估自动修复方案。',
            status: 'evaluated',
            repair_plan_ref: 'artifact:repair-plan-1',
          },
        },
      },
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.plan_created',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，已生成自动修复方案。',
            status: 'plan_created',
            repair_plan_ref: 'artifact:repair-plan-1',
          },
        },
      },
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.rerun_started',
          visibility: 'user_visible',
          payload: {
            summary: '字段口径不匹配，正在重新执行查询。',
            status: 'rerun_started',
            repair_plan_ref: 'artifact:repair-plan-1',
          },
        },
      },
      {
        type: 'repair',
        event_envelope: {
          event_type: 'repair.patch_applied',
          visibility: 'user_visible',
          payload: {
            repair_patch_summary: {
              repair_strategy: '按业务口径自动修复字段引用。',
              failure_class: 'FIELD_NOT_FOUND',
              confidence_band: 'high',
              validation_summary: '修复方案已通过工具校验。',
            },
            repair_patch: {
              trace_only_metadata: {
                replacement_field_ref: 'work_log.bad_col',
              },
            },
            raw_sql: 'select bad_col from work_log',
          },
        },
      },
      {
        type: 'final',
        answer: '已完成查询。',
        conversation_id: 42,
        message_id: 99,
        result_ref: 'artifact:result-1',
        repair_plan_ref: 'artifact:repair-plan-1',
        repair_patch_summary: {
          repair_strategy: '按业务口径自动修复字段引用。',
          failure_class: 'FIELD_NOT_FOUND',
          confidence_band: 'high',
          validation_summary: '修复方案已通过工具校验。',
        },
        repair_patch: {
          trace_only_metadata: {
            replacement_field_ref: 'work_log.bad_col',
          },
        },
        artifact_card: {
          title: 'BI 查询结果',
          status: 'ready',
          summary_for_chat: '已自动修复并完成查询',
          primary_ref: { ref_id: 'artifact:result-1', ref_type: 'result' },
          related_refs: [
            { ref_id: 'artifact:repair-plan-1', ref_type: 'repair_plan', label: 'RepairPlan' },
          ],
          actions: [
            { action_id: 'view', label: '查看详情', payload_ref: 'artifact:result-1', enabled: true },
          ],
          preview_payload: {
            patch: { field: 'bad_col' },
            raw_sql: 'select bad_col from work_log',
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯 2024 年工作日志' }));
    const custom = chunks.at(-1).metadata.custom;

    expect(custom.repairPlan).toMatchObject({
      summary: '按业务口径自动修复字段引用。',
      status: 'patch_applied',
      failureClass: 'FIELD_NOT_FOUND',
      repairPlanRef: 'artifact:repair-plan-1',
      confidenceBand: 'high',
    });
    expect(custom.repairTimeline.map((item) => item.eventType)).toEqual([
      'repair.evaluated',
      'repair.plan_created',
      'repair.rerun_started',
      'repair.patch_applied',
    ]);
    expect(custom.taskTimeline.map((item) => item.type)).toContain('repair_patch');
    expect(custom.taskTimeline.filter((item) => item.type === 'repair_patch')).toHaveLength(1);
    expect(custom.artifactCard.related_refs).toEqual([
      { ref_id: 'artifact:repair-plan-1', ref_type: 'repair_plan', label: 'RepairPlan' },
    ]);
    expect(custom.artifactCard.actions).toEqual([
      { action_type: 'view', label: '查看详情', ref: 'artifact:result-1', disabled: false },
    ]);
    expect(custom.artifactCard.preview_payload).toBeNull();
    expect(JSON.stringify(custom)).not.toMatch(/bad_col|work_log|raw_sql|select/i);
  });

  it('maps repair_patch graph step into business timeline without internal patch body', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        type: 'step',
        node: 'repair_patch',
        status: 'done',
        repair_patch_summary: {
          repair_strategy: '按业务口径自动修复字段引用。',
          failure_class: 'FIELD_NOT_FOUND',
          confidence_band: 'high',
        },
        repair_patch: {
          trace_only_metadata: {
            replacement_field_ref: 'work_log.bad_col',
          },
        },
      },
      {
        type: 'final',
        answer: '已完成查询。',
        conversation_id: 42,
        message_id: 99,
        result_ref: 'artifact:result-1',
        repair_plan_ref: 'artifact:repair-plan-1',
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询杨凯 2024 年工作日志' }));
    const final = chunks.at(-1);

    expect(final.content.some((part) => part.type === 'reasoning' && /自动修复/.test(part.text))).toBe(true);
    expect(final.metadata.custom.taskTimeline.map((item) => item.type)).toContain('repair_patch');
    expect(JSON.stringify(final.metadata.custom)).not.toMatch(/bad_col|work_log|replacement_field_ref/i);
  });

  it('projects handoff, tool groups and timing into assistant-ui parts with safe metadata', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.handoff.started',
          task_id: 'task-p3',
          trace_id: 'trace-p3',
          payload: {
            from_agent: 'agent_team_leader',
            to_agent: 'bi_agent',
            summary: '已转交 BI Agent 处理问数任务',
            reason: '需要查询数据集',
            timing: { elapsed_ms: 120 },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'tool_call.started',
          task_id: 'task-p3',
          trace_id: 'trace-p3',
          payload: {
            tool_name: 'dataset_query',
            tool_call_id: 'tool-p3',
            agent: 'bi_agent',
            summary: '正在查询数据集',
            timing: { started_at: '2026-07-03T10:00:00Z' },
            query_plan: { sql: 'SELECT secret_col FROM hidden_table' },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'tool_call.completed',
          task_id: 'task-p3',
          trace_id: 'trace-p3',
          payload: {
            tool_name: 'dataset_query',
            tool_call_id: 'tool-p3',
            agent: 'bi_agent',
            summary: '已完成数据集查询',
            artifact_ref: 'artifact:tool-safe',
            checkpoint_ref: 'checkpoint:tool-safe',
            row_count: 42,
            timing: { started_at: '2026-07-03T10:00:00Z', ended_at: '2026-07-03T10:00:01Z', elapsed_ms: 1000 },
            schema: { fields: ['secret_col'] },
            rows: [{ secret_col: 'raw_row_value' }],
            RepairPatch: { replacement_field_ref: 'hidden_table.secret_col' },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          task_id: 'task-p3',
          trace_id: 'trace-p3',
          payload: {
            summary: '查询完成',
            artifact_ref: 'artifact:tool-safe',
            row_count: 42,
            timing: { elapsed_ms: 1400 },
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询销售趋势', threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const reasoning = final.content.find((part) => part.type === 'reasoning' && part.kind === 'handoff');
    const toolPart = final.content.find((part) => part.type === 'tool-call' && part.toolName === 'dataset_query');
    const custom = final.metadata.custom;

    expect(reasoning).toMatchObject({
      kind: 'handoff',
      status: 'running',
      title: 'Agent handoff',
      agent: 'bi_agent',
      timing: { elapsed_ms: 120 },
    });
    expect(toolPart).toMatchObject({
      type: 'tool-call',
      toolCallId: 'tool-p3',
      toolName: 'dataset_query',
      args: {
        kind: 'tool',
        status: 'completed',
        title: 'dataset_query',
        summary: '已完成数据集查询',
        agent: 'bi_agent',
        rowCount: 42,
      },
      result: {
        kind: 'tool',
        status: 'completed',
        refs: {
          artifactRef: 'artifact:tool-safe',
          checkpointRef: 'checkpoint:tool-safe',
        },
        rowCount: 42,
      },
      timing: { elapsed_ms: 1000 },
    });
    expect(custom.toolGroups).toEqual([
      expect.objectContaining({
        kind: 'tool_group',
        status: 'completed',
        agent: 'bi_agent',
        toolName: 'dataset_query',
        rowCount: 42,
        refs: {
          artifactRef: 'artifact:tool-safe',
          checkpointRef: 'checkpoint:tool-safe',
        },
        timing: expect.objectContaining({ elapsed_ms: 1000 }),
      }),
    ]);
    expect(custom.timing).toMatchObject({
      message: { elapsed_ms: 1400 },
      tools: [{ toolName: 'dataset_query', elapsed_ms: 1000 }],
    });
    expect(JSON.stringify(final)).not.toMatch(/SELECT|secret_col|hidden_table|raw_row_value|query_plan|schema|rows|RepairPatch|replacement_field_ref/i);
  });

  it('projects confirmation requests as reasoning parts and safe metadata only', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'confirmation.required',
          task_id: 'task-p4',
          payload: {
            agent: 'bi_agent',
            tool_name: 'dataset_query',
            summary: '需要确认查询范围',
            dataset_id: 7,
            timing: { elapsed_ms: 320 },
            schema: { fields: ['secret_col'] },
            raw_rows: [{ secret_col: 'raw' }],
          },
        },
      },
      {
        type: 'final',
        answer: '请确认查询范围后继续。',
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询销售趋势', threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const confirmation = final.content.find((part) => part.type === 'reasoning' && part.kind === 'confirmation');

    expect(confirmation).toMatchObject({
      kind: 'confirmation',
      status: 'requires_action',
      title: '需要确认',
      summary: '需要确认查询范围',
      agent: 'bi_agent',
      toolName: 'dataset_query',
      timing: { elapsed_ms: 320 },
    });
    expect(final.metadata.custom.confirmations).toEqual([
      expect.objectContaining({
        kind: 'confirmation',
        status: 'requires_action',
        summary: '需要确认查询范围',
        agent: 'bi_agent',
        toolName: 'dataset_query',
      }),
    ]);
    expect(JSON.stringify(final)).not.toMatch(/secret_col|schema|raw_rows/i);
  });

  it('projects worker HITL confirmation route ids for UI actions', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'confirmation.required',
          task_id: 'task-hitl',
          payload: {
            agent: 'bi-worker',
            worker_session_id: 'worker-session-1',
            worker_agent_id: 'worker-agent-1',
            reply_id: 'reply-1',
            tool_name: 'Glob',
            tool_call_id: 'call-1',
            summary: 'bi-worker 正在等待确认工具调用 Glob。',
            tool_calls: [
              {
                id: 'call-1',
                name: 'Glob',
                input: '{"pattern":"**/*","path":"/tmp/private"}',
                state: 'asking',
              },
            ],
          },
        },
      },
      {
        type: 'final',
        answer: '需要确认后继续。',
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '查询销售趋势', threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const confirmation = final.metadata.custom.confirmations[0];

    expect(confirmation).toMatchObject({
      kind: 'confirmation',
      status: 'requires_action',
      agent: 'bi-worker',
      workerSessionId: 'worker-session-1',
      workerAgentId: 'worker-agent-1',
      replyId: 'reply-1',
      toolName: 'Glob',
      toolCallId: 'call-1',
    });
    expect(confirmation.toolCalls).toEqual([{ id: 'call-1', name: 'Glob', state: 'asking' }]);
    const encoded = JSON.stringify(final);
    expect(encoded).not.toMatch(/pattern|input/i);
    expect(encoded).not.toContain('/tmp/private');
  });

  it('projects stage-4 tool-call contract fields (status enum, agentRole, workerSessionId, columnCount) and blocks SQL/schema/raw_rows/query_plan in tool part', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'tool_call.started',
          task_id: 'task-stage3',
          payload: {
            tool_name: 'datalogue_execute_query_plan_bundle',
            tool_call_id: 'bundle-1',
            agent: 'bi-worker',
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-42',
            reply_id: 'reply-42',
            summary: '正在执行 Query Plan Bundle',
            // 下列字段是控制面数据，必须被 chat-adapter 拒入 args/result。
            sql: 'SELECT secret_col FROM hidden_table',
            schema: { tables: ['hidden_table'] },
            raw_rows: [{ secret_col: 'raw' }],
            query_plan: { steps: [{ kind: 'sql', sql: 'SELECT secret_col FROM hidden_table' }] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'tool_call.completed',
          task_id: 'task-stage3',
          payload: {
            tool_name: 'datalogue_execute_query_plan_bundle',
            tool_call_id: 'bundle-1',
            agent: 'bi-worker',
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-42',
            reply_id: 'reply-42',
            summary: '已完成 Query Plan Bundle',
            artifact_ref: 'artifact:bundle-1',
            row_count: 10,
            column_count: 5,
            timing: { elapsed_ms: 800 },
            // 后端偶尔会把控制面 payload 一起 flush 出来；前端必须一票拒入。
            sql: 'SELECT secret_col FROM hidden_table',
            schema: { tables: ['hidden_table'] },
            raw_rows: [{ secret_col: 'raw' }],
            query_plan: { steps: [{ kind: 'sql', sql: 'SELECT secret_col FROM hidden_table' }] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '查询完成', artifact_ref: 'artifact:bundle-1', row_count: 10 },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '统计销售', threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const toolPart = final.content.find((part) => part.type === 'tool-call' && part.toolCallId === 'bundle-1');

    // 阶段 4 契约字段
    expect(toolPart).toMatchObject({
      type: 'tool-call',
      toolCallId: 'bundle-1',
      toolName: 'datalogue_execute_query_plan_bundle',
      status: 'complete',
      agentRole: 'worker',
      agentName: 'BI Worker',
      workerSessionId: 'worker-session-42',
      replyId: 'reply-42',
    });
    expect(toolPart.args).toEqual(
      expect.objectContaining({
        toolName: 'datalogue_execute_query_plan_bundle',
        agentRole: 'worker',
        workerSessionId: 'worker-session-42',
        rowCount: 10,
        columnCount: 5,
      }),
    );
    expect(toolPart.result).toEqual(
      expect.objectContaining({ kind: 'tool', status: 'completed', rowCount: 10, columnCount: 5 }),
    );
    expect(typeof toolPart.argsText).toBe('string');
    // 关键：args / argsText / result 都不应携带 sql/schema/raw_rows/query_plan。
    const toolPartEncoded = JSON.stringify(toolPart);
    expect(toolPartEncoded).not.toMatch(/select|secret_col|hidden_table|raw_rows?/i);
    // tool 名 datalogue_execute_query_plan_bundle 合法包含 query_plan 子串；只拦截字段名。
    expect(toolPartEncoded).not.toMatch(/"schema"\s*:/);
    expect(toolPartEncoded).not.toMatch(/"query_plan"\s*:/);

    // group 里也不能泄漏。
    const group = final.metadata.custom.toolGroups.find((g) => g.groupId === 'worker:worker-session-42');
    expect(group).toBeTruthy();
    expect(group).toMatchObject({
      agentRole: 'worker',
      workerSessionId: 'worker-session-42',
      toolName: 'datalogue_execute_query_plan_bundle',
      rowCount: 10,
      columnCount: 5,
    });
    expect(JSON.stringify(group)).not.toMatch(/select|secret_col|hidden_table|raw_rows?/i);
    expect(JSON.stringify(group)).not.toMatch(/"schema"\s*:/);
    expect(JSON.stringify(group)).not.toMatch(/"query_plan"\s*:/);
  });

  it('maps running tool_call_started to status=running with args but no result', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'tool_call.started',
          task_id: 'task-running',
          payload: {
            tool_name: 'dataset_query',
            tool_call_id: 'run-1',
            agent: 'bi_agent',
            summary: '正在查询',
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const streamingChunk = chunks[chunks.length - 1];
    const toolPart = streamingChunk.content.find((part) => part.type === 'tool-call' && part.toolCallId === 'run-1');
    expect(toolPart).toMatchObject({ status: 'running', toolCallId: 'run-1' });
    expect(toolPart.result).toBeUndefined();
  });

  it('maps tool_call.failed to status=error with isError flag', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'tool_call.failed',
          task_id: 'task-failed',
          payload: {
            tool_name: 'dataset_query',
            tool_call_id: 'fail-1',
            agent: 'bi_agent',
            summary: '查询失败',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '任务失败。' },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const toolPart = final.content.find((part) => part.type === 'tool-call' && part.toolCallId === 'fail-1');
    expect(toolPart).toMatchObject({ status: 'error', isError: true, toolCallId: 'fail-1' });
    expect(toolPart.result).toBeTruthy();
  });

  it('folds confirmation event with toolCallId into a tool-call part with status=requires_action', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'tool_call.started',
          task_id: 'task-hitl',
          payload: {
            tool_name: 'Glob',
            tool_call_id: 'call-hitl-1',
            agent: 'bi-worker',
            agent_role: 'worker',
            worker_session_id: 'worker-session-hitl',
            reply_id: 'reply-hitl',
            summary: 'Worker 正在准备工具调用。',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'confirmation.required',
          task_id: 'task-hitl',
          payload: {
            agent: 'bi-worker',
            worker_session_id: 'worker-session-hitl',
            reply_id: 'reply-hitl',
            tool_name: 'Glob',
            tool_call_id: 'call-hitl-1',
            summary: '需要确认工具调用。',
            schema: { tables: ['hidden_table'] },
            raw_rows: [{ x: 1 }],
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: { summary: '等待人工确认。' },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const toolPart = final.content.find((part) => part.type === 'tool-call' && part.toolCallId === 'call-hitl-1');
    expect(toolPart).toMatchObject({
      status: 'requires_action',
      toolName: 'Glob',
      agentRole: 'worker',
      workerSessionId: 'worker-session-hitl',
      replyId: 'reply-hitl',
    });
    expect(JSON.stringify(toolPart)).not.toMatch(/schema|raw_rows?/i);
  });

  it('emits DataMessagePart entries for artifactCard and candidateDatasets while excluding unsafe fields', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'clarification.required',
          payload: {
            route_decision: {
              decision: 'ambiguous',
              candidates: [
                { dataset_id: 1, dataset_name: '销售明细', reason: '与销售趋势相关' },
                { dataset_id: 2, dataset_name: '订单明细', reason: '包含订单数据' },
              ],
            },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '请选择要查询的数据集',
            artifact_ref: 'artifact:from-data-ui',
            row_count: 3,
            original_question: '统计销售趋势',
            route_decision: {
              decision: 'ambiguous',
              candidates: [
                { dataset_id: 1, dataset_name: '销售明细', reason: '与销售趋势相关' },
                { dataset_id: 2, dataset_name: '订单明细', reason: '包含订单数据' },
              ],
            },
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const dataParts = final.content.filter((part) => part.type === 'data');
    const names = dataParts.map((part) => part.name);
    expect(names).toContain('datalogue-artifact-card');
    expect(names).toContain('datalogue-candidate-datasets');
    const candidate = dataParts.find((part) => part.name === 'datalogue-candidate-datasets');
    expect(candidate.data.candidates.map((c) => c.dataset_name)).toEqual(['销售明细', '订单明细']);
    // DataMessagePart 自然会包含 primary_ref / dataset_name 等业务字段；控制面字段不应出现。
    expect(JSON.stringify(dataParts)).not.toMatch(/raw_rows?|raw_sql|schema=|repair_patch|query_plan|checkpoint:/i);
  });

  it('aggregates sub-agent messages by workerSessionId with reasoning + tool-call parts and blocks SQL/schema/raw_rows/query_plan', async () => {
    streamAgentTeamTask.mockReturnValue(events([
      {
        event_envelope: {
          event_type: 'agent.handoff.started',
          task_id: 'task-multiagent',
          payload: {
            from_agent: 'leader',
            to_agent: 'bi-worker',
            summary: '已将任务交给 BI Worker',
            worker_session_id: 'worker-session-A',
            reply_id: 'reply-A',
            sql: 'SELECT secret_col FROM hidden_table',
            schema: { fields: ['secret_col'] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-multiagent',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-A',
            reply_id: 'reply-A',
            phase: 'dataset_match',
            status: 'running',
            title: '数据集匹配',
            summary: '正在筛选候选数据集。',
            raw_rows: [{ x: 1 }],
            query_plan: { steps: [] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'tool_call.started',
          task_id: 'task-multiagent',
          payload: {
            tool_name: 'datalogue_execute_query_plan_bundle',
            tool_call_id: 'call-A-1',
            agent: 'bi-worker',
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-A',
            reply_id: 'reply-A',
            summary: '正在执行查询计划。',
            sql: 'SELECT secret_col FROM hidden_table',
            schema: { tables: ['hidden_table'] },
            raw_rows: [{ secret_col: 'raw' }],
            query_plan: { steps: [{ kind: 'sql', sql: 'SELECT x FROM y' }] },
          },
        },
      },
      {
        event_envelope: {
          event_type: 'tool_call.completed',
          task_id: 'task-multiagent',
          payload: {
            tool_name: 'datalogue_execute_query_plan_bundle',
            tool_call_id: 'call-A-1',
            agent: 'bi-worker',
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-A',
            reply_id: 'reply-A',
            summary: '已完成查询。',
            artifact_ref: 'artifact:A',
            row_count: 10,
            column_count: 3,
          },
        },
      },
      // 第二个 worker session：确保聚合按 workerSessionId 而非 reply/agent 名混淆。
      {
        event_envelope: {
          event_type: 'agent.progress',
          task_id: 'task-multiagent',
          payload: {
            agent_role: 'worker',
            agent_name: 'BI Worker',
            worker_session_id: 'worker-session-B',
            reply_id: 'reply-B',
            phase: 'thinking',
            status: 'running',
            title: 'BI Worker 思考中',
            summary: '正在分析问题。',
          },
        },
      },
      {
        event_envelope: {
          event_type: 'message.completed',
          payload: {
            summary: '任务完成。',
            answer: '销售总额为 100 万。',
            artifact_ref: 'artifact:A',
            row_count: 10,
          },
        },
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: 7 } });
    const chunks = await collectRun(adapter, runInput({ question: '统计销售', threadId: 'local-thread' }));
    const final = chunks.at(-1);
    const subAgentMessages = final.metadata.custom.subAgentMessages;

    expect(Array.isArray(subAgentMessages)).toBe(true);
    // 两个 workerSessionId → 两条 sub-agent message
    expect(subAgentMessages.map((m) => m.metadata.custom.workerSessionId).sort()).toEqual([
      'worker-session-A',
      'worker-session-B',
    ]);

    const messageA = subAgentMessages.find((m) => m.metadata.custom.workerSessionId === 'worker-session-A');
    expect(messageA).toMatchObject({
      role: 'assistant',
      status: { type: 'complete', reason: 'stop' },
      metadata: {
        custom: {
          workerSessionId: 'worker-session-A',
          agentRole: 'worker',
          agentName: 'BI Worker',
        },
      },
    });
    // 至少一条 reasoning + 一条 tool-call
    const messageATypes = messageA.content.map((part) => part.type);
    expect(messageATypes).toContain('reasoning');
    expect(messageATypes).toContain('tool-call');
    const messageAToolPart = messageA.content.find((part) => part.type === 'tool-call');
    expect(messageAToolPart).toMatchObject({
      toolCallId: 'call-A-1',
      status: 'complete',
      agentRole: 'worker',
      workerSessionId: 'worker-session-A',
    });

    // ToolCallMessagePart.messages 挂载：worker A 的最后一个 tool-call 应带 messages
    const outerToolPart = final.content.find(
      (part) => part.type === 'tool-call' && part.toolCallId === 'call-A-1',
    );
    expect(Array.isArray(outerToolPart.messages)).toBe(true);
    expect(outerToolPart.messages).toHaveLength(1);
    expect(outerToolPart.messages[0].metadata.custom.workerSessionId).toBe('worker-session-A');

    // 安全：sub-agent messages 序列化后不应出现 SQL/schema/raw_rows/query_plan 字段
    const encoded = JSON.stringify(subAgentMessages);
    expect(encoded).not.toMatch(/select |secret_col|hidden_table|raw_rows?/i);
    expect(encoded).not.toMatch(/"schema"\s*:/);
    expect(encoded).not.toMatch(/"query_plan"\s*:/);
    expect(encoded).not.toMatch(/"sql"\s*:/);
  });
});

// chat-adapter.test.js
// 验证 Chat adapter 将后端 SSE/final payload 收敛为 C-ready 消息 metadata。

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeChatAdapter, buildBusinessSessionId } from './chat-adapter';
import { buildHistoryMessageCustom } from './thread-list-adapter';

vi.mock('./agentic-direct-query-api', () => ({
  runAgenticDirectQuery: vi.fn(),
  streamAgenticDirectQuery: vi.fn(),
}));

vi.mock('./agentic-shell-task-api', () => ({
  streamAgenticShellTask: vi.fn(),
}));

vi.mock('../api/client', () => ({
  getArtifact: vi.fn(),
}));

vi.mock('./thread-list-adapter', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    resolveRemoteId: vi.fn(() => null),
    resolveRecentInitializedRemoteId: vi.fn(() => null),
  };
});

const { streamAgenticShellTask } = await import('./agentic-shell-task-api');
const { runAgenticDirectQuery, streamAgenticDirectQuery } = await import('./agentic-direct-query-api');
const { getArtifact } = await import('../api/client');

async function* events(items) {
  for (const item of items) {
    yield item;
  }
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
    getArtifact.mockResolvedValue(null);
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = null;
    window.history.pushState({}, '', '/chat');
  });

  it('uses AgenticLeadAgent direct-query as the default chat send path', async () => {
    streamAgenticDirectQuery.mockReturnValue(events([
      {
        type: 'agent_message',
        agent: 'agentic_lead_agent',
        role: 'user',
        title: 'AgenticLeadAgent 输入',
        content: '正在判断任务类型并选择业务 Agent。',
      },
      {
        type: 'agent_message',
        agent: 'agentic_lead_agent',
        role: 'assistant',
        title: 'AgenticLeadAgent 返回',
        content: '已选择 BI Agent 执行问数。',
      },
      {
        type: 'agent_event',
        agent: 'bi_agent',
        title: 'BI Agent 执行',
        content: '正在通过 AgentScope 工具链查询数据集。',
      },
      {
        type: 'final',
        answer: '双周会议共有 100 条记录。',
        status: 'completed',
        selected_agent: 'bi_agent',
        result_ref: 'artifact:direct-1',
        artifact_ref: 'artifact:direct-1',
        checkpoint_ref: 'checkpoint:direct-1',
        row_count: 100,
        column_count: 67,
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 12 } });
    const chunks = await collectRun(adapter, runInput({
      question: '统计双周会议数据记录数量',
      threadId: 'local-thread',
    }));
    const finalChunk = chunks.at(-1);

    expect(streamAgenticDirectQuery).toHaveBeenCalledWith(
      {
        question: '统计双周会议数据记录数量',
        dataset_id: 12,
        conversation_id: null,
        trace_id: expect.stringMatching(/^chat-direct-/),
      },
      expect.any(Object),
    );
    expect(runAgenticDirectQuery).not.toHaveBeenCalled();
    expect(streamAgenticShellTask).not.toHaveBeenCalled();
    expect(chunks[0].content.some((part) => part.type === 'reasoning')).toBe(true);
    expect(finalChunk).toMatchObject({
      status: { type: 'complete', reason: 'stop' },
      content: expect.arrayContaining([{ type: 'text', text: '双周会议共有 100 条记录。' }]),
    });
    expect(finalChunk.content.filter((part) => part.type === 'reasoning')).toHaveLength(3);
    expect(finalChunk.metadata.custom).toMatchObject({
      resultRef: 'artifact:direct-1',
      artifactCard: null,
    });
    expect(JSON.stringify(finalChunk.metadata.custom)).not.toMatch(/checkpoint:direct-1|\bSELECT\b|raw_rows|schema_context/i);
  });

  it('passes the selected model config id to direct-query when the composer chooses a model', async () => {
    streamAgenticDirectQuery.mockReturnValue(events([
      {
        type: 'final',
        answer: '已完成模型指定查询。',
        status: 'completed',
        selected_agent: 'bi_agent',
      },
    ]));

    const adapter = makeChatAdapter({
      datasetIdRef: { current: 12 },
      modelConfigIdRef: { current: 8 },
    });
    await collectRun(adapter, runInput({
      question: '用指定模型查询销售趋势',
      threadId: 'local-thread',
    }));

    expect(streamAgenticDirectQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '用指定模型查询销售趋势',
        dataset_id: 12,
        model_config_id: 8,
      }),
      expect.any(Object),
    );
    expect(streamAgenticShellTask).not.toHaveBeenCalled();
  });

  it('routes missing dataset through Agentic Shell so BI Agent can choose it', async () => {
    streamAgenticShellTask.mockReturnValue(events([
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

    expect(streamAgenticShellTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        question: '查询销售趋势',
        dataset_id: null,
      }),
      expect.any(Object),
    );
    expect(streamAgenticDirectQuery).not.toHaveBeenCalled();
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

  it('passes the selected model config id through Agentic Shell when dataset selection is needed', async () => {
    streamAgenticShellTask.mockReturnValue(events([
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

    expect(streamAgenticShellTask).toHaveBeenCalledWith(
      expect.objectContaining({
        question: '查询销售趋势',
        dataset_id: null,
        model_config_id: 8,
      }),
      expect.any(Object),
    );
    expect(streamAgenticDirectQuery).not.toHaveBeenCalled();
  });

  it('renders direct-query artifact rows as a markdown table in the assistant text part', async () => {
    streamAgenticDirectQuery.mockReturnValue(events([
      {
        type: 'final',
        answer: '您的查询“查询杨凯2024年日志”已完成。系统已返回 100 条 记录，每条记录包含 48 个 数据字段。',
        status: 'completed',
        selected_agent: 'bi_agent',
        result_ref: 'artifact:direct-table',
        artifact_ref: 'artifact:direct-table',
        row_count: 2,
        column_count: 3,
      },
    ]));
    getArtifact.mockResolvedValueOnce({
      kind: 'sql_result',
      content_json: {
        columns: ['姓名', '日期', '工作内容'],
        rows: [
          { 姓名: '杨凯', 日期: '2024-01-01', 工作内容: '完成问数链路联调' },
          { 姓名: '杨凯', 日期: '2024-01-02', 工作内容: '修复 Markdown 表格展示' },
        ],
        row_count: 2,
      },
    });

    const adapter = makeChatAdapter({ datasetIdRef: { current: 12 } });
    const chunks = await collectRun(adapter, runInput({
      question: '查询杨凯2024年日志',
      threadId: 'local-thread',
    }));
    const finalChunk = chunks.at(-1);
    const text = finalChunk.content.find((part) => part.type === 'text')?.text || '';

    expect(getArtifact).toHaveBeenCalledWith('artifact:direct-table');
    expect(text).toContain('| 姓名 | 日期 | 工作内容 |');
    expect(text).toContain('| 杨凯 | 2024-01-01 | 完成问数链路联调 |');
    expect(text).toContain('| 杨凯 | 2024-01-02 | 修复 Markdown 表格展示 |');
    expect(text).not.toContain('您的查询“查询杨凯2024年日志”已完成');
    expect(text).not.toContain('📊');
    expect(text).not.toContain('📂');
  });

  it('does not fall back to generic completed text when direct-query final answer is empty', async () => {
    streamAgenticDirectQuery.mockReturnValue(events([
      {
        type: 'final',
        answer: '',
        status: 'completed',
        selected_agent: 'bi_agent',
        result_ref: 'artifact:direct-empty',
        artifact_ref: 'artifact:direct-empty',
        row_count: 1,
        column_count: 2,
      },
    ]));

    const adapter = makeChatAdapter({ datasetIdRef: { current: 12 } });
    const chunks = await collectRun(adapter, runInput({
      question: '统计合同总金额',
      threadId: 'local-thread',
    }));
    const finalChunk = chunks.at(-1);
    const text = finalChunk.content.find((part) => part.type === 'text')?.text || '';

    expect(text).toMatch(/^## 查询结果/);
    expect(text).toContain('- **数据规模**：返回 1 行，2 列');
    expect(text).not.toContain('结果入口');
    expect(text).not.toContain('artifact:direct-empty');
    expect(text).not.toBe('查询已完成。');
  });

  it('builds stable business session ids from conversation or thread context', () => {
    expect(buildBusinessSessionId({ conversationId: 12, threadId: 'local', fallbackSessionId: 'fallback' }))
      .toBe('conversation-12');
    expect(buildBusinessSessionId({ conversationId: null, threadId: 'thread/abc', fallbackSessionId: 'fallback' }))
      .toBe('assistant-thread-thread-abc');
    expect(buildBusinessSessionId({ conversationId: null, threadId: '', fallbackSessionId: 'fallback' }))
      .toBe('fallback');
  });

  it('converts route, step and final events into timeline and artifact metadata', async () => {
    streamAgenticShellTask.mockReturnValue(events([
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

    expect(streamAgenticShellTask).toHaveBeenCalledWith(
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
    streamAgenticShellTask.mockReturnValue(events([
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

  it('maps Agentic Shell artifact refs from message completed envelopes into result metadata', async () => {
    streamAgenticShellTask.mockReturnValue(events([
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
    expect(JSON.stringify(final.content)).not.toMatch(/checkpoint:safe|artifact:safe/i);
  });

  it('exposes only business-level candidate dataset confirmation metadata', async () => {
    streamAgenticShellTask.mockReturnValue(events([
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
      },
    ]));

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    const chunks = await collectRun(adapter);
    const candidateDatasets = chunks.at(-1).metadata.custom.candidateDatasets;

    expect(candidateDatasets).toEqual({
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
    streamAgenticShellTask.mockReturnValue(events([{ type: 'final', answer: '已确认' }]));
    window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__ = {
      selected_dataset_id: 7,
      selected_text: '销售明细',
    };

    const adapter = makeChatAdapter({ transport: 'stream', datasetIdRef: { current: null } });
    await collectRun(adapter);

    expect(streamAgenticShellTask).toHaveBeenCalledWith(
      expect.objectContaining({
        task_source: 'chat',
        task_type: 'bi_query',
        dataset_id: 7,
        clarification_response: {
          selected_dataset_id: 7,
          selected_text: '销售明细',
        },
      }),
      expect.any(Object),
    );
    expect(window.__DATALOGUE_PENDING_CLARIFICATION_RESPONSE__).toBeNull();
  });

  it('passes pending workbench retry request to chat stream once and clears it', async () => {
    streamAgenticShellTask.mockReturnValue(events([{ type: 'final', answer: '已从检查点恢复' }]));
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

    expect(streamAgenticShellTask).toHaveBeenCalledWith(
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
    streamAgenticShellTask.mockReturnValue(events([
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
    streamAgenticShellTask.mockReturnValue(events([
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
    streamAgenticShellTask.mockReturnValue(events([
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
    streamAgenticShellTask.mockReturnValue(events([
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
});

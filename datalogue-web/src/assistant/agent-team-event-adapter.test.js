import { describe, expect, it } from 'vitest';

import { agentTeamEnvelopeToChatEvent } from './agent-team-event-adapter.js';

describe('agentTeamEnvelopeToChatEvent', () => {
  it('rejects legacy non-envelope events instead of bypassing safety projection', () => {
    const event = agentTeamEnvelopeToChatEvent({
      type: 'final',
      answer: 'SELECT secret_col FROM hidden_table',
      raw_rows: [{ secret_col: 'raw' }],
    });

    expect(event).toBeNull();
  });

  it('maps message.delta to token event', () => {
    const event = agentTeamEnvelopeToChatEvent({
      event_envelope: {
        event_type: 'message.delta',
        payload: { content: '合同总金额' },
      },
    });

    expect(event).toEqual({ type: 'token', content: '合同总金额' });
  });

  it('maps task.completed to final event', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'message.completed',
        payload: { summary: '完成' },
        legacy_payload: { type: 'final', answer: '完成' },
      },
    });

    expect(event.type).toBe('final');
    expect(event.task_id).toBe('task-1');
  });

  it('keeps original question on dataset confirmation final payload', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'message.completed',
        payload: {
          summary: '请选择数据集',
          original_question: '查询杨凯2025年工作日志',
          route_decision: {
            decision: 'ambiguous',
            candidates: [{ dataset_id: 10, dataset_name: '生产经营管理系统日志数据集' }],
          },
        },
      },
    });

    expect(event).toMatchObject({
      type: 'final',
      answer: '请选择数据集',
      original_question: '查询杨凯2025年工作日志',
      route_decision: {
        decision: 'ambiguous',
      },
    });
  });

  it('does not turn task.completed into a final answer payload', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'task.completed',
        payload: { summary: 'Agent Team 任务已完成。' },
      },
    });

    expect(event.type).toBe('step');
    expect(event.node).toBe('task.completed');
  });

  it('keeps repair envelopes as repair events', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'repair.plan_created',
        payload: { summary: '已生成自动修复方案。' },
      },
    });

    expect(event.type).toBe('repair');
    expect(event.event_envelope.event_type).toBe('repair.plan_created');
  });

  it('normalizes agent handoff envelopes into safe multi-agent events', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-1',
      event_envelope: {
        event_type: 'agent.handoff.started',
        task_id: 'task-1',
        trace_id: 'trace-1',
        payload: {
          from_agent: 'agent_team_leader',
          to_agent: 'bi_agent',
          reason: '需要进入问数执行',
          summary: '已将任务交给 BI Agent',
          raw_sql: 'SELECT secret_col FROM hidden_table',
          schema: { fields: ['secret_col'] },
        },
      },
    });

    expect(event).toMatchObject({
      type: 'agent_handoff',
      kind: 'handoff',
      status: 'running',
      agent: 'bi_agent',
      from_agent: 'agent_team_leader',
      to_agent: 'bi_agent',
      title: 'Agent handoff',
      summary: '已将任务交给 BI Agent',
      task_id: 'task-1',
      trace_id: 'trace-1',
    });
    expect(JSON.stringify(event)).not.toMatch(/SELECT|secret_col|hidden_table|schema|raw_sql/i);
  });

  it('normalizes tool lifecycle envelopes with timing, refs and row count only', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-2',
      event_envelope: {
        event_type: 'tool_call.completed',
        task_id: 'task-2',
        trace_id: 'trace-2',
        payload: {
          tool_name: 'dataset_query',
          tool_call_id: 'tool-1',
          agent: 'bi_agent',
          summary: '已完成数据集查询',
          artifact_ref: 'artifact:safe',
          checkpoint_ref: 'checkpoint:safe',
          row_count: 42,
          timing: { started_at: '2026-07-03T10:00:00Z', elapsed_ms: 1280 },
          query_plan: { sql: 'SELECT secret_col FROM hidden_table' },
          rows: [{ secret_col: 'raw' }],
          RepairPatch: { replacement_field_ref: 'hidden_table.secret_col' },
        },
      },
    });

    expect(event).toMatchObject({
      type: 'tool_call',
      kind: 'tool',
      status: 'completed',
      agent: 'bi_agent',
      toolName: 'dataset_query',
      toolCallId: 'tool-1',
      summary: '已完成数据集查询',
      refs: {
        artifactRef: 'artifact:safe',
        checkpointRef: 'checkpoint:safe',
      },
      rowCount: 42,
      timing: { started_at: '2026-07-03T10:00:00Z', elapsed_ms: 1280 },
    });
    expect(JSON.stringify(event)).not.toMatch(/SELECT|secret_col|hidden_table|query_plan|rows|RepairPatch/i);
  });

  it('normalizes confirmation envelopes without leaking schema or raw rows', () => {
    const event = agentTeamEnvelopeToChatEvent({
      event_envelope: {
        event_type: 'confirmation.required',
        payload: {
          agent: 'bi_agent',
          tool_name: 'dataset_query',
          summary: '请确认是否继续查询',
          dataset_id: 7,
          timing: { elapsed_ms: 300 },
          schema: { fields: ['secret_col'] },
          raw_rows: [{ secret_col: 'raw' }],
        },
      },
    });

    expect(event).toMatchObject({
      type: 'confirmation',
      kind: 'confirmation',
      status: 'requires_action',
      agent: 'bi_agent',
      toolName: 'dataset_query',
      summary: '请确认是否继续查询',
      timing: { elapsed_ms: 300 },
    });
    expect(JSON.stringify(event)).not.toMatch(/secret_col|schema|raw_rows/i);
  });

  it('normalizes subagent HITL confirmation route fields without leaking tool input', () => {
    const event = agentTeamEnvelopeToChatEvent({
      task_id: 'task-hitl',
      event_envelope: {
        event_type: 'confirmation.required',
        task_id: 'task-hitl',
        trace_id: 'trace-hitl',
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
    });

    expect(event).toMatchObject({
      type: 'confirmation',
      kind: 'confirmation',
      status: 'requires_action',
      agent: 'bi-worker',
      workerSessionId: 'worker-session-1',
      workerAgentId: 'worker-agent-1',
      replyId: 'reply-1',
      toolName: 'Glob',
      toolCallId: 'call-1',
      summary: 'bi-worker 正在等待确认工具调用 Glob。',
    });
    expect(event.toolCalls).toEqual([{ id: 'call-1', name: 'Glob', state: 'asking' }]);
    const encoded = JSON.stringify(event);
    expect(encoded).not.toMatch(/pattern|input/i);
    expect(encoded).not.toContain('/tmp/private');
  });
});

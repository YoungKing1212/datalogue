import { describe, expect, it } from 'vitest';

import { buildHistoryMessageCustom } from '../../../src/features/chat/thread-list-adapter';

describe('artifact metadata custom fields', () => {
  it('maps result/report refs from subagent tool metadata', () => {
    const custom = buildHistoryMessageCustom({
      id: 42,
      response_metadata: {
        subagent_tool_result: {
          status: 'ok',
          dataset_id: 1,
          result_ref: 'artifact:result-1',
          report_ref: 'artifact:report-1',
        },
      },
    });

    expect(custom.resultRef).toBe('artifact:result-1');
    expect(custom.reportRef).toBe('artifact:report-1');
    expect(custom.messageId).toBe(42);
  });

  it('maps fan-out safe visible results', () => {
    const custom = buildHistoryMessageCustom({
      id: 43,
      response_metadata: {
        subagent_tool_results: [
          { status: 'ok', dataset_id: 1, result_ref: 'artifact:r1' },
          { status: 'empty', dataset_id: 2, report_ref: 'artifact:p2' },
        ],
      },
    });

    expect(custom.subagentToolResults).toHaveLength(2);
    expect(custom.subagentToolResults[0].result_ref).toBe('artifact:r1');
    expect(custom.subagentToolResults[1].report_ref).toBe('artifact:p2');
  });

  it('does not forge ArtifactCard for legacy result refs', () => {
    const custom = buildHistoryMessageCustom({
      id: 44,
      response_metadata: {
        result_ref: 'artifact:legacy-result',
        report_ref: 'artifact:legacy-report',
      },
    });

    expect(custom.resultRef).toBe('artifact:legacy-result');
    expect(custom.reportRef).toBe('artifact:legacy-report');
    expect(custom.artifactCard).toBeNull();
    expect(custom.primaryRef).toBeNull();
    expect(custom.relatedRefs).toBeNull();
  });

  it('maps persisted ArtifactCard refs for new history messages', () => {
    const artifactCard = {
      title: 'BI 查询结果',
      primary_ref: { ref_id: 'artifact:result-1', ref_type: 'result' },
      related_refs: [{ ref_id: 'trace:trace-1', ref_type: 'trace' }],
    };
    const custom = buildHistoryMessageCustom({
      id: 45,
      response_metadata: {
        task_id: 'conv-1-msg-45',
        trace_id: 'trace-1',
        artifact_card: artifactCard,
        primary_ref: artifactCard.primary_ref,
        related_refs: artifactCard.related_refs,
      },
    });

    expect(custom.artifactCard.title).toBe('BI 查询结果');
    expect(custom.artifactCard.primary_ref.ref_id).toBe('artifact:result-1');
    expect(custom.artifactCard.related_refs[0].ref_id).toBe('trace:trace-1');
    expect(custom.primaryRef.ref_id).toBe('artifact:result-1');
    expect(custom.relatedRefs[0].ref_id).toBe('trace:trace-1');
    expect(custom.taskId).toBe('conv-1-msg-45');
    expect(custom.traceId).toBe('trace-1');
  });
});

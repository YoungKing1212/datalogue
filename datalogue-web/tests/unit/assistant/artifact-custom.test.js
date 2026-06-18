import { describe, expect, it } from 'vitest';

import { buildHistoryMessageCustom } from '../../../src/assistant/thread-list-adapter';

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
});

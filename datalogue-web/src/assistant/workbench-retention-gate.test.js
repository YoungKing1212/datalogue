// workbench-retention-gate.test.js
// 验证 Workbench 退役闸门只放行“14 天主路径归零 + Chat 侧详情承接一致”的窗口。

import { describe, expect, it } from 'vitest';

import { evaluateWorkbenchRetentionGate } from './workbench-retention-gate.js';
import {
  buildArtifactDetailExpectedEvent,
  buildArtifactDetailViewEvent,
} from './workbench-retention-events.js';

function buildWindow(overrides = {}) {
  return {
    window_start: '2026-06-01T00:00:00.000Z',
    window_end: '2026-06-15T00:00:00.000Z',
    ui_events: [],
    api_events: [],
    ...overrides,
  };
}

describe('WorkbenchRetentionGate', () => {
  it('rejects retirement when api_workbench_main_path_total is non-zero', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        api_events: [
          {
            api_path: '/api/workbench/thread/conv_1',
            source_kind: 'ordinary_chat_history',
            count: 2,
          },
        ],
        expected_artifact_detail_total: 0,
      }),
    );

    expect(result.pass).toBe(false);
    expect(result.metrics.api_workbench_main_path_total).toBe(2);
    expect(result.metrics.main_path_total).toBe(2);
    expect(result.reasons.join('\n')).toContain('main_path_non_zero');
  });

  it('rejects retirement when ui_workbench_main_path_total is non-zero', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        ui_events: [
          {
            event_name: 'page_view',
            route_path: '/workbench/thread/conv_1',
            source_kind: 'ordinary_chat',
            count: 3,
          },
        ],
        expected_artifact_detail_total: 0,
      }),
    );

    expect(result.pass).toBe(false);
    expect(result.metrics.ui_workbench_main_path_total).toBe(3);
    expect(result.metrics.main_path_total).toBe(3);
    expect(result.reasons.join('\n')).toContain('main_path_non_zero');
  });

  it('allows hidden recovery traffic but excludes it from main_path_total', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        ui_events: [
          {
            event_name: 'page_view',
            route_path: '/workbench/recover/conv_1',
            source_kind: 'hidden_recovery_shell',
            is_hidden_recovery: true,
            count: 4,
          },
          {
            event_name: 'artifact_detail_view',
            route_path: '/chat/conv_1',
            source_kind: 'ordinary_chat',
            artifact_detail_visible: true,
            count: 1,
          },
        ],
        api_events: [
          {
            api_path: '/api/workbench/actions/retry',
            source_kind: 'hidden_recovery_shell',
            is_hidden_recovery: true,
            count: 2,
          },
          {
            api_path: '/api/artifacts/artifact:result-1',
            source_kind: 'ordinary_chat',
            count: 1,
          },
        ],
        expected_artifact_detail_total: 2,
      }),
    );

    expect(result.pass).toBe(true);
    expect(result.metrics.main_path_total).toBe(0);
    expect(result.metrics.api_workbench_recovery_total).toBe(2);
    expect(result.metrics.ui_workbench_recovery_total).toBe(4);
    expect(result.metrics.chat_artifact_detail_total).toBe(2);
  });

  it('passes retirement with standard Chat-side artifact detail events', () => {
    const artifactCard = {
      title: '查询结果',
      actions: [{ action_type: 'view', ref: 'artifact:result-1' }],
    };
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        ui_events: [
          buildArtifactDetailExpectedEvent({
            artifactCard,
            messageId: 'msg-1',
            routePath: '/chat/conv_1',
          }),
          buildArtifactDetailViewEvent({
            artifactRef: 'artifact:result-1',
            messageId: 'msg-1',
            routePath: '/chat/conv_1',
          }),
        ],
      }),
    );

    expect(result.pass).toBe(true);
    expect(result.metrics.expected_artifact_detail_total).toBe(1);
    expect(result.metrics.chat_artifact_detail_total).toBe(1);
  });

  it('does not count workbench-origin detail view events as Chat-side detail coverage', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        ui_events: [
          {
            ...buildArtifactDetailViewEvent({
              artifactRef: 'artifact:result-1',
              messageId: 'msg-1',
              routePath: '/workbench/thread/conv_1',
            }),
            source_kind: 'legacy_mirror',
          },
        ],
        expected_artifact_detail_total: 1,
      }),
    );

    expect(result.pass).toBe(false);
    expect(result.metrics.chat_artifact_detail_total).toBe(0);
    expect(result.reasons.join('\n')).toContain('artifact_detail_mismatch');
  });

  it('requires one full release window of zero main-path traffic before retirement', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        window_end: '2026-06-14T23:59:59.000Z',
        expected_artifact_detail_total: 0,
      }),
    );

    expect(result.pass).toBe(false);
    expect(result.reasons.join('\n')).toContain('window_too_short');
  });

  it('rejects retirement when chat_artifact_detail_total does not match expected_artifact_detail_total', () => {
    const result = evaluateWorkbenchRetentionGate(
      buildWindow({
        ui_events: [
          {
            event_name: 'artifact_detail_view',
            route_path: '/chat/conv_1',
            source_kind: 'ordinary_chat',
            artifact_detail_visible: true,
          },
        ],
        expected_artifact_detail_total: 2,
      }),
    );

    expect(result.pass).toBe(false);
    expect(result.metrics.chat_artifact_detail_total).toBe(1);
    expect(result.metrics.expected_artifact_detail_total).toBe(2);
    expect(result.reasons.join('\n')).toContain('artifact_detail_mismatch');
  });
});

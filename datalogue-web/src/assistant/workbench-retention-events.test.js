// workbench-retention-events.test.js
// 验证 Workbench 退役闸门前端事件口径，确保真实埋点接入时不依赖 Workbench 旧日志倒推。

import { describe, expect, it, vi } from 'vitest';

import {
  RETENTION_UI_EVENT_NAMES,
  WORKBENCH_RETENTION_EVENT_TYPE,
  artifactDetailRefFromCard,
  buildArtifactDetailExpectedEvent,
  buildArtifactDetailViewEvent,
  emitWorkbenchRetentionUiEvent,
  hasExpectedArtifactDetailProjection,
} from './workbench-retention-events.js';

describe('workbench-retention-events', () => {
  it('builds expected detail event only when Chat artifact projection has a readable detail ref', () => {
    const artifactCard = {
      title: '查询结果',
      summary_for_chat: '返回 2 行',
      actions: [
        { action_type: 'copy', label: '复制', ref: 'artifact:result-1' },
        { action_type: 'view', label: '查看详情', ref: 'artifact:result-1' },
      ],
    };

    expect(hasExpectedArtifactDetailProjection(artifactCard)).toBe(true);
    expect(artifactDetailRefFromCard(artifactCard)).toBe('artifact:result-1');
    expect(buildArtifactDetailExpectedEvent({
      artifactCard,
      messageId: 'msg-1',
      routePath: '/chat/conv_1',
    })).toEqual({
      event_name: RETENTION_UI_EVENT_NAMES.artifactDetailExpected,
      route_path: '/chat/conv_1',
      source_kind: 'ordinary_chat',
      artifact_ref: 'artifact:result-1',
      message_id: 'msg-1',
      artifact_detail_expected: true,
      count: 1,
    });
  });

  it('does not treat pure summary card as expected detail', () => {
    const artifactCard = {
      title: '查询摘要',
      summary_for_chat: '仅展示摘要，不提供详情入口',
      actions: [{ action_type: 'copy', label: '复制', ref: 'artifact:result-1' }],
    };

    expect(hasExpectedArtifactDetailProjection(artifactCard)).toBe(false);
    expect(buildArtifactDetailExpectedEvent({ artifactCard })).toBeNull();
  });

  it('builds and emits actual Chat-side detail view event', () => {
    const event = buildArtifactDetailViewEvent({
      artifactRef: 'artifact:result-1',
      messageId: 'msg-1',
      routePath: '/chat/conv_1',
      status: 'opened',
    });
    const listener = vi.fn();
    window.addEventListener(WORKBENCH_RETENTION_EVENT_TYPE, listener);

    expect(event).toEqual({
      event_name: RETENTION_UI_EVENT_NAMES.artifactDetailView,
      route_path: '/chat/conv_1',
      source_kind: 'ordinary_chat',
      artifact_ref: 'artifact:result-1',
      message_id: 'msg-1',
      artifact_detail_visible: true,
      status: 'opened',
      count: 1,
    });
    expect(emitWorkbenchRetentionUiEvent(event)).toBe(true);
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({ detail: event }));

    window.removeEventListener(WORKBENCH_RETENTION_EVENT_TYPE, listener);
  });
});


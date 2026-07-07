// DatalogueActionBar — 消息动作栏的 assistant-ui primitive 壳层。
// 只提供用户可见动作，不暴露 SQL、schema等内部控制面信息。

import React from 'react';
import { ActionBarPrimitive, AuiIf } from '@assistant-ui/react';
import { Icon } from '../components/icons';

function ActionIcon({ name, title, children, ...props }) {
  return (
    <button type="button" className="action-btn" title={title} aria-label={title} {...props}>
      {children || <Icon name={name} />}
    </button>
  );
}

/**
 * DatalogueActionBar — Copy / Reload / Speak / Edit 的可见层。
 * Feedback 先禁用：旧链路依赖 submitMessageFeedback(messageId, action)，需要先定义 assistant-ui message id 与后端反馈契约。
 */
export function DatalogueActionBar({
  className = 'msg-actions',
  autohide = 'not-last',
  visible = false,
  feedbackTitle = '反馈暂未接入',
  feedbackDisabled = true,
  onApprove,
  onReject,
}) {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide={autohide}
      autohideFloat="single-branch"
      className={`${className}${visible ? ' visible' : ''}`}
    >
      <ActionBarPrimitive.Copy asChild copiedDuration={2000}>
        <ActionIcon name="copy" title="复制回答" />
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Reload asChild>
        <ActionIcon name="refresh" title="重新生成" />
      </ActionBarPrimitive.Reload>
      <AuiIf condition={(s) => !s.message.isSpeaking}>
        <ActionBarPrimitive.Speak asChild>
          <ActionIcon name="play" title="朗读" />
        </ActionBarPrimitive.Speak>
      </AuiIf>
      <AuiIf condition={(s) => s.message.isSpeaking}>
        <ActionBarPrimitive.StopSpeaking asChild>
          <ActionIcon name="pause" title="停止朗读" />
        </ActionBarPrimitive.StopSpeaking>
      </AuiIf>
      <ActionBarPrimitive.Edit asChild>
        <ActionIcon name="edit" title="编辑消息" />
      </ActionBarPrimitive.Edit>
      <ActionIcon
        name="thumbs_up"
        title={feedbackTitle || '点赞'}
        disabled={feedbackDisabled}
        aria-disabled={feedbackDisabled}
        onClick={feedbackDisabled ? undefined : onApprove}
      />
      <ActionIcon
        name="thumbs_down"
        title={feedbackTitle || '点踩'}
        disabled={feedbackDisabled}
        aria-disabled={feedbackDisabled}
        onClick={feedbackDisabled ? undefined : onReject}
      />
      {/* TODO: 接入反馈前需要先定义 messageId、反馈动作和后端持久化接口的业务契约。 */}
    </ActionBarPrimitive.Root>
  );
}

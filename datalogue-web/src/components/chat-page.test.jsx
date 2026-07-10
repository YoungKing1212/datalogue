// ChatPage 测试兼容入口：实际测试已迁到 src/features/chat；旧路径只验证 re-export 仍可被历史命令加载。
import { describe, expect, it } from 'vitest';
import { ChatPage } from './chat-page.jsx';

describe('ChatPage legacy test entry', () => {
  it('re-exports ChatPage from the chat feature domain', () => {
    expect(ChatPage).toBeTypeOf('function');
  });
});

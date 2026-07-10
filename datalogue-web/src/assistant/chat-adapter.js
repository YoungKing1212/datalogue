// chat-adapter.js
// 兼容入口：Chat 功能域已迁到 src/features/chat，旧 assistant 路径只保留 re-export，避免一次性改动调用方 import。

export * from '../features/chat/chat-adapter';

import { describe, expect, it } from 'vitest';

import {
  resolveUrlSyncTarget,
  resolveWorkbenchThreadId,
  shouldAcceptResolvedWorkbenchThread,
  shouldSwitchToRouteThread,
} from './chat-page.jsx';

describe('shouldSwitchToRouteThread', () => {
  it('skips route sync when no conversation id is present', () => {
    expect(shouldSwitchToRouteThread(undefined, 'thread-1', '1')).toBe(false);
  });

  it('skips route sync when the main thread already matches the route id', () => {
    expect(shouldSwitchToRouteThread('16', '16', undefined)).toBe(false);
  });

  it('skips route sync when the current thread remote id already matches the route id', () => {
    expect(shouldSwitchToRouteThread('16', 'thread-mapping-16', 16)).toBe(false);
  });

  it('requests route sync when direct URL entry is still on a local draft thread', () => {
    expect(shouldSwitchToRouteThread('16', 'local-draft', undefined)).toBe(true);
  });
});

describe('resolveUrlSyncTarget', () => {
  it('does not let initial runtime state override a direct route', () => {
    expect(resolveUrlSyncTarget({
      routeId: '24',
      remoteId: '21',
      mainThreadChanged: true,
      hasObservedThread: false,
    })).toBeNull();
  });

  it('does not roll back the URL while route-driven switch is pending', () => {
    expect(resolveUrlSyncTarget({
      routeId: '1',
      remoteId: '25',
      mainThreadChanged: false,
      hasObservedThread: true,
    })).toBeNull();
  });

  it('syncs URL when the runtime main thread changes to another persisted conversation', () => {
    expect(resolveUrlSyncTarget({
      routeId: '25',
      remoteId: '1',
      mainThreadChanged: true,
      hasObservedThread: true,
    })).toBe('/chat/1');
  });

  it('keeps draft route when no route id is present and runtime did not change', () => {
    expect(resolveUrlSyncTarget({
      routeId: undefined,
      remoteId: '25',
      mainThreadChanged: false,
      hasObservedThread: true,
    })).toBeNull();
  });

  it('syncs URL when a no-route page switches to a persisted runtime thread', () => {
    expect(resolveUrlSyncTarget({
      routeId: undefined,
      remoteId: '25',
      mainThreadChanged: true,
      hasObservedThread: true,
    })).toBe('/chat/25');
  });
});

describe('resolveWorkbenchThreadId', () => {
  it('maps numeric chat routes to legacy conv threads', () => {
    expect(resolveWorkbenchThreadId('25', null)).toBe('conv_25');
  });

  it('keeps AgentScope chat routes as the workbench thread source', () => {
    expect(resolveWorkbenchThreadId('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', null)).toBe(
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });

  it('uses runtime remote id when the URL has no route id', () => {
    expect(resolveWorkbenchThreadId(undefined, 'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null)).toBe(
      'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    );
  });

  it('keeps the route as the panel source while runtime remote id is catching up', () => {
    expect(resolveWorkbenchThreadId('25', 'as_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null)).toBe('conv_25');
    expect(resolveWorkbenchThreadId('as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '25', null)).toBe(
      'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    );
  });

  it('prefers resolved AgentScope thread over numeric runtime id for a new chat draft', () => {
    expect(resolveWorkbenchThreadId(undefined, '29', 'as_cccccccc-cccc-cccc-cccc-cccccccccccc')).toBe(
      'as_cccccccc-cccc-cccc-cccc-cccccccccccc',
    );
  });
});

describe('shouldAcceptResolvedWorkbenchThread', () => {
  it('accepts the latest AgentScope mirror on a route-less chat page', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: undefined,
      threadId: 'as_dddddddd-dddd-dddd-dddd-dddddddddddd',
      mainThreadId: 'local-thread',
      localThreadId: '30',
    })).toBe(true);
  });

  it('keeps explicit history routes as the panel source', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: '25',
      threadId: 'as_dddddddd-dddd-dddd-dddd-dddddddddddd',
      mainThreadId: 'local-thread',
      localThreadId: 'local-thread',
    })).toBe(false);
  });

  it('rejects non-AgentScope thread ids', () => {
    expect(shouldAcceptResolvedWorkbenchThread({
      routeId: undefined,
      threadId: 'conv_25',
      mainThreadId: 'local-thread',
      localThreadId: 'local-thread',
    })).toBe(false);
  });
});

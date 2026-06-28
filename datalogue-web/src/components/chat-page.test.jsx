import { describe, expect, it } from 'vitest';

import { resolveUrlSyncTarget, shouldSwitchToRouteThread } from './chat-page.jsx';

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

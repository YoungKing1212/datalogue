import { describe, expect, it } from 'vitest';

import { shouldSwitchToRouteThread } from './chat-page.jsx';

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

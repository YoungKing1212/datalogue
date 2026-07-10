import { describe, expect, it } from 'vitest';

import {
  classifyWorkbenchMountSource,
  isAllowedWorkbenchRecoverySource,
} from './workbench-mount-source.js';

describe('workbench-mount-source', () => {
  it('classifies ordinary chat routes as non-recovery sources', () => {
    expect(classifyWorkbenchMountSource({ route_path: '/chat', routeId: undefined })).toBe('ordinary_chat');
    expect(classifyWorkbenchMountSource({ route_path: '/chat/25', routeId: '25' })).toBe('ordinary_chat_history');
    expect(isAllowedWorkbenchRecoverySource('ordinary_chat')).toBe(false);
    expect(isAllowedWorkbenchRecoverySource('ordinary_chat_history')).toBe(false);
  });

  it('classifies the hidden recovery shell and explicit recovery routes as allowed recovery sources', () => {
    expect(
      classifyWorkbenchMountSource({
        route_path: '/workbench/as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        routeId: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        source_kind: 'hidden_recovery_shell',
        is_hidden_recovery: true,
      }),
    ).toBe('hidden_recovery_shell');

    expect(
      classifyWorkbenchMountSource({
        route_path: '/workbench/as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/artifact:result-1',
        routeId: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        source_kind: 'legacy_mirror',
      }),
    ).toBe('legacy_mirror');

    expect(
      classifyWorkbenchMountSource({
        route_path: '/workbench/as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        routeId: 'as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        source_kind: 'explicit_recovery',
        deep_link_intent: true,
      }),
    ).toBe('explicit_recovery');

    expect(isAllowedWorkbenchRecoverySource('hidden_recovery_shell')).toBe(true);
    expect(isAllowedWorkbenchRecoverySource('legacy_mirror')).toBe(true);
    expect(isAllowedWorkbenchRecoverySource('explicit_recovery')).toBe(true);
  });

  it('fails closed on conflicting or unknown sources', () => {
    expect(
      classifyWorkbenchMountSource({
        route_path: '/chat',
        source_kind: 'explicit_recovery',
      }),
    ).toBeNull();

    expect(
      classifyWorkbenchMountSource({
        route_path: '/workbench/as_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        source_kind: 'ordinary_chat',
      }),
    ).toBeNull();

    expect(classifyWorkbenchMountSource({ route_path: '/unknown' })).toBeNull();
  });
});

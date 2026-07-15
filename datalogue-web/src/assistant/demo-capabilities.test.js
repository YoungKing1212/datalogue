import { describe, expect, it } from 'vitest';

import {
  DEMO_CAPABILITY_LEVELS,
  exposesAgentTeam,
  resolveDemoCapabilityLevel,
} from './demo-capabilities.js';

describe('demo capabilities', () => {
  it('defaults to the first-stage safe projection when Vite env is absent or invalid', () => {
    expect(resolveDemoCapabilityLevel({})).toBe(DEMO_CAPABILITY_LEVELS.SINGLE_TABLE);
    expect(resolveDemoCapabilityLevel({ VITE_DATALOGUE_DEMO_CAPABILITY_LEVEL: 'unknown' }))
      .toBe(DEMO_CAPABILITY_LEVELS.SINGLE_TABLE);
  });

  it('only exposes agent team projection in the fourth-stage capability', () => {
    expect(exposesAgentTeam(resolveDemoCapabilityLevel({
      VITE_DATALOGUE_DEMO_CAPABILITY_LEVEL: 'semantic_metrics',
    }))).toBe(false);
    expect(exposesAgentTeam(resolveDemoCapabilityLevel({
      VITE_DATALOGUE_DEMO_CAPABILITY_LEVEL: 'agent_team',
    }))).toBe(true);
  });
});

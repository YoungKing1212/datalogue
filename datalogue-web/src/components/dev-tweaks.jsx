// 仅开发环境动态加载的视觉调试面板，避免调试协议进入生产 bundle。
import React from 'react';
import {
  TweaksPanel,
  TweakSection,
  TweakColor,
  TweakRadio,
  TweakToggle,
  TweakButton,
} from './tweaks-panel';

export function DevTweaks({ t, setTweak, onOpenPublish }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="主题色" />
      <TweakColor
        label="Accent"
        value={t.accent}
        options={['#1976c9']}
        onChange={(value) => setTweak('accent', value)}
      />
      <TweakSection label="布局" />
      <TweakRadio
        label="密度"
        value={t.density}
        options={['compact', 'regular', 'comfy']}
        onChange={(value) => setTweak('density', value)}
      />
      <TweakSection label="问数体验" />
      <TweakRadio
        label="Agent 推理"
        value={t.agentVerbosity}
        options={[
          { value: 'minimal', label: '简洁' },
          { value: 'expanded', label: '展开' },
          { value: 'full', label: '完整' },
        ]}
        onChange={(value) => setTweak('agentVerbosity', value)}
      />
      <TweakToggle
        label="显示追问 chips"
        value={t.showFollowups}
        onChange={(value) => setTweak('showFollowups', value)}
      />
      <TweakSection label="调试" />
      <TweakButton label="打开发布接口 Drawer" onClick={onOpenPublish} />
    </TweaksPanel>
  );
}

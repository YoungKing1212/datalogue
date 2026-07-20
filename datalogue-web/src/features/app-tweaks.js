// 应用级视觉参数状态；生产环境只保留默认参数，不打包调试面板和跨窗口编辑协议。
import { useCallback, useState } from 'react';

const EDIT_MODE_ORIGIN = import.meta.env.VITE_EDIT_MODE_ORIGIN || window.location.origin;

export function useTweaks(defaults) {
  const [values, setValues] = useState(defaults);
  const setTweak = useCallback((keyOrEdits, value) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null
      ? keyOrEdits
      : { [keyOrEdits]: value };
    setValues((previous) => ({ ...previous, ...edits }));
    if (import.meta.env.DEV && window.parent !== window) {
      // 跨源调试宿主必须通过 VITE_EDIT_MODE_ORIGIN 显式配置，禁止广播到任意来源。
      window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, EDIT_MODE_ORIGIN);
    }
    window.dispatchEvent(new CustomEvent('tweakchange', { detail: edits }));
  }, []);
  return [values, setTweak];
}

// 测试专用 ECharts 轻量替身：作为 Vitest 全局兜底 mock，只覆盖组件单测需要的接口。
// 若测试需要断言 init/setOption 调用，应在测试文件内使用 vi.mock('echarts') 覆盖本 alias。

export function init() {
  return {
    setOption() {},
    resize() {},
    dispose() {},
  };
}

export default { init };

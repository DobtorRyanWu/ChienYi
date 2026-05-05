import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // happy-dom 提供 DOMParser，比 jsdom 輕量快速
    environment: 'happy-dom',
    include: ['tests/unit/**/*.test.ts'],
    // 跑 fixture 測試需要讀檔，限制在 Node 端可用 fs
    globals: false,
  },
});

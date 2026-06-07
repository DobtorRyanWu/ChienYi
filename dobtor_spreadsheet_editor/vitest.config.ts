import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // 用純 Node 環境 + setup 檔注入 @xmldom/xmldom 的 DOMParser
    // 沿用 dobtor_doc_editor 的選擇：happy-dom 對 prefix 命名空間（如 OOXML 的 <x:c>）解析不可靠
    environment: 'node',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/unit/**/*.test.ts', 'tests/integration/**/*.test.ts'],
    globals: false,
  },
});

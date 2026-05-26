# Sprint 279 — ShapingEngine browser-compat refactor ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Phase 2.1-2.3 全套 cluster 第 1/3 / caller-injectable hbModuleLoader

**日期**：2026-05-26（週二）
**類型**：Strategy A production code 擴張 / 紀律 #18 scope-down（不擴張載入策略、不接 Layout）
**規畫書對應**：§Phase 2.1 ShapingEngine 封裝（user pinned「最值得做的一條」）
**前置**：Sprint 278 spike 揭示 ShapingEngine.ts `createRequire(import.meta.url)` 為 Node-only blocker

---

## Hypothesis & Result

**hypothesis**：把 ShapingEngine.ts 的 harfbuzzjs 載入路徑改為 caller-injectable
loader、預設保留 Node createRequire fallback，可讓同一份 ShapingEngine 程式在
Node + browser 兩端執行（browser caller 注入自取 wasm 的 loader）。

**結論**：**verified、5/5 unit test + 25/25 既有 ShapingEngine 測試零 regression**。

---

## 設計：caller-injectable loader（Sprint 64 ProtonClone DI pattern 重現）

### API 變更

```typescript
// 新增 export
export function setHbModuleLoader(loader: () => Promise<HBInstance>): void;
export function __resetHbModuleLoaderForTesting(): void;
```

### 內部行為

```typescript
async function loadHb(): Promise<HBInstance> {
  if (!hbInstancePromise) {
    if (hbModuleLoader) {
      // caller-injected path（browser / 自訂 wasm 來源）
      hbInstancePromise = hbModuleLoader();
    } else {
      // 預設 Node 路徑：dynamic import 避免 browser bundle resolver 拒絕
      hbInstancePromise = (async () => {
        const { createRequire } = await import('node:module');
        const localRequire = createRequire(import.meta.url);
        return localRequire('harfbuzzjs') as Promise<HBInstance>;
      })();
    }
  }
  return hbInstancePromise;
}
```

### 三大關鍵設計決策

| 決策 | 為何如此 |
|---|---|
| `createRequire` 從 top-level import 改為 lazy dynamic import | browser bundler（rollup/esbuild）看到 top-level `import 'node:module'` 會直接報錯；lazy 允許 caller 不走 default path、browser side 從不 invoke 該 branch |
| 不寫死 browser path（如 fetch('/wasm/hb.wasm')）| wasm 路徑因 caller 而異（CDN / static asset / inline base64）、由 caller 注入；ShapingEngine 不做選擇 |
| setHbModuleLoader 重複呼叫 reset cache | 測試友好、caller 換 loader 不需重啟 |

---

## 5 unit test（`tests/unit/sprint279_shaping_engine_loader_injection.test.ts`）

| Test | 驗證 |
|---|---|
| default path（無 injection）= Node createRequire fallback | 既有行為不變、Sprint 265-275 既有測試零 regression |
| setHbModuleLoader 注入 mock loader → shape 走 caller | loader invoke 計數 = 1、glyph 正確 |
| caller loader 被 cache、第二次 shape 不重 invoke | 多次 shape 計數仍 = 1 |
| setHbModuleLoader 重複呼叫 reset cache | loader B 被 invoke、loader A 不再增加 |
| __resetHbModuleLoaderForTesting 清 loader + cache | reset 後 shape 走 default path、injected counter 不增 |

**5/5 passed / 589ms**。

---

## Regression check

執行 `vitest run tests/unit/sprint265_shaping_engine_phase2.test.ts
tests/unit/sprint266_shaping_glyph_cache.test.ts tests/unit/sprint278_harfbuzz_node_parity.test.ts`：

- Sprint 265 ShapingEngine 15 案 ✓
- Sprint 266 Glyph cache 8 案 ✓
- Sprint 278 Node parity 2 案 ✓

**25/25 passed / 7.09s、零 regression**。

---

## 為何 Sprint 279 不另做 browser 端 spike

Sprint 278 已證 harfbuzzjs 可在 browser 跑（`<script>` 載 hb.js + hbjs.js +
createHarfBuzz({locateFile})）。Sprint 279 證 ShapingEngine.ts API 接受 caller
loader。**兩個合起來 = browser 端能用 ShapingEngine** — 但實際組合需要：

- Browser ESM 端能 import ShapingEngine.ts 編譯產物（rollup bundle）
- 字型 byte buffer 取得（next: Sprint 280 BrowserFontLoader）

組合驗證在 Sprint 280 整合 spike 一次做：BrowserFontLoader → ShapingEngine
（含 setHbModuleLoader 注入）→ measureRun → 確認與 Node 端輸出 byte-identical。

紀律 #18 scope-down：本 sprint 純 API refactor + Node-side regression
guarantee；browser e2e 留 Sprint 280。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：production code 擴張 ~50 行 ShapingEngine.ts | ✅ |
| #14.b clean scope：commit 含 ShapingEngine.ts refactor + index.ts barrel + 1 unit test + 1 doc | ✅ |
| #18 scope-down：純 API refactor、不擴張載入策略、不寫死 browser path、不接 Layout | ✅ |
| #21 audit 不 touch VR / 既有測試輸出（25/25 regression 零異動）| ✅ |
| #22 verify：unit test 5/5 + regression 25/25 為硬數據；browser e2e 留 Sprint 280 hypothesis | ✅ |
| 雙驗紀律（Sprint 277 確立）：tsc + vitest 兩路徑通；browser 路徑 留 Sprint 280 | ✅ |

---

## End of Sprint 279

**Phase 2.1-2.3 全套 cluster 第 1/3 完成**：ShapingEngine API 已 caller-injectable、
browser 端能注入自訂 wasm loader。

vitest 2094 → 2099 hypothesis（+5 Sprint 279 unit test）/ tsc Sprint 279 新檔
零新 error / VR 第 68 連 maintained。

下一步：Sprint 280 BrowserFontLoader（FontFace.load + CJK chain + 整合 spike
含 setHbModuleLoader 注入 + measureRun byte-identical 比對）。

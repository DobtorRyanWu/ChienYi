# Sprint 58 — LayoutCache（layout 結果 L1 快取）

**期間**：2026-05-15
**主軸**：Sprint 57 收割 memoize-only 6.36× 後 warm 87.1% 仍 renderMs；OffscreenCanvas + Web Worker render（原 Sprint 58 候選）為高風險改造。本 sprint 走低風險高槓桿替代路徑 = **layout 結果 L1 in-memory 快取**（warm 路徑 layout 110-318ms / 7.5% 仍未被 cache）。
**結論**：**42 fixture full-warm 7.01× total speedup（cold 9430ms → warm 1346ms）**，vs Sprint 57 6.36× 改善 +0.65×；**42/42 fixture layout cache 100% hit、layout 99.1% 消除**；warm path 更 render-dominated（87.1% → **94.1%**）；VR 0.0749 byte-identical；vitest 940 passed + 1 skipped（+19 LayoutCache 測試）。
**意義**：Sprint 50-58 cache 路線（parse / IDB AST / image L1 / image IDB / memoize render / layout）已 100% cache 全 deterministic 階段；warm 1346ms 中 **94.1% 為 render**，Sprint 59+ 必須做 render 段根本改造（OffscreenCanvas worker 或 native draw call 合併）才能進一步加速。

---

## 1. 動機

Sprint 55 full-warm benchmark 揭示 warm path 87.3% 為 renderMs；Sprint 57 memoize-only 把 render 消除提到 70.3%、warm 87.1%；但**沒人對 layout 階段下手**。

Sprint 55 量測：
```
warm total: 2282ms = parse 0.9 + preload 1.8 + render 1991 + layout 184 + hash 104
```

Sprint 57 memoize-only：
```
warm total: 1458ms = parse 0.8 + preload 0.7 + render 1270 + layout 110 + hash 75
```

Layout 110ms 占 warm 7.5%、是僅次於 render 的次大成本。layout 是 `(documentNode, LayoutOptions)` 的純函數 → **可安全快取**。

## 2. 設計

### 2.1 [LayoutCache](../static/src/core/cache/layout_cache.ts) — ~140 行

```
key = SHA-256(docx bytes) + '|' + SHA-256(canonicalize(layoutOptions))
value = DocumentLayout (含 pages array + warnings)
LRU = Map insertion order；put 時 evict 最舊；get 時 delete + set 推到尾
```

關鍵設計：

| 取捨 | 決定 | 原因 |
|---|---|---|
| Cache layer | L1 in-memory only | warm 命中率高、cold 不需跨 session；IDB 層留 Sprint 59+ |
| Key 組成 | docxHash `|` optsHash | 兩段都是 hex 64 字元、`|` 無歧義；docxHash 重用 [[ast_cache]] 已算過的 |
| optsHash | `canonicalizeJson(opts)` → SHA-256 | LayoutOptions 是小 object；`canonicalizeJson` 遞迴 key 排序避免「同 opts 不同來源 key 順序」造成 key 不穩 |
| LRU pattern | 同 [[AstCache]]（Sprint 51） | code DRY；Map.delete + set 推到尾端 |
| maxEntries | 8（同 AST cache 預設）| 工地 portal 多開幾個 docx 即夠用；harness 內覆寫成 64 |

### 2.2 pipeline 整合

[`tools/visual_regression_pipeline.entry.ts`](../tools/visual_regression_pipeline.entry.ts)：

```ts
RenderOptions.layoutCache?: LayoutCache

// hash 在 cache 或 layoutCache 任一開時計算
if (options.cache || options.layoutCache) {
  docxHash = await computeDocxHash(arrayBuffer);
}

// AST cache lookup（與 Sprint 51 同）
...

// Sprint 58 layout cache lookup
if (options.layoutCache && docxHash) {
  const optsHash = await hashLayoutOptions(options.layoutOptions ?? {});
  const layoutKey = composeLayoutKey(docxHash, optsHash);
  const cached = options.layoutCache.get(layoutKey);
  if (cached) {
    layout = cached;
    layoutCacheHit = true;
  } else {
    layout = layoutDocument(documentNode.sections, options.layoutOptions ?? {});
    options.layoutCache.put(layoutKey, layout);
  }
} else {
  layout = layoutDocument(documentNode.sections, options.layoutOptions ?? {});
}
```

`PipelineTiming` 加 `layoutCacheHit: boolean`（純加性 telemetry）。

### 2.3 harness + perf 整合

- harness：加 `useLayoutCache / clearLayoutCacheFirst` 旗標，singleton 在 `window.__dobtorLayoutCache`
- perf_baseline：`--layout-cache` 單獨模式 + `--full-warm` 自動連動開啟（AST + image + layout 三層）
- pipeline label：`sprint58_full_warm_with_layout_cache` / `sprint58_layout_cache_cold_vs_warm`

## 3. 結果

### 3.1 全 42 fixture full-warm（AST + image + layout cache 合用）

| 階段 | cold | warm | 消除 | warm 占比 |
|---|---|---|---|---|
| parse | 3964.1ms | 0.2ms | **100.0%** | 0.0% |
| layout | 318.5ms | 2.8ms | **99.1%** | 0.2% |
| preload | 675.7ms | 1.0ms | **99.9%** | 0.1% |
| render | 4385.6ms | 1266.0ms | 71.1% | **94.1%** ← 仍是主成本 |
| hash | — | 75.8ms | — | 5.6% |
| **total** | **9430.5ms** | **1345.8ms** | — | — |

→ **42/42 fixture layout cache 100% hit**；layout 99.1% 消除（剩 2.8ms = optsHash 計算開銷）。

### 3.2 vs 歷代基線

| Sprint | warm total | speedup vs cold | 主要新增 cache |
|---|---|---|---|
| 50 baseline（無 cache）| — | 1.0× | — |
| 55 baseline（AST L1 + image L1 合用） | 2282ms | 5.32× | AST + image L1 |
| 57 memoize-only | 1458ms | 6.36× | + render string memoize |
| **58（當前）** | **1346ms** | **7.01×** | + layout L1 |

→ Sprint 58 vs Sprint 57：warm -112ms、total speedup **+0.65×**。

### 3.3 為何 layout 318.5ms cold（不只 Sprint 57 的 110ms）

Sprint 57 量到的 110ms layout 是「**未開 layout cache 的 warm**」— 那時 AST 從 cache 命中、layout 仍跑、measureText cache 命中（同 process 內 measureText 結果穩定）。
Sprint 58 量到的 318.5ms layout 是「**真 cold layout**」— clearLayoutCacheFirst=true 強制 layout cache 也清掉；同時 AST cache 也 cold（每份 fixture 第一次 run）。

兩者並非可比 — 真實「冷開文件」layout cost 是 ~7-8ms / fixture（318.5/42），符合 Sprint 50 量測。

### 3.4 warm path 結構變化

| Sprint | warm parse | warm layout | warm preload | warm render | warm 主成本 |
|---|---|---|---|---|---|
| 55 | 0.9ms | 184ms（**8.1%**）| 1.8ms | 1991ms（87.3%） | render |
| 57 | 0.8ms | 110ms（7.5%）| 0.7ms | 1270ms（87.1%）| render |
| **58** | **0.2ms** | **2.8ms（0.2%）** | **1.0ms** | **1266ms（94.1%）** | **render（更主導）** |

warm path 已是 **94.1% renderMs** — Sprint 50-58 cache 路線完成所有 deterministic 階段 100% cache，剩下 render 是「該頁不會比上次重畫得更快」的根本性限制（單執行緒、V8 fillText、no GPU offload）。

## 4. 爭議點 / 重要發現

### 4.1 為何 100% cache hit（vs Sprint 51 AST cache 也是 100%）

Sprint 58 perf 模式裡，每 fixture 在同一 page 跑 3 次：
- run 0：`clearLayoutCacheFirst=true` + `clearCacheFirst=true` → cold（AST + layout cache 都清掉）
- run 1, 2：warm（cache 命中）

所以 warm 100% hit 是預期的（與 Sprint 51 AST cache 100% hit 同邏輯）。生產環境真實命中率取決於使用者開同份文件的頻率 — 跨 session 重開要等 Sprint 59+ IDB layer。

### 4.2 為何不做 IDB layer

- warm path 94.1% 是 render；layout cache 命中省 ~110ms warm，相對 1266ms render 是 8.7%
- IDB layer 跨 session 命中能再多省「每天第一次開檔」的 layout 7-8ms — 但這個量級不值得 IDB schema + serialization 投資
- DocumentLayout 含 Box / Line / Page nested 結構，structured-clone 可序列化但體積較大；IDB 寫入有 quota 風險
- 等 Sprint 59 OffscreenCanvas worker 上線時，layout 結果可以透過 postMessage 直接傳 worker（不一定需要 IDB）

### 4.3 layoutCacheHit telemetry 的用途

加在 `PipelineTiming.layoutCacheHit: boolean` 是純加性 telemetry — production 可用於：
- 開發階段：驗證 cache 命中率（debug 為何重開同份 docx 沒命中 → 可能 docx 內容變動 / layoutOptions 變動）
- 監控：cache miss 率高代表使用者頻繁切換文件、可調大 maxEntries

### 4.4 canonicalizeJson 為何遞迴 + 排序

LayoutOptions 是小 object，但有 nested 結構（如 fontMap、defaultPageSize）。如果只做 shallow stringify：
```js
JSON.stringify({ a: 1, b: { x: 1, y: 2 } })  // 結果 = '{"a":1,"b":{"x":1,"y":2}}'
JSON.stringify({ a: 1, b: { y: 2, x: 1 } })  // 結果 = '{"a":1,"b":{"y":2,"x":1}}'
```

→ Two 同邏輯 opts，hash 不同。canonicalizeJson 遞迴排序所有 nested key，確保兩者輸出相同字串：`{"a":1,"b":{"x":1,"y":2}}`。

19 個 unit test 中 5 個專門驗 canonicalizeJson 穩定性（同 obj 不同 key 順序 / nested / undefined 剔除 / array 順序保留 / primitive）。

## 5. vitest / VR

- vitest **921 → 940 passed + 1 skipped**（+19 LayoutCache 測試 — 基本 CRUD、LRU、canonicalizeJson 穩定性、hashLayoutOptions deterministic、composeLayoutKey）
- **VR 0.0749 byte-identical**（per_page_mean 0.074895 與 Sprint 50-57 完全一致；layoutCache 預設不啟用、VR 不開）
- Sprint 12/16 baseline 未變

## 6. Sprint 50-58 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51 | L1 AST cache | warm 4.79× | 同 session 命中 |
| 52 | L2 IDB AST | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 1.16-1.43× | 多頁 payoff、≤6p 限制 |
| 54 | image decode L1 | preload 29× / image-bearing 100% hit | 重開含照片文件加速 |
| 55 | 合用驗證量測 | full-warm 5.32× / 6p image-heavy 1.4-4.5× | 暴露 render 是新主成本 |
| 56 | L2 IDB image + ImageBitmap | preload L1 105.74× / L2 2.79× | 跨 session image preload |
| 57 | render memoize-only（aggressive 翻車） | full-warm 6.36× / +1.04× | 第八層紀律應驗 / 字串 memoize 安全 |
| **58** | **layout L1 cache** | **full-warm 7.01× / +0.65× / 100% layout hit / 99.1% elimination** | **cache 路線完成所有 deterministic 階段；warm 94.1% render** |

## 7. Sprint 59+ 候選

| 候選 | 打中的段 | 槓桿 | 風險 |
|---|---|---|---|
| **OffscreenCanvas + Web Worker render** | render 整段非阻塞 + 多核 | 主執行緒空閒、跨多核並行 | 高（render code 重寫、Safari < 16.4 不支援、puppeteer 行為差異）|
| **drawLine path coalescing** | render line stroke 數量 | 表格 fixture cell border 邊重畫 dedup 50%+ | 中（state interaction 細節需 VR 驗）|
| **fillText 同 run 合併** | render fillText 數量 | 同 paragraph 內 same-style runs 合併 | 高（layout 已 pre-compute x position、合併易破壞 alignment）|
| **font metric LRU 跨頁共享** | layout 細節 | EstimateMetrics 已有 per-instance cache、改 module singleton +5-10% | 低 |
| HarfBuzz / opentype.js | layout + render | VR mean -1~2pp + 順帶 metric 提速 | 大（bundle size、依賴）|
| 大文件 50+ 頁 fixture | render 多頁 | Sprint 53 預測但未證實 | 待外部（user 提供）|

**建議 Sprint 59 = drawLine path coalescing**（不是 OffscreenCanvas）：
- 中等風險、中等槓桿，符合 Sprint 57 教訓（避免高風險 render 改造一次性投入太多）
- 對表格密集 fixture（02_std_table、03_complex_table）渲染量大幅減少
- 改 BrowserCanvasRenderContext + CanvasRenderer 局部、可精細 VR 驗證

OffscreenCanvas worker 路徑風險過高 — Safari < 16.4 不支援、puppeteer 環境行為可能差異、render code 重寫即便成功也只省主執行緒阻塞（不一定縮短 wall time）。先做 path coalescing 累積經驗、Sprint 60+ 再評估 worker。

## 8. 工作摘要

```
+  static/src/core/cache/layout_cache.ts  | 新增 LayoutCache（~140 行 L1 LRU + canonicalizeJson + hashLayoutOptions + composeLayoutKey）
+  tests/unit/LayoutCache.test.ts          | 19 unit tests
M  tools/visual_regression_pipeline.entry.ts  | RenderOptions.layoutCache + PipelineTiming.layoutCacheHit + docxHash 提早計算（layoutCache 也需要）+ window.LayoutCache export + version 'sprint58'
M  tools/dist/visual_regression_pipeline.iife.js  | rollup 重編
M  scripts/visual_regression_v14_harness.html  | useLayoutCache / clearLayoutCacheFirst 旗標
M  scripts/perf_baseline.mjs               | --layout-cache 模式 + --full-warm 自動連動 + fullWarmSummary 加 layout 欄位 + cold/warm 印表加 layout 階段
M  tests/fixtures/perf_baseline_report.json  | Sprint 58 量測結果
+  docs/sprint58_layout_cache.md           | 本文件
```

VR：**0.0749 byte-identical**。vitest **940 passed + 1 skipped**。**Sprint 58 full-warm 7.01× total speedup**（cold 9430ms → warm 1346ms），vs Sprint 57 6.36× 改善 +0.65×；**42/42 fixture layout cache 100% hit、layout 99.1% 消除**；warm path 94.1% 為 renderMs（cache 路線到此 100% 覆蓋 deterministic 階段）。

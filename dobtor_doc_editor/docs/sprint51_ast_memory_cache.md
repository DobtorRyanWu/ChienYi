# Sprint 51 — AST in-memory LRU cache（路線 A 第二步、Phase 7）

**期間**：2026-05-15
**主軸**：Sprint 50 基線量測證實 parse 占 60.7% 為瓶頸。路線 A Sprint 51 首選 = IndexedDB AST 快取。本 sprint 走「先驗 precondition」紀律 → **先做 in-memory LRU cache 證實「parse 可快取」假設**，IndexedDB 持久化留 Sprint 52。
**結論**：**warm vs cold total speedup = 4.79× / parse speedup ≈ 無窮大（4585ms → 0.3ms）**。SHA-256 hash 成本僅 100.8ms / 42 fixture（warm 總時 4.5%），完全可接受。hypothesis 確認；Sprint 52 = 同層 API 加 IDB 後端（跨 page reload）。VR 維持 0.0749、vitest 877 passed（+11 新 cache 測試）。

---

## 1. 背景：為何 Sprint 51 先做 in-memory 而非直接 IDB

- 規劃書 §11.18 與 Sprint 50 audit doc 都標 Sprint 51 = **IndexedDB AST 快取**
- 但專案紀律從 Sprint 41-44 已驗證：**沒先用 prep test 證實假設 → 假設先行翻車**（Sprint 41/42 的 vAlign tight-fit、Sprint 33-35 假設先行三連敗）
- 「cache 可顯著加速重開」是個 hypothesis，先用最簡單最低風險的 in-memory 證實它，再加上 IDB 的非同步/版本/持久化複雜度
- 這也讓 Sprint 51 範圍可控（單層 cache + LRU + 量測），Sprint 52 範圍清晰（同 API 加 IDB 後端）

## 2. 設計

### 2.1 新模組

[static/src/core/cache/ast_cache.ts](../static/src/core/cache/ast_cache.ts) — 90 行：

- **`computeDocxHash(bytes): Promise<string>`** — SHA-256 hex via `globalThis.crypto.subtle.digest`（瀏覽器 native；Node 16+ 亦支援，便於 vitest）
- **`class AstCache`** — `Map<string, DocumentNode>` 後的 LRU，touch 用 `delete + set` 重新插入到 Map 尾端、淘汰用 `keys().next().value` 取最舊
- `get/put/has/clear/stats`；`maxEntries` 預設 8、puppeteer harness 用 64

### 2.2 pipeline 整合

[tools/visual_regression_pipeline.entry.ts](../tools/visual_regression_pipeline.entry.ts) 的 `render()` 加 `options.cache?: AstCache`：

- 若無 cache → 維持 Sprint 50 行為（VR 預設無 cache）
- 若有 cache → hash → get → hit 直接用 cached AST、miss 才 parse + put
- `PipelineTiming` 加 `hashMs`（SHA-256 計算）+ `cacheHit: boolean`，純加性

harness [scripts/visual_regression_v14_harness.html](../scripts/visual_regression_v14_harness.html) 加 `options.useCache` / `options.clearCacheFirst` 旗標控制 `window.__dobtorAstCache` singleton。

### 2.3 量測

[scripts/perf_baseline.mjs](../scripts/perf_baseline.mjs) 加 `--cache` 模式：每份 fixture run0 = cold（清空 cache 後 parse），run1+ = warm（命中 LRU）。

## 3. 結果：cold vs warm（42 fixture 加總）

| 指標 | cold | warm | speedup |
|---|---|---|---|
| **total** | 10738.4ms | **2240.0ms** | **4.79×** |
| parse | 4584.7ms | **0.3ms** | 15282× |
| hash（warm only） | — | 100.8ms | — |

warm 配置：**hash 100.8ms（warm 總時 4.5%）取代 parse 4584.7ms**。

### 3.1 分類 speedup

| 分類 | cold mean | warm mean | speedup | 解讀 |
|---|---|---|---|---|
| 01_simple | 154.7 | 63.8 | 2.4× | parse 是 cold 的 60% → 消掉後減半 |
| 02_std_table | 145.5 | 58.5 | 2.5× | 含 preload（image 文件），warm 後 preload+render 變主成本 |
| 03_complex_table | 99.6 | 28.5 | 3.5× | 全套管 1p 文件，warm 後 render 主導 |
| **04_with_image** | 255.4 | 95.5 | **2.7×** | 6p+ 大照片：preload/render 主導，cache 救不了 |
| **05_header_footer** | 300.4 | 45.8 | **6.6×** | parse-heavy（複雜 XML）、無 image → cache 收益最大 |
| **06_template** | 167.0 | 22.0 | **7.6×** | 同上 |

**範圍**：1.9× ~ 9.8×。05_header_footer/自主檢查表---植栽 達 9.8×（cold 355.7ms → warm 36.2ms）。

### 3.2 warm 路徑新瓶頸

cold 時 parse 60.7%、render 29.3%；**warm 時 render 64.4%、preload 24.8%、layout 6.4%、parse 0.0%**。瓶頸轉移到 render — Sprint 53+ 的 render 優化（image decode 快取 / 可視頁虛擬化）會直接拉開。

## 4. 爭議點 / 設計決策

### 4.1 為何不快取 layout

layout cold 占 1.8%（Sprint 50），warm 後仍只 6.4%（小絕對量），收益不抵 LayoutOptions 變動失效風險（用戶切 DPI、改頁邊距時 cache key 必須包含 options）。AST 是 docx bytes 純函數、cache key 單純；layout 還受多個 options 影響。

### 4.2 hash 成本可預測嗎

- 大多數 fixture hash < 1ms（42KB 小檔）
- 大檔（1-2MB）hash 2-8ms
- 全 42 fixture warm 時 hash 加總 100.8ms = 平均 2.4ms/份
- 對 < 10MB 文件，SHA-256 走 native crypto subtle、線性 throughput ~500MB/s，可忽略

### 4.3 為何 maxEntries 預設 8（harness 用 64）

- 一般使用者單次 session 內活躍編輯 ~3-5 份文件，8 足以涵蓋
- AST 物件大小：典型監造文件 ~100KB-1MB 在 V8 heap 上（粗估，含 Map/array 開銷）。8 entries ≈ 1-8MB heap，可接受
- perf 量測時為消除 LRU 淘汰干擾、用 64

### 4.4 為何 hash docx bytes 而非用「檔案路徑」

工地常見「同名 docx 已被修改」情境（廠商重傳同檔名）。bytes hash 才能正確區分。代價是每次都要算 hash（不能跳過），但實測成本 < 3ms 平均，遠小於 parse 80-180ms 收益。

## 5. Sprint 52 候選

| 候選 | 接 Sprint 51 的價值 | 風險 |
|---|---|---|
| **IndexedDB 持久化層**（首選） | 跨 page reload / tab close 都能命中；Odoo Portal user 重新登入打開同份文件直接 warm | 低（IDB 用 native structuredClone、DocumentNode 已驗證可序列化）|
| Hash worker pool | hash 100.8ms / 42 = 2.4ms/份目前可忽略，但極大文件（> 50MB）會明顯 | 低 |
| **Render path 優化**（warm 後新瓶頸） | warm 後 render 占 64.4%、是新主成本 | 中（image decode 快取 / 可視頁虛擬化各自複雜度）|

**建議 Sprint 52 = IndexedDB 持久化**：同 API 加後端、不改 caller、把 cache 從「single session」擴到「同 origin 永久」。Sprint 53+ 啟動 render path 優化。

## 6. vitest / VR

- vitest **877 passed + 1 skipped**（Sprint 50: 866 → Sprint 51: 877，+11 AstCache 測試）
- VR v14：**0.0749 全 6 分類與 Sprint 49/50 byte-identical** — cache 為 opt-in、VR 預設不啟用、IIFE rebuild 不影響渲染
- Sprint 12/16 baseline 未變動

## 7. 工作摘要

```
+  static/src/core/cache/ast_cache.ts          | LRU memory cache + SHA-256 hash（90 行）
+  tests/unit/AstCache.test.ts                 | 11 個單元測試（hash 決定性、LRU 淘汰、stats）
M  tools/visual_regression_pipeline.entry.ts   | options.cache 參數 + hashMs + cacheHit 純加性
M  tools/dist/visual_regression_pipeline.iife.js(.map) | rollup rebuild
M  scripts/visual_regression_v14_harness.html  | __dobtorAstCache singleton + useCache/clearCacheFirst 旗標
M  scripts/perf_baseline.mjs                   | --cache 模式（run0 cold / run1+ warm）+ cold-vs-warm 聚合
M  tests/fixtures/perf_baseline_report.json    | 加 cacheSummary 區段（speedup 4.79x）
+  docs/sprint51_ast_memory_cache.md           | 本文件
```

VR：**0.0749**。vitest **877 passed + 1 skipped**。cold vs warm **4.79× total speedup**。

## 8. Sprint 50-51 軌跡

| Sprint | 類型 | 關鍵 |
|---|---|---|
| 50 | 純診斷（轉路線 A）| 效能基線：parse 60.7% 為瓶頸；parse 成本由 XML 結構複雜度主導 |
| **51** | **落地（路線 A）** | **in-memory AST cache 證實 hypothesis：cold→warm 4.79× speedup、parse 完全消除（warm 0.3ms）；瓶頸轉移到 render 64.4%** |

**心得**：Sprint 50 量化問題、Sprint 51 證實假設並落地 in-memory 層。連兩 sprint 為路線 A 建立可觀測且資料驅動的優化模式（量測 → 假設 → 落地小範圍 → 量測確認 → 落地大範圍）。這也呼應 Sprint 43-44 連續突破的成功公式（trace 診斷 → prep test 驗 precondition → 精準修改 → VR 量化）。

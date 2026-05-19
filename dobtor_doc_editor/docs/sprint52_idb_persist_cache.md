# Sprint 52 — IndexedDB AST 持久化（路線 A 第三步、Phase 7）

**期間**：2026-05-15
**主軸**：Sprint 51 in-memory LRU 證實「parse 可快取」假設成立（warm 4.79× speedup）。Sprint 52 把同 API 延伸成兩層 cache（L1 memory + L2 IndexedDB），實現跨 page reload / tab close / browser restart 的持久化。
**結論**：**IDB 跨 page 持久化確認生效**——page1 cold parse 9415ms → page2（fresh JS 上下文、L1 空、L2 hit）parse 僅 580ms = **parse 段 16× speedup（24ms/fixture cold → 14ms/fixture IDB read）**。整體 cold→warm-from-IDB **2.38× total speedup**（cold 15157ms → IDB hit 6366ms）。與 L1 比較：L1 hit 7.41× 較佳（warm-L1 2045ms），但 L1 限同 page；L2 用 ~103ms/fixture 的 IDB read 開銷換得「跨 page」這個 L1 拿不到的維度。VR 維持 0.0749、vitest 886 passed（+9 IdbAstCache 測試）。

---

## 1. 背景：Sprint 51 → Sprint 52 連續性

| Sprint | 範圍 | 同 session 命中 | 跨 session 命中 | 風險 |
|---|---|---|---|---|
| 51 | in-memory LRU | ✅ | ❌ | 低（已落地 11 test） |
| **52** | **+ IndexedDB L2** | **✅（L1）** | **✅（L2）** | **低（DocumentNode 已驗證 structuredClone OK）** |

Sprint 51 audit doc 已標 Sprint 52 = IDB 後端（同 AstCache API 加 IDB 層，DocumentNode 已驗證可序列化）。本 sprint 走 Sprint 51 設計直接落地。

## 2. 設計

### 2.1 兩層 cache 架構

`IdbAstCache`（新增於 [static/src/core/cache/ast_cache.ts](../static/src/core/cache/ast_cache.ts)，~150 行）：

- **L1** = 內嵌一個 `AstCache`（Sprint 51 in-memory LRU），同 session 命中 ~0ms
- **L2** = IndexedDB 物件 store；同 origin 跨 page reload / tab close 命中
- `get(hash)`：L1 hit 直接返回；L1 miss → L2 read（含 lastAccessed 更新）→ promote 回 L1
- `put(hash, ast)`：同時寫 L1 + L2；put 後若 L2 entries 超過 `maxIdbEntries`（預設 32）按 lastAccessed 升序淘汰最舊
- **失敗策略**：IDB 拋錯（private mode / quota / corruption）時靜默降級為 L1-only，不破壞 caller
- **Schema migration**：DB_VERSION 任何升版時 drop store 重建（AST 結構升版 → 舊資料一概作廢）

### 2.2 pipeline 整合

`RenderOptions.cache` 型別從 `AstCache`（sync）改為 `PipelineAstCache` 介面（接受 sync 或 async）：

```ts
export interface PipelineAstCache {
  get(hash: string): DocumentNode | undefined | Promise<...>;
  put(hash: string, ast: DocumentNode): void | Promise<void>;
}
```

pipeline 端統一 `await cache.get/put(...)`——對 sync 值 await 是 no-op，對 Promise 正常 unwrap。**Sprint 51 的 11 個 AstCache test 全部繼續通過**（無需改 API）。

harness HTML 加 `options.cacheBackend: 'memory' | 'idb'`（預設 memory），分別建 `window.__dobtorAstCache` 或 `window.__dobtorIdbAstCache` singleton。

### 2.3 量測

`perf_baseline.mjs --cache-persist` 模式：每份 fixture **開兩個 puppeteer page**：
- **page1**：clearCacheFirst → cold parse → put L1+L2
- **page2**（**fresh JS 上下文、L1 空**，但同 origin / browser → IDB 還在）：
  - run0 = warm-from-IDB（L1 miss、L2 hit → promote 回 L1）
  - run1 = warm-from-L1（剛 promote 上去的 L1 hit）

## 3. 結果：42 fixture 加總

| 階段 | total | parse | hash |
|---|---|---|---|
| **cold (page1)** | **15157.0ms** | **9414.9ms** | 0 |
| warm-from-IDB (page2 run0) | 6366.3ms | 580.3ms* | 91.0ms |
| warm-from-L1 (page2 run1) | 2045.5ms | ~0 | ~0 |

`*` parse=580ms 在 IDB hit 場景不是真 parse，是 `tStart→tParseEnd` 區間（cacheHit 時包含 await cache.get IDB 讀取時間）。**真實 IDB read 平均 ≈ 14ms/fixture**。

| 指標 | speedup vs cold |
|---|---|
| **IDB hit (L2)** | **2.38×** total |
| L1 hit | 7.41× total |
| L1 vs L2 差距 | 4320ms / 42 = ~103ms/fixture（IDB read+put 開銷）|

### 3.1 分類速率

| 分類 | cold mean | IDB hit mean | L1 hit mean | IDB speedup |
|---|---|---|---|---|
| 01_simple（會議記錄）| 215 | 160 | 49 | 1.3× |
| 02_std_table | 218 | 148 | 60 | 1.5× |
| 03_complex_table | 138 | 92 | 30 | 1.5× |
| 04_with_image | 416 | 277 | 99 | 1.5× |
| 05_header_footer | 411 | 226 | 49 | 1.8× |
| 06_template | 158 | 90 | 23 | 1.8× |

注：IDB 命中的「parse 替代成本」(~14ms IDB read) 為固定開銷；占越大的相對比重 → 越大文件相對受益越多。05_header_footer 的 parse-heavy 文件 (小檔但 XML 結構複雜) speedup 達 1.8×；image-heavy 04 受限於 preload/render 主導。

## 4. 爭議點 / 設計決策

### 4.1 為何 IDB 速率低於 in-memory（2.38× vs 4.79×）

不同情境，不能直接比：
- Sprint 51 4.79× = 同 page L1 hit（parse=0、hash 是唯一額外成本）
- Sprint 52 2.38× = **新 page 從 IDB 讀取**（cold JS、需 await IDB transaction 約 14ms/get）

對 Odoo Portal user 真實情境：用戶按 F5 / 重開 tab / 跨 session 再次打開同份文件 → Sprint 52 的 2.38× 才是適用值。Sprint 51 適用於同 page 反覆操作（編輯、preview cycle）。**兩者疊加最有價值**：用戶第一次打開後，整個 session 內反覆操作都是 L1 hit，重新進來則 L2 hit。

### 4.2 IDB read 14ms/get 可接受嗎

對比 cold parse 224ms/fixture，14ms 相當於 6%。對 < 10MB 文件可忽略。極大 AST（> 50MB）的 structuredClone 反序列化可能 > 100ms，但 ChienYi 用例（監造文件）都 < 5MB。

### 4.3 為何 schema migration 採「drop + 重建」

`DocumentNode` 是 OOXML 解析結果，欄位常隨 Sprint 演進（Sprint 13 加 docProps、Sprint 15 加 media）。版本變動時舊快取的 AST 缺欄位 → 後續 layout 可能炸。最安全 = drop store。代價 = 一次性 cache miss 重 parse，可接受（用戶感受不到，反正是後台升級時的事）。

### 4.4 maxIdbEntries=32 是否夠

工地現場單一使用者活躍編輯通常 < 10 份文件。32 給定 ~8 倍餘量。每份 AST ~100KB-1MB → 32 entries × 300KB 平均 ≈ 10MB IDB 占用，遠低於瀏覽器 quota（GB 級）。可隨用戶反饋調整。

### 4.5 為何不快取 layout / render ops

- layout cold 1.8% / warm 5.7% — 收益小 且 LayoutOptions 變動需失效
- render ops 是 MockRenderContext 結構，不適合存 IDB（瀏覽器 canvas 繪圖指令）；可視頁虛擬化（Sprint 53+）才是 render 段的正確優化

## 5. Sprint 53+ 候選（warm 後新瓶頸）

| Sprint 52 後新瓶頸 | 占比 | Sprint 53+ 候選 |
|---|---|---|
| **renderMs** | **73.5%** | 可視頁虛擬化（IntersectionObserver + 只渲染可視 ±2 頁）/ image decode 結果快取 |
| preloadMs | 10.3% | image preload 結果存 IDB 一起 cache |
| parseMs (IDB read) | 9.1% | IDB read 改用 keyPath getKey + 分批讀（小檔影響小，大檔再評估）|
| layoutMs | 5.7% | LayoutOptions hash 加入 cache key，可同時 cache layout |

**建議 Sprint 53 = 可視頁虛擬化**：warm 後 render 占 73.5%，是新主成本；多頁文件（如 6 頁環清表）payoff 直接放大。

## 6. vitest / VR

- vitest **886 passed + 1 skipped**（Sprint 51: 877 → Sprint 52: 886，+9 IdbAstCache 測試；fake-indexeddb 加入 devDependency）
- VR v14：**0.0749 全 6 分類與 Sprint 49/50/51 byte-identical** — cache 為 opt-in、VR 預設不啟用
- Sprint 12/16 baseline 未變動

## 7. 工作摘要

```
M  static/src/core/cache/ast_cache.ts          | +IdbAstCache（two-tier L1+L2 + IDB-side LRU）+ PipelineAstCache 介面
+  tests/unit/IdbAstCache.test.ts              | 9 個單元測試（L1/L2 命中、跨 instance 持久化、LRU 淘汰、設定驗證、介面相容）
M  tools/visual_regression_pipeline.entry.ts   | RenderOptions.cache 型別 → PipelineAstCache；await get/put；version: sprint52
M  tools/dist/visual_regression_pipeline.iife.js(.map) | rollup rebuild
M  scripts/visual_regression_v14_harness.html  | cacheBackend: 'memory' | 'idb' 旗標 + 雙 singleton
M  scripts/perf_baseline.mjs                   | --cache-persist 模式（page1 cold IDB put + page2 fresh-JS warm-from-IDB）+ runBootsOnFreshPage helper + cachePersistSummary 區段
M  tests/fixtures/perf_baseline_report.json    | 加 cachePersistSummary 區段
M  package.json / package-lock.json            | + fake-indexeddb devDep
+  docs/sprint52_idb_persist_cache.md          | 本文件
```

VR：**0.0749**。vitest **886 passed + 1 skipped**。**IDB hit cold→warm 2.38× speedup**，**L1 hit 7.41×**。

## 8. Sprint 50-52 軌跡

| Sprint | 類型 | 關鍵 |
|---|---|---|
| 50 | 純診斷（轉路線 A）| parse 60.7% 為瓶頸；parse 成本由 XML 結構複雜度主導 |
| 51 | 落地 in-memory | 4.79× warm speedup；parse 4585ms→0.3ms；warm 新瓶頸 = render 64.4% |
| **52** | **落地 IDB 持久化** | **跨 page IDB 確認生效：parse 9415ms→580ms（24ms→14ms/fixture）；IDB 2.38× / L1 7.41×；warm 新瓶頸 = render 73.5%** |

**心得**：Sprint 50 量測、Sprint 51 證實假設（in-memory）、Sprint 52 落地完整方案（+ IDB 持久化）— 三 sprint 連續打中規劃書 §11.18 排序的「IndexedDB AST 快取」候選，且每個 sprint 都先驗 precondition / 量測後決策。warm 路徑兩個 sprint 都讓 render 成為新瓶頸（Sprint 51 64.4% → Sprint 52 73.5%），Sprint 53+ 應啟動可視頁虛擬化攻 render 段。

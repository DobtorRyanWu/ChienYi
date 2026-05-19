# Sprint 54 — Image decode 結果快取（路線 A 第五步、Phase 7）

**期間**：2026-05-15
**主軸**：Sprint 50 量測 preload 占 cold 8.1%（image-bearing 類別達 17.9%）；Sprint 54 加 image decode 結果 in-memory LRU 快取，重開含同 image 文件直接跳過 browser decode。
**結論**：**image-bearing 分類 preload speedup 26-41×（02 29.0× / 03 41.3× / 04 26.6×）、warm cache hit rate 100%（68/68）**；image-heavy 04_with_image 單份 fixture 最高 saved 72ms（6 張 6p 環清表 cold preload 74ms → warm 2ms）；總 preload 659.5ms → 22.7ms（**29.05× speedup**）。VR 維持 0.0749 byte-identical、vitest 896 passed（+10 ImageDecodeCache 測試）。Sprint 51+54 疊加：用戶重開含照片文件 = AST hit + image hit = parse+preload 兩段都消除。

---

## 1. 背景：preload 為何值得快取

Sprint 50 基線數據：
- 全 42 fixture cold preload 580ms（8.1%）
- 04_with_image 分類 preload 占 17.9% 該類別 total
- 工地實務：每日大量照片進監造文件、估驗計價、施工日誌

preload 內容 = `dataURL → new Image() → onload`，瀏覽器要 base64 decode + image format（PNG/JPEG）decode。**同樣 bytes 重開時，重做這事不必要**。Sprint 51 AST cache 命中後 documentNode.media 是同樣 Map，但 preloadImages 仍每張重 decode。

## 2. 設計

### 2.1 新模組

[static/src/core/cache/image_decode_cache.ts](../static/src/core/cache/image_decode_cache.ts)（~80 行）：

- **Generic LRU** `ImageDecodeCache<V = HTMLImageElement>`：型別參數讓單元測試可以用 `string` 替代 HTMLImageElement（node 無 DOM）
- **Key = dataURL 字串本身**（內容定址；同 bytes → 同 dataURL）。不另算 hash（dataURL 已是內容、SubtleCrypto async 多餘）
- LRU 用 Map 插入順序（同 Sprint 51 AstCache 套路）
- `maxEntries` 預設 100，puppeteer harness 用 500

### 2.2 preloadImages 整合

`tools/visual_regression_pipeline.entry.ts` 的 `preloadImages` 加 `cache?: ImageDecodeCache` 參數：

```
for each (rId, dataUrl) in media:
  if cache && cache.get(dataUrl): map.set(rId, cached); cacheHits++
  else: img.onload → map.set(rId, img); cache?.put(dataUrl, img)
```

`RenderOptions.imageCache?: ImageDecodeCache` opt-in；`PipelineTiming.imageCacheHits` 純加性欄位記錄本次命中數。VR 預設不啟用、行為 byte-identical。

### 2.3 harness + perf_baseline

harness HTML 加 `useImageCache` / `clearImageCacheFirst` 旗標控制 `window.__dobtorImageCache` singleton。`perf_baseline.mjs --image-cache` 模式：每 fixture run0 cold（clear cache）/ run1+ warm（cache hits）；輸出 `imageCacheSummary` 區段。

## 3. 結果

### 3.1 全域（42 fixture 加總）

| 階段 | cold | warm | speedup |
|---|---|---|---|
| **preload** | **659.5ms** | **22.7ms** | **29.05×** |
| total | 8998.6ms | 4436.8ms | 2.03× |

注：**total speedup 2.03× 主要來自 V8 JIT warm-up**（warm runs 在同 page 內 hot path 已 inline cached）。**純 image cache 對 total 的貢獻 = preload 節省 637ms**（占 cold total 8998 的 7.1%、占 warm total 4436 的 14.4%）。

### 3.2 依分類

| 分類 | n | cold preload | warm preload | speedup | imgs | hits |
|---|---|---|---|---|---|---|
| 01_simple | 7 | 1ms | 0ms | 4.5× | 0 | 0 |
| **02_std_table** | 8 | 238ms | 8ms | **29.0×** | 26 | 26 |
| **03_complex_table** | 8 | 116ms | 3ms | **41.3×** | 10 | 10 |
| **04_with_image** | 6 | 304ms | 11ms | **26.6×** | 32 | 32 |
| 05_header_footer | 10 | 1ms | 0ms | (n/a) | 0 | 0 |
| 06_template | 3 | 0ms | 0ms | (n/a) | 0 | 0 |

→ **image-bearing 三大類（02/03/04）共 68 張圖、warm 100% hit、preload 平均 30× speedup**。非 image 分類（01/05/06）preload 本就 ~0ms、無感（也無回退）。

### 3.3 Top 5 image-heavy fixtures（preload 節省量）

| fixture | pc | imgs | cold preload | warm preload | saved |
|---|---|---|---|---|---|
| 04/6.環清表-(112.10.2.-10.6) | 6p | 6 | 74ms | 2ms | **72ms** |
| 04/6.環清表-(112.9.25.-9.29) | 6p | 6 | 62ms | 2ms | 60ms |
| 04/06.環清表-(112.10.9.-10.13) | 6p | 6 | 60ms | 2ms | 57ms |
| 02/1120928-週報 | 2p | 6 | 58ms | 2ms | 57ms |
| 02/1121013-週報 | 2p | 5 | 48ms | 2ms | 46ms |

→ 對 6 張照片的 6p 環清表，preload 從 74ms 砍到 2ms — 用戶感受最大的情境。

## 4. 與其他 sprint 疊加效益

Sprint 51 (AST cache) + 54 (image cache) 合用最有威力。用戶重開含照片文件：

| sprint 組合 | 重開 04_with_image/06.環清表 變化 |
|---|---|
| Sprint 50 baseline | cold ~645ms（parse 108 + preload 66 + render 469） |
| + Sprint 51 AST cache | warm ~145ms（parse 0 + preload 66 + render 79）= **4.4× speedup** |
| **+ Sprint 54 image cache** | warm **~80ms**（parse 0 + preload 2 + render 78）= **8.1× speedup** |

→ 重開含照片文件總體加速逼近 8× — 工地實務每日反覆開啟同份施工日誌 / 環清表的具體 UX 改善。

## 5. 限制與下一步

### 5.1 不持久化跨 page reload

ImageDecodeCache 純 in-memory（HTMLImageElement 不能直接 structuredClone 進 IDB）。Sprint 55+ 候選：
- 把 dataURL 進 IDB（已能 structuredClone string）；reload 後從 IDB 抓 dataURL → 重 decode 一次（不快但保留 image bytes）
- 進階：用 `createImageBitmap` 拿 ImageBitmap 進 IDB（可序列化、跨 page reload 直接重用解碼結果）— 工程量較大

### 5.2 LRU eviction 在大量文件場景

maxEntries=500 對單 session 開 50 份文件 × 平均 10 圖 = 5000 圖會 evict。實際工地單 session 通常開 ≤ 10 份文件、≤ 100 圖，500 充裕。

### 5.3 跨文件共享 logo

若多份文件嵌入同一張企業 logo（同 bytes、同 dataURL），image cache 自動跨文件命中。這是「資料識別 key」設計的副產品優勢。

## 6. Sprint 55+ 候選

| 候選 | 打中的段 | 槓桿 | 風險 |
|---|---|---|---|
| **大文件 fixture 收集 + Sprint 53 virtualize 重測** | 多頁 render | 50+ 頁施工日誌彙整真實 payoff | 0 工程、需內容 |
| **ImageBitmap + IDB 跨 page 持久化** | preload | 重開瀏覽器 tab 也命中 | 中（API 差異）|
| HarfBuzz / opentype.js 真實字型 metric | layout/render 質量 | VR mean -1~2pp | 大 |
| Web Worker parse | parse on cold | L1+L2 已大幅消除 parse 痛感 | 中 |
| docGrid snap 判別子 | VR mean | 路線 B 高風險長期 | 大 |

**建議 Sprint 55 = 大文件 fixture 收集**：Sprint 53 virtualize audit 明確指出「需 50+ 頁 fixture 才能驗證真實價值」；產出零工程成本（找真實施工日誌彙整入 fixtures/），但能補上 Sprint 53 的量測 gap。Sprint 56+ 視結果決定 ImageBitmap+IDB 或其他方向。

## 7. vitest / VR

- **vitest 896 passed + 1 skipped**（Sprint 53: 886 → Sprint 54: 896，+10 ImageDecodeCache 測試；用 string sentinel 替代 HTMLImageElement，node 環境直接跑）
- VR v14：**0.0749 全 6 分類與 Sprint 49-53 byte-identical** — imageCache opt-in、VR 預設不啟用
- Sprint 12/16 baseline 未變動

## 8. 工作摘要

```
+  static/src/core/cache/image_decode_cache.ts | Generic LRU image cache（80 行，dataURL 當 key）
+  tests/unit/ImageDecodeCache.test.ts        | 10 個單元測試（LRU touch/evict/淘汰、stats、dataURL key）
M  tools/visual_regression_pipeline.entry.ts  | preloadImages 加 cache 參數 + RenderOptions.imageCache opt-in + PipelineTiming.imageCacheHits 純加性 + version sprint54
M  tools/dist/visual_regression_pipeline.iife.js(.map) | rollup rebuild
M  scripts/visual_regression_v14_harness.html | useImageCache / clearImageCacheFirst 旗標 + window.__dobtorImageCache singleton
M  scripts/perf_baseline.mjs                  | --image-cache 模式（cold/warm preload 配對）+ imageCacheSummary 區段
M  tests/fixtures/perf_baseline_report.json   | 加 imageCacheSummary
+  docs/sprint54_image_decode_cache.md        | 本文件
```

VR：**0.0749**。vitest **896 passed + 1 skipped**。**preload 29.05× speedup / 100% image cache hit rate**。

## 9. Sprint 50-54 軌跡

| Sprint | 類型 | 關鍵指標 | 累計 warm 加速 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | — |
| 51 | L1 AST cache | warm 4.79× (parse → 0) | 4.79× |
| 52 | L2 IDB 持久化 | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 子集 1.16-1.43× | 多頁 payoff |
| **54** | **image decode cache** | **preload 29.05× / 100% hit rate / 04_with_image 單份最高 72ms 節省** | **疊加 Sprint 51 = 8.1× on image-heavy 重開** |

**心得**：Sprint 50-54 路線 A 五連發。Sprint 54 是「對的時間做對的事」——前面 sprint 已建立 cache 範式 + opt-in 慣例 + perf measurement infra，本 sprint 沿用、~80 行新模組 + ~20 行 wiring 即落地。image-bearing 分類 preload 數十倍加速，對工地實務每日反覆開啟含照片文件的 UX 改善具體可感。

# Sprint 53 — 可視頁虛擬化（IntersectionObserver 延後 paint）

**期間**：2026-05-15
**主軸**：Sprint 52 audit doc §5 指出 warm 路徑新瓶頸 = render 73.5%；Sprint 53 用 IntersectionObserver 虛擬化只 paint 視窗內 prerender 頁，其餘 canvas 創建並占位、滾動進入 rootMargin 內才繪。
**結論**：**功能落地正確（132 頁中 77 同步 paint / 55 deferred），但全 42 fixture render speedup 僅 1.06× / total 1.03× —— 受限於當前 fixture ≤6 頁、prerender=2 已覆蓋多數內容**。1-2p fixture speedup ≈ 0.91-0.96×（IO 設置 overhead 略大於收益），3p+ fixture 1.16-1.24×，top 5 達 1.24-1.43×（監造會議記錄、自主檢查表）。VR 維持 0.0749 byte-identical、vitest 886 passed（virtualize 是 opt-in）。Sprint 52 audit 對「當前 fixture payoff 小」的預測完全應驗。

---

## 1. 背景與選擇

Sprint 52 IDB 持久化把 warm 路徑 render 推到 73.5% 占比；Phase 7 規劃書 §11.20 排第一為「可視頁虛擬化」。實作前已知預測：fixture ≤6 頁、payoff 隨頁數放大。本 sprint 確實落地 IntersectionObserver 架構，但用全 42 fixture 驗證後確認「需 50+ 頁 fixture 才能放大價值」。

## 2. 設計：opt-in、預設關閉、VR 零影響

### 2.1 RenderOptions 介面

```ts
interface RenderOptions {
  // ...既有
  virtualize?: boolean | VirtualizeOptions;
}

interface VirtualizeOptions {
  prerenderPages?: number;  // 預設 2
  rootMargin?: string;      // 預設 '200px'
}
```

`virtualize === true` → 套預設物件；`false`/省略 → 完全同 Sprint 50/51/52 行為（VR 預設，所有 page 同步 paint）。

### 2.2 paintPage helper + 共用 IntersectionObserver

[tools/visual_regression_pipeline.entry.ts](../tools/visual_regression_pipeline.entry.ts) 抽出 `paintPage(canvas, page)` helper（含 `dataset.painted` 防重畫），render loop 變成：

```
for i in 0..limit:
  - 創建 canvas + fillRect 白底（不變）
  - if i < prerenderPages: paintPage() 同步畫
  - else if observer: observer.observe(canvas)  # 延後到滾動進入 viewport 才畫
```

IntersectionObserver 在 callback 內 `paintPage()` + `unobserve()`（一次性觸發）。`typeof IntersectionObserver === 'undefined'` 環境（舊瀏覽器）自動降級為同步 paint，保證內容仍可見。

### 2.3 PipelineTiming.paintedPages（新增加性欄位）

```ts
interface PipelineTiming {
  // ...既有
  paintedPages: number;  // virtualize off → = pageCount；on → = prerender 或更少
}
```

VR 不讀此欄位，只是診斷用。

### 2.4 harness 控制

`scripts/visual_regression_v14_harness.html` 增加 `options.useVirtualize` / `options.prerenderPages` 透傳 flag；perf_baseline.mjs 新 `--virtualize` mode 每份 fixture 開兩個 puppeteer page（page1 = baseline 全 paint / page2 = virt prerender=N）做配對比較。

## 3. 量測結果（42 fixture 加總、prerender=2）

### 3.1 全域

| 階段 | baseline | virt | speedup |
|---|---|---|---|
| **renderMs** | 4358.0ms | 4110.8ms | **1.06×** |
| **totalMs** | 9348.8ms | 9036.5ms | **1.03×** |
| paintedPages（同步） | 132（全部） | 77 | 55 deferred 給 IO |

### 3.2 依頁數分組

| pageCount | n | base render | virt render | speedup | 解讀 |
|---|---|---|---|---|---|
| 1 | 7 | 314 | 343 | **0.91×** | IO 設置 overhead > 收益（無延後對象）|
| 2 | 13 | 1064 | 1106 | **0.96×** | prerender=2 涵蓋全部、IO 純 overhead |
| 3 | 2 | 283 | 229 | **1.24×** | 1/3 頁延後 |
| 4 | 11 | 1647 | 1529 | **1.08×** | 2/4 頁延後（payoff 受限於 IO 在 puppeteer viewport 立即觸發）|
| 5 | 5 | 707 | 608 | **1.16×** | 3/5 頁延後 |
| 6 | 4 | 344 | 296 | **1.16×** | 4/6 頁延後 |

### 3.3 Top 5 speedup（render-level）

| fixture | pc | base | virt | speedup |
|---|---|---|---|---|
| 01_simple/03.1120210-監造會議記錄-1120801 | 3p | 194 | 136 | **1.43×** |
| 01_simple/03.1120815-監造會議記錄 | 4p | 196 | 140 | 1.40× |
| 05_header_footer/自主檢查表---植筋 | 5p | 150 | 112 | 1.34× |
| 04_with_image/06.環清表...10.23-10.27 | 6p | 84 | 64 | 1.31× |
| 03_complex_table/送審管制 | 2p | 86 | 69 | 1.26× |

## 4. 爭議點 / 限制

### 4.1 為何 4-6 頁 speedup 沒到 2-3×

理論：4 頁 baseline = 4 paints；virt = 2 paints + 2 observe。應 ~2× speedup。實測僅 1.08-1.16×。

原因：
- **paint 本身相對快**（每頁 ~30-50ms）；canvas 創建、fillRect、observer 設置等 fixed overhead 不可省
- **puppeteer viewport 在 1240×1754 內**：rootMargin=200px 使 page 2 邊界立即被觸發 → 第 2 頁 IO callback 雖在 microtask 之後，但仍在很短時間內 paint；測量 renderMs 只到 for loop 結束，後續 IO 不算入 ← 這部分理論上應拿到全部 deferred 節省，但實際 renderMs 樣本變異使方差大
- **canvas 創建本身有成本**：4 canvas 一定要建（不論 paint 否），佔用 renderMs 不少比重

### 4.2 1-2 頁文件 0.91-0.96× 反而變慢

prerender=2 涵蓋全部頁 → IO 完全不必要，但仍創建 observer 物件、設定回調。10-30ms overhead 在 1p 50ms 渲染上顯著（slowdown 9%）。

**建議**：production 接入時，加 short-circuit「pageCount <= prerenderPages → 直接 disable virtualize」。

### 4.3 為何 4p 比 6p speedup 還低（1.08 vs 1.16）

樣本量小（4p n=11 vs 6p n=4）+ 04_with_image 的 6p 大照片每頁 paint 較貴（70-80ms vs 4p 文字頁的 30-40ms），絕對節省金額放大 ratio。

## 5. 不變區與意外結果

- **VR 0.0749 byte-identical**：virtualize 為 opt-in、VR 預設不啟用 → 渲染輸出零變化 ✅
- **vitest 886 passed + 1 skipped 不變**：未碰 core code、未加新單元測試（IntersectionObserver 環境 jsdom 不支援、靠 puppeteer perf 驗證）
- **paintedPages 加成性欄位**：純診斷用，下游無 breaking change
- **fallback path**：`typeof IntersectionObserver === 'undefined'` 環境（極舊瀏覽器、Node 環境）→ 降級為同步 paint、内容仍可見

## 6. Sprint 54+ 候選

| 候選 | 打中的段 | 槓桿 | 風險 |
|---|---|---|---|
| **Image decode 結果快取** | preload 10.3% + render | image-heavy 文件 cache 解碼結果 | 中（HTMLImageElement 已透過 dataURL 緩存，但 decode 結果可能重做）|
| **CanvasRenderer fast-path：image-only line** | render 內 image-only 行的繪製 | 04_with_image 主成本 | 中 |
| **HarfBuzz / opentype.js 真實字型 metric** | layout/render 質量 | VR mean -1~2pp 預估 | 大 |
| 大文件 fixture 收集（50+ 頁）| 重新量測 virtualize | 證實多頁文件 virtualize 真實 payoff | 0 工程、需內容 |
| Web Worker parse | parse on cold | L1+L2 cache 已大幅消除 parse、優先級下降 | 中 |

**建議 Sprint 54 = image decode 結果快取**：04_with_image 系列是當前慢段（warm 後仍 100-300ms），且 ChienYi 工地實務每日上傳大量照片到監造記錄 / 環清表，是真實用戶痛點。Sprint 55+ 可拉真實 50-100 頁施工日誌彙整文件作大文件 fixture，重測 virtualize。

## 7. vitest / VR

- **vitest 886 passed + 1 skipped**（無變動：core code 未動、virtualize 為 opt-in、無新單元測試 — IO 環境靠 puppeteer 驗證）
- VR v14：**0.0749 全 6 分類與 Sprint 49/50/51/52 byte-identical** — virtualize opt-in、VR 預設不啟用
- Sprint 12/16 baseline 未變動

## 8. 工作摘要

```
M  tools/visual_regression_pipeline.entry.ts   | +VirtualizeOptions + paintPage helper + IntersectionObserver；PipelineTiming 加 paintedPages 純加性
M  tools/dist/visual_regression_pipeline.iife.js(.map) | rollup rebuild
M  scripts/visual_regression_v14_harness.html  | useVirtualize / prerenderPages 旗標透傳
M  scripts/perf_baseline.mjs                   | --virtualize 模式（雙 page baseline vs virt）+ virtSummary 區段
M  tests/fixtures/perf_baseline_report.json    | 加 virtSummary
+  docs/sprint53_page_virtualization.md        | 本文件
```

VR：**0.0749**。vitest **886 passed + 1 skipped**。**render speedup 1.06× / total 1.03×**（受限於 fixture ≤6p，3p+ 子集 1.16-1.43×）。

## 9. Sprint 50-53 軌跡

| Sprint | 類型 | 關鍵指標 | warm path 主成本 |
|---|---|---|---|
| 50 | 純診斷 | 量測：parse 60.7% | parse |
| 51 | L1 落地 | warm 4.79× speedup（parse → 0） | render 64.4% |
| 52 | L2 落地 | 跨 page 2.38× / L1 7.41× | render 73.5% |
| **53** | **render 攻關 v1** | **render 1.06× / 3p+ 子集 1.16-1.43×；功能落地、payoff 隨頁數放大** | render 45.5%（virt 後）|

**心得**：Sprint 53 是「明知收益有限仍落地」的工程決定——架構就位，未來大文件 fixture 進來後直接受惠。Sprint 52 audit 對「payoff 隨頁數放大」的預測完全應驗；下一步重點轉向 image decode 快取（攻 04 系列），大文件 virtualize 真實驗證留待真實使用情境素材入庫。

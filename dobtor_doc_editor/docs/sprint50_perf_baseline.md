# Sprint 50 — Phase 7 效能基線量測（純診斷；路線 A 商業化先行第一步）

**期間**：2026-05-15
**主軸**：規劃書 §11.16 路線 A（商業化先行）。連兩 sprint（46、49）snap 全域實驗翻車證實 VR 收斂進入地雷區，total 0.0749 穩 A- 級已達商用標準 → 轉 Phase 7 產品打磨。依專案一貫紀律「先量測再優化」（對應 Sprint 36 grid_analysis、Sprint 43 photo trace 的純診斷模式），本 sprint **不改 core code、不動 VR**，只建效能基線、定位瓶頸。
**結論**：**全域瓶頸 = parse（占 60.7%）**，render 29.3%、preload 8.1%、layout 僅 1.8%。關鍵反直覺發現：**parse 成本與檔案大小不相關，由 XML 結構複雜度（元素數）主導**。Sprint 51 最高槓桿 = IndexedDB AST 快取（消除 62.5% 重開成本）+ Web Worker parse（瓶頸段移出主執行緒）。VR 維持 0.0749 baseline、vitest 866 passed 不變。

---

## 1. 背景：為何 Sprint 50 是「量測 sprint」

- Sprint 43-49 七個 sprint 全在壓 VR mean（layout engine 收斂）。Sprint 46（exact 不 snap → 04 爆 +19.86pp）、Sprint 49（無 spacing.line snap → 02 爆 +3.61pp）兩次 snap 全域實驗翻車。
- 規劃書 §11.16 三條路線，使用者選 **路線 A：商業化先行**。
- 路線 A = Phase 7 產品打磨（規劃書 §5 Phase 7：大文件虛擬化、Web Worker、IndexedDB 快取 AST）。
- 專案紀律：Sprint 36 / 43 / 46 / 49 都先純診斷再動手。效能優化同理——**不知瓶頸在哪就優化，等於 Sprint 33-35 的假設先行**。本 sprint 先建基線。

## 2. 技術細節：量測方法

### 2.1 instrumentation（純加性、零 core 改動）

[tools/visual_regression_pipeline.entry.ts](../tools/visual_regression_pipeline.entry.ts) 的 `render()` 加四段 `performance.now()` 計時，`RenderResult` 加純加性欄位 `timing: PipelineTiming`：

| 段 | 量測範圍 |
|---|---|
| `parseMs` | `OoxmlParser.parse(arrayBuffer)` — docx zip 解壓 + XML → Document AST |
| `layoutMs` | `layoutDocument(sections)` — AST → DocumentLayout（斷行、表格排版、分頁） |
| `preloadMs` | `preloadImages(media)` — media dataURL → HTMLImageElement（含瀏覽器 image decode） |
| `renderMs` | 逐頁 render loop — `CanvasRenderer.render` → `BrowserCanvasRenderContext` 繪圖 |

VR v14 只讀 `pageCount`/`warnings`，新欄位不影響它。IIFE rebuild 後 **VR 重跑 = 0.0749，全 6 分類與 Sprint 49 byte-identical**（第八層紀律確認 instrumentation 對渲染零影響）。

### 2.2 量測腳本

新建 [scripts/perf_baseline.mjs](../scripts/perf_baseline.mjs)：共用 VR 的 IIFE bundle + harness HTML，每份 fixture 跑 3 次取 `totalMs` 中位數那一筆（避開 JIT 冷啟動 / GC 抖動）。輸出 [tests/fixtures/perf_baseline_report.json](../tests/fixtures/perf_baseline_report.json)。

## 3. 現況：42 fixture 基線數據

### 3.1 分類聚合（median 加總）

| 分類 | n | totalMs | parse% | layout% | preload% | render% |
|---|---|---|---|---|---|---|
| 01_simple | 7 | 1083.0 | 59.2% | 3.2% | 0.0% | 37.6% |
| 02_std_table | 8 | 1163.7 | 72.3% | 1.2% | 12.7% | 13.8% |
| 03_complex_table | 8 | 639.8 | 67.8% | 2.1% | 11.4% | 18.6% |
| 04_with_image | 6 | 2002.2 | 41.1% | 0.7% | 17.9% | 40.3% |
| 05_header_footer | 10 | 1949.3 | 70.1% | 2.5% | 0.0% | 27.4% |
| 06_template | 3 | 290.7 | 76.4% | 2.1% | 0.0% | 21.5% |

### 3.2 全域瓶頸（42 fixture median 加總占比）

| 段 | ms | 占比 |
|---|---|---|
| **parseMs** | **4326.2** | **60.7%** ← 瓶頸 |
| renderMs | 2091.7 | 29.3% |
| preloadMs | 580.0 | 8.1% |
| layoutMs | 130.8 | 1.8% |

### 3.3 最慢 5 份

| fixture | totalMs | 檔案 | 頁數 |
|---|---|---|---|
| 04_with_image/06.環清表...112.10.23.-10.27 | 645.3 | 1405KB | 6p |
| 04_with_image/06.環清表...112.10.9.-10.13 | 446.0 | 1880KB | 6p |
| 04_with_image/6.環清表...112.10.2.-10.6 | 293.9 | 2127KB | 6p |
| 04_with_image/6.環清表...112.9.25.-9.29 | 281.3 | 1984KB | 6p |
| 05_header_footer/自主檢查表---植栽 | 259.0 | 42KB | 4p |

## 4. 爭議點 / 反直覺發現

### 4.1 parse 成本 ≠ 檔案大小（最重要發現）

| fixture | 檔案 | parseMs |
|---|---|---|
| 02_std_table/1120928-...週報 | **1860KB** | 147.6 |
| 05_header_footer/自主檢查表---植栽 | **42KB** | **187.2** |
| 05_header_footer/自主檢查表---地坪鋪面 | 43KB | 175.8 |

**44× 大的檔案 parse 時間反而更短。** → parse 瓶頸**不是** zip 解壓或 media 位元組數，而是 **XML 結構複雜度（element 數、巢狀深度）**。自主檢查表 / 監造會議記錄有大量巢狀表格 → XML 節點多 → parse 慢。這推翻了「大文件才慢」的直覺，也決定 Sprint 51 不該往「streaming unzip」方向走，而要 profile parse 內部（zip unzip vs XML DOM parse vs AST walk 三段細分）。

### 4.2 render 在 image-heavy fixture 爆量

`04_with_image/06.環清表...10.23-10.27`：render 469.1ms（6 頁、單頁 78ms）。其餘 image fixture render 56-140ms。→ render 成本對「每頁照片數」高度敏感（`CanvasRenderer.drawImage` × 大照片）。但最大頁數僅 6p，虛擬化在當前 fixture 規模收益有限。

### 4.3 layout 僅占 1.8% — Sprint 43-49 動的是最便宜的段

七個 sprint 的 layout engine 收斂工作，全程在占比 1.8% 的段上施工。這不是說那些 sprint 沒價值（VR 0.1128 → 0.0749 是視覺正確性，與效能正交），但**效能優化完全不該碰 layout**。

## 5. 結論：Sprint 51 候選排序（資料驅動）

| 候選 | 打中的段 | 槓桿 | 風險 | 建議 |
|---|---|---|---|---|
| **IndexedDB 快取 parsed AST** | parse + layout = **62.5%** | 重開未改動文件 → 直接跳過 parse+layout | 低（AST 由 docx bytes 決定，可用 hash 當 key） | 🟢 **Sprint 51 首選** |
| **Web Worker 跑 parser** | parse 60.7% | 不縮短 parse，但移出主執行緒 → UI 不凍 | 中（worker 訊息序列化 AST 成本待測） | 🟢 Sprint 52 |
| parse 內部 profile + 優化 | parse 60.7% | 找 XML DOM parse vs AST walk 真瓶頸 | 中（需再一個診斷 sprint） | 🟡 Sprint 53 候選 |
| 可視頁虛擬化 | render 29.3% | 只渲染可視頁 ±2 | 低 | 🟡 收益隨頁數放大，當前 fixture ≤6p 收益小；待有 50+ 頁 fixture 再做 |
| image decode 優化 | preload 8.1% + render | image-heavy 文件 | 中 | 🟡 低優先 |

**建議 Sprint 51 = IndexedDB AST 快取**：打中 62.5%（parse+layout）、風險最低、對「同一份文件反覆開啟編輯」的真實使用情境收益最大。Web Worker（Sprint 52）解決首次開啟的 UI 凍結。虛擬化收益隨頁數放大，但當前 fixture 最多 6 頁、payoff 小，應待蒐集大文件 fixture 後再做。

## 6. vitest / VR

- vitest **866 passed + 1 skipped**（無變動 — 本 sprint 不碰 core code 與 test）。
- VR v14：**0.0749（維持 Sprint 48/49 baseline）**，6 分類與 Sprint 49 byte-identical。IIFE rebuild 的 timing instrumentation 為純加性、對渲染零影響。
- Sprint 12/16 baseline 未變動。

## 7. 工作摘要

```
M  tools/visual_regression_pipeline.entry.ts | render() 加 4 段 performance.now() 計時 + RenderResult.timing 純加性欄位
M  tools/dist/visual_regression_pipeline.iife.js(.map) | rollup rebuild（含 timing；VR 重跑 0.0749 確認渲染零影響）
+  scripts/perf_baseline.mjs                 | 42 fixture 效能基線量測 harness（共用 VR IIFE，每份 3 次取中位數）
+  tests/fixtures/perf_baseline_report.json  | 基線數據（診斷保留）
+  docs/sprint50_perf_baseline.md            | 本文件
```

VR v14：**維持 0.0749 baseline**。vitest 866 passed + 1 skipped。

## 8. Sprint 43-50 軌跡

| Sprint | 類型 | 關鍵 |
|---|---|---|
| 44 | 落地 | image-only line baseline — VR 0.1128 → 0.0955 |
| 45 | 落地 | trHeight omitted-hRule = atLeast — -1.81pp |
| 46 | 翻車 revert | exact 不 snap 全域 → 04 爆 |
| 47 | 架構 | naturalUnsnapped 基礎建設 |
| 48 | 落地 | image 列 honors trHeight val — -0.24pp |
| 49 | 翻車 revert | 無 spacing.line snap 全域 → 02 爆 |
| **50** | **純診斷（轉路線 A）** | **效能基線：parse 占 60.7% 為瓶頸；parse 成本由 XML 結構複雜度主導非檔案大小；Sprint 51 首選 IndexedDB AST 快取** |

**心得**：Sprint 50 是專案首個「效能 sprint」，但延續一貫紀律——Sprint 36/43/46/49 教的「先診斷再動手」同樣套用在效能。基線數據翻案了兩個直覺：(1) 大文件才慢 ❌（parse 由結構複雜度主導）、(2) layout 是重點 ❌（僅 1.8%）。沒先量測就做虛擬化，會是又一次假設先行。

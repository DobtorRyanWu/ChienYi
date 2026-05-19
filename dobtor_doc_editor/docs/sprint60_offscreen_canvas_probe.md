# Sprint 60 — OffscreenCanvas + Web Worker render 可行性 probe（純診斷）

**期間**：2026-05-15 → 2026-05-16
**主軸**：Sprint 59 確認單執行緒 render 漸進優化邊際遞減；Sprint 60 候選 OffscreenCanvas + Web Worker render 為高風險改造（render code 重寫、Safari < 16.4 不支援、puppeteer 行為差異）。本 sprint 沿襲 Sprint 36/43/46/49 純診斷模式 — **不改 production code，只收集事實給 Sprint 61 commit OffscreenCanvas worker vs pivot HarfBuzz 做依據**。
**結論**：**OffscreenCanvas + Web Worker 在 puppeteer/Chromium 環境技術可行性 GREEN**（feature detection 全綠、postMessage overhead ~5ms、transferControlToOffscreen 成功、worker paint ~7ms）；但 **Sprint 61 commit 仍建議 pivot HarfBuzz** — 因為 (1) Safari < 16.4 production user 占比未知、(2) render 重寫 3-5 sprints 工程量大、(3) 真正 payoff 是「UI responsiveness 主執行緒不阻塞」puppeteer 量不到、(4) HarfBuzz 提供預測收益 VR mean -1~2pp 與 perf 路徑正交、(5) Sprint 50-59 cache 路徑已收割完 wall-clock 7.01× 接近單執行緒上限、現在攻 VR 視覺品質比攻 perf wall-clock 對 ChienYi production 價值更高。
**Sprint 61 建議**：**HarfBuzz / opentype.js 真實字型 metric**（layout-side、低風險、預估 VR mean -1~2pp）；OffscreenCanvas worker 留 Sprint 62+ 作為「VR 收斂後的下一階段攻關」。

---

## 1. 動機 / 探測範圍

Sprint 59 audit §5 重新評估後 Sprint 60 候選兩條都高風險：

| 選項 | 風險 | 預估 sprint 數 | 預估 payoff |
|---|---|---|---|
| OffscreenCanvas + Web Worker render | 高（render 重寫、Safari 相容、puppeteer 行為差異）| 3-5 | UI 不阻塞（puppeteer 量不到）|
| HarfBuzz / opentype.js | 中（bundle size、字型檔分發）| 1-2 | VR mean -1~2pp |

直接 commit 任一條都可能在 mid-sprint 發現環境不支援、需要 revert（Sprint 57 教訓）。本 sprint **先做 probe + 收集事實**，再讓 Sprint 61 走得乾淨。

## 2. 探測項目

[`scripts/offscreen_canvas_probe.mjs`](../scripts/offscreen_canvas_probe.mjs) 在 puppeteer 環境執行三組檢測：

### 2.1 Feature detection

| API | puppeteer/Chromium 結果 |
|---|---|
| `typeof OffscreenCanvas` | ✓ |
| `'transferControlToOffscreen' in HTMLCanvasElement.prototype` | ✓ |
| `typeof Worker` | ✓ |
| `typeof createImageBitmap` | ✓ |
| User-Agent | Chrome (puppeteer bundled) |

→ **puppeteer 環境 4/4 features 支援**。技術可行性 GREEN。

### 2.2 Worker prototype（postMessage round-trip + transfer）

| 量測 | 結果 |
|---|---|
| Worker 建構 + ping/pong | **18.60ms**（含 worker spawn 啟動成本一次性）|
| transferControlToOffscreen | ✓ |
| Worker paint 簡單 fillRect × 2 到 OffscreenCanvas | **6.60ms** |

→ postMessage 機制可運作；worker 確實可 paint 到 OffscreenCanvas，輸出可見於主 canvas（同 buffer）。

### 2.3 Render benchmark（main-thread vs worker simulated）

量測 1 fixture（02_std_table 週報 2p）跑 5 次取中位數：

| 路徑 | wall-clock |
|---|---|
| Main-thread 完整 pipeline | **166.60ms**（cold path、含 parse + layout + preload + render）|
| Worker simulated render（500 fillRect + 100 fillText 模擬 workload）| **8.30ms total**（worker 內 3.80ms + postMessage overhead 4.50ms）|

⚠️ **這兩個數字不能直接比 — workload 不同**：
- Main-thread 跑完整 pipeline（parse XML + layout 排版 + 千次 fillText）
- Worker 跑簡化 500 fillRect + 100 fillText（沒 parse、沒 layout）
- 真正可比的「完整 pipeline 在 worker 內 vs main thread」需要 Sprint 61 工程實作（把 IIFE bundle 整個 import 到 worker scope）

**可推論的事**：
1. postMessage overhead per render call ≈ 4-5ms（極小）
2. Worker 內 canvas op 效能與主執行緒同階（500 ops 3.8ms）
3. Worker 啟動成本 ~18ms 是一次性（可 long-lived worker 攤平）
4. 完整 pipeline 在 worker 內預估 wall-clock = 主執行緒 - 主執行緒 GC/UI blocking 影響 + 4-5ms postMessage overhead

## 3. Sprint 61 commit 決策分析

### 3.1 commit OffscreenCanvas worker 的優劣

**✅ 好處**：
- 主執行緒空閒給 UI（user 滾動 / 編輯期間不卡）
- 跨多核（多份 docx 並行 render）
- Sprint 59 path coalescing 的 flushPath 介面已為 worker postMessage protocol 打底

**❌ 壞處**：
- **render code 重寫** — CanvasRenderer + BrowserCanvasRenderContext + entry.ts 都需要 worker-compatible 版本（無 DOM 依賴、無 document/Image 等）
- **Safari < 16.4 不支援 transferControlToOffscreen** — 雖然 2026 年市占降低，但 ChienYi 用戶若用舊 iPad / 公文系統內嵌 webview 仍受影響；需要 fallback 路徑（在主執行緒 render）
- **puppeteer 行為差異** — probe 證實 puppeteer 支援，但生產環境 Safari/iOS WebView 行為可能與 puppeteer 不同
- **3-5 sprints 工程量**：
  1. 拆 BrowserCanvasRenderContext 為 worker-safe 版（無 HTMLImageElement / Image global）
  2. 設計 postMessage protocol（docx + media + options → 渲染結果）
  3. 主執行緒 fallback 路徑（feature detection 不支援 → 退主執行緒）
  4. 整合 Sprint 56 ImageBitmap IDB cache（worker 端能存取嗎？）
  5. VR 重跑（worker render 是否 byte-identical？預估 sub-pixel 差異微 jitter）
- **真正 payoff（UI 不阻塞）puppeteer 量不到** — 必須在真實瀏覽器跑互動測試才能驗證
- **與 ChienYi production 需求對齊度低** — 目前 user 痛點不是「render 期間 UI 卡」（warm 1346ms / cold 9430ms 已可接受），而是「視覺品質還沒到 OnlyOffice / Google Docs 等級」

### 3.2 pivot HarfBuzz 的優劣

**✅ 好處**：
- **預估 VR mean -1~2pp**（0.0749 → ~0.057-0.067）— 視覺品質首次直接攻關
- **layout-side change** — 不動 render path、不破壞 Sprint 57 教訓
- **與 perf 路徑正交** — Sprint 50-59 perf 已到頂；現在攻 VR 是新主軸
- **FontMetricsAdapter 已存在** — `static/src/core/layout/FontMetricsAdapter.ts` 已有 `registerFont` API + opentype.js 整合骨架，Sprint 60+ 只需把它接入 layout pipeline
- **1-2 sprints 工程量**

**❌ 壞處**：
- **bundle size 增加** — 需要至少 1-2 個字型檔（標楷體 / Times New Roman 各 ~600KB-2MB）；可以做按需 load
- **字型授權** — 商用字型有授權問題，需用開源替代（Noto Sans CJK、思源黑體）
- **CJK shape async 仍不支援** — `FontMetricsAdapter.measureWidth` 還是 fallback EstimateMetrics（HarfBuzz shape 是 async、無法 sync 接入 Layout）
- 主要只解 measureLineHeight（行高）這條軸；advance width 仍是估算
- 對表格密集 fixture（02 週報、03 全套管）的 VR mean 改善程度未實測（可能 -1pp、可能 -3pp，需 prep test）

### 3.3 建議：Sprint 61 = HarfBuzz

**理由**：
1. **單執行緒 perf 已到頂** — Sprint 50-59 從 1.0× 推到 7.01× 已收割完 cache 路徑、wall-clock 接近單執行緒上限
2. **VR mean 視覺品質是 ChienYi 商用價值更大的軸** — user 看到的是「文件像不像 Word」，不是「文件多快開」
3. **HarfBuzz 路徑風險可控** — opentype.js 整合骨架已存在；Sprint 61 工程量集中在 (a) 選字型 (b) bundle 策略 (c) 接入 pipeline (d) 量 VR 改善
4. **Sprint 62+ 再考慮 OffscreenCanvas worker** — Sprint 60 probe 已證實技術可行；可在 VR 收斂後再投資 perf 收割；屆時 ChienYi production 的 Safari 用戶占比也可以實測
5. **Sprint 57 教訓延伸**：寧可選風險可控、payoff 預測準的路徑，也不要選風險高、payoff 不確定（worker UI 改善 puppeteer 量不到）的路徑

## 4. Sprint 60 outputs

### 4.1 Probe 報告

[`tests/fixtures/offscreen_canvas_probe_report.json`](../tests/fixtures/offscreen_canvas_probe_report.json)：完整 feature detection + worker prototype + render bench 結果（JSON 給後續 sprint 參考）。

### 4.2 Sprint 61 計劃骨架

**Sprint 61 = HarfBuzz / opentype.js 真實字型 metric**：

1. 選字型：開源 + 涵蓋 ChienYi 文件常見字（標楷體 fallback = Noto Sans TC、Times New Roman fallback = Liberation Serif）
2. Bundle 策略：lazy load `assets/fonts/*.woff2` 由 portal 端按需請求（避免 IIFE 主 bundle 增加 2-5MB）
3. 接入 FontMetricsAdapter：layout pipeline 入口接收 adapter；harness 預先 register
4. 量 VR mean 改善：subset 5 fixture → 確認 ≥1pp 改善才擴展全 42
5. Sprint 12 fingerprint 預期會變（行高變了、layout 變了）— 重 record baseline
6. Sprint 16 page count baseline 可能跨更多 fixture（行高變 → 分頁變）— 重 baseline

### 4.3 OffscreenCanvas worker 留待 Sprint 62+

Probe 已證實技術可行；Sprint 62+ 可重新評估，屆時：
- Sprint 61 HarfBuzz 已落地、VR mean 應 -1~2pp
- 主要 perf 軸（cache、layout、render fast path）都收割完
- 可重新評估 Safari 用戶占比（ChienYi production 數據）
- Worker 改造可基於 Sprint 60 probe 數據 + Sprint 59 flushPath 介面開工

## 5. vitest / VR

本 sprint **無 production code 變動**：
- vitest 953 passed + 1 skipped（與 Sprint 59 相同）
- VR per-page mean 0.074899（與 Sprint 59 相同 — 未跑新 VR）
- Sprint 12/16 baseline 未變

純診斷 sprint — 沒有需要驗證的程式碼修改，只新增了 probe 腳本（不影響 production / VR / vitest）。

## 6. Sprint 50-60 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51-55 | cache 五連發 | warm 5.32× | 命中 |
| 56 | L2 IDB image | preload L1 105.74× / L2 2.79× | 跨 session image |
| 57 | render memoize（aggressive 翻車） | +1.04× | 第八層紀律 |
| 58 | layout cache | +0.65× / 100% hit | cache 完成 deterministic 階段 |
| 59 | drawLine path coalescing | ≈0 噪音內 | 單執行緒 render 邊際遞減 |
| **60** | **OffscreenCanvas probe（純診斷）** | **技術可行 ✓ / Sprint 61 = HarfBuzz** | **perf 路徑到頂、轉攻 VR 視覺品質** |

## 7. 工作摘要

```
+  scripts/offscreen_canvas_probe.mjs            | OffscreenCanvas + Web Worker 可行性 probe（feature detection + worker prototype + simulated render bench）
+  tests/fixtures/offscreen_canvas_probe_report.json | probe 量測結果
+  docs/sprint60_offscreen_canvas_probe.md       | 本文件
```

無 production code、無新 unit test、無 VR / vitest 變動。

## 8. 心得：純診斷 sprint 的紀律價值

Sprint 60 沿襲 Sprint 36/43/46/49 模式 = **不改 production code，只收集事實給下個 sprint 做決策依據**。

- Sprint 36 grid analysis → Sprint 37 cell-internal anchor（修對方向）
- Sprint 43 photo Y trace + Pillow → Sprint 44 image-only baseline=height（突破）
- Sprint 46 A2 假設實測 → Sprint 47 val-as-min naturalUnsnapped 基準（架構正確修法）
- Sprint 49 docGrid snap 全域實驗 → Sprint 50 轉商業化先行（路線 A）
- **Sprint 60 OffscreenCanvas probe → Sprint 61 HarfBuzz**（捨 perf 收割、轉攻 VR 視覺品質）

每次純診斷 sprint 都讓下個 sprint 走得乾淨。Sprint 57 教訓「unit 綠 ≠ VR 綠 → 強制全 VR」也應該升級為 **「高風險改造前先 probe 收集事實，再 commit」**。本 sprint 是這條紀律的執行範例。

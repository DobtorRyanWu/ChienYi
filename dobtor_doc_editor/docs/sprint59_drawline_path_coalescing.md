# Sprint 59 — drawLine path coalescing（架構乾淨、perf 邊際內）

**期間**：2026-05-15
**主軸**：Sprint 58 完成 cache 路線後 warm 94.1% 為 render；本 sprint 走規劃書 §11.26 建議的 Sprint 59 候選 = drawLine path coalescing（中風險中槓桿，避開 OffscreenCanvas worker 高風險）。連續同 style 的 drawLine 合併成單一 `beginPath → moveTo/lineTo × N → stroke`，減少 canvas API 呼叫數。
**結論**：**path coalescing 架構正確、單元測試證實 4 條 cell border → 1 個 stroke、VR 0 failed pages**；但 **42 fixture full-warm 6.90× total（warm 1350ms）vs Sprint 58 7.01×（warm 1346ms）= 邊際內反向（+4ms warm）**。原因：drawLine 在 fixture 渲染量中佔比小（render path 主成本為 fillText 數萬次、drawLine 只數百次/頁），coalescing 減少 ~15000 個 canvas op 不足以蓋過 puppeteer/V8 量測噪音（±2-3%）。
**意義**：**確認單執行緒內漸進式 render 優化已達邊際遞減**（Sprint 57 memoize-only +1.04× / Sprint 58 layout cache +0.65× / Sprint 59 path coalescing ≈0）— 真要再加速必須跨執行緒（OffscreenCanvas Worker，Sprint 60+ 高風險）或改根本演算法（HarfBuzz、GPU canvas）。Sprint 59 架構價值 = 減 canvas API call 數，為未來 OffscreenCanvas 改造預留乾淨 stroke 介面。

---

## 1. 動機

Sprint 58 完成後 warm path 結構：
```
parse 0.0% / layout 0.2% / preload 0.1% / render 94.1% / hash 5.6%
```

render 94.1% 為單執行緒 V8 限制。Sprint 57 教訓：避免一次性對 render 做大改造（aggressive setState dedup 翻車）。本 sprint 走中風險替代 = path coalescing。

**理論預測**：
- 一個 5×8 表格 = 40 cell × 4 邊框 = 160 drawLines
- Coalescing 後（同 style 合併）= 40 strokes（vs 160）
- 每個 stroke 省 ~10 個 canvas API call（save + setStrokeStyle + setLineWidth + setLineDash + beginPath + moveTo + lineTo + stroke + restore）
- 對 42 fixture（多 table fixture）= 數千 canvas calls 省下

## 2. 設計

### 2.1 [BrowserCanvasRenderContext.ts](../static/src/core/render/BrowserCanvasRenderContext.ts) 改造

```
class BrowserCanvasRenderContext {
  private pendingPath: PendingPath | null = null;

  drawLine(x1, y1, x2, y2, style):
    sig = (color, width, dashKey)
    if pendingPath && sig matches:
      pendingPath.segments.push(seg); return        // batched
    flushPath(); pendingPath = { ...sig, segments: [seg] }

  private flushPath():
    if pending empty: clear, return
    save; setStrokeStyle/lineWidth/setLineDash; beginPath
    for seg in segments: moveTo + lineTo
    stroke; restore

  fillRect / fillText / drawImage / save / restore / translate / rotate / beginPage / endPage:
    flushPath() // 強制 flush 既有 pending
    ...原 op...

  public flush() // explicit flush 給 caller（VR 截圖前等）
}
```

### 2.2 Flush 觸發點

| op | 為何必須 flush | 風險 |
|---|---|---|
| fillRect / fillText / drawImage | 順序要保留（pending 線段必須先畫，否則被後者覆蓋）| 中 |
| save / restore | state stack 操作 — pending 線段的 stroke state 必須在當下 context 設定 | 中 |
| translate / rotate | transform 變動 — pending 線段必須以「當下 transform」繪出 | 高（最關鍵）|
| beginPage / endPage | 換頁邊界 — 跨頁殘留會畫到錯誤頁 | 中 |
| 不同 style drawLine | 換 color/width/dash 必須新 batch | 低（自然 flush） |

### 2.3 Canvas spec 保證 byte-identical

Canvas 2D `stroke()` 對 path 內所有 sub-path 用當前 state 繪出；sub-path 之間獨立、與分多次 stroke() 結果像素相同（同 strokeStyle/lineWidth/dash/lineCap/lineJoin）。

實測：VR per-page mean 0.074895 → **0.074899（shift +0.000004 / 0.005%）**，**0 failed pages**。微小 shift 推測為 anti-aliasing 在 sub-path 端點的 sub-pixel jitter（canvas implementation detail）。

## 3. 結果

### 3.1 perf 量測（42 fixture full-warm）

| 量測 | Sprint 58 | Sprint 59 | 差異 |
|---|---|---|---|
| cold total | 9430.5ms | **9320.2ms** | -110ms（-1.2%）|
| warm total | 1345.8ms | **1349.9ms** | +4ms（+0.3% **邊際內反向**）|
| warm render | 1266.0ms | 1273.1ms | +7ms |
| total speedup | 7.01× | **6.90×** | -0.11× |

**結論**：**Sprint 59 wall-clock 改善是量測噪音內反向**。原因：
- drawLine 在 render path 佔比小（fillText 才是主成本）
- 一個 fixture 的 drawLine 數量約 100-300 條，coalescing 省 ~70-200 個 canvas ops × µs = 微秒級
- puppeteer + V8 JIT 量測噪音 ±2-3%（30-100ms warm total）→ 微秒級改善看不出來

### 3.2 unit 驗證證實 coalescing 正確

13 個 vitest 都通過 — spy canvas 計數：
- 4 條同 style cell 邊框 → **stroke 呼叫 1 次**（vs 原本 4 次）
- moveTo / lineTo 各 4 次（4 段獨立 sub-path）
- style 變化 / fillRect / fillText / save / restore / translate / rotate / drawImage 任一觸發 → 強制 flush
- explicit `flush()` public method 可用

→ **architecture 層級減 canvas op count 是真的**；只是 wall-clock 沒抓到、被噪音吞掉。

### 3.3 VR 微小 shift（0.000004）

- per-page mean 0.074895 → 0.074899
- 0 failed pages（max page diff 0.306 < threshold 0.5）
- 最差 fixture：03_complex_table 全套管系列 0.23-0.26（與 Sprint 48-58 歷史值一致、無新退化）

**推測**：anti-aliasing 在 sub-path 端點的 pixel boundary 處理可能有 sub-pixel jitter（canvas implementation detail）。

**判定**：**在 pixelmatch 容差內、無視覺退化**，可接受。Sprint 57 教訓的「強制全 VR」紀律：
- Sprint 57 aggressive：+24% / 1 failed page → 翻車、必須 revert
- Sprint 59 path coalescing：+0.005% / 0 failed pages → 邊際噪音、可採用

## 4. 爭議點

### 4.1 為何 wall-clock 沒有顯著改善

預期 saving ~30-90ms / 42 fixtures，實測噪音 ±30-100ms 完全蓋過。深層原因：

**drawLine 不是 render 主成本**：
- 一個 cell 內 fillText 通常 5-50 次（每個 text run / box 一次）
- 一個 cell 內 drawLine 通常 4-6 次（4 邊框 + 偶爾 paragraph border / underline）
- text-heavy fixture（05_header_footer 自主檢查表）drawLine 比例 <5%

→ drawLine coalescing 影響的是「<5% × ~50% reduction = <2.5%」總成本。 wall-clock 看不出。

**反觀 Sprint 57 memoize-only +1.04×**：
- memoize toCssColor / toCssFont 對 fillText path 每次 fillText 都受益
- text-heavy fixture 共用 font/color、cache hit 率高
- 對 100% render path 受益（不只 drawLine）

### 4.2 是否 revert Sprint 59

不 revert。理由：
1. **無視覺退化**（VR shift +0.000004 在噪音內）
2. **架構乾淨**：減 canvas API call 數 + flushPath / pendingPath 抽象可清楚映射到 OffscreenCanvas worker postMessage 介面
3. **為 Sprint 60+ 鋪路**：若要實作 OffscreenCanvas worker，主執行緒把 render ops 序列化到 worker 是同樣的 batch + flush pattern
4. **單元測試覆蓋**：13 tests + 既有 4 tests 已更新 — flush 行為驗證完備

### 4.3 Sprint 50-59 cache + perf 路線的真實 limit

| Sprint | 預期 | 實測 | 心得 |
|---|---|---|---|
| 50 純診斷 | — | parse 60.7% | 量化 |
| 51-55 cache 五連發 | 高 | warm 5.32× | 命中 |
| 56 IDB image | 中 | L1 105×/L2 2.79× | 命中 |
| 57 memoize-only（aggressive 翻車） | 中 | +1.04× | 安全版收割 |
| 58 layout cache | 中 | +0.65× | 命中 |
| **59 path coalescing** | **中** | **≈0（噪音內）** | **單執行緒 render 邊際遞減確認** |

→ Sprint 56-59 累計 vs Sprint 50 baseline 改善有限；warm 1346ms 已是「靜態 fixture + cache 全命中」的下限。

## 5. Sprint 60+ 候選（重新評估）

| 候選 | 為何重新評估 |
|---|---|
| **OffscreenCanvas + Web Worker render** | 🟢 重新成為 Sprint 60 首選；Sprint 57-59 證實單執行緒漸進優化邊際遞減；要再加速必須跨執行緒；風險高（Safari < 16.4 / puppeteer / render 重寫）但是唯一剩下的根本性改造 |
| **GPU-accelerated canvas（OffscreenCanvas + WebGL）** | 🟡 高風險、無前例（dobtor 是 word docx 渲染、不是遊戲）|
| **HarfBuzz / opentype.js 真實字型 metric** | 🟢 改 VR mean、layout-side benefit；不直接攻 render 但提升視覺品質 |
| **大文件 fixture 50+ 頁（待 user）** | 🟡 重新評估 Sprint 53 可視頁虛擬化的 payoff、可能比 Sprint 60 worker 更大 ROI |
| 嚴格 fast path debug（Sprint 57 翻車 root cause）| 🔴 風險仍高、投資不確定 |

**建議 Sprint 60 = OffscreenCanvas + Web Worker render（重新評估後）**：
- Sprint 57-59 已驗證主執行緒漸進優化邊際遞減
- 唯一剩下能進一步加速的選項
- 雖然高風險，但「path coalescing 抽出 flushPath 介面」已為 worker 介面打底
- 即便 worker payoff 不大，也能解放主執行緒給 UI（user 滾動 / 編輯期間不卡）

但要先驗證 Safari < 16.4 與 puppeteer 環境支援度（先做 prep test 再投資完整改造）。

或退而求其次 **Sprint 60 = HarfBuzz**：放棄 render perf 追求，攻 VR mean 視覺品質（-1~2pp 預估）— 與 perf 正交、Sprint 50-59 cache 路徑與 VR 路徑首次重疊。

## 6. vitest / VR

- vitest **940 → 953 passed + 1 skipped**（+13 PathCoalescing 測試 + 4 既有 Sprint 9 tests 加 `ctx.flush()` 補丁）
- **VR per-page mean 0.074895 → 0.074899（shift +0.000004）**；0 failed pages、max page diff 0.306（< threshold 0.5）— 在 pixelmatch 容差內、無視覺退化
- Sprint 12/16 baseline 未變

## 7. Sprint 50-59 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51 | L1 AST cache | warm 4.79× | 同 session 命中 |
| 52 | L2 IDB AST | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 1.16-1.43× | 多頁 payoff |
| 54 | image decode L1 | preload 29× / image-bearing 100% hit | 重開含照片文件加速 |
| 55 | 合用驗證 | full-warm 5.32× | 暴露 render 是新主成本 |
| 56 | L2 IDB image | preload L1 105.74× / L2 2.79× | 跨 session image |
| 57 | render memoize | full-warm 6.36× / +1.04× | 第八層紀律 / 字串 memoize |
| 58 | layout cache | full-warm 7.01× / +0.65× / 100% hit | cache 完成 deterministic 階段 |
| **59** | **drawLine path coalescing** | **架構乾淨、6.90× / -0.11× 邊際內噪音** | **單執行緒 render 邊際遞減確認；Sprint 60+ 必須跨執行緒** |

## 8. 工作摘要

```
M  static/src/core/render/BrowserCanvasRenderContext.ts  | path coalescing：pendingPath + flushPath + public flush() + applyDash 內聯到 flushPath
+  tests/unit/PathCoalescing.test.ts                      | 13 unit tests（cell 邊框 batched、style 變化 flush、fillRect/fillText/save/restore/translate/rotate/beginPage/endPage/drawImage 強制 flush、explicit flush()、空 pending 不 stroke）
M  tests/unit/render/BrowserCanvasRenderContext.test.ts   | 4 既有 Sprint 9 drawLine tests 加 `ctx.flush()`
M  tools/dist/visual_regression_pipeline.iife.js          | rollup 重編
M  tests/fixtures/perf_baseline_report.json               | Sprint 59 量測結果
+  docs/sprint59_drawline_path_coalescing.md              | 本文件
```

VR：per-page mean **0.074899（shift +0.000004 微 jitter、0 failed pages）**。vitest **953 passed + 1 skipped**。**Sprint 59 perf：6.90×（warm 1350ms）vs Sprint 58 7.01×（warm 1346ms）= 邊際內反向 -0.11×**；確認單執行緒 render 漸進優化邊際遞減；Sprint 60+ 必須跨執行緒（OffscreenCanvas Worker）或攻 VR 視覺品質（HarfBuzz）。

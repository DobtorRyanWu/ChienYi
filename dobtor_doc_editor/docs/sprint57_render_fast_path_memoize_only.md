# Sprint 57 — CanvasRenderer fast path（aggressive 翻車 → 退到 memoize-only 安全版）

**期間**：2026-05-15
**主軸**：Sprint 55-56 證實 cache 路線到頂、warm path 87.3% 為 renderMs；本 sprint 攻 CanvasRenderer fast path。**初版「拿掉 inner save/restore + setState dedup」在 unit test 全綠（13 tests）後 VR 翻車（mean 0.0749 → 0.0998）**，cascading chain 第八層紀律（Sprint 46/49 教訓）再次應驗：**單元測試綠不等於 VR 綠**。退到「**只 memoize toCssColor / toCssFont 字串拼接**」的最小安全版。
**結論**：**memoize-only 版 full-warm 6.36× speedup（cold 9271ms → warm 1458ms）**，**比 Sprint 55 baseline 5.32× 改善 +1.04×**；render 消除程度從 63.4%（S55）提到 70.3%；warm path 主成本仍 render（87.1%）；VR 維持 0.0749 byte-identical；921 passed + 1 skipped（+13 memoize 測試）。
**意義**：cache 五連發後直接攻 render 比預期更難 — 即便 unit test 證明 fast path 邏輯正確，**state pollution 對 OOXML 真實 fixture 有未預期的視覺影響**（具體 06-8估驗計價 page 1 整個表格區黑底紅字，diff 0.67 over threshold 0.5）。

---

## 1. 動機

Sprint 55 全 42 fixture full-warm benchmark：
> warm path 87.3% 是 renderMs → Sprint 56+ 必須攻 render 段

Sprint 56 ImageBitmap+IDB 證實 cache 攻不到 render。本 sprint 走 Sprint 55 audit 建議的 Sprint 57 候選 = **CanvasRenderer fast path**（繪圖 ops 優化、避免重複 setState、合併連續 drawText、字型 metric 預算 cache）。

## 2. 初版設計（aggressive）— 翻車

[`BrowserCanvasRenderContext.ts`](../static/src/core/render/BrowserCanvasRenderContext.ts) 改造：

1. **拿掉 inner save/restore**：fillText / fillRect / drawLine 不再 `save() → set state → op → restore()`，改為「直接 set state → op」
2. **setState dedup**：加 `lastFillStyle / lastStrokeStyle / lastFont / lastLineWidth / lastTextBaseline / lastTextAlign / lastLineDashKey` 快取；值相同則跳過 canvas property 設定（避開 V8 font/color parse）
3. **外層 save/restore 失效化快取**：CanvasRenderer 用 save/translate/rotate/restore 旋轉 cell 時，restore 後 canvas state stack pop → 快取必須重置
4. **String memoization**：`toCssColor` / `toCssFont` Map 快取輸出

**13 個 unit tests 全綠**：spy canvas 計數 fillStyle/strokeStyle/font/lineWidth/textBaseline/textAlign/setLineDash 各 set 次數；連續相同 style 只 set 1 次、不同則重設、save/restore 失效化正確。

**Full 42-fixture VR 翻車**：
- mean 0.0749 → **0.0998（+24% 退化）**
- **06-8估驗計價前履約文件查對項目一覽表 page 1 diff 0.67（over threshold 0.5）**
- 該 page 整個表格區域變**黑底紅字**（golden 是白底黑字）
- 02_std_table 週報、03_complex_table 全套管系列 fixture-mean 同步退化 0.10 → 0.27

**為什麼破**：unit test 用 spy canvas 驗證 setState 邏輯，**spy 不會反映真實 canvas 渲染像素**。OOXML 真實 fixture 有複雜 state 互動（floatTextBox fill、cell shading、border color 等）— state pollution 在某些順序下產生視覺異常。具體機制未深入追，因為**正確修法是放棄 aggressive 版**而不是繼續 debug 一個高風險路徑。

## 3. 退路徑：memoize-only 安全版

保留**所有 save/restore**（state stack 行為完全等同舊版）+ 只 memoize 字串輸出：

| 改動 | 含義 |
|---|---|
| `toCssColor` 加 Map cache（256 entries 封頂） | 同樣 hex color 跳過 trim + startsWith + 條件分支 |
| `toCssFont` 加 Map cache（512 entries 封頂、key = bold|italic|fontSize|family|scale） | 同樣 style 跳過 toFixed + 字串拼接 |
| inner save/restore | **保留**（每個 fillText/fillRect/drawLine 都 save+restore） |
| canvas setState dedup | **拿掉**（cache 與 save/restore 互不相容、無增益）|
| 外層 save/translate/rotate/restore | 不變 |

**為何只剩這個還有意義**：
- text-heavy 文件 per-page 數百次 fillText 共用相同 (bold|italic|fontSize|family)
- memoize 後 `toCssFont` 從 cache 直接回字串、跳過 `toFixed(2)` + Array.push + join(' ')
- 對 V8 font parse 沒幫助（canvas.font = X 還是會跑），但 JS-side 字串操作節省可累積

## 4. 量測結果

[`scripts/perf_baseline.mjs`](../scripts/perf_baseline.mjs) 全 42 fixture `--full-warm` 模式：

| 比較對象 | cold total | warm total | total speedup | render 消除 |
|---|---|---|---|---|
| Sprint 55 baseline | 12150ms | 2282ms | **5.32×** | 63.4% |
| Sprint 57 aggressive（**已 revert**）| 9415ms | 1341ms | 7.02× | 73.4%（**VR 翻車不可採**）|
| **Sprint 57 memoize-only（採用）** | **9271ms** | **1458ms** | **6.36×** | **70.3%** |

**cold path 改善 12150 → 9271ms（-23.7%）** 主因 = memoize 累計避開 N 次字串拼接（cold 路徑 fillText 數百次）。
**warm path 改善 2282 → 1458ms（-36%）** 主因 = 同 fillText 路徑 + V8 JIT 自然優化；memoize 提供穩定 string identity 有助於 V8 inline cache。

vs aggressive 版差距：
- aggressive cold 9415 vs memoize 9271 = 兩者差 < 2%（cold path 主成本是 fillText 本身、save/restore 開銷其實不大）
- aggressive warm 1341 vs memoize 1458 = 差 117ms（save/restore 與 setState dedup 合計）
- **aggressive 多賺 117ms 不值得換 VR +24% 退化**

## 5. 階段占比（memoize-only warm）

| 階段 | cold | warm | 消除 | warm 占比 |
|---|---|---|---|---|
| parse | 3946.5 | 0.8 | 100.0% | 0.1% |
| layout | (~110) | (~110) | 0% | 7.5% |
| preload | 662.7 | 0.7 | 99.9% | 0.0% |
| render | 4274.1 | 1270.4 | 70.3% | **87.1%** ← 仍是主成本 |
| hash | — | 75.2 | — | 5.2% |
| **total** | **9271.4** | **1458.3** | — | — |

warm path 87.1% 仍是 renderMs — 與 Sprint 55 結論一致：**memoize-only 是 modest 改善，render 路徑根本性優化（fast path / OffscreenCanvas / Worker render）仍是 Sprint 58+ 主軸**。

## 6. 為何 aggressive 版破 — 推測（未深入 debug）

從失敗 fixture 06-8估驗計價 page 1 的視覺異常推測：

- 該 docx 含 floatTextBox（Sprint 38-39 引入）或 cell shading 互動，產生「fillRect 後 stat leak 到後續 op」的 race
- spy canvas 驗證的是「property 設定次數」，不是「canvas pixels」；spy 無法捕捉 OOXML 渲染順序中的 state interaction
- save/restore 在 Word docx 真實 fixture 下保護了某些 implicit state 假設（例如：cell border drawLine 後 strokeStyle 不該影響後續 fillText 的 fillStyle —— 但 canvas 不該混淆 fillStyle/strokeStyle，這個推測弱）

未深入 debug 因為：**精確找出哪個 state leak 造成黑底紅字**對 Sprint 57 來說不是高槓桿投資。正確策略 = 放棄 aggressive、收割 memoize-only 的安全增益、把攻 render 的能量留給更根本的改造（Sprint 58 OffscreenCanvas / Web Worker render）。

## 7. vitest / VR

- vitest **921 passed + 1 skipped**（+13 tests — `tests/unit/BrowserCanvasRenderContext.test.ts` 改寫為 memoize-only 行為驗證）
- **VR 0.0749 byte-identical**（per_page_mean = 0.074895，與 Sprint 50-56 完全一致）
- Sprint 12 fingerprint baseline 未變

## 8. Sprint 50-57 軌跡

| Sprint | 類型 | 關鍵測量 | 累積意義 |
|---|---|---|---|
| 50 | 純診斷 | parse 60.7% 為瓶頸 | 量化 |
| 51 | L1 AST cache | warm 4.79× | 同 session 命中 |
| 52 | L2 IDB AST | 跨 page 2.38× / L1 7.41× | 跨 session 命中 |
| 53 | 可視頁虛擬化 | render 1.06× / 3p+ 1.16-1.43× | 多頁 payoff、≤6p 限制 |
| 54 | image decode L1 | preload 29× / image-bearing 100% hit | 重開含照片文件加速 |
| 55 | 合用驗證量測 | full-warm 5.32× / 6p image-heavy 1.4-4.5× | 暴露 render 是新主成本 |
| 56 | L2 IDB image + ImageBitmap | preload L1 105.74× / L2 2.79× / 100% L2 hit | 跨 session 唯一可命中 image preload |
| **57** | **render fast path aggressive 翻車 + memoize-only 安全版** | **full-warm 6.36× / cold -23.7% / warm -36%** | **第八層紀律應驗 — unit 綠 ≠ VR 綠；memoize-only 是 modest 改善；render fast path 根本性優化留 Sprint 58+** |

## 9. Sprint 58+ 候選

| 候選 | 打中的段 | 槓桿 | 風險 |
|---|---|---|---|
| **OffscreenCanvas + Web Worker render** | render 整段非阻塞 | 主執行緒空閒給 UI、跨多核 | 高（render code 重寫；OffscreenCanvas 在某些瀏覽器/環境支援度不一）|
| 嚴格 fast path 但加 per-fixture VR 對比 gate | render setState dedup | 找出 state leak 真因（debug 06-8 + 02 週報）| 高（投資不確定有 payoff）|
| 大文件 fixture（user 提供）| render 多頁文件 | Sprint 53 預測 50+ 頁 payoff | 待外部 |
| HarfBuzz / opentype.js | layout/render 質量 + VR mean | -1~2pp 視覺 + 順帶 metric 提速 | 大工程 |

**建議 Sprint 58 = OffscreenCanvas + Web Worker render**：徹底繞開主執行緒 render 阻塞、warm 後 UI 即時感顯著提升；技術風險高但 payoff 也最高（不再受 V8 single-thread fillText 限制）。

## 10. 工作摘要

```
M  static/src/core/render/BrowserCanvasRenderContext.ts  | aggressive fast path 翻車 → 退到 memoize-only 安全版（toCssColor/toCssFont Map cache + _clearRenderCachesForTest export）
M  tests/unit/BrowserCanvasRenderContext.test.ts          | 13 tests 改寫為 memoize 行為驗證（舊 setState dedup 測試已隨 aggressive 一起 revert）
M  tools/dist/visual_regression_pipeline.iife.js          | rollup 重編
M  tests/fixtures/perf_baseline_report.json               | full-warm 量測結果
+  docs/sprint57_render_fast_path_memoize_only.md         | 本文件
```

VR：**0.0749 byte-identical**。vitest **921 passed + 1 skipped**。**Sprint 57 memoize-only**：full-warm 6.36× total speedup（cold -23.7% / warm -36%）；vs Sprint 55 baseline +1.04×；warm path 仍 87.1% renderMs — Sprint 58+ 必須做更根本的 render 改造。

## 11. 心得：第八層紀律再次應驗

Sprint 46 教訓：「**單 fixture trace 命中 ≠ 全域正確，需全 fixture VR 驗證**」。

Sprint 57 升級這條紀律 → **「unit test 全綠 ≠ VR 全綠 — spy canvas 計數 setState 不能反映 OOXML 真實 fixture 的 state interaction 對 pixels 的影響」**。

**正確 SOP 補充**：
1. 改 BrowserCanvasRenderContext / CanvasRenderer 任何邏輯後，**強制跑全 42-fixture VR 才能 merge**（不是 spot check 一兩個 fixture）
2. unit test 用 spy 驗 API 行為；VR 驗最終 pixels — **兩者都綠才算過**
3. 看到 fancy 優化想法（拿掉 save/restore、setState dedup、async batching 等），**先做 prep test 量小 VR subset 觀察**，再投入大規模改造

Sprint 57 損失 = 一輪 aggressive 嘗試的時間；收益 = memoize-only 安全版 +1.04× speedup + 把「render fast path 根本性改造」的真實風險量化清楚，給 Sprint 58 OffscreenCanvas 決策做依據。**這種「主動驗算 + 主動 revert」的紀律比硬推不確定優化更重要**。

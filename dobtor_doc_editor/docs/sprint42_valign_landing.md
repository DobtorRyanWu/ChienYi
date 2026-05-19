# Sprint 42 — cell.vAlign='center' / 'bottom' 實作 + Sprint 41 預估翻車

**期間**：2026-05-14
**主軸**：依 Sprint 41 純診斷推測的 root cause 實作 cell.vAlign
**結論**：**Sprint 41 預估翻車（第七次連敗）**。
vAlign 三分支實作 architectural 完整，6 unit test + 1 整合 test 全綠，**但 visual mean 完全持平 0.1127→0.1128**。
真根因（trace 確認）：photo cell `rowHeight=290.9pt ≈ contentHeight=288pt`（tight fit），availableHeight≈281pt < contentHeight=288pt → **vAlign 自動退化為 top fallback（safety mechanism）** — 沒有空間可 center。
Sprint 41 「rowHeight 大於 contentHeight 才有 vAlign 效應」這個前提**未驗證**就直接斷定 vAlign 是 root cause，違反「6 層 cascading chain 全綠才開工」自己訂的紀律。

---

## 1. 規劃 vs 真實

| 規劃預估（高保真書 §11.8） | 真實結果 |
|---|---|
| 04 cat -5pp（0.30 → 0.25）| 04 cat 0.3013 → 0.3014（+0.0001） |
| 02/03 微改善 | 02 +0.0002、03 0 |
| 總體 -1pp 達 mean ≤ 0.10 | 總體 0.1127 → 0.1128（**完全持平**） |

## 2. 實作落地（architectural 100% 完整）

### 2.1 AST / Layout
- [CellLayout](../static/src/core/layout/types.ts) 新增 `contentHeight: Pt` 必要欄位
- [TableLayout.layoutCell](../static/src/core/layout/TableLayout.ts) 把累積的 `contentHeight` 傳進 CellLayout

### 2.2 CanvasRenderer
- 新增 helper `computeVAlignYStart(y, rowHeight, padding, contentHeight, vAlign)` 處理三分支 + 防呆 fallback
- `renderCell` L278 從硬寫 `y + cell.padding.top` 改為呼叫 helper

```typescript
function computeVAlignYStart(y, rowHeight, padding, contentHeight, vAlign) {
  if (vAlign === 'top') return y + padding.top;
  const availableHeight = rowHeight - padding.top - padding.bottom;
  if (contentHeight >= availableHeight) return y + padding.top; // 防呆：無 slack → top
  if (vAlign === 'center') return y + padding.top + (availableHeight - contentHeight) / 2;
  return y + rowHeight - padding.bottom - contentHeight; // bottom
}
```

### 2.3 Vitest 6 unit test + 1 整合 test + 1 debug test

| 測試 | 結果 |
|---|---|
| vAlign=top（預設）text y 接近 padding.top | ✅ |
| vAlign=center text y offset ≈ 92pt（rowHeight=200）| ✅ |
| vAlign=bottom text y offset ≈ 180pt | ✅ |
| vAlign=center + contentHeight ≥ availableHeight → 退化 top | ✅（用 heightRule='exact' h=8pt 觸發）|
| vAlign=center 對 inline image 也下移 ~80pt | ✅ |
| vAlign 不影響 cell 邊框與背景座標 | ✅ |
| 整合 test 對 06.環清表 fixture photo y > 50pt（sanity）| ✅ |
| debug test dump cells dims | ✅ |

**Sprint 12 fingerprint snapshot 未變動**（drawImage / fillText ops 數量及 Y 座標未變 = 確認 photo cell vAlign 沒被觸發）。

## 3. Debug 找 visual 0 改變真因

debug test 對 06.環清表 fixture page 1 dump table 0：

```
table at (85.05, 60.55)
  row 0 h=38.9pt:   cell.vAlign=center  ch=36.0   h=38.9   hasImg=false   <- 標題行 text
  row 1 h=20.9pt:   cell.vAlign=center  ch=18.0   h=20.9   hasImg=false
  row 2 h=20.9pt:   cell.vAlign=center  ch=18.0   h=20.9   hasImg=false (×2 cells)
  row 3 h=20.9pt:   cell.vAlign=center  ch=18.0   h=20.9   hasImg=false (×4 cells)
  row 4 h=290.9pt:  cell.vAlign=center  ch=288.0  h=290.9  hasImg=true   <- photo cell #1
  row 5 h=290.9pt:  cell.vAlign=center  ch=288.0  h=290.9  hasImg=true   <- photo cell #2
```

**關鍵觀察**：所有 cell 都是 `vAlign='center'`，但每個 cell 的 `contentHeight ≈ rowHeight - 2*padding`（極接近）：

| 行 | rowHeight | contentHeight | availableHeight (=rowH-10) | vAlign 效應 |
|---|---|---|---|---|
| 0 | 38.9 | 36.0 | 28.9 | contentHeight(36) > availableH(28.9) → fallback **top** |
| 1-3 | 20.9 | 18.0 | 10.9 | contentHeight(18) > availableH(10.9) → fallback **top** |
| 4-5 (photo) | 290.9 | 288.0 | 280.9 | contentHeight(288) > availableH(280.9) → fallback **top** |

→ **沒有任何一個 cell 的 vAlign 取得空間發揮效應**！

## 4. Sprint 41 失敗模式分析（第七層 cascading chain）

Sprint 41 audit doc §8.2 自己列了 6 層 chain 檢查表，全打勾。但忽略了**第七層**：

7. **修法的 precondition（前提條件）是否在實際 fixture 中滿足？**

vAlign 修法的前提：`rowHeight > contentHeight + padding.top + padding.bottom`。
06 fixture 的所有 cell **都不滿足**這個前提（rowHeight 自動 fit 到 contentHeight + ~3pt padding）。

→ vAlign 修法正確但**沒有觸發路徑**。

## 5. 真根因新假設（待 Sprint 43 驗證）

Sprint 41 pixel sampling 觀察 render 比 golden 高 ~96pt。Sprint 42 trace 確認我們的 row 4 photo cell top 在 y = 60.55 + (38.9 + 20.9 + 20.9 + 20.9) = 162.15pt = 338 px @ 150 DPI。

但 pixel sampling 顯示 render 端照片從 y≈270 px 開始 = 130 pt。**比 trace 預測（162.15pt）還要 30pt 高**。

可能原因：
- A. **Photo Y 不是 cell top + padding**：可能 BoxBuilder/LineBreaker 把 photo Box 的高度算進 baseline 的 ascender，導致 drawImage 的 y = baseline - height 比 cell padding.top 還小
- B. **Row 0-3 累積 row height 在 layout 與實際渲染不一致**（rowHeight 38.9pt 但實際 cell border 在 y=60.55+30 而非 60.55+38.9）
- C. **table y 起點偏差**：60.55pt 可能是錯的（empty paragraph 之前/之後高度誤算）
- D. **Golden 端有 sectPr 沒讀的 setting**（如 docGrid linePitch 360 = 18pt 強制 line snap）

**Sprint 43 建議**：純診斷再一次（與 Sprint 41 相同 pattern）。具體：
1. 對 06.環清表 page 1 render 用 `python3 + Pillow` 找照片實際 top 像素位置（精確到 ±5px）
2. trace renderer ops 找 `drawImage` 對應 photo cell 的 (x, y, w, h) 數值
3. 比對：render trace 的 photo y × 150/72 是否 == 觀察 pixel y
4. 比對：golden 觀察 pixel y × 72/150 → 推算 golden 認為 photo top 應在哪個 pt
5. 此 diff (render trace - golden) 就是真根因偏移源

## 6. Sprint 33-42 失敗總結

| Sprint | 教訓 | 應用？ |
|---|---|---|
| 33 | 不規格先行 | ⚠️ Sprint 41 又規格先行 |
| 34 | 規格意義精確查證 | ✅ |
| 35 | 機制 ≠ 視覺收斂 | ✅ |
| 36 | 資料先行（grid analysis）| ✅ |
| 37 | 修對方向但選錯 type | ⚠️ Sprint 41 漏了 precondition |
| 38 | 修對 type 但選錯細節 | ⚠️ |
| 39 | 修對細節但選錯 hot zone | ✅ |
| 40 | 修對 5 層但選錯 fixture | ⚠️ Sprint 41 未驗證 fixture data 滿足 precondition |
| 41 | 純診斷找 root cause | 但**沒驗證前提**！|
| **42** | **修法的 precondition 必須在實際 fixture data 上驗證才開工** | 本 sprint 即是教訓 |

新失敗模式（第七層）：**修對 6 層但 precondition 不滿足**

實際應該的紀律：Sprint 41 寫出 vAlign 修法後，**先在 vitest 直接針對 06 fixture 跑一個 disable+enable 對照**，確認修法會改變 render output，再正式開工 Sprint 42。

## 7. 工作摘要

```
M  static/src/core/layout/types.ts                       | +14  CellLayout.contentHeight 必要欄位
M  static/src/core/layout/TableLayout.ts                 | +3   layoutCell 兩 path 都傳 contentHeight
M  static/src/core/render/CanvasRenderer.ts              | +32  computeVAlignYStart helper + renderCell 引用
M  tests/unit/render/CanvasRenderer.test.ts              | +110 6 個 Sprint 42 test
+  tests/integration/sprint42_valign_real.test.ts        | new  1 整合 test
+  tests/integration/sprint42_debug.test.ts              | new  1 debug test dump cells
+  docs/sprint42_valign_landing.md                       | 本文件
```

VR v14：**total mean 0.1127 → 0.1128（持平）**；04 mean 0.3013 → 0.3014（持平）；03/05 微 +0.0001 噪音。
Sprint 12/16 snapshot 未變動（render ops 數值 / Y 座標 / page count 都未變）。

## 8. Sprint 43 開工前 checklist（第七層紀律）

新增規則：
- ✅ 6 層 cascading chain 全綠（方向 / 機制 / type / 細節 / 位置 / fixture 涵蓋率）
- ✅ **7. 修法 precondition 在 fixture data 上驗證**（用 debug test 或 trace 工具確認觸發路徑會發生）
- ✅ 連 7 個 sprint 視覺 = 0 的事實放在每個 audit doc 最前面，提醒自己謙卑

Sprint 43 主軸：對 photo Y 偏移 96pt 真根因做**精細 trace**（render op + pixel sampling 雙路徑），先**驗證假設**才開工修。

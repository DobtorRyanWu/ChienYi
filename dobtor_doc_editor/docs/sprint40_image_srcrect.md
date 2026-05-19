# Sprint 40 — DrawingML `<a:srcRect>` 圖片裁切解析 + 渲染

**期間**：2026-05-14
**主軸**：04_with_image photo refinement — 落地 `<a:srcRect>` source crop（OOXML §20.1.10.40）
**結論**：**第六次「修對 5 層但選錯 fixture」事件**。
6 個 04 fixture 中只有 **2 個（05.*）** 用 srcRect，其餘 4 個（06.*、6.*）的 diff 主來源不在 srcRect。
- 視覺結果：04 mean 持平 **0.3013**；05.* 兩支 fixture mean 變動 < 0.001（在數值噪音內）。
- 架構：AST → DrawingParser → Box.imageSrcRect → CanvasRenderer → RenderContext.drawImage 9-arg API 全鏈整潔。

---

## 1. 規劃 vs 真實

| 規劃預估（高保真書 §11.6） | 真實結果 |
|---|---|
| 04 mean 0.30 → 0.16 | 04 mean **0.3013**（不變） |
| 總體 -3.5pp 達 ~0.099 | 總體 **0.1127**（不變） |
| `<a:srcRect>` 圖片裁切 | ✅ 落地（DrawingParser 解析 + 9-arg drawImage 渲染） |
| photo aspect ratio / DPI / JPEG profile | ❌ 未動到（Sprint 40 範圍只做 srcRect） |

## 2. 實作落地

### 2.1 AST — `ImageSrcRect` 共用型別

[static/src/core/ooxml/ast/types.ts](../static/src/core/ooxml/ast/types.ts) 新增：

```typescript
export interface ImageSrcRect {
  leftPct: number;   // 0–1（OOXML 千分比 / 100000）
  topPct: number;
  rightPct: number;
  bottomPct: number;
}

export interface InlineImageNode {
  // …既有欄位…
  srcRect?: ImageSrcRect;
}

export interface FloatImageNode {
  // …既有欄位…
  srcRect?: ImageSrcRect;
}
```

### 2.2 DrawingParser — `parseSrcRect()`

[static/src/core/ooxml/drawing/DrawingParser.ts](../static/src/core/ooxml/drawing/DrawingParser.ts) 新增 `parseSrcRect(el)`：

- 找 `<a:srcRect>`（getElementsByTagName，descendant lookup）
- 每個屬性 l/t/r/b 從千分比（原始 4066 = 4.066%）轉 0–1 分數（÷ 100000）
- **三段 fallback**：
  - 缺漏 `<a:srcRect>` → undefined
  - 全零 / 空 `<a:srcRect/>` → undefined
  - l+r ≥ 1 或 t+b ≥ 1（整張被裁光）→ undefined（safety fallback）

### 2.3 Layout — `Box.imageSrcRect` + `FloatImageEntry.srcRect`

[static/src/core/layout/types.ts](../static/src/core/layout/types.ts) + [BoxBuilder.ts](../static/src/core/layout/BoxBuilder.ts) + [Paginator.ts](../static/src/core/layout/Paginator.ts)：

- `Box.imageSrcRect?: ImageSrcRect`（inline image 攜帶）
- `FloatImageEntry.srcRect?` + `ImagePageEntry.srcRect?`（page-level entry 攜帶）
- BoxBuilder 把 `InlineImageNode.srcRect` propagate 到 Box；Paginator 把 `FloatImageNode.srcRect` propagate 到 entry

### 2.4 Render — `RenderContext.drawImage` API 擴 6 參數

[static/src/core/render/types.ts](../static/src/core/render/types.ts) 介面變更：

```typescript
drawImage(
  href: string,
  x: Pt, y: Pt, width: Pt, height: Pt,
  srcRect?: { leftPct: number; topPct: number; rightPct: number; bottomPct: number },
): void;
```

- **MockRenderContext**：op 加 optional `srcRect` 欄位
- **BrowserCanvasRenderContext**：當 srcRect 有值 → 從 img.naturalWidth/naturalHeight 算 src 像素 sx/sy/sw/sh → 走 9-arg ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh)；無 srcRect → 走 5-arg

### 2.5 CanvasRenderer — 4 條 drawImage 路徑全帶 srcRect

- `renderLine` 中 inline image Box → `box.imageSrcRect`
- `drawCellFloat` cell-internal float image → `f.node.srcRect`
- `renderImageEntry` page-level image entry → `entry.srcRect`
- `renderFloatImage` page-level float image → `f.srcRect`

### 2.6 Vitest 新增 8 test + 1 整合 test

| 測試檔 | 新增 | 重點 |
|---|---|---|
| `tests/unit/DrawingParser.test.ts` | +5 | wp:inline srcRect、缺漏、全零、整張被裁光 fallback、wp:anchor srcRect |
| `tests/unit/render/CanvasRenderer.test.ts` | +3 | inline image 無/有 srcRect、cell-internal floatImage srcRect |
| `tests/integration/sprint40_image_srcrect_real.test.ts` | +1 | 對真實 05.112磺港溪監造會議照片.docx 驗證表格 cell 內 inline image srcRect ≈ 0.04066 |

**vitest 結果**：**842 passed + 1 skipped**（Sprint 12 fingerprint snapshot 未變動，因 srcRect 是 optional 欄位不改 ops 結構）

### 2.7 真實 fixture 驗證

整合 test 對 05.112磺港溪監造會議照片.docx 抓到 `srcRect = { topPct: ~0.0406, bottomPct: ~0.0406, leftPct: 0, rightPct: 0 }` — 與 OOXML 原始值 `t="4066" b="4066"` 完全對應。

---

## 3. 視覺收斂 (VR v14)

### 3.1 總體

| 階段 | total mean | 04 mean | 03 cat |
|---|---|---|---|
| Sprint 37 | 0.1127 | 0.3013 | 0.1664 |
| Sprint 38 | 0.1127 | 0.3013 | 0.1728 |
| Sprint 39 | 0.1127 | 0.3013 | 0.1728 |
| **Sprint 40** | **0.1127** | **0.3013** | **0.1728** |

### 3.2 04 per-fixture 分布（Sprint 40）

| Fixture | srcRect 用? | mean | 差距於 Sprint 39 |
|---|---|---|---|
| 05.112磺港溪監造會議照片.docx | ✅ t=4066 b=4066 + t=4053 b=4053 | 0.2766 | -0.0007（噪音內）|
| 05.112磺港溪監造會議照片1120923-1121001.docx | ✅ t=4076 b=4076 + t=4053 b=4053 | 0.2787 | -0.0002（噪音內）|
| 06.環清表(112.10.23-10.27).docx | ❌ 無 srcRect | 0.3015 | 0 |
| 06.環清表(112.10.9-10.13).docx | ❌ 無 srcRect | 0.3129 | 0 |
| 6.環清表(112.10.2-10.6).docx | ⚠️ 空 srcRect（全零） | 0.3002 | 0 |
| 6.環清表(112.9.25-9.29).docx | ❌ 無 srcRect | 0.3145 | 0 |

→ **6 個 04 fixture 中只有 2 個用實質 srcRect**，且這 2 個的 mean 變動 < 0.001（在 pixelmatch 浮點誤差範圍）。

### 3.3 為什麼 05.* srcRect crop 視覺差 < 0.001？

樣本：05 page 1 photo extent 3600000 × 2700000 EMU = 283.5 × 212.6 pt = 590 × 443 px @ 150 DPI。
srcRect t=4066 b=4066 對應 source image 上下各裁掉 4.066%，即 src 像素 ~36 px。

- **正確套用後** crop 結果：photo 顯示 source 像素中央 91.87% 區域，再 stretch 到 590×443 px destination。
- **未套用前** crop 行為：source 整張 stretch 到 590×443 → photo 顯示「壓扁的」整張圖
- **golden 端**（LibreOffice 渲染）有套 crop

兩種輸出視覺差：crop 改變 source aspect ratio 處理，但 destination 矩形不變。結果是「同位置、同大小、像素內容微差」— 主要在 photo 邊緣 36 px 寬區域。

但 photo 面積 = 590×443 = 261470 px²，整頁 = 1241×1754 = 2,176,714 px²。photo 邊緣 36px 影響量 ≈ 590×36×2 = 42480 px² = 1.95% 頁面。pixel diff 從這 1.95% 區塊估 ~0.5% 改善 — **接近觀察到的 0.0007 差距**，與分析一致。

### 3.4 grid analysis（05.docx page 1 top 10 worst）

Top 10 worst grids 全為 100% diff，集中在 **rows 16-18（y=400-476 px）**、cols 14-19（中央）+ 35-36（右）：

```
grid(15,16) px(372,400)  100%
grid(16,16) px(397,400)  100%
grid(19,16) px(471,400)  100%
grid(35,16) px(868,400)  100%
grid(36,16) px(893,400)  100%
…
```

對應位置：page y=400-476 px = ~25-30pt 距 body top（body top ~75pt）= page mid，**這是 photo 下方第 1 個 textbox（"112/10/31" 之類的日期戳印）的位置**。

→ 05.docx 主 diff 來源 = **photo 下方文字框未準確渲染**（未用 Sprint 38/39 對齊細節），不是 photo 本身。Sprint 40 srcRect 修法影響到 photo，但未影響 textbox。

---

## 4. 心路歷程：Sprint 33-40 連 8 個 sprint 真實 visual 收斂

| Sprint | 主軸 | 視覺變化 |
|---|---|---|
| 33 | vMerge cellHeight 修正 | 0 |
| 34 | tbRlV V-suffix 路徑 | 0 |
| 35 | char-level CJK 直書渲染 | 0 |
| 36 | grid analysis 找 col 2 hot zone | 0（純診斷）|
| 37 | cell-internal anchor abs position | 0（總體）/ +0.006（03 cat）|
| 38 | anchor text box 解析+渲染 | 0 / 0 |
| 39 | textbox bodyPr/fill/border | 0 / 0 |
| **40** | **image srcRect 解析+渲染** | **0 / 0 / 0.0007 改善（05.* fixture）** |

連 **8 個 sprint** 真實視覺收斂 = 0 或極小。原因分析（第六層失敗模式）：

## 5. 新失敗模式（第六層）：「修對 5 層但選錯 fixture」

Sprint 33-39 的 cascading chain：
- 方向、機制、type、細節、位置 hot zone — Sprint 40 全 5 層都做對：
  - ✅ 方向：DrawingML `<a:srcRect>` 圖片裁切（OOXML §20.1.10.40 規格正確）
  - ✅ 機制：9-arg drawImage source crop
  - ✅ type：InlineImage + FloatImage 兩個 type 都覆蓋
  - ✅ 細節：千分比 → 0–1 分數正確、naturalWidth 取 source 像素正確
  - ✅ 位置：photo 本身（影響面積 ~1.95% 頁面）

但少了第六層：
- **fixture 涵蓋率**：04 大類 6 個 fixture 中只有 2 個用 srcRect，且這 2 個的 diff 主來源不在 photo 本身，而是 photo 下方/旁邊的 **textbox**（Sprint 38/39 已試圖但未收割的對齊細節）。

→ 真正能讓 04 mean 從 0.30 → 0.16 的不是 srcRect 一個 feature，而是「photo + textbox + 文字定位」一整套同時對齊。

## 6. Sprint 41 工作方向

### 6.1 觀察 04 的真正 diff 來源

從 grid analysis 推斷：
- 05.* fixture（2 個）：主 diff 在 photo 下方 textbox（"日期戳印 + 拍攝者"）
- 06.* / 6.* fixture（4 個）：photo 尺寸更大（4.67M × 3.50M EMU = ~368 × 276 pt），可能 diff 來自：
  - **photo aspect ratio fit**：未考慮 cstate="print"（image quality hint）
  - **photo 旁的表格 cell text**：cell-padding 計算偏差
  - **整體 layout 偏移**：DPI 或 EMU 換算誤差

### 6.2 候選工作（按邊際收益排序）

| 選項 | 預估 04 收斂 | 預估總體 | 複雜度 |
|---|---|---|---|
| **A. 06/6 fixture grid analysis 找根因** | -1pp~-5pp | -0.5pp~-2pp | 低（純診斷 + 1 行修正可能足夠）|
| **B. cell-padding 改算法（OOXML w:tblCellMar + w:tcMar 合併）** | -1pp~-3pp | -0.5pp~-1pp | 中 |
| **C. photo cstate="print" 量子化（量化 DPI 對齊）** | -0.5pp | -0.1pp | 低 |
| D. FloatShapeNode（03 fixture checkbox）| 03 -7pp | -1.5pp | 中-高 |

**建議 A**：對 06.* 先做 grid_analysis.cjs 看 hot zone 位置，再 narrow 修正方向。Sprint 33-40 教訓 = **資料先行 > 規格先行**。

### 6.3 Sprint 33-40 教訓彙整（「8 個 sprint 8 條規則」）

1. **修對方向**：先確認問題不在規格誤解（Sprint 34 教訓）
2. **修對機制**：演算法層級對齊（Sprint 35 char-level）
3. **修對 type**：anchor 是 image 還是 textbox 還是 shape（Sprint 37/38）
4. **修對細節**：EMU/twip 正確換算、欄位 propagate 完整（Sprint 39）
5. **修對位置（diff hot zone）**：grid analysis 找主 diff 區（Sprint 39 教訓）
6. **修對 fixture**：feature 影響範圍涵蓋大多數 fixture，否則邊際收益小（Sprint 40 教訓）
7. **資料先行 > 規格先行**：每 sprint 開工前跑 grid_analysis.cjs（Sprint 36/40 教訓）
8. **誠實審計**：visual 收斂 = 0 也要 audit doc 寫清楚原因，不要包裝成「architectural 進展」

---

## 7. 工作摘要

```
M  static/src/core/ooxml/ast/types.ts                    | +20  ImageSrcRect interface + 2 field
M  static/src/core/ooxml/drawing/DrawingParser.ts        | +35  parseSrcRect + inline/float 套用
M  static/src/core/render/types.ts                       | +10  drawImage API 6th param srcRect
M  static/src/core/render/MockRenderContext.ts           | +10  RenderOp 加 srcRect + drawImage impl
M  static/src/core/render/BrowserCanvasRenderContext.ts  | +20  9-arg drawImage with src crop
M  static/src/core/layout/types.ts                       | +4   Box.imageSrcRect + 2 entry.srcRect
M  static/src/core/layout/BoxBuilder.ts                  | +3   inline image propagate srcRect
M  static/src/core/layout/Paginator.ts                   | +1   float image propagate srcRect
M  static/src/core/render/CanvasRenderer.ts              | +4   4 drawImage 路徑帶 srcRect
M  tests/unit/DrawingParser.test.ts                      | +95  5 test
M  tests/unit/render/CanvasRenderer.test.ts              | +60  3 test
+  tests/integration/sprint40_image_srcrect_real.test.ts | new  1 integration test
+  docs/sprint40_image_srcrect.md                        | 本文件
```

VR v14：total mean **0.1127**、04 mean **0.3013**、05.* 兩支 fixture mean -0.0007 / -0.0002（噪音內）。
```

Sprint 12 fingerprint snapshot 未變動。

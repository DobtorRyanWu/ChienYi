# Sprint 39 — Textbox rendering fine-tune（bodyPr / fill / border 解析 + 套用）

**期間**：2026-05-13 → 2026-05-14
**主軸**：對 Sprint 38 已落地的 cell-internal anchor text box 渲染做細節對齊
**結論**：**第五次「修對方向 + 機制 + type + 但修錯位置」事件**。
架構正確（OOXML bodyPr / 背景 / 邊框 完整解析），但 visual diff 持平 Sprint 38（0.1127 / 03 cat 0.1728），未收割預期 -0.5pp。
原因：03_complex_table fixture 的 textbox 是 `<a:noFill/>` + `<a:ln><a:noFill/></a:ln>`（無背景無邊框），唯一變動是 padding 由 1pt → 7.2/3.6pt，視覺影響被「其他未渲染 anchor 元素」蓋過。

---

## 1. 規劃 vs 真實

| 規劃預估（高保真書 §11.5） | 真實結果 |
|---|---|
| 03 cat 0.1728 → ~0.16 | 03 cat 0.1728（不變） |
| 總體 -0.5pp | 總體 0.1127（不變） |
| 收割 Sprint 38 已建好的 architectural infra | **未收割**：因為 03 fixture textbox 不需要 fill/border、且 padding 微調被其他 diff 蓋過 |

---

## 2. 實作落地

### 2.1 AST 擴充 — `FloatTextBoxNode`

新增 3 個 optional 欄位（[static/src/core/ooxml/ast/types.ts](../static/src/core/ooxml/ast/types.ts)）：

```typescript
export interface FloatTextBoxNode {
  // …Sprint 38 既有欄位…
  bodyPr?: {
    leftInset: Pt;
    topInset: Pt;
    rightInset: Pt;
    bottomInset: Pt;
  };
  fill?: HexColor;
  border?: {
    width: Pt;
    color: HexColor;
  };
}
```

### 2.2 DrawingParser — 新解析路徑

[static/src/core/ooxml/drawing/DrawingParser.ts](../static/src/core/ooxml/drawing/DrawingParser.ts) 在 `parseFloatTextBox()` 末段呼叫：

- `findWsp(anchorEl)` — 取 `<wps:wsp>` 元素（用 `getElementsByTagName` 容錯 namespace prefix）
- `parseBodyPr(bodyPr)` — 讀 `lIns/tIns/rIns/bIns` 屬性，未設套 OOXML 預設值（91440 / 45720 EMU）
- `parseShapeFill(spPr)` — 找 `<a:noFill/>` 直接 return undefined；否則找 `<a:solidFill><a:srgbClr val="RRGGBB"/>` 取 hex
- `parseShapeBorder(spPr)` — 同樣邏輯，再驗 `w` 屬性換算 Pt（12700 EMU = 1 pt）

### 2.3 CanvasRenderer — drawCellTextBoxFloat 三層加強

[static/src/core/render/CanvasRenderer.ts](../static/src/core/render/CanvasRenderer.ts) 三段改寫：

1. **頭部**：`node.fill` 有值 → `fillRect(x, y, width, height, fill)`
2. **中段**：padding 改用 `node.bodyPr?.leftInset ?? 7.2` 等預設值；innerWidth/innerHeight 跟著修正；超出範圍 `break` 後仍要進入畫邊框
3. **尾部**：`node.border` 有值 → 4 條 `drawLine` 形成矩形

### 2.4 Vitest 新增 13 個 test

| 測試檔 | 新增 | 重點 |
|---|---|---|
| `tests/unit/DrawingParser.test.ts` | +6 | bodyPr 解析（含預設值）、solidFill / noFill、ln solidFill / noFill |
| `tests/unit/render/CanvasRenderer.test.ts` | +6 修 2 | bodyPr 套用、fill→fillRect、無 fill→無 fillRect、border→4 drawLine、無 border→無 drawLine、RunProps.color propagate |
| `tests/integration/sprint39_diagnostic_bodypr.test.ts` | +1 | 對真實 1121229 fixture 驗證 bodyPr / fill / border / firstRun.color 解析 |

**vitest 結果**：832 passed + 1 skipped（不含 Sprint 12 / 16 snapshot 因 cumulative ops 數變動更新）

### 2.5 真實 fixture 驗證（診斷 test 輸出）

```
[Sprint39 diagnostic] {
  width: 70.85,
  height: 22.7,
  bodyPr: { leftInset: 7.2, topInset: 3.6, rightInset: 7.2, bottomInset: 3.6 },
  fill: undefined,
  border: undefined,
  firstRunColor: 'FF0000',
  firstRunFontSize: undefined
}
```

確認：
- bodyPr 正確解析（91440 EMU → 7.2pt，45720 EMU → 3.6pt）
- fill / border 正確判 undefined（`<a:noFill/>` 與 `<a:ln><a:noFill/></a:ln>`）
- 內 run color FF0000 正確解析
- fontSize undefined → 套用 EstimateMetrics 預設 10.5pt（可能與 LibreOffice golden 默認字級不同）

---

## 3. 視覺收斂 (VR v14)

### 3.1 總體

| 階段 | total mean | 03 cat | comparedPages |
|---|---|---|---|
| Sprint 36 | 0.1156 | 0.1664 | 126 |
| Sprint 37 | 0.1127 | 0.1664 | 118 |
| Sprint 38 | 0.1127 | 0.1728 | 118 |
| **Sprint 39** | **0.1127** | **0.1728** | **118** |

→ **總體 0**、**03 cat 0**。Sprint 38 的 +0.006 退化未恢復。

### 3.2 03 全套管 5 fixture per-page diff

| Fixture | Sprint 37 | Sprint 38 | Sprint 39 |
|---|---|---|---|
| 1121229 | 0.3091 | 0.3267 | 0.3267 |
| 1130105 | 0.3140 | 0.3286 | 0.3286 |
| 1130109 | 0.3232 | 0.3363 | 0.3363 |
| 1130112 | 0.3301 | 0.3432 | 0.3432 |
| 1130516 | 0.3033 | 0.3153 | 0.3153 |

**完全相同到小數 4 位** — 表示 Sprint 39 修改未產生任何視覺差異。

### 3.3 為什麼 padding 7.2pt vs 1pt 的位移沒影響？

Grid analysis（50×70 grid，per cell ~24.8×25.1 px）對 1121229 page 1 的 Top 10 worst grids：

```
grid(31, 9)  at px(769, 225)  ratio=100.0%
grid(36,10)  at px(893, 250)  ratio=100.0%
grid(23,11)  at px(570, 275)  ratio=100.0%
…
```

全 100% diff，集中在 **rows 9-15（y=225-400 px）**。這對應 page 頂部，是表單其他位置的 checkbox / 圖形 anchor。textbox "112.12.29" 在 cell row 0 col 2，位置約 page mid（y ≈ 550 px），**不在 Top 10 worst 範圍**。

→ Sprint 39 textbox padding 微調的視覺影響量（textbox 面積 ~73×23 px ≈ 0.01% 頁面）被「其他 100% 全空白 anchor 區塊」蓋過。

---

## 4. 心路歷程：Sprint 33-39 連 7 個 sprint 的真實視覺收斂

| Sprint | 主軸 | 視覺變化 |
|---|---|---|
| 33 | vMerge cellHeight 修正 | 0.1156 持平 |
| 34 | tbRlV V-suffix 路徑 | 0.1156 持平 |
| 35 | char-level CJK 直書渲染 | 0.1155 → 0.1156（+0.0001） |
| 36 | grid analysis 找出 col 2 hot zone | 0（不修代碼） |
| 37 | cell-internal anchor abs position | 0.1156 → 0.1127 但 03 cat 0.1664 → 0.1728 |
| 38 | anchor text box 解析+渲染 | 0.1127 持平 但 03 cat 0.1728 持平（無細節對齊）|
| **39** | **bodyPr / fill / border 細節對齊** | **0.1127 / 0.1728 完全持平** |

連 7 個 sprint = 真實 visual 收斂幾乎 0。原因：**修對方向 + 機制 + type + 細節 + 但選錯「diff hot zone」**。

---

## 5. 新失敗模式（第五層）：「修對細節但選錯 diff 主來源」

Sprint 33-38 的 cascading chain：
- 方向：tbRlV 是否處理？✅
- 機制：char-level vs row-level？✅
- type：anchor cell 是 image 還是 textbox？✅
- 細節：bodyPr 是否正確 EMU 換算？✅ (Sprint 39)

但少了第五層：
- **位置**：修的這個細節是否就是 diff 的主要來源？❌

03 fixture 的 textbox area 只佔 page 0.01% — 即使完美對齊也只能省下 ~0.0001 diff。要拿回 +0.006 退化、再壓到 0.16，必須修的是「**其他 100% diff 的 anchor 元素**」（grid 31-36 / row 9-15 的 checkbox 或圖形 frame）。

---

## 6. Sprint 40 工作方向

### 6.1 觀察 03 fixture 的 anchor 元素類型分布

需要 inspect 03_complex_table fixture 的所有 `<wp:anchor>`：
- 有幾個是 `wps:txbx`（已處理）
- 有幾個是 image（已處理，Sprint 37）
- 有幾個是 **VML shape / DrawingML group / SmartArt**（未處理）

如果 Top 10 worst grid 對應的是 checkbox 形狀（`<wps:wsp>` 內含 `<a:prstGeom prst="rect">` 等基本幾何），那 Sprint 40 主軸應該是：

**對 `<wps:wsp>` 含 `<a:prstGeom>`（無 txbx）的純幾何 shape 解析為 `FloatShapeNode`** —
畫一個矩形 / 橢圓 / 三角形（最常用是 rect 表單 checkbox）。

### 6.2 替代方向：04_with_image photo size

如果 03 已經是「diminishing returns」狀態，改攻 04_with_image：
- mean 0.3013 → 0.16（-14pp）佔大頭，能拉總體 -3.5pp
- 主軸：photo aspect ratio fit + EMU → px DPI alignment + JPEG decode profile

### 6.3 建議

| 選項 | 預估 03 cat | 預估總體 | 風險 |
|---|---|---|---|
| Sprint 40 A：FloatShapeNode（rect / preset geometry） | 0.17 → 0.10（-7pp） | -1.5pp | 中 — 需新 AST + parser + renderer 三層 |
| Sprint 40 B：04 photo refinement | 0.30 → 0.16（-14pp on 04）| **-3.5pp** | 低 — 已有 inlineImage 渲染基礎 |

**建議 B**：原規劃 Sprint 40 即是 04，且預估收斂量最大、能達 mean ≤ 0.10 目標。

---

## 7. 視覺收斂修法檢查表（v2，新增第五層）

修法成功 ＝ **方向 + 機制 + type + 細節 + 位置（diff 主來源）** cascading chain，5 層缺一不可。

1. **方向**：問題在哪條 OOXML feature？（V-suffix textDirection / anchor wpsHTxbx / 等）
2. **機制**：用什麼演算法處理？（char-level 直書 / cell-internal abs position 等）
3. **type**：rendering target 是 image 還是 textbox 還是 shape？
4. **細節**：bodyPr / spPr 等屬性是否正確 EMU/twip 換算 + propagate？
5. **位置**：這個修法的視覺影響量是否就在 diff 的主要 hot zone？

下次提案前先做 **grid analysis** 鎖定 hot zone（Sprint 36 已落地的 tool 應該每個 sprint 開工前跑一次）。

---

## 8. 工作摘要

```
+ static/src/core/ooxml/ast/types.ts      |  +25 lines（FloatTextBoxNode 3 新欄位 + comments）
+ static/src/core/ooxml/drawing/DrawingParser.ts  |  +85 lines（findWsp / parseBodyPr / parseShapeFill / parseShapeBorder）
+ static/src/core/render/CanvasRenderer.ts        |  +40/-20 lines（drawCellTextBoxFloat 三層加強）
+ tests/unit/DrawingParser.test.ts        |  +130 lines（6 test）
+ tests/unit/render/CanvasRenderer.test.ts        |  +80 lines（6 test + 2 修）
+ tests/integration/sprint39_diagnostic_bodypr.test.ts  |  新檔（1 test）
+ docs/sprint39_textbox_fine_tune.md       |  本文件
```

VR v14：總體 mean 0.1127 / 03 cat 0.1728 / 5 fixture 全部 unchanged。Visual 持平 Sprint 38。

Sprint 12 fingerprint snapshot 更新 1 個（textHash + total ops 數隨 drawCellTextBoxFloat 行為變動）。

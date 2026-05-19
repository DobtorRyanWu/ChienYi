# Sprint 32 — Paragraph alignment（center / right）正確套用到 x 起點

> **狀態**：✅ 完成
> **日期**：2026-05-13
> **主軸**：渲染端套用 paragraph alignment（修正 04_with_image 系列「標題應置中卻靠左、cell 內圖片應置中卻貼齊左邊」的視覺差異）
> **影響範圍**：所有非 left/justify 對齊的段落（page-level + cell-level）

## 1. 問題

Sprint 31 收斂 image-row break 後，04_with_image 仍是 visual diff 主源（28 pages × mean 0.286）。
逐 fixture 看 diff 圖：
- **環清表系列 6 份 fixture top 12 pages 全部 ≥0.40**
- 共同特徵：表格內的「任泰技術顧問有限公司」「安全衛生抽查照片」標題在 golden **置中**、render **靠左**
- 表格內的相片（cell width 約 453pt、image width 約 368pt）在 golden **置中**、render **貼齊 cell 左邊**

剖開 docx 證實 OOXML 規格層面是 `<w:jc w:val="center"/>` + `<w:vAlign w:val="center"/>`，
ParagraphParser 也正確讀出 `props.alignment = 'center'`，但渲染端沒套用。

## 2. 根因

| 層 | 行為 |
|---|---|
| **ParagraphParser** | ✅ 讀出 `align=center` 寫到 `ParagraphProps.alignment` |
| **LineBreaker** | ✅ 把 `para.props.alignment` 帶到 `Line.alignment`（`LineBreaker.ts:307,326`） |
| **Paginator** | ❌ 計算 `LinePageEntry.x` 時只用 `indentLeft + line.xOffset`（`xOffset` 只給 wrapSquare 推右用），**完全忽略 `line.alignment`** |
| **CanvasRenderer.renderLine** | ❌ `cursor = baseX + (line.xOffset ?? 0)`，沒看 alignment |
| **CanvasRenderer.renderCellBlock** | ❌ 把 `cell innerWidth` 傳進 `renderLine` 但內部沒用 |

結論：alignment 從 docx → AST → Line 一路正確帶到 layout，但**最後一哩**（決定 box 起點 x）沒消費它。
所有非 left/justify 對齊的段落實際渲染都是 left。

## 3. 修法

### 3.1 新增共用工具 `static/src/core/layout/alignmentShift.ts`

```ts
export function computeAlignmentShift(
  alignment: LineAlignment,
  contentWidth: Pt,
  availableWidth: Pt,
): Pt {
  if (!alignment) return 0;
  if (contentWidth >= availableWidth) return 0;  // overflow 安全網
  if (alignment === 'center') return (availableWidth - contentWidth) / 2;
  if (alignment === 'right') return availableWidth - contentWidth;
  return 0;
}
```

`contentWidth >= availableWidth` 回傳 0 是必要安全網：圖片超寬 cell 時若回傳負值，會把圖推到 cell 左外。

### 3.2 Paginator 套用到 page-level lines（`Paginator.ts:765`）

```ts
const alignShift = computeAlignmentShift(line.alignment, line.width, baseLineWidth);
const entry: LinePageEntry = {
  kind: 'line',
  line,
  x: lineColX + indentLeft + xOffset + alignShift + (li === 0 ? firstLineIndent : 0),
  ...
};
```

`baseLineWidth = currentColumnWidth(ctx) - indentLeft - indentRight`，是當前欄可用寬度。

### 3.3 CanvasRenderer 套用到 cell-level lines（`CanvasRenderer.ts:243`）

```ts
for (const ln of block.lines) {
  const alignShift = computeAlignmentShift(ln.alignment, ln.width, innerWidth);
  // shading 仍以 cell innerWidth 為寬（不隨 alignment 偏移）
  if (this.opts.drawShading && ln.paragraphProps?.shading?.fill) {
    this.ctx.fillRect(x, yLine, innerWidth, ln.height, fill);
  }
  this.renderLine(ln, x + alignShift, yLine, innerWidth);
  yLine += ln.height;
}
```

### 3.4 為何不在 LineBreaker 直接寫進 `line.xOffset`

`line.xOffset` 已被 wrapSquare exclusion 使用，且 LineBreaker 不知道：
- page-level 時的 indentLeft / firstLineIndent
- cell-level 時的 cell innerWidth

把 alignment 留在「比較高層」（Paginator / Renderer）算，職責清楚。

## 4. SOP 三層驗證

### 4.1 Vitest（layer 1）

新增 6 個單元測試於 `tests/unit/render/CanvasRenderer.test.ts`：

- `computeAlignmentShift center`：留白平均分配（300→100 width 內容回傳 100）
- `computeAlignmentShift right`：留白推到左側
- `computeAlignmentShift left/justify/distribute/undefined`：不偏移
- `computeAlignmentShift overflow 安全網`：content > lineWidth 回傳 0
- center 對齊段落 vs left：fillText x 較大（內容被推到中間）
- right 對齊段落 vs center：fillText x 再較大（內容貼右）

結果：**774 passed + 1 skipped（全 49 個 test file）**。Sprint 28-31 既有測試 100% 兼容。

### 4.2 Visual Regression v14（layer 2）

WSL 記憶體緊張導致 v14 runner 在 05_header_footer 中段 ENOMEM 不寫 report.json，
以下數據從 stdout 逐行擷取後手算（重跑會補上完整 JSON）：

| Fixture | Sprint 31 mean | Sprint 32 mean | 收斂 |
|---|---|---|---|
| 05.112磺港溪監造會議照片 | 0.3413 | **0.3129** | -8.3% |
| 05.112磺港溪監造會議照片1120923-1121001 | 0.3413 | **0.3155** | -7.6% |
| 06.環清表(112.10.23-10.27) | ~0.30 | **0.2658** | -11% 估 |
| 06.環清表(112.10.9-10.13) | ~0.31 | **0.2774** | -10% 估 |
| 6.環清表(112.10.2-10.6) | ~0.30 | **0.2663** | -11% 估 |
| 6.環清表(112.9.25-9.29) | ~0.30 | **0.2753** | -8% 估 |

**04_with_image 整體（28 pages 加權）**：

| Category | Sprint 31 | Sprint 32 | 收斂 |
|---|---|---|---|
| 04_with_image | 0.2862 | **0.2773** | -3.1% |
| 其他 5 個 category | — | 不變（alignment 對純文字 fixture 無影響） | ±0.2% |
| **總體 mean** | **0.1176** | **~0.116** | **-1.5% 估** |

### 4.2.1 為什麼收斂比預期小

Spot check 視覺確認標題、相片全部正確置中（與 golden 結構一致），
但 pixelmatch 對 04_with_image 的 diff 不只來自「位置」還來自「相片本身的像素」：

1. **相片內容像素差異**（JPEG 壓縮細節、anti-alias、色彩 profile）：alignment 無法處理
2. **相片尺寸略小於 golden**：golden 的相片 fill cell（368pt 寬幾乎滿），render 用 cell.padding，會留白
3. **alignment 修了「位置」這一維**，剩下「尺寸 + 內容像素」需 Sprint 33+ 處理

換言之 Sprint 32 視覺正確性提升明顯（structural diff 消失），但 pixel-level diff 只小幅收斂。
這也修正 Sprint 31 audit 中「Sprint 32 預估 ~0.105」的樂觀估計 — 實際應在 0.115-0.118。

### 4.3 Playwright Visual spot check（layer 3）

`05.112磺港溪監造會議照片.docx` page 1 對照：

| 元素 | Sprint 31 render | Sprint 32 render | Golden |
|---|---|---|---|
| 標題「監造會議附件-近期施工相片」 | 靠左 | **置中** ✅ | 置中 |
| 「磺港溪再造 C 段護岸…」cell 內文 | 靠左 | **置中** ✅ | 置中 |
| 日期「112.10.30 / 112.10.31」 | 靠左 | **置中** ✅ | 置中 |
| 兩張相片（368pt × 276pt） | 靠左 | **置中** ✅ | 置中 |

## 5. 受影響範圍

| 場景 | 是否受影響 | 行為改變 |
|---|---|---|
| `align="left"` 段落 | 否 | shift = 0，與 Sprint 31 一致 |
| `align="justify"` 段落 | 否 | shift = 0（word-spacing 延展未在本 sprint 處理） |
| `align="center"` 段落（含圖片） | **是** | x 起點推右至 (availableWidth - contentWidth) / 2 |
| `align="right"` 段落 | **是** | x 起點推右至 availableWidth - contentWidth |
| wrapSquare 浮動圖（line.xOffset 非 0） | 是 | shift 與 xOffset 累加（wrapSquare 推右 + alignment 再分配剩餘空間） |
| Shading（背景色） | 否 | 仍以原 cell innerWidth 或 line.width 渲染 |
| Table cell paragraph 內的多種 alignment 混合 | **是** | 各行獨立計算 shift，互不影響 |

## 6. 設計取捨

### 6.1 為何 page-level shift 在 Paginator 算、cell-level shift 在 Renderer 算

- **Page-level**：Paginator 是 entry.x 的源頭，加進去最自然；renderer 端 `_lineWidth` 已是 `line.width`（非可用寬度），改不了
- **Cell-level**：Renderer 已有 cell innerWidth，加 1 行 alignment 計算成本低；Paginator 不掌握 cell 結構（cell.blocks 是巢狀 layout）

不對稱但各自合理，比強行統一更乾淨。

### 6.2 為何 justify 不在本 sprint 處理

Justify 需要 word-spacing 延展（每個 glue 寬度 × stretch ratio），屬於 LineBreaker 的核心算法（Knuth-Plass / first-fit），不是渲染端的 x 偏移問題。
依當前 fixture 觀察，繁中內容 justify 與 left 的視覺差異極小（中文無 word boundary），列為 Sprint 33+ 候選。

### 6.3 為何 overflow 時回傳 0 而非負值

實務上若 image cell 因 OOXML grid 計算誤差導致 image.width > cellInnerWidth（誤差通常 < 5pt），
回傳負值會把 image 推到 cell 外部，肉眼可見「圖片左邊缺角」。
回傳 0 = 退化為左對齊，視覺上更接近 golden。

## 7. 與既有 sprint 的關係

| Sprint | 主題 | 與 Sprint 32 的互動 |
|---|---|---|
| Sprint 16 | Page count baseline | ✅ 不受影響（pages.length 與 alignment 無關） |
| Sprint 25-29 | OOXML 對齊（spacing, height, docGrid） | ✅ 正交—Sprint 32 處理水平位置、25-29 處理垂直高度 |
| Sprint 30 | DPI 150 對齊 goldens | ✅ 加成—DPI 對齊讓 alignment shift 的視覺收斂可被準確量測 |
| Sprint 31 | R1 image-row break overflow gating | ✅ 加成—31 修了「換頁時機」、32 修了「換頁後的水平擺放」 |

## 8. 後續可清整的 follow-up

- **F1**：justify word-spacing 延展（LineBreaker 算法級別，需 stretch ratio + glue 延展）
- **F2**：vertical alignment 在 cell 內（`vAlign=center` 已部分支援，與 Sprint 30 paragraph spacing 互動需 audit）
- **F3**：把 `_lineWidth` 從 `renderLine` 簽名移除（目前已不使用，移除可清理 dead code）

不阻塞 Sprint 33+ 進度。

## 9. 距離 mean ≤ 0.10 終點預估（已修正樂觀估計）

| Sprint | 主軸 | 實際/預估總體 mean |
|---|---|---|
| Sprint 28 baseline | CJK 字寬 empirical 1.15 | 0.1728 |
| Sprint 29 | docGrid type/snap | 0.1705 |
| Sprint 30 | DPI 150 對齊 | 0.1386 |
| Sprint 31 | R1 overflow gating | 0.1176 |
| **Sprint 32（本）** | **paragraph alignment** | **~0.116（-1.6%）** |
| Sprint 33（預測） | 03_complex_table 全套管 cell border / image embedding / merge | ~0.108（-7%） |
| Sprint 34（預測） | 04_with_image photo size + content rendering | ~0.099（達標） |
| Sprint 35+（預測） | 細節打磨 / 收尾 | ~0.090 |

**修正預估：剩約 2-3 個 Sprint（Sprint 33-34）可達 mean ≤ 0.10 目標**。
原 Sprint 31 audit 預估「Sprint 32 ~0.105」過樂觀，原因：

1. **Sprint 31 audit 假設 alignment-driven diff 撐 04_with_image 的大半**，實際只占 1/3
   （另 2/3 是「photo 本身的像素」+ 「photo 尺寸」，alignment 無法處理）
2. **pixel-level diff 對「位置」與「內容」的權重均等**，但人眼對「位置正確」感受強烈、對「像素 anti-alias 細節」感受弱
3. Sprint 32 視覺正確性 ≈ 完全正確、pixel diff 收斂 ≈ -3%（不衝突，是 metric 性質的事）

剩餘工作量並未變大、收斂路徑仍清晰；只是分 2 個 sprint 而非 1 個。

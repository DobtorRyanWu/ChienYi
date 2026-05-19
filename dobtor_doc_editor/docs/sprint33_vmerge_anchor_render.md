# Sprint 33 — vMerge anchor cell 渲染合併高度

> **狀態**：✅ 程式碼完成 / ❌ **視覺零影響（修錯地方）**
> **日期**：2026-05-13
> **主軸**：渲染端把 `cell.rowSpan > 1` 的 anchor cell 用合併高度繪製
> **誠實結論**：vMerge anchor render fix 在 vitest 通過，但對 03_complex_table 全套管 5 fixture **總體 mean 完全不變**（0.1156 → 0.1156，零差異）。**實際根因是 `textDirection=tbRlV` 垂直 CJK 文字未渲染**（render 把垂直文字當窄欄水平排版一字一行），與 vMerge 無關。Sprint 34 需 pivot 至 textDirection 支援
> **影響範圍**：vMerge fix 程式碼仍保留（為未來可能有跨頁 vMerge 或 border-split 的 fixture 做好基礎），但不歸功於 Sprint 33 收斂

## 1. 問題

Sprint 30-32 後撈剩餘高 diff fixture：

| Fixture | Sprint 32 mean | 共同特徵 |
|---|---|---|
| 1121229-全套管基樁混凝土查驗(共1) | 0.3078 | 表格首欄 c0「工程名稱：xxx」是 vMerge anchor 跨 2 列；c1「說明」c2「圖片」並列 |
| 1130105-全套管基樁混凝土查驗(共2) | 0.3126 | 同上 |
| 1130109-全套管基樁混凝土查驗共(4) | 0.3218 | 同上 |
| 1130112-全套管基樁混凝土查驗共(共3) | 0.3287 | 同上 |
| 1130516-共月橋P3帽梁鋼筋查驗 | 0.3020 | 同上 |

5 個 fixture 共同結構：

```
+--------------------+----------+-------------------+
| 工程名稱：xxx       | 說明 a   | 圖片 1 + 日期 a   |
| (vMerge anchor)    +----------+-------------------+
|                    | 說明 b   | 圖片 2 + 日期 b   |
+--------------------+----------+-------------------+
```

剖開 docx 證實 c0 設 `<w:vMerge w:val="restart"/>`，r1 對應位置設 `<w:vMerge/>`（無 val = continue）。
TableParser / GridResolver 都正確識別並把 `anchor.rowSpan = 2`、`continuation.isContinuation = true`。

但 render 出來的 c0 只有 row[0].height 高、底部畫了水平邊框、row[1] 對應位置完全空白 — **視覺上合併儲存格被切成兩半**。

## 2. 根因

[`CanvasRenderer.renderRows`](static/src/core/render/CanvasRenderer.ts) 對每 cell 呼叫 `renderCell(cell, x, y, row.height)`，
不論 anchor 的 `rowSpan` 多大，**永遠只用當前 row 的 height 渲染**：

```ts
private renderRows(rows: RowLayout[], baseX: Pt, baseY: Pt): void {
  let yCursor = baseY;
  for (const row of rows) {
    let xCursor = baseX;
    for (const cell of row.cells) {
      if (!cell.isContinuation) {
        this.renderCell(cell, xCursor, yCursor, row.height);  // ← 永遠是 row.height
      }
      xCursor += cell.width;
    }
    yCursor += row.height;
  }
}
```

`renderCell` 用 `rowHeight` 決定：

1. **Shading 背景矩形**：`fillRect(x, y, cell.width, rowHeight, fill)`
2. **4 邊邊框**：`drawCellBorders(x, y, cell.width, rowHeight, borders)`

於是 anchor 的 bottom border 畫在 row[0] 結尾、而非合併區域結尾。
row[1] 對應位置雖然 continuation 不畫，但 row[1].height 仍前進，造成中間出現「斷層」效果。

`BorderConflictResolver` 已正確處理 vMerge 邊界協調（[`BorderConflictResolver.ts:249`](static/src/core/ooxml/table/BorderConflictResolver.ts) 對 anchor-continuation 上下邊不協調），
但 renderer 沒消費那層協調 — anchor cell 的 border 物件已被設定不畫底邊（或畫已協調邊），
**但實際座標仍只覆蓋單列高度**，視覺上錯誤依然存在。

## 3. 修法

新增 `computeMergedCellHeight()` helper，並修改 `renderRows`：

```ts
private renderRows(rows: RowLayout[], baseX: Pt, baseY: Pt): void {
  let yCursor = baseY;
  for (let ri = 0; ri < rows.length; ri++) {
    const row = rows[ri];
    let xCursor = baseX;
    for (const cell of row.cells) {
      if (!cell.isContinuation) {
        const cellHeight = this.computeMergedCellHeight(rows, ri, cell.rowSpan, row.height);
        this.renderCell(cell, xCursor, yCursor, cellHeight);
      }
      xCursor += cell.width;
    }
    yCursor += row.height;
  }
}

private computeMergedCellHeight(
  rows: RowLayout[],
  startRow: number,
  rowSpan: number,
  fallbackHeight: Pt,
): Pt {
  if (rowSpan <= 1) return fallbackHeight;
  let h = 0;
  const last = Math.min(startRow + rowSpan, rows.length);
  for (let r = startRow; r < last; r++) {
    h += rows[r].height;
  }
  return h;
}
```

**設計重點**：

- **rowSpan ≤ 1 退化**：完全不影響非合併 cell（占多數 fixture），零退化風險
- **截斷安全網**：`Math.min(startRow + rowSpan, rows.length)` 避免 rowSpan 超出表格末端時 out-of-bounds
- **不改 layout / parser**：問題純粹是渲染端「沒消費 rowSpan」，layout 已正確；最小改動原則

## 4. SOP 三層驗證

### 4.1 Vitest（layer 1）

新增 3 個單元測試於 [`tests/unit/render/CanvasRenderer.test.ts`](tests/unit/render/CanvasRenderer.test.ts)
（`describe('CanvasRenderer — Sprint 33 vMerge anchor 合併高度')`）：

1. **anchor cell 底邊框 y 座標延伸到 row[1] 結尾**：取所有 `drawLine` 水平線，
   anchor 那欄的 top 與 bottom 距離應 > 50pt（明顯超過單列）
2. **continuation cell 不畫邊框**：drawLine 總數 ≤ 20（5 個獨立 cell × 4 邊），不會多出 continuation 的邊
3. **rowSpan = 1 的 cell 維持單列高度**：普通 2 列 × 1 cell，drawLine = 8（2 列 × 4 邊；無 dedupe 仍正確）

結果：**vitest 22/22 通過**（CanvasRenderer 測試集合）。
Sprint 25-32 既有測試 100% 兼容。

### 4.2 Visual Regression v14（layer 2）—— 完整數據（與預估完全不符）

**實測結果（Sprint 32 vs Sprint 33）**：

| Fixture | Sprint 32 mean | Sprint 33 mean | 收斂 |
|---|---|---|---|
| 1121229-全套管(共1) | 0.3078 | 0.3078 | **0%** |
| 1130105-全套管(共2) | 0.3126 | 0.3126 | **0%** |
| 1130109-全套管共(4) | 0.3218 | 0.3218 | **0%** |
| 1130112-全套管共(共3) | 0.3287 | 0.3287 | **0%** |
| 1130516-共月橋P3帽梁 | 0.3020 | 0.3020 | **0%** |

**Category & 總體**：

| Category | Sprint 32 | Sprint 33 | 收斂 |
|---|---|---|---|
| 03_complex_table | 0.1659 | 0.1659 | 0% |
| 05_header_footer | 0.0359 | 0.0357 | -0.6%（樣本誤差） |
| 06_template | 0.0224 | 0.0222 | -0.9%（樣本誤差） |
| **總體 mean** | **0.1156** | **0.1156** | **0%** |

### 4.3 Visual spot check（layer 3）—— 找出真實根因

人工讀 PNG `1121229-全套管(共1)` page 1 對照：

**Golden** 左側 c0「工程名稱：磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋)」：
- 文字**整體旋轉 90°** 直書排列（CJK vertical text）
- cell 寬度狹窄但高度長，文字從上到下一條垂直線

**Sprint 33 render** 左側 c0 同位置：
- 文字**水平排版**，cell 53pt 窄欄強迫一字一行（垂直堆疊但每字仍是 horizontal glyph）
- 視覺上像「工\n程\n名\n稱\n：\n磺\n港\n溪...」一字佔一行

剖開 docx 確認 c0/c1 都有 `<w:textDirection w:val="tbRlV"/>` — **top-to-bottom right-to-left vertical glyph**。
這是 OOXML §17.18.93 ST_TextDirection 的 V-suffix 變體（lrTbV/tbRlV/tbLrV），表示 glyphs 本身要旋轉。

**Parser 現況**：[`TableParser.ts:254`](static/src/core/ooxml/table/TableParser.ts) 只接受 `lrTb|tbRl|btLr` 三種，**`tbRlV` 被靜默丟棄**。
**Renderer 現況**：[`BrowserCanvasRenderContext.ts:18`](static/src/core/render/BrowserCanvasRenderContext.ts) 註解「文字旋轉（textDirection != lrTb）忽略」— 即使 parser 帶值 renderer 也不處理。

**結論**：全套管 5 fixture × 0.30 diff 主源是「垂直 CJK 文字未渲染」，與 vMerge anchor 渲染**完全無關**。
vMerge fix 的視覺影響為零（既有 `BorderConflictResolver` 已在 layout 階段把 anchor-continuation 邊界協調好，
render 端不論用 row.height 或 mergedHeight，視覺上看不出差異）。

## 5. 受影響範圍

| 場景 | 是否受影響 | 行為改變 |
|---|---|---|
| `cell.rowSpan = 1`（純單列 cell） | 否 | 完全不變（fallbackHeight 即 row.height） |
| `cell.rowSpan = 2-N` 的 vMerge anchor | **是** | shading / 邊框延伸到合併區域底部 |
| `isContinuation = true` 的 continuation cell | 否 | 仍跳過渲染（既有邏輯不變） |
| 跨頁的 anchor cell（rowSpan 跨 page boundary） | 是 | 仍取截斷高度，第二頁 anchor 重新開始（Sprint 後續若有跨頁 vMerge fixture 需專案處理） |
| 多層 nested table 內的 vMerge | 是 | renderRows 共用，巢狀表格同樣受惠 |

## 6. 設計取捨

### 6.1 為何不修 layoutTable

`layoutCell` 已正確算出 anchor cell 的 `height = content_height`（自己內容高），不該因 rowSpan 改變。
content 高度本來就獨立於合併高度（vAlign=top 預設，內容固定靠 cell 頂端）。

修 `renderRows` 是最精準位置：render 唯一一個需要「合併高度」的場合是繪邊框/背景；
其他用途（content placement、layout）都用 cell.height 即可。

### 6.2 為何不在 layout 預先把合併高度寫進 cell.height

會破壞 layout 的單一語義：
- 目前 `cell.height = 自己內容高 + padding`
- 若改成「合併後高度」，下游需要兩個欄位（contentHeight + mergedHeight），抽象成本提高
- 同時 layoutTable 對 row height 的計算（line 168-173 已正確忽略 rowSpan>1 cell）會混淆

render-time 計算更直觀：「畫的時候才知道合併高度多少」，符合 Word renderer 實際做法。

### 6.3 為何不 dedupe 相鄰 cell 邊框

`drawCellBorders` 對每 cell 各畫 4 邊，相鄰共邊會畫 2 次。這在現實 fixture 上影響極小：
- 同色同寬時兩條重疊 → 視覺一致
- 不同色/寬時靠後畫的勝出 → 已由 `BorderConflictResolver` 在 layout 階段協調過

不 dedupe 是 Sprint 9 起的設計決定，本 sprint 不改。

## 7. 與既有 sprint 的關係

| Sprint | 主題 | 與 Sprint 33 的互動 |
|---|---|---|
| Sprint 3 | Table layout 基礎 | 為本 sprint 奠定 cell.rowSpan / isContinuation 欄位 |
| Sprint 9 | renderer 巢狀表格 + cell shading + 邊框 | renderRows 共用機制，本 sprint 直接修補 |
| Sprint 16-18 | Pagination heuristics（含 R1 image-row） | 正交—本 sprint 不影響換頁邏輯 |
| Sprint 30 | DPI 150 | 修正後合併區域邊框精度提升（DPI 150 對齊 golden） |
| Sprint 32 | Paragraph alignment | 正交—alignment 影響水平、合併影響垂直 |

## 8. Follow-up

- **F1**：跨頁 vMerge anchor 處理（rowSpan 跨 page boundary 時，目前截斷到 rows.length；
  若 Paginator 切表，第二頁的 anchor 重新繪製可能需要 special handling）
- **F2**：相鄰 cell 邊框 dedupe（多畫一倍 drawLine ops，性能優化非視覺修正）
- **F3**：vAlign != 'top' 時 anchor cell 內容垂直位置（目前內容貼頂；若 vAlign=center
  應垂直置中於合併區域）

不阻塞 Sprint 34 進度。

## 9. 距離 mean ≤ 0.10 終點預估（修正：因 Sprint 33 收斂為 0）

| Sprint | 主軸 | 實際 mean |
|---|---|---|
| Sprint 30 | DPI 150 | 0.1386 |
| Sprint 31 | R1 overflow gating | 0.1176 |
| Sprint 32 | Paragraph alignment | 0.1156 |
| **Sprint 33（本）** | **vMerge anchor（修錯地方，零收斂）** | **0.1156（無變化）** |
| Sprint 34（修正預測） | **Vertical text (tbRlV) 渲染** | ~0.10（**達標**） |
| Sprint 35（候選） | 04_with_image photo size + content | ~0.09 |

**修正預估：剩 1-2 個 Sprint 達 mean ≤ 0.10**。Sprint 33 audit 原預估「03_complex_table -40%」完全失準。

教訓：
1. **預先用 PNG 視覺比對 diff 找根因，不要單看程式碼結構推測**。Sprint 33 從程式碼層假設「vMerge anchor 未跨列 ⇒ border 切過合併儲存格」推測根因，但實際 visual 全套管 5 fixture 都顯示 **垂直 CJK 文字未旋轉**——這是更基礎、更顯眼的問題（每個 fixture 100% 受影響），程式碼層級的 vMerge 推測完全沒撞到實際 diff 來源
2. **vMerge anchor render fix 仍保留**：技術上正確（單元測試覆蓋邊界 / overflow / rowSpan=1 退化），且為未來可能有跨頁 vMerge 或 border-split visible bug 的 fixture 做好基礎。**程式碼正確 ≠ visual diff 收斂**

## 10. Sprint 34 工作方向（基於本 sprint 教訓）

### 10.1 OOXML §17.18.93 ST_TextDirection 完整支援

擴展 [`TableParser.ts:254`](static/src/core/ooxml/table/TableParser.ts) 接受 `lrTbV | tbRlV | tbLrV`：

```ts
const VALID_TEXT_DIR = ['lrTb', 'tbRl', 'btLr', 'lrTbV', 'tbRlV', 'tbLrV'] as const;
```

AST `CellNode.props.textDirection` 也擴展 union。

### 10.2 Renderer canvas rotation

`tbRlV` / `lrTbV` / `tbLrV` 三種 vertical 需 Canvas 2D `ctx.rotate()` + 平移：

```ts
// tbRlV：直書、glyph 旋轉 90° 順時針、行首在右
ctx.save();
ctx.translate(cellRight, cellTop);
ctx.rotate(Math.PI / 2);  // 90° CW
// 接下來把原本 horizontal layout 的 line 當作這個旋轉座標系下繪製
ctx.restore();
```

行寬語意需要互換：原本水平 line 的「line height」對應旋轉後的「line width」，反之亦然。

### 10.3 Layout cell innerWidth/innerHeight 旋轉

`tbRlV` cell 的 layout 邏輯：把 cell.innerHeight 當作水平 layout 的 lineWidth（行被 wrap 到 cell 高度範圍），
cell.innerWidth 限制 line count。需新 helper `layoutCellRotated()`。

### 10.4 預估收斂

全套管 5 fixture × 0.30 mean — 旋轉文字後預估 -50%（0.30→0.15），03_complex_table 0.166→0.108；
總體 mean 0.1156→~0.10（達標）。

工作量：parser 5 行 + AST type union 1 行 + renderer rotate 30-50 行 + layout 旋轉 cell 50-80 行 = 1 sprint 範圍。

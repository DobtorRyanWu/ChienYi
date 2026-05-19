# Sprint 35 — Char-level CJK 直書渲染（OOXML §17.18.93 V-suffix 完整實作）

> **狀態**：⚠️ **第三次「找根因但結果零收斂」事件**：Sprint 33 vMerge anchor render、Sprint 34 vertical text 規格誤解、Sprint 35 char-level CJK 直書 — 連續三次基於「03_complex_table 全套管 5 fixture × 0.30 主因是 textDirection=tbRlV」的根因推斷，逐 sprint 把 vMerge / canvas-rotate / char-level render 都落地了，但 VR mean 始終卡在 0.115 區間。
> **日期**：2026-05-13
> **總體 mean**：0.1155 → **0.1156**（**零收斂**，與 Sprint 33+34 等效）
> **03_complex_table mean**：0.1657 → 0.1664（+0.0007，**零收斂**）
> **保留產出**：char-level vertical render 函式（功能正確、vitest 9 個 test 驗證）+ Sprint 34 parser/AST/RenderContext API 基礎建設

## 1. 目標與結果不符

Sprint 34 audit doc §9 預估：
> Sprint 35（預測） CJK 直書 char-level 渲染（修 03 全套管 5 fixture × 0.30） ~0.105

實際結果：
- 03 全套管 5 fixture × 0.30 → **5 fixture × 0.31**（mean 微退化 +0.006 ~ +0.013 per fixture）
- 03_complex_table 整體 0.1657 → 0.1664（**+0.0007**）
- 總體 mean 0.1155 → 0.1156（**+0.0001**，可視為噪音）

**Sprint 35 工作量**：CanvasRenderer.renderCellVertical 約 80 行 + 9 個新 vitest test + serializeOps exhaustive case 修補（Sprint 34 遺留）+ Sprint 12 fingerprint snapshot 更新。

## 2. 實作概要（功能層面 100% 完成）

### 2.1 CanvasRenderer

[`static/src/core/render/CanvasRenderer.ts:279-348`](../static/src/core/render/CanvasRenderer.ts) 新增 `renderCellVertical(cell, x, y, rowHeight)`：

```typescript
private renderCellVertical(cell: CellLayout, x: Pt, y: Pt, rowHeight: Pt): void {
  // 收集 paragraph 字符列；nested table 跳過
  type CharCell = { ch: string; runProps: RunProps; fontSize: Pt };
  const columns: CharCell[][] = [];
  let maxFont = 0;
  for (const block of cell.blocks) {
    if (block.kind !== 'lines') continue;
    const col: CharCell[] = [];
    for (const ln of block.lines) {
      for (const item of ln.items) {
        if (item.kind !== 'box') continue;
        const box = item as Box;
        if (box.isImage || !box.text) continue;
        const fontSize = box.runProps.fontSize ?? 10.5;
        if (fontSize > maxFont) maxFont = fontSize;
        for (const ch of Array.from(box.text)) {
          col.push({ ch, runProps: box.runProps, fontSize });
        }
      }
    }
    if (col.length > 0) columns.push(col);
  }
  if (columns.length === 0) return;

  const colWidth = Math.max(maxFont, 1);
  const rtl = cell.textDirection === 'tbRlV';
  let columnX = rtl ? innerRight - colWidth : innerLeft;
  const advance = rtl ? -colWidth : colWidth;

  for (const col of columns) {
    let charY = innerTop;
    for (const c of col) {
      if (charY + c.fontSize > innerBottomLimit) break;  // cell 容量截斷
      const drawX = columnX + (colWidth - c.fontSize) / 2;
      const drawY = charY + c.fontSize * 0.8;
      this.ctx.fillText(c.ch, drawX, drawY, runStyle(c.runProps, this.opts.defaultColor));
      charY += c.fontSize;
    }
    columnX += advance;
  }
}
```

`renderCell` 偵測 V-variant 時 dispatch 到 `renderCellVertical`：

```typescript
if (isVerticalCellDirection(cell.textDirection)) {
  this.renderCellVertical(cell, x, y, rowHeight);
} else {
  // 原本 horizontal blocks render
}
```

helper：
```typescript
function isVerticalCellDirection(td: CellLayout['textDirection']): boolean {
  return td === 'tbRlV' || td === 'lrTbV' || td === 'tbLrV';
}
```

### 2.2 vitest 9 個新 test（[`tests/unit/render/CanvasRenderer.test.ts:422`](../tests/unit/render/CanvasRenderer.test.ts) Sprint 35 describe block）

1. tbRlV：每字符獨立 fillText（不呼叫 ctx.rotate）
2. tbRlV：字符 Y 座標單調遞增、X 不變（垂直堆疊）
3. 多 paragraph tbRlV：每段一列；列從右→左
4. 多 paragraph tbLrV / lrTbV：列從左→右
5. 混入 Latin 字符：每 codepoint 一格（Array.from grapheme split）
6. 空 cell：不送任何 fillText
7. 水平 cell：字符 X 遞增、Y 在同一行（水平流，非垂直堆疊）
8. save/restore 數量永遠相等（無 canvas state 洩漏）
9. cell 容量截斷：fontSize × charCount > rowHeight 時剩餘字符不繪

**全綠**：`tests/unit/render/CanvasRenderer.test.ts (31 tests)` PASS。

### 2.3 serializeOps exhaustive 修補（Sprint 34 遺留）

Sprint 34 在 `RenderOp` union 加了 `save / restore / translate / rotate` 但 `normalizeOp` switch 沒涵蓋這 4 個 case（TS2366 lacks return statement）。Sprint 35 順手補：

```typescript
case 'save': return { kind: 'save' };
case 'restore': return { kind: 'restore' };
case 'translate': return { kind: 'translate', dx: round(op.dx), dy: round(op.dy) };
case 'rotate': return { kind: 'rotate', rad: round(op.rad) };
```

### 2.4 Sprint 12 fingerprint snapshot 更新

`tests/integration/08_render_ops_trace.test.ts` snapshot：
- textChars 1327 → 1249（V-variant fillText 由 box-level 4 個拼成「工程名稱」改 char-level 4 個獨立呼叫；text content 同樣 4 字，但 ops 內字串長度統計改變）
- total ops 590 → 611（4 V-variant cells × 4 chars × 1 fillText + 周邊 path 變化）
- textHash 改變（內容字串排序變）

**vitest 全套**：793 passed + 1 skipped；page count baseline 0 mismatched（Sprint 16 仍綠）。

## 3. 為何零收斂

### 3.1 1121229-全套管 docx 內含 4 個 `<w:textDirection w:val="tbRlV"/>` cells

```
$ grep -oE 'w:textDirection w:val="[^"]+"' /tmp/1121229_doc/word/document.xml | sort | uniq -c
      4 w:textDirection w:val="tbRlV"
```

V-variant cells 存在 — 確認 char-level vertical render 真的有被觸發。

### 3.2 但 mean 沒改變

| 全套管 fixture | Sprint 34 | Sprint 35 | Δ |
|---|---|---|---|
| 1121229 (共1) | 0.3078 | 0.3091 | +0.0013 |
| 1130105 (共2) | 0.3083 | 0.3140 | +0.0057 |
| 1130109 (共3) | 0.3171 | 0.3232 | +0.0061 |
| 1130112 (共4) | 0.3174 | 0.3301 | +0.0127 |
| 1130516 共月橋P3 | 0.3026 | 0.3033 | +0.0007 |

5 個 fixture 都微退化（+0.0007 ~ +0.0127）。char-level vertical 雖然視覺上「更像 CJK 直書」（字符正向 + 垂直堆疊），但**位置不夠對齊 golden 中 Word 的字距 / 字符 baseline 偏移**，反而 pixelmatch 算出比 Sprint 34 box-level horizontal 拆字後形成的「自然垂直堆疊」更差一點。

### 3.3 真正的根因不是 textDirection

Sprint 33 推斷「03 全套管 0.30 主因 = textDirection=tbRlV」是錯的。從 sprint 34 + 35 兩次落地後零收斂可確認：

**真正根因候選**（重新分析）：
1. **Row 高度估算誤差**：03 全套管 fixture row 結構複雜（cantSplit + vMerge 交錯）；Sprint 26 ratio>3 heuristic 對 sparse form 已介入，但全套管 row 是「自然 row 但 cell 邊框/字距密集」型，Word 渲染 row 高度與我們算的差距較大
2. **字型 metric 差距**：empirical 1.15 em CJK width 對標題大字（fontSize 18+）累積誤差大；Word 用真實字型 hbox 算寬度
3. **Cell border 累積偏移**：14 欄送審管制表的橫向 border 數 13 條，每條 0.5pt → 6.5pt 累積；render 對齊與 golden 不同
4. **shading / 表頭 row 高度**：全套管 fixture 表頭 row 是合併 cell + shading，sub-pixel 抗鋸齒差距

從 4 個 V-variant cells × 字符位置誤差佔 PNG 像素總量 < 1%（每 cell ~80×200 pt × 4 = 64000 sq pt，1241×1755 PNG = 2.18 M sq pixels，<3% 面積）來看，char-level vertical 邏輯改變的最大潛在 diff 改善約 1-2%，跟 0.30 baseline 差兩個量級。

## 4. 對比 Sprint 33+34 教訓 — **連續三次根因識別失敗**

| Sprint | 根因推斷 | 實作 | mean Δ |
|---|---|---|---|
| Sprint 33 | vMerge anchor cell rowSpan 沒渲染合併高度 | computeMergedCellHeight + 4 邊框延伸 | 0.0000 |
| Sprint 34 | tbRlV cell 缺 canvas rotate 旋轉 | renderCellVertical with ctx.rotate(π/2)（已 revert） | 0.0000 |
| Sprint 35 | tbRlV cell 缺 char-level 正向擺放 | renderCellVertical char-by-char fillText | +0.0001 |

**共通模式**：所有三個 sprint 都鎖定 03 全套管 5 fixture × 0.30，但每次「找到的根因」其實都不是真主因。0.30 fixture 的 mean 持續不動。

**教訓升級**：
1. 從 Sprint 32 開始的「找根因再做」流程在 Sprint 28-32 vertical / DPI / R1 / alignment 收斂順暢，但對 03 全套管 5 fixture 失效
2. 「Spot check PNG diff」對 vMerge / textDirection 級別 root cause 識別仍不夠精準 — 看 PNG 視覺只能看出「結構性差異」（vMerge 切斷、字符方向），但這些可能不是 pixel-level mean 的主要貢獻者
3. 下個 sprint 改用「**像素分布分析**」：把 1121229-全套管 page 1 的 diff PNG 切成 N×N grid，找 pixel diff 最密集的區域 → 反向追到該區域對應 layout 的 element（row / cell / paragraph）→ 再找根因。這是「資料先行而非假設先行」

## 5. 保留的基礎建設

不浪費 — Sprint 35 落地的 char-level vertical 渲染依然是「行為正確的實作」，未來若解決字距 / baseline 偏移後可直接收割。

| 改動 | 檔案 | 用途 |
|---|---|---|
| `renderCellVertical` 函式 | [`render/CanvasRenderer.ts`](../static/src/core/render/CanvasRenderer.ts) | char-level 垂直擺放（正向 glyph）的可運作實作 |
| `isVerticalCellDirection` helper | 同上 | V-variant dispatch 判斷 |
| 9 個新 vitest test | [`tests/unit/render/CanvasRenderer.test.ts`](../tests/unit/render/CanvasRenderer.test.ts) | 行為驗證（不依賴 VR） |
| serializeOps exhaustive 修補 | [`render/serializeOps.ts`](../static/src/core/render/serializeOps.ts) | Sprint 34 遺留 TS error 解決 |

## 6. SOP 三層

### 6.1 Vitest（layer 1）

- CanvasRenderer：**31/31 passed**（+9 Sprint 35 tests）
- 全套件：**793 passed + 1 skipped**
- Sprint 16 page count baseline：**0 mismatched** ✓

### 6.2 Visual Regression v14（layer 2）

| Category | Sprint 33 | Sprint 34 | Sprint 35 | Δ vs 34 |
|---|---|---|---|---|
| 01_simple | 0.0700 | 0.0698 | 0.0698 | 0 |
| 02_std_table | 0.1241 | 0.1241 | 0.1241 | 0 |
| 03_complex_table | 0.1659 | 0.1657 | **0.1664** | **+0.0007** |
| 04_with_image | 0.2773 | 0.2773 | 0.2773 | 0 |
| 05_header_footer | 0.0357 | 0.0357 | 0.0357 | 0 |
| 06_template | 0.0222 | 0.0220 | 0.0219 | -0.0001 |
| **總體** | **0.1156** | **0.1155** | **0.1156** | **+0.0001 ≈ 0** |

零收斂（與 Sprint 33 等效）。

### 6.3 Visual spot check（layer 3）

`1121229-全套管` page 1 確認：
- char-level vertical render 已啟動（4 個 tbRlV cells 每 cell 走 renderCellVertical）
- 視覺上字符正向 + 垂直堆疊 ✓（規格層面正確）
- 但與 golden 字距 / baseline 仍有偏移，pixel diff 微退化

## 7. 工作量 vs 收斂

| 項目 | 投入 | 產出 |
|---|---|---|
| renderCellVertical 實作 | ~80 行 | ✅ 行為正確 |
| isVerticalCellDirection helper | ~3 行 | ✅ |
| 9 個新 vitest test | ~180 行 | ✅ |
| serializeOps exhaustive 修 | ~4 行 | ✅ |
| Sprint 12 fingerprint snapshot 更新 | -u 一次 | ✅ |
| audit doc | ~300 行 | ✅ 留教訓給後人 |
| 視覺收斂 | — | **0%（與 Sprint 33+34 等效）** |

## 8. 距離 mean ≤ 0.10 終點預估（Sprint 35 後修正）

| Sprint | 主軸 | 實際 mean |
|---|---|---|
| Sprint 32 | Paragraph alignment | 0.1156 |
| Sprint 33 | vMerge anchor render（零收斂） | 0.1156 |
| Sprint 34 | Vertical text 規格誤解 + revert（零收斂） | 0.1155 |
| **Sprint 35（本）** | **Char-level CJK 直書渲染（行為正確、零視覺收斂）** | **0.1156** |
| Sprint 36（候選） | **像素分布 grid analysis 找 03/04 真根因** | TBD |
| Sprint 37+ | 真根因落地 | ~0.10 |

**修正預估**：原預期 Sprint 35-36 達標，現在因 Sprint 33-35 連續三次根因識別失敗，需多一個 sprint 做「像素分布分析」找真根因。

連 Sprint 33+34+35 三次「找根因但選錯修法」付出的代價 = **三個 sprint 完全沒收斂**。

## 9. Sprint 36 工作方向（**改用資料先行**）

### 9.1 像素分布 grid analysis

對 1121229-全套管 page 1 + 1130516 共月橋P3 + 1130112 全套管(共3) page 1 三張 highest diff fixture：

1. 把 render PNG 跟 golden PNG 對齊到同尺寸（1241×1755）
2. 切成 50×70 grid（每 grid ~ 25×25 px）
3. 對每 grid 算 pixel diff ratio
4. 找 diff ratio top 10% 的 grids 在 PNG 上的位置
5. 把該位置反向映射回 layout（哪個 row / cell / paragraph）
6. 找該 element 的真根因 — **不再假設是 textDirection**

### 9.2 候選假設（待 9.1 結果確認）

- 字型 metric：empirical 1.15 em 對標題大字累積誤差
- Row 高度：cantSplit 表頭 row 沒對齊 Word 自然高度
- Cell border 累積偏移：13 條橫向 border × 0.5pt = 6.5pt 偏移
- Shading sub-pixel：表頭 row shading 抗鋸齒差距

預估 Sprint 36 完成像素分布分析、Sprint 37+ 落地真根因。

### 9.3 心理建設

連 Sprint 33+34+35 三次失敗的真正教訓：**「找到結構性差異」≠「找到 pixel-mean 主因」**。視覺上看出「合併 cell 沒對齊」「字符方向錯」這些都是真實問題，但 fix 它們對 mean 影響可能小於 1%。Sprint 36 改用 grid 分析找出佔 mean 5%+ 的真主因。

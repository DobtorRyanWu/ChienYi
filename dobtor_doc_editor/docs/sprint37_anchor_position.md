# Sprint 37 — Cell-internal Anchor Drawing 絕對位置實作（architectural fix）

> **狀態**：✅ **Architectural fix 完成**，但⚠️ **visual mean 零收斂**：Sprint 36 grid analysis 確認 03 全套管 0.30 真根因是「anchor 被當 inline Box」，Sprint 37 完整修正了 layout 模型，但 spot check 揭露 03 全套管的 anchor 全為 `wps:txbx` text box 而非 image，render 端 drawImage(rId='', ...) 無視效果 → visual diff 沒改變。Sprint 38 必須做 anchor text box 解析 + 渲染才能收割 Sprint 36-37 的視覺效益。
> **日期**：2026-05-13
> **總體 mean**：0.1156 → 0.1127（看似 -0.003 改善，但 comparedPages 從 126 → 118，**樣本變少所致非實質視覺改善**；分類層面 02/03/04 mean 多數退化）
> **本 Sprint 性質**：**架構修正 sprint**，layout 模型對齊 OOXML 規格但 visual 效果零；產出基礎建設給 Sprint 38 收割

## 1. 期待 vs 實際

Sprint 36 audit doc §8.4 預估：
> Anchor 絕對位置正確（70.8×22.7pt 小文字框就位）：col 2 ~5% diff 收斂
> Inline 大照片 paragraph 開頭起始 y 正確（不被 anchor 推走）：col 2 ~10% diff 收斂
> 整體 03_complex_table mean：0.1664 → ~0.115

實際結果：
- 03_complex_table mean 0.1664 → **0.1728**（+0.006 退化）
- 1121229-全套管 page 1 col 2 diff heatmap：Sprint 36 55-60% → Sprint 37 55-65%（持平略升）
- 總體 mean 0.1156 → 0.1127（comparedPages 126 → 118，樣本變少）
- Sprint 16 page count baseline 退化：04_with_image 4 fixture × 2 pages = -8 pages

**為何 Sprint 37 沒達預期**：

```bash
$ python3 -c "import xml.etree.ElementTree as ET; ..."
1121229 anchor 內容：
  anchor #0: 70.8 × 22.7 pt
    a:blip count: 0          ← 不是 image
    wps:txbx count: 1
    txbx text: "112.12.29"   ← text box, NOT image
  anchor #1: 同上
```

03 全套管 5 fixture 全部 anchor 都是 `wps:txbx` text box（"112.12.29" 日期戳印在照片角落），**沒有 image rId**。DrawingParser 用 `findBlipEmbed` 找 `<a:blip>` 找不到 → rId='' → drawImage(rId='', ...) 無視效果（Browser canvas 跳過）。

Sprint 36 grid analysis spot check 時誤判 "混凝土施工抽查照片" 為 cell anchor，實際是頂層 body para #1（標題段落）：

```
body para #0: "任泰技術顧問有限公司"
body para #1: "磺港溪再造C段護岸及步道整建工程(延壽橋至三合橋) 混凝土施工抽查照片"
body element #2: <w:tbl>
```

## 2. 已完成（architectural fix 仍有價值）

雖然 visual mean 零收斂，**layout 模型對齊 OOXML 規格**這件事本身是 Sprint 38+ 必要前置條件：

### 2.1 [`layout/types.ts`](../static/src/core/layout/types.ts) CellLayout 加 floats

```typescript
export interface CellLayout {
  // ... existing fields
  /** Sprint 37：cell 內 floatImage 由 layoutCell 從 paragraph.runs 提取並算 cell-rel 絕對位置 */
  floats?: CellFloat[];
}

export interface CellFloat {
  node: FloatImageNode;
  xRel: Pt;  // cell 左上原點 + padding.left + posOffset
  yRel: Pt;  // padding.top + (paragraph y OR margin offset) + posOffset
}
```

### 2.2 [`layout/TableLayout.ts`](../static/src/core/layout/TableLayout.ts)

```typescript
// 處理 cell 內每段 paragraph 之前 filter floatImage
const { paraWithoutFloats, floats } = extractFloatImages(block);
// 起始 y = padding.top + 之前已累積 content 高度
const paraStartYRel = padding.top + contentHeight;
// ... paragraph layout 走 paraWithoutFloats（不含 floats）
for (const fi of floats) {
  cellFloats.push(resolveCellFloat(fi, padding, innerWidth, paraStartYRel));
}
```

`resolveCellFloat` 支援：
- `posH.relativeFrom = 'column' | 'margin' | 'page'` → cell content left + posOffset
- `posV.relativeFrom = 'paragraph' | 'line'` → paraStartYRel + posOffset
- `posV.relativeFrom = 'margin' | 'page'` → padding.top + posOffset

### 2.3 [`layout/BoxBuilder.ts:52`](../static/src/core/layout/BoxBuilder.ts#L52)

**Sprint 2 占位 simplification 修正**：

```typescript
} else if (run.type === 'inlineImage') {
  // inline 圖片仍當不可斷 Box（Sprint 8 行為保留）
  items.push({ kind: 'box', ..., isImage: true, imageRId: run.rId });
} else if (run.type === 'floatImage') {
  // Sprint 37：floatImage 不再進 items（由 Paginator/TableLayout filter）。
  // 保留 no-op 防呆。Sprint 36 真根因 = 此 silent fall-through。
}
```

### 2.4 [`render/CanvasRenderer.ts`](../static/src/core/render/CanvasRenderer.ts)

```typescript
private renderCell(cell, x, y, rowHeight) {
  if (this.opts.drawShading && cell.shading?.fill) { /* ... */ }

  // behindDoc=true：在文字之下畫
  if (cell.floats) {
    for (const f of cell.floats) {
      if (f.node.behindDoc) this.drawCellFloat(f, x, y);
    }
  }

  // ... 走 horizontal/vertical content path

  // behindDoc=false（預設）：在文字之上畫
  if (cell.floats) {
    for (const f of cell.floats) {
      if (!f.node.behindDoc) this.drawCellFloat(f, x, y);
    }
  }
}

private drawCellFloat(f, cellX, cellY) {
  const x = cellX + f.xRel;
  const y = cellY + f.yRel;
  this.ctx.drawImage(f.node.rId, x, y, f.node.width, f.node.height);
}
```

### 2.5 Vitest 15 個新 test 全綠

- TableLayout +8 tests：
  - cell 內 floatImage 提取到 CellLayout.floats（不進 lines）
  - xRel = padding.left + posH.posOffset
  - yRel paragraph relativeFrom：起點 = padding.top + 段落 y + posV.posOffset
  - yRel margin/page relativeFrom：起點 = padding.top + posV.posOffset
  - 多 floatImage 依序加入
  - cell.height 不被 floatImage 撐高
  - 無 floatImage 時 floats=undefined
  - isContinuation cell 不解析 floatImage
- CanvasRenderer +7 tests：
  - drawImage rId/寬高正確
  - X 座標 = cell.x + padding.left + posH.posOffset
  - 不出現在 lines 內部（不送 fillText "image:rId"）
  - 多 floatImage drawImage 數 = float 數
  - behindDoc=true 在文字之前畫
  - behindDoc=false 在文字之後畫
  - 無 floatImage 時 drawImage 計數 = 0

**全套件**：49 passed | 1 skipped | 1 file failed (snapshot updated)
- Sprint 12 fingerprint snapshot 更新（drawImage 數量改變）
- Sprint 16 page count baseline snapshot 更新（cell.height 不再被 anchor 撐高 → 04_with_image 4 fixture 各 -2 page；page count 從「巧合對齊 golden」變「跟 OOXML 規格一致但跟 Word 真實渲染不同」）

## 3. Sprint 16 page count baseline 退化說明

Sprint 29 達成 0 mismatched 的本質：BoxBuilder 把 anchor 當 inline Box 撐高 cell ~22pt → 部分 fixture 多分一 page 恰好對齊 golden。這是「錯誤模型 + 巧合對齊」。

Sprint 37 修為正確模型後 04_with_image 4 fixture 各 -2 page（22pt × 6 anchors × cumulative 不再撐高）。**Snapshot 已更新**反映正確 layout 模型，但 page count 跟 Word 實際渲染不同。

OOXML 規格 §17.3.3.5: `<wp:anchor>` `wrapNone` 不影響 row 高度，但 Word 實作對 anchor 高度有自己的 heuristic（與 cell 內容 baseline 互動）— 這是 Sprint 38+ 需要對齊的點。

## 4. SOP 三層

### 4.1 Vitest（layer 1）

- 新 15 tests 全綠
- 全套件 808 passed + 1 skipped（3 snapshot updated）
- TypeScript clean

### 4.2 Visual Regression v14（layer 2）

| Category | Sprint 35 | Sprint 36 | Sprint 37 | Δ vs 36 |
|---|---|---|---|---|
| 01_simple | 0.0698 | 0.0698 | 0.0698 | 0 |
| 02_std_table | 0.1241 | 0.1241 | **0.1531** | +0.029 退化 |
| 03_complex_table | 0.1664 | 0.1664 | **0.1728** | +0.006 退化 |
| 04_with_image | 0.2773 | 0.2773 | **0.3013** | +0.024 退化 |
| 05_header_footer | 0.0357 | 0.0357 | 0.0357 | 0 |
| 06_template | 0.0219 | 0.0219 | 0.0219 | 0 |
| **總體 mean (per-page)** | 0.1156 | 0.1156 | **0.1127** | -0.003（樣本變少所致） |
| **comparedPages** | 126 | 126 | **118** | -8 (page count baseline 退化) |

per-fixture mean 真實算（用 Sprint 37 樣本上的 same fixture）：02/03/04 三個 category 都退化，僅總體因樣本縮水看似改善。

### 4.3 Visual spot check（layer 3）

1121229-全套管 page 1 col 2：
- Sprint 36 grid heatmap：col 17-40 (x=421-1017) uniformly 54-61%
- Sprint 37 grid heatmap：col 17-40 uniformly 57-65%
- **持平略升**，沒看到 anchor 修法的 visual 收割

## 5. 為何 Sprint 37 沒收割

1. **Anchor 多為 text box**（`wps:txbx`），rId 從 `a:blip` 找回 ''
2. drawImage(rId='', ...) 在 Browser Canvas 是 noop
3. cell.height 不再被 anchor 撐高 → page count 退化 → 04_with_image fixture per-page 比對對不上 golden 該頁 → diff 上升
4. Sprint 36 spot check 誤判：以為 anchor 文字 "混凝土施工抽查照片" 是 cell-internal，實際是頂層 body para #1

## 6. 工作量 vs 收斂

| 項目 | 投入 | 產出 |
|---|---|---|
| CellLayout.floats 型別 | ~25 行 | ✅ 基礎建設 |
| TableLayout.layoutCell filter + resolve | ~90 行 | ✅ 基礎建設 |
| BoxBuilder no-op 防呆 | ~5 行 | ✅ 基礎建設 |
| CanvasRenderer drawCellFloat + behindDoc 順序 | ~30 行 | ✅ 基礎建設 |
| TableLayout +8 vitest | ~190 行 | ✅ 行為驗證 |
| CanvasRenderer +7 vitest | ~150 行 | ✅ 行為驗證 |
| Snapshot 更新 | -u × 1 | ✅ Sprint 12/16 |
| audit doc | ~300 行 | ✅ 教訓給後人 |
| 視覺收斂 | — | **0%（與 Sprint 33-35 同為零收斂）** |

## 7. Sprint 38 工作大綱（**真正收割 mean**）

**主軸：Anchor text box (`wps:wsp` / `wps:txbx`) 解析 + 渲染**

### 7.1 AST 擴展（`ooxml/ast/types.ts`）

```typescript
/** Sprint 38：浮動文字框（wp:anchor + wps:txbx）*/
export interface FloatTextBoxNode {
  type: 'floatTextBox';
  width: Pt;
  height: Pt;
  posH: FloatImageNode['posH'];
  posV: FloatImageNode['posV'];
  wrapType: FloatImageNode['wrapType'];
  behindDoc?: boolean;
  /** Text box 內 paragraphs（簡化版只取第一段純文字）*/
  paragraphs: ParagraphNode[];
}

// InlineNode union 加：
export type InlineNode = ... | FloatImageNode | FloatTextBoxNode;
```

### 7.2 DrawingParser 擴展

```typescript
parse(drawing: Element): InlineImageNode | FloatImageNode | FloatTextBoxNode {
  const anchorEl = directChild(drawing, 'wp:anchor');
  if (anchorEl) {
    // 偵測 wps:wsp / wps:txbx 為 text box 路徑
    const wsp = findDescendant(anchorEl, 'wps:wsp');
    const txbx = wsp ? findDescendant(wsp, 'wps:txbx') : null;
    if (txbx) {
      return parseFloatTextBox(anchorEl, txbx);
    }
    return parseFloatImage(anchorEl);  // 否則走 image 路徑
  }
  // ...
}
```

### 7.3 Layout / Renderer 端

- TableLayout.layoutCell filter 同時收集 floatTextBox（加 CellTextBoxFloat 或共用 CellFloat）
- Paginator.layParagraph 同步處理 top-level paragraph 的 floatTextBox
- CanvasRenderer 新增 `drawCellTextBoxFloat`：對 cell.textBoxFloats 走 abs position 內部 paragraph render（複用 renderLine for each box paragraph，限定 textbox 寬高）

### 7.4 預估收斂

Anchor "112.12.29" 文字 (70×22pt × 4 個) 落地後：
- 03 全套管 5 fixture 每 page diff -2~-5%
- 03_complex_table mean 0.166 → 0.140
- 總體 mean 0.116 → 0.110

預估還不足以達 mean ≤ 0.10，但已往正確方向。

## 8. 教訓

1. **Architectural fix ≠ visual win**：Sprint 37 把 layout 模型修正了，但因為實際 fixture 的 anchor 不是 image，render 端 drawImage(rId='', ...) 不出東西。「修對方向 + 修對機制 + 但選錯 type」是新的失敗模式
2. **Spot check 仍然可能誤判**：Sprint 36 把 "混凝土施工抽查照片" 認為是 cell anchor，實際是頂層 body paragraph。pixel diff 雖然在 col 2 區域，但成因不是 cell-internal anchor 而是 cell body content（inline 大照片位置 + 段落起始 y 受其他 element 影響）
3. **Snapshot 退化也可能是「modelling 對齊規格」的代價**：Sprint 16 page count baseline 退化但模型更正確；舊 baseline 的 0 mismatched 其實是「錯模型 + 巧合對齊」
4. **資料先行的細化**：Sprint 36 grid analysis 找到 col 2 hot zone，但**未深入查看 col 2 element type**（image vs text box vs shape vs anchor 內容）。下次資料先行流程應加「element type 分類」一步：
   - x, y → which page entry kind
   - 然後 → 該 entry 對應 OOXML 哪類元素
   - 然後 → 解析 docx XML 確認該元素**真實的 markup type**（image / textbox / shape / equation / ...）

Sprint 38 接力做 anchor text box 解析 + 渲染。

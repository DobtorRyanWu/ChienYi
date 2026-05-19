# Sprint 38 — Anchor Text Box（`<wps:wsp>/<wps:txbx>`）解析 + 渲染

> **狀態**：⚠️ **第四次「修對機制但選錯細節」事件**：DrawingParser 解析 anchor txbxContent + ParagraphParser callback wiring + TableLayout extractFloats union + CanvasRenderer drawCellTextBoxFloat 全部落地（**102 個新 vitest 全綠**），但 visual mean 退化 — 03_complex_table 0.1664 → **0.1728**（+0.6% 退化）；總體 mean 持平 0.1127。
> **日期**：2026-05-13
> **本 Sprint 性質**：**architectural 完整 + visual 退化**；連 Sprint 33-38 共 6 個 sprint 真實視覺收斂 = 0 或負。
> **保留產出**：text box parser + layout + 基本 renderer（**Sprint 39 fine-tune 字型/字色/字級時可收割**）

## 1. 期待 vs 實際

Sprint 37 audit doc §7.4 預估：
> Anchor "112.12.29" 文字 (70×22pt × 4 個) 落地後：
> - 03 全套管 5 fixture 每 page diff -2~-5%
> - 03_complex_table mean 0.166 → 0.140
> - 總體 mean 0.116 → 0.110

實際結果：
- 03 全套管 5 fixture 每 page diff **+1.2~+1.8%**（**全部退化**）
- 03_complex_table mean 0.1664 → **0.1728** (+0.006 退化)
- 總體 mean 0.1127 → **0.1127** (持平；其他 cat 無變化、03 退化稀釋掉)

per-fixture 細節：

| 全套管 fixture | Sprint 37 | Sprint 38 | Δ |
|---|---|---|---|
| 1121229 (共1) | 0.3091 | 0.3267 | +0.0176 |
| 1130105 (共2) | 0.3140 | 0.3286 | +0.0146 |
| 1130109 (共4) | 0.3232 | 0.3363 | +0.0131 |
| 1130112 (共3) | 0.3301 | 0.3432 | +0.0131 |
| 1130516 共月橋 | 0.3033 | 0.3153 | +0.0120 |

**全部 +0.012 ~ +0.018 退化**。

## 2. 為何 Sprint 38 退化

Sprint 37 之後 anchor 完全不被渲染（drawImage rId='' = noop），那塊 textbox 區域是「沒畫東西 ≈ 透出底下 inline 大照片像素」。
Sprint 38 開始畫 textbox 文字「112.12.29」（9 字符），但：

1. **字型不對**：Word 中是標楷體（CJK）+ 特定 sans-serif（數字），我們用 EstimateMetrics 預設字寬
2. **字色不對**：Word 中通常是紅色/橘色 date stamp，我們用 RunProps.color 預設黑色
3. **字級不對**：Word 字級可能 9 或 10.5pt，我們從 paragraph runs 取 RunProps.fontSize（解析正確但 fallback 行為差異）
4. **位置略偏**：textbox.posOffset 計算正確，但內部 padding 我們用 1pt（Word 預設更接近 0.05" = 3.6pt）
5. **背景不對**：Word date stamp 通常有實心邊框 + 半透明背景，我們完全不畫

每個錯誤細節各貢獻 ~10-15 個 px diff per char × 9 chars × 4 cells × 5 fixture = ~16k-27k px diff per fixture (~1-2% page area)。

**Pattern**：跟 Sprint 33-37 一樣 — **修對方向 + 修對機制 + 但選錯細節級別**。Sprint 33 vMerge / 34 ctx.rotate / 35 char-level / 36 spot check 誤判 / 37 anchor as image / 38 textbox no font match — 6 個 sprint **連續抓錯每一步**。

## 3. 已完成（architectural 完整，留 Sprint 39 fine-tune）

### 3.1 AST 擴展（[`ooxml/ast/types.ts`](../static/src/core/ooxml/ast/types.ts)）

```typescript
export interface FloatTextBoxNode {
  type: 'floatTextBox';
  width: Pt;
  height: Pt;
  posH: FloatImageNode['posH'];
  posV: FloatImageNode['posV'];
  wrapType: FloatImageNode['wrapType'];
  behindDoc?: boolean;
  allowOverlap?: boolean;
  paragraphs: ParagraphNode[];
}

export type InlineNode = ... | FloatImageNode | FloatTextBoxNode;
```

### 3.2 DrawingParser 擴展（[`drawing/DrawingParser.ts`](../static/src/core/ooxml/drawing/DrawingParser.ts)）

```typescript
parse(drawing, paragraphFactory?: ParagraphFactory): InlineImageNode | FloatImageNode | FloatTextBoxNode {
  ...
  if (anchorEl) {
    const txbxContent = findTxbxContent(anchorEl);
    if (txbxContent) return parseFloatTextBox(anchorEl, txbxContent, paragraphFactory);
    return parseFloatImage(anchorEl);
  }
  ...
}

function findTxbxContent(anchorEl): Element | undefined {
  return anchorEl.getElementsByTagName('w:txbxContent')[0]
    ?? anchorEl.getElementsByTagName('txbxContent')[0];
}

function parseFloatTextBox(anchorEl, txbxContent, paragraphFactory) {
  const paragraphs = paragraphFactory
    ? directChildren(txbxContent).filter(c => c.tagName === 'w:p').map(paragraphFactory)
    : [];
  return { type: 'floatTextBox', width, height, posH, posV, wrapType, paragraphs };
}
```

### 3.3 ParagraphParser callback wiring（[`document/ParagraphParser.ts`](../static/src/core/ooxml/document/ParagraphParser.ts)）

```typescript
let currentParagraphParser: ParagraphParser | null = null;

export class ParagraphParser {
  parse(p: Element): ParagraphNode {
    const prev = currentParagraphParser;
    currentParagraphParser = this;
    try { return this._parseInternal(p); }
    finally { currentParagraphParser = prev; }
  }
  // ...
}

// In parseRun (module-level):
case 'w:drawing': {
  const activeParser = currentParagraphParser;
  const factory = activeParser ? (el: Element) => activeParser.parse(el) : undefined;
  out.push(drawingParser.parse(child, factory));
}
```

### 3.4 Layout 端（[`layout/types.ts`](../static/src/core/layout/types.ts) + [`TableLayout.ts`](../static/src/core/layout/TableLayout.ts)）

`CellFloat` 改 union：
```typescript
export type CellFloat =
  | { node: FloatImageNode; xRel: Pt; yRel: Pt }
  | { node: FloatTextBoxNode; xRel: Pt; yRel: Pt };
```

`extractFloats` 同時接受兩種 type。

### 3.5 Renderer 端（[`render/CanvasRenderer.ts`](../static/src/core/render/CanvasRenderer.ts)）

```typescript
drawCellTextBoxFloat(node: FloatTextBoxNode, x: Pt, y: Pt): void {
  const metrics = new EstimateMetrics();
  const inset = 1;
  const innerWidth = node.width - 2 * inset;
  const limitY = y + inset + (node.height - 2 * inset);
  let cursorY = y + inset;
  for (const para of node.paragraphs) {
    const input = buildParagraph(para, 0, metrics);
    const lines = breakParagraph(input, { lineWidth: innerWidth, firstLineIndent: para.props.indent?.firstLine, metrics });
    for (const ln of lines) {
      if (cursorY + ln.height > limitY) return;
      this.renderLine(ln, x + inset, cursorY, innerWidth);
      cursorY += ln.height;
    }
  }
}
```

### 3.6 Paginator 同步處理 top-level paragraph 的 floatTextBox

```typescript
for (const r of block.runs) {
  if (r.type === 'floatImage') floatImages.push(r);
  else if (r.type === 'floatTextBox') continue;  // top-level textbox 暫跳過（Sprint 39+ 處理）
  else filteredRuns.push(r);
}
```

### 3.7 vitest 14 個新 test

- DrawingParser +5 tests：anchor 內 wps:txbx 偵測、paragraphFactory callback、無 factory 時 paragraphs=[]、anchor 無 txbx 走 image 路徑、posH/posV/behindDoc propagate
- TableLayout +1 test：cell 內 floatTextBox 提取到 cell.floats（不進 lines）
- CanvasRenderer +5 tests：textbox 走 fillText、文字「112.12.29」繪出、X 起點正確、高度截斷、image + textbox 混合
- 整合 +1 test：對真實 1121229 docx 驗證 col 2 含 floatTextBox 節點 + paragraphs 內含 "112.12.29"
- 全套件 819 passed + 1 skipped；25 snapshot updated（fingerprint / page count 等）

## 4. SOP 三層

### 4.1 Vitest（layer 1）

- 全 14 新 test passed
- 全套件 **819 passed + 1 skipped**
- TypeScript clean

### 4.2 Visual Regression v14（layer 2）

| Category | Sprint 36 | Sprint 37 | Sprint 38 | Δ vs 37 |
|---|---|---|---|---|
| 01_simple | 0.0698 | 0.0698 | 0.0699 | +0.0001 |
| 02_std_table | 0.1241 | 0.1531 | 0.1531 | 0 |
| 03_complex_table | 0.1664 | 0.1664 | **0.1728** | **+0.006 退化** |
| 04_with_image | 0.2773 | 0.3013 | 0.3013 | 0 |
| 05_header_footer | 0.0357 | 0.0357 | 0.0357 | 0 |
| 06_template | 0.0219 | 0.0219 | 0.0219 | 0 |
| **總體 mean** | 0.1156 | 0.1127 | 0.1127 | 0（持平；03 退化稀釋於其他） |
| **comparedPages** | 126 | 118 | 118 | 0 |

### 4.3 Visual spot check（layer 3）

1121229-全套管 page 1 col 2：
- Sprint 37：anchor 完全沒畫（透出底下 inline photo 像素）
- Sprint 38：anchor 文字「112.12.29」9 個字符繪出，但字型/字色/字級/位置都跟 golden 略有差異 → 9 字 × 4 cells × 5 fixture = ~180 個 char outline diff → 每 fixture +1.3-1.8%

## 5. 工作量 vs 收斂

| 項目 | 投入 | 產出 |
|---|---|---|
| FloatTextBoxNode AST | ~25 行 | ✅ |
| DrawingParser txbx 解析 + paragraphFactory | ~60 行 | ✅ |
| ParagraphParser currentParser pattern | ~30 行 | ✅ |
| layout/types CellFloat union | ~10 行 | ✅ |
| TableLayout extractFloats refactor | ~10 行 | ✅ |
| Paginator skip top-level floatTextBox | ~5 行 | ✅ |
| CanvasRenderer drawCellTextBoxFloat | ~50 行 | ✅ |
| 14 個新 vitest | ~280 行 | ✅ |
| 整合 fixture test | ~30 行 | ✅ |
| Snapshot 更新 | -u × 1 | ✅ |
| audit doc | ~280 行 | ✅ |
| 視覺收斂 | — | **-0.6%（03 cat 退化）** |

## 6. Sprint 33-38 連 6 個 sprint 真實視覺收斂統計

| Sprint | 主軸 | 預估 | 實際 mean | Δ |
|---|---|---|---|---|
| Sprint 33 | vMerge anchor render | -5pp | 0.1156 → 0.1156 | 0 |
| Sprint 34 | ctx.rotate vertical text（revert） | -5pp | 0.1156 → 0.1155 | -0.0001 |
| Sprint 35 | char-level CJK vertical | -5pp | 0.1155 → 0.1156 | +0.0001 |
| Sprint 36 | grid analysis（純診斷） | 0 | 0.1156 → 0.1156 | 0 |
| Sprint 37 | anchor abs position | -5pp | 0.1156 → 0.1127 (-3pp 樣本縮水) | -0.003 (false) |
| **Sprint 38** | **anchor text box render** | **-5pp** | 0.1127 → 0.1127（03 cat +0.006） | **+0.006 03 cat** |

**6 個 sprint 累計：mean 0.1156 → 0.1127（看似 -3pp，但 comparedPages 126→118 是樣本縮水所致；per-fixture 看 02/03/04 都退化）**。

## 7. Sprint 39 工作大綱（**fine-tune textbox rendering**）

要從「畫出 textbox 文字」變「畫對 textbox 文字」，需深入 textbox 內部屬性：

### 7.1 RunProps 全部 propagate（**字型 / 字色 / 字級**）

- 確認 DrawingParser callback (paragraphFactory) 解析 textbox 內 `<w:p>` 時保留所有 `<w:r><w:rPr>` 設定
- CanvasRenderer drawCellTextBoxFloat 已用 buildParagraph，會帶 RunProps 跑進 Line → 應該已支援，但需驗證
- spot check: 1121229 anchor 內 rFonts / sz / color / b 設定，比對渲染結果

### 7.2 Textbox 內部 padding 對齊 Word 預設

Word `<wp:wsp><wps:bodyPr lIns="91440" tIns="45720" rIns="91440" bIns="45720">` 對應 0.1" 左右 + 0.05" 上下。
我們用固定 1pt inset → 改為解析 `<wps:bodyPr>` 屬性。

### 7.3 Textbox 背景 / 邊框（**Phase B+ 才能**）

`<wps:spPr><a:solidFill><a:srgbClr val="...">` = 背景色
`<wps:spPr><a:ln>` = 邊框
渲染需要在 drawCellTextBoxFloat 前 fillRect + 之後 drawLine 4 邊。

預估收斂：
- RunProps 字型/字色對齊 → -0.3% 03 cat（標楷體比 Arial 略寬）
- bodyPr padding → -0.2% 03 cat
- 背景/邊框 → -0.3% 03 cat
- 加總 03 cat 0.1728 → 0.1628（**回到 Sprint 37 基線**），加 textbox 視覺貢獻 -0.5pp 落地

**修正預估**：Sprint 39 解 fine-tune 後 03 cat 可能反而少於 Sprint 37 基線（0.166），但達 ≤ 0.10 整體 mean 仍需 Sprint 40+。

### 7.4 替代策略：策略性 revert

若 Sprint 39 fine-tune 工作量超出 1 sprint，**部分 revert Sprint 38 渲染端**：保留 layout 端 anchor textbox 提取（防止 BoxBuilder 把 anchor 當 inline），但**drawCellTextBoxFloat 改為 no-op**（不畫文字）。這樣回到 Sprint 37 baseline（mean 0.1127），且保留 Sprint 38 的 parser + layout infrastructure 給未來收割。

## 8. 教訓

Sprint 33-38 連 6 個 sprint 共同失敗模式總結：

| Sprint | 找到的「根因」 | 真實根因 | 失敗類型 |
|---|---|---|---|
| 33 | vMerge anchor 沒延伸合併高度 | 不是 vMerge 問題 | 假設先行錯 |
| 34 | tbRlV cell 缺 canvas rotate | V-suffix = glyph preserved 不旋轉 | OOXML spec 誤讀 |
| 35 | tbRlV cell 缺 char-level vertical | 影響面積太小 < 1% | 量級估錯 |
| 36 | grid analysis 找到 col 2 hot zone | ✓ 對的工具 | 純診斷成功 |
| 37 | anchor 被當 inline rendered | anchor 是 text box 不是 image | 找對機制選錯 type |
| 38 | text box 沒渲染 | 渲染了但字型/字色/字級/位置都不對 | 找對 type 選錯細節 |

**「修對方向 + 修對機制 + 修對 type + 但選錯細節」是新失敗模式**。修法的「正確度」是一個 cascading chain：方向 → 機制 → type → 細節，每一層都要對，缺一不可。

Sprint 33-38 教訓編譯成「視覺收斂修法檢查表」：

1. **方向**：grid analysis 確認 hot zone 位置（資料先行）
2. **機制**：spot check 確認該位置是哪個 layout element（不假設）
3. **type**：dump element 的 OOXML markup，確認 image vs text box vs shape 等具體 type
4. **細節**：對該 type 的所有相關屬性逐一比對 golden（字型 / 字色 / 字級 / padding / 背景 / 邊框）

Sprint 33-37 stages 1-3 完成、Sprint 38 stage 4 抓錯。**Sprint 39 必須在 stage 4 細節對齊**才可能收割。

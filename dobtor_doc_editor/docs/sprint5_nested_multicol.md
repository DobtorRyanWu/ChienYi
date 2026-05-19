# Sprint 5 巢狀表格 + Multi-column

**狀態**：W11+ 主線 Sprint 5 — Layout Engine 進階版面  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3.3 / 3.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)  
**前置**：[docs/sprint4_section_float_widow.md](sprint4_section_float_widow.md)

---

## 1. 範圍

Sprint 5 補完 Layout Engine 兩項版面進階功能：

1. **巢狀表格**（cell 內含 TableNode 遞迴 layout）
2. **Multi-column**（依 SectionNode.columns 切多欄流）

落地：

| 檔案 | 變更 |
|---|---|
| `static/src/core/ooxml/ast/types.ts` | `CellNode.content` 從 `ParagraphNode[]` 改為 `BlockNode[]` |
| `static/src/core/ooxml/table/TableParser.ts` | 移除 cell 內 TableNode 的 filter |
| `static/src/core/ooxml/styles/TableStyleApplicator.ts` | 跳過 cell 內 TableNode（不對巢狀表格遞迴套樣式） |
| `static/src/core/ooxml/mapper/ToCanvasEditor.ts` | cell 內 TableNode 暫降級為「[巢狀表格 N×M]」文字占位 |
| `static/src/core/layout/types.ts` | 新增 `NestedTableInCell` + `CellLayout.nestedTables?` |
| `static/src/core/layout/TableLayout.ts` | layoutCell 區分 paragraph / table；遞迴呼叫 layoutTable |
| `static/src/core/layout/Paginator.ts` | PaginateContext 加 columnCount/columnIndex/columnWidth/columnSpace；新增 `currentColumnX` / `nextColumnOrPage`；改 layParagraph / laySingleTable / placeFloatImage / flushPage 用 columnWidth / columnX |
| `static/src/core/layout/index.ts` | 公開 `NestedTableInCell` |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint5.test.ts`（新檔） | 8 | 巢狀表格 4 + Multi-column 4 |

**全套**：vitest 505 case 全綠（Sprint 4 後 497 → 505）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 巢狀表格 — `CellNode.content: BlockNode[]`

OOXML 規格允許 `<w:tbl>` 出現在 `<w:tc>` 內。Sprint 4 之前 AST 把 cell 內的 TableNode filter 掉，避免 layout 邏輯複雜化。Sprint 5 升級：

- **AST 改造**：`CellNode.content` 從 `ParagraphNode[]` → `BlockNode[]`（= `ParagraphNode | TableNode`）
- **TableParser**：移除 filter，cell 內 table 進入 AST
- **layoutCell**：用 type guard 區分 paragraph（→ lines）vs table（→ nestedTables）
- **CellLayout**：新增 `nestedTables?: NestedTableInCell[]`；cell.height 累加巢狀表格高度

**視覺順序簡化**：Sprint 5 把 cell.lines（所有段落）排在前面，nestedTables（所有巢狀表格）排在後面。**真實 fixture 中 cell 內混排「段落+表格+段落」極罕見**（多半是「只有段落」或「只有 1 張小表格」），這個簡化能避免 Sprint 5 引入更複雜的 block-order tracking。Sprint 6 再補完 paragraph/table 真實混排順序。

**ToCanvasEditor 降級**：cell 內 TableNode 在 canvas-editor IElement 結構不支援（IElement.type=table 不能巢狀），暫時降級為「[巢狀表格 R×C]」文字占位。Sprint 7（自寫 Renderer）才會真實繪製。

**TableStyleApplicator 跳過巢狀**：Sprint 5 不對 cell 內巢狀 TableNode 遞迴套表格樣式（避免 conditional style 跨層污染）。Sprint 6+ 評估是否補完。

### 2.2 Multi-column — column-flow Paginator

`SectionNode.columns: { count, space?, equalWidth? }` 在 Sprint 0 就有。Sprint 5 把 Paginator 改成支援多欄：

**PaginateContext 新增**：
- `columnCount`：欄數（1 = 單欄）
- `columnIndex`：當前欄 0..count-1
- `columnWidth`：每欄寬 = `(contentWidth - (count-1) * columnSpace) / count`
- `columnSpace`：欄間距（OOXML w:space 預設 36pt = 0.5 inch）

**核心邏輯**：
- `currentColumnX(ctx)` = `marginLeft + columnIndex * (columnWidth + columnSpace)`
- `nextColumnOrPage(ctx)`：column < count-1 時切下一欄；否則 flushPage
- 所有 lineWidth / X 計算改用 `columnWidth` / `columnX`

**段落、表格、float image 全部走欄級**：
- layParagraph：line break 用 columnWidth；overflow → nextColumnOrPage
- laySingleTable：tableContentWidth 限於 columnWidth；跨頁邏輯改 nextColumnOrPage
- placeFloatImage：以欄為基準 align（center/left/right）

**Widow/orphan**：原本直接 flushPage，Sprint 5 改用 nextColumnOrPage（允許切到下一欄）。

### 2.3 等寬 vs 不等寬欄

Sprint 5 採等寬簡化（`(contentWidth - gaps) / count`）。OOXML `w:cols` 也支援 `equalWidth=0` + 個別 `<w:col w:w="..."/>` 不等寬欄。**SectionNode.columns 結構目前不存個別欄寬**，留 Sprint 6 擴充 AST 與 Paginator。

### 2.4 column break（強制換欄）— 接口已備

`BoxBuilder` 把 `<w:br type="column">` 轉成 `flagged` penalty。LineBreaker 與 Paginator 目前把它當作 page break 處理（Sprint 4 行為）。Sprint 5 沒做完整 column break 處理，留 Sprint 6 — 接口已備。

---

## 3. fixture 統計（Sprint 4 → Sprint 5）

| 類別 | Sprint 4 avgPages | Sprint 5 avgPages |
|---|---|---|
| 全部 | 持平 | 持平 |

**讀法**：42 份 fixture **沒有 multi-column** 或巢狀表格，所以 smoke 統計沒變。Sprint 5 的功能由 8 個 Sprint5.test.ts 合成 fixture 驗證。

> 真實 fixture 含巢狀表格的情況：03_complex_table 的「送審管制」與「履約文件查對」可能有少量巢狀，但實際 audit 顯示主要是 14-18 欄寬表（不是巢狀）。Sprint 5 主要是 LATER 用戶把 Word 巢狀表格匯進來時不會炸。

---

## 4. Sprint 5 已知限制（→ Sprint 6+ 補完）

| 限制 | 原因 | 補完 Sprint | 對應規劃 |
|---|---|---|---|
| Cell 內 paragraph/table 混排視覺順序 | 簡化為「先 lines、後 nestedTables」 | Sprint 6 | §3.3 |
| 巢狀表格樣式繼承 | TableStyleApplicator 跳過 | Sprint 6+ | §3.3 / Phase 4 |
| ToCanvasEditor 巢狀表格真實渲染 | IElement 結構不支援 | Sprint 7（自寫 Renderer） | §3.3 / Phase 6 |
| 不等寬欄（individual col widths） | SectionNode.columns 結構不存 | Sprint 6 | §3.5 |
| Column break（`<w:br type="column">`）| 目前當 page break 處理 | Sprint 6 | §3.5 |
| Column balancing（末頁欄平衡） | 簡單 first-fit 即可 | Sprint 6+ | §3.5 |
| wrapSquare / wrapTight / wrapThrough 行寬動態 | LineBreaker 仍 const lineWidth | Sprint 6 | §3.4 |
| Cell 內部 mid-row break | 簡化跨頁 row-level | Sprint 6+ | §3.3 |
| Knuth-Plass 精細斷行 | 貪婪算法 baseline 已穩定 | Sprint 7+ | §3.1 |
| 表格邊框衝突解決 | 留 Renderer 處理 | Sprint 7 | Phase 4 |
| HarfBuzz 字型實測 metrics | EstimateMetrics 偏差 ±5% | Sprint 7+ | Phase 2 |
| 註腳 / 尾註 | Paginator 無 footnote 區概念 | Sprint 7+ | §3.6 |

---

## 5. 對 Sprint 1-4 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | `CellNode.content` 改型別，但 fixture 不含巢狀表格 → snapshot 未變 | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 同上 | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2/3/4） | layoutCell 行為微調（多了 nestedTables 路徑） | 48 case 全綠 |
| Sprint 2-4 unit tests | 無 | 全綠 |
| Python integration（54 case） | 無 | 全綠 |

**vitest 全套**：30 files / **505 tests pass**（Sprint 4 後 497 → 505，新增 8 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（29 → 30 files；497 → 505 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 5
npx vitest run tests/unit/layout/Sprint5.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 6）

依規劃 §3.4 + §3.3 殘餘工作 + §3.1（Knuth-Plass 開頭），建議優先：

1. **wrapSquare 行寬動態**（§3.4，最高用戶可見價值）
   - LineBreaker 加 `getLineWidth?: (y: Pt) => Pt` callback
   - Paginator 注入 callback：依當前 floatImage 計算 per-y 行寬
2. **Cell 內 paragraph/table 混排視覺順序**（§3.3 殘餘）
   - CellLayout.contents 用 union type 或 ordered list 取代 lines + nestedTables 兩欄
3. **不等寬欄**（§3.5 殘餘）
   - SectionNode.columns 加 `colWidths?: Pt[]`
   - SectionParser 抓 `<w:col w:w="..."/>` 個別欄寬
4. **Cell 內部 mid-row break**（§3.3 殘餘，最複雜）
   - 允許 cell 內 paragraph 跨頁

Sprint 6 完成後預期：
- 浮動圖片 wrapSquare 可在合成 fixture 跑通
- 巢狀表格 + 段落混排視覺順序正確

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 5。

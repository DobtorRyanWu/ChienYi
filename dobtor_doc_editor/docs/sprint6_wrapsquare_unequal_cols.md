# Sprint 6 wrapSquare + 不等寬欄 + Cell blocks ordered

**狀態**：W11+ 主線 Sprint 6 — Layout Engine 進階版面（行寬動態 / 不等寬 / 視覺順序）  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3.4 / 3.5 / 3.3](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)  
**前置**：[docs/sprint5_nested_multicol.md](sprint5_nested_multicol.md)

---

## 1. 範圍

Sprint 6 補完 Layout Engine 三項功能：

1. **wrapSquare 行寬動態**（per-y lineWidth callback；wrapTight/wrapThrough 簡化為 square 矩形）
2. **不等寬欄**（SectionNode.columns.colWidths + colSpaces；SectionParser 抽 `<w:col w:w="..."/>`）
3. **Cell paragraph/table 混排視覺順序**（CellLayout.blocks 依 source order）

落地：

| 檔案 | 變更 |
|---|---|
| `static/src/core/ooxml/ast/types.ts` | `SectionNode.columns.colWidths?` / `colSpaces?` 新增 |
| `static/src/core/ooxml/section/SectionParser.ts` | 抽 `<w:col>` 個別欄寬 + 欄距 |
| `static/src/core/layout/types.ts` | 新增 `CellBlock` union；`Line.xOffset?` 新增；`CellLayout.blocks` 新增 |
| `static/src/core/layout/LineBreaker.ts` | `getLineWidth` / `getLineXOffset` callback hooks；逐行套用、追蹤 `accumulatedHeight` |
| `static/src/core/layout/TableLayout.ts` | layoutCell 產出 `blocks` ordered list |
| `static/src/core/layout/Paginator.ts` | PaginateContext.activeFloats / ActiveFloat；placeFloatImage 對 wrapSquare 註冊排除區；layParagraph 注入 callback；computeColumnLayout 支援 colWidths；currentColumnX/currentColumnWidth helper |
| `static/src/core/layout/index.ts` | 公開 `CellBlock` |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint6.test.ts`（新檔） | 8 | 不等寬欄 2 + Cell blocks 2 + wrapSquare/callback 4 |
| `tests/unit/layout/SectionBreak.test.ts` | 1 case 行為更新 | wrapSquare 不再產生降級 warning |

**全套**：vitest 513 case 全綠（Sprint 5 後 505 → 513）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 wrapSquare per-y lineWidth — Sprint 6 主菜

**LineBreaker 介面擴充**：
```ts
interface LineBreakOptions {
  lineWidth: Pt;                                                      // 預設行寬（fallback）
  getLineWidth?: (lineIndex: number, accumulatedHeight: Pt) => Pt;    // 行寬覆寫
  getLineXOffset?: (lineIndex: number, accumulatedHeight: Pt) => Pt;  // 行 X 推右量
}
```

**為什麼用 callback 而不是 lineWidths 陣列**：
- Layout 過程中 LineBreaker 並不知道每行最終會放在哪個絕對 y 上（widow/orphan 可能整段推下頁）
- 段落起點 y 由 Paginator 在呼叫前確定，傳入 `paraStartAbsY`
- callback 收到 `accumulatedHeight`（從段落起點起算）後反算絕對 y，查詢 activeFloats

**Paginator 端**：
```ts
PaginateContext.activeFloats: ActiveFloat[]
interface ActiveFloat {
  yTop, yBottom, xLeft, xRight: Pt;
  side: 'left' | 'right';   // 由 image 中線 vs 欄中線判斷
  padding: 6;                // 圖片與內文間隔（pt）
}
```

當 `placeFloatImage` 看到 wrapSquare（或 wrapTight/Through 簡化版）：
1. 計算 image.x（依 align）
2. 判斷 side（image mid vs column mid）
3. push 到 `activeFloats`
4. **不擠壓 currentY**（讓內文與圖共存）

`layParagraph` 偵測到 activeFloats 非空時，傳入兩個 callback：
- `getLineWidth(li, accH)` = `baseLineWidth - leftPush - rightShrink`，依重疊判斷
- `getLineXOffset(li, accH)` = `leftPush`（左 float 把行推右）

**purgeStaleFloats**：每行放完後檢查 `activeFloats[].yBottom <= currentAbsY`，過期就清掉。

**簡化決策**：
- `wrapTight` / `wrapThrough` 規格上是 polygon 緊密貼邊；Sprint 6 簡化為 square 矩形 + warning 標 Sprint 7+ 補完
- `wrapSquare` 不再產生降級警告

### 2.2 不等寬欄

`SectionNode.columns.colWidths?` 新增（OOXML `<w:cols equalWidth="0"><w:col w:w="..." w:space="..."/>...</w:cols>`）。

**Paginator 重構**：
- PaginateContext 從 `columnWidth: Pt + columnSpace: Pt` 改為陣列 `columnWidths: Pt[] + columnSpaces: Pt[]`
- `currentColumnX(ctx)` 累加前 N 欄寬度 + 欄距得到 X
- `currentColumnWidth(ctx)` 取 `columnWidths[columnIndex]`

**fallback 策略**：
- 沒 colWidths → 等寬計算（Sprint 5 行為）
- colWidths 含 0（缺值）→ 平均分配剩餘空間給 0 的欄位

### 2.3 Cell blocks ordered list

**Sprint 5 限制**：`cell.lines + cell.nestedTables` 兩個平面陣列導致視覺順序失真：
- cell content 為 `[paragraph, table, paragraph]` 時，Sprint 5 模型把 lines（含兩個 paragraph）排在前，table 排在後
- 真混排（罕見但存在）會錯位

**Sprint 6 修正**：
```ts
type CellBlock =
  | { kind: 'lines'; sourceIndex; lines: Line[]; height }
  | { kind: 'table'; sourceIndex; table: NestedTableInCell };

interface CellLayout {
  blocks: CellBlock[];           // 新：依 source order
  lines: Line[];                 // Sprint 5 平面（向下相容）
  nestedTables?: NestedTableInCell[];   // Sprint 5 平面（向下相容）
}
```

`lines` 與 `nestedTables` 仍同步保留，Sprint 5 unit tests 無破壞。新版 Renderer 應用 `blocks`。

---

## 3. fixture 統計（Sprint 5 → Sprint 6）

42 份 fixture 不含 floatImage 也不用不等寬欄，smoke 統計沒變。Sprint 6 由 8 個合成 fixture 在 Sprint6.test.ts 驗證。

---

## 4. Sprint 6 已知限制（→ Sprint 7+ 補完）

| 限制 | 原因 | 補完 Sprint | 對應規劃 |
|---|---|---|---|
| wrapTight / wrapThrough polygon 緊密貼邊 | 簡化為 square 矩形 | Sprint 7+ | §3.4 |
| Cell 內部 mid-row break | 簡化跨頁 row-level | Sprint 7 | §3.3 |
| 巢狀表格樣式繼承 | TableStyleApplicator 跳過 | Sprint 7 | §3.3 |
| Knuth-Plass 精細斷行 | 貪婪算法 baseline 已穩定 | Sprint 7+ | §3.1 |
| 表格邊框衝突解決 | 留 Renderer 處理 | Sprint 7（Renderer） | Phase 4 |
| HarfBuzz 字型實測 metrics | EstimateMetrics 偏差 ±5% | Sprint 7+ | Phase 2 |
| 註腳 / 尾註 | Paginator 無 footnote 區概念 | Sprint 7+ | §3.6 |
| Column break（`<w:br type="column">`）| 目前當 page break 處理 | Sprint 7 | §3.5 |
| Column balancing | 簡單 first-fit | Sprint 7+ | §3.5 |
| Float image 與 multi-column 同時用 | 簡化（不依 columnIndex 區分 activeFloat） | Sprint 7+ | §3.4 + §3.5 |

---

## 5. 對 Sprint 1-5 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 無 | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-5） | 無 | 48 case 全綠 |
| Sprint 4 SectionBreak.test.ts | 1 case 行為更新（wrapSquare 不再降級） | 11 case 全綠 |
| Sprint 5 Sprint5.test.ts | 無 | 8 case 全綠 |

**vitest 全套**：31 files / **513 tests pass**（Sprint 5 後 505 → 513，新增 8 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（30 → 31 files；505 → 513 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 6
npx vitest run tests/unit/layout/Sprint6.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 7）

依規劃 §3.3（殘餘）+ §3.1（Knuth-Plass）+ Phase 4（樣式 + 邊框衝突），建議優先：

1. **Cell 內部 mid-row break**（§3.3，最複雜也最高用戶價值）
   - 允許 cell 內 paragraph 跨頁
   - laySingleTable 接受「row 太大時內部切」
2. **巢狀表格樣式繼承**（§3.3）
   - TableStyleApplicator 對 cell 內 TableNode 遞迴
3. **Column break / Column balancing**（§3.5）
   - `<w:br type="column">` 真正觸發 nextColumnOrPage
4. **wrapTight / wrapThrough polygon 緊密貼邊**（§3.4）
   - 從 OOXML wrapPolygon 解析多邊形頂點
   - LineBreaker per-y lineWidth 用 polygon 邊界計算

Sprint 7 完成後預期：
- 大型表格內含長 paragraph 不再被裁切
- 巢狀表格樣式正確繼承

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 6。

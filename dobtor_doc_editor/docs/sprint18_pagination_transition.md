# Sprint 18 R1 Transition 變體啟用 + Cell-Internal Page Break + Grid Search 工具

**狀態**：W11+ 主線 Sprint 18 — Paginator 對齊大躍進，全 fixture mismatched **17→7 (-59%)**，sumAbsDelta **26→7 (-73%)**
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint17_pagination_break.md](sprint17_pagination_break.md)、[docs/word_pagebreak_rules.md](word_pagebreak_rules.md)

---

## 1. 範圍

Sprint 17 留下三個交付物等 Sprint 18 接手：grid search 工具、ratio 調諧、R1 變體。本
sprint 額外發現第 4 個關鍵 root cause（cell-internal page break 不被處理）並一併補完。

| 子工項 | Sprint 17 留 | Sprint 18 交付 |
|---|---|---|
| Grid search 工具 | 規劃中 | ✅ `tests/integration/sprint18_ratio_grid_search.test.ts`（env-gated） |
| R1 ratio 調諧 | 預設 0（OFF） | ✅ ratio=0.34 + transition 變體（預設啟用） |
| R1 transition 變體 | 規劃中 | ✅ `ctx.lastRowWasImage` 追蹤；連續 image row 不破 |
| Cell-internal page break | 規劃外 | ✅ `splitRowAtPageBreak` + table-level guard |

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `tests/integration/sprint18_ratio_grid_search.test.ts` | A | env-gated grid search test（`SPRINT18_GRID_SEARCH=1` 觸發），對 12 個 ratio × 42 fixture 跑層 layout，輸出 `tests/fixtures/sprint18_ratio_grid_report.json` |
| `static/src/core/layout/Paginator.ts` | M | (1) PaginateContext + `lastRowWasImage` 追蹤；(2) `flushPage` / `layParagraph` 結尾重設旗標；(3) `laySingleTable` R1 改 transition 變體；(4) cell-internal `splitRowAtPageBreak` 接入 + table-level guard；(5) imageRowBreakRatio 預設 0.34 |
| `static/src/core/layout/TableLayout.ts` | M | 新增 export `splitRowAtPageBreak(row)`：偵測 cell.blocks 的 line.forcedBreakAfter='page'，依首個 break 切 first/second cell；無 break → null |
| `static/src/core/layout/types.ts` | M | LayoutOptions.imageRowBreakRatio 預設值與註解更新 |
| `tests/unit/layout/TableLayout.test.ts` | M | +5 case：splitRowAtPageBreak null / 單 cell 切 / 多 cell 切 / 巢狀 / containsImage 重算 |
| `tests/unit/layout/Paginator.test.ts` | M | +4 case：cell page break 兩頁 / 無 break 一頁 / image table fall through R1 / 連鎖切 |
| `tests/integration/__snapshots__/09_page_count_baseline.test.ts.snap` | M | mismatched 17→7、totalDelta -26→-7、sumAbsDelta 26→7 |
| `tests/integration/__snapshots__/08_render_ops_trace.test.ts.snap` | M | Sprint 12 fingerprint 隨 layout 改動同步更新 |

---

## 3. R1 ratio 調諧結果

### 3.1 第一輪 grid search（Sprint 17 R1，無 transition）

從 Sprint 17 audit：

| ratio | mismatched | totalDelta | sumAbsDelta |
|---|---|---|---|
| 0.0  | 17 | -26 | 26 |
| 0.30 | 23 | +9 | 37 ⚠ over-paginate |
| 0.4-1.0 | 17 | -26 | 26（threshold 太高，不觸發）|

無單一 ratio 改善 → Sprint 17 audit §9 建議：嘗試 transition 變體。

### 3.2 第二輪 grid search（R1 + transition 變體）

實作 transition 後重跑：

| ratio | mismatched | totalDelta | sumAbsDelta |
|---|---|---|---|
| 0.0  | 17 | -26 | 26 |
| 0.30 | 19 | -7 | 21 |
| 0.32 | 19 | -7 | 21 |
| **0.34** | **13** | **-14** | **14** ← best |
| 0.36 | 13 | -14 | 14 |
| 0.38 | 17 | -10 | 18 |
| 0.40+ | 17 | -26 | 26 |

ratio=0.34 / 0.36 出現 sweet spot。檢查 0.34 的 fixture-level diff：**4 個 04_with_image
fixture 從 -3 完美對齊 0，零 regression**。

### 3.3 R1 transition 變體實作

```ts
// PaginateContext 加 lastRowWasImage: boolean

// flushPage / layParagraph 結尾：lastRowWasImage = false

// laySingleTable each row:
const isLargeImageRow = row.containsImage
  && row.cantSplit
  && imageBreakRatio > 0
  && row.height >= ctx.contentHeight * imageBreakRatio;
const enterImageBlock = isLargeImageRow && !ctx.lastRowWasImage;
const leaveImageBlock = !isLargeImageRow && ctx.lastRowWasImage;
if ((enter || leave) && hasPriorContent && imageBreakRatio > 0) {
  // flushTableEntry → nextColumnOrPage → push tblHeader
}
ctx.lastRowWasImage = isLargeImageRow;
```

連續 image row（row[4] + row[5]）的 `lastRowWasImage` 都是 true → enterImageBlock=false，
不破。Word 行為一致：image block 內可同頁；boundary 才 break。

---

## 4. Cell-internal page break

### 4.1 發現

01_simple 7 個 fixture 各有 -1/-2 偏差。從 docx XML 看到 `<w:br w:type="page"/>` 標籤
但 Paginator 沒處理。Debug 後發現：

```ts
// AST page breaks (top-level): 0
// AST page breaks (in-cell):   2  ← 都在 table cell 內
```

我們的 ParagraphParser → BoxBuilder → LineBreaker 已正確把 `<w:br type="page"/>` 轉成
`Penalty(breakKind='page')` → `Line.forcedBreakAfter='page'`。但 Paginator.layParagraph
只處理 **top-level** Line.forcedBreakAfter；**cell-internal** Line 進入 `cell.blocks`
裡面，從未被 Paginator 檢視 → 漏觸發。

### 4.2 實作

新增 `splitRowAtPageBreak(row)`（in `TableLayout.ts`）：
- 走訪 row.cells[*].blocks[*].lines，找第一個 `forcedBreakAfter='page'` 的 line
- 該 line 之前（含本身）的 lines 入 firstHalf，之後 + 後續 blocks 入 secondHalf
- 沒 break 的 cell：整 cell 在 first，second 為空 placeholder
- 沒任何 break：回 null

`laySingleTable` 整合：
```ts
// Sprint 18：cell-internal page break（排除 image-rich 表，避免與 R1 雙觸發）
if (!tableHasImageRow) {
  const split = splitRowAtPageBreak(row);
  if (split) {
    pendingRows.push(split.first);
    flushTableEntry(true);
    flushPage(ctx);
    leftoverRow = split.second;  // 下輪續處理
    continue;
  }
}
```

### 4.3 Table-level Guard（避免 R1 + cell-break 雙觸發）

早期實驗（無 guard）：04_with_image 4 fixture 從 0 翻 +5（雙觸發 over-paginate +5）。
原因：04_with_image 表內既有 image row（R1 會觸發）又有 cell-internal break，兩者
重疊覆蓋同一頁邊界 → 算 2 次。

修正：`tableHasImageRow = rows.some(r => r.containsImage)`。整張表含 image row 時，
頁邊界由 R1 主導，cell-break 不啟用。

### 4.4 改善效果

| 類別 | 改善前（Sprint 17 R1 OFF） | Sprint 18 |
|---|---|---|
| 01_simple | 7 fixtures: 1×-2, 6×-1（共 -8）| 1 fixture: -1 |
| 02_std_table | 1 fixture: -1 | 1 fixture: -1 |
| 03_complex_table | 5 fixtures: 5×-1 + 04 with image -3×4 | 2 fixtures: 2×-1 |
| 04_with_image | 4×-3 + 1×-1 + 1×-1 + 1×-1 | 0 mismatched |
| 05_header_footer | 3×-1 | 3×-1（未動） |

---

## 5. 全 fixture 改善總結

| 指標 | Sprint 16 baseline | Sprint 17 結束 | **Sprint 18 結束** | Sprint 16→18 改善 |
|---|---|---|---|---|
| mismatched | 17/42 | 17/42 | **7/42** | **-59%** |
| totalDelta | -26 | -26 | **-7** | **-73%** |
| sumAbsDelta | 26 | 26 | **7** | **-73%** |
| 04_with_image -3 | 4 個 | 4 個 | **0 個** | **完全修復** |
| 01_simple -1/-2 | 7 個 | 7 個 | **1 個** | **-86%** |

剩下 7 個 -1 fixture 可能對應規則 R6（keepNext / keepLines）或其他細節，留 Sprint 19+。

---

## 6. 對 Sprint 1-17 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **更新**（layout 改 → ops 改）| 2 case 全綠 |
| `09_page_count_baseline.test.ts`（Sprint 16）| **更新**（17→7 mismatched）| 2 case 全綠 |
| `TableLayout.test.ts` | **+5 case** | 25 case 全綠 |
| `Paginator.test.ts` | **+4 case** | 22 case 全綠 |
| Sprint 18 grid_search test | **+1 case (skipped)** | env-gated，預設不跑 |
| Visual regression v14 | layout 改 → 預期 mean diff 略動，但 baseline 鎖在 0.50 上限 | 待 Sprint 19 重跑驗證 |
| Python integration | 無 | 61 case 全綠 |

**vitest 全套**：**46 files / 724 tests pass + 1 skipped**（Sprint 17 後 46/712 → 46/724 + 1 skipped，**+13 case**）。

---

## 7. 已知限制（Sprint 19+ 補完）

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| 7/42 fixture 仍有 -1 偏差 | 多數可能對應 R6 keepNext/keepLines | Sprint 19+ |
| Cell-internal break 在 image-rich 表內 fall through | 雙觸發 over-paginate 風險 | 累積樣本後可細化（如 row-by-row 判斷而非 table-level） |
| splitRowAtPageBreak 不處理巢狀表內的 break | 簡化決策，極罕見 | Sprint 19+ |
| Visual regression v14 baseline 未重跑 | 計算成本高（puppeteer 全 fixture 渲染）| Sprint 19+ 重跑 |

---

## 8. 驗證指令

```bash
# 跑 Sprint 18 grid search（env-gated，預設 skip）
SPRINT18_GRID_SEARCH=1 npx vitest run tests/integration/sprint18_ratio_grid_search.test.ts

# 跑 Sprint 18 新增 unit tests
npx vitest run tests/unit/layout/TableLayout.test.ts tests/unit/layout/Paginator.test.ts

# 全套 regression（46 files / 724 tests + 1 skipped）
npm test

# Python integration
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev --test-tags dobtor_doc_editor --stop-after-init --xmlrpc-port=8169
```

---

## 9. 下個 Sprint（Sprint 19）建議

1. **R6 keepNext / keepLines 實作**
   - 對 7 個剩 -1 偏差 fixture 抽 docx XML，確認是否含 keepNext/keepLines
   - 若是：實作 paragraph 黏連（pre-pass 切 group + atomic 排版）
   - 若否：往別的方向找 root cause（header/footer 高度算錯？）

2. **Visual regression v14 重跑 + 收斂門檻**
   - layout 改動後，重跑 puppeteer harness 全 42 fixture
   - 預期 mean diff 略改善（pages 多了 → 更接近 golden）
   - 視結果決定是否把 max-diff 從 0.5 收斂到 0.4 或 0.3

3. **Cell-internal break 細化**
   - 目前 table-level guard 太粗；改成 per-row（只跳過含 image 的 row 內的 break）
   - 需新樣本驗證此細化不破壞 04_with_image 已對齊狀態

**建議優先順序**：1（最大 ROI）→ 2（驗證視覺）→ 3（精修）

---

## 10. 變更摘要

| 範疇 | Sprint 17 結束 | **Sprint 18 結束** | 差量 |
|---|---|---|---|
| vitest test files | 46 | 46 (+1 skipped grid_search) | 同 |
| vitest test cases | 712 | **724 + 1 skipped** | +12 active |
| Python tests | 61 | 61 | 同 |
| Layout output | Sprint 16 baseline 不變 | **17→7 mismatched (-59%)** | **大幅改善** |
| Paginator features | 17 個（R1 opt-in） | **19 個**（R1 transition default-on + cell-internal break） | +2 |
| OOXML rules 已知模型 | R1-R6 文件化 | + cell-internal break 規則 | +1 已實作規則 |

---

**附註**：Sprint 1-18 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染
- Sprint 12：完整 field 系統 + Renderer ops fingerprint regression
- Sprint 13：OOXML docProps + Knuth-Plass opt-in
- Sprint 14：自家 pipeline IIFE + puppeteer harness + 42 fixture / 100 頁 baseline
- Sprint 15：圖片真渲染（pre-load + imageResolver + async render）+ doc.template UI bug 完整修復
- Sprint 16：頁數對齊 baseline lock（vitest snapshot 鎖 17/42 mismatched）+ Word page-break 規則差距文件化
- Sprint 17：Word page-break 規則樣本資料庫 + RowLayout.containsImage + Paginator R1 image-row break heuristic（opt-in）
- **Sprint 18：R1 transition 變體啟用（ratio=0.34 grid search）+ cell-internal page break + table-level guard，全 fixture mismatched 17→7 (-59%)、sumAbsDelta 26→7 (-73%)**

到 Sprint 18，Paginator 對 docx 規則的還原度（從 page count 衡量）：
- 結構性鎖：Sprint 12 fingerprint snapshot
- 頁數鎖：Sprint 16 page count snapshot（17/42 mismatched）→ **Sprint 18 收斂為 7/42**
- 像素級基準：Sprint 14 baseline（mean diff 17.73%，待 Sprint 19 重跑）

Sprint 19 主軸：R6 keepNext + visual regression 收斂。剩下 7 個 -1 偏差是「最後一哩路」。

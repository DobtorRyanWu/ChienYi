# Sprint 17 Word Page-Break 規則知識庫 + Image-Row Break Heuristic Infra

**狀態**：W11+ 主線 Sprint 17 — Paginator 加 image-row break heuristic infrastructure（預設 OFF）+ Word page-break 規則樣本資料庫
**完成日期**：2026-05-08
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §0.5](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)
**前置**：[docs/sprint16_pagination_baseline.md](sprint16_pagination_baseline.md)

---

## 1. 範圍

Sprint 16 把全 fixture 的 page count 鎖到 vitest snapshot，並提出 Sprint 17+ 應「累積
Word 規則樣本後再動 Paginator」。Sprint 17 依此優先順序交付：

1. **Word page-break 規則樣本資料庫**（[docs/word_pagebreak_rules.md](word_pagebreak_rules.md)）
2. **`RowLayout.containsImage` 旗標**（infrastructure）
3. **Paginator R1 image-row break heuristic**（opt-in，預設 OFF）

刻意**不修 Sprint 16 baseline snapshot**，避免在 Word 規則樣本不足時做出隨機修正。

---

## 2. 落地檔案

| 檔案 | 狀態 | 變更 |
|---|---|---|
| `docs/word_pagebreak_rules.md` | A | Sprint 16 觀察的 Word page-break 規則資料庫（R1-R6 + 4 個 pending），含 04_with_image fixture 的 trPr / wp:extent 細部解構 |
| `static/src/core/layout/types.ts` | M | RowLayout 加 `containsImage: boolean`；LayoutOptions 加 `imageRowBreakRatio?: number` |
| `static/src/core/layout/TableLayout.ts` | M | layoutRow 計算 `containsImage`；新增 `cellsContainImage` / `cellHasImage` helper（含巢狀表格遞迴） |
| `static/src/core/layout/Paginator.ts` | M | `laySingleTable` 加 R1 條件判斷（opt-in）：`row.containsImage && row.cantSplit && row.height ≥ contentHeight × imageBreakRatio && hasPriorContent` 時 flushTableEntry + nextColumnOrPage |
| `tests/unit/layout/TableLayout.test.ts` | M | +5 case：純文字 row / image row / 巢狀表內 image / vMerge continuation / layoutTable 全部 row 旗標 |
| `tests/unit/layout/Paginator.test.ts` | M | +6 case：預設 OFF / opt-in 大 image / opt-in 小 image / opt-in non-cantSplit / opt-in 空頁 / layoutDocument 預設 OFF |

---

## 3. 為何 R1 heuristic 預設 OFF

### 3.1 Sprint 17 早期實驗

把 `imageRowBreakRatio` 預設 `0.3` 跑 09_page_count_baseline：

| 指標 | Sprint 16 baseline | Sprint 17 ratio=0.3 |
|---|---|---|
| mismatched | 17 / 42 | 23 / 42（+6） |
| totalDelta | -26 | +9（從 under-paginate 翻成 over-paginate） |
| 04_with_image delta | -3 | **+3** |

ratio=0.3 把 04_with_image 的 image row 全部各自獨佔頁面：

```
我們 ratio=0 ：1 頁含全 6 row table（< 742pt 容量）
我們 ratio=0.3：std rows 1 頁、row[4] 1 頁、row[5] 1 頁、std rows of next table 同頁、…
                → 9 頁
golden Word    ：6 頁（image row 與後續 std rows 共頁，規則更精細）
```

ratio=0.3 對 04_with_image 過度切頁。Word 真實邏輯**不是「每個大型 image row 都獨佔一頁」**，
而是更微妙的「image row 之後（不是之前）才是強斷點」「連續 image row 可共頁」「下一張表
的 std rows 可接在 image row 後」等規則 — 需要更多 fixture 樣本才能確定。

### 3.2 對齊 Sprint 16 audit §4.3 的決策

Sprint 16 audit §4.3 已預測此風險（方案 A 風險：「5+ fixture 的 -1 偏差可能變 +1 / +2」）。

**Sprint 16 採用方案 C**：累積 Word 規則樣本後再動。Sprint 17 在此原則下：

- 完成「樣本資料庫」基礎建設（R1-R6 規則 + 4 pending）
- 完成「heuristic infrastructure」（containsImage flag、ratio option、Paginator 條件分支）
- 預設 ratio=0 確保 baseline snapshot 完全不變
- 留待 Sprint 18+ 累積夠樣本後，啟用 ratio 調整為合適值

### 3.3 Sprint 18+ 啟用 R1 的條件

需先完成以下其中一項才動 ratio 預設：

- 至少 5 個額外 image-row fixture（涵蓋連續 image / 跨表 image / image+keepNext 互動）
- 對 5-10 個 ratio 值做矩陣搜尋，挑全 fixture totalDelta 最低（接近 0）的 ratio
- 確認啟用 R1 後 Sprint 16 baseline snapshot 變動方向**收斂於 0**（不是翻面）

---

## 4. R1 Heuristic 條件詳解

```ts
// in laySingleTable (Paginator.ts)
const imageBreakRatio = options.imageRowBreakRatio ?? 0;   // 預設 OFF

const isLargeImageRow = row.containsImage
  && row.cantSplit
  && imageBreakRatio > 0
  && row.height >= ctx.contentHeight * imageBreakRatio;
const hasPriorContent = pendingRows.length > 0 || ctx.entries.length > 0;

if (isLargeImageRow && hasPriorContent) {
  if (pendingRows.length > 0) flushTableEntry(/* more = */ true);
  nextColumnOrPage(ctx);
  isContinuation = true;
  // ...重新 push tblHeader rows
}
```

**4 個必要條件**（缺一不觸發）：

1. `row.containsImage`：row 含 inline image（透過 cell.blocks.lines.items 走訪）
2. `row.cantSplit`：Word 標記不可切斷的 row（避免破壞 cantSplit 語意）
3. `row.height >= contentHeight × ratio`：高度占比達門檻
4. `hasPriorContent`：當前頁/欄已有內容（空頁不必換）

**觸發行為**：先把 pending rows flush 到當前 entry，換新頁/欄，重 push tblHeader，
然後此 row 從新頁起點放。

---

## 5. RowLayout.containsImage 計算邏輯

```ts
function cellsContainImage(cells: CellLayout[]): boolean {
  return cells.some(cellHasImage);
}

function cellHasImage(cell: CellLayout): boolean {
  for (const block of cell.blocks) {
    if (block.kind === 'lines') {
      for (const line of block.lines) {
        for (const item of line.items) {
          if (item.kind === 'box' && item.isImage) return true;
        }
      }
    } else {
      // 巢狀表格：遞迴
      for (const row of block.table.rows) {
        if (cellsContainImage(row.cells)) return true;
      }
    }
  }
  return false;
}
```

**特性**：
- 走訪 `cell.blocks`（Sprint 6 的 ordered blocks 模型，含 paragraph lines + nested table）
- 巢狀表格遞迴檢查（極罕見但保證正確）
- vMerge isContinuation cell 自然回 false（blocks 為空）
- floatImage 不算（已被 ParagraphParser 從 RunNode 流分流；Box.isImage 只標記 inline image）

---

## 6. 對 Sprint 1-16 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-7） | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts`（Sprint 10） | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（Sprint 12 fingerprint） | **完全不變** | 2 case 全綠 |
| `09_page_count_baseline.test.ts`（Sprint 16 snapshot） | **預設 OFF → 完全不變** | 2 case 全綠 |
| `TableLayout.test.ts` | **+5 case** | 20 case 全綠 |
| `Paginator.test.ts` | **+6 case** | 15 case 全綠 |
| Visual regression v14 | 預設 OFF → layout output 完全相同 → 與 Sprint 15 一致 | rendered 42/42, mean diff 0.1773 |
| Python integration | 無 | 61 case 全綠 |

**vitest 全套**：**46 files / 712 tests pass**（Sprint 16 後 46/701 → 46/712，+11 case）。

---

## 7. 已知限制（Sprint 18+ 補完）

| 限制 | 原因 | 補完 Sprint |
|---|---|---|
| R1 heuristic 預設 OFF | 樣本不足，ratio=0.3 在 04_with_image 過度切頁 | Sprint 18+ 累積樣本 |
| 17/42 fixture page count 仍不對齊 golden | Word 規則 R1 / R6 / R-pending-1..4 待補 | Sprint 18+ |
| 沒有 ratio 矩陣搜尋工具 | 手動跑 4-5 個 ratio 值試 | Sprint 18+（建 scripts/ratio_grid_search.mjs） |
| keepNext / keepLines 未實作 | 樣本資料庫提到但本 sprint 範圍外 | Sprint 18+（規則 R6） |
| trHeight w:hRule="exact" + image overflow 截斷渲染 | Renderer 未檢查 | Sprint 18+（規則 R-pending-2） |

---

## 8. 驗證指令

```bash
# 跑 Sprint 17 新增的 unit tests
npx vitest run tests/unit/layout/TableLayout.test.ts tests/unit/layout/Paginator.test.ts

# 確認 Sprint 16 baseline 完全不變
npx vitest run tests/integration/09_page_count_baseline.test.ts

# 全套 regression（46 files / 712 tests）
npm test

# 手動測 R1 啟用後行為（用 Node REPL 或 ad-hoc script）
#   imageBreakRatio=0.3 跑全 fixture，比較 mismatched / totalDelta

# Python integration（不變）
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev --test-tags dobtor_doc_editor --stop-after-init --xmlrpc-port=8169
```

---

## 9. 下個 Sprint（Sprint 18）建議

Sprint 17 把 R1 infrastructure 與規則樣本資料庫建好。Sprint 18 候選方向：

1. **建 ratio grid search 工具**（scripts/ratio_grid_search.mjs）
   - 跑 ratio ∈ {0.3, 0.4, 0.5, 0.6, 0.7} × 全 42 fixture
   - 產出矩陣 JSON：每個 cell 是 (mismatched, totalDelta)
   - 找最佳 ratio；若無單一 ratio 對所有 fixture 都好 → 證明需要更精細 heuristic

2. **R6 keepNext / keepLines 實作**
   - 對 01_simple 7 個 -1 偏差最有可能是 keepNext 衝突
   - Paginator 在跨頁前判斷段落 props.keepNext，必要時推前段也下頁

3. **連續 image row 的 R1 變體**
   - 若 ratio 1 個值不夠好，改 R1 為「只在 lastRowWasImage=false 時觸發」
   - 連續 image row 不破，避免 Sprint 17 ratio=0.3 的 over-paginate 問題

**建議優先順序**：1（建工具）→ 3（精修 R1）→ 2（拓展 R6）

---

## 10. 變更摘要

| 範疇 | Sprint 16 結束 | Sprint 17 結束 | 差量 |
|---|---|---|---|
| vitest test files | 46 | 46 | 同 |
| vitest test cases | 701 | **712** | +11 |
| Python tests | 61 | 61 | 同 |
| Layout output | Sprint 15 baseline | **完全相同**（R1 預設 OFF） | 0 |
| Visual regression mean diff | 17.73% | 17.73%（不變） | 0 |
| Paginator features | 16 個 | **17 個**（+R1 opt-in） | +1 |
| OOXML rules 已知模型 | 隱式 | **明確 R1-R6 文件化** | +6 規則 |

---

**附註**：Sprint 1-17 累計（W11+ 主線）：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2-7：Layout Engine 主軸
- Sprint 8：Renderer 起步 + FontMetricsAdapter + CellLayout.borders
- Sprint 9：BrowserCanvasRenderContext + cell.blocks 視覺順序 + shading + 文字裝飾
- Sprint 10：欄分隔線 + PAGE/NUMPAGES 真值 + 全 fixture Render smoke
- Sprint 11：Page header / footer 渲染 + PAGE 在 header/footer 自動套真值
- Sprint 12：完整 field 系統（DATE/TIME/AUTHOR/FILENAME）+ Renderer ops fingerprint regression
- Sprint 13：OOXML docProps/core.xml 自動讀取 + Knuth-Plass 斷行器（opt-in）
- Sprint 14：自家 pipeline IIFE bundle + puppeteer harness + 42 fixture / 100 頁 baseline
- Sprint 15：圖片真渲染（pre-load + imageResolver + async render）+ doc.template UI bug 完整修復（含 form view content_html 隱藏欄位 onchange 寫回）
- Sprint 16：頁數對齊 baseline lock（vitest snapshot 鎖 17/42 mismatched fixture）+ Word page-break 規則差距文件化
- **Sprint 17：Word page-break 規則樣本資料庫（R1-R6 + 4 pending）+ RowLayout.containsImage infrastructure + Paginator R1 image-row break heuristic（opt-in，預設 OFF；ratio 樣本不足，留 Sprint 18 grid search）**

到 Sprint 17，Paginator 進階所需的「規則層 / 機制層 / 樣本層」**完整建構**：
- 規則層：[docs/word_pagebreak_rules.md](word_pagebreak_rules.md)（R1-R6 規則文件）
- 機制層：`RowLayout.containsImage` 旗標 + `LayoutOptions.imageRowBreakRatio` 控制
- 樣本層：[docs/sprint16_pagination_baseline.md](sprint16_pagination_baseline.md) +
  09_page_count_baseline snapshot（17/42 mismatched fixture 鎖死）

Sprint 18 起可有計畫地透過 ratio grid search 啟用 R1，或加 R6 keepNext。

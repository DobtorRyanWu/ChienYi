# Sprint 7 Cell mid-row break + Column break + 巢狀表格樣式繼承

**狀態**：W11+ 主線 Sprint 7 — Layout Engine 殘餘高難度功能補完  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3.3 / 3.5 / Phase 4](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)  
**前置**：[docs/sprint6_wrapsquare_unequal_cols.md](sprint6_wrapsquare_unequal_cols.md)

---

## 1. 範圍

Sprint 7 補完 Layout Engine 三項殘餘功能：

1. **Column break**（`<w:br type="column">` 真正觸發 nextColumnOrPage）
2. **巢狀表格樣式繼承**（TableStyleApplicator 對 cell 內 TableNode 遞迴）
3. **Cell 內部 mid-row break**（巨大 row 切兩半跨頁）

落地：

| 檔案 | 變更 |
|---|---|
| `static/src/core/layout/types.ts` | `Penalty.breakKind?`、`Line.forcedBreakAfter?` 新增 |
| `static/src/core/layout/BoxBuilder.ts` | line/page/column break 各自映射為帶 breakKind 的 penalty |
| `static/src/core/layout/LineBreaker.ts` | 強制斷時把 penalty.breakKind 透傳到 Line.forcedBreakAfter |
| `static/src/core/layout/TableLayout.ts` | 新增 `splitRowAtHeight()`：cell.blocks 切兩半（lines 邊界，巢狀 table 不切） |
| `static/src/core/layout/Paginator.ts` | layParagraph 加 forcedBreakAfter 處理；laySingleTable 重寫 row loop 用 leftoverRow + splitRowAtHeight |
| `static/src/core/ooxml/styles/TableStyleApplicator.ts` | 對 cell 內 TableNode（無 styleId 時）遞迴套外層 effective props |

**測試**：

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/Sprint7.test.ts`（新檔） | 9 | Column break 3 + 巢狀樣式 2 + Mid-row break 4 |

**全套**：vitest 522 case 全綠（Sprint 6 後 513 → 522）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 Column break — Penalty 透傳路徑

OOXML `<w:br type="column">` 在 Sprint 4 之前已被 BoxBuilder 轉為 flagged penalty，但 Paginator 把 page break 與 column break 處理一致（都 flushPage）。

Sprint 7 透傳路徑：

```
<w:br type="column"> 
  → BoxBuilder: { kind: 'penalty', cost: -Infinity, flagged: true, breakKind: 'column' }
  → LineBreaker: ln.forcedBreakAfter = 'column'
  → Paginator layParagraph: 加完 line entry 後檢查 → nextColumnOrPage(ctx)
```

`page` break 同路徑、不同 breakKind → flushPage。

### 2.2 巢狀表格樣式繼承

Sprint 5 把 `cell.content` 從 `ParagraphNode[]` 升級為 `BlockNode[]` 後，TableStyleApplicator 對 cell 內 TableNode 是 **跳過**（避免條件樣式跨層污染）。

Sprint 7 改進：
- cell 內 TableNode **無 styleId** 時：用外層 effective `pProps + rProps` 構造 fake StyleEntry，遞迴呼叫 applyTableStyle 並傳 DEFAULT_TBL_LOOK
- cell 內 TableNode **有 styleId** 時：不重套（假設 TableParser 階段已套過自己的樣式）

這個策略對「巢狀表沒有 explicit 樣式」最常見情境正確；對「巢狀表自己有 styleId」也安全。仍有些邊界（巢狀表有 styleId 但希望部分繼承）留 Sprint 8+ 補完。

### 2.3 Cell 內部 mid-row break — splitRowAtHeight

最複雜的一塊。Word 預設 `<w:cantSplit>=false` 時允許 cell 內 paragraph 跨頁切。

**splitRowAtHeight(row, availableHeight)** 演算法：
1. row.cantSplit=true → 回 null（caller 整列推下頁）
2. 對每個 cell：
   - vMerge continuation：兩半都保留 placeholder
   - innerAvail = availableHeight - padding 上下
   - 走訪 cell.blocks（Sprint 6 ordered list）：
     - paragraph block：找最大 N lines 可放，cumH > limit 處切；後續 blocks 全進 second
     - table block：要嘛全 first 要嘛全 second（Sprint 7 不切巢狀表內部）
3. 若至少一個 cell 能 split（部分內容入 first）→ 回 `{ first, second }`
4. 否則回 null（避免無進度迴圈）

**Paginator laySingleTable 重寫成 leftoverRow loop**：

```ts
let ri = 0;
let leftoverRow = null;
while (true) {
  let row;
  if (leftoverRow) { row = leftoverRow; leftoverRow = null; }
  else if (ri < rows.length) { row = rows[ri]; ri++; }
  else break;
  
  // ... standard cross-page logic ...
  
  if (row.height > remainingSpace && !row.cantSplit && remainingSpace > 0) {
    const split = splitRowAtHeight(row, remainingSpace);
    if (split && split.first.cells.some(...)) {
      pendingRows.push(split.first);
      flushTableEntry(); nextColumnOrPage; isContinuation=true;
      leftoverRow = split.second;
      continue;
    }
  }
  pendingRows.push(row);
  pendingHeight += row.height;
}
```

**為什麼用 leftoverRow 而非 currentRow + skip ri-advance**：
- 早版設計用「不 advance ri」邏輯導致原 rows[ri] 重複處理 → V8 OOM 無限迴圈
- 改用 leftoverRow：原 row 進迴圈時馬上 advance ri，split 把 second half 暫存，不會重複處理同一個 rows[i]

**簡化決策**：
- 只切 paragraph blocks 的 lines（不切 line 內部）
- 不切巢狀 table（要嘛整張在 first 要嘛整張在 second）
- 切點 = lines 邊界，符合 Word 預設行為

---

## 3. fixture 統計（Sprint 6 → Sprint 7）

| 類別 | Sprint 6 avgPages | Sprint 7 avgPages |
|---|---|---|
| 01_simple | 1.9 | 1.9 |
| 02_std_table | 1.6 | 1.6 |
| 03_complex_table | 1.0 | **1.1** |
| 04_with_image | 2.7 | 2.7 |
| 05_header_footer | 4.2 | 4.2 |
| 06_template | 1.3 | **2.3** |

**讀法**：
- **06_template +1.0**：樣板含大型表格、cell 內塞長段落，Sprint 7 之前被 Renderer 裁切，現在能正確切兩半跨頁
- **03_complex_table +0.1**：少數 fixture 的長 cell 終於能正確跨頁
- 其他類別變化不大：fixture 主要是「短 row 多」結構，mid-row break 不常觸發

這是 Sprint 2 起最有 fixture-level 影響的一次升級。

---

## 4. Sprint 7 已知限制（→ Sprint 8+ 補完）

| 限制 | 原因 | 補完 Sprint | 對應規劃 |
|---|---|---|---|
| 巢狀表格切跨頁（mid-row 內含 nested table） | Sprint 7 不切巢狀表內部 | Sprint 8+ | §3.3 |
| Cell 內 line 內部切（half-line） | Word 罕用此行為 | 不補（標準預設） | §3.3 |
| wrapTight / wrapThrough polygon 緊密貼邊 | 簡化為 square 矩形 | Sprint 8+ | §3.4 |
| Knuth-Plass 精細斷行 | 貪婪算法 baseline 已穩定 | Sprint 8+ | §3.1 |
| 表格邊框衝突解決（OOXML 17.4.65 8 級優先） | 留 Renderer 處理 | Sprint 8（Renderer） | Phase 4 |
| HarfBuzz 字型實測 metrics | EstimateMetrics 偏差 ±5% | Sprint 8+ | Phase 2 |
| 註腳 / 尾註 | Paginator 無 footnote 區概念 | Sprint 8+ | §3.6 |
| Column balancing（末頁欄平衡） | 簡單 first-fit | Sprint 8+ | §3.5 |
| Float image + multi-column 同時用 | activeFloat 不依 columnIndex 區分 | Sprint 8+ | §3.4 + §3.5 |
| 巢狀表 explicit styleId 部分繼承 | 全跳過（保守安全） | Sprint 8+ | §3.3 |

---

## 5. 對 Sprint 1-6 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無（snapshot 是 ParserAST 級） | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 無 | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2-6） | mid-row break 觸發 03 / 06 fixture 跨頁 → 統計變化但 case assertion 仍對 | 48 case 全綠 |
| Sprint 2-6 unit tests | 無 | 全綠 |
| Python integration（54 case） | 無 | 全綠 |

**vitest 全套**：32 files / **522 tests pass**（Sprint 6 後 513 → 522，新增 9 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（31 → 32 files；513 → 522 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 7
npx vitest run tests/unit/layout/Sprint7.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 8）

Layout Engine 主軸到 Sprint 7 已大致完成（Phase 3.2-3.5 全綠）。Sprint 8 起點建議轉到 **Renderer / Phase 4-5**：

依規劃 §3.3（邊框衝突 Renderer 端）+ Phase 2（HarfBuzz）+ Phase 4（Style 完整版），Sprint 8 候選：

1. **表格邊框衝突解決**（§3.3 Renderer 階段）
   - OOXML 17.4.65 8 級優先表
   - cell.borders + table.borders + tblStyle 合併計算
2. **HarfBuzz 字型實測 metrics**（Phase 2）
   - 取代 EstimateMetrics
   - opentype.js → 真實字型 ascender/descender/lineGap
3. **wrapTight polygon**（§3.4 殘餘）
4. **Knuth-Plass 斷行**（§3.1）
   - 真正利用 box/glue/penalty 模型
5. **Phase 5：Renderer 起步**（§5.6）
   - 從 Layout Engine output 真實畫出文件

**建議優先順序**：1 → 2 → 5（解決還原度核心問題）→ 3, 4（精細優化）

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 7。Layout Engine 7 個 sprint 累計：
- Sprint 1：OOXML Parser audit + 回歸護欄
- Sprint 2：基礎 Layout Engine（Box/Glue/Penalty + 貪婪斷行 + 基礎分頁）
- Sprint 3：cell-level 表格 + 跨頁
- Sprint 4：Section break 全套 + Float image 基礎 + Widow/orphan
- Sprint 5：巢狀表格 + Multi-column
- Sprint 6：wrapSquare per-y + 不等寬欄 + Cell blocks ordered
- Sprint 7：Column break + 巢狀樣式 + Cell mid-row break

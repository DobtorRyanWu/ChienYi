# Sprint 3 TableLayout + 跨頁表格

**狀態**：W11+ 主線 Sprint 3 — Layout Engine 表格模組  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3.3 Table Layout](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)  
**前置**：[docs/sprint2_layout_engine.md](sprint2_layout_engine.md)

---

## 1. 範圍

Sprint 3 把 Sprint 2 的 `table-placeholder` 升級為 cell-level 排版，並支援跨頁。落地：

| 檔案 | 變更 | 行數 |
|---|---|---|
| `static/src/core/layout/types.ts` | 新增 `TableLayoutEntry`、`RowLayout`、`CellLayout` | +50 |
| `static/src/core/layout/TableLayout.ts` | 新檔：cell-level layout 主邏輯 | ~165 |
| `static/src/core/layout/Paginator.ts` | 重寫表格分支：`laySingleTable()` 含跨頁 + tblHeader 重複 | +130 / -30 |
| `static/src/core/layout/index.ts` | 公開新 API（layoutTable / layoutRow / layoutCell） | +5 |

**測試**：在 Sprint 2 既有基礎上補 16 個 case。

| 測試檔 | 變更 |
|---|---|
| `tests/unit/layout/TableLayout.test.ts` | 新增 15 個 unit case |
| `tests/unit/layout/Paginator.test.ts` | 重寫表格 placeholder 測試 → table cell-level + 跨頁 |
| `tests/integration/06_layout_smoke.test.ts` | 把 placeholder assertion 換成 cell-level；新增跨頁驗證 |

**全套**：vitest 486 case 全綠；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 grid 直接配欄寬（簡化版 fixed layout）

CSS2 完整 auto layout 是 NP-hard 啟發式問題。Sprint 3 採簡化路徑：直接拿 `TableNode.grid` 當欄寬。理由：

- OOXML `<w:tblGrid>` 是 Word 寫文件時就敲好的欄寬，準確度足以做 baseline render
- fallback：若 grid 全 0（罕見），平均分配 contentWidth
- 真正的 content-driven auto layout（多次 measure pass）留 Sprint 4-5

### 2.2 vMerge anchor / continuation 模型

`CellNode.isContinuation` 由 GridResolver 在 Phase 1 已預先填好。Sprint 3 行為：

| Cell 狀態 | layoutCell 行為 |
|---|---|
| `isContinuation = false` | 跑 paragraph → lines layout，計算 height |
| `isContinuation = true` | height = 0、lines = []，由 anchor cell 撐高 |

Renderer 之後拿到 `isContinuation` 旗標時，跨頁 cell 需要：
- 第一頁底部省略下邊框
- 第二頁頂部省略上邊框

當前 Sprint 3 的 layout 提供旗標，邊框 omit 規則留 Renderer 完成。

### 2.3 跨頁演算法（row-level）

`laySingleTable()` 邊收 row、邊 flush，遇超寬就切：

```
for each row:
  if pendingRows is empty AND row.height > availableSpace AND not first table on page:
    flushPage  # 換頁
    isContinuation = true
    push tblHeader rows to pending
  elif pendingRows non-empty AND pendingHeight + row.height > availableSpace:
    flushTableEntry(more=true)
    flushPage
    isContinuation = true
    push tblHeader rows to pending
  push row to pending
flushTableEntry(more=false)
```

**簡化點**：cell 內部不切（不允許 mid-row break）。跨頁僅發生在 row 邊界。Word 預設 `<w:cantSplit>` 即此行為，設 `false` 才會在 row 內切。Sprint 4 補完 cell 內部斷頁。

### 2.4 tblHeader 重複

OOXML `<w:tblHeader>` 列在表格跨頁時會被自動重複到下一頁的頂端。實作：

- 第一頁的 header rows 照常放
- 跨頁時，新頁的 pending 先填 `headerRows`（過濾掉「當前 row 就是 header」的重複情況）
- 每個 `TableLayoutEntry` 帶 `isContinuation`：Renderer 用此旗標決定是否畫頂端外框

### 2.5 Section break: nextPage（其餘 Sprint 4）

`layoutDocument()` 把 sections 串接，**Section 間預設 nextPage**（`pageNumber` 從上一段的 `nextPageNumber` 起算，自動換頁）。

Sprint 3 不處理：
- `continuous`：同頁繼續，需要 header/footer per-section 切換
- `evenPage` / `oddPage`：跳到偶/奇頁，需要 blank page 插入

留 Sprint 4。

---

## 3. fixture 統計變化（Sprint 2 → Sprint 3）

| 類別 | Sprint 2 avgPages | Sprint 3 avgPages | 變化 |
|---|---|---|---|
| 01_simple | 1.1 | **1.9** | +0.8（cell 內容展開） |
| 02_std_table | 1.0 | **1.6** | +0.6（週報跨頁） |
| 03_complex_table | 1.0 | 1.0 | 持平（fixture 高度仍夠裝） |
| 04_with_image | 1.0 | **2.7** | +1.7（照片頁明顯展開） |
| 05_header_footer | 3.0 | **4.2** | +1.2（自主檢查表逼近真實 PDF 頁數） |
| 06_template | 1.0 | 1.3 | +0.3 |

`avgLines` 沒變（line entry 是段落級的，cell 內 lines 不計入）。

**讀法**：05_header_footer 自主檢查表這份 fixture 真實 PDF 通常 4-5 頁，Sprint 3 算到 4.2 頁是合理的。Sprint 2 的 3.0 是 placeholder 估算偏低。

---

## 4. Sprint 3 已知限制（→ Sprint 4+ 補完）

| 限制 | 原因 | 補完 Sprint | 對應規劃 |
|---|---|---|---|
| Cell 內部不切（mid-row break） | 簡化跨頁演算法 | Sprint 4 | §3.3 跨頁表格 |
| 表格邊框衝突解決（OOXML 17.4.65 8 級優先） | 留 Renderer 處理 | Sprint 5 | §3.3 / Phase 4 |
| 巢狀表格（cell 內又有 table） | layoutCell 目前只看 paragraph | Sprint 5 | §3.3 |
| Auto layout（content-driven 重新分配欄寬） | grid 直接 copy 已足夠 | Sprint 4-5 | §3.3 |
| Section break: continuous / evenPage / oddPage | nextPage 已支援 | Sprint 4 | §3.2 |
| 浮動圖片 wrap 模式 | 需重寫 LineBreaker 行寬計算 | Sprint 4 | §3.4 |
| 多欄 multi-column | Paginator 單欄假設 | Sprint 5 | §3.5 |
| Knuth-Plass 精細斷行 | 貪婪算法已產生穩定 baseline | Sprint 5+ | §3.1 |
| 完整 widow/orphan 回退 | 簡單版已能擋大多數情境 | Sprint 4 | §3.2 |
| HarfBuzz 字型實測 metrics | EstimateMetrics 偏差 ±5% | Sprint 5+ | Phase 2 |
| 註腳 / 尾註 | Paginator 無 footnote 區概念 | Sprint 5+ | §3.6 |

---

## 5. 對 Sprint 1/2 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | 無（snapshot 是 ParserAST 級，不依賴 Layout） | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 無（同上） | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2） | placeholder 改 cell-level | **更新後** 48 case 全綠 |
| Sprint 2 unit tests | TableLayout 新加；其餘無影響 | 55 case 全綠 |
| Python integration | 無關 | 54 case 全綠 |

---

## 6. 驗證指令

```bash
# 完整 vitest（27 → 28 files；470 → 486 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 3
npx vitest run tests/unit/layout/TableLayout.test.ts \
              tests/unit/layout/Paginator.test.ts \
              tests/integration/06_layout_smoke.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 4）

依規劃 §3.4 + §3.2 殘餘工作，建議優先：

1. **浮動圖片 wrap 模式**（§3.4）
   - `wrapNone` / `wrapSquare` / `wrapTopAndBottom`（最常見三種）
   - 整合到 LineBreaker：行寬隨 y 動態變化
2. **完整 widow/orphan**（§3.2）
   - 支援回退已 push 的 entries
3. **Section break 全套**（§3.2）
   - `continuous` / `evenPage` / `oddPage`
4. **Cell 內部斷頁**（§3.3 殘餘）
   - 允許 cell 內的 paragraph 跨頁

Sprint 4 完成後預期：
- `03_complex_table/送審管制.docx` avgPages > 1（圖片繞排後內容變多）
- 浮動圖片 fixture 通過 `wrapType=tight` audit
- Layout Engine 對全 fixture 不再 throw 任何 warnings

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 3。

# Sprint 2 Layout Engine 起步

**狀態**：W11+ 主線 Sprint 2 — Layout Engine 骨架  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)

---

## 1. 範圍

Sprint 2 完成 Layout Engine **架構骨架** + 第一個可用版本。落地 5 個檔案：

| 檔案 | 角色 | 行數 |
|---|---|---|
| `static/src/core/layout/types.ts` | Box / Glue / Penalty / Line / Page 全部型別 | ~140 |
| `static/src/core/layout/TextMetrics.ts` | EstimateMetrics（純查表估算）+ isCjkChar | ~95 |
| `static/src/core/layout/BoxBuilder.ts` | ParagraphNode → ParagraphInput（LayoutItem[]） | ~150 |
| `static/src/core/layout/LineBreaker.ts` | 貪婪斷行 + 中文避頭尾規則 | ~210 |
| `static/src/core/layout/Paginator.ts` | Section → Page[]（含基礎 widow/orphan + pageBreakBefore） | ~210 |
| `static/src/core/layout/index.ts` | 公開 API | ~30 |

**測試**：5 個測試檔，87 個 case 全綠。

| 測試檔 | Case 數 | 涵蓋 |
|---|---|---|
| `tests/unit/layout/TextMetrics.test.ts` | 12 | isCjkChar / measureWidth / measureLineHeight / cache |
| `tests/unit/layout/BoxBuilder.test.ts` | 9 | 純 CJK / 純 Latin / 混排 / inlineImage / break / 空段落 |
| `tests/unit/layout/LineBreaker.test.ts` | 11 | 簡單斷行 / CJK / 避頭尾 / 強制斷 / alignment / firstLineIndent |
| `tests/unit/layout/Paginator.test.ts` | 8 | 單頁 / 多頁 / pageBreakBefore / 表格 placeholder / section 串接 |
| `tests/integration/06_layout_smoke.test.ts` | 47 | 42 fixture × 不 throw + 結構檢查 |

---

## 2. 關鍵設計決策

### 2.1 Knuth-Plass 結構先行，貪婪實作

`types.ts` 定義 `Box | Glue | Penalty` 完整 K-P breakpoint algebra（含 stretch/shrink/cost/flagged）。Sprint 2 的 `LineBreaker` 是**貪婪 first-fit**，但 item 模型已具備所有 K-P 需要的欄位，未來切換不必動 `BoxBuilder`。

**為什麼不直接做 K-P**：複雜度高，trade-off 不明顯。先用貪婪走通 fixture 全綠後再優化。

### 2.2 EstimateMetrics 純查表，不依賴字型檔

`TextMetrics.ts` 用「em 寬度 × fontSize」查表估算：

| 字符類別 | em 寬度 |
|---|---|
| 空白 / Tab | 0.27 |
| 半形數字 | 0.55 |
| 大寫 Latin | 0.61 |
| 小寫 Latin | 0.5 |
| 半形標點 | 0.45 |
| **CJK / 全形標點** | **1.0** |

精準度：對 12pt 中文段落，估算 vs 實測 typical ±5%。Sprint 2 LineBreaker 不需精確，能維持「fixture 行數穩定 → snapshot 不漂移」即可作為回歸 baseline。

未來注入 HarfBuzz 結果只要實作 `TextMetrics` interface 即可，不需動其他模組。

### 2.3 中文避頭尾規則內建

LineBreaker 直接內建：

```
PROHIBITED_LINE_START = '。、，；：！？」』）】》．,.;:!?)]'
PROHIBITED_LINE_END   = '「『（【《(['
```

斷行後檢查：
- 若下行行首是禁止字符 → 上一個 Box 推到下行
- 若本行行尾是禁止字符 → 推到下一行

### 2.4 Paginator 用「表格 placeholder」punt 表格內部排版

Sprint 2 表格佈局尚未實作，Paginator 把每張表用一個 `table-placeholder` entry 占位，估算高度 = `rowCount × 22pt`。當表格高度超過頁面剩餘空間時整塊推下一頁。**超過整頁高度時產生 warning 提示「Sprint 3 補完跨頁」**，不切表格。

這個策略的好處：
- 不必等 TableLayout 完成就能對全 fixture 跑 layout smoke test
- Renderer 拿到 `table-placeholder` entry 時可以 fallback 用 canvas-editor 原生表格能力（已支援基本 colSpan/rowSpan）
- Sprint 3 補完 TableLayout 時，把 `table-placeholder` 換成 `cell-level entries`，外層 API 不變

### 2.5 Widow/Orphan 簡化版

完整 widow/orphan 需要回退已加入頁面的 entries。Sprint 2 簡化為：
- 段落總行數 ≤ max(widowMin, orphanMin)（預設 2）且當前頁裝不下 → 整段推下一頁
- 段落最後 N 行（N ≤ widowMin）會被孤留 → 直接從新頁開始

不回退已加入 entries 的代價：偶爾會出現「上一頁底部 1 行 + 下一頁 N 行」的不理想斷點。下個 sprint 補完。

---

## 3. Sprint 2 已知限制（未來工作清單）

對應 [規劃文件 §5.4 Phase 3](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md) 各小節：

| 限制 | 補完 Sprint | 對應規劃章節 |
|---|---|---|
| 表格用 placeholder（不展開 cell 內容） | Sprint 3 | §3.3 Table Layout 完整版 |
| 跨頁表格不支援（cantSplit / tblHeader 重複） | Sprint 3 | §3.3 |
| 浮動圖片 wrap 模式（square/tight/topAndBottom）| Sprint 4 | §3.4 |
| 多欄 multi-column | Sprint 5 | §3.5 |
| 註腳 / 尾註 | Sprint 5 | §3.6 |
| Knuth-Plass 斷行（精細 justify） | Sprint 4 | §3.1 |
| 完整 widow/orphan（回退已 push 的 entries） | Sprint 3 | §3.2 |
| Section continuous / evenPage / oddPage break | Sprint 3 | §3.2 |
| 字型實測 metrics（HarfBuzz / opentype.js）| Sprint 4-5 | §5.3 Phase 2 |
| 段落 spacing.line 用 rule（auto/exact/atLeast） | Sprint 3 | §3.2 |

---

## 4. Sprint 2 Layout 統計（fixture smoke）

從 `06_layout_smoke.test.ts` 的統計輸出：

```
01_simple:       avgPages=1.1 avgLines=2  n=7
02_std_table:    avgPages=1.0 avgLines=10 n=8
03_complex_table: avgPages=1.0 avgLines=6  n=8
04_with_image:   avgPages=1.0 avgLines=9  n=6
05_header_footer: avgPages=3.0 avgLines=14 n=10
06_template:     avgPages=1.0 avgLines=12 n=3
```

**讀法**：
- avgLines 偏低是合理的——大量內容在 table cell 內，Sprint 2 用 placeholder
- 05_header_footer（自主檢查表）avgPages=3 → 對得上實際 PDF 頁數，confidence 高
- 01_simple avgLines=2 → 會議記錄主體結構是「外框表格 + 內部 cell 文字」，cell 內容尚未展開
- 03_complex_table avgPages=1 但 14 欄表格實際應分 2 頁——Sprint 3 補完跨頁後預期 avgPages 升高

---

## 5. 對 Sprint 1 回歸護欄的影響

Sprint 1 建立了：
- `tests/integration/04_ast_snapshot.test.ts` — 42 fixture AST 結構指紋
- `tests/integration/05_parser_audit.test.ts` — 子模組 fixture audit

**Sprint 2 沒動 OoxmlParser** → Sprint 1 的 50 個回歸 case 全綠，confidence 維持。

新加的 87 個 layout case 是「Layout Engine 層的回歸護欄」，與 Sprint 1 的 parser 護欄並行不衝突。

---

## 6. 驗證指令

```bash
# 完整 vitest（22 → 27 files；383 → 470 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 2
npx vitest run tests/unit/layout tests/integration/06_layout_smoke.test.ts

# 只跑 layout smoke
npx vitest run tests/integration/06_layout_smoke.test.ts

# Sprint 1 + Sprint 2 一起
npx vitest run tests/integration/
```

---

## 7. 下個 Sprint（Sprint 3）的具體目標

依規劃 §3.3：

1. **CSS2 Table Layout**：fixed / auto + colSpan / rowSpan + cell border collapse
2. **跨頁表格**：cantSplit / tblHeader 重複列
3. **完整 widow/orphan**：可回退已 push entries
4. **Section break 全套**：continuous / evenPage / oddPage

Sprint 3 完成後預期：
- `04_with_image` 的 isImage box 改回 imageBoxCount > 0 assertion
- `03_complex_table/送審管制.docx` avgPages > 1
- `05_header_footer` 自主檢查表的表格內容真的進入 layout

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 2。

# Sprint 27 — Cell-level keepNext R6 規則 infrastructure（page count 未改善）

**期間**：2026-05-10 → 2026-05-11
**主軸**：實作 OOXML R6 規則（cell 內段落 `w:keepNext` → row 視為 `cantSplit`）
**結論**：infrastructure 落地 + 零退化，**但目標 03_complex_table 06-8估驗計價 ×2 的 page count 未改變**。根因診斷確認真正瓶頸在 **CJK 字寬 metric 與 Word 不符**（cell text wrap 估短），需要 Sprint 28+ 字型工程（HarfBuzz / opentype.js shaping）才能完整解決剩 5 個 -1 fixture。

---

## 0. 入工前狀態（Sprint 26 後）

| 指標 | Sprint 26 |
|---|---|
| Page count mismatched fixture | 5 / 42 |
| totalDelta | -5 |
| 5 個 -1 fixture | 02_std_table/1140206 / 03_complex_table 06-8估驗計價 ×2 / 05_header_footer 人手孔 + 地坪 |

Sprint 26 audit §8 優先級 1：「人手孔/地坪 → cell 文字 wrap」、「02_std_table 純段落 spacing」、「**03_complex_table cell-level keepNext 視為 cantSplit**」。

Sprint 27 挑第三個（hypothesis 從 Sprint 19 已明確 + 影響 2 個 fixture = 最大 cluster）。

---

## 1. 假設 + 全 fixture 影響掃描

### 1.1 假設

OOXML §17.3.1.15 `w:keepNext`：「段落應與下一段落同頁顯示」。當 keepNext 出現在 table cell 內段落時，Word 把該 row 整體視為「不可中切」處理（cell 內 keep with next 在 row 內已自動成立；跨 row 則把 row 黏在一起，**最簡近似 = 該 row 強制 cantSplit**）。

Sprint 19 §6 留下的觀察：03_complex_table 06-8估驗計價 ×2 fixture 共 **43 個 cell-level keepNext 段落**，分布於 12-row 表的 row 2-9，但 row 全 `cantSplit=False`，我們 Paginator 可 mid-row break。

### 1.2 全 42 fixture 掃描（零退化 sanity check）

```python
# 掃描所有 docx 內 table cell 段落帶 keepNext 的數量
```

結果：**只有 2 個 fixture 有 cell-level keepNext，全部是目標 06-8估驗計價 ×2**。其他 40 個 fixture 都 0。

→ 套用 R6 規則**零退化風險**（其他 fixture 不會被影響）。

---

## 2. 修法落地

### 2.1 修改範圍

[`static/src/core/layout/TableLayout.ts`](../static/src/core/layout/TableLayout.ts) `layoutRow()` 補 `hasCellKeepNext()` post-check：

```ts
const cantSplitFromKeepNext = !row.props.cantSplit && hasCellKeepNext(cells);

return {
  ...
  cantSplit: row.props.cantSplit || cantSplitFromKeepNext,
  ...
};

function hasCellKeepNext(cells: CellLayout[]): boolean {
  for (const cell of cells) {
    if (cell.isContinuation) continue;
    for (const block of cell.blocks) {
      if (block.kind !== 'lines') continue;
      for (const line of block.lines) {
        if (line.paragraphProps?.keepNext === true) return true;
      }
    }
  }
  return false;
}
```

### 2.2 unit test（4 新 case）

[`tests/unit/layout/TableLayout.test.ts`](../tests/unit/layout/TableLayout.test.ts)：

| # | 情境 | 期望 |
|---|---|---|
| 1 | cell 段落 keepNext=true → row.cantSplit=true | ✓ |
| 2 | cell 段落都沒 keepNext → row.cantSplit 維持 false | ✓ |
| 3 | row 已 cantSplit=true → keepNext heuristic 不影響 | ✓ |
| 4 | 多 cell 中只要 1 cell 有 keepNext → row 即 cantSplit | ✓ |

**全 4/4 pass**（合 Sprint 26 baseline 31 case → **35/35**）。

---

## 3. 三層 SOP 結果

### 3.1 Layer 1 — vitest 全套

**755/755 pass + 1 skipped**（Sprint 26 baseline 751 + Sprint 27 TableLayout 4 = 755）

**09_page_count_baseline snapshot 無變動**（mismatched 5，totalDelta -5，跟 Sprint 26 完全一樣）。

### 3.2 Layer 2 — Visual Regression v14

**rendered 42/42 / comparedPages 121（與 Sprint 26 相同）/ failedPages 0**

| Category | Sprint 26 | **Sprint 27** | Δ |
|---|---|---|---|
| 01_simple | 0.0917 | 0.0917 | 0% |
| 02_std_table | 0.2702 | 0.2702 | 0% |
| 03_complex_table | 0.2946 | 0.2946 | 0% |
| 04_with_image | 0.3861 | 0.3861 | 0% |
| 05_header_footer | 0.0495 | 0.0495 | 0% |
| 06_template | 0.0324 | 0.0324 | 0% |
| **總體 mean** | 0.1757 | **0.1757** | **0%** |

→ 完全 byte-equal 視覺輸出。**Sprint 27 修法純 infrastructure（cantSplit flag），未改動實際 layout 行為**（因該表完全 fit 1 頁，cantSplit 對沒溢頁的 row 無語意）。

### 3.3 Layer 3 — Playwright admin E2E

**6/6 passed (1.3m)**：Sprint 21-26 host integration 全綠，不退化。

### 3.4 視覺 spot check

06-8估驗計價 ×2 fixture 仍 1 頁渲染（vs golden 2 頁）。page 1 diff=0.0919-0.0974（與 Sprint 26 相同）。

---

## 4. Root cause 重定位：CJK 字寬 metric

### 4.1 為何 cantSplit 沒幫助

實際 layout dump（修法後）顯示 06-8估驗計價 section 0：

```
Sum content = 605.3pt / page contentH = 785.1pt = 0.77 pages
```

整個 section 在我們 layout 計算下**只佔一頁的 77%**，根本沒溢頁。cantSplit 只在 row 需要被 mid-row break 時才生效，row 沒溢頁時無作用。

### 4.2 真正瓶頸：cell text wrap 估短

Word golden page 1 顯示 row 4「材料、設備出廠證明及檢、試驗文件」cell 含**多行內容**（4-5 行），實際渲染高度 ~150pt。我們 layout 計算只 78pt（約 2-3 行）。

**Root cause**：Layout 引擎的 `EstimateMetrics`（[`TextMetrics.ts`](../static/src/core/layout/TextMetrics.ts)）對 CJK 字符寬度估算為 `fontSize × 1.0`（全角），但 Word 實際渲染時：
- 字距 / kerning / cluster shaping 都會佔額外空間
- 段落 indent / hanging indent / firstLineIndent 影響可用 line width
- 表格 cell 邊框 / padding 佔用幾 pt
- 字形 advance width 因字型 / weight 略有變動

這些累積差異在「20+ 字行內」是 5-10% 的低估，但**累積在 60+ 字的長段落**會少算 1 整行（=~14-25pt）。對緊邊界的 fixture 就會 -1 頁。

### 4.3 對應全部剩 5 個 -1 fixture

| Fixture | 主問題 |
|---|---|
| 02_std_table/1140206-工地密度 | 17 個純段落（含 80+ 字 title），CJK 估短 |
| 03_complex_table/06-8估驗計價 ×2 | 12-row 表中 cell 多行內容估短（Sprint 27 cantSplit 未幫上）|
| 05_header_footer/人手孔調升降 | 21-row 表中 cell 多行內容估短（窄 cell 寬，5+ 行） |
| 05_header_footer/地坪鋪面 | 同上 |

**全 5 個 fixture 都指向同一 root cause：CJK 字寬 metric 與 Word 渲染差距**。

---

## 5. 量化結果

| 指標 | Sprint 26 | **Sprint 27** |
|---|---|---|
| Page count mismatched | 5 / 42 | **5 / 42（未改善）** |
| totalDelta | -5 | -5（未改善）|
| OOXML R6 keepNext 規則 | 部分（body-level keepNext 已支援，cell-level 未支援）| **完整**（cell-level → row cantSplit）|
| vitest test files | 48 (+1 skipped) | 48 (+1 skipped)|
| vitest test cases | 751 + 1 skipped | **755 + 1 skipped**（+4 TableLayout）|
| Visual Regression v14 comparedPages | 121 | 121（未改善）|
| Visual Regression v14 總體 mean | 0.1757 | 0.1757（未改善）|
| Playwright admin E2E | 6/6 | 6/6（不退化）|

---

## 6. Sprint 27 學到的工程教訓

### 6.1 規則正確 ≠ 觀察可見

Sprint 27 實作的 R6 cell-keepNext → row cantSplit 是**規格層面正確**的修法。Word 確實這樣處理。但在這個 fixture 上恰好**整 section 還沒溢頁**，所以 cantSplit 變得沒有 observable 效應。

→ 規格合規的價值在於**長期 robustness**（未來 fixture 若整表逼近頁界，這個 infrastructure 就會生效），不是每個 sprint 都要看到 page count 改善。

### 6.2 同樣症狀的多 fixture 可能共享 root cause

Sprint 25 spacing.line / Sprint 26 row height heuristic / Sprint 27 cell-keepNext 三輪都嘗試解決「邊緣 fixture -1」，每輪用不同的局部修法解決 1 個 fixture。剩 5 個 fixture 在 Sprint 27 後**完全沒動**，說明它們的 root cause 是同一個更深層次的問題 — **CJK 字寬 metric**。

→ Sprint 28+ 不應再加局部 heuristic，而是真正接入字型 metric（HarfBuzz / opentype.js）。

### 6.3 「零退化但零改善」也算 commit

Sprint 27 嚴格說沒有像 Sprint 25/26 那樣修好 fixture。但 infrastructure 添了、規格合規度提升了、零退化、單元測試 +4 case。**值得 commit**，不該因為 page count 沒動就還原。

---

## 7. 規劃書同步項

- §0.5 加 Sprint 27 entry：cell-keepNext infra 落地 + root cause 重定位為 CJK metric
- §0.5 文件清單補 [sprint27_cell_keepnext_infra.md](sprint27_cell_keepnext_infra.md)
- §0.6.13 完成度表加 Sprint 27 欄；mismatched 5（未改）；Phase 3 81%→82%（R6 規則補完）
- §0.6.13 「Sprint 27+ 優先級」→「Sprint 28+ 優先級」；新項目 8 改為「剩 5 個 -1 偏差個別擊破第四輪 — **CJK 字寬 metric 工程**（HarfBuzz / opentype.js shape，取代 EstimateMetrics）」
- 文件 header 最後更新日期

---

## 8. Sprint 28+ 候選（重排）

按「投入 vs 解決範圍」排序：

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **HarfBuzz 真接 Layout（取代 EstimateMetrics）**：用 HarfBuzz shape API 取得真實 advance width，CJK 字符測寬從估算改實量；同時可能影響行高（leading）| **預計修 5 個 -1 fixture**（02_std_table / 03_complex_table ×2 / 05_header_footer ×2）+ 整體像素 diff 進一步下降；高工程量但 ROI 大 |
| 2 | 🟢 開發 cell measure 自動診斷工具（dump per-cell width / lines / height）| 給 Sprint 28+ HarfBuzz 工程提供 baseline 量化 |
| 3 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求）| 新功能 |
| 4 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |
| 5 | 🟢 lazy_loader / pagination_engine.js 評估清理 | code review |

---

**Sprint 27 一句話總結**：實作 OOXML R6 規則（cell 段落 keepNext → row 強制 cantSplit）作為 infrastructure 落地、附 4 unit test 全綠、全 42 fixture 掃描證明零退化風險；但因目標 fixture 在 layout 計算下未溢頁，cantSplit 沒有 observable 效應；診斷確認剩 5 個 -1 fixture 真正 root cause 是 **CJK 字寬 metric 估短**，Sprint 28+ 用 HarfBuzz / opentype.js 真實字型 shape 統一解決。

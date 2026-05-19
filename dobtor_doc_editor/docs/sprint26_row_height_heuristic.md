# Sprint 26 — 7 個 -1 偏差 fixture 個別擊破第二輪：auto row height 啟發式

**期間**：2026-05-10
**主軸**：對 OOXML `<w:trHeight w:val="X"/>` 不帶 `w:hRule`（auto 預設）的 row 套用啟發式 val-as-min
**結論**：意外修好 01_simple/03.1120210（Sprint 19 留下的 cell-internal break case）；mismatched 從 6 收到 **5（-17%）**，零退化；Visual Regression v14 comparedPages 120→**121**、總體 mean 0.1766→**0.1757（-0.5%）**、01_simple per-cat 0.0933→**0.0917（-1.7%）**。原訂目標（人手孔調升降 / 地坪鋪面）**未修復**，留 Sprint 27+ 換角度（cell 文字 wrap / 字型 metric）。

---

## 0. 入工前狀態（Sprint 25 後）

| 指標 | Sprint 25 |
|---|---|
| Page count mismatched fixture | 6 / 42 |
| totalDelta | -6 |
| 6 個 -1 fixture | 01_simple ×1（03.1120210）/ 02_std_table ×1 / 03_complex_table ×2 / 05_header_footer ×2（人手孔, 地坪）|

Sprint 25 audit §7 優先級 1：「人手孔調升降 / 地坪鋪面 → cell 內段落行高 / cell padding 計算」。

---

## 1. Hypothesis A（被否決，已還原）

### 1.1 假設

OOXML `<w:trHeight w:val="X"/>` 不帶 `w:hRule` 時 ParagraphParser 解成 `heightRule='auto'`。
規格說 auto 純看 content（val 純粹 cached value），但 [TableLayout.ts:178-182](../static/src/core/layout/TableLayout.ts) 的舊代碼：

```ts
if (row.props.heightRule === 'atLeast' && row.props.height) {
  rowHeight = Math.max(rowHeight, row.props.height);
} else if (row.props.heightRule === 'exact' && row.props.height) {
  rowHeight = row.props.height;
}
```

**對 auto 完全忽略 val**。Word 對某些 fixture（如 04/05 自主檢查表）卻把 val 當下限渲染，造成 -1 偏差。

### 1.2 修法 A

無條件對 `auto || atLeast` 套 `Math.max(natural, val)`。

### 1.3 結果（被否決）

| 影響 | Δ |
|---|---|
| 修好 fixture | 3（人手孔調升降 / 地坪鋪面 / 植筋）|
| 退化 fixture | 11（01_simple ×6 監造會議記錄 / 03_complex_table ×5 全套管基樁混凝土查驗）|
| **mismatched 6 → 14** | -8 net 退化 |
| **totalDelta -6 → +8** | 反向過度分頁 |

→ **Hypothesis A 否決 / 還原**。

### 1.4 為何 A 不可行

對比兩類 fixture 的 val/natural ratio：

| Fixture 類型 | 範例 | val | natural | ratio | 期望行為 |
|---|---|---|---|---|---|
| 自主檢查表 sparse form row | 人手孔 row 7 | 57.2pt | 14.4pt | **3.97** | val 當下限 |
| 監造會議記錄 row | 03.1120815 row 1 | 16.65pt | 14.4pt | **1.16** | val 不當下限（content 為主）|
| 1121229-全套管 row | row 0 | 266.8pt | 249.5pt | **1.07** | val 不當下限 |

→ Word 對這兩類行為**不同**，純 val-as-min 無法兼顧。

---

## 2. Hypothesis B（採用，含啟發式 ratio>3）

### 2.1 修法 B

[TableLayout.ts](../static/src/core/layout/TableLayout.ts) `layoutRow()` 加 ratio 判斷：

```ts
if (row.props.heightRule === 'exact' && row.props.height) {
  rowHeight = row.props.height;
} else if (row.props.heightRule === 'atLeast' && row.props.height) {
  rowHeight = Math.max(rowHeight, row.props.height);
} else if (row.props.height && rowHeight > 0 && row.props.height > rowHeight * 3) {
  // auto + sparse form row：套 val-as-min（對齊 Word 實際渲染）
  rowHeight = row.props.height;
}
```

**啟發式 ratio > 3**：val 必須**顯著** > natural（至少 3 倍）才視為 sparse form row 套 val-as-min。

### 2.2 設計依據

- `ratio > 3`：val 是「設計指定固定高」（form 設計，user 在裡面填單）— Word 把 val 當下限
- `ratio < 3`：val 是「Word autosave 快取」（接近 content 自然高）— Word 純看 content
- 兩個語意在 docx 內無正式區分 fag，3 倍是 empirical 觀察（Sprint 26 試驗 fixture 後挑的閾值）

### 2.3 自動化驗證（unit test）

[`tests/unit/layout/TableLayout.test.ts`](../tests/unit/layout/TableLayout.test.ts) 新增 5 case：

| # | 情境 | 期望 |
|---|---|---|
| 1 | auto + ratio>3（val 60 / 自然 14.4，4.17 倍）| height = 60（套 val-as-min）|
| 2 | auto + ratio<3（val 25 / 自然 14.4，1.74 倍）| height < 20（不套，保護 1121229-全套管 / 監造會議記錄）|
| 3 | auto + content > val | height > val（natural 主導）|
| 4 | undefined heightRule + ratio>3 | 同 case 1（解析時 'auto'）|
| 5 | 自主檢查表 row 復現（val 57.2 / 自然 14.4）| 57.2 inflate |
| 6 | 1121229-全套管 row 復現（多段落自然接近 val）| 不 inflate |

**全 6/6 pass**（合既有 25 case → 31/31）。

---

## 3. 結果

### 3.1 Layer 1 — vitest 全套 regression

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run -u --pool=forks --poolOptions.forks.singleFork=true
```

**751/751 pass + 1 skipped**（Sprint 25 baseline 745 + Sprint 26 TableLayout 6 = 751）。
3 個 snapshot updated（09_page_count_baseline / 08_render_ops_trace）。

### 3.2 Layer 2 — Visual Regression v14

```bash
npx rollup -c rollup.visual_regression.config.js
node scripts/visual_regression_v14.mjs --max-diff 1.0
```

**rendered 42/42 / comparedPages 121 / failedPages 0**（Sprint 25: 120 → +1 from 03.1120210 修好新增第 3 頁）

| Category | Sprint 25 | **Sprint 26** | Δ |
|---|---|---|---|
| **01_simple** | 0.0933 | **0.0917** | **-1.7%** |
| 02_std_table | 0.2702 | 0.2702 | 0% |
| 03_complex_table | 0.2946 | 0.2946 | 0% |
| 04_with_image | 0.3861 | 0.3861 | 0% |
| 05_header_footer | 0.0494 | 0.0495 | +0.2%（持平）|
| 06_template | 0.0322 | 0.0324 | +0.6%（持平）|
| **總體** | **0.1766** | **0.1757** | **-0.5%** |

### 3.3 Layer 3 — 視覺 spot check

01_simple/03.1120210-監造會議記錄-1120801（Sprint 26 解鎖的第 3 頁）：

- Ours page 3：[`tests/fixtures/.visual_regression_tmp/v14/03.1120210-監造會議記錄-1120801-3.rendered.png`](../tests/fixtures/.visual_regression_tmp/v14/) — 顯示 1-19 ~ 1-22 共 4 個工項表格 row
- Golden page 3：[`tests/fixtures/01_simple/golden/03.1120210-監造會議記錄-1120801-3.png`](../tests/fixtures/01_simple/golden/) — 顯示 1-15 ~ 1-22 共 8 row（含分頁交接）
- diffRatio = **0.0674**（121 頁中第 5 低）

→ 這頁的存在本身就是 Sprint 26 修法成果；頁數對 + 內容類型對（都是工項列表續頁）。

### 3.4 Playwright admin E2E

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright && npx playwright test --project=admin
```

**6/6 passed (1.2m)**：Sprint 21-25 的 5 個 host model 按鈕 + end-to-end 點擊全綠。Sprint 26 純 layout 改動，未碰 host integration / view，不退化符合預期。

---

## 4. 為何沒修到原訂目標（人手孔/地坪）

實裝 dump 後發現 row 7-16 的 cell 自然高 **已經 > val**：

| Row | val (pt) | layoutHeight (pt) | natural |
|---|---|---|---|
| 7 | 57.2 | 72.0 | natural |
| 8-10 | 57.2 | **100.8** | **natural** |
| 11-15 | 55.3 | 72-86.4 | natural |
| 16 | 67.0 | 86.4 | natural |

Cell 6 欄寬窄（每 cell ~1.67in），`+++INS inspection.stages[2].itemX.result+++` 模板字串在我們 LineBreaker 算下來 wrap 到 5+ 行 = 72-100pt natural，**遠 > val**，ratio < 1，啟發式 B 完全不觸發 inflate。

→ 這兩個 fixture 的 -1 偏差**root cause 不在 row val**，而在更深層的 layout 行為差異：
- 我們的字型 metric / 文字 wrap 算法和 Word 略有差異
- 表格 cell padding / cell border / 段落 spacing 在 cell 內可能還有未補完規則
- section overhead（3 個 nextPage section）的處理可能也有差距

留 **Sprint 27+** 換角度繼續。

---

## 5. 量化結果

| 指標 | Sprint 25 | **Sprint 26** |
|---|---|---|
| Page count mismatched | 6/42 | **5/42（-17%）** |
| totalDelta | -6 | **-5** |
| Layout 引擎 OOXML row height 對齊度 | exact + atLeast 完整支援；auto 完全忽略 val | **exact + atLeast 完整 + auto 啟發式 val-as-min（ratio>3）** |
| vitest test files | 48 (+1 skipped) | 48 (+1 skipped) |
| vitest test cases | 745 + 1 skipped | **751 + 1 skipped**（+6 TableLayout）|
| Visual Regression v14 comparedPages | 120 | **121** |
| Visual Regression v14 01_simple | 0.0933 | **0.0917（-1.7%）** |
| Visual Regression v14 總體 mean | 0.1766 | **0.1757（-0.5%）** |
| Playwright admin E2E | 6/6 | 6/6（不退化）|

---

## 6. 對 Sprint 1-25 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts` | 無 | 42 case 全綠 |
| `06_layout_smoke.test.ts` | 無 | 48 case 全綠 |
| `07_render_smoke.test.ts` | 無 | 44 case 全綠 |
| `08_render_ops_trace.test.ts`（fingerprint）| 部分 textHash 變（行 y 位移）| 2 case 全綠（snapshot updated）|
| `09_page_count_baseline.test.ts`（Sprint 16）| **mismatched 6→5；01_simple/03.1120210 改善** | 2 case 全綠（snapshot updated）|
| `TableLayout.test.ts` | **+6 新 case** | **31 case 全綠** |
| `Paginator.test.ts` | 無 | 22 case 全綠 |
| `LineBreaker.spacingLine.test.ts`（Sprint 25）| 無 | 10 case 全綠 |
| Visual regression v14 | 121 pages（+1）/ 0 fail | rendered 42/42 |
| Python integration | 無 | 105 case 全綠 |
| Playwright admin E2E | 無 | 6/6 全綠 |

---

## 7. 規劃書同步項

- §0.5 加 Sprint 26 entry：Hypothesis A 否決過程 + Hypothesis B 啟發式 + 01_simple/03.1120210 意外修好
- §0.5 結論段：「Sprint 25 起聚焦…」改為「Sprint 26 完成第二輪 / Sprint 27+ 換角度繼續剩 5 個」
- §0.5 文件清單補 [sprint26_row_height_heuristic.md](sprint26_row_height_heuristic.md)
- §0.6.13 完成度表加 Sprint 26 欄；mismatched 6→5；Phase 3 80%→81%
- §0.6.13 「Sprint 26+ 優先級」→「Sprint 27+ 優先級」；新項目 7 改為 「剩 5 個 -1 偏差個別擊破第三輪（人手孔/地坪 → cell 文字 wrap / 字型 metric；02_std_table 純段落；03_complex_table cell-level keepNext）」
- 文件 header 最後更新日期

---

## 8. Sprint 27+ 候選（重排）

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **剩 5 個 -1 偏差個別擊破第三輪**：1) 人手孔/地坪 cell 文字 wrap / 字型 metric 偏差；2) 02_std_table 純段落 spacing 對齊；3) 03_complex_table ×2 cell-level keepNext 視為 cantSplit | mismatched 5→0（**主軸達成**）|
| 2 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求） | 新功能 |
| 3 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |
| 4 | 🟢 lazy_loader / pagination_engine.js 評估清理 | code review |
| 5 | 🟢 HarfBuzz 真接 Layout（CJK 字距） | Layout + visual |

---

## 9. 學到的工程教訓

### 9.1 啟發式優於規格嚴格

Word 的實際行為與 ECMA-376 嚴格規格有出入（auto 是典型）。我們的 goldens 來自 Word 渲染，所以**啟發式對齊 Word 行為 > 嚴格遵循規格**。

### 9.2 「過度修正」是隱性回歸

Hypothesis A 修了 3 但退化 11，net 更糟。Sprint 26 的價值不在於修了多少，而在於**沒退化**。每個改動先看 snapshot diff 全貌再 commit。

### 9.3 ratio threshold 是 empirical 工具

3.0 是觀察 fixture 後挑的，不是從規格推導。日後若有反例可調整（甚至改成 cantSplit + ratio 雙條件）。

---

**Sprint 26 一句話總結**：對 OOXML `<w:trHeight>` auto 規則加 `val/natural > 3` 的啟發式 val-as-min，意外修好 01_simple/03.1120210 一個 fixture（mismatched 6→5、totalDelta -6→-5、零退化）；Visual Regression v14 121 pages / 01_simple per-cat -1.7%；原訂目標人手孔/地坪未修但證明了 root cause 不在 row val（在 cell 文字 wrap），留 Sprint 27+ 換角度。

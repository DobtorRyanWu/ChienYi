# Sprint 30 — Visual Regression DPI 對齊（96 → 150）

**期間**：2026-05-11
**主軸**：Sprint 29 page count 對齊 100% 達成後，轉攻像素級 visual diff 收斂；發現 Visual Regression 比對長期 DPI 不匹配是最大失準源
**結論**：把 visual regression pipeline 從 **96 DPI** 改成 **150 DPI** 對齊 golden 解析度，**單一改動**讓 Visual Regression v14 總體 mean 從 **0.1705 → 0.1386（-18.7%）**，6 個 category 全部改善（02_std_table -51.5% / 03_complex_table -33.6% / 06_template -31.2% / 05_header_footer -24.1% / 01_simple -23.7% / 04_with_image -1.9%），零退化 + zero failedPages、vitest 767/767 + 1 skipped 不變。

---

## 0. 入工前狀態（Sprint 29 後）

| 指標 | Sprint 29 |
|---|---|
| Page count mismatched | 0 / 42（達成 100% 對齊）|
| Visual Regression v14 總體 mean | 0.1705 |
| 04_with_image | 0.3805 |
| 03_complex_table | 0.2500 |
| 02_std_table | 0.2560 |
| comparedPages | 126 |
| failedPages | 0 |

Sprint 29 留下主軸：「**像素級 visual diff 收斂**：04_with_image 0.388 / 03_complex_table 0.250 / 02_std_table 0.256 是主要 diff 來源；目標總體 mean 0.1705 → 0.10」。

---

## 1. 根本原因：DPI 不匹配 + pixelmatch crop 邏輯

### 1.1 偵測過程

從 v14 report 撈 top 20 worst pages：

```
diff=0.6401  page=2  02_std_table/1120928 週報.docx
diff=0.6302  page=2  02_std_table/1121020 週報.docx
diff=0.6257  page=2  02_std_table/1121027 週報.docx
diff=0.6191  page=2  02_std_table/1121006 週報.docx
diff=0.6188  page=2  02_std_table/1121013 週報.docx
...
```

**5 個 02_std_table 週報 page 2 包辦前 5 名 worst**，diff 0.62-0.64。看 diff PNG：4 個 photo cell 整片紅，title 條紅 + 黃文字浮上。一眼看像「圖片完全沒渲染」。

### 1.2 比對 PNG 維度（決定性線索）

```bash
$ file tests/fixtures/02_std_table/golden/1120928-*-2.png \
       tests/fixtures/.visual_regression_tmp/v14/1120928-*-2.rendered.png
# golden:    PNG image data, 1241 x 1754
# ours:      PNG image data,  794 x 1123
```

**Golden 是 1241×1754 px = A4 @ 150 DPI**（1241/595.3pt × 72 ≈ 150）
**我們是 794×1123 px = A4 @ 96 DPI**

[scripts/visual_regression_v14.mjs](../scripts/visual_regression_v14.mjs) 用 `pixelmatch` 比對前先 `cropOrPad` 到雙方 min 尺寸 `(794, 1123)`：
- Golden（1241×1754）被 crop 成 **左上 794×1123**（約 64×64% 區域）
- Ours（794×1123）整張

所以實際比對是：
- 我們完整 A4 內容（含全部 4 張照片）
- vs Golden 左上 64% 內容（只含 title + 1 張半照片，其他被 crop 掉）

**內容完全錯位**，整個 photo cell 變紅。

### 1.3 為何只看到一部分 fixture 影響大

| Fixture 類型 | 影響 | 原因 |
|---|---|---|
| 02_std_table 週報 page 2 | 0.62-0.64 | photo 在 page 2 中下方，被 crop 掉 |
| 04_with_image | 0.38-0.44 | photo 滿頁，crop 部分失準累積 |
| 1140206 取樣紀錄 page 2 | 0.027 | 只有單行空白段落內容，crop 沒影響 |
| 05_header_footer | 0.047 | header/footer 在 cropped 區外但內容稀疏 |

**內容越擠近頁面下半 / 右半的 fixture，DPI 不匹配傷害越大**。

### 1.4 為何長期沒人發現

- Sprint 14 建 visual regression 時 default DPI = 96，註解「對齊 canvas-editor harness 96dpi」
- Golden PNG 應該是 Word/PDF export 在 150 DPI 產出（標準辦公列印解析度）
- 兩條 pipeline 各自設定，沒人 cross-check 過 PNG 維度
- 報告聚焦 diff 比例變化（每 sprint 看相對改善），絕對值 0.17 看起來「合理」，沒人去想「為何 04_with_image 是 0.38」

---

## 2. 修法落地

### 2.1 改動範圍

[`scripts/visual_regression_v14.mjs:202`](../scripts/visual_regression_v14.mjs)：

```diff
- const r = window.__bootDobtorPipeline(b64, { dpi: 96 });
+ const r = window.__bootDobtorPipeline(b64, { dpi: 150 });
```

[`tools/visual_regression_pipeline.entry.ts`](../tools/visual_regression_pipeline.entry.ts)：
- `DEFAULT_DPI = 96` → `DEFAULT_DPI = 150`
- 註解修正：「對齊 canvas-editor harness 96dpi」→「對齊 goldens 1241×1754 = A4 @ 150 DPI」

### 2.2 Rebuild bundle

```bash
npx rollup -c rollup.visual_regression.config.js
```

新 `tools/dist/visual_regression_pipeline.iife.js` 約 22 秒重建（同 bundle size，僅 default 值改）。

### 2.3 為何不改 golden、只改 ours

- 改 golden 須重 export 42 份 docx（Word 操作 + 手動）→ 工程量大 + 失去與 Word 真實渲染的 baseline
- 改 ours 只動 2 行設定 → 立即見效 + 維持 goldens 為 Word ground truth

---

## 3. 三層 SOP 結果

### 3.1 Layer 1 — vitest 全套

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run
```

**767/767 + 1 skipped**（與 Sprint 29 完全相同，零變動 — DPI 純影響 visual regression pipeline）

### 3.2 Layer 2 — Visual Regression v14

```bash
node scripts/visual_regression_v14.mjs --max-diff 1.0
```

**rendered 42/42 / comparedPages 126 / failedPages 0**

| Category | Sprint 29 | **Sprint 30** | Δ |
|---|---|---|---|
| **02_std_table** | 0.2560 | **0.1241** | **-51.5%** |
| **03_complex_table** | 0.2500 | **0.1661** | **-33.6%** |
| **06_template** | 0.0325 | **0.0224** | **-31.2%** |
| **05_header_footer** | 0.0473 | **0.0359** | **-24.1%** |
| **01_simple** | 0.0917 | **0.0700** | **-23.7%** |
| 04_with_image | 0.3880 | 0.3805 | -1.9% |
| **總體 mean** | 0.1705 | **0.1386** | **-18.7%** |

**所有 category 全改善**。04_with_image 改善小因 photo 滿頁原本就 dominant，需後續 sprint 個案處理。

### 3.3 Layer 3 — 視覺 spot check

新 render 對比舊 render（1120928 週報 page 2）：

| | 舊（96 DPI 794×1123）| **新（150 DPI 1240×1754）**|
|---|---|---|
| 照片 cell | 4 張 photo 正確置入 2×2 | 4 張 photo 正確置入 2×2 |
| 內容區域使用率 | 約 65% 頁面（壓在左上）| **100% 頁面（與 golden 對齊）** |
| 對應 golden crop | golden 左上 64%（內容錯位）| **golden 全頁（正確比對）** |

肉眼確認新 render 與 golden 結構一致，剩餘 diff 為真實 layout 細節（caption 位置、photo 比例等）。

### 3.4 為何不跑 Playwright

DPI 是純 visual regression pipeline 參數，**不影響任何 Python / Odoo / 模組行為**。Sprint 29 的 Playwright 結果（12 pass / 6 unrelated fail）不會因 DPI 變動。

---

## 4. Sprint 30 後 top diff sources

```
diff=0.4112  page=1  04_with_image/6.環清表安全衛生抽查照片(112.9.25.-9.29)
diff=0.4086  page=3  04_with_image/06.環清表安全衛生抽查照片(112.10.9.-10.13)
diff=0.4048  page=3  04_with_image/6.環清表安全衛生抽查照片(112.9.25.-9.29)
...全部前 10 worst page 都在 04_with_image
```

**04_with_image 28 pages × 0.38 = ~10.6 diff units 包辦剩 48% 總和**。Sprint 31+ 主軸應該是 04_with_image fixture 個案處理：
- Photo cell 內 image alignment（我們可能不 center、不 fit）
- Caption text 位置 / size
- Photo aspect ratio handling
- table border / cell spacing

---

## 5. 量化結果

| 指標 | Sprint 29 | **Sprint 30** |
|---|---|---|
| Page count mismatched | 0/42（不變）| 0/42 |
| Visual Regression v14 comparedPages | 126 | 126 |
| Visual Regression v14 failedPages | 0 | 0 |
| **Visual Regression v14 總體 mean** | **0.1705** | **0.1386（-18.7%）** |
| 02_std_table per-cat | 0.2560 | **0.1241（-51.5%）** |
| 03_complex_table per-cat | 0.2500 | **0.1661（-33.6%）** |
| 06_template per-cat | 0.0325 | **0.0224（-31.2%）** |
| 05_header_footer per-cat | 0.0473 | **0.0359（-24.1%）** |
| 01_simple per-cat | 0.0917 | **0.0700（-23.7%）** |
| 04_with_image per-cat | 0.3880 | 0.3805（-1.9%）|
| vitest test files / cases | 49 / 767+1skip | 49 / 767+1skip（不變）|
| Rendered PNG dimension | 794×1123 | **1240×1754** |
| Golden PNG dimension | 1241×1754 | 1241×1754（不變）|

---

## 6. Sprint 30 學到的工程教訓

### 6.1 Test infrastructure 也要審查

13 個 sprint 沒人查過「我們和 goldens 的 PNG 維度是否一致」，靠 diff 比例變化追蹤。每次 sprint 報告都看「Sprint N+1 比 Sprint N 改善 X%」，但 **絕對值 0.17 是否合理**沒人質疑。

教訓：**新 sprint 開頭花 5 分鐘讀 top diff sample 比看綜合報告更高 ROI**。

### 6.2 Pipeline 默認值要寫實情，不寫假設

Sprint 14 寫「DPI 96 對齊 canvas-editor harness」是當時假設，但事實上 goldens 由 Word/PDF 在 150 DPI 產出。註解錯誤掩蓋了真實情況 12 個 sprint。

教訓：**註解寫「為什麼是 X」必須附證據**，否則容易變成永遠正確的虛假理由。

### 6.3 單一 magic number 校準的 ROI 仍然很高

Sprint 25 (spacing.line) / 26 (auto row heuristic) / 28 (CJK em 1.15) 都印證 magic number 校準的價值。Sprint 30 再次驗證：**DPI 96→150 兩行改動**，視覺 diff -18.7%、6 個 category 全改善。

只要假設方向對（fixture-driven），單點修正可一次清掉大量問題。

### 6.4 用 file/identify 工具讀 PNG 維度

`file *.png` 顯示寬高 × bit-depth，**比讀 image header 程式快**。除錯 visual 問題第一步該是「golden 和 ours 是不是同 size / DPI」。

---

## 7. 規劃書同步項

- §0.5 加 Sprint 30 entry：DPI 96→150 對齊，總體 mean -18.7%
- §0.5 文件清單補 [sprint30_dpi_alignment.md](sprint30_dpi_alignment.md)
- §0.6.13 完成度表加 Sprint 30 欄；Phase 3 (Layout) 90% 不變、test infra 加註 DPI 修正
- §0.6.13 「Sprint 30+ 優先級建議」→「Sprint 31+」；新主軸：04_with_image 個案處理（image cell layout）
- 文件 header 最後更新日期

---

## 8. Sprint 31+ 候選

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **04_with_image fixture 個案處理**：照片 cell 內 image alignment / center / aspect ratio / caption 位置 — 28 pages × 0.38 包辦 48% 剩餘 diff | 總體 mean 0.1386 → 預估 0.10 |
| 2 | 🟡 **03_complex_table 全套管系列細節**：5 個 fixture page 1 mean 0.30-0.33；可能是 cell border / merge / image embedding 細節 | 03_complex_table 0.1661 → 預估 0.10 |
| 3 | 🟡 opentype.js `charToGlyph().advanceWidth` 接入（Sprint 28 長期方案）：取代 empirical 1.15 → 真實字型 metric | 長期正確性 |
| 4 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求） | 新功能 |
| 5 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |
| 6 | 🟢 docGrid type=linesAndChars 水平 snap（Sprint 29 補完） | 規範完整性 |

---

**Sprint 30 一句話總結**：發現 visual regression pipeline 預設 DPI=96 與 goldens（150 DPI）不匹配，pixelmatch crop 到 min(794, 1241) 把 golden 砍成左上 64% → 02_std_table 週報 page 2 等 fixture 假象 0.62-0.64 diff；改 DPI 96→150 後**單一修正**：總體 mean **0.1705→0.1386（-18.7%）**、6 個 category 全改善（02_std_table -51.5% / 03_complex_table -33.6%）、零退化、vitest 767+1skip 不變；Sprint 31+ 轉向 04_with_image 個案處理（剩 48% diff 主源）。

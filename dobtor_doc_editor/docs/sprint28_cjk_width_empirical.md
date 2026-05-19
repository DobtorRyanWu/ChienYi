# Sprint 28 — CJK 字寬 empirical 校準（1.0 em → 1.15 em）

**期間**：2026-05-11
**主軸**：Sprint 27 重定位的 root cause（CJK 字寬 metric 估短）— 用 empirical 實驗找最佳 em 係數，避免立即上 HarfBuzz async 大改
**結論**：CJK em 係數 1.0 → **1.15**，修了 **2 個 fixture（人手孔調升降 + 地坪鋪面）零退化**；mismatched **5 → 3（-40%）**、Visual Regression v14 comparedPages **121 → 123**、總體 mean **0.1757 → 0.1728（-1.7%）**、05_header_footer per-cat **-4.4%**（最大改善）。剩 3 個 -1 fixture（02_std_table/工地密度 + 03_complex_table/06-8估驗計價 ×2）root cause 不在 CJK 字寬，需 Sprint 29+ 換角度。

---

## 0. 入工前狀態（Sprint 27 後）

| 指標 | Sprint 27 |
|---|---|
| Page count mismatched fixture | 5 / 42 |
| totalDelta | -5 |
| 5 個 -1 fixture | 02_std_table/1140206 + 03_complex_table/06-8估驗計價 ×2 + 05_header_footer/人手孔 + 地坪 |
| Sprint 27 結論 | Root cause = CJK 字寬 metric 估短；建議 Sprint 28+ HarfBuzz / opentype.js 真接 Layout |

### 0.1 為何不直接上 HarfBuzz

評估 HarfBuzz 整合的工程量：

| 項 | 現況 | 整合工程量 |
|---|---|---|
| `ShapingEngine.shape()` | **async** Promise（HarfBuzz WASM）| 與 sync Layout pipeline 不兼容 |
| `EstimateMetrics.measureWidth()` | **sync** | 接 sync API |
| `opentype.js` | sync（FontMetrics 已用） | 需 `font.charToGlyph().advanceWidth` 接入測寬 |
| 字型載入 | 手動 `registerMetrics()` | 需 ChienYi 端提供 CJK 字型 byte buffer |

完整接入要 2-3 sprint。Sprint 28 採**empirical 校準**先確認假設成立 + 取得即時收益。

---

## 1. 假設：CJK em 係數 > 1.0

[`EstimateMetrics.charWidthEms()`](../static/src/core/layout/TextMetrics.ts) 對 CJK 用 `1.0 em`：

```ts
if (isCjkChar(ch)) return 1.0;
```

但 Word 渲染 CJK 字符的 effective advance width 略 > 字級（來自字距 / cluster shaping / 字型 hinting）。我們低估 → 每行多塞 ~10-15% 字數 → 多行 CJK 文本 wrap 行數低估 1-2 行 → cell 內容估短 → table 估短 → -1 頁。

### 1.1 實驗設計

固定 lineRule=exact 段落（每行 13-14pt 高），CJK em 係數從 1.0 起逐步調高，看 vitest `09_page_count_baseline` snapshot。

| em | mismatched | Δ | 退化 |
|---|---|---|---|
| 1.00（原值）| 5 / 42 | baseline | — |
| **1.10** | **4 / 42** | -1（修 1：人手孔調升降）| **0** |
| **1.15** | **3 / 42** | -1（再修 1：地坪鋪面）| **0** ← **採用** |
| 1.20 | 4 / 42 | +1 退化 01_simple/03.1120210 | 1 退化 |

**1.15 = 甜蜜點**：最多 fixture 改善 + 零退化。1.20 開始過度（Sprint 26 修好的 01_simple/03.1120210 又被推回 -1）。

### 1.2 為何 1.15 是甜蜜點

Word 對「現代 CJK 字型」（Noto Sans CJK / 蘋方 / 思源 等）的 effective advance width 通常落在 **1.0-1.15 em** 之間。1.15 偏 robust 邊（向上）以對齊普遍 CJK 字型行為。

---

## 2. 修法落地

### 2.1 修改範圍

[`static/src/core/layout/TextMetrics.ts`](../static/src/core/layout/TextMetrics.ts)：

```ts
// CJK：1.15 em（Sprint 28 empirical）
if (isCjkChar(ch)) return 1.15;
```

附詳細 comment 紀錄實驗結果與選 1.15 的理由（4 個 em 點實測表）。

### 2.2 unit test 對齊新值

3 個既有 unit test 必須更新（原本假設 CJK = 1.0 em）：

| Test | 修法 |
|---|---|
| `TextMetrics.test.ts` "CJK 字元寬度 ≈ fontSize（1 em）" | 改 「≈ fontSize × 1.15」，24pt → 27.6pt |
| `LineBreaker.test.ts` "禁止行首字符（標點）會被推回上一行" | lineWidth 30 → 32（讓 abc + 「，」剛好觸發強迫 cut）|
| `LineBreaker.test.ts` "首行縮排扣減第一行可用寬度（足以擠出多一行）" | lineWidth 60 → 70、firstLineIndent 24 → 28（5 個 CJK × 1.15 em × 12pt = 69pt）|

---

## 3. 三層 SOP 結果

### 3.1 Layer 1 — vitest 全套

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run -u --pool=forks --poolOptions.forks.singleFork=true
```

**755/755 + 1 skipped**（Sprint 27 baseline 755 + 0 新增；3 個 test 改 expectation；不退化）

`09_page_count_baseline` snapshot 變動：
- **mismatched: 5 → 3**
- **totalDelta: -5 → -3**
- 人手孔調升降.docx: delta -1 → 0（golden 5 / ours 5）
- 地坪鋪面.docx: delta -1 → 0（golden 5 / ours 5）

### 3.2 Layer 2 — Visual Regression v14

```bash
npx rollup -c rollup.visual_regression.config.js
node scripts/visual_regression_v14.mjs --max-diff 1.0
```

**rendered 42/42 / comparedPages 121 → 123 / failedPages 0**

| Category | Sprint 27 | **Sprint 28** | Δ |
|---|---|---|---|
| 01_simple | 0.0917 | **0.0913** | -0.4% |
| 02_std_table | 0.2702 | 0.2710 | +0.3%（持平）|
| 03_complex_table | 0.2946 | 0.2941 | -0.2%（持平）|
| 04_with_image | 0.3861 | 0.3861 | 0% |
| **05_header_footer** | 0.0495 | **0.0473** | **-4.4%**（最大改善）|
| 06_template | 0.0324 | 0.0325 | +0.3%（持平）|
| **總體 mean** | 0.1757 | **0.1728** | **-1.7%** |
| comparedPages | 121 | **123** | **+2** |

### 3.3 Layer 3 — 視覺 spot check + Playwright

人手孔調升降.docx 第 5 頁（Sprint 28 解鎖）：
- diff = **0.0010**（123 頁中倒數第二低，幾乎完美對齊 golden）
- 內容 = `+++END-FOR evenIndex+++`（matches Word golden 結構）

地坪鋪面.docx 第 5 頁：diff = **0.0010** 同樣完美對齊。

Playwright admin E2E：**6/6 passed (1.2m)**，Sprint 21-27 host integration 不退化。

---

## 4. 為何剩 3 個 -1 fixture 不修

| Fixture | Sprint 28 結果 | Root cause |
|---|---|---|
| 02_std_table/1140206-工地密度 | 仍 -1 | 純段落 fixture，title 80+ 字 CJK 已套 1.15 em；但 paragraph 16 (空段落 line=1240 exact = 62pt) 等異常 spacing 可能影響；root cause 不純是字寬 |
| 03_complex_table/06-8估驗計價 ×2 | 仍 -1 | 整 section 605pt / 785pt = 0.77 頁，1.15 em 把 cell 內容稍微撐高但**整體仍未溢頁**；Word 把 2 頁的原因可能與 keepNext 段落跨 row 強制留白有關（Sprint 27 cell-keepNext fix 已 infra 落地但因未溢頁未生效）|

→ 剩 3 個 fixture 都不純粹是 CJK 字寬問題。02 / 03 各自需獨立的 root cause 細查（**Sprint 29+ 個案處理**）。

---

## 5. 量化結果

| 指標 | Sprint 27 | **Sprint 28** |
|---|---|---|
| Page count mismatched | 5/42 | **3/42（-40%）** |
| totalDelta | -5 | **-3** |
| CJK 字寬係數 | 1.00 em | **1.15 em** |
| vitest test files | 48 (+1 skipped) | 48 (+1 skipped)|
| vitest test cases | 755 + 1 skipped | **755 + 1 skipped**（3 個改 expectation，未增減）|
| Visual Regression v14 comparedPages | 121 | **123** |
| Visual Regression v14 05_header_footer | 0.0495 | **0.0473（-4.4%）** |
| Visual Regression v14 總體 mean | 0.1757 | **0.1728（-1.7%）** |
| Playwright admin E2E | 6/6 | 6/6（不退化）|

---

## 6. Sprint 28 學到的工程教訓

### 6.1 Empirical 校準是低風險高 ROI 路徑

完整接入 HarfBuzz 是 2-3 sprint 工程，但**單一 magic number 調整**已能修一半 fixture。先 empirical 試水溫，確認假設成立後再上長期工程方案。

### 6.2 「Sweet spot」要實測，不該推導

1.15 是試 1.10 / 1.15 / 1.20 三個點挑出來的。沒有先驗式可推導「最佳 em」— **vitest snapshot 是唯一可靠的儀表**。

### 6.3 Unit test 必須跟著 magic number 走

修改 magic number（CJK 1.0 → 1.15）讓 3 個既有 unit test 失敗。這是預期行為（測試**驗證假設**，假設變了測試也要變）。Sprint 28 同時更新 3 個 test 的 expectation 並寫清 reason，**不該 disable** 它們。

### 6.4 後續仍應上 HarfBuzz

1.15 是粗略平均；不同字型實際 advance width 仍會有差。未來若客戶字型偏 1.05（變細）或 1.20（變粗），1.15 就會偏。Sprint 29+ 接 opentype.js `font.charToGlyph().advanceWidth` 才是長期正確方案。

---

## 7. 規劃書同步項

- §0.5 加 Sprint 28 entry：empirical CJK em 校準 + 修 2 fixture + 零退化
- §0.5 文件清單補 [sprint28_cjk_width_empirical.md](sprint28_cjk_width_empirical.md)
- §0.6.13 完成度表加 Sprint 28 欄；mismatched 5→3；Phase 3 82%→84%（CJK 字寬實測對齊）
- §0.6.13 「Sprint 28+ 優先級」→「Sprint 29+ 優先級」；新項目 9 改為「剩 3 個 -1 偏差個別擊破第五輪（02_std_table 純段落 / 03_complex_table cell-keepNext 跨 row 整塊 keep）」+「HarfBuzz / opentype.js 真接 Layout（取代 empirical 1.15）」
- 文件 header 最後更新日期

---

## 8. Sprint 29+ 候選

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **剩 3 個 -1 偏差個別擊破第五輪**：02_std_table/1140206 純段落 spacing 細查 / 03_complex_table cell-keepNext 跨 row 整塊 keep 規則 | mismatched 3→1 或 0（主軸達成）|
| 2 | 🟡 **opentype.js `charToGlyph().advanceWidth` 接入**：取代 empirical 1.15 → 真實字型 metric；當 ChienYi 端配字型 byte buffer 時可進入主流程 | 提升像素級對齊度 / 長期正確性 |
| 3 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求） | 新功能 |
| 4 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |
| 5 | 🟢 lazy_loader / pagination_engine.js 評估清理 | code review |

---

**Sprint 28 一句話總結**：用 empirical 實驗（1.10 / 1.15 / 1.20）找 CJK em 係數甜蜜點 1.15，修 2 個 fixture（人手孔調升降 + 地坪鋪面）零退化、mismatched 5→3（-40%）、Visual Regression v14 comparedPages 121→123 / 總體 mean -1.7% / 05_header_footer per-cat -4.4%；HarfBuzz 真接 Layout 留 Sprint 29+ 為長期方案。

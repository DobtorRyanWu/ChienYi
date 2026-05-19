# Sprint 25 — 7 個 -1 偏差 fixture 個別擊破第一輪：spacing.line 規則套用

**期間**：2026-05-10
**主軸**：把 Sprint 19 已解析但**從未被 layout 引擎消費**的 `spacing.line / lineRule` 套進 LineBreaker
**結論**：05_header_footer 自主檢查表---植筋.docx 從 -1 偏差修為 **0 偏差**（第一個用該 fixture cluster 內容對齊 Word 的）；vitest 745/745 + 1 skipped 全綠；Visual Regression v14 03_complex_table mean diff -7.9% / 05_header_footer -2%；mismatched 從 7 收到 **6（-14%）**。

---

## 0. 入工前狀態（Sprint 24 後）

| 指標 | Sprint 24 |
|---|---|
| Page count mismatched fixture | 7 / 42 |
| totalDelta | -7（每個都少 1 頁） |
| 7 個 -1 fixture 分類 | 01_simple ×1 / 02_std_table ×1 / 03_complex_table ×2 / 05_header_footer ×3 |
| Sprint 19 診斷結論 | 異質根因，留 Sprint 20+ 個別擊破 |

Sprint 19 §8 建議優先順序：1) **05_header_footer ×3**（最大 fixture 數）→ 2) 03_complex_table ×2 → 3) 01/02 個案 → 4) header/footer 樣式合併 → 5) run-level 樣式合併。

Sprint 25 從 (1) 起手。

---

## 1. Root cause 診斷

### 1.1 假設驗證（先排除既有假設）

Sprint 19 推測「段落 spacing.before/after 預設值對齊 Word（OOXML 預設 240 twips = 12pt）」。
實裝清查**否定**這個假設：

```python
# 自主檢查表---人手孔調升降.docx 的 styles.xml docDefaults 與預設段落 style "a1"
docDefaults rPr: only fonts/lang  # 沒 spacing
default paragraph style: a1 → widowControl=0, autoSpace=0  # 也沒 spacing
```

→ Word 對這個 fixture 確實沒有 240 twips 預設 spacing.before/after。假設不成立。

### 1.2 真正的 root cause

掃 `git grep 'spacing\.line'` 在 layout 引擎下：

```
static/src/core/ooxml/document/ParagraphParser.ts:219:  spacing.line = { rule, value };
（其他 layout/render 路徑：0 命中）
```

→ ParagraphParser 把 `<w:spacing w:line="500" w:lineRule="exact"/>` 解析進 `paragraph.props.spacing.line`，但 **LineBreaker 與 Paginator 都沒讀取 spacing.line**，只 Paginator 用了 `spacing.before/after`。

LineBreaker.makeLine() 算行高的方式（pre-Sprint 25）：

```ts
let height = 0;
for (const it of items) {
  if (it.kind === 'box') if (it.height > height) height = it.height;
}
if (height === 0) height = (para.defaultFontSize ?? 10.5) * 1.2;
```

純看 box 高度（從字型 metric 來），**完全無視段落級 line spacing 規則**。

### 1.3 fixture 對 spacing.line 的實際依賴

5 個 fixture 段落（人手孔調升降 section 0 + section 1 表頭段落）的 spacing：

| 段落 | sz | spacing | 實際應行高 | 我們算的 | Δ |
|---|---|---|---|---|---|
| p[0] 廠商列 | 36 (=18pt) | line=480 lineRule=exact | **24pt**（強制） | ~22pt 自然 | -2 |
| p[2] 表名 | 32 (=16pt) | 無 | 自然 ~19pt | ~19pt | 0 |
| p[3] 編號 | 28 (=14pt) | line=500 lineRule=exact | **25pt**（強制） | ~17pt 自然 | -8 |
| p[5] 簽名 | 28 (=14pt) | line=500 lineRule=exact | **25pt**（強制） | ~17pt 自然 | -8 |
| section[1] p×6 | 28 (=14pt) | line=500 / 200 lineRule=exact | **25pt / 10pt**（強制） | ~17pt | 累積 |

**規格依據**：ECMA-376 §17.3.1.33 spacing
- `lineRule="exact"` → w:line 是固定 twip
- `lineRule="atLeast"` → w:line 是最低 twip
- `lineRule="auto"` → w:line 是 240 為基準的倍率

我們系統性低估行高 → 段落擠 → 最後一頁吃進前一頁 → 整 fixture 少 1 頁。

---

## 2. 修法

### 2.1 落地檔案

| 檔案 | 變更 |
|---|---|
| [`static/src/core/layout/LineBreaker.ts`](../static/src/core/layout/LineBreaker.ts) | `makeLine` / `makeEmptyLine` 加 `applySpacingLine(natural, para)` post-pass：exact 覆蓋 / atLeast clamp / auto 乘以 ratio |
| [`tests/unit/layout/LineBreaker.spacingLine.test.ts`](../tests/unit/layout/LineBreaker.spacingLine.test.ts) | 新增 10 case unit test：3 rule × 多重組合 + 多行段落 + K-P 路徑 + 空段落 + 復現 fixture 段落 |

### 2.2 applySpacingLine 實作

```ts
function applySpacingLine(natural: Pt, para: ParagraphInput): Pt {
  const spLine = para.props.spacing?.line;
  if (!spLine) return natural;
  const value = spLine.value;
  if (!Number.isFinite(value) || value <= 0) return natural;
  switch (spLine.rule) {
    case 'exact':   return value;
    case 'atLeast': return natural >= value ? natural : value;
    case 'auto':    return natural * value;
    default:        return natural;
  }
}
```

ParagraphParser:218 早就處理過 unit 換算（auto 已除以 240 變成 ratio，exact/atLeast 已從 twip 轉成 pt）；這裡直接用即可。

### 2.3 涵蓋面

- ✅ greedy 斷行（Sprint 2 預設）走 `makeLine`：每行套用
- ✅ Knuth-Plass（Sprint 13 opt-in）也走 `makeLine`：自動受惠
- ✅ 空段落（`makeEmptyLine`）：套用後空行高也尊重 spacing.line
- ✅ Table cell 內段落：cell paragraphs 透過 TableLayout → BoxBuilder → LineBreaker，自動受惠
- ✅ Header / footer 段落：同 layout pipeline，自動受惠

---

## 3. 三層 SOP 結果

### 3.1 Layer 1 — vitest 全套 regression

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run -u --pool=forks --poolOptions.forks.singleFork=true
```

**745/745 pass + 1 skipped**（Sprint 19 baseline 735 + Sprint 25 spacingLine 10 = 745）。

關鍵 snapshot 變動：

| Snapshot | Δ |
|---|---|
| `09_page_count_baseline.test.ts.snap` | 植筋.docx delta -1→0、ours 4→5；mismatched **7→6**；totalDelta **-7→-6** |
| `08_render_ops_trace.test.ts.snap` | 3 個 01_simple textHash 變（行 y 位移使 hash 重算；text 字數不變、不退化）|

零 unexpected fail。

### 3.2 Layer 2 — Visual Regression v14 像素級量化

```bash
npx rollup -c rollup.visual_regression.config.js  # 21.3s build
node scripts/visual_regression_v14.mjs --max-diff 1.0  # puppeteer 全 42 fixture
```

**rendered 42/42 / comparedPages 120 / failedPages 0**

| Category | Sprint 19 | **Sprint 25** | Δ |
|---|---|---|---|
| 01_simple | 0.0930 | 0.0933 | +0.3%（持平）|
| 02_std_table | 0.2674 | 0.2702 | +1%（持平）|
| **03_complex_table** | 0.3198 | **0.2946** | **-7.9%** |
| 04_with_image | 0.3862 | 0.3861 | 持平 |
| **05_header_footer** | 0.0504 | **0.0494** | **-2%** |
| 06_template | 0.0325 | 0.0322 | 持平 |
| **總體 page-weighted mean** | 0.1784 | **0.1766** | **-1%** |
| comparedPages | 119 | **120** | **+1**（植筋 4→5 解鎖）|

**重點**：03_complex_table 雖然頁數還沒對齊，但**像素級對齊度提升 7.9%**（cell 內段落行高也受惠 spacing.line 使每 row 對 Word 更接近）。05_header_footer 額外從 0.0504→0.0494 細部改善（其他 9 個 5_hf fixture 連帶受益）。

### 3.3 Layer 3 — 視覺 spot check（人工可驗）

植筋.docx 第 5 頁（Sprint 25 解鎖的「新頁」）：

- Ours: [`tests/fixtures/.visual_regression_tmp/v14/自主檢查表---植筋-5.rendered.png`](../tests/fixtures/.visual_regression_tmp/v14/) — 內容只有 `+++END-FOR evenIndex +++`，左上偏左
- Golden: [`tests/fixtures/05_header_footer/golden/自主檢查表---植筋-5.png`](../tests/fixtures/05_header_footer/golden/) — 同樣只有 `+++END-FOR evenIndex+++`，水平居中
- diffRatio = **0.0010**（120 個頁面中倒數第二低，幾乎完美對齊）

→ 這頁的存在本身就是 Sprint 25 修法成果；頁數對 + 內容對 + 像素級接近 0 diff。

### 3.4 Playwright admin E2E（regression check）

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright && npx playwright test --project=admin
```

**6/6 passed (1.3m)**：Sprint 21-24 的 5 個 host model 按鈕 + end-to-end 點擊全綠。Sprint 25 純 layout 改動，未碰 host integration / view，不退化符合預期。

---

## 4. 為何只修了 1/3 的 05_header_footer fixture？

| Fixture | section[0] table | sumMinHeight | Sprint 25 後 |
|---|---|---|---|
| 人手孔調升降 | 21 rows | 13.64 in | 仍 -1 |
| 地坪鋪面 | 21 rows | 13.16 in | 仍 -1 |
| **植筋** | **22 rows** | **14.55 in** | **0 ✓** |

差別：植筋 section[0] 的 22-row 大表 sumMinHeight = 14.55 in，原本就在「2 頁邊界」附近。Sprint 25 把 section[0] 表頭 4 個段落每個從 ~17pt 拉到 25pt（+8pt × 3 段落 ≈ 0.33 in），剛好把總和推過 2 頁界線變 3 頁，section[0] +1 頁 → 整 fixture 4→5 頁。

人手孔調升降 13.64 in / 地坪鋪面 13.16 in 兩個離界線還有距離，Sprint 25 +0.33 in 仍不足以推下一頁。它們的 -1 偏差 root cause 在**別處**——可能：
- 表格 cell 內段落行高（cell paragraphs **無** spacing.line，所以 Sprint 25 完全沒影響它們的 cell 內容高）
- 表格 cell padding / borderHeight 計算
- section[1] 的 2-row 大表（每 row trHeight=5783 = 4.02 in，2 rows = 8.03 in）的 row 邊界與 cell 內容的互動

**留 Sprint 26+** 細查（不在 spacing.line 主軸範圍內）。

---

## 5. 量化結果

| 指標 | Sprint 24 | **Sprint 25** |
|---|---|---|
| Page count mismatched fixture | 7 / 42（83% 對齊）| **6 / 42（86% 對齊）** |
| totalDelta | -7 | **-6** |
| Layout 引擎已支援的 OOXML pPr 規格 | spacing.before / after / 部分 | **+ spacing.line（exact / atLeast / auto）** |
| vitest test files | 47 (+1 skipped) | **48 (+1 skipped)** |
| vitest test cases | 735 + 1 skipped | **745 + 1 skipped**（+10 spacingLine）|
| Python regression | 105/105 | 105/105（不退化）|
| Visual Regression v14 comparedPages | 119 | **120** |
| Visual Regression v14 03_complex_table | 0.3198 | **0.2946（-7.9%）** |
| Visual Regression v14 05_header_footer | 0.0504 | **0.0494（-2%）** |
| Visual Regression v14 總體 mean | 0.1784 | **0.1766（-1%）** |
| Playwright admin E2E | 6/6 | 6/6（不退化）|

---

## 6. 規劃書同步項

- §0.5 加 Sprint 25 entry：spacing.line 套用、植筋 -1→0、03_complex 像素 -7.9%、三層 SOP 全綠
- §0.5 結論段：「Sprint 24 起聚焦…」改為「Sprint 25 完成 7 個 -1 偏差 fixture 個別擊破第一輪」
- §0.5 文件清單補 [sprint25_spacing_line_consume.md](sprint25_spacing_line_consume.md)
- §0.6.13 完成度表加 Sprint 25 欄；🟡「7 個剩 -1 偏差 fixture 個別擊破」改為 🟡「**剩 6 個 -1 偏差**」（ChienYi mixin 第三輪 Sprint 24 已劃掉、Sprint 25 第一輪劃半條）
- §5.4 Phase 3.x（pagination）補：「Sprint 25 補 spacing.line consume」
- 文件 header 最後更新日期

---

## 7. Sprint 26+ 候選（重排）

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **剩 6 個 -1 偏差個別擊破第二輪**：人手孔調升降 / 地坪鋪面 — table cell 內段落行高 / cell padding 計算 | mismatched 6→4 |
| 2 | 🟡 03_complex_table ×2 — cell-level keepNext 視為 cantSplit 嘗試 | mismatched 4→2 |
| 3 | 🟡 01_simple ×1 / 02_std_table ×1 個案 | mismatched 2→0（**主軸達成**）|
| 4 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求） | 新功能 |
| 5 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |
| 6 | 🟢 lazy_loader / pagination_engine.js 評估清理 | code review only |
| 7 | 🟢 HarfBuzz 真接 Layout（CJK 字距） | Layout + visual diff |

---

## 8. 環境註記

Sprint 25 在 WSL 7.8GB / swap 4GB 記憶體環境下完成；vitest 全套 + rollup build + puppeteer 視覺 regression 加總用量約 2.5GB。記憶體吃緊時可：
- `--pool=forks --poolOptions.forks.singleFork=true` 降低 vitest 並行開銷
- `NODE_OPTIONS="--max-old-space-size=1800"` 限制 V8 heap
- 跑前殺掉長期占記憶體的 `bfs` / `find /` 背景作業

---

**Sprint 25 一句話總結**：把 ParagraphParser 早就解析卻被 LineBreaker 完全忽略的 OOXML `w:spacing line/lineRule` 規則接通；植筋.docx 一個 fixture 從 -1 修為 0 對齊 Word；7→6 mismatched / 03_complex_table 像素 -7.9% / 全套三層 SOP 全綠；剩 6 個 -1 偏差留 Sprint 26+ 第二輪個別擊破。

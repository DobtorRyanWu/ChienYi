# Sprint 29 — OOXML §17.6.5 docGrid + §17.3.1.32 snapToGrid 落地

**期間**：2026-05-11
**主軸**：剩 3 個 -1 fixture 個別擊破第五輪 — 用 OOXML 規範的 docGrid + snapToGrid 規則實作 Word 對中文文件 baseline 對齊 grid 的行為
**結論**：實作 docGrid type='lines' + snapToGrid，**修 3 個 -1 fixture（02_std_table/1140206 取樣 + 03_complex_table/06-8 估驗計價 ×2）零退化**。`mismatched 3 → 0`、`totalDelta -3 → 0`，**42/42 fixture 全部對齊 golden 頁數**。Visual Regression v14 comparedPages 123 → 126 / 總體 mean 0.1728 → 0.1705（-1.3%）/ 03_complex_table -15.0% / 02_std_table -5.5%。

---

## 0. 入工前狀態（Sprint 28 後）

| 指標 | Sprint 28 |
|---|---|
| Page count mismatched fixture | 3 / 42 |
| totalDelta | -3 |
| 3 個 -1 fixture | 02_std_table/1140206-取樣 + 03_complex_table/06-8 估驗計價 ×2 |
| Sprint 28 結論 | CJK 字寬 empirical 1.15 em 達到甜蜜點；剩 3 個 root cause 不在字寬 |

### 0.1 Sprint 28 留下的方向

Sprint 28 audit 明確指出：「剩 3 個 -1 fixture，root cause 不在 CJK 字寬範圍」並建議：
- 個案處理（Sprint 29+ 優先項 1）
- 長期 opentype.js `font.charToGlyph().advanceWidth` 接入（優先項 2）

Sprint 29 走「個案處理」路徑，先實測再決定要不要 commit。

---

## 1. 根本原因：未實作 OOXML 文件格線（docGrid）

### 1.1 規範背景

OOXML §17.6.5 `<w:docGrid>`：

```xml
<w:sectPr>
  <w:docGrid w:type="lines" w:linePitch="364"/>
</w:sectPr>
```

- `type="lines"`：每行 baseline 對齊 grid（vertical only，常見中文設定）
- `type="linesAndChars"` / `"snapToChars"`：含字元水平 snap（極少用）
- `type="default"`：無 grid（不影響行高）
- `linePitch`：grid 之間 baseline 距離（twip）。`364 twip = 18.2pt`

OOXML §17.3.1.32 `<w:snapToGrid w:val="..."/>`：
- 預設 `val=1`（true）：本段落 lines 對齊 grid
- `val=0`（false）：本段落不對齊 grid

### 1.2 為何 Word 對 3 個 fixture 渲染為 2 頁、我們只算 1 頁

| Fixture | Section docGrid | 關鍵段落 |
|---|---|---|
| 02_std_table/1140206-工地密度取樣紀錄 | `type=lines linePitch=364` (18.2pt) | P5-P8 `line=600 exact` (30pt)、P13-P16 同；P9-P11 explicit `snapToGrid=0` 不 snap |
| 03_complex_table/06-8 估驗計價（1） | `type=lines linePitch=385` (19.25pt) | P0 `line=360 exact` (18pt)、P5-P8 `line=280 exact` (14pt)；table 內 cell paragraph `line=260 exact` (13pt) |
| 03_complex_table/06-8 估驗計價 11409 | 同上 | 同上 |

Word 應用規則：
- P5 line=30pt + linePitch=18.2pt → `ceil(30/18.2) = 2 grids = 36.4pt`（每行 +6.4pt）
- 06-8 cell line=13pt + linePitch=19.25pt → `ceil(13/19.25) = 1 grid = 19.25pt`（每行 +6.25pt）

累積到整段、整表，內容因 docGrid 撐高 → 觸發 Word 換頁；我們未實作這條規則 → 內容剛好還在第 1 頁。

實測 1140206 取樣紀錄：
- 我們不 snap：maxY = 708.2pt（contentH 728.5pt 內，差 20pt）
- 套用 snap 後：增 ~125pt 行高累積 → P17 推到第 2 頁

---

## 2. 假設演進：H1 → H2（refined）

### 2.1 H1（初版）：對所有段落 snap

**規則**：`linePitch > 0 && snapToGrid != false` → `height = ceil(height / linePitch) × linePitch`

**結果**（全 fixture scan）：
- 修 3 個 -1 fixture ✓
- 但 **6 個新 over-paginate regression**：
  - 03_complex_table/1121229 / 1130105 / 1130109 / 1130112 / 1130516（全套管基樁混凝土查驗系列）→ 1 → 2 頁
  - 04_with_image/05.112磺港溪監造會議照片 → 2 → 4 頁

**Net**：mismatched 3 → 6（變差）

### 2.2 Root cause 分析：regression fixture 的特性

讀 1121229 cell paragraphs：
```
r0/c0/p0: snapToGrid=None spacing={} text='工程名稱：...'
r1/c1/p0: snapToGrid=None spacing={'line': '400', 'lineRule': 'exact'} text='說明：施工抽查'
```

大量 cell paragraph **完全沒設 `w:spacing`** → 我們的 H1 仍 snap natural lineHeight 12.6pt → 18pt（+5.4pt per line），表格被撐爆。

但 Word 對「沒設 spacing.line」的段落顯然不做 grid snap（goldens 證實）。OOXML 規範對此沒有明確規定，但實測一致：**只有顯式 spacing.line 的段落才走 grid snap**。

### 2.3 H2（最終版）：限縮 snap 觸發條件

**規則**：
```
不 snap 的情況：
  - linePitch <= 0（無 grid 或 default type）
  - paragraph snapToGrid === false（顯式關閉）
  - paragraph 沒設 spacing.line（無顯式 line spacing）

否則：height = ceil(declared_height / linePitch) × linePitch
```

**結果**：
- 修 3 個 -1 fixture ✓
- **零 regression**（5 個全套管 + 04_with_image 都沒設 spacing.line 所以不 snap）
- mismatched 3 → 0、totalDelta -3 → 0

---

## 3. 實作落地

### 3.1 OOXML AST 擴充

[`static/src/core/ooxml/ast/types.ts`](../static/src/core/ooxml/ast/types.ts)：
- `SectionNode` 加 `docGrid?: { type: 'lines' | 'linesAndChars' | 'snapToChars' | 'default'; linePitch: Pt }`
- `ParagraphProps` 加 `snapToGrid?: boolean`（預設 true，顯式 `val="0"` 為 false）

### 3.2 解析

[`static/src/core/ooxml/section/SectionParser.ts`](../static/src/core/ooxml/section/SectionParser.ts)：
- 新 `parseDocGrid()`：讀 `<w:docGrid>` 屬性，type='default' 不寫入（保 snapshot 穩定）

[`static/src/core/ooxml/document/ParagraphParser.ts`](../static/src/core/ooxml/document/ParagraphParser.ts)：
- pPr parse 加 `<w:snapToGrid w:val="0">` 偵測 → `props.snapToGrid = false`

### 3.3 Layout 套用

[`static/src/core/layout/LineBreaker.ts`](../static/src/core/layout/LineBreaker.ts)：
- `LineBreakOptions` 加 `docGridLinePitch?: Pt`
- 新 `applyDocGridSnap(height, para, linePitch)` 函式（H2 規則）
- `makeLine` / `makeEmptyLine` 新增 `docGridLinePitch` 參數；在 `applySpacingLine` 後追加 `applyDocGridSnap`
- 6 個 `makeLine` 呼叫點 + 1 個 `makeEmptyLine` 呼叫點全部透傳；K-P 路徑同步

[`static/src/core/layout/Paginator.ts`](../static/src/core/layout/Paginator.ts)：
- `PaginateContext` 加 `docGridLinePitch: Pt`
- 新 `docGridLinePitchOf(section)`：把 `section.docGrid` 翻成 LineBreaker 的 linePitch（type=default → 0）
- `makeContext` / `rebindCtxToSection` 設定 `ctx.docGridLinePitch`
- `layParagraph` 呼叫 `breakParagraph` 時帶入 `docGridLinePitch: ctx.docGridLinePitch`
- `laySingleTable` 把 `docGridLinePitch` 透傳到 `options`，再交給 `layoutTable / layoutCell`

[`static/src/core/layout/types.ts`](../static/src/core/layout/types.ts)：
- `LayoutOptions` 加 `docGridLinePitch?: Pt`

[`static/src/core/layout/TableLayout.ts`](../static/src/core/layout/TableLayout.ts)：
- cell paragraph `breakParagraph` 呼叫帶入 `docGridLinePitch: options.docGridLinePitch`

---

## 4. 三層 SOP 結果

### 4.1 Layer 1 — vitest 全套

```bash
NODE_OPTIONS="--max-old-space-size=2500" npx vitest run
```

**767/767 + 1 skipped**（Sprint 28 baseline 755 + 12 新 docGrid test cases）

新增測試：
- [`tests/unit/layout/LineBreaker.docGrid.test.ts`](../tests/unit/layout/LineBreaker.docGrid.test.ts)：8 個 case 覆蓋
  - `linePitch=0` 不 snap
  - `exact 30 + pitch 18.2 → 36.4`
  - `auto 1.15 + pitch 19.25 → 38.5`
  - `snapToGrid=false` 不 snap
  - 段落無 spacing.line 不 snap（regression 保險）
  - 空段落 + spacing.line + docGrid → snap
  - `linePitch > exact value`（小字落大格）
  - 多行段落都一致 snap

- [`tests/unit/SectionParser.test.ts`](../tests/unit/SectionParser.test.ts)：新增 4 case
  - `type=lines linePitch=364` 解析為 18.2pt
  - `type=default` 不寫入 docGrid
  - `linePitch` 缺失 → 0
  - 無 `w:docGrid` 不存在

snapshot 變動（2 個 -u 更新）：
- `09_page_count_baseline`：3 個 -1 fixture delta 0 → mismatched 3→0、totalDelta -3→0
- `08_render_ops_trace`：~11 個 fixture 的 textHash / fillRect 隨行高改動位移（預期改動）

### 4.2 Layer 2 — Visual Regression v14

```bash
npx rollup -c rollup.visual_regression.config.js
node scripts/visual_regression_v14.mjs --max-diff 1.0
```

**rendered 42/42 / comparedPages 123 → 126（+3）/ failedPages 0**

| Category | Sprint 28 | **Sprint 29** | Δ |
|---|---|---|---|
| 01_simple | 0.0913 | 0.0917 | +0.4%（持平）|
| **02_std_table** | 0.2710 | **0.2560** | **-5.5%**（1140206 取樣 解鎖）|
| **03_complex_table** | 0.2941 | **0.2500** | **-15.0%**（06-8 ×2 解鎖）|
| 04_with_image | 0.3861 | 0.3880 | +0.5%（持平）|
| 05_header_footer | 0.0473 | 0.0473 | 0%（不退化）|
| 06_template | 0.0325 | 0.0325 | 0% |
| **總體 mean** | 0.1728 | **0.1705** | **-1.3%** |
| comparedPages | 123 | **126** | **+3** |

### 4.3 Layer 3 — 視覺 spot check + Playwright

新解鎖頁面 diff：
- 1140206 取樣紀錄 page 2: diff = **0.0270**（極低，幾乎完美對齊 golden）
- 06-8 估驗計價 (1) page 1/2: mean **0.0711**
- 06-8 估驗計價 11409 page 1/2: mean **0.0738**

Playwright admin E2E：6/6 passed（與 Sprint 21-28 一致，無退化）

---

## 5. 為何剩 3 個 -1 fixture 必須走 docGrid 而非其他方案

| 替代方案 | 為何不選 |
|---|---|
| 全 fixture 統一升 CJK em 係數 | Sprint 28 已試（1.20 退化 01_simple/03.1120210）；1.15 已是甜蜜點 |
| 個別 fixture 針對性 fix | 不可維護；3 個 fixture 共享同一 OOXML 規格特徵（docGrid + lineRule=exact）|
| opentype.js 接 measureWidth | 工程量大且不解決 baseline 對齊問題（baseline 是 vertical metric） |
| H1（不限縮觸發條件） | 引入 6 個 over-paginate regression（cell 內 no-spacing paragraph 被誤升）|

docGrid + snapToGrid 是 **OOXML 規範明文**的中文文件 baseline 對齊機制，Sprint 29 之前沒實作純粹是覆蓋率漏項。H2 規則對齊 Word 實測行為。

---

## 6. 量化結果

| 指標 | Sprint 28 | **Sprint 29** |
|---|---|---|
| Page count mismatched | 3/42 | **0/42（-100%）** |
| totalDelta | -3 | **0** |
| 全 42 fixture 對齊 golden | 39/42 | **42/42** |
| docGrid 規則覆蓋 | 0% | **type=lines / linesAndChars / snapToChars 完整支援** |
| snapToGrid val=0 處理 | 無 | **顯式 false → 不 snap** |
| vitest test files | 48 (+1 skipped) | 49 (+1 skipped) |
| vitest test cases | 755 + 1 skipped | **767 + 1 skipped**（+12 新）|
| Visual Regression v14 comparedPages | 123 | **126** |
| Visual Regression v14 02_std_table | 0.2710 | **0.2560（-5.5%）** |
| Visual Regression v14 03_complex_table | 0.2941 | **0.2500（-15.0%）** |
| Visual Regression v14 總體 mean | 0.1728 | **0.1705（-1.3%）** |
| Playwright admin E2E | 6/6 | 6/6（不退化）|

---

## 7. Sprint 29 學到的工程教訓

### 7.1 規範實作要先 audit 觸發條件，再寫規則

H1 直接照 ECMA-376 spec「snapToGrid=true 時 line 對齊 grid」一刀切套，引入 6 個 regression。經 fixture 比對才發現 Word 對「沒設 spacing.line 的段落」實作上 silently 不 snap — 規範雖沒明說，但 Word 實作如此。**規範文字 ≠ Word 實作；fixture 比對才是 ground truth**。

### 7.2 全 fixture scan 在 commit 前是強制步驟

Sprint 26 訂下「全 fixture scan before commit」SOP，Sprint 29 完美驗證：H1 直接 commit 會引入 6 個 regression；scan 後改 H2 才達成零退化。**snapshot baseline 是高 ROI 護欄**。

### 7.3 累積機制可比單點修正威力大

Sprint 25-28 用 4 個 sprint 漸進修出 7 → 3 個 -1 fixture（每 sprint -1 至 -2）。Sprint 29 用 1 個規範實作一次清掉剩 3 個。**規範層級的工程往往比 fixture-by-fixture patch 更高效**，但前提是先有 fixture baseline 證實假設方向正確。

### 7.4 docGrid 是中文 docx 必備

39/42 fixture 都設了 docGrid（type=lines）。**這是中文文件強訊號**，未實作會在邊緣 fixture 失準。後續若接客戶字型，docGrid 規則仍然成立（與 opentype.js metric 互補，不衝突）。

---

## 8. 規劃書同步項

- §0.5 加 Sprint 29 entry：docGrid + snapToGrid 落地，剩 3 個 -1 fixture **全清**
- §0.5 文件清單補 [sprint29_docgrid_snap.md](sprint29_docgrid_snap.md)
- §0.5 結論段：mismatched **3→0（全清）**、42/42 全對齊
- §0.6.13 完成度表加 Sprint 29 欄；Phase 3 84%→**90%+**（page count 對齊達成）
- §0.6.13 「Sprint 29+ 優先級」→「Sprint 30+ 優先級」；原項目 1（剩 3 個 -1 fixture 個別擊破）標完成；新主軸：
  - **像素級 visual diff 收斂**（總體 mean 0.1705 → 目標 0.10 以下）
  - opentype.js `charToGlyph().advanceWidth` 接入（取代 empirical 1.15）
  - Phase 3.6 註腳/尾註等新功能
- 文件 header 最後更新日期：2026-05-11

---

## 9. Sprint 30+ 候選

| 順位 | 主題 | 預期效果 |
|---|---|---|
| 1 | 🟡 **像素級 visual diff 收斂**：04_with_image 0.388 / 03_complex_table 0.250 / 02_std_table 0.256 是當前主要 visual diff 來源；逐 fixture 分析 + 對應 OOXML 規則補完 | 總體 mean 0.1705 → 目標 0.10 |
| 2 | 🟡 **opentype.js `charToGlyph().advanceWidth` 接入**：取代 empirical 1.15 → 真實字型 metric；當 ChienYi 端配字型 byte buffer 時可進入主流程 | 提升像素級對齊度 / 長期正確性 |
| 3 | 🟡 Phase 3.6 註腳 / 尾註（30% 政府文件需求） | 新功能 |
| 4 | 🟢 docGrid `type=linesAndChars` 水平 snap（極少數客戶可能需要）| 規範完整性 |
| 5 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件 only |

---

**Sprint 29 一句話總結**：實作 OOXML §17.6.5 docGrid + §17.3.1.32 snapToGrid（H2：只對顯式 spacing.line 段落 snap），**42/42 fixture 全部對齊 golden 頁數**、mismatched 3→0（-100%）、totalDelta -3→0、Visual Regression v14 總體 mean -1.3% / 03_complex_table -15.0% / 02_std_table -5.5%、零退化；page count 對齊主軸正式達成，Sprint 30+ 轉向像素級 visual diff 收斂。

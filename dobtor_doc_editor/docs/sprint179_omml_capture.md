# Sprint 179 — OMML 數學公式 capture（Phase 5.1）

**日期**：2026-05-22
**類型**：parser（capture-only、Phase 5.1 OMML 數學公式）
**規畫書對應**：§5 階段 D Phase 5.1「OMML → KaTeX / MathJax」
**前置**：決策 C（user 2026-05-21 GO 全 6 子功能）；Sprint 179 P0 prep（Phase 5 fixtures 入庫）
**fixture**：`tests/fixtures/09_omml/`（6 份 synthetic：分數 / 根號 / 求和 / 上下標 / 矩陣）

---

## Hypothesis

Phase 5.1 OMML：Word「插入 → 方程式」的數學公式，以 OMML（Office Math Markup
Language、ECMA-376 §22.1、`m:` 命名空間）內嵌於 document.xml 段落中：
- 段落直屬 `<m:oMath>`（§22.1.2.77）→ 行內公式（inline math）
- 段落直屬 `<m:oMathPara><m:oMath>...`（§22.1.2.78）→ 獨立置中公式（display math）

現況 probe：ParagraphParser 段落子元素 loop 處理 `w:r`/`w:fldSimple`/`w:hyperlink`/
`w:bookmarkStart-End`/`w:commentRange*`/`w:ins`/`w:del`，**無 `m:oMath`/`m:oMathPara`
case → 數學公式內容完全被丟棄**。

42/42 VR fixture 無 OMML（grep 確認、§142 probe 已記錄 0 覆蓋）→ capture 必 VR byte-identical。

---

## 修法

### 1. `OmmlNode` / `MathNode` 型別 + `ParagraphNode.math?`（types.ts、+38 行）

- `OmmlNode`：OMML 元素的遞迴通用樹節點（`tag` localName / `text` 僅 `m:t` /
  `children` 遞迴、無子節點不掛 key）。capture-only —— 不解語意、不轉 MathML / KaTeX。
- `MathNode`：段落內一段公式（`display` 區分 inline / display math、`omml` 為樹）。
- `ParagraphNode.math?: MathNode[]`：比照 Sprint 177 `commentRefs?` 側陣列模式、
  非空才掛 key（紀律 #21）。

### 2. `omml/OmmlParser.ts`（新模組、+72 行）

`parseOmmlChildren(el)`：遞迴走訪 OMML 元素子節點 → `OmmlNode[]`。
- `stripMathPrefix`：去 `m:` 命名空間前綴留 localName。
- `<m:t>` 為文字葉節點 → 讀 `textContent`（含空字串）。
- 其餘結構元素遞迴解子節點；無子節點不掛 `children`（紀律 #21）。
- 防禦：undefined / null / 無元素子節點 → 空陣列（不 throw）。
- 用 `directChildren`（純元素子節點、不展開 `mc:AlternateContent`）。

### 3. ParagraphParser wiring（+16 行）

段落子元素 loop 新增二 case：
- `case 'm:oMath'`：段落直屬 → `MathNode{ display: false }`（行內公式）。
- `case 'm:oMathPara'`：逐 `<m:oMath>` 子元素 → `MathNode{ display: true }`（display）。
收集到 `mathNodes` 區域陣列、段落結束時非空才掛 `node.math`（紀律 #21）。

**Scope-down（紀律 #18）**：capture-only —— `math` 為段落層級側陣列、layout / render
不消費。OMML → KaTeX 渲染 + 行內精確位置 wire-up 留 Sprint 180。

### 4. 測試（+21）

- `tests/unit/OmmlParser.test.ts`（新檔、13 test）：parseOmmlChildren 基礎
  （undefined / 空 / `m:t` 文字 / 去前綴 / 紀律 #21 不掛 children）+ 結構元素遞迴
  （分數 / 根號 / n 元 / 上下標 / 矩陣 / 屬性容器 / 順序保留）。
- `tests/unit/ParagraphParser.test.ts`（+8 test）：行內 / display 公式、分數樹、
  多 `m:oMath`、公式與 run 混排、順序保留、紀律 #21 不掛 key、空 `m:oMath`。

### 5. baseline integration 測試排除 Phase 5 fixture（紀律 #14）

Sprint 179 P0 prep 入庫的 18 份 Phase 5 fixture（07_chart 8 / 08_smartart 4 /
09_omml 6）被 4 個 glob `tests/fixtures/` 的 baseline 程式掃進去、撐破「42 fixture」
基線。修正：新增 `PHASE5_FIXTURE_DIRS` 排除集到——
- `04_ast_snapshot.test.ts`（AST 結構快照）
- `08_render_ops_trace.test.ts`（renderer fingerprint）
- `09_page_count_baseline.test.ts`（page count baseline）
- `scripts/visual_regression_v14.mjs`（VR pipeline）

維持 VR / baseline = 42 fixture 不變；清除 04 寫入的 18 個過時 snapshot。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite（`npm test`）1540 → **1561 passed + 1 skipped**（+21） |
| L2 VR v14 | ✅ **byte-identical 第 39 連** | rendered 42/42、comparedPages 126、failedPages 0；VR mean 0.073191 維持 |
| L3 visual spot check | ✅ capture-only | math 為段落側陣列、layout / render 不消費 → 42 fixture 渲染零變動 |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js 宣告 /
  SettingsParser position enum）、**無新增**。
- flake8（`tools/build_phase5_fixtures.py`、Sprint 179 P0 prep）：clean。
- frontend bundle 重建（ParagraphParser / types 在 frontend 依賴樹）。

**vitest 計數說明**：本 sprint 改採 `npm test`（vitest.config include `tests/unit/**`
+ `tests/integration/**`）全套口徑 = 1561。progress_snapshot 記錄的 Sprint 178 數字
1468 與全套實測（~1540）不符、疑為先前 sprint 計數方法不一致；本 sprint 起標註全套數字。

---

## 紀律

- **#1.a**：改 parser（ParagraphParser）跑全 42 fixture VR、byte-identical 第 39 連。
- **#18 scope-down**：capture-only —— OMML 樹完整保留、不解語意 / 不轉 KaTeX /
  不做行內位置；render 留 Sprint 180。
- **#21**：`OmmlNode.children` 無子節點不掛、`ParagraphNode.math` 非空才掛 key。
- **#14（DRY / 模組化）**：`omml/` 子目錄聚集；`MathNode` 比照 `commentRefs` 側陣列、
  `parseOmmlChildren` 用既有 `directChildren`。
- **#14（baseline 一致性）**：4 處 glob `tests/fixtures/` 的 baseline 統一加
  `PHASE5_FIXTURE_DIRS` 排除、維持「42 fixture」不變。
- **#8 / 決策 C**：09_omml 6 份為 synthetic fixture（OMML 無真實工程資料來源、
  user 同意）；07_chart / 08_smartart 為真實工程資料抽取。

---

## 後續

- **Sprint 180**：OMML → KaTeX render wire-up（`MathNode` 從段落側陣列接到 layout /
  render、行內精確位置、KaTeX 整合）。
- Phase 5.2 SmartArt mc:Fallback capture（08_smartart fixture 已就緒）。
- Phase 5.3 Charts mc:Fallback capture（07_chart fixture 已就緒）。
- Phase 5 fixture 待 render + golden 就緒後、評估納入 VR baseline（屆時 42 → 60）。

---

## Sprint 179 結尾累積指標

- vitest **1561 passed + 1 skipped**（`npm test` 全套；+21）
- VR mean **0.073191**（byte-identical 第 39 連、rendered 42/42 / comparedPages 126 / failedPages 0）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 178 → **179**
- Phase 5.1 OMML capture 完成（capture 端閉合、render 留 Sprint 180）

---

## File-level summary

```
A  static/src/core/ooxml/omml/OmmlParser.ts          OMML 遞迴樹解析（+72）
A  static/src/core/ooxml/omml/index.ts               re-export（+1）
A  tests/unit/OmmlParser.test.ts                     13 test
M  static/src/core/ooxml/ast/types.ts                OmmlNode / MathNode / ParagraphNode.math?（+38）
M  static/src/core/ooxml/document/ParagraphParser.ts m:oMath / m:oMathPara case（+16）
M  tests/unit/ParagraphParser.test.ts                +8 test（Sprint 179 OMML）
M  tests/integration/04_ast_snapshot.test.ts         PHASE5_FIXTURE_DIRS 排除
M  tests/integration/08_render_ops_trace.test.ts     PHASE5_FIXTURE_DIRS 排除
M  tests/integration/09_page_count_baseline.test.ts  PHASE5_FIXTURE_DIRS 排除
M  scripts/visual_regression_v14.mjs                 PHASE5_FIXTURE_DIRS 排除
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
```

**淨 production code 變動 = +127 行**（OmmlParser +72 / index +1 / types +38 / ParagraphParser +16）、
capture-only、VR byte-identical 第 39 連、Phase 5.1 OMML capture 端閉合。

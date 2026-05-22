# Sprint 180 — OMML 數學公式 render（Phase 5.1 收尾）

**日期**：2026-05-22
**類型**：parser 增強 + mapper render（Phase 5.1 OMML、線性文字 fallback）
**規畫書對應**：§5 階段 D Phase 5.1「OMML → KaTeX / MathJax、AST 解析 + 渲染」
**前置**：Sprint 179（OMML capture）；決策 C（user 2026-05-21 GO）

---

## Hypothesis

Sprint 179 完成 OMML capture（`ParagraphNode.math` 側陣列、`OmmlNode` 遞迴樹）。
本 sprint 把公式 render 出來。

**render 策略決定 — 線性文字 fallback（非 KaTeX）**：
- 規畫書 §5 Phase 5.1 原列「OMML → KaTeX」。但 KaTeX 非現有依賴，整合 = bundle
  +~270KB。Sprint 128 對 HarfBuzz WASM +465KB 已判「production 整合不可接受」。
- user 2026-05-21 對 Phase 5 大三項已拍板 **mc:Fallback 壓縮**（接受降級保真度、
  避免重 infra）。OMML 無 fallback 圖、其對應的降級策略 = **線性文字**
  （分數 `a/b`、根號 `√(x)`、上下標 `x_(n)^(2)`、矩陣 `[a, b; c, d]`）。
- → 本 sprint 採線性文字 fallback render；KaTeX 全保真排版列為未來 optional sprint。

**capture 增強需求**：Sprint 179 `OmmlNode` 只存 tag/text/children、未存屬性。
n 元運算子字元（`<m:chr m:val="∑">`）、delimiter 括號（`<m:dPr begChr endChr>`）
等語意載於屬性 → linearize 需要 → 本 sprint 補 `OmmlNode.attrs`。

---

## 修法

### 1. `OmmlNode.attrs?`（types.ts、+6 行）

`attrs?: Record<string, string>` — 元素屬性 localName → 值（去 `m:` 前綴）。
無屬性不掛 key（紀律 #21）。Sprint 179 既有 no-attr 測試不受影響（純 capture 元素
多無屬性、`toEqual` 形狀不變）。

### 2. OmmlParser 屬性捕捉 + `ommlToLinearText`（OmmlParser.ts、+約 130 行）

- `collectAttrs(el)`：收集元素屬性 → Record（跳過 `xmlns*` 宣告、去 `m:` 前綴）；
  `parseOmmlChildren` 對每個元素掛 `attrs`（紀律 #21 無屬性不掛）。
- `ommlToLinearText(omml)`：遞迴把 OmmlNode 樹轉線性文字。
  - `f` 分數 → `num/den`；`rad` 根號 → `deg√(e)`；`nary` → `chr_(sub)^(sup)(e)`
    （`chr` 取自 `<m:naryPr><m:chr m:val>`、缺則預設積分符號 `∫`、OOXML §22.1.2.70）；
    `sSub`/`sSup`/`sSubSup` → `e_(sub)` / `e^(sup)`；`d` delimiter → `begChr…endChr`；
    `m` 矩陣 → `[列, 格 ; …]`。
  - 屬性容器（`rPr`/`ctrlPr`/`naryPr`/…）→ 不產生文字；未明列元素 → 遞迴拼接子節點。

### 3. ToCanvasEditor render wire-up（+約 14 行）

`appendParagraph`：`para.runs` 迴圈後，若 `para.math` 非空 → 逐 `MathNode` 以
`ommlToLinearText` 轉線性文字、`appendChars` 接到段落 IElement 陣列。

**Scope-down（紀律 #18）**：capture-only 階段 `math` 未保留行內精確位置 →
公式一律 append 於段落 runs 之後。多數公式為 math-only 段落、此近似可接受；
inline-mixed 精確位置 + KaTeX 全保真排版留未來 optional sprint。

### 4. 測試（+16）

- `tests/unit/OmmlParser.test.ts`（+12）：屬性捕捉（attrs / 紀律 #21 / xmlns 排除）
  + `ommlToLinearText`（分數 / 根號 / nary 含 chr / nary 預設 ∫ / sSubSup / 矩陣 /
  屬性容器不產字 / 空樹）。
- `tests/unit/ToCanvasEditor.test.ts`（+4）：行內分數、display 根號、公式與 run
  混排、無 math 段落不受影響。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1561 → **1577 passed + 1 skipped**（+16） |
| L2 VR v14 | ✅ **byte-identical 第 40 連** | rendered 42/42、comparedPages 126、failedPages 0；0/42 fixture 含 OMML → `para.math` 皆 undefined → render 新分支 0 觸發 |
| L3 visual spot check | ✅ 線性文字 fallback | 公式以線性符號近似（`a/b` / `√(9)` / `x_(1)^(2)` / `[1, 2; 3, 4]`）|

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle 重建（OmmlParser / ToCanvasEditor 在 frontend 依賴樹）。

---

## 紀律

- **#1.b / Strategy C**：render 新分支只在 `para.math` 非空時觸發；0/42 fixture
  含 OMML → byte-identical 第 40 連（render 只對真有公式的文件改輸出）。
- **#1.a**：改 mapper 跑全 42 fixture VR。
- **#18 scope-down**：線性文字 fallback（非 KaTeX、避免 +270KB bundle）；
  行內精確位置留未來。**與 user mc:Fallback 壓縮決策一致**（OMML 的降級對應）。
- **#21**：`OmmlNode.attrs` 無屬性不掛 key。
- **#14（DRY）**：linearizer 與 capture 同檔（omml/OmmlParser.ts）；ToCanvasEditor
  複用既有 `appendChars` / `mapRunProps`。
- **#22**：KaTeX 依賴決定 — 依 Sprint 128（HarfBuzz +465KB 不可接受）precedent +
  user mc:Fallback 決策、直接採線性 fallback、未另開 probe sprint。

---

## 後續

- KaTeX 全保真排版（OMML → KaTeX）— 未來 optional sprint（需評估 bundle 取捨）。
- OMML 行內精確位置 wire-up（math 從段落側陣列改 inline）— 未來 optional。
- **Phase 5.1 OMML 完成**（capture Sprint 179 + render Sprint 180）。
- 下一步：Phase 5.2 SmartArt mc:Fallback capture（08_smartart fixture 已就緒）。

---

## Sprint 180 結尾累積指標

- vitest **1577 passed + 1 skipped**（`npm test` 全套；+16）
- VR mean **0.073191**（byte-identical 第 40 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 179 → **180**
- Phase 5.1 OMML 完成（capture + 線性文字 fallback render）

---

## File-level summary

```
M  static/src/core/ooxml/ast/types.ts                OmmlNode.attrs?（+6）
M  static/src/core/ooxml/omml/OmmlParser.ts          attrs 捕捉 + ommlToLinearText（+約 130）
M  static/src/core/ooxml/omml/index.ts               export ommlToLinearText
M  static/src/core/ooxml/mapper/ToCanvasEditor.ts    para.math 線性文字 render（+約 14）
M  tests/unit/OmmlParser.test.ts                     +12 test（attrs + linearizer）
M  tests/unit/ToCanvasEditor.test.ts                 +4 test（OMML render）
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
```

**淨 production code 變動 = +約 150 行**、線性文字 fallback render、VR byte-identical
第 40 連、Phase 5.1 OMML（capture + render）完成。

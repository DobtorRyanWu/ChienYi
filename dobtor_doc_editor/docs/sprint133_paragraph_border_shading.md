# Sprint 133 — 段落邊框 / 底色解析 + borderShading utility 抽出（Phase 4.4 起點）

**日期**：2026-05-17
**類型**：code change（新 utility 抽出 + ParagraphParser 補完 / Phase 4.4 Paragraph 進階起點）
**規畫書對應**：§Phase 4.4「`<w:pBdr>` 段落邊框 + 陰影」+ autonomous_roadmap.md 階段 B cluster 6 行 1
**前置 sprint**：Sprint 132 numberingFormatter 模組（cluster 5 收尾）

---

## Hypothesis（驗證對象）

`ParagraphParser.parseParagraphProps` 完全沒處理 `<w:pBdr>`（段落邊框）與 `<w:shd>`（段落底色）；ParagraphProps 雖然在 types.ts line 99-109 有 `borders?` 與 `shading?` 欄位定義，但沒人 set。實務影響：Word「報告封面框線」「醒目區段背景填色」匯入後完全消失。

額外觀察：TableParser 已有 `parseBorderDef` / `parseShading` 私有 helper、與段落邊框 schema 完全相同（`<w:top w:val="single" w:sz="4" w:color="000000"/>`）；不抽出共用會在兩處維護同樣 logic。

**Hypothesis A（功能正確性）**：抽 `parseBorderDef` / `parseShading` 到 `styles/borderShading.ts`、新增 `parseParagraphBorders`（段落專用、無 insideH/V）；ParagraphParser 與 TableParser 共用、shape 一致。

**Hypothesis B（VR 穩定性）**：42 fixture 多為政府表格、段落層級邊框 / 底色少用（多用 cell-level borders + shading）；預期 byte-identical（紀律 #1.a 第 10 次連續驗證機會）。

**Hypothesis C（refactor 風險）**：TableParser 把 `parseBorderDef` / `parseShading` 改為 import 後、所有 30 個 TableParser test 應 100% pass（行為等價、無語意改變）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B cluster 6 第 1 個：「133 | Phase 4 Style | 4.4 `<w:pBdr>` 段落邊框 + 陰影」（Sprint 132 audit 中決議）
- 規畫書 §Phase 4.4 列：「`<w:frame>` 段落框、`<w:pBdr>` 段落邊框 + 陰影、`<w:tab>` tab stop 進階、`<w:textAlignment>`」
- 本 sprint scope = **`<w:pBdr>` 4 邊 + `<w:shd>` shading parser + DRY refactor**
- 不在 scope（留 Sprint 134+）：
  - `<w:tab>` tab stop leader / decimal alignment 進階（Sprint 134）
  - `<w:textAlignment>` 文字行內對齊（Sprint 134）
  - `<w:frame>` 段落框（罕見、defer）
  - `<w:pBdr>` 的 `<w:between>`、`<w:bar>` 邊（不對應 ParagraphProps.borders 4 邊、defer）
- PR-size：borderShading.ts +130 行（新檔）/ ParagraphParser.ts +20 行 / TableParser.ts -38 行（移除 parseBorderDef + parseShading）+ 4 行 import / ParagraphParser.test.ts +150 行 / 11 新 test / 1 audit / 1 bundle rebuild

### 2. 設計決策

#### 2.1 為什麼新建 `borderShading.ts` 而非 export from TableParser

選擇 A：把 TableParser 內部 helper 改為 `export function`
選擇 B：抽到 `styles/borderShading.ts` 共用模組

**選 B**：

- TableParser 已 import DocumentParser、ParagraphParser 又 import TableParser 會形成循環（DocumentParser → TableParser → ParagraphParser → TableParser）
- borderShading 是「OOXML 知識共用層」、屬 `styles/` 目錄語意（已有 ThemeResolver / colorResolver / TableStyleApplicator 在此）
- 未來 BorderConflictResolver 也可共用此模組、避免散落

#### 2.2 parseParagraphBorders vs parseCellBorders 拆分

- `parseCellBorders`（TableParser 內）支援 6 邊：top / bottom / left / right + insideH / insideV
- `parseParagraphBorders`（borderShading.ts）僅 4 邊：top / bottom / left / right
- 段落 `<w:pBdr>` 的 `<w:between>` / `<w:bar>` 屬「段落間 / 邊欄」、不對應 ParagraphProps.borders 4 邊 → silent drop（紀律 #21 候選做法、需未來 sprint 加 between/bar 支援時擴 ParagraphProps shape）

#### 2.3 為什麼把 `auto` 色保留為字面值

- `w:color="auto"` 在 OOXML 意義是「使用 default」（黑色或主題色）
- borderShading 不嘗試解析 auto → '000000'，保留為字面值 'auto' 由 renderer / mapper 決定
- 與既有 TableParser 行為一致、避免改變 cell borders 解析結果

### 3. 修法

#### 3.1 新檔 `static/src/core/ooxml/styles/borderShading.ts`（+130 行）

```ts
export function parseBorderDef(el: Element): BorderDef | undefined { /* w:val + w:sz + w:color + w:space */ }
export function parseShading(el: Element): { fill?, color?, pattern? } { /* w:fill + w:color + w:val */ }
export function parseParagraphBorders(pBdr: Element): { top?, bottom?, left?, right? } | undefined { /* 4 邊掛 key、between/bar 略過 */ }
```

3 個 export、share `parseBorderDef` 內部、`parseParagraphBorders` 包裝專用於段落。

#### 3.2 TableParser.ts refactor（-38 行、+4 行 import）

```diff
- function parseBorderDef(el: Element): BorderDef | undefined { /* 22 行 */ }
- function parseShading(el: Element): { /* 16 行 */ }
+ import { parseBorderDef, parseShading } from '../styles/borderShading';
```

清理同時：`BorderDef` / `BorderStyle` 兩個 type import 不再需要（只有 parseBorderDef 函式用到）、一併移除。

#### 3.3 ParagraphParser.ts（+20 行）

```ts
import { parseParagraphBorders, parseShading } from '../styles/borderShading';

// 在 parseParagraphProps 內、boolFlag 處理後新增：
const pBdrEl = directChild(pPr, 'w:pBdr');
if (pBdrEl) {
  const borders = parseParagraphBorders(pBdrEl);
  if (borders) props.borders = borders;
}

const shdEl = directChild(pPr, 'w:shd');
if (shdEl) {
  const shading = parseShading(shdEl);
  if (shading.fill || shading.color || shading.pattern) {
    props.shading = shading;
  }
}
```

紀律 #21 enforce：empty borders / shading 不掛 key。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1118 passed + 1 skipped**（從 1107+1 起、+11 新 ParagraphParser pBdr/shd test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 10 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（pre-existing warning 同前、bundle rebuild 27.8s）|
| L4 Odoo backend | **跳過**（無 backend / model / ACL 變動）|

**Refactor 等價驗證**：TableParser 既有 30 個 unit test 0 修改、100% pass、證明 parseBorderDef / parseShading 抽出語意等價。

### 5. Unit test 設計（11 個新 test）

| Test | 鎖定行為 |
|---|---|
| pBdr 完整 4 邊 → borders 含 top/bottom/left/right BorderDef | 主路徑、含 sz=4 → width=0.5pt 轉換驗證 |
| pBdr 部分邊（只 top）→ borders 只含 top key | 紀律 #21：empty 邊不掛 |
| pBdr 全空（無子邊）→ borders 不掛 key | 紀律 #21：empty borders 整體不掛 |
| pBdr 子邊缺 w:val → 該邊 silent drop（無效邊） | parseBorderDef 邊界 |
| pBdr w:start / w:end → 對應 left / right | OOXML logical direction |
| pBdr w:between / w:bar → silent drop、不影響其他邊 | scope 釐清：4 邊以外 defer |
| shd 完整 → shading 含 fill + color + pattern | 主路徑 |
| shd 只有 fill → 其他 key 不掛 | 紀律 #21：empty 屬性不掛 |
| shd 全空（無屬性）→ shading 不掛 key | 紀律 #21：empty shading 整體不掛 |
| pBdr + shd 同時存在 → 互不干擾 | 兩 path 獨立 |
| 普通段落（無 pBdr / shd）→ borders / shading 都不掛 | 回歸：原有路徑不被影響 |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/styles/borderShading.ts` | +130 行 / 新檔 | parseBorderDef / parseShading / parseParagraphBorders 共用 |
| `static/src/core/ooxml/document/ParagraphParser.ts` | +20 行 / +1 import | pBdr + shd 解析 |
| `static/src/core/ooxml/table/TableParser.ts` | -38 行（移除 parseBorderDef + parseShading）+ 1 import + 移除 2 unused types | DRY refactor |
| `tests/unit/ParagraphParser.test.ts` | +150 行 / 11 新 test | 鎖定 pBdr + shd 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、byte-identical | VR confirm |
| `docs/sprint133_paragraph_border_shading.md` | 本 audit doc | 紀錄補完設計 |
| `docs/autonomous_roadmap.md` | Sprint 133 ✅ + 進度表 | cluster 6 啟動 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §0.2 Phase 4 83% → 84% + §Phase 4.4 註記 | 同步 |

### Test 數變動

- Sprint 132 結尾：vitest 1107 + 1 skipped
- Sprint 133 結尾：vitest **1118 + 1 skipped**（+11）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 132 結尾：mean 0.073191（byte-identical）
- Sprint 133 結尾：mean **0.073191**（byte-identical、**第 10 次連續** 121→126→130→131→132→133）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style Theme：83% → **84%**（+1%、4.4 pBdr + shd 解析補完；剩 tab stop leader+decimal、textAlignment、frame、between/bar borders）

---

## Root cause

**為什麼 Sprint 1-132 沒做 pBdr / shd parsing**：

1. Sprint 1 落地 ParagraphParser 時 focus 主流 props（alignment / indent / spacing / numbering）；pBdr / shd 屬「進階格式」延後
2. ParagraphProps shape 已預留 borders / shading 欄位（未來 ready）、但實際 parse 路徑漏 → 結構性技術債
3. 42 fixture 段落層級 pBdr 罕見（多為自由段落或 cell-level shading）、VR 無 signal trigger
4. TableParser 已有 parseBorderDef helper、未抽出共用、形成「pBdr 解析能力存在於系統內、但沒人接到段落」的奇景

**為什麼 VR byte-identical**：

ParagraphParser 改動屬「parser 補完」、現有 fixture 段落多無 pBdr → 新增的 if 分支根本不 trigger、render 路徑完全等價。TableParser refactor 屬「函式位置搬遷」、語意 byte-identical、30 個 TableParser test 0 修改全綠證明。

---

## 紀律

### 紀律 #1.a 第 10 次連續驗證（Sprint 133）

連續 10 sprint code change 都跑全 VR 並維持 byte-identical：

| Sprint | 改動 | VR |
|---|---|---|
| 121 | TableParser trHeight | 0.073191 |
| 122 | OLE/pict fallback | 0.073191 |
| 123 | field code 完整 | 0.073191 |
| 124 | sdt unwrap | 0.073191 |
| 125 | bookmark capture | 0.073191 |
| 126 | hyperlink 3 屬性 | 0.073191 |
| 130 | HSL luminance | 0.073191 |
| 131 | tblStylePr/tcPr | 0.073191 |
| 132 | numberingFormatter | 0.073191 |
| **133** | **pBdr/shd + DRY refactor** | **0.073191** |

紀律 #1.a 穩固、**10 次連續 byte-identical**、覆蓋至 6 類修改點（parser / dom utility / style resolver / table applicator / pure utility 新模組 / DRY refactor）。

### 紀律 #21 第 3 次正式應用（Sprint 133）

> optional 欄位空集合不掛 key（升正式 Sprint 131）。

Sprint 133 嚴格 enforce：
- pBdr 全空 → borders 不掛
- pBdr 部分邊缺 → 該邊不掛、整 borders 仍掛（部分填）
- shd 全空（無 attr）→ shading 不掛
- shd 部分 attr 缺 → 該 attr 不掛、整 shading 仍掛

### 紀律 #18 持續

PR-size 守住：1 新 utility 檔 +130 / 1 parser +20 / 1 refactor -38+1 / 1 test +150 / 1 audit / 1 bundle。明示 5 項不在 scope（tab stop leader / decimal align / textAlignment / frame / between+bar borders）。

### 紀律 #4 應用（Sprint 133）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 133 揭示：
1. **ParagraphProps 預留欄位 ≠ parser 實作**：types.ts shape 完整不代表系統 work、需正向反向 trace
2. **跨檔 schema 重複是技術債來源**：TableParser 與 ParagraphParser 對同一 `<w:bdr>` schema 處理應集中、不集中會在演進時發散
3. **VR 不揭示段落層級 pBdr 缺失**：fixture 偏 cell-level、整 Sprint 1-132 沒被觸發；證明 Phase 完成度需多向 audit（不能只靠 VR signal）

---

## 後續

### Sprint 134（cluster 6 第 2 個）

階段 B cluster 6 第 2 個：**Phase 4.4 剩餘 `<w:tab>` leader + decimal alignment + `<w:textAlignment>`**。

當前 `parseParagraphProps` 已有 tabs 基本解析（Sprint 1 時落地）含 leader 屬性 capture、但 align 只接受 left/right/center/decimal、`decimal` align 是否真實渲染由 Layout 處理。Sprint 134 補：
- `<w:textAlignment>` 文字行內垂直對齊（baseline / center / top / bottom）
- tab stop leader 渲染補完（如 `leader="dot"` 對應「.....」）— 屬 Layout 階段、parser 部分 Sprint 1 已 capture
- 可能補：`<w:frame>` 段落框基礎 capture（屬罕見、簡化版）

預期 PR-size 小：types.ts +5~10 行（textAlignment 欄位）/ ParagraphParser +5 行 / unit test +20~30 行。

### Sprint 133+ 候選

- **pBdr `<w:between>` / `<w:bar>`**：擴 ParagraphProps.borders shape 加 between/bar 欄位、罕用、defer
- **`<w:frame>` 完整支援**：段落框、罕見於 ChienYi 文件、defer
- **wire-up borders / shading 到 mapper / renderer**：需 paragraph layout 階段渲染框線 / 背景、屬 Layout sprint
- **BorderConflictResolver 對段落邊框的處理**：段落層級邊框與 cell borders 互動、罕見、defer

---

## Sprint 133 結尾累積指標

- vitest **1118 passed + 1 skipped**（+11）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 10 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style Theme 83% → **84%**
- 21 ADR / 紀律 **20 條** + 6 子 + 2 候選（無新增、#22 候選持平 2/3、#20 候選持平 1/3）
- Sprint audit doc 數 132 → **133**
- 階段 B cluster 6 (133) 第 1 個完成、134 進行 Phase 4.4 收尾

---

## File-level summary

```
A  addons/dobtor_doc_editor/static/src/core/ooxml/styles/borderShading.ts  (+130 行新 utility)
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+20 行 / +1 import：pBdr + shd 解析)
M  addons/dobtor_doc_editor/static/src/core/ooxml/table/TableParser.ts  (-38 行 helper / +1 import / -2 unused type import：DRY refactor)
M  addons/dobtor_doc_editor/tests/unit/ParagraphParser.test.ts  (+150 行 / 11 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint133_paragraph_border_shading.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 133 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 4 83→84%)
```

無 model / view / ACL / rule / controller / backend 變動。階段 B cluster 6 第 1 個完成、紀律 #1.a 第 10 次連續 byte-identical、紀律 #21 第 3 次正式應用。

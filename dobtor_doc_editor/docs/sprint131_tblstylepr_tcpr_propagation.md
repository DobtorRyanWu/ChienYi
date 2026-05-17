# Sprint 131 — tblStylePr/tcPr 條件樣式 cell-level props 傳遞（Phase 4.2 起點）

**日期**：2026-05-17
**類型**：code change（API 擴充 + 條件樣式邏輯補完 / Phase 4.2 tblStylePr 補完）
**規畫書對應**：§Phase 4.2「`<w:tblStylePr>` 15 種條件、字元樣式 + 段落樣式的合併順序、樣式連結」+ autonomous_roadmap.md 階段 B cluster 4 行 2
**前置 sprint**：Sprint 130 ThemeResolver HSL luminance 升級（cluster 4 第 1 個）

---

## Hypothesis（驗證對象）

`StyleResolver.parseRawStyle` 對 `<w:tblStylePr>` 只收集 `w:pPr`（段落屬性）與 `w:rPr`（run 屬性），**完全 silent drop** `w:tcPr`（cell-level 屬性）。`TableStyleApplicator.applyTableStyle` 對應只 mutate `paragraph.props` 與 `run.props`、不寫 `cell.props`。

實務影響：Word 最常見的「標題列背景色」（`<w:tblStylePr w:type="firstRow"><w:tcPr><w:shd w:fill="DEEAF6"/></w:tcPr></w:tblStylePr>`）目前被 silent drop、render 出來標題列無背景填色。

**Hypothesis A（功能正確性）**：補完 tcPr 後、firstRow / lastCol / wholeTable 等 conditional 對應的 cell shading + vAlign 能正確 mutate 到 `cell.props.shading` / `cell.props.vAlign`、且 explicit `cell.props` 優先（不被覆蓋）。

**Hypothesis B（VR 穩定性）**：42 fixture 多為政府工程文件、表格樣式以 explicit `<w:tcPr><w:shd/>` 為主、少用 conditional shading；預期 byte-identical（紀律 #1.a 第 8 次連續驗證機會）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B cluster 4 第 2 個：「131 | Phase 4 Style | 4.2 tblStylePr 15 種條件完整」
- 規畫書 §Phase 4.2 列：「`<w:tblStylePr>` 15 種條件、字元樣式 + 段落樣式的合併順序、樣式連結」
- **重要 scope 釐清**：13 種 conditional type（`wholeTable`/`firstRow`/`lastRow`/`firstCol`/`lastCol`/`band1Horz`/`band2Horz`/`band1Vert`/`band2Vert`/`nwCell`/`neCell`/`swCell`/`seCell`）**Sprint 1-130 已全部支援 pProps/rProps 傳遞**（TableStyleApplicator.ts 完整實作 + 既有 16 個 baseline test 鎖定）；本 sprint 補的是「跨 type 都漏掉的 **cell-level tcProps**」、不是「補新 type」
- 本 sprint scope = **w:tcPr 內的 shading + vAlign 兩個最常用屬性傳遞**
- 不在 scope（留未來 sprint）：
  - `w:tcBorders`（需與 BorderConflictResolver 互動、複雜度高）
  - `w:tcMar`（margins）、`w:noWrap`、`w:textDirection`（罕見於條件樣式）
  - `w:trPr`（row-level 條件）— 影響 `row.props.isHeader`、罕見
  - `w:tblPr`（table-level 條件、只 wholeTable 有意義）— 影響 `table.props.borders` 等、複雜
  - 樣式連結（`<w:link>`）— defer 到 Phase 6 export 時再評估
- PR-size：types +30 行 / StyleResolver +50 行 / TableStyleApplicator +60 行 / test +180 行（9+4 新 test）/ 1 audit / 1 bundle rebuild

### 2. 修法

#### 2.1 types.ts：新型別 `TableConditionalCellProps`

```ts
/** Sprint 131：tblStylePr 的 w:tcPr 內可套用的 cell-level 條件 props 子集 */
export interface TableConditionalCellProps {
  shading?: { fill?: HexColor; color?: HexColor; pattern?: string };
  vAlign?: 'top' | 'center' | 'bottom';
}
```

`StyleEntry.conditional` Map 值擴充：

```ts
conditional?: Map<
  TableConditionalType,
  {
    pProps?: ParagraphProps;
    rProps?: RunProps;
    cProps?: TableConditionalCellProps;  // ← 新增
  }
>;
```

#### 2.2 StyleResolver.ts：parseConditionalTcPr helper

新 helper 在 `<w:tblStylePr>` 處理路徑加 `directChild(child, 'w:tcPr')` 解析：

```ts
function parseConditionalTcPr(tcPr: Element): TableConditionalCellProps | undefined {
  const out: TableConditionalCellProps = {};

  const shdEl = directChild(tcPr, 'w:shd');
  if (shdEl) {
    // 從 w:fill / w:color / w:val 三屬性各自抽取（缺則不掛 key）
    ...
  }

  const vAlignEl = directChild(tcPr, 'w:vAlign');
  if (vAlignEl) {
    const v = vAlignEl.getAttribute('w:val');
    if (v === 'top' || v === 'center' || v === 'bottom') out.vAlign = v;
    // 無效值（如 'baseline'）silent drop、out 仍可能全空
  }

  // 空集合不掛 key（紀律 #21 候選驗證第 3 次機會）
  if (!out.shading && !out.vAlign) return undefined;
  return out;
}
```

flattenStyle 步驟把 `entry.cPr` (raw) → `conv.cProps` (AST 型) 直接 copy（不參與 basedOn 鏈展開、與既有 conditional 處理一致）。

#### 2.3 TableStyleApplicator.ts：cProps 累積 + 寫回 cell.props

`applyTableStyle` 主迴圈內新增：

```ts
// 累積條件樣式的 cell-level props（與 effP / effR 平行）
let effC: TableConditionalCellProps = {};

const apply = (entry) => {
  ...
  if (entry.cProps) effC = mergeCellConditionalProps(effC, entry.cProps);
};

// ... 13 條條件套用後 ...

// 7a：把 effective cell-level props 寫回 cell.props（explicit 優先）
if (effC.shading || effC.vAlign) {
  applyConditionalCellProps(cell, effC);
}
```

新 helper：

```ts
function mergeCellConditionalProps(base, overlay) {
  // shading: per-key 淺合併（fill/color/pattern 各自獨立）
  // vAlign: atomic 整體覆蓋
}

function applyConditionalCellProps(cell, effC) {
  if (effC.shading && cell.props.shading === undefined) cell.props.shading = { ...effC.shading };
  if (effC.vAlign !== undefined && cell.props.vAlign === undefined) cell.props.vAlign = effC.vAlign;
}
```

**`cell.props.shading === undefined` 才補**：與 paragraph/run props 一致的「explicit 優先」語意。差別是 shading 是 atomic（不做 per-key 合併、避免半填 conditional 半填 explicit）；TableParser 對 `<w:shd w:val="clear"/>` 已會 set `shading={pattern:'clear'}`、會卡掉 conditional，但這在實務 fixture 罕見、accept trade-off。

#### 2.4 mergeCellConditionalProps 設計

```
mergeCellConditionalProps:
  out.shading = overlay.shading
    ? { ...base.shading, ...overlay.shading }  // shading 巢狀淺合併
    : base.shading                              // 無 overlay 保留 base
  out.vAlign  = overlay.vAlign ?? base.vAlign  // vAlign atomic 覆蓋
```

設計理由：shading 的 fill / color / pattern 三個 sub-key 在 OOXML 允許部分指定（如 wholeTable 只 set fill、firstRow 補 color）；保留巢狀合併符合 Word 行為。vAlign 無 sub-key、整體覆蓋即可。

### 3. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1057 passed + 1 skipped**（從 1044+1 起、+13 新 test：9 TableStyleApplicator + 4 StyleResolver）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 8 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（pre-existing warning 同前、bundle rebuild 26.0s）|
| L4 Odoo backend | **跳過**（無 backend / model / ACL 變動）|

### 4. Unit test 設計（13 個新 test）

#### TableStyleApplicator.test.ts 新增 9 個（describe: 'Sprint 131 cell-level conditional props'）

| Test | 鎖定行為 |
|---|---|
| firstRow tcPr shading 套用第一列 cell 背景色 | 經典「標題列背景填色」場景 |
| lastCol tcPr vAlign 套用最後一欄 cell 垂直對齊 | vAlign 條件樣式 |
| explicit cell shading 不被 conditional 覆蓋 | atomic explicit 優先（與 pProps/rProps 一致） |
| wholeTable + firstRow cProps 後者覆蓋（merge 順序）| 套用順序：wholeTable → firstRow，後者贏 |
| shading 巢狀 per-key 合併（fill + color 共存）| shading 三 sub-key 各自獨立合併 |
| nwCell cProps：角落 cell 套用 | corner cell 角落特殊規則 |
| tblLook firstRow=false 時 firstRow cProps 不套用 | tblLook gating 與 pProps/rProps 一致 |
| isContinuation cell 不套用 cProps shading | vMerge 連續 cell 不渲染、跳過 |
| cProps 與 pProps/rProps 三者各自獨立套用 | 三軌完整整合驗證 |

#### StyleResolver.test.ts 新增 4 個（describe: 'Sprint 131 tblStylePr/tcPr 解析'）

| Test | 鎖定行為 |
|---|---|
| tblStylePr/firstRow/tcPr/shd → conditional.cProps.shading | parser 路徑、fill + pattern 都進 |
| tblStylePr/lastCol/tcPr/vAlign → conditional.cProps.vAlign | parser 路徑、vAlign 進 |
| tcPr 全空（只有 tcBorders）不掛 cProps key | **紀律 #21 候選第 3 次驗證**：空集合不掛 |
| w:vAlign 無效值 'baseline' 不掛 vAlign key | OOXML 允許值 enum 嚴格檢查 |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | +30 行（TableConditionalCellProps interface + StyleEntry.conditional 擴 cProps）| API 擴充 |
| `static/src/core/ooxml/styles/StyleResolver.ts` | +50 行（RawStyleEntry.conditional 擴 cPr / parseConditionalTcPr helper / flattenStyle 補 cProps 傳遞）| parser 補完 |
| `static/src/core/ooxml/styles/TableStyleApplicator.ts` | +60 行 / 修改 4 行（apply 函式擴 cProps / effC 累積 / applyConditionalCellProps + mergeCellConditionalProps helper）| applicator 補完 |
| `tests/unit/TableStyleApplicator.test.ts` | +180 行 / 9 新 test + makeStyleEntry helper 型別擴充 | 鎖定 cell-level conditional 行為 |
| `tests/unit/StyleResolver.test.ts` | +60 行 / 4 新 test | 鎖定 parser tcPr 路徑 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、byte-identical | VR confirm |
| `docs/sprint131_tblstylepr_tcpr_propagation.md` | 本 audit doc | 紀錄補完設計 |
| `docs/autonomous_roadmap.md` | Sprint 131 ✅ + 進度表 | cluster 4 推進 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §0.2 Phase 4 81% → 82% + §Phase 4.2 註記 | 同步 |

### Test 數變動

- Sprint 130 結尾：vitest 1044 + 1 skipped
- Sprint 131 結尾：vitest **1057 + 1 skipped**（+13）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 130 結尾：mean 0.073191（byte-identical）
- Sprint 131 結尾：mean **0.073191**（byte-identical、**第 8 次連續** 121→126→130→131）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style Theme：81% → **82%**（+1%、4.2 tblStylePr cell-level props 補完最常用 2 屬性、剩 tcBorders/trPr/tblPr 條件樣式 defer）

---

## Root cause

**為什麼 Sprint 1-130 沒補 tcPr 傳遞**：

1. Sprint 19 落地 `tblStylePr` 條件樣式初版時、焦點在 `pPr / rPr` 主路徑（字體、對齊、粗體斜體）；`tcPr` 列為 future work、註解未顯式留 TODO
2. 既有 16 個 TableStyleApplicator baseline test 鎖定 pProps/rProps 行為、無 cProps tests 揭示 gap
3. fixture 多用 explicit `<w:tcPr><w:shd/>` 直接寫在 `<w:tc>` 內（已被 TableParser 主路徑 set 到 `cell.props.shading`）、conditional 路徑被繞過、VR 無 signal 揭示 gap
4. Sprint 130 切到 Phase 4 系統收口、第一次系統審視 tblStylePr 全部 sub-element 才注意到此漏

**為什麼 VR byte-identical**：

42 fixture 表格樣式用 explicit shading 為主（直接在 `<w:tc><w:tcPr><w:shd/>` 寫死）、少用「定義 table style + conditional firstRow shading」的進階模式。Word 桌面版產生的政府工程文件偏向 explicit 寫法、避免 style override 不確定性。

未來若 fixture 含 user 自訂 table style with conditional shading（如稅單、考試成績單），VR 會顯示明顯改善（標題列從無背景 → 有背景）。

---

## 紀律

### 紀律 #1.a 第 8 次連續驗證（Sprint 131）

連續 8 sprint code change 都跑全 VR 並維持 byte-identical：

| Sprint | 改動 | VR |
|---|---|---|
| 121 | TableParser trHeight defensive | 0.073191 |
| 122 | ParagraphParser OLE/pict fallback | 0.073191 |
| 123 | ParagraphParser field code 完整覆蓋 | 0.073191 |
| 124 | dom.ts effectiveChildren sdt unwrap | 0.073191 |
| 125 | ParagraphParser bookmark capture（首次真實 trigger）| 0.073191 |
| 126 | parseHyperlinkInfo 擴 3 屬性 | 0.073191 |
| 130 | ThemeResolver HSL luminance 升級 | 0.073191 |
| **131** | **StyleResolver/TableStyleApplicator tcPr 傳遞** | **0.073191** |

紀律 #1.a 穩固、8 次連續 byte-identical、覆蓋 OOXML parser / dom utility / style resolver / table applicator 四類修改點。

### 紀律 #21 候選跨 sprint 驗證進展 2 → 3（升正式）

紀律 #21 候選「optional 欄位空集合不掛 key、避免 AST diff noise + 保 cache key 穩定」：

- Sprint 125 揭示（ParagraphNode.bookmarks 空陣列不掛 key）
- Sprint 126 套用（HyperlinkInfo `tgtFrame / history / docLocation` 有值才掛、history 用 `!== undefined` 偵測 false）
- **Sprint 131 套用**（parseConditionalTcPr 全空集合回 undefined、entry.cPr undefined 不掛、makeRow entry 缺值整層不存）

跨 3 sprint 驗證完成、**升正式紀律 #21**：

> **紀律 #21**（Sprint 131 升正式）：optional 欄位空集合不掛 key。
> **Why**：避免 AST diff noise、保 cache key 穩定（Sprint 51-58 cache 五連發教訓）
> **How to apply**：parser 函式回 optional 欄位前先檢查是否「真的有值」；空陣列、空 Map、無 attribute 命中、無 sub-element 都回 undefined 而非 `[]` / `new Map()` / `{}`；對 boolean false 值用 `!== undefined` 而非 truthy 檢測（避免 false 被誤丟）

紀律 19 → **20 條**。

### 紀律 #18 持續

PR-size 守住：types +30 / StyleResolver +50 / TableStyleApplicator +60 / 2 個 test file +240 / 1 audit / 1 bundle。明示 5 項不在 scope（tcBorders / tcMar / noWrap / textDirection / trPr / tblPr 條件樣式 / 樣式連結）。

### 紀律 #4 應用（Sprint 131）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 131 揭示：

1. **「Phase 4.2 = 15 種條件」是誤導性描述**：實際 13 種 conditional type Sprint 1-130 早已支援 pProps/rProps；真正的 gap 是「跨 type 都漏的 cell-level tcPr 傳遞」、非「補新 type」
2. **TableStyleApplicator 既有 16 baseline test 不夠覆蓋率**：完全沒鎖定 `cell.props.shading` mutation；TableParser test 也只測 explicit shading；揭示「conditional × cell-level props」是測試矩陣盲區
3. **VR 不揭示 conditional style gap**：fixture 偏 explicit 寫法、規避了 conditional 路徑、整個 Sprint 1-130 沒人發現 bug；證明「VR mean 穩定」≠「Phase 完成度高」，後者要靠 spec compliance audit（紀律 #4 強化）

### 紀律 #14 應用（Sprint 131）

> Docs 同步：CONTRIBUTING.md / glossary 紀律列表需 catch-up

紀律 #21 升正式、規畫書 §6.5 紀律表 18 → 19 條（含 Sprint 130 的 #1.a 第 7 次→8 次連續）、本 audit doc 完整記錄。CONTRIBUTING.md / glossary 同步留 Sprint 132+ 再 catch-up（PR-size 控制）。

---

## 後續

### Sprint 132（cluster 4 收口或進 cluster 5）

階段 B cluster 4 (130-131) 已完成（Phase 4.1 + 4.2 大部分）。下一個方向：

**選項 A：cluster 5 Phase 4.3 中文編號格式**（規畫書原排 Sprint 132、autonomous_roadmap.md 階段 B 行 5）：
- `chineseCounting`（一二三四五）/ `ideographDigital`（壹貳參肆伍）/ `japaneseCounting`（日文編號）
- 對 ChienYi 政府工程文件「第一章、第二項」等中文編號直接相關
- PR-size 中等：NumberingResolver / lvlText 解析 +50~80 行、unit test +40~60 行

**選項 B：Phase 4.2 收口剩餘 tcBorders 條件樣式**（本 sprint defer 的部分）：
- 與 BorderConflictResolver 互動、複雜度較高、PR-size 大
- 對 VR 影響中等（仍多為 explicit borders）

**autonomous 決策**：走選項 A（Sprint 132 = Phase 4.3 中文編號格式）；理由：(1) ChienYi 監造文件高度依賴中文編號、實務影響大、(2) cluster 4 兩 sprint scope 已適中、收尾；(3) tcBorders 留給專門 sprint 評估 BorderConflictResolver 整合風險。

### Sprint 131+ 候選

- **tcBorders 條件樣式**：需 BorderConflictResolver 整合、defer 專門 sprint
- **trPr 條件樣式**（`row.props.height` / `isHeader` 受 conditional 影響）：罕見、defer
- **tblPr 條件樣式**（只 wholeTable 有意義、影響 `table.props.borders`）：罕見、defer
- **樣式連結 `<w:link>`**：char↔para style 配對、屬 Phase 6 export 需求、defer

---

## Sprint 131 結尾累積指標

- vitest **1057 passed + 1 skipped**（+13）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 8 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style Theme 81% → **82%**
- 21 ADR / 紀律 **20 條**（+#21 升正式）+ 6 子 + 2 候選（#22 候選持平 2/3、#20 候選持平 1/3）
- Sprint audit doc 數 130 → **131**
- 階段 B cluster 4 (130-131) **完成**、進入 cluster 5 (132) Phase 4.3 中文編號

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/ast/types.ts  (+30 行 TableConditionalCellProps + StyleEntry.conditional 擴 cProps)
M  addons/dobtor_doc_editor/static/src/core/ooxml/styles/StyleResolver.ts  (+50 行 parseConditionalTcPr + RawStyleEntry/flattenStyle cPr 傳遞)
M  addons/dobtor_doc_editor/static/src/core/ooxml/styles/TableStyleApplicator.ts  (+60 行 effC 累積 + applyConditionalCellProps + mergeCellConditionalProps)
M  addons/dobtor_doc_editor/tests/unit/TableStyleApplicator.test.ts  (+180 行 / 9 新 test)
M  addons/dobtor_doc_editor/tests/unit/StyleResolver.test.ts  (+60 行 / 4 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint131_tblstylepr_tcpr_propagation.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 131 ✅ + cluster 4 完成 + 紀律 #21 升正式註記)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 4 81→82% + 紀律表 18→19 條)
```

無 model / view / ACL / rule / controller / backend 變動。階段 B cluster 4 完成、紀律 #21 升正式（19 → 20 條）。

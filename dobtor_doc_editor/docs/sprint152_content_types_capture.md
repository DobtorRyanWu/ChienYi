# Sprint 152 — [Content_Types].xml capture-only(PackageReader internal expose)

**落地 / 2026-05-19**
**性質**:Phase 1 capture-only、PackageReader 內部 ParsedContentTypes 暴露至 DocumentNode
**範圍**:[Content_Types].xml(OPC §3.2、OOXML §10.2.2 強制 manifest)

---

## Hypothesis

Sprint 151 retro 已 explicit「autonomous-friendly §11.2 backlog 大幅消化、剩餘候選不適 capture-only」、但 user 指示「繼續」。重新掃描:

| 候選 | 評估 |
|---|---|
| theme1.xml fmtScheme / objectDefaults / extraClrSchemeLst | 41/42 覆蓋、但內部結構極複雜(fillStyleLst × N + gradFill / blipFill / pattFill) → 不適 capture-only |
| styles.xml docDefaults | ✅ StyleResolver 已 wire-up(rPrDefault + pPrDefault)|
| styles.xml latentStyles | 41/42 覆蓋、~376 lsdException entries、scope 中 |
| **[Content_Types].xml** | **42/42 覆蓋(spec 強制)、PackageReader 已 parse 但未暴露、scope 小** |

→ Sprint 152 = **[Content_Types].xml capture-only**(PackageReader internal `ParsedContentTypes` 暴露至 OoxmlPackage + DocumentNode)。

**假設**:
1. PackageReader 已內部 `parseContentTypes` + `resolveContentType`(無新 parser code 需寫、只 expose internal)
2. capture-only 不破 VR baseline、可延長 byte-identical streak 至第 22 連
3. 紀律 #18 scope-down 嚴守:只暴露 readonly Map、不解析 MIME 語意

**為何需要**:Phase 6 docx export 對稱性必備(export 端需 verbatim 重建 [Content_Types].xml、否則 Word 拒讀)。

---

## Method

### 9-step archetype 變體(Sprint 145-151 模式延伸)

**Step 1 - probe**:
- 42/42 fixture 有 [Content_Types].xml(spec 強制、不可缺)
- 結構:`<Default Extension ContentType>` × 2-3 + `<Override PartName ContentType>` × 10-15
- PackageReader L72-79 已 `parseContentTypes(strFromU8(ctRaw))`、結果為 internal `ParsedContentTypes`
- 結果未暴露到 `OoxmlPackage` interface(L41-54)、也未到 DocumentNode

**Step 2 - PackageReader 暴露 internal table** +18 行(`PackageReader.ts`):
```ts
export interface PackageContentTypes {
  defaults: ReadonlyMap<string, string>;
  overrides: ReadonlyMap<string, string>;
}
export interface OoxmlPackage {
  // ... existing fields
  contentTypes: PackageContentTypes;   // Sprint 152 新
}
```

`makePackage()` 簽名擴 + 直接複用 internal `ParsedContentTypes`(Map 不複製、readonly 形式對外保證)。

**Step 3 - types.ts** +25 行:
- `DocContentTypes` interface(等價於 `PackageContentTypes`、avoid 外部 import package/ 子目錄)
- `DocumentNode.contentTypes` 新欄位

**Step 4 - OoxmlParser orchestrator** +5 行:
- Step 8.3 `const contentTypes = pkg.contentTypes`(無新 parse 工作、純 forward)
- DocumentNode 構造加 `contentTypes`

**Step 5 - 5 個既有 DocumentNode constructor patch**(+5 行):
- DocumentParser.ts(makeEmpty 用 `{ defaults: new Map(), overrides: new Map() }`)
- 4 個 test fixture 同模式

**Step 6 - 新 unit test** `tests/unit/PackageContentTypes.test.ts` +118 行 / 14 test:
- 6 組:defaults / overrides / part 一致性 / 跨 fixture 通用性 / capture-only 性質

**Step 7 - 三層 SOP**:見 Verification

**Step 8 - 三檔文件**:
- `docs/sprint152_content_types_capture.md`(本)
- `docs/autonomous_roadmap.md`(+1 列)
- 規畫書標頭

**Step 9 - commit**「Sprint 152: [Content_Types].xml capture-only Parser」

### 設計決策

**為何不新增 `ContentTypesParser.ts`**:
- PackageReader 已 internal `parseContentTypes` + `resolveContentType`(L117-149)
- 重寫 parser 違反 DRY、且 PackageReader L73-77 已對「缺 [Content_Types].xml」throw
- 直接 expose internal table 是最自然路徑、無 scope 重疊

**ReadonlyMap 對外保證(TypeScript 介面層)**:
- runtime 仍是 Map 實例、size / get / keys / values / entries / forEach / has 全可用
- 對外不可變動(類型系統強制、不需 Object.freeze)、紀律 #18 不過度防禦

**為何不在本 sprint 寫 ContentTypes-to-MIME 反向 lookup**:
- 紀律 #18 scope-down:留 Phase 6 docx export 階段、不為「completeness 而 over-design」
- `PackagePart.contentType` 已存在於每個 part、forward lookup 已可用
- 反向 lookup(MIME → part list)只在 export validate 階段需要

**為何不解析 MIME 語意 (e.g. wordprocessingml.document.main)**:
- MIME 字串為 OOXML 規格 contract(WordprocessingML / SpreadsheetML / PresentationML)
- 不展開語意 = layout/render 端維持「MIME-agnostic」、未來支援 .xlsx / .pptx 不需改 capture 層
- 紀律 #18 scope-down 維度光譜應用

### 與 Sprint 150/151 對比

| 維度 | Sprint 150 (app.xml) | Sprint 151 (custom.xml) | **Sprint 152 ([Content_Types].xml)** |
|---|---|---|---|
| 覆蓋率 | 42/42(100%)| 25/42(60%)| **42/42(100%、spec 強制)** |
| 新 Parser code | +189 行 | +179 行 | **0 行(復用 PackageReader internal)** |
| 結構 | flat element bag | dynamic property bag | **2 個 Map(Default × N + Override × M)** |
| 紀律 #18 | enum 不展開 | variant 不展開內部 | **MIME 語意不展開、反向 lookup 留 export** |
| Test | 20 | 29 | **14** |

Sprint 152 是「最薄」的 capture-only sprint — 沒有新 parser、只暴露已存在 internal table。

---

## Verification

### L1 Vitest 全套

```
Test Files  77 passed | 1 skipped (78)
     Tests  1312 passed | 1 skipped (1313)
  Duration  157.51s
```

- 1298 → **1312 passed**(+14、本 sprint)
- 0 regression(既有 1298 全綠)

### L2 Visual Regression v14

```
[v14] rendered=42/42  bootFailed=0  comparedPages=126  failedPages=0
mean = 0.073191
```

- VR mean **0.073191**(byte-identical 第 **22** 次連續)
- 0 fail / 0 boot fail / 0 missing golden

### L3 spot check

- TypeScript build `npm run build:all`(rollup × 2)pass
- bundle byte-identical rebuild

### L4 Odoo backend test

跳過(本 sprint 0 Python 端變動)。

### 防禦覆蓋

| 防禦條件 | 結果 |
|---|---|
| 缺 [Content_Types].xml | PackageReader throw(spec 強制、已 Sprint 0 處理)|
| 壞 [Content_Types].xml XML | PackageReader throw(parseXml 已 Sprint 0 處理)|
| Default Extension 大小寫 | parseContentTypes 強制小寫 key(L125)|
| Override PartName 含前導 "/" | parseContentTypes 強制去除(L133)|
| Override 優先於 Default | resolveContentType 已 Sprint 0 處理(L141-149)|

防禦邏輯全部已存在於 PackageReader、本 sprint 不需新增 — 紀律 #18 不重複實作。

---

## Discipline

### 紀律 #1.a 第 22 連 byte-identical

> parser / layout 改完跑全 VR

連續第 22 個 sprint VR 不破 baseline、Sprint 145-152 八連 capture-only 全部維持。

### 紀律 #14 模組化 + DRY

> 集中索引、避免重複實作

PackageReader 已 internal parse、本 sprint 直接暴露(無新 Parser code)、避免 Sprint 150/151 的「新 parser 新模組」模式重複造輪子。

### 紀律 #18 守住 + scope-down 多維度

PR-size:`+18 行 PackageReader + 25 行 types + 5 行 OoxmlParser + 5 行 patch + 118 行 test`(最薄一 sprint、紀律 #18 嚴格守)。

scope-down 維度應用:
- 不寫新 Parser(復用 internal)
- 不解析 MIME 語意(留 export)
- 不寫反向 lookup(留 export)
- 不深拷貝 Map(ReadonlyMap 介面層保證)

### 紀律 #22 第 16 次正式應用

> 不確定 mental model 先 probe sprint

probe 揭示 PackageReader L72-79 已 internal `parseContentTypes` + 結果為 `ParsedContentTypes` 而非外部介面 → 直接 expose、不寫新 parser。

### 紀律 #1.b 候選 v2 第 15 次正面驗證

連續第 7 個 capture-only sprint(145-152、跳過 149 retro)無翻車、紀律 #1.b 對「capture-only」+「internal expose」變體類型再次穩定。

---

## Result

### Sprint 152 結尾累積指標

- vitest **1312 passed + 1 skipped**(+14)
- VR mean **0.073191** / failed 0 / compared 126(**第 22 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML **89% → 89.5%**(content_types capture、無大進度因 PackageReader 已 internal parse)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 151 → **152**

### Phase 1 capture-only **八連** cluster(Sprint 145-152、跳過 149 retro)累積

| Sprint | Part | New parser code | Test | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes + endnotes | +135 | +12 | 80% → 82% |
| 146 | settings | +187 | +27 | 82% → 84% |
| 147 | fontTable | +150 | +20 | 84% → 86% |
| 148 | webSettings | +95 | +14 | 86% → 87% |
| 150 | app.xml | +189 | +20 | 87% → 88% |
| 151 | custom.xml | +179 | +29 | 88% → 89% |
| **152** | **[Content_Types].xml** | **+0 (expose)** | **+14** | **89% → 89.5%** |
| **合計** | **8 parts** | **+935** | **+136** | **+9.5pp** |

七連 → 八連、VR 第 21 → 22 連、Phase 1 +9pp → +9.5pp。

---

## 後續

### Sprint 153 候選(autonomous 評估)

| 候選 | 預期 | 理由 |
|---|---|---|
| **F-1. session 自然停止 + 總結** | 0 | 八連已超越「autonomous 邊界」、§11.2 backlog 真的近耗盡(剩 latentStyles 與 stylesWithEffects 不適合)|
| E-15. styles.xml latentStyles capture-only | 1 sprint | 41/42 覆蓋、~376 lsdException entries、結構單純但 ROI 低(export 才用)|
| E-16. Sprint 145-152 cluster retro(短週期)| 1 sprint docs | 8 sprint pattern 已成熟、可寫精煉版 retro |
| E-17. 進入 wire-up 階段 | 1-2 sprint | 會破 VR baseline、走 Strategy C(紀律 #1.b)|

**autonomous 推薦 F-1**(session 自然停止):
- 八連 capture-only 已是 cluster 成熟邊緣、繼續延伸 ROI 下降
- 剩餘 backlog 不是「需 user GO」就是「ROI 過低不適」
- 留 session 給 user 看成果、決定 wire-up 或 retro 方向

如 user 繼續 → 推薦 E-15(latentStyles、簡單延伸)或 E-16(retro)。

### user 介入點(維持清單)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference docx fixture | 觸發 Sprint 145 wire-up 升級 |
| Sprint 153+ wire-up 階段 GO | 接受首次破 baseline 風險(Strategy C 模式)|
| Phase 6 docx export | customProps / appProps / contentTypes 對稱性鏈接設計 |

---

## File-level summary

```
M  static/src/core/ooxml/package/PackageReader.ts  (+18 行 PackageContentTypes interface + makePackage 簽名)
M  static/src/core/ooxml/ast/types.ts  (+25 行 DocContentTypes + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+5 行 Step 8.3 forward)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/PackageContentTypes.test.ts  (+118 行 / 14 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint152_content_types_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 152 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 89.5%)
```

**Phase 1 capture-only 八連 cluster(145-152)延續**、+9.5pp Phase 1 / +136 test / **第 22 連 byte-identical**。本 sprint 是「最薄」capture-only(0 新 parser code、復用 PackageReader internal)、紀律 #18 + #14 DRY 雙重應用範例。下個 sprint = session 自然停止點。

# Sprint 151 — docProps/custom.xml capture-only(autonomous-friendly §11.2 backlog 延續)

**落地 / 2026-05-19**
**性質**:Phase 1 capture-only、Sprint 150 doc-props 子目錄延伸
**範圍**:docProps/custom.xml(OOXML §22.3 custom-properties)、variant 型別 discriminated union

---

## Hypothesis

Sprint 150 §後續推薦 = E-10 docProps/custom.xml capture-only:
- 25/42 fixture 有 custom.xml(WPS / Grammarly 等 SaaS app stamp)
- 17 fixture 無此 part(純 Word 預設、無自訂屬性)
- 同 doc-props 子目錄延伸自然(紀律 #14 模組化一致性)
- 結構單純(property bag、name/value/fmtid/pid)

**假設**:
1. variant 型別在 fixture 只見 vt:lpwstr(25 entries)、但 OOXML §22.4 spec 定義 ~20 種 variant、需設計擴充性
2. capture-only 不會破 VR baseline、可延長 byte-identical streak 至第 21 連
3. 紀律 #18 scope-down:只實作前 5 個常見 variant 類別(string / int / bool / real / filetime)、其他降級 unknown

---

## Method

### 9-step archetype 應用(沿用 Sprint 150)

**Step 1 - probe**:
- Fixture 覆蓋率:25/42(60%、僅次於 Sprint 150 的 100%)
- variant 型別統計:vt:lpwstr × 25(100% of entries)、其他 variant 0 出現
- property name 統計:KSOProductBuildVer × 24 + GrammarlyDocumentId × 14 = 38 entries total
- 結構:`<Properties> <property fmtid pid name> <vt:variant>value</vt:variant> </property> </Properties>`

**Step 2 - 新檔** `static/src/core/ooxml/doc-props/CustomPropsParser.ts` +179 行:
- `parseCustomProps(pkg)` + `parseCustomPropsXml(xml)`
- variant discriminated parsing(switch by localName)
- 紀律 #18 scope-down:5 個常見 variant 類別 + unknown fallback

**Step 3 - types.ts** +37 行:
- `CustomPropertyValue` discriminated union(6 kinds)
- `DocPropsCustom = Map<string, CustomPropertyValue>` 別名
- DocumentNode 1 新欄位 `customProps: DocPropsCustom`

**Step 4 - OoxmlParser orchestrator** +6 行:
- `import { parseCustomProps }`
- Step 8.2 `const customProps = parseCustomProps(pkg)`
- DocumentNode constructor 加 customProps

**Step 5 - 5 個既有 DocumentNode constructor patch**(+5 行):
- DocumentParser.ts(makeEmpty fallback)
- 4 個 test fixture(AstCache / IdbAstCache / ParagraphStyleMerger / ToCanvasEditor)

**Step 6 - 新 unit test** `tests/unit/CustomPropsParser.test.ts` +189 行 / 29 test:
- 字串 variant × 5 / 整數 variant × 4 / 布林 variant × 4 / 浮點 variant × 2 /
  filetime variant × 3 / 未知 variant 降級 × 2 / 真實 fixture × 1 / 防禦邊界 × 8

**Step 7 - 三層 SOP**:見下節 Verification

**Step 8 - 三檔文件**:
- `docs/sprint151_customprops_capture.md`(本 audit doc)
- `docs/autonomous_roadmap.md`(+1 列)
- `dobtor_doc_editor_高保真匯入開發規劃.md`(標頭最後更新)

**Step 9 - commit**「Sprint 151: docProps/custom.xml capture-only Parser」

### 設計決策

**variant 型別 discriminated union(scope-down 紀律 #18)**:
- 觀察:42 fixture 只有 vt:lpwstr 出現、但 spec 允許 ~20 variant
- 解決方案:5 個常見 variant 類別 + unknown 降級保留 raw
- 對未來 wire-up 友善:caller 用 `value.kind` switch、TypeScript 型別狹窄化
- 對未來擴充友善:加新 variant 只在 switch 加 case、不破 existing test

| variant | 處理 |
|---|---|
| vt:lpwstr / vt:lpstr / vt:bstr | `kind: 'string'` |
| vt:i4 / vt:i8 / vt:int / vt:uint | `kind: 'int'` |
| vt:bool | `kind: 'bool'`(寬鬆 true/false/1/0)|
| vt:r4 / vt:r8 / vt:decimal | `kind: 'real'` |
| vt:filetime / vt:date | `kind: 'filetime'`(保留 ISO 字串、不轉 Date)|
| 其他(vt:vector / vt:cy 等)| `kind: 'unknown'`(保留 raw textContent)|

**紀律 #18 scope-down 維度**:
- ❌ fmtid / pid 不保留(name 已足夠作為 key)
- ❌ filetime 不轉 Date(避免 timezone 副作用、留 wire-up 階段)
- ❌ vt:vector 內部結構不展開(留未來 wire-up 階段)

**紀律 #21 應用**:
- property 無 name → 跳過(不掛 key)
- property name 為空字串 → 跳過
- property 無 vt:* 子元素 → 跳過
- 整數 / 浮點 / 布林 parse 失敗 → 跳過該 property
- (字串 variant 空字串合法、允許顯式空值)

**重複 name 處理**:
- 理論上不應發生、但若發生則後者覆蓋前者(Map.set 行為)
- 不 throw、不警告(紀律 #18 不為邊界 case 過度設計)

### 與 Sprint 150 對比

| 維度 | Sprint 150 (app.xml) | Sprint 151 (custom.xml) |
|---|---|---|
| 覆蓋率 | 42/42(100%)| 25/42(60%)|
| 結構 | flat element bag(17 elements 已知)| dynamic property bag(name/variant 任意)|
| 型別處理 | optional flat fields(15 typed + 2 string variant)| discriminated union(6 kinds + unknown)|
| 紀律 #18 | scope-down enum 名稱不展開、罕見 elements 不 capture | scope-down 至 5 常見 variant + unknown |
| 紀律 #21 | 17 fields 全空集合不掛 key | property 級不掛 key + variant 級失敗跳過 |
| Test | 20 個 | 29 個 |

---

## Verification

### L1 Vitest 全套

```
Test Files  76 passed | 1 skipped (77)
     Tests  1298 passed | 1 skipped (1299)
  Duration  160.23s
```

- 1269 → **1298 passed**(+29、本 sprint 新增 29 test)
- 0 regression(既有 1269 全綠)

### L2 Visual Regression v14

```
[v14] rendered=42/42  bootFailed=0  comparedPages=126  failedPages=0
mean = 0.073191
```

- VR mean **0.073191**(byte-identical 第 **21** 次連續)
- 0 fail / 0 boot fail / 0 missing golden
- 所有 42 fixture × 126 pages 與 Sprint 65 baseline 完全一致

### L3 spot check

- TypeScript build `npm run build:all`(rollup × 2)pass — 既有循環依賴警告無關
- `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` rebuild byte-identical
- `tools/dist/visual_regression_pipeline.iife.js` rebuild byte-identical

### L4 Odoo backend test

跳過(本 sprint 0 Python 端變動)。

### 防禦覆蓋

| 防禦條件 | 結果 |
|---|---|
| undefined input | 空 Map |
| 空字串 input | 空 Map |
| 壞 XML(unclosed tag)| 空 Map(不 throw)|
| 空 Properties 骨架 | 空 Map |
| property 無 name 屬性 | 跳過該 property |
| property name 為空字串 | 跳過 |
| property 無 vt:* 子元素 | 跳過 |
| 重複 name | 後者覆蓋前者(Map.set 行為)|
| 非數字字串於 vt:i4 | 跳過該 property |
| 小數於 vt:i4 (嚴格整數) | 跳過 |
| NaN/Infinity 於 vt:r8 | 跳過 |
| 不合法布林(yes/no) | 跳過 |
| 未知 variant(vt:vector 等)| `kind: 'unknown'` + raw 保留 |

---

## Discipline

### 紀律 #1.a 第 21 連 byte-identical

> parser / layout 改完跑全 VR

連續第 21 個 sprint VR 不破 baseline、Sprint 145-151 七連 capture-only 全部維持 byte-identical。

### 紀律 #21 應用(第 11 次)

> optional 欄位空集合不掛 key

property-level + variant-level 雙層應用:
- property 無 name / name 為空 / 無子元素 → 不掛 key
- variant parse 失敗 → 跳過該 property

### 紀律 #22 第 15 次正式應用

> 不確定 mental model 先 probe sprint

本 sprint 開工前先做 variant 型別統計 probe:
- fixture 全部只用 vt:lpwstr → 揭示「實際使用範圍小、spec 範圍大」mental model
- 確認 scope-down 策略(5 常見 + 1 unknown 降級)合理

### 紀律 #18 守住 + scope-down 多維度

PR-size:`+179 行 production / +189 行 test / +5 行 patch`(同 Sprint 150 範圍)。

scope-down 維度光譜應用:
- 不保留 fmtid / pid(metadata level)
- 不轉 Date 物件(value level)
- 不展開 vt:vector 內部(variant level)
- 不為重複 name throw(error handling level)

→ Sprint 148 webSettings.xml 的 scope-down 模式在 Sprint 151 多維度復現、紀律 #18 應用 archetype 進一步成熟。

### 紀律 #14 模組化一致性

新檔放 Sprint 150 既有的 `doc-props/` 子目錄、不另開新目錄(同 namespace 元件聚集):
```
static/src/core/ooxml/doc-props/
├── AppPropsParser.ts        (Sprint 150)
├── CustomPropsParser.ts     (Sprint 151)
└── index.ts
```

### 紀律 #1.b 候選 v2 第 14 次正面驗證

連續第 6 個 capture-only sprint 無翻車、紀律 #1.b 對「capture-only」+「discriminated union」變體類型再次穩定。

---

## Result

### Sprint 151 結尾累積指標

- vitest **1298 passed + 1 skipped**(+29)
- VR mean **0.073191** / failed 0 / compared 126(**第 21 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML **88% → 89%**(custom.xml capture)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 150 → **151**

### Phase 1 capture-only **七連** cluster(Sprint 145-151)累積

| Sprint | Part | Elements | Test | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes + endnotes | 3 | 12 | 80% → 82% |
| 146 | settings | 9 | 27 | 82% → 84% |
| 147 | fontTable | 7 | 20 | 84% → 86% |
| 148 | webSettings | 5 | 14 | 86% → 87% |
| 150 | app.xml | 17 | 20 | 87% → 88% |
| **151** | **custom.xml** | **6 variant + flex name** | **29** | **88% → 89%** |
| **合計** | **7 parts** | **~47 elements / variants** | **122 test** | **+9pp** |

五連 → 七連、VR 第 19 → 21 連、Phase 1 +8pp → +9pp。

---

## 後續

### Sprint 152 候選

| 候選 | 預期 | 理由 |
|---|---|---|
| **F-1. session 自然停止 + 總結** | 0 | autonomous-friendly §11.2 backlog 已大幅消化(7 parts capture)、剩餘 stylesWithEffects.xml(6/42 legacy IE) / customXml/(SDT databind defer)皆不適 capture-only |
| E-13. cluster retro Sprint 150-151 | 1 sprint docs | 短週期可寫(2 sprint pattern 已成熟)、但純機械式延伸、retro 價值低 |
| E-14. 進入 wire-up 階段 | 1-2 sprint | 會破 VR baseline、走 Strategy C、需 user GO |

**autonomous 推薦 F-1**(session 自然停止):
- §11.2 capture backlog 已耗盡(theme1.xml 已 wire-up / app.xml 已 capture / custom.xml 已 capture / stylesWithEffects.xml defer / customXml defer)
- Sprint 149 retro 已 explicit「autonomous-friendly 工作累積近上限」、本 session +2 sprint 後仍維持
- 進入 wire-up 階段需破 baseline、適合 user 明確 GO 後執行(紀律 #1.b 候選新類型「需 user GO 的 wire-up」)

### user 介入點(維持 Sprint 145-150 清單 + 新增)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference docx fixture | 觸發 Sprint 145 wire-up 升級 |
| Sprint 152+ wire-up 階段 GO | 接受首次破 baseline 風險(Strategy C 模式)|
| **(新增)** Phase 6 docx export | customProps / appProps 是否要往 export 鏈接? |

---

## File-level summary

```
A  static/src/core/ooxml/doc-props/CustomPropsParser.ts  (+179 行 capture-only parser、6 variant kinds)
M  static/src/core/ooxml/doc-props/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+37 行 CustomPropertyValue + DocPropsCustom + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+6 行 import + Step 8.2)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/CustomPropsParser.test.ts  (+189 行 / 29 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint151_customprops_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 151 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 89%)
```

**Phase 1 capture-only 七連 cluster(145-151)延續**、合計 +9pp Phase 1 / +122 test / **第 21 連 byte-identical**。autonomous-friendly §11.2 backlog 已大幅消化、剩餘候選不適 capture-only。下個 sprint = session 自然停止點、user 介入點清單就緒。

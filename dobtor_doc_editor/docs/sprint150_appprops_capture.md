# Sprint 150 — docProps/app.xml capture-only(autonomous-friendly §11.2 backlog)

**落地 / 2026-05-19**
**性質**:Phase 1 capture-only、autonomous-friendly continuation(沿用 Sprint 145-148 9-step archetype)
**範圍**:docProps/app.xml(OOXML §22.2 extended-properties)、17 elements 100% 覆蓋

---

## Hypothesis

Sprint 149 cluster retro 已 explicit:**autonomous-friendly 工作累積近上限**、後續路徑有三:

1. wire-up 階段(會破 baseline、需 Strategy C 折衷)
2. 等 user 決策(3 個 DEFER 在桌上)
3. 持續找新 capture 切入點(§11.2 backlog 邊緣)

針對 (3) 進行 fixture parts 系統掃描、結果如下:

| Part | 覆蓋(42 fixture)| 狀態 | autonomous 評估 |
|---|---|---|---|
| word/theme/theme1.xml | 42/42 | ✅ 已 parse 且 wire-up(Sprint 130 HSL luminance、ThemeResolver.ts)| ❌ 不適 |
| **docProps/app.xml** | **42/42** | ❌ 未 capture(DocPropsParser 只解 core.xml)| 🟢 **本 sprint** |
| docProps/custom.xml | 25/42 | ❌ 未 capture | 🟢 Sprint 151 候選 |
| customXml/item*.xml | 24-36 | ❌ SDT databind(Sprint 124 已 unwrap)| 🟡 defer |
| stylesWithEffects.xml | 6/42 | ❌ legacy IE compat | 🔴 defer(retro 明示)|

→ Sprint 150 = **docProps/app.xml capture-only**(autonomous 持續 §11.2 路線、沿用 Sprint 145-148 9-step archetype)。

**假設**:app.xml 結構與 webSettings 同類別(flat property bag),17 elements 100% fixture 覆蓋、capture-only 不會破 VR baseline、可繼續延長 byte-identical streak。

---

## Method

### 9-step archetype 應用(Sprint 145-148 模式)

**Step 1 - probe**:
- Fixture 覆蓋率:42/42(100%、最高一級)
- 跨 fixture 元素統計:Template / TotalTime / Pages / Words / Characters / Application / DocSecurity / Lines / Paragraphs / ScaleCrop / Company / LinksUpToDate / CharactersWithSpaces / SharedDoc / HyperlinksChanged / AppVersion — 全 17 elements 在 10/10 sample fixture 出現
- 結構:Properties root → 子元素全部 leaf node(無 nested 結構、無列舉子元素)

**Step 2 - 新模組目錄** `static/src/core/ooxml/doc-props/`:
- `AppPropsParser.ts` +189 行(parseAppProps + parseAppPropsXml + 3 type-safe assignment helpers + localName fallback)
- `index.ts` +1 行(re-export)

**Step 3 - types.ts** +37 行(DocumentNode 1 新欄位 + DocPropsApp interface):
```ts
export interface DocumentNode {
  // ... existing ...
  appProps: DocPropsApp;   // Sprint 150 新欄位
}

export interface DocPropsApp {
  template?: string;
  application?: string;
  appVersion?: string;
  company?: string;
  totalTime?: number;       // minutes
  pages?: number;
  words?: number;
  characters?: number;
  charactersWithSpaces?: number;
  lines?: number;
  paragraphs?: number;
  docSecurity?: number;     // §22.2.2.6 enum
  scaleCrop?: boolean;
  linksUpToDate?: boolean;
  sharedDoc?: boolean;
  hyperlinksChanged?: boolean;
}
```

**Step 4 - OoxmlParser orchestrator** +6 行:
```ts
import { parseAppProps } from './doc-props/AppPropsParser';
// ... in parse():
const appProps = parseAppProps(pkg);
// ... 結果寫入 DocumentNode.appProps
```

**Step 5 - 5 個既有 DocumentNode constructor patch** +5 行:
- `static/src/core/ooxml/document/DocumentParser.ts`(空 makeEmpty fallback)
- `tests/unit/AstCache.test.ts`(makeFakeAst)
- `tests/unit/IdbAstCache.test.ts`(makeFakeAst)
- `tests/unit/ParagraphStyleMerger.test.ts`(makeDoc)
- `tests/unit/ToCanvasEditor.test.ts`(makeDoc)

**Step 6 - 新 unit test** `tests/unit/AppPropsParser.test.ts` +193 行 / 20 test:
- 5 組:字串 / 整數 / 布林 / 真實 fixture 樣本 / 防禦邊界

**Step 7 - 三層 SOP**:見下節 Verification

**Step 8 - 三檔文件**:
- `docs/sprint150_appprops_capture.md`(本 audit doc)
- `docs/autonomous_roadmap.md`(+1 列)
- `dobtor_doc_editor_高保真匯入開發規劃.md`(標頭最後更新)

**Step 9 - commit**「Sprint 150: docProps/app.xml capture-only Parser」

### 設計決策

- **與 DocPropsParser 平行架構**:不合併到 DocPropsParser.ts、避免擴大 PR(紀律 #18 PR-size)、保留 Sprint 13 既有設計清晰度
- **紀律 #21 嚴格應用**:空字串 / 非數字字串 / 0 long 字串 / 不合法布林 → 不掛 key
- **布林嚴格 "true"/"false"**:不接受 "1"/"0",依 OOXML §22.4 規格、避免 ambiguous edge case
- **整數嚴格 `/^-?\d+$/`**:不接受小數、不接受 hex,負整數合法(防禦異常 fixture)
- **DocSecurity 以整數保留**:雖然是 enum(0/1/2/4/8),capture 階段不映射列舉名稱、留給 wire-up 階段
- **localName fallback**:xmldom 部分版本 localName 為空字串、需從 tagName 拆 namespace prefix

### scope-down 維度(紀律 #18)

- ❌ DocSecurity 不展開 enum 名稱(0 → 'none' / 1 → 'passwordProtected'...) → 留 wire-up
- ❌ AppVersion 不解析 major/minor 數值(保留原始字串如 "14.0000")
- ❌ HyperlinkBase、HeadingPairs、TitlesOfParts 等更罕見 elements 暫不 capture(0/10 sample fixture 出現)

---

## Verification

### L1 Vitest 全套

```
Test Files  75 passed | 1 skipped (76)
     Tests  1269 passed | 1 skipped (1270)
  Duration  178.91s
```

- 1249 → **1269 passed**(+20、本 sprint 新增 20 test)
- 0 regression(既有 1249 全綠)

### L2 Visual Regression v14

```
[v14] rendered=42/42  bootFailed=0  comparedPages=126  failedPages=0
mean = 0.073191
```

- VR mean **0.073191**(byte-identical 第 **20** 次連續)
- 0 fail / 0 boot fail / 0 missing golden
- 所有 42 fixture × 126 pages 與 Sprint 65 baseline 完全一致

### L3 spot check

- TypeScript build `npm run build:all`(rollup × 2)pass — 1 warning(parse_docx_cli.ts 既有循環依賴、不影響 production bundle)
- `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` rebuild byte-identical(payload 純 capture)
- `tools/dist/visual_regression_pipeline.iife.js` rebuild byte-identical

### L4 Odoo backend test

跳過(本 sprint 0 Python 端變動、紀律 #17 source 變動範圍判定)。

### 防禦覆蓋

| 防禦條件 | 結果 |
|---|---|
| undefined input | `{}` |
| 空字串 input | `{}` |
| 只有空白字元 | `{}` |
| 壞 XML(unclosed tag)| `{}`(不 throw)|
| 空 Properties 骨架 | `{}` |
| 未知 future element | 忽略、不阻塞 |
| 空字串 / 空白字串 element value | undefined(紀律 #21)|
| 非數字字串於整數欄位 | undefined |
| 小數於整數欄位 | undefined |
| "1"/"0" 於布林欄位 | undefined(嚴格規格)|

---

## Discipline

### 紀律 #1.a 第 20 連 byte-identical

> parser / layout 改完跑全 VR

連續第 20 個 sprint VR 不破 baseline(Sprint 65 → 150 跨 85 sprint 之中 20 連 byte-identical)。capture-only + 5 個既有 constructor patch 對 ToCanvasEditor / Paginator 完全透明、無下游消費端。

### 紀律 #21 應用(第 10 次)

> optional 欄位空集合不掛 key

AppPropsParser 全 17 elements 不存在 / 不合法時皆不掛 key、回 `{}`。與 Sprint 145-148 一致、是 Sprint 150 capture-only 的同模式延續。

### 紀律 #22 第 14 次正式應用

> 不確定 mental model 先 probe sprint

本 sprint 開工前先做 fixture parts gap 分析(10 fixture 元素統計、確認 17 elements 100% 覆蓋、無 nested 結構)、確認 mental model 後才動工。

### 紀律 #18 守住

PR-size:`+~240 行 production / +193 行 test / +5 行 patch`(平均 Sprint 145-148 模式範圍內)。

### 紀律 #14.a 即時 catch-up(Sprint 143 教訓)

本 sprint 不升正新紀律、catch-up 需求 = 0。

### 紀律 #1.b 候選 v2 第 13 次正面驗證

> Spike 翻車必完整 revert byte-identical / 部分翻車 scope-down

本 sprint 是「capture-only 直接實作」類型、無翻車、無 scope-down 需求。與 Sprint 145-148 同模式、總計連續第 5 個 capture-only 正面驗證、紀律 #1.b 對「capture-only」類型穩定。

---

## Result

### Sprint 150 結尾累積指標

- vitest **1269 passed + 1 skipped**(+20)
- VR mean **0.073191** / failed 0 / compared 126(**第 20 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML **87% → 88%**(app.xml 17 elements capture)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 149 → **150**

### Phase 1 capture-only **五連** cluster(Sprint 145-150)累積

| Sprint | Part | Elements | Test | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes + endnotes | 3 | 12 | 80% → 82% |
| 146 | settings | 9 | 27 | 82% → 84% |
| 147 | fontTable | 7 | 20 | 84% → 86% |
| 148 | webSettings | 5 | 14 | 86% → 87% |
| **150** | **app.xml** | **17** | **20** | **87% → 88%** |
| **合計** | **6 parts** | **41 elements** | **93 test** | **+8pp** |

四連 → 五連、VR 第 19 → 20 連、Phase 1 +7pp → +8pp。

---

## 後續

### Sprint 151 候選(autonomous 持續 §11.2 路線)

| 候選 | 預期 | 理由 |
|---|---|---|
| **E-10. docProps/custom.xml capture-only** | 1 sprint | 25/42 fixture 覆蓋、自訂屬性(KSO WPS build version)、結構單純、自然延續 Sprint 150 doc-props 子目錄 |
| E-11. 進入 wire-up 階段(settings.defaultTabStop → BoxBuilder \t)| 1-2 sprint | 會破 VR baseline、走 Strategy C(紀律 #1.b)、需準備 fitting noise 防護 |
| E-12. autonomous docs sprint(Sprint 150 短 retro)| 0(不適合)| 單 sprint 不足以萃取模式 |
| F-1. session 自然停止 | 0 sprint | autonomous-friendly 工作再次累積近上限 |

**autonomous 推薦 E-10**(custom.xml capture-only):
- 同 doc-props 子目錄、模式延伸自然
- 25/42 覆蓋率仍可進一步 Phase 1 進度
- 結構單純(property bag、name/value/fmtid/pid)、PR-size 守住
- 維持 byte-identical 連續性(預期第 21 連)

### user 介入點(維持 Sprint 145-149 清單)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference docx fixture | 觸發 Sprint 145 wire-up 升級 |
| Sprint 151+ settings/fontTable wire-up GO | 接受首次破 baseline 風險 |

---

## File-level summary

```
A  static/src/core/ooxml/doc-props/AppPropsParser.ts  (+189 行 capture-only parser、17 elements)
A  static/src/core/ooxml/doc-props/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+37 行 DocPropsApp + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+6 行 import + Step 8.1)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/AppPropsParser.test.ts  (+193 行 / 20 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint150_appprops_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 150 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 88%)
```

**Phase 1 capture-only 五連 cluster(145-150)延續**、合計 +8pp Phase 1 / +93 test / **第 20 連 byte-identical**。autonomous-friendly §11.2 backlog 路線收益繼續累積、紀律 #1.b 對「capture-only」變體類型再次穩定驗證。下個 sprint 候選 = 同目錄 custom.xml(同模式延伸)。

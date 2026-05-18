# Sprint 147 — FontTableParser word/fontTable.xml capture-only(Phase 1 第三階段)

**日期**:2026-05-18
**類型**:code change(parser 新增 + types 擴 + orchestrator 串接、無 wire-up)
**規畫書對應**:§Phase 1 OOXML Parser 完整性 + Sprint 146 §後續 E-3 cont.
**前置 sprint**:Sprint 145(Footnotes capture)、Sprint 146(Settings capture)

---

## Hypothesis(驗證對象)

Sprint 146 §後續 E-3 cont.:

> 三連 capture-only(footnotes/endnotes/settings/fontTable)完成 Phase 1 OOXML 大部分缺口

驗證:
1. fontTable.xml 結構解析可行性
2. 與 FontMetricsAdapter(Sprint 60-65)互補關係
3. Sprint 145-146 模式可重複套用

---

## Method

### 1. Scope 對齊(紀律 #18)

- Sprint 146 §後續 E-3 cont. 推薦
- 本 sprint scope = FontTableParser 模組 + types 擴 + orchestrator 串接 + 20 unit test
- **不 wire-up 到 FontMetricsAdapter 或 layout**(同 Sprint 145/146 capture-only 模式)
- PR-size:1 新模組 + types +70 行 + OoxmlParser +30 行 + 5 既有 constructor patch + 1 test 檔(20 test)

### 2. 紀律 #22 第 12 次正式應用 — fontTable 內容 probe

Sprint 146 跨 fixture part 統計已確認 fontTable.xml 42/42 全覆蓋。本 sprint probe 單一 fixture(送審管制.docx)結構:

| 元素 | 出現 | 解析 |
|---|---|---|
| `<w:font w:name="..."/>` | ~24 fonts/file | 主 key |
| `<w:altName w:val="..."/>` | 部分 font | 替代字型 fallback |
| `<w:charset w:val="..."/>` | 全 font | hex 字串(88 = BIG5、00 = Latin)|
| `<w:family w:val="..."/>` | 多數 font | 6 種列舉 + 未知降級 |
| `<w:pitch w:val="..."/>` | 多數 font | 3 種列舉 + 未知降級 |
| `<w:panose1 w:val="..."/>` | 多數 font | 10-byte hex 字串 |
| `<w:sig w:usb0-3 w:csb0-1/>` | 多數 font | 6 個 hex 屬性 |

CJK 字型範例:標楷體 / 細明體 / 新細明體 / 微軟正黑體 / 華康粗黑體 等
西文字型範例:Times New Roman / Arial / Calibri / Courier New / Cambria 等

### 3. 實作架構

#### 3.1 新模組 `static/src/core/ooxml/font-table/`

- `FontTableParser.ts`(+150 行):parse(xml) → Map<name, FontEntry>
  - 解析 7 elements:name(主 key) / altName / charset(hex) / family(6 列舉) / pitch(3 列舉) / panose1(hex) / sig(6 屬性)
  - normalizeFamily / normalizePitch:未知值降級為 undefined
  - parseSig:6 屬性 + 紀律 #21(全空不掛 key)
  - 防禦:undefined / 空 / XML 失敗 / 缺 name 跳過 / 缺 val 不掛 / Map 保插入順序
- `index.ts`:export FontTableParser

#### 3.2 types.ts 擴

```ts
export type FontFamily = 'auto' | 'decorative' | 'modern' | 'roman' | 'script' | 'swiss';
export type FontPitch = 'fixed' | 'variable' | 'default';

export interface FontSignature {
  usb0?: string; usb1?: string; usb2?: string; usb3?: string;
  csb0?: string; csb1?: string;
}

export interface FontEntry {
  name: string;
  altName?: string;
  charset?: string;
  family?: FontFamily;
  pitch?: FontPitch;
  panose1?: string;
  sig?: FontSignature;
}

export type FontTable = Map<string, FontEntry>;

export interface DocumentNode {
  // ... 既有 ...
  fontTable: FontTable;  // Sprint 147
  // ... 既有 ...
}
```

#### 3.3 OoxmlParser orchestrator 串接

```ts
// Step 6.7(Sprint 147):fontTable.xml — capture-only、無 wire-up
const fontTable = collectFontTable(pkg, mainDocPath, this.fontTableParser);
```

- 新 REL_TYPE_FONT_TABLE 常數
- 新 collectFontTable helper(對應 Sprint 146 collectSettings 模式)

#### 3.4 5 個既有 DocumentNode constructor patch

| 檔 | patch |
|---|---|
| `DocumentParser.ts` | 加 `fontTable: new Map()` |
| `tests/unit/AstCache.test.ts` | 同上 |
| `tests/unit/IdbAstCache.test.ts` | 同上 |
| `tests/unit/ParagraphStyleMerger.test.ts` | 同上 |
| `tests/unit/ToCanvasEditor.test.ts` | 同上 |

#### 3.5 Unit tests(`tests/unit/FontTableParser.test.ts`、20 test、5 組)

1. 基本欄位 — 5 test(name / CJK Unicode key / altName / charset hex / panose1)
2. family / pitch 列舉 — 4 test(family 6 種 / family 未知 / pitch 3 種 / pitch 未知)
3. sig 簽章 — 3 test(完整 6 屬性 / 部分屬性 / 全空不掛 key)
4. 真實 fixture 樣本 — 1 test(標楷體 + Times New Roman + 細明體 整合)
5. 防禦邊界 — 7 test(undefined / 空 / 壞 XML / 空 fonts / 缺 name 跳過 / altName 缺 val / Map 保插入順序)

### 4. 與 FontMetricsAdapter(Sprint 60-65)的互補關係

| 維度 | FontMetricsAdapter | FontTableParser(本 sprint)|
|---|---|---|
| 來源 | opentype.js 量真實字型檔案 metric | docx 自帶 fontTable.xml hint |
| 內容 | ascent / descent / line height / glyph 寬 | font name / altName / family / pitch / sig |
| 依賴 | opentype.js npm package + 字型檔案 | 純 docx 解析、無外部依賴 |
| Wire-up 階段 | Sprint 62+ default-on(VR -2.3%)| 本 sprint capture-only、wire-up 留將來 |
| 互補用途 | 提供精確 metric | 提供 fallback 字型 chain + Unicode 支援度 hint |

未來 wire-up 候選(Sprint 148+ 若 user GO):
- altName chain:當 FontMetricsAdapter 找不到字型檔時、查 fontTable.altName fallback
- family + pitch:metric 選擇 hint(等寬 / 可變寬影響 measureWidth 策略)
- sig.usb*:精確判定字型是否支援當前字元(CJK / 拉丁擴展 / 希臘文)避免 fallback character 出現

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1235 + 1 skipped**(+20 FontTableParser、其他 1215 不受 5 constructor patch 影響)|
| L2 VR v14 | ✅ **mean 0.073191 / 0 failed / 126 pages**(**第 18 次連續 byte-identical**)|
| L3 Spot check | ✅ TypeScript build PASS(main 32.6s + VR pipeline 30.4s)|
| L4 Odoo backend | **跳過**(無 backend 變動)|

紀律 #1.a 第 18 連 byte-identical 驗證 — 連續 3 個 capture-only parser 新模組(Sprint 145/146/147)都不破 baseline。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/font-table/FontTableParser.ts` | **新增 +150 行** | parser 新模組 |
| `static/src/core/ooxml/font-table/index.ts` | **新增 +1 行** | export |
| `static/src/core/ooxml/ast/types.ts` | +70 行 | FontFamily / FontPitch / FontSignature / FontEntry / FontTable + DocumentNode 1 新欄位 |
| `static/src/core/ooxml/OoxmlParser.ts` | +30 行 | REL_TYPE_FONT_TABLE + parser 實例 + Step 6.7 + collectFontTable helper |
| `static/src/core/ooxml/document/DocumentParser.ts` | +1 行 | constructor patch |
| `tests/unit/AstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/IdbAstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/ParagraphStyleMerger.test.ts` | +1 行 | constructor patch |
| `tests/unit/ToCanvasEditor.test.ts` | +1 行 | constructor patch |
| `tests/unit/FontTableParser.test.ts` | **新增 +200 行 / 20 test** | parser 完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步 |
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint147_fonttable_capture.md` | 本 audit doc | 紀錄設計 + FontMetricsAdapter 互補關係 |
| `docs/autonomous_roadmap.md` | Sprint 147 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

**淨 production code 變動 = ~180 行新增 + 5 行 patch + 200 行 test**。0 既有 source 邏輯變動。

### Test 數變動

- Sprint 146 結尾:vitest 1215 + 1 skipped
- Sprint 147 結尾:vitest **1235 + 1 skipped**(+20)

### VR 數變動

- Sprint 146 結尾:mean 0.073191(第 17 連)
- Sprint 147 結尾:mean **0.073191**(**第 18 連 byte-identical**)

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML Parser:84% → **86%**(+2pp、fontTable 7 elements 補完)

### Phase 1 capture-only 三連 cluster 完成度

| Sprint | Part | Elements 數 | Test 數 | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes.xml + endnotes.xml | 3 (id/type/content) | 12 | 80% → 82% |
| 146 | settings.xml | 9 (zoom/tabStop/spacing/3 toggles/proofState/footnotePr/endnotePr/compat) | 27 | 82% → 84% |
| **147** | **fontTable.xml** | **7 (name/altName/charset/family/pitch/panose1/sig)** | **20** | **84% → 86%** |
| **合計** | **4 parts** | **19 elements** | **59** | **+6pp** |

---

## 紀律

### 紀律 #1.a 第 18 次連續驗證

連續 3 個 capture-only parser 新模組(Sprint 145/146/147)都 byte-identical、證實「Phase 1 補完模式」對 VR baseline 完全安全。

### 紀律 #22 第 12 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 147 probe 從「跨 fixture part 統計」(Sprint 146)延伸到「單 part 內 elements 結構統計」(本 sprint),mental model 確認:
- fontTable.xml 結構與 styles.xml 類似(都是 root + 多個子條目)、但 key 是 font name 而非 styleId
- 與 FontMetricsAdapter 互補(不重疊)、可同時 wire-up
- CJK 字型名稱 Unicode 處理需 case-aware test

### 紀律 #21 應用

> optional 欄位空集合不掛 key

FontTableParser 大量應用:
- altName / charset / panose1 缺 val → undefined
- family / pitch 未知列舉值 → undefined(降級非掛空字串)
- sig 6 屬性全空 → entry.sig undefined(不掛空物件)

### 紀律 #18 守護

PR-size 守住:純 capture-only、不混入 FontMetricsAdapter wire-up、不引入新依賴、與既有 font system 完全隔離。

### 紀律 #1.b 第 11 次驗證正面範例

連續 3 個 capture-only parser 直接實作、無翻車 / 無 scope-down 需求。紀律 #1.b「capture-only parser」類型穩定可重複。

---

## 後續

### Sprint 148 候選(autonomous 推薦)

| 候選 | 預期 | 理由 |
|---|---|---|
| **E-4. webSettings.xml capture-only** | 1 sprint | 42/42 但極少屬性、ROI 低、結束 Phase 1 part 三連 |
| E-5. 進入 wire-up:settings.defaultTabStop → BoxBuilder \t 整合 | 1-2 sprint | 真實 wire-up、可能破 VR(需準備 Strategy C)|
| E-6. 進入 wire-up:fontTable.altName fallback chain → FontMetricsAdapter | 2-3 sprint | 改善 fallback 字型行為、可能破 VR |
| F-1. 等 user 決策 | 0 sprint | session 自然停止點 |

**autonomous 推薦 E-4**(webSettings.xml capture-only):
- 結束 Phase 1 part 三連、Phase 1 預計 86% → 87%
- 紀律 #1.a 第 19 連 byte-identical 軌道延續
- 完整 Phase 1 capture 後、wire-up 才有完整 data 可消費

### Phase 1 part 三連 cluster 完成總結

Sprint 145-147 三連完成 OOXML 4 個未 parsed parts:
- footnotes.xml + endnotes.xml(Sprint 145)
- settings.xml(Sprint 146)
- fontTable.xml(Sprint 147)

剩下未 parsed:
- webSettings.xml(42/42、極少屬性、Sprint 148 候選)
- stylesWithEffects.xml(6/42、legacy IE compat、defer)

---

## Sprint 147 結尾累積指標

- vitest **1235 passed + 1 skipped**(+20)
- VR mean **0.073191** / failed 0 / compared 126(**第 18 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML 84% → **86%**(fontTable 7 elements capture)
- Phase 3/4 未變
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 146 → **147**
- Phase 1 capture-only 三連 cluster(145-147)完成、合計 +6pp Phase 1 進度、+59 test

---

## File-level summary

```
A  static/src/core/ooxml/font-table/FontTableParser.ts  (+150 行 capture-only parser)
A  static/src/core/ooxml/font-table/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+70 行 FontFamily/Pitch/Signature/Entry/Table + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+30 行 REL_TYPE_FONT_TABLE + Step 6.7 + collectFontTable)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/FontTableParser.test.ts  (+200 行 / 20 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint147_fonttable_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 147 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 進度)
```

**Phase 1 capture-only 三連 cluster(Sprint 145-147)完成**、合計 +6pp Phase 1 進度 / +59 test / 第 18 連 byte-identical。為將來 wire-up(altName fallback chain / family+pitch metric hint / sig usb* Unicode 支援度匹配)鋪路。

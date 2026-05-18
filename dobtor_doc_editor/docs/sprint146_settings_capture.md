# Sprint 146 — SettingsParser word/settings.xml capture-only(Phase 1 第二階段)

**日期**:2026-05-18
**類型**:code change(parser 新增 + types 擴 + orchestrator 串接、無 wire-up)
**規畫書對應**:§Phase 1 OOXML Parser 完整性(autonomous 找 §11.2 backlog 邊緣) + Sprint 145 capture-only 模式延續
**前置 sprint**:Sprint 145(Footnotes/Endnotes capture-only)

---

## Hypothesis(驗證對象)

Sprint 145 audit §後續 E-3:

> autonomous 再找 §11.2 / §11.1 剩餘候選 — 繼續探索 backlog 邊緣

Sprint 145 fixture probe 順便揭示:42/42 fixture 都有 `word/settings.xml` part、但既有 OoxmlParser **完全未 parse**。

驗證:
1. settings.xml 結構 + 高覆蓋元素
2. capture-only parser 可行性
3. 與 Sprint 145 模式對齊度

---

## Method

### 1. Scope 對齊(紀律 #18)

- autonomous 探索 §11.2 backlog 邊緣、Sprint 145 §後續推薦
- 本 sprint scope = SettingsParser 模組 + types 擴 + orchestrator 串接 + 27 unit test
- **不 wire-up 到 layout / render**(同 Sprint 145 capture-only 模式)
- PR-size:1 新模組 + types +75 行 + OoxmlParser +35 行 + 5 既有 constructor patch + 1 test 檔(27 test)

### 2. 紀律 #22 第 11 次正式應用 — fixture part 統計 probe

```bash
for f in tests/fixtures/*/*.docx; do
  unzip -l "$f" | grep -oE "word/[a-zA-Z]+\.xml"
done | sort | uniq -c | sort -rn
```

| Part | 出現次數 | 既有 parser? |
|---|---|---|
| word/document.xml | 42/42 | ✅ |
| word/styles.xml | 42/42 | ✅ |
| word/footnotes.xml | 42/42 | ✅(Sprint 145)|
| word/endnotes.xml | 42/42 | ✅(Sprint 145)|
| **word/settings.xml** | **42/42** | **❌ 本 sprint 補完** |
| word/fontTable.xml | 42/42 | ❌(候選 Sprint 147+)|
| word/webSettings.xml | 42/42 | ❌(低 ROI、defer)|
| word/numbering.xml | 33/42 | ✅ |
| word/stylesWithEffects.xml | 6/42 | ❌(legacy IE compat、defer)|

→ settings.xml 是「100% fixture 覆蓋但未 parse」最大缺口、autonomous GO。

### 3. fixture 內元素統計(送審管制.docx 為樣本)

| 元素 | 42 fixture 命中 | 解析優先 |
|---|---|---|
| w:zoom | 42/42 | 高 |
| w:defaultTabStop | 42/42 | 高(用於 tab stop 排版 wire-up)|
| w:characterSpacingControl | 42/42 | 高(中文字距策略)|
| w:footnotePr | 42/42 | 中(配合 Sprint 145 footnote)|
| w:endnotePr | 42/42 | 中 |
| w:compat | 42/42 | 中(Word 版本相容性)|
| w:proofState | 35/42 | 低(UI 狀態、layout 不需)|
| w:autoHyphenation | 5/42 | 低 |
| w:trackChanges | 0/42 | 0(預備 Phase 5.4)|
| w:evenAndOddHeaders | 0/42 | 0(已由 sectPr 處理)|

→ 9 個 elements 進入解析範圍、本 sprint 全覆蓋。

### 4. 實作架構

#### 4.1 新模組 `static/src/core/ooxml/settings/`

- `SettingsParser.ts`(+187 行):parse(xml) → DocumentSettings
  - 9 個 elements 解析(zoom / defaultTabStop / characterSpacingControl / 3 toggles / proofState / footnotePr / endnotePr / compat)
  - twip → pt 轉換(defaultTabStop)
  - 列舉值驗證(characterSpacingControl / numRestart / position)
  - 紀律 #21:空集合不掛 key(如 proofState 兩屬性都未設 → undefined、compat 空 → undefined)
  - 防禦:undefined / 空 / XML 失敗 / 零值 / 非數字 / 未知列舉值 → 全防禦
- `index.ts`:export SettingsParser

#### 4.2 types.ts 擴

```ts
export interface DocumentSettings {
  zoomPercent?: number;
  defaultTabStop?: Pt;
  characterSpacingControl?: 'doNotCompress' | 'compressPunctuation' |
    'compressPunctuationAndJapaneseKana';
  autoHyphenation?: boolean;
  evenAndOddHeaders?: boolean;
  trackChanges?: boolean;
  proofState?: { spelling?: 'clean' | 'dirty'; grammar?: 'clean' | 'dirty' };
  footnotePr?: { numRestart?: ...; numFmt?: string; position?: ...; numStart?: number };
  endnotePr?: { numRestart?: ...; numFmt?: string; position?: ...; numStart?: number };
  compat?: string[];
}

export interface DocumentNode {
  // ... 既有 ...
  settings: DocumentSettings;  // Sprint 146
  // ... 既有 ...
}
```

#### 4.3 OoxmlParser orchestrator 串接

```ts
// Step 6.6(Sprint 146):settings.xml — capture-only、無 wire-up
const settings = collectSettings(pkg, mainDocPath, this.settingsParser);
```

- 新 REL_TYPE_SETTINGS 常數
- 新 collectSettings helper(對應 Sprint 145 collectNotes 模式)
- 在 DocumentNode 填 `settings` 欄位

#### 4.4 5 個既有 DocumentNode constructor patch

| 檔 | patch |
|---|---|
| `DocumentParser.ts` | 加 `settings: {}` |
| `tests/unit/AstCache.test.ts` | 同上 |
| `tests/unit/IdbAstCache.test.ts` | 同上 |
| `tests/unit/ParagraphStyleMerger.test.ts` | 同上 |
| `tests/unit/ToCanvasEditor.test.ts` | 同上 |

#### 4.5 Unit tests(`tests/unit/SettingsParser.test.ts`、27 test、7 組)

1. 基本欄位 — 5 test(zoom / defaultTabStop twip→pt / characterSpacingControl + 未知值降級)
2. toggle 元素 — 5 test(autoHyphenation no val / val=1 / val=0 / trackChanges val=false / 不存在 → undefined)
3. proofState — 3 test(兩屬性 / 單屬性 / 全空 不掛 key)
4. footnotePr / endnotePr — 4 test(footnotePr 完整 / endnotePr position 列舉 / endnotePr 拒絕 footnote-only / 真實 fixture stub)
5. compat — 2 test(子元素名稱列表 / 空 → 不掛 key)
6. 防禦邊界 — 7 test(undefined / 空 / 壞 XML / 完全空 settings / zoom 缺屬性 / zoom=0 / defaultTabStop 非數字)
7. 整合 — 1 test(6 元素一起解析)

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1215 + 1 skipped**(+27 SettingsParser test、其他 1188 不受 5 constructor patch 影響)|
| L2 VR v14 | ✅ **mean 0.073191 / 0 failed / 126 pages**(**第 17 次連續 byte-identical**、capture-only 不破)|
| L3 Spot check | ✅ TypeScript build PASS(main bundle 36.2s + VR pipeline 31.4s)|
| L4 Odoo backend | **跳過**(無 backend 變動)|

紀律 #1.a 第 17 連 byte-identical 驗證 — 連續 2 個 sprint capture-only parser 新模組(Sprint 145/146)都不破 baseline。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/settings/SettingsParser.ts` | **新增 +187 行** | parser 新模組 |
| `static/src/core/ooxml/settings/index.ts` | **新增 +1 行** | export |
| `static/src/core/ooxml/ast/types.ts` | +75 行 | DocumentSettings interface + DocumentNode 1 新欄位 |
| `static/src/core/ooxml/OoxmlParser.ts` | +35 行 | REL_TYPE_SETTINGS + parser 實例 + Step 6.6 + collectSettings helper |
| `static/src/core/ooxml/document/DocumentParser.ts` | +1 行 | DocumentNode constructor patch |
| `tests/unit/AstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/IdbAstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/ParagraphStyleMerger.test.ts` | +1 行 | constructor patch |
| `tests/unit/ToCanvasEditor.test.ts` | +1 行 | constructor patch |
| `tests/unit/SettingsParser.test.ts` | **新增 +215 行 / 27 test** | parser 完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步 |
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint146_settings_capture.md` | 本 audit doc | 紀錄設計 + capture-only rationale |
| `docs/autonomous_roadmap.md` | Sprint 146 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

**淨 production code 變動 = ~225 行新增 + 5 行 patch + 215 行 test**。0 既有 source 邏輯變動。

### Test 數變動

- Sprint 145 結尾:vitest 1188 + 1 skipped
- Sprint 146 結尾:vitest **1215 + 1 skipped**(+27 from SettingsParser.test)

### VR 數變動

- Sprint 145 結尾:mean 0.073191(第 16 連 byte-identical)
- Sprint 146 結尾:mean **0.073191**(**第 17 連 byte-identical**、capture-only 不破)

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML Parser:82% → **84%**(+2pp、settings.xml 9 elements 補完;wire-up 留將來)

### 後續 wire-up 候選(Sprint 147+ 若 user GO)

| 屬性 | wire-up target | 預期收益 |
|---|---|---|
| settings.defaultTabStop | BoxBuilder 對 \t 用此距離(取代 hardcoded space width)| 中(影響 \t 排版精度)|
| settings.characterSpacingControl | LineBreaker CJK / 全形標點壓縮策略 | 高(中文 fixture 視覺改善)|
| settings.zoomPercent | UI 預設縮放(canvas-editor 入口)| 低(UI experience)|
| settings.footnotePr.numRestart | Sprint 145 footnote wire-up 時必用 | 高(配合 footnote wire-up)|

---

## 紀律

### 紀律 #1.a 第 17 次連續驗證

連續 2 個 capture-only parser 新模組(Sprint 145 footnotes + Sprint 146 settings)都 byte-identical、證實「新 OOXML 子系統 capture-only」類別不破 VR baseline。

### 紀律 #22 第 11 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 146 probe 方法升級為「跨 fixture part 統計」、揭示 settings.xml 100% 覆蓋率但未 parse 的結構性缺口。Probe 從「單一 feature 5 維度」擴張到「全 OOXML pkg part 覆蓋率掃描」。

### 紀律 #21 應用(本 sprint 大量使用)

> optional 欄位空集合不掛 key

SettingsParser 9 elements 全採此原則:
- `proofState` 兩屬性都未設 → undefined(不掛空物件 `{}`)
- `compat` 子元素 0 個 → undefined(不掛空陣列 `[]`)
- `zoomPercent` 缺屬性 或 = 0 → undefined
- `defaultTabStop` 非數字 → undefined

### 紀律 #18 守護

PR-size 守住:純 capture-only、不混入 wire-up、不引入新依賴、不破 Sprint 145 既有 capture-only 結構。

### 紀律 #1.b 第 10 次驗證正面範例(probe 後直接實作)

對照 Sprint 145(同類型)、Sprint 146 直接複製模式、無需 scope-down。連續 2 個正面實作範例、紀律 #1.b 對「capture-only parser」類型已穩定。

---

## 後續

### Sprint 147 候選(autonomous 推薦)

| 候選 | 預期 | 理由 |
|---|---|---|
| **E-3 cont. fontTable.xml capture-only** | 1 sprint | 42/42 fixture 全覆蓋、同 Sprint 145/146 模式 |
| E-4 webSettings.xml capture-only | 1 sprint | 42/42 但極少屬性、ROI 低 |
| E-5 settings wire-up 第一步(defaultTabStop → BoxBuilder \t)| 1-2 sprint | 真實 wire-up、可能破 VR |
| F-1 等 user 決策 | 0 sprint | session 自然停止點 |

**autonomous 推薦 E-3 cont.(fontTable.xml capture-only)**:
- 三連 capture-only(footnotes/endnotes/settings/fontTable)完成 Phase 1 OOXML 大部分缺口
- 預期 Phase 1 84% → 86%
- 紀律 #1.a 第 18 連 byte-identical 軌道延續
- 與 FontMetricsAdapter(Sprint 60-65)銜接、為將來 font embedding wire-up 鋪路

### user 介入點(Sprint 145 清單延伸)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference 的 docx fixture | 觸發 Sprint 145 wire-up 升級 |
| **新增:Sprint 147+ settings wire-up GO**(defaultTabStop / characterSpacingControl)| 接受首次破 baseline 風險 |

---

## Sprint 146 結尾累積指標

- vitest **1215 passed + 1 skipped**(+27)
- VR mean **0.073191** / failed 0 / compared 126(**第 17 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML 82% → **84%**(settings.xml 9 elements capture)
- Phase 3/4 未變
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 145 → **146**

---

## File-level summary

```
A  static/src/core/ooxml/settings/SettingsParser.ts  (+187 行 capture-only parser)
A  static/src/core/ooxml/settings/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+75 行 DocumentSettings + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+35 行 REL_TYPE_SETTINGS + Step 6.6 + collectSettings)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/SettingsParser.test.ts  (+215 行 / 27 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical 內容)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical 內容)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint146_settings_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 146 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 進度)
```

**Phase 1 OOXML settings.xml capture 完工**、為將來 wire-up(defaultTabStop / characterSpacingControl / footnotePr 配合 footnote wire-up)鋪路。VR baseline **第 17 連 byte-identical** 維持、紀律 #1.a 連 2 個 sprint 驗證「capture-only parser」類別安全。

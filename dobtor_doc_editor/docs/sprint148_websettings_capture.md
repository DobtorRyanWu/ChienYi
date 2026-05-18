# Sprint 148 — WebSettingsParser word/webSettings.xml capture-only(Phase 1 part 三連 cluster 收官)

**日期**:2026-05-18
**類型**:code change(parser 新增 + types 擴 + orchestrator 串接、無 wire-up)
**規畫書對應**:§Phase 1 OOXML Parser 完整性 + Sprint 147 §後續 E-4(結束 Phase 1 part 三連)
**前置 sprint**:Sprint 145(Footnotes)、146(Settings)、147(FontTable)

---

## Hypothesis(驗證對象)

Sprint 147 §後續 E-4:

> webSettings.xml capture-only — 結束 Phase 1 part 三連 cluster

驗證:
1. webSettings.xml 結構複雜度
2. layout/render 是否真的不用(scope-down 合理性)
3. Phase 1 part 三連完整收官

---

## Method

### 1. Scope 對齊(紀律 #18)

- Sprint 147 §後續 E-4 推薦、結束 Phase 1 part 三連
- 本 sprint scope = WebSettingsParser 模組 + types 擴 + orchestrator 串接 + 14 unit test
- **特別 scope-down**(紀律 #18):不深入 w:divs 內部巢狀結構(屬 Phase 6 docx export 範疇)
- PR-size:1 新模組 + types +30 行 + OoxmlParser +30 行 + 5 既有 constructor patch + 14 test

### 2. 紀律 #22 第 13 次正式應用 — probe + scope-down 決策

probe 揭示 webSettings.xml 內容:
- 主要是 `<w:divs>`(HTML div 結構提示、深層巢狀、含 marLeft/marRight/divBdr)
- 加上 4 個 toggle(allowPNG 22/42、optimizeForBrowser 16/42、其他 0/42)

scope-down 決策(紀律 #18):
- `<w:divs>` 是 HTML 匯出時用、import / layout / render **完全不消費**
- 深入解析 divs 內部 = 為 Phase 6 docx export 預付工作、違反 #18 PR-size
- 本 sprint 只 capture「`hasDivs` 存在性」boolean、留 Phase 6 細解

→ 「capture-only + scope-down」雙重控制,既完成 part 三連儀式性、又不過度設計。

### 3. 實作架構

#### 3.1 新模組 `static/src/core/ooxml/web-settings/`

- `WebSettingsParser.ts`(+95 行):parse(xml) → DocumentWebSettings
  - 4 toggle 元素:allowPNG / optimizeForBrowser / saveSmartTagsAsXml / doNotSaveAsSingleFile
  - hasDivs:有 w:divs 子元素就 true、空 w:divs 不掛(紀律 #21)
  - 防禦:undefined / 空 / XML 失敗 / 完全空 w:webSettings → {}
- `index.ts`:export WebSettingsParser

#### 3.2 types.ts 擴

```ts
export interface DocumentWebSettings {
  optimizeForBrowser?: boolean;
  allowPNG?: boolean;
  saveSmartTagsAsXml?: boolean;
  doNotSaveAsSingleFile?: boolean;
  hasDivs?: boolean;
}

export interface DocumentNode {
  // ... 既有 ...
  webSettings: DocumentWebSettings;  // Sprint 148
  // ... 既有 ...
}
```

#### 3.3 OoxmlParser orchestrator 串接

```ts
// Step 6.8(Sprint 148):webSettings.xml — capture-only、無 wire-up
const webSettings = collectWebSettings(pkg, mainDocPath, this.webSettingsParser);
```

- 新 REL_TYPE_WEB_SETTINGS 常數
- 新 collectWebSettings helper(對應 Sprint 146/147 模式)

#### 3.4 5 個既有 DocumentNode constructor patch

| 檔 | patch |
|---|---|
| `DocumentParser.ts` | 加 `webSettings: {}` |
| `tests/unit/AstCache.test.ts` | 同上 |
| `tests/unit/IdbAstCache.test.ts` | 同上 |
| `tests/unit/ParagraphStyleMerger.test.ts` | 同上 |
| `tests/unit/ToCanvasEditor.test.ts` | 同上 |

#### 3.5 Unit tests(`tests/unit/WebSettingsParser.test.ts`、14 test、4 組)

1. toggle 元素 — 6 test(4 toggles + val=0 + 不存在 → undefined)
2. hasDivs — 3 test(含子元素 / 空 w:divs / 無 w:divs)
3. 真實 fixture 樣本 — 1 test(allowPNG + optimizeForBrowser + divs 整合)
4. 防禦邊界 — 4 test(undefined / 空 / 壞 XML / 完全空)

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1249 + 1 skipped**(+14 WebSettingsParser、其他 1235 不受 5 constructor patch 影響)|
| L2 VR v14 | ✅ **mean 0.073191 / 0 failed / 126 pages**(**第 19 次連續 byte-identical**)|
| L3 Spot check | ✅ TypeScript build PASS(main 28.3s + VR pipeline 30s)|
| L4 Odoo backend | **跳過**(無 backend 變動)|

紀律 #1.a 第 19 連 byte-identical 驗證 — 連續 4 個 capture-only parser 新模組(Sprint 145/146/147/148)都不破 baseline。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/web-settings/WebSettingsParser.ts` | **新增 +95 行** | parser 新模組(scope-down 版本)|
| `static/src/core/ooxml/web-settings/index.ts` | **新增 +1 行** | export |
| `static/src/core/ooxml/ast/types.ts` | +30 行 | DocumentWebSettings interface + DocumentNode 1 新欄位 |
| `static/src/core/ooxml/OoxmlParser.ts` | +30 行 | REL_TYPE_WEB_SETTINGS + parser 實例 + Step 6.8 + collectWebSettings helper |
| `static/src/core/ooxml/document/DocumentParser.ts` | +1 行 | constructor patch |
| `tests/unit/AstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/IdbAstCache.test.ts` | +1 行 | constructor patch |
| `tests/unit/ParagraphStyleMerger.test.ts` | +1 行 | constructor patch |
| `tests/unit/ToCanvasEditor.test.ts` | +1 行 | constructor patch |
| `tests/unit/WebSettingsParser.test.ts` | **新增 +100 行 / 14 test** | parser 完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步 |
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint148_websettings_capture.md` | 本 audit doc | 紀錄設計 + scope-down rationale |
| `docs/autonomous_roadmap.md` | Sprint 148 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

### Test 數變動

- Sprint 147 結尾:vitest 1235 + 1 skipped
- Sprint 148 結尾:vitest **1249 + 1 skipped**(+14)

### VR 數變動

- Sprint 147 結尾:mean 0.073191(第 18 連)
- Sprint 148 結尾:mean **0.073191**(**第 19 連 byte-identical**)

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML Parser:86% → **87%**(+1pp、webSettings 5 elements 補完、scope-down 故 +1pp 而非 +2pp)

### Phase 1 capture-only **四連 cluster**(145-148)完成總結

| Sprint | Part | Elements 數 | Test 數 | Phase 1 進度 |
|---|---|---|---|---|
| 145 | footnotes + endnotes | 3 | 12 | 80% → 82% |
| 146 | settings | 9 | 27 | 82% → 84% |
| 147 | fontTable | 7 | 20 | 84% → 86% |
| **148** | **webSettings** | **5 (scope-down)** | **14** | **86% → 87%** |
| **合計** | **5 parts** | **24 elements** | **73** | **+7pp** |

→ Phase 1 OOXML capture **80% → 87%**(+7pp、4 sprint 連發、19 連 byte-identical)。

剩餘未 parsed parts:
- stylesWithEffects.xml(6/42、legacy IE compat、defer)
- 其他 application-specific parts(極少出現)

---

## 紀律

### 紀律 #1.a 第 19 次連續驗證

**連續 4 個 capture-only parser 新模組(Sprint 145/146/147/148)都 byte-identical**、證實「Phase 1 補完模式」可重複套用、對 VR baseline 完全安全。

### 紀律 #18 守護 — scope-down 案例

本 sprint 主動 scope-down 不解析 `<w:divs>` 內部巢狀結構,理由:
- divs 是 docx 匯出 HTML 時用、import 不消費
- 深入解析 = Phase 6 預付工作、違反 PR-size
- 「hasDivs boolean」足夠標示「文件有 / 無 HTML 結構提示」

→ 紀律 #18 應用案例新增:**「儀式性 part 三連完成」可用 scope-down 達成、不必為 closure 而 over-parse**。

### 紀律 #22 第 13 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 148 probe 揭示:
- webSettings.xml 主要內容是 HTML hint、非 import 對象
- divs 結構深層、解析複雜度高、ROI 接近 0
- scope-down 至 5 elements + hasDivs 已涵蓋 100% fixture 實際用到的範圍

### 紀律 #21 應用

> optional 欄位空集合不掛 key

WebSettingsParser:
- 4 toggle 不存在 → undefined
- w:divs 空(無子元素) → hasDivs undefined(不掛 false)
- 與 Sprint 145-147 一致

### 紀律 #1.b 第 12 次驗證正面範例

連續 4 個 capture-only parser 直接實作(本 sprint 含 scope-down)、無翻車。紀律 #1.b 對「capture-only + scope-down」變體類型穩定。

---

## 後續

### Sprint 149 候選(autonomous 已耗盡 §11.2 明列 backlog)

| 候選 | 預期 | 理由 |
|---|---|---|
| **E-7. 進入 wire-up 階段(settings.defaultTabStop → BoxBuilder \t 整合)** | 1-2 sprint | Phase 1 capture 已完整、可進 wire-up;Strategy C 模式可用(若破 VR)|
| E-8. fontTable.altName fallback chain → FontMetricsAdapter wire-up | 2-3 sprint | 與 Sprint 60-65 FontMetricsAdapter 結合 |
| E-9. autonomous docs sprint(Sprint 143-148 cluster retro)| 1 sprint | 沿用 Sprint 120/144 retro 模式 |
| F-1. 等 user 決策 | 0 sprint | session 自然停止點 |

**autonomous 推薦 E-9**(cluster retro):
- Sprint 143-148 6 sprint 累積:紀律 #1.b 升正 + Phase 1 四連 capture + 19 連 byte-identical
- 紀律 #14 即時 retro 比較不會「事後 catch-up」(像 Sprint 143 補做 21-22 sprint 的紀律升正)
- 純 docs、不破 baseline

但若 user 想看 wire-up 進展、可選 E-7(會破 baseline、走 Strategy C 模式)。

### user 介入點(維持 Sprint 145-147 清單)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| 含 footnoteReference docx fixture | 觸發 Sprint 145 wire-up 升級 |
| Sprint 149+ settings/fontTable wire-up GO | 接受首次破 baseline 風險 |

---

## Sprint 148 結尾累積指標

- vitest **1249 passed + 1 skipped**(+14)
- VR mean **0.073191** / failed 0 / compared 126(**第 19 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML 86% → **87%**(webSettings 5 elements capture、scope-down)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 147 → **148**
- **Phase 1 capture-only 四連 cluster(145-148)完成**:5 parts / 24 elements / +73 test / +7pp Phase 1(80→87%)

---

## File-level summary

```
A  static/src/core/ooxml/web-settings/WebSettingsParser.ts  (+95 行 capture-only scope-down parser)
A  static/src/core/ooxml/web-settings/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+30 行 DocumentWebSettings + DocumentNode 1 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+30 行 REL_TYPE_WEB_SETTINGS + Step 6.8 + collectWebSettings)
M  static/src/core/ooxml/document/DocumentParser.ts  (+1 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+1 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+1 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+1 行 constructor patch)
A  tests/unit/WebSettingsParser.test.ts  (+100 行 / 14 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild byte-identical)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild byte-identical)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、0.073191 byte-identical)
A  docs/sprint148_websettings_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 148 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 進度)
```

**Phase 1 capture-only 四連 cluster(Sprint 145-148)完工**、合計 +7pp Phase 1 進度 / +73 test / 第 19 連 byte-identical。紀律 #18 scope-down 案例新增(儀式性收尾不過度設計)。下個 cluster 進入 wire-up 階段或 cluster retro。

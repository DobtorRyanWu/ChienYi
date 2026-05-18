# Sprint 145 — Footnotes / Endnotes Parser capture-only(Phase 3.6 第一階段)

**日期**:2026-05-18
**類型**:code change(parser 新增 + types 擴 + orchestrator 串接、無 wire-up)
**規畫書對應**:§11.2 行 2「Phase 3.6 註腳 / 尾註:30% 政府文件需求」+ Sprint 144 cluster retro §3.4 user 介入點延伸
**前置 sprint**:Sprint 134(textAlignment / framePr capture-only 模式)、Sprint 144(cluster retro)

---

## Hypothesis(驗證對象)

規畫書 §11.2 行 2:

> Phase 3.6 註腳 / 尾註:30% 政府文件需求

Sprint 144 cluster retro §3.4 user 介入點清單延伸:
- abc 三連 probe + DEFER 後、autonomous 仍可做 §11.2 backlog 候選
- 模式 = capture-only(Sprint 134 textAlignment 案例)、不破 baseline

驗證:
1. footnotes.xml / endnotes.xml 結構解析可行性
2. 42 fixture 對 footnote/endnote 真實使用度
3. capture-only 是否真不影響 VR baseline

---

## Method

### 1. Scope 對齊(紀律 #18)

- 規畫書 §11.2 行 2 明列、autonomous 授權範圍
- 本 sprint scope = parser 模組 + types 擴 + orchestrator 串接 + unit test
- **不 wire-up 到 layout / render**(同 Sprint 134 capture-only 模式)
- PR-size:1 新模組 + types +18 行 + OoxmlParser +30 行 + 4 DocumentNode constructors patch + 1 test 檔(12 test)

### 2. 紀律 #22 第 10 次正式應用 — 5 維度 probe

| Probe | 結果 |
|---|---|
| 1. footnotes.xml part 存在於 42 fixture? | ✅ **全部 42/42**(Word 預設骨架)|
| 2. footnoteReference 在 document.xml 內出現? | ❌ **0/42**(無實際 footnote 使用)|
| 3. footnotes.xml 內容結構? | `<w:footnote w:type="separator" w:id="-1">` + `continuationSeparator w:id="0"`(Word 預設)|
| 4. 普通 footnote(w:type 未設、w:id=1+)? | 0/42 真實出現、設計需覆蓋(test 用合成 fixture)|
| 5. 與 HeaderFooterParser 模式對齊度? | 高(都是 `BlockNode[]` content + 重用 DocumentParser)|

→ probe 結論:**真實 fixture 0 wire-up 觸發、但 parser 仍應做**(規畫書 §11.2 明列、為將來 user 提供含 footnoteReference fixture 鋪路)。

### 3. 實作架構

#### 3.1 新模組 `static/src/core/ooxml/footnotes/`

- `FootnotesParser.ts`(+135 行):parse(xml) → Map<id, FootnoteContent>
  - 支援 footnotes.xml(w:footnote 根節點)+ endnotes.xml(w:endnote 根節點)同一 parser
  - 解析 w:type:'separator' / 'continuationSeparator' / 'continuationNotice' / undefined(普通)
  - 解析 w:id 整數(-1 = separator、0 = continuationSeparator、1+ = 普通)
  - 重用 DocumentParser.parseBodyContent 解析 footnote 內部段落 + 表格(同 HeaderFooterParser)
  - 防禦:undefined / 空字串 / XML 解析失敗 → 回空 Map(不阻塞 OoxmlParser)
- `index.ts`:export FootnotesParser

#### 3.2 types.ts 擴

```ts
export interface FootnoteContent {
  id: number;
  type?: 'separator' | 'continuationSeparator' | 'continuationNotice';
  content: BlockNode[];
}

export interface DocumentNode {
  // ... 既有 ...
  footnotes: Map<number, FootnoteContent>;  // Sprint 145
  endnotes: Map<number, FootnoteContent>;   // Sprint 145
  // ... 既有 ...
}
```

#### 3.3 OoxmlParser orchestrator 串接

```ts
// Step 6.5(Sprint 145):Footnotes / Endnotes — capture-only、無 wire-up
const footnotes = collectNotes(pkg, mainDocPath, this.footnotesParser, REL_TYPE_FOOTNOTES);
const endnotes = collectNotes(pkg, mainDocPath, this.footnotesParser, REL_TYPE_ENDNOTES);
```

- 新 REL_TYPE_FOOTNOTES / REL_TYPE_ENDNOTES 常數
- 新 collectNotes helper(取 rels 中 footnotes.xml / endnotes.xml part、parse 後回 Map)
- 在 DocumentNode 填 `footnotes` / `endnotes` 欄位

#### 3.4 4 個既有 DocumentNode constructor patch

| 檔 | patch |
|---|---|
| `DocumentParser.ts` L120 | 加 `footnotes: new Map()` + `endnotes: new Map()` |
| `tests/unit/AstCache.test.ts` | 同上 |
| `tests/unit/IdbAstCache.test.ts` | 同上 |
| `tests/unit/ParagraphStyleMerger.test.ts` | 同上 |
| `tests/unit/ToCanvasEditor.test.ts` | 同上 |

#### 3.5 Unit tests(`tests/unit/FootnotesParser.test.ts`、12 test、4 組)

1. 真實 fixture 結構 — 2 test(separator + continuationSeparator)
2. endnotes.xml 不同 root 標籤 — 1 test
3. 含普通 footnote 內容(合成 fixture) — 2 test
4. 防禦邊界 — 6 test(undefined / 空字串 / XML 失敗 / 未知 type / 缺 id / 非數字 id)
5. w:type 列舉完整 — 1 test(continuationNotice)

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1188 + 1 skipped**(+12 FootnotesParser test、其他 1176 不受 4 個 constructor patch 影響)|
| L2 VR v14 | ✅ **mean 0.073191 / 0 failed / 126 pages**(**第 16 次連續 byte-identical**、capture-only 不破 baseline)|
| L3 Spot check | ✅ TypeScript build PASS(main bundle 35.8s + VR pipeline 30.1s)|
| L4 Odoo backend | **跳過**(無 backend 變動)|

紀律 #1.a 第 16 連 byte-identical 驗證 — 證實「capture-only 新模組」不會破 VR pipeline。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/footnotes/FootnotesParser.ts` | **新增 +135 行** | parser 新模組 |
| `static/src/core/ooxml/footnotes/index.ts` | **新增 +1 行** | export |
| `static/src/core/ooxml/ast/types.ts` | +18 行 | FootnoteContent interface + DocumentNode 2 新欄位 |
| `static/src/core/ooxml/OoxmlParser.ts` | +30 行 | REL_TYPE × 2 + parser 實例 + Step 6.5 + collectNotes helper |
| `static/src/core/ooxml/document/DocumentParser.ts` | +2 行 | DocumentNode constructor patch |
| `tests/unit/AstCache.test.ts` | +2 行 | constructor patch |
| `tests/unit/IdbAstCache.test.ts` | +2 行 | constructor patch |
| `tests/unit/ParagraphStyleMerger.test.ts` | +2 行 | constructor patch |
| `tests/unit/ToCanvasEditor.test.ts` | +2 行 | constructor patch |
| `tests/unit/FootnotesParser.test.ts` | **新增 +165 行 / 12 test** | parser 完整覆蓋 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild | bundle 同步 |
| `tools/dist/visual_regression_pipeline.iife.js` | rebuild | VR pipeline 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | re-run | 0.073191 byte-identical |
| `docs/sprint145_footnotes_capture.md` | 本 audit doc | 紀錄設計 + capture-only rationale |
| `docs/autonomous_roadmap.md` | Sprint 145 ✅ | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |

**淨 production code 變動 = ~186 行新增 + 8 行 patch + 165 行 test**。0 既有 source 邏輯變動(僅加新欄位)。

### Test 數變動

- Sprint 144 結尾:vitest 1176 + 1 skipped
- Sprint 145 結尾:vitest **1188 + 1 skipped**(+12 from FootnotesParser.test)

### VR 數變動

- Sprint 144 結尾:mean 0.073191(第 15 連 byte-identical)
- Sprint 145 結尾:mean **0.073191**(**第 16 連 byte-identical**、capture-only 不破)

### 規畫書 §0.2 Phase 完成度

- Phase 3 Layout Engine:93%(未變、本 sprint 不影響 layout)
- Phase 1 OOXML Parser:80% → **82%**(footnote/endnote parser 補完;wire-up 留將來)

---

## 紀律

### 紀律 #1.a 第 16 次連續驗證

| Sprint | 改動類型 | VR |
|---|---|---|
| 121-126 | parser / utility 補完 | 0.073191 ×6 |
| 130-134 | Phase 4 補完 | 0.073191 ×5 |
| 135 | probe no code | 0.073191 |
| 136 revert | byte-identical | 0.073191 |
| 137-139 | numbering wire-up cluster | 0.073191 ×3 |
| 140-142 | abc 三連 probe DEFER | 0.073191 ×3 |
| 143-144 | docs(紀律升正 + retro) | 0.073191 ×2 |
| **145** | **footnotes/endnotes parser capture-only** | **0.073191** |

→ 紀律 #1.a 第 16 連驗證「capture-only 新模組」類別仍 byte-identical。

### 紀律 #22 第 10 次正式應用

> backlog 開工前先 probe sprint 確認 mental model vs 實況差距

Sprint 145 probe 5 維度(fixture 存在度 / 引用頻率 / 結構複雜度 / 普通 footnote 覆蓋 / parser 模式對齊)、確認:
- parser 應做(規畫書 §11.2 明列)
- wire-up 暫不做(fixture 0 真實引用)
- capture-only 模式套用 Sprint 134 範本

### 紀律 #18 守護

PR-size 守住:純 capture-only、不混入 wire-up、不引入新依賴。

### 紀律 #1.b(本 sprint 第 9 次驗證、含 Sprint 143 升正後)

> spike 後遇結構性問題、scope-down 或完整 revert

本 sprint 是正面範例:probe 確認 capture-only 安全、不需 scope-down、實作直接完成。對照 Sprint 137(probe 主動 scope down 到 capture-only)、Sprint 145 走的是「probe 後直接實作」路徑。

---

## 後續

### Sprint 146 候選(autonomous 推薦)

| 候選 | 預期 | 理由 |
|---|---|---|
| **E-1. 規畫書 §11.2 行 1 — opentype.js 真實字型 metric 加強** | 1-2 sprint | Sprint 60-65 FontMetricsAdapter 已做、但 production migration probe(Sprint 127)結論 Strategy D 維持現狀 — 可重 probe 找小型可實作切片 |
| E-2. 規畫書 §11.2 GPU canvas / Web Worker parse | 大 scope | Phase 7 範圍、autonomous_roadmap §階段 E |
| **E-3. autonomous 再找 §11.2 / §11.1 剩餘候選** | varies | 繼續探索 backlog 邊緣 |
| F-1. 等 user 決策(階段 C / Phase 5 / textAlignment GO)| 0 sprint | session 自然停止點 |

**autonomous 推薦 E-3**(autonomous 再找 backlog 候選):
- Sprint 145 證實「capture-only 模式」可繼續推進 §11.2 backlog
- 已知剩餘:opentype.js 加強(Sprint 60-65 / 127 已 probe defer)、GPU canvas / Web Worker(Phase 7)
- 可能新發現:OOXML §11.2 未列、但 fixture 中真實存在的 capture 機會

### user 介入點(維持 Sprint 144 清單)

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 同意換 baseline + OnlyOffice docker |
| C Phase 5 任一子功能 | fixture + 優先順序 |
| A textAlignment 微弱 wire-up | 確認接受 < 1pt 視覺差 |
| **新增:含 footnoteReference 的 docx fixture** | 觸發 Sprint 145 → wire-up 升級 |

---

## Sprint 145 結尾累積指標

- vitest **1188 passed + 1 skipped**(+12)
- VR mean **0.073191** / failed 0 / compared 126(**第 16 次連續 byte-identical**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML 80% → **82%**(footnote/endnote capture)
- Phase 3 Layout 93%(未變)
- Phase 4 Style 90%(未變)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)
- Sprint audit doc 144 → **145**

---

## File-level summary

```
A  static/src/core/ooxml/footnotes/FootnotesParser.ts  (+135 行 capture-only parser)
A  static/src/core/ooxml/footnotes/index.ts  (+1 行 export)
M  static/src/core/ooxml/ast/types.ts  (+18 行 FootnoteContent + DocumentNode 2 新欄位)
M  static/src/core/ooxml/OoxmlParser.ts  (+30 行 REL_TYPE × 2 + Step 6.5 + collectNotes helper)
M  static/src/core/ooxml/document/DocumentParser.ts  (+2 行 constructor patch)
M  tests/unit/AstCache.test.ts  (+2 行 constructor patch)
M  tests/unit/IdbAstCache.test.ts  (+2 行 constructor patch)
M  tests/unit/ParagraphStyleMerger.test.ts  (+2 行 constructor patch)
M  tests/unit/ToCanvasEditor.test.ts  (+2 行 constructor patch)
A  tests/unit/FootnotesParser.test.ts  (+165 行 / 12 test)
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  tools/dist/visual_regression_pipeline.iife.js  (rebuild)
M  tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  docs/sprint145_footnotes_capture.md  (本 audit doc)
M  docs/autonomous_roadmap.md  (Sprint 145 ✅)
M  dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新 + Phase 1 進度)
```

**Phase 3.6 註腳 / 尾註 parser 完工**(capture-only),為 user 將來提供含 footnoteReference fixture 後 wire-up 鋪路。VR baseline 第 16 連 byte-identical 維持、紀律 #1.a 應用範圍延伸到「capture-only 新 OOXML 子系統」。

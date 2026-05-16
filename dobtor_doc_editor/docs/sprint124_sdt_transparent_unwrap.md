# Sprint 124 — w:sdt 結構化文件標籤透明展開（Phase 1.9）

**日期**：2026-05-17
**類型**：code change（改善 / Phase 1.9 SDT 收口）
**規畫書對應**：§Phase 1.9 SDT 結構化文件標籤 + autonomous_roadmap.md 階段 B 行 2 cluster 1/3
**前置 sprint**：Sprint 123 field code（同 ParagraphParser 範圍、紀律 #1.a 升正式）

---

## Hypothesis

`<w:sdt>`（Structured Document Tag，ECMA-376 §17.5.2）目前被 silent drop：

- DocumentParser body 走訪只認 `w:p` / `w:tbl` / `w:sectPr`
- ParagraphParser 段落走訪只認 `w:r` / `w:fldSimple` / `w:hyperlink`
- 兩處都不認 `w:sdt`、其內容（`<w:sdtContent>`）整段消失

實際影響：Word 表單欄位（plain text content control / rich text / picture / date picker）、Word 自動編號保護區、Mail Merge 欄位範本都用 SDT 包。Silent drop 等於「整個欄位內容不見」。

**Hypothesis**：把 `<w:sdt>` 視為**透明 wrapper**、unwrap 到 `<w:sdtContent>` 的子節點再交給上層 parser 即可。這是 mammoth.js / docx4j 的標準做法。Sprint 124 在 `effectiveChildren()` 中央加 unwrap，三層（block / inline / cell）一次覆蓋。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 2 cluster：「124-126 | Phase 1 OOXML | 1.9 **SDT 結構化標籤**、1.9 bookmark range、1.9 hyperlink rels 完整」
- 規畫書 §Phase 1.9：列「`<w:sdt>` 結構化文件標籤」
- 本 sprint scope = **透明 unwrap**（不解 sdtPr metadata、不渲染 form control 互動）
- 進階：alias / tag / placeholder text / date picker UI 屬規畫書 §Phase 5 候選
- PR-size：dom.ts +15 行 / unit test +160 行 / 1 audit

### 2. Fixture 排查

`<w:sdt>` 在 42 fixture 0 出現（earlier "sdt matches" 是 `sdtdatahash` / `sdtdh` 不同元素）。Sprint 124 預測 VR mean byte-identical（無 fixture trigger）— 與 Sprint 121-123 同型 forward-looking 防禦 sprint。

### 3. 修法（dom.ts effectiveChildren 加 case）

```ts
} else if (child.tagName === 'w:sdt') {
  // Sprint 124 — SDT 結構化文件標籤透明展開（ECMA-376 §17.5.2）
  const sdtContent = directChild(child, 'w:sdtContent');
  if (sdtContent) {
    out.push(...effectiveChildren(sdtContent));  // 遞迴展開（sdtContent 內可能再含 sdt / AlternateContent）
  }
}
```

設計重點：

- **中央處理**：放在 `effectiveChildren()` 內、自動覆蓋 DocumentParser body 層 / parseBodyContent / ParagraphParser._parseInternal / parseRun 內。零下游 caller 改動
- **遞迴展開**：sdtContent 內可能再嵌套 sdt 或 AlternateContent（OOXML 允許）
- **malformed 容錯**：`<w:sdt>` 缺 `<w:sdtContent>` 時跳過（不 throw）
- **sdtPr 忽略**：metadata（tag / alias / id / type）不進 AST。未來如需 form control 互動 / Mail Merge 變數替換、可加 SdtMetadataParser

### 4. 限制（不在本 sprint scope）

- **TableParser row/cell 層 sdt**：TableParser 用 `directChildren` 不是 `effectiveChildren`、本 sprint 中央 unwrap 不覆蓋。Sprint 124+ 候選若有 fixture 需求再補
- **sdtPr metadata**：alias / tag 完全忽略、無 AST 表達
- **form control 互動 UI**：date picker / dropdown 不渲染為 UI 元素

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1010 passed + 1 skipped**（從 1002+1 起、+8 新 Sprint 124 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（與 Sprint 123 baseline byte-identical、**第 4 次連續**）|
| L3 Spot check | ✅ TypeScript build PASS（warning 同前 pre-existing）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

### 6. Unit test 設計（8 個新 test）

| Test | 鎖定行為 |
|---|---|
| block-level w:sdt → 子段落 inline 到 body | 標準 case |
| inline w:sdt → 子 run inline 到段落 | 標準 case |
| w:sdt 缺 sdtContent → 跳過、其他兄弟不受影響 | malformed 容錯 |
| 嵌套 w:sdt 遞迴展開 | sdt in sdt |
| sdt 內含 AlternateContent → 兩層展開都正常 | sdt + mc 共存 |
| sdt 多個段落內容全部 inline | sdtContent 多子節點 |
| sdt 內含 sdtEndPr 不影響 sdtContent 展開 | 容錯 sdtEndPr |
| ParagraphParser 整合：inline sdt → run 進 paragraph.runs | 端到端驗證 |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/utils/dom.ts` | +15 行（effectiveChildren 加 w:sdt 分支）| SDT 透明 unwrap 中央處理 |
| `tests/unit/PhaseB_Plus.test.ts` | +160 行 / 8 新 test | 鎖定 7 個 effectiveChildren SDT case + 1 ParagraphParser 整合 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR confirm（紀律 #1.a 應用）|
| `docs/sprint124_sdt_transparent_unwrap.md` | 本 audit doc | 紀錄 SDT unwrap 設計 |
| `docs/autonomous_roadmap.md` | 階段 B cluster 2 (124-126) 1/3 + 進度表 Sprint 124 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + Phase 1 75→76% | 同步 |

### Test 數變動

- Sprint 123 結尾：vitest 1002 + 1 skipped
- Sprint 124 結尾：vitest **1010 + 1 skipped**（+8）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 123 結尾：mean 0.073191
- Sprint 124 結尾：mean **0.073191**（byte-identical、第 4 次連續 parser 變動 VR 不變）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：75% → **76%**（+1%、1.9 SDT 透明展開補完）

---

## Root cause

**為什麼 SDT silent drop 沒早修**：

1. Sprint 0-2 DocumentParser / ParagraphParser 落地時 focus 主流元素
2. 42 fixture 全是「靜態表單文件」（監造日誌 / 估驗單）、無 Mail Merge / Form Field、SDT 不出現
3. ParagraphParser._parseInternal 註解寫「其他子節點 (w:bookmarkStart, w:proofErr) 暫時忽略」、sdt 也被歸入此類沒明示
4. Sprint 124 階段 B Phase 1.9 cluster 收口、補入口透明 unwrap

**為什麼 effectiveChildren 是正確的位置**：

- 4 個 caller 都用 effectiveChildren（DocumentParser / parseBodyContent / ParagraphParser / parseRun）
- 中央加 case = 一次修四處、不需 caller 改動
- 與既有 AlternateContent unwrap 同一機制、語意一致（兩者都是「透明包裝、unwrap 子節點」）

---

## 紀律

### 紀律 #1.a 應用（Sprint 124）

新升正式紀律 #1.a 在 Sprint 124 第一次應用 — dom.ts 是 parser 子模組、預期 VR 不變但仍跑 → byte-identical。**紀律 #1.a 通過第一次正式應用驗證**。

### 紀律 #18 持續（Sprint 124）

PR-size 守住：dom.ts +15 / test +160 / audit。明示三項不在 scope（cell/row SDT / sdtPr metadata / form control UI），避免 scope creep。

---

## 後續

### Sprint 125（階段 B cluster 2 行 2）

Phase 1.9 bookmark range 完整（`<w:bookmarkStart>` / `<w:bookmarkEnd>`）。

### Sprint 124+ 候選

- TableParser 對 row/cell 層 SDT 補（用 effectiveChildren 取代 directChildren）— PR-size 小、可獨立 sprint
- sdtPr metadata 解析（alias / tag → AST 標籤）— 為 Mail Merge / form fill 鋪路、屬 Phase 5 候選
- date picker / dropdown UI（規畫書 §Phase 5 候選）

---

## Sprint 124 結尾累積指標

- vitest **1010 passed + 1 skipped**（+8）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 4 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 75% → **76%**
- 21 ADR / 19 條紀律 + 6 子 + 1 候選（無變）
- Sprint audit doc 數 123 → **124**
- 階段 B cluster 2 (124-126) 進度 1/3

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/utils/dom.ts  (+15 行 SDT unwrap)
M  addons/dobtor_doc_editor/tests/unit/PhaseB_Plus.test.ts  (+160 行 / 8 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint124_sdt_transparent_unwrap.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 2 1/3 + Sprint 124)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 1 75→76%)
```

無 model / view / ACL / rule 變動。Sprint 124 階段 B cluster 2 起點。

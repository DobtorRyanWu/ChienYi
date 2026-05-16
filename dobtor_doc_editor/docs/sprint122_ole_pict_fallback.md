# Sprint 122 — OLE / VML pict 降級 placeholder（Phase 1.8）

**日期**：2026-05-17
**類型**：code change（改善 / 防禦 / Phase 1 OOXML 1.8 收口）
**規畫書對應**：§Phase 1.8 Drawings 與 OLE + autonomous_roadmap.md 階段 B 行 1 cluster 2/3
**前置 sprint**：Sprint 121 trHeight 入口防禦（同 cluster code change 模式）

---

## Hypothesis

`ParagraphParser.parseRun` 對 `<w:object>`（OLE 嵌入物件）與 `<w:pict>`（VML legacy 圖）目前是 **silent drop**（switch case 沒接、註解寫「暫不處理」）。後果：

- Word 含 OLE（公式 / Excel 物件 / Visio）的段落、在 dobtor renderer 顯示為「空白段落」
- 沒有任何提示告訴使用者「這裡原本有東西」
- Audit trail 缺失（無法知道 docx 內 OLE 數量）

階段 B Phase 1.8 範疇內補 graceful fallback：emit italic 文字 placeholder（`[嵌入物件: <ProgID>]` 或 `[圖片(VML)]`），讓使用者至少知道有嵌入內容、配合 ProgID / alt 顯示類型。

**Hypothesis**：真實 fixture 都不含 `<w:object>` / `<w:pict>` 結構（previous scan 確認）、本 sprint VR 0 變動是預期；但前瞻防禦讓未來 Word 公式 fixture / 第三方 docx 出現 OLE 時不再 silent drop。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 1 cluster：「121-123 | Phase 1 OOXML | 1.5 進階 row height、**1.8 OLE objects 降級渲染**、1.9 field code...」
- 規畫書 §Phase 1.8 列：「`<v:shape>` VML（舊 Word 的圖形） — 降級處理」
- 本 sprint scope = **入口降級 placeholder**（不嘗試實際 OLE blob render、那屬規畫書 §Phase 5.1 OMML→KaTeX 等進階）
- PR-size：ParagraphParser +85 行（含 2 helper）/ unit test +145 行 / docs +1 audit

### 2. 修法

#### 2.1 ParagraphParser.parseRun 加 2 case

```ts
case 'w:object': {
  flushText();
  const placeholder = buildOleFallbackText(child);
  if (placeholder) {
    out.push({ type: 'run', text: placeholder, props: { ...baseProps, italic: true } });
  }
  break;
}
case 'w:pict': {
  flushText();
  const placeholder = buildPictFallbackText(child);
  if (placeholder) {
    out.push({ type: 'run', text: placeholder, props: { ...baseProps, italic: true } });
  }
  break;
}
```

設計重點：
- `italic: true` overlay 於 baseProps（即使 rPr 沒 italic、placeholder 也斜體、視覺暗示是 fallback）
- baseProps 其他屬性（bold / color / size）保留繼承、placeholder 仍順著段落樣式
- 不動 `effectiveChildren` mc:AlternateContent 解包邏輯（既有）

#### 2.2 2 個 helper（同檔尾）

`buildOleFallbackText(objectEl)`：
- 寬鬆 walk 找 `OLEObject`（localName）的 `ProgID` 屬性
- 寬鬆 walk 找 `shape` 的 `alt` 屬性
- 拼裝：`[嵌入物件: <ProgID> — <alt>]` / `[嵌入物件: <ProgID>]` / `[嵌入物件: <alt>]` / `[嵌入物件]`

`buildPictFallbackText(pictEl)`：
- 同樣 walk、但區分 `hasOle`
- 內含 OLE → 走 OLE 文案（VML 只是包 OLE 圖象化）
- 純 VML → `[圖片(VML)]` 或 `[圖片(VML): <alt>]`

寬鬆 walk 用 `el.localName ?? el.tagName.split(':').pop()`：happy-dom / browser 對 namespace 前綴處理不一致（OOXML 真實 docx 偶見 `<OLEObject>` 無前綴或 `<vml:shape>` 改前綴）。

### 3. 真實 fixture scan

```bash
for f in tests/fixtures/*/*.docx; do
  unzip -p "$f" word/document.xml | grep -ciE "<w:object" | { read n; [ "$n" -gt 0 ] && echo "$f: $n"; }
done
# → 0 matches across 42 fixtures
```

`<mc:AlternateContent>` 有大量（drawing / shape 的相容性包裝）、但 `<w:object>` / `<w:pict>` 不出現。本 sprint 0 fixture trigger 新 branch、預測 VR mean byte-identical。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **993 passed + 1 skipped**（從 985+1 起、+8 新 Sprint 122 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（與 Sprint 121 baseline byte-identical）|
| L3 Spot check | ✅ TypeScript build PASS（warning 同 Sprint 121 pre-existing）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

L1 指令：`npx vitest run --reporter=basic`（總 71.8s）
L2 指令：`node scripts/visual_regression_v14.mjs`（總 ~5 min）
L3 指令：`npm run build:frontend`（rollup 27s）

### 5. Unit test 設計（8 個新 test）

| Test | 鎖定行為 |
|---|---|
| w:object 帶 ProgID → italic 文字 placeholder | 標準 case（Word 公式典型） |
| w:object 帶 ProgID + v:shape alt → 兩者組合 | 複合文案 |
| w:object 完全沒 ProgID / alt → 純「[嵌入物件]」 | 防 silent drop |
| w:pict 純 VML（無 OLEObject）→「[圖片(VML)]」 | 區分 OLE vs pure VML |
| w:pict 純 VML 帶 alt → 加 alt 補充 | alt 取出 |
| w:pict 內含 OLEObject → 走 OLE 文案 | VML 包 OLE 圖象化的 case |
| w:object 與 w:t 文字並存 → text run + placeholder run 分離 | flushText 在 OLE 前後切 run 行為 |
| w:object placeholder 繼承 baseProps（rPr bold）+ italic overlay | 樣式繼承不丟、italic 強制 overlay |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/document/ParagraphParser.ts` | +85 行（2 case + 2 helper）| OLE / pict 入口降級 placeholder |
| `tests/unit/ParagraphParser.test.ts` | +145 行 / 8 新 test | 鎖定 8 個 fallback 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #5）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR 確認 0 regression |
| `docs/sprint122_ole_pict_fallback.md` | 本 audit doc | 紀錄 OLE / pict 降級設計 |
| `docs/autonomous_roadmap.md` | 階段 B 121-123 → 2/3 done + 進度表 Sprint 122 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + Phase 1 73→74% | 同步 |

### Test 數變動

- Sprint 121 結尾：vitest 985 + 1 skipped
- Sprint 122 結尾：vitest **993 + 1 skipped**（+8）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 121 結尾：mean 0.073191 / failed 0 / compared 126
- Sprint 122 結尾：mean **0.073191** / failed 0 / compared 126（byte-identical、預測命中）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：73% → **74%**（+1%、1.8 OLE / VML pict 入口降級補完；實際 OLE blob render 仍屬 Phase 5.1 OMML 等進階）

---

## Root cause

**為什麼 OLE / pict silent drop 沒早修**：

1. ParagraphParser Sprint 1 落地時 註解寫「暫不處理」、留 TODO
2. 真實 fixture 不含 `<w:object>` / `<w:pict>`（監造文件 / 工程表單為主、無公式 / 嵌入 Excel）
3. 沒有測試 → 沒被 VR 抓
4. 階段 B Phase 1.8 是規畫書明列項、Sprint 122 收口剛好順手

**為什麼 placeholder 用 italic + 中文文字**：

- 視覺暗示 fallback、與正常文字區別
- 中文文字符合 ChienYi 使用情境（target user 都是中文閱讀者）
- 不用 emoji / 特殊符號避免字型相容性問題

**為什麼寬鬆 walk localName**：

- happy-dom 對 namespace 前綴查 inconsistent（測試環境）
- 真實 docx 偶見前綴變動（`<OLEObject>` 無前綴 / `<vml:shape>` 改前綴）
- localName fallback 保證跨 parser 一致

---

## 紀律

### 紀律 #1 子候選跨 sprint 驗證進展（Sprint 121 → 122）

- Sprint 121：parser 變動跑全 VR（首次應用、TableParser trHeight）
- Sprint 122：parser 變動跑全 VR（第二次應用、ParagraphParser OLE/pict）
- 兩次都 byte-identical、紀律 #1 子候選累積 2 sprint 驗證
- Sprint 123 同 cluster code change 可完成 3 sprint 驗證、升正式 #1.a

### 紀律 #5 持續（Sprint 122）

紀律 #5「vitest 通過不保證 IIFE bundle 同 code 也 work」連續應用：vitest 993 綠 → rebuild bundle → VR pipeline 用 bundle 跑 → byte-identical。

### 紀律 #18 持續（Sprint 122）

PR-size 守住：parser code +85 / test +145 / docs。不擴 scope（如 OLE 實際 blob render / Word 公式 OMML 解析）— 那些屬 Phase 5.1 範疇、不混 Sprint 122。

---

## 後續

### Sprint 123（roadmap 階段 B 行 1 cluster 收尾）

Phase 1.9 field code 完整覆蓋（PAGE / DATE / SEQ / TOC）。同 cluster code change、同 SOP（vitest + bundle + VR）。完成後紀律 #1 子候選跨 3 sprint 驗證 → 可升正式 #1.a。

### Sprint 122+ 候選

- Sprint 5.1 OMML 數學公式真正渲染（規畫書 3-4 週、屬階段 D）— 本 sprint placeholder 是 fallback、未來公式渲染落地時 placeholder branch 可保留為 graceful degradation
- 收集真實含 OLE 的 fixture（user 端公文 / 學術文件）、加 fixture 驗證 placeholder 不 break VR

---

## Sprint 122 結尾累積指標

- vitest **993 passed + 1 skipped**（+8）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 73% → **74%**
- 21 ADR / 18 條紀律 + 6 子 + 2 候選（#1 子候選跨 2 sprint 驗證、待 Sprint 123 完成第 3 次）
- Sprint audit doc 數 121 → **122**
- 階段 B cluster 1 進度 2/3

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+85 行 OLE/pict fallback)
M  addons/dobtor_doc_editor/tests/unit/ParagraphParser.test.ts  (+145 行 / 8 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint122_ole_pict_fallback.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 1 → 2/3 + Sprint 122 進度表)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 1 73→74%)
```

無 model / view / ACL / rule 變動。Sprint 122 階段 B cluster 1 中段。

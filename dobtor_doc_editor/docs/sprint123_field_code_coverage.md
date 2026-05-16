# Sprint 123 — field code 完整覆蓋 PAGE / DATE / SEQ / TOC（Phase 1.9）

**日期**：2026-05-17
**類型**：code change（改善 / 補完 / Phase 1.9 field code 收口）
**規畫書對應**：§Phase 1.9 進階結構（field code 完整覆蓋）+ autonomous_roadmap.md 階段 B 行 1 cluster 3/3
**前置 sprint**：Sprint 121 trHeight / Sprint 122 OLE pict（同 cluster Phase 1 OOXML 收尾）

---

## Hypothesis

`ParagraphParser` 對 field code 的覆蓋有 2 個缺口：

1. **fieldType 集合不全**：`PAGE / NUMPAGES / DATE / TIME / AUTHOR / FILENAME` 已覆蓋，**SEQ / TOC / REF / HYPERLINK / STYLEREF 全部標 'unknown'**。實際 Word 公文 / 學術論文 / 工程文件這些 5 型常用。
2. **複式 fldChar 不解析**：`<w:fldChar>` + `<w:instrText>` 三段式（begin / separate / end）跨多 `<w:r>` 結構被 silent drop。Word 對「動態欄位」（如目錄 / 序號）內部都用複式形式。

階段 B cluster 收尾 sprint、補入口邊界：擴 fieldType 集合 + 加複式 fldChar state machine。同時驗證 Sprint 121 揭示的紀律 #1 子候選（parser 變動跑全 VR）跨 3 sprint。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 1 cluster：「121-123 | Phase 1 OOXML | 1.5 進階 row height、1.8 OLE objects、**1.9 field code 完整覆蓋（PAGE / DATE / SEQ / TOC）**」
- 規畫書 §Phase 1.9：列「`<w:fldSimple>` / `<w:instrText>` 欄位（PAGE、DATE、SEQ、複雜欄位）」
- 本 sprint scope = **入口解析**（fieldType 分類 + 複式 fldChar 收集）；不動 render（欄位值的真實計算屬規畫書 §11.2 行 1）
- PR-size：types 擴 +6 行 / ParagraphParser +85 行（_parseInternal 加 state machine + 2 helper + classifyFieldType 抽函式）/ unit test +145 行（9 新）

### 2. 修法

#### 2.1 types.ts FieldNode.fieldType 擴展

```ts
fieldType:
  | 'PAGE' | 'NUMPAGES'
  | 'DATE' | 'TIME'
  | 'AUTHOR' | 'FILENAME'
  | 'SEQ' | 'TOC' | 'REF' | 'HYPERLINK' | 'STYLEREF'  // ⊕ Sprint 123
  | 'unknown';
```

#### 2.2 抽 classifyFieldType helper

從 parseFldSimple 抽出來、共用給複式 fldChar 收集：

```ts
function classifyFieldType(instruction: string): FieldNode['fieldType'] {
  const firstToken = instruction.trim().split(/\s+/)[0]?.toUpperCase() ?? '';
  const knownTypes = [
    'PAGE', 'NUMPAGES', 'DATE', 'TIME', 'AUTHOR', 'FILENAME',
    'SEQ', 'TOC', 'REF', 'HYPERLINK', 'STYLEREF',
  ] as const;
  return (knownTypes as readonly string[]).includes(firstToken) ? firstToken as ... : 'unknown';
}
```

#### 2.3 _parseInternal 加複式 fldChar state machine

OOXML §17.16.1.7 複式 field 形式：

```xml
<w:r><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:instrText> PAGE </w:instrText></w:r>
<w:r><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:t>7</w:t></w:r>  <!-- cachedValue -->
<w:r><w:fldChar w:fldCharType="end"/></w:r>
```

跨 5 個 `<w:r>` 兄弟、必須在 paragraph 層收集。State machine：

| state | 看到 | 動作 |
|---|---|---|
| null | r 含 fldChar begin | 進 `instr` mode、append instrText |
| instr | instrText | append 到 instruction buffer |
| instr | fldChar separate | 切 `cached` mode |
| cached | w:t | append 到 cachedValue buffer |
| cached / instr | fldChar end | emit FieldNode、回 null mode |
| (segment 結尾未閉合) | — | 段尾強制 emit（malformed docx 容錯） |

實作 2 helper：

- `detectFieldBegin(r)`：純判斷、不消費
- `consumeRunIntoField(r, callbacks)`：處理 r 內 fldChar / instrText / w:t

#### 2.4 入口邏輯

```ts
case 'w:r': {
  const inField = fieldMode !== null;
  const beginFound = !inField && detectFieldBegin(child);
  if (inField || beginFound) {
    consumeRunIntoField(child, ...);  // 內部會 setMode / append / emit
    break;
  }
  for (const node of parseRun(child)) runs.push(node);  // 普通 run
  break;
}
```

關鍵設計：**不 pre-set fieldMode**，由 consumeRunIntoField 內部讀到 begin 才 setMode。早期版本我 pre-set 'instr' 再 call consume、結果 consume 看到 begin 又認為「mode 已存在 = nested begin」並 emit 空 field（修 bug 中發現、見 §Root cause）。

#### 2.5 邊界

- nested begin（field 內又 begin）= malformed、強制 close 前一個再開新
- 段落結尾未閉合 = emit 已收集部分（容錯）
- instrText 跨多 `<w:r>` = 自然 append 串接（OOXML 規格允許 long instruction 切多段）
- separate 後立刻 end（無 cachedValue）= emit field、不設 cachedValue key

### 3. 真實 fixture scan

```bash
for f in tests/fixtures/*/*.docx; do
  unzip -p "$f" word/document.xml | grep -cE "<w:fldChar|<w:fldSimple|<w:instrText"
done
# → 0 across 42 fixtures
```

預測 VR mean byte-identical（無 fixture trigger 新 branch）。已驗證、見 §3 結果。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1002 passed + 1 skipped**（從 993+1 起、+9 新 Sprint 123 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（與 Sprint 122 baseline byte-identical）|
| L3 Spot check | ✅ TypeScript build PASS（warning 同 121/122 pre-existing）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

### 5. Unit test 設計（9 個新 test）

| Test | 鎖定行為 |
|---|---|
| fldSimple SEQ 分類 | 從 unknown 升正式類別 |
| fldSimple TOC 分類 | 同上 |
| fldSimple REF / HYPERLINK / STYLEREF 分類（含 `&quot;` 轉義）| 3 型一次驗 |
| 複式 fldChar PAGE 跨 5 個 w:r | 標準三段式收集 |
| 複式 fldChar instrText 跨多 w:r 串接 | long instruction 切多段（OOXML 允許）|
| 複式 fldChar 無 cachedValue（separate→end 直連）| cachedValue 該 key 不存在 |
| 複式 fldChar 段落結尾未閉合（malformed）| 強制 emit 容錯 |
| 複式 fldChar 與普通文字並存 | run / field / run / field 順序保留 |
| 複式 fldChar TOC instruction 含空白 trim 正常 | instruction 清洗 |

既有 test `w:fldSimple unknown` 改用 `XYZGIBBERISH` 取代 `SEQ`（因 SEQ 升正式類）。

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | +6 行 | FieldNode.fieldType 擴 SEQ/TOC/REF/HYPERLINK/STYLEREF |
| `static/src/core/ooxml/document/ParagraphParser.ts` | +85 行（state machine + 2 helper + classifyFieldType 抽函式）| 複式 fldChar 解析 + fieldType 擴 |
| `tests/unit/ParagraphParser.test.ts` | +145 行 / 9 新 test（含既有 `SEQ` test 改 `XYZGIBBERISH`）| 鎖定 9 個 field code 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #5）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR confirm 0 regression |
| `docs/sprint123_field_code_coverage.md` | 本 audit doc | 紀錄 field code 收口設計 |
| `docs/autonomous_roadmap.md` | 階段 B 121-123 cluster ✅ + 進度表 Sprint 123 | cluster 1 完成 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + Phase 1 74→75% | 同步 |

### Test 數變動

- Sprint 122 結尾：vitest 993 + 1 skipped
- Sprint 123 結尾：vitest **1002 + 1 skipped**（+9）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 122 結尾：mean 0.073191 / failed 0
- Sprint 123 結尾：mean **0.073191** / failed 0（byte-identical、第 3 次連續 parser 變動 VR 不變）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：74% → **75%**（+1%、1.9 field code 入口解析補完；field 真實值的 render-time 計算屬規畫書 §11.2 候選）

### 紀律 #1 子候選跨 3 sprint 驗證完成

| Sprint | 變動類型 | rebuild bundle | VR run | VR mean |
|---|---|---|---|---|
| 121 | parser (TableParser trHeight) | ✅ | ✅ | byte-identical |
| 122 | parser (ParagraphParser OLE/pict) | ✅ | ✅ | byte-identical |
| 123 | parser (ParagraphParser fldChar) | ✅ | ✅ | byte-identical |

→ **紀律 #1 子候選升正式為 #1.a**：「**改 parser / style / layout 任一層、即使預期 VR 不變、仍應 rebuild bundle + 跑全 VR 確認**」。

---

## Root cause

**為什麼 fieldType 集合不全 / 複式 fldChar 不解析這麼久才修**：

1. Sprint 1 ParagraphParser 落地時 focus 簡式 `<w:fldSimple>` + 6 個 hard-coded type
2. 真實 fixture 不含 field（監造 / 工程文件以靜態文字為主）、無 VR 觸發
3. 註解寫「w:fldChar 暫不處理（Sprint 123 候選）」、留 TODO
4. 階段 B Phase 1.9 是規畫書明列項、Sprint 123 cluster 收尾

**為什麼第一版 state machine 撞 nested begin bug**：

我 pre-set `fieldMode='instr'` 再 call `consumeRunIntoField` 處理含 begin 的 r。consume 內部看到 begin 又判斷「mode!==null = nested」並 emit 空 field。修法：**不 pre-set mode、由 consume 內部讀 begin 才 setMode**。

教訓（紀律候選）：**state machine 的 mode 變更應集中在一處（consume 內部）、callsite 不應預設**。Sprint 124+ 若有類似 state machine、可驗證此模式。

---

## 紀律

### 紀律 #1.a 升格正式紀律（Sprint 123 完成跨 3 sprint 驗證）

> **#1.a**：**改 parser / style resolver / layout engine 任一層、即使預期 VR 不變、也應 rebuild bundle + 跑全 42 fixture VR 確認**。
>
> **Why**：parser → layout → renderer 三層任一變動都可能傳到 VR。Sprint 121-123 連 3 次都是 happy case（byte-identical），但「以為不變」與「跑了確認不變」差距是隱性 assumption 風險。
>
> **How to apply**：
> - 改任一 parser / style / layout 檔案、commit 前必跑 `npm run build:frontend` + `node scripts/visual_regression_v14.mjs`
> - VR mean 變動 > 0.0001 即視為 regression、停手 audit
> - 純 docs / security / backend 變動不需跑 VR（保留紀律 #1 原版 scope）

### 紀律 #5 持續（Sprint 123）

連續 3 sprint vitest 綠 → rebuild → VR byte-identical、紀律 #5 應用穩定。

### 紀律 #18 持續（Sprint 123）

PR-size 守住：types +6 / parser +85 / test +145 / audit +1。不擴 scope（如 field 真實值 render 計算、屬規畫書 §11.2 候選）。

---

## 後續

### Sprint 124（階段 B cluster 2 開工）

階段 B Sprint 124-126：Phase 1 OOXML 1.9 進階（SDT / bookmark range / hyperlink rels 完整）。Sprint 124 候選 = SDT 結構化文件標籤（`<w:sdt>`）。

### Sprint 123+ 候選

- field 真實值 render 計算（PAGE 動態值、DATE 用當前日期、SEQ counter）— 屬規畫書 §11.2 / Phase 5 候選
- TOC 自動生成（讀文件 heading 結構 → 生成 ToC 內容）— Phase 5 候選
- HYPERLINK field 與 `<w:hyperlink>` element 整合（兩個都是連結、目前分開處理）— 收口候選

---

## Sprint 123 結尾累積指標

- vitest **1002 passed + 1 skipped**（+9）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、第 3 次連續）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 74% → **75%**
- 21 ADR / **19 條紀律**（紀律 #1.a 升正式）+ 6 子 + 1 候選（#20 集中索引 §0 段）
- Sprint audit doc 數 122 → **123**
- 階段 B cluster 1 (121-123) **完成**、進入 cluster 2 (124-126)

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/ast/types.ts  (+6 行 FieldNode.fieldType 擴)
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+85 行 state machine + helpers)
M  addons/dobtor_doc_editor/tests/unit/ParagraphParser.test.ts  (+145 行 / 9 新 test、SEQ 既有 test 改 XYZGIBBERISH)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint123_field_code_coverage.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 1 121-123 ✅ + Sprint 123)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 1 74→75% + 紀律 19 條)
```

無 model / view / ACL / rule 變動。Sprint 123 階段 B cluster 1 收口。

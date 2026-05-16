# Sprint 125 — bookmark range 完整覆蓋（Phase 1.9）

**日期**：2026-05-17
**類型**：code change（改善 / Phase 1.9 bookmark 收口）
**規畫書對應**：§Phase 1.9 bookmark range + autonomous_roadmap.md 階段 B 行 2 cluster 2/3
**前置 sprint**：Sprint 124 SDT 透明 unwrap（同 cluster 結構標記類）

---

## Hypothesis

`<w:bookmarkStart>` / `<w:bookmarkEnd>`（ECMA-376 §17.13.6）目前 silent drop：

- DocumentParser body 註解寫「`w:bookmarkStart` 等通常僅作標記」
- ParagraphParser 註解寫「其他子節點 (w:bookmarkStart, w:proofErr) 暫時忽略」

結果：

- 段落內的 bookmark 名稱完全丟失
- `<w:hyperlink w:anchor="myBookmark">` 無法在 dobtor 內反查到目標
- REF / PAGEREF field 無法解析
- PDF 匯出無法生成內部跳轉錨點

**Hypothesis**：bookmark 純錨點、不影響 render；只需把名稱 capture 到 ParagraphNode.bookmarks 列表、未來下游 features 可消費。預期 VR byte-identical（即使 fixture 真實含 20 `_GoBack`）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 2 cluster：「124-126 | Phase 1 OOXML | 1.9 SDT、1.9 **bookmark range**、1.9 hyperlink rels 完整」
- 規畫書 §Phase 1.9：列「`<w:bookmarkStart>` / `End`」
- 本 sprint scope = **capture 段落內 bookmark 名稱**（不解 colFirst / colLast cell-range、不建 cross-paragraph map）
- 不在 scope：DocumentNode 全域 bookmark → 段落 location map（屬 hyperlink resolution、Sprint 126 候選）
- PR-size：types.ts +9 行 / ParagraphParser +30 行 / unit test +110 行 / 1 audit

### 2. Fixture 排查

```bash
total=0
for f in tests/fixtures/*/*.docx; do
  c=$(unzip -p "$f" word/document.xml | grep -cE "<w:bookmarkStart")
  total=$((total+c))
done
# → 20 bookmarkStart across 42 fixtures，全是 Word 自動生成的 _GoBack
```

**Sprint 121-124 是 0 fixture trigger；Sprint 125 首次有真實 fixture trigger（20 個）**。

VR 預期仍 byte-identical（bookmarks 不影響 render layout / pixels）— 但這是首次本 cluster 對「真實有資料的元素」做 capture。VR 結果是 byte-identical 還是漂移、是 Sprint 125 的重點實驗（紀律 #1.a 應用）。

### 3. 修法

#### 3.1 types.ts ParagraphNode 加 optional bookmarks

```ts
export interface ParagraphNode {
  type: 'paragraph';
  props: ParagraphProps;
  runs: InlineNode[];
  styleId?: string;
  bookmarks?: string[];  // Sprint 125
}
```

設計選擇：

- **`string[]` 不是 `Map`**：每段落 bookmark 量通常 ≤ 2、array 簡單
- **去重**：同 name 重複 bookmarkStart 只記一次（Set 收集 → Array 輸出）
- **bookmark 在 cross-paragraph 範圍**：本 sprint 只記「本段落內 start 的 name」、跨段落 range 不解（未來如需要可加 DocumentNode 全域 map）

#### 3.2 ParagraphParser _parseInternal 加 bookmark 收集

兩個位置會出現 bookmark：

```
<w:p>
  <w:bookmarkStart w:name="A"/>          <!-- 段落直屬 -->
  <w:r>
    <w:bookmarkStart w:name="B"/>        <!-- w:r 內含（真實 docx 常見）-->
    <w:t>text</w:t>
    <w:bookmarkEnd w:id="B"/>
  </w:r>
  <w:bookmarkEnd w:id="A"/>
</w:p>
```

實作：

```ts
const bookmarkNames = new Set<string>();
const collectBookmarksFromRun = (r: Element): void => {
  for (const c of directChildren(r)) {
    if (c.tagName === 'w:bookmarkStart') {
      const name = c.getAttribute('w:name');
      if (name) bookmarkNames.add(name);
    }
  }
};

// 在 switch 內：
case 'w:r':
  collectBookmarksFromRun(child);  // 先收
  // ... 既有 field state machine / parseRun ...
case 'w:hyperlink':
  // 對 hyperlink 內每個 w:r 也收
case 'w:bookmarkStart':
  // 段落直屬
case 'w:bookmarkEnd':
  // 純結尾、無 name、跳過
```

#### 3.3 輸出時掛 key（避免 AST diff noise）

```ts
if (bookmarkNames.size > 0) {
  node.bookmarks = Array.from(bookmarkNames);
}
```

沒 bookmark 的段落不掛 key、與 Sprint 120 之前的 AST byte-identical（重要：紀律 #1.a 跑 VR 必過）。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1018 passed + 1 skipped**（從 1010+1 起、+8 新 Sprint 125 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（**真實 20 fixture bookmark 被 capture、但 render byte-identical**、第 5 次連續）|
| L3 Spot check | ✅ TypeScript build PASS（warning 同前 pre-existing）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

**Sprint 125 是本 cluster 首個對真實 fixture 元素做 capture 的 sprint、VR byte-identical 證明 bookmarks AST 變動完全 isolated 在資料層、不漏到 render**。

### 5. Unit test 設計（8 個新 test）

| Test | 鎖定行為 |
|---|---|
| 段落內單一 bookmark（直屬 w:p）→ bookmarks=[name] | 標準 case |
| w:r 內嵌 bookmarkStart → 仍被段落層 capture | 真實 docx 常見結構 |
| 多個 bookmark 都被收集、去重 | Set 行為 |
| 沒 bookmark 的段落 → bookmarks key 不存在 | AST diff 0 noise |
| Word 自動生成的 _GoBack 也被捕捉 | fixture 真實 case |
| bookmark 名稱缺失（malformed）→ 不收集、不 throw | 容錯 |
| hyperlink 內 w:r 含 bookmarkStart → 段落層 capture | hyperlink + bookmark 共存 |
| bookmark 與 field 共存 → 兩者都 capture | field + bookmark 共存（紀律 #18 確認不互相影響）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | +9 行（ParagraphNode.bookmarks）| Optional 欄位、不破壞既有 consumer |
| `static/src/core/ooxml/document/ParagraphParser.ts` | +30 行（bookmark 收集 + 輸出時掛 key）| 段落直屬 + w:r 內含 + hyperlink 內 三路收集 |
| `tests/unit/ParagraphParser.test.ts` | +110 行 / 8 新 test | 鎖定 8 個 bookmark 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR 確認 0 regression（real bookmarks capture 不影響 render）|
| `docs/sprint125_bookmark_range_coverage.md` | 本 audit doc | 紀錄 bookmark 收口設計 + 首次真實 fixture trigger 驗證 |
| `docs/autonomous_roadmap.md` | cluster 2 (124-126) 2/3 + 進度表 Sprint 125 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + Phase 1 76→77% | 同步 |

### Test 數變動

- Sprint 124 結尾：vitest 1010 + 1 skipped
- Sprint 125 結尾：vitest **1018 + 1 skipped**（+8）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 124 結尾：mean 0.073191
- Sprint 125 結尾：mean **0.073191**（byte-identical、第 5 次連續、**首次有真實 fixture trigger 仍 byte-identical**）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：76% → **77%**（+1%、1.9 bookmark range 入口 capture 補完）

---

## Root cause

**為什麼 bookmark silent drop 沒早修**：

1. Sprint 0-2 落地時 bookmark 在 ParagraphParser / DocumentParser 註解都明說「暫時忽略」、有 TODO 痕跡
2. 42 fixture 內 20 bookmark 全是 `_GoBack`（Word 自動生成、純編輯記憶）、無實質連結用途、silent drop 視覺上無感
3. 沒有 hyperlink anchor / REF field 用到 bookmark 的 fixture trigger
4. Sprint 124 補 SDT 後、bookmark 是 cluster 2 自然下一個收口項

**為什麼 VR 在首次有真實 trigger 仍 byte-identical**：

- bookmarks 是 AST 資料層欄位、不影響 layout（不撐長 / 撐寬段落）
- 不影響 renderer（mapper / ToCanvasEditor 不消費 bookmarks）
- 設計選擇「沒 bookmark 不掛 key」確保既有段落 AST byte-identical
- 「資料層 capture vs render 影響」分離乾淨 — 這是紀律 #1.a 期望看到的健康訊號

---

## 紀律

### 紀律 #1.a 強化驗證（Sprint 125）

Sprint 124 第一次正式應用紀律 #1.a 是「dom.ts utility 0 fixture trigger」、形式驗證。Sprint 125 升級為「**ParagraphParser 真實 fixture trigger 仍 byte-identical**」、實質驗證紀律 #1.a 的價值：

> 即使「20 fixture 真的撞到 bookmarks 收集邏輯」、跑 VR 確認 render unchanged 才能 commit。如果省略 VR、可能漏網「bookmarks 不小心被 mapper 渲染成可見內容」這類 bug。

### 紀律 #18 持續

PR-size 守住：types +9 / parser +30 / test +110 / audit。明示 scope 邊界：DocumentNode 全域 bookmark map / cross-paragraph range / cell-column bookmark 都不在本 sprint。

### 新候選（Sprint 125 揭示）

> **紀律 #21 候選**：**新加 AST optional 欄位、預設「不掛 key」而非「掛 undefined / null / []」**。
>
> **Why**：Sprint 125 bookmarks 若預設掛 `bookmarks: []`、所有段落 AST byte 變動、紀律 #1.a 跑 VR 可能看到雜訊（即使 render 不變、cache key 可能變）。「沒值不掛 key」確保 AST byte-identical、cache key 穩定、未來 mapper / serializer 工作量降低。
>
> **How to apply**：
> - 新 optional 欄位空集合時不 set
> - JSON serialization 透過 `if (size > 0)` 守門
> - Test 用 `toBeUndefined()` 而非 `toEqual([])`

候選未升正式紀律、需跨 3 sprint 驗證（Sprint 126 / 後續若同樣手法即可驗證）。

---

## 後續

### Sprint 126（階段 B cluster 2 收尾）

Phase 1.9 hyperlink rels 完整。可消費本 sprint capture 的 bookmark names 做 anchor → paragraph 反查（如果有跨段落需求）。

### Sprint 125+ 候選

- DocumentNode 全域 bookmark map（cross-paragraph anchor resolution）— Sprint 126 hyperlink rels 自然 cousin
- `<w:bookmarkStart w:colFirst w:colLast>` cell-range bookmark（table-aware bookmark、規畫書 §1.5.3 邊界）
- REF / PAGEREF field 解析（fldChar 已落地、+ bookmark resolution = 完整內部引用）
- PDF export 用 bookmarks 生成內部跳轉（屬 Phase 6 docx export 對稱）

---

## Sprint 125 結尾累積指標

- vitest **1018 passed + 1 skipped**（+8）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 5 次連續**、**首次真實 fixture trigger 仍 byte-identical**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 76% → **77%**
- 21 ADR / 19 條紀律 + 6 子 + **2 候選**（+ #21 候選 Sprint 125 「optional 欄位空時不掛 key」）
- Sprint audit doc 數 124 → **125**
- 階段 B cluster 2 (124-126) 進度 2/3

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/ast/types.ts  (+9 行 ParagraphNode.bookmarks)
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+30 行 bookmark 收集)
M  addons/dobtor_doc_editor/tests/unit/ParagraphParser.test.ts  (+110 行 / 8 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint125_bookmark_range_coverage.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 2 2/3 + Sprint 125)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 1 76→77%)
```

無 model / view / ACL / rule 變動。Sprint 125 階段 B cluster 2 中段、首次真實 fixture trigger 驗證紀律 #1.a。

# Sprint 126 — hyperlink rels 完整覆蓋（Phase 1.9 cluster 2 收尾）

**日期**：2026-05-17
**類型**：code change（改善 / Phase 1.9 hyperlink rels 收口）
**規畫書對應**：§Phase 1.9 hyperlink rels + autonomous_roadmap.md 階段 B 行 2 cluster 3/3
**前置 sprint**：Sprint 125 bookmark range（同 cluster、為 hyperlink anchor reverse-lookup 鋪路）

---

## Hypothesis

`HyperlinkInfo` 目前 4 個欄位（`rId / url / anchor / tooltip`）；ECMA-376 §17.16.22 完整 `<w:hyperlink>` 還有：

- `w:tgtFrame`：HTML 風格 target 視窗（`_blank` / `_self` / `_parent` / `_top` / 自訂 frame 名）— Web/HTML 匯出時必要
- `w:history`：是否計入瀏覽歷史（OOXML 布林：`"1"`/`"true"`/`"0"`/`"false"`）— Word visited 樣式判斷
- `w:docLocation`：替代文件位置（早期 Word 跨文件連結）

這 3 屬性目前 silent drop。階段 B cluster 2 收尾、補完。

**Hypothesis**：與 Sprint 121-125 同型 — 真實 fixture 0 hyperlink（earlier 確認）、VR 預期 byte-identical（紀律 #1.a 第 6 次連續驗證）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 2 cluster：「124-126 | Phase 1 OOXML | 1.9 SDT、1.9 bookmark range、1.9 **hyperlink rels 完整**」
- 規畫書 §Phase 1.9：列「`<w:hyperlink>` + rels 查詢」
- 本 sprint scope = **HyperlinkInfo 擴 3 個 OOXML 屬性 + 防禦 edge case**
- 不在 scope：anchor → bookmarks 反查 map（屬 DocumentNode 全域 lookup、未來 sprint）、 hyperlink visited UI 樣式渲染（屬 §Phase 5）
- PR-size：types +12 行 / ParagraphParser parseHyperlinkInfo +15 行 / test +145 行 / 1 audit

### 2. Fixture 排查

```bash
total=0
for f in tests/fixtures/*/*.docx; do
  c=$(unzip -p "$f" word/document.xml | grep -cE "<w:hyperlink")
  total=$((total+c))
done
# → 0 hyperlink across 42 fixtures
```

與 Sprint 121-124 同型 0 trigger。VR 預期 byte-identical。

### 3. 修法

#### 3.1 types.ts HyperlinkInfo 擴 3 欄位

```ts
export interface HyperlinkInfo {
  rId?: string;
  url?: string;
  anchor?: string;
  tooltip?: string;
  tgtFrame?: string;     // Sprint 126
  history?: boolean;     // Sprint 126
  docLocation?: string;  // Sprint 126
}
```

#### 3.2 parseHyperlinkInfo 加 3 屬性讀取

```ts
const tgtFrame = el.getAttribute('w:tgtFrame') ?? undefined;
const docLocation = el.getAttribute('w:docLocation') ?? undefined;
const historyRaw = el.getAttribute('w:history');
let history: boolean | undefined;
if (historyRaw === '1' || historyRaw === 'true') history = true;
else if (historyRaw === '0' || historyRaw === 'false') history = false;

if (tgtFrame) info.tgtFrame = tgtFrame;
if (history !== undefined) info.history = history;  // false 是合法值、不能用 if (history)
if (docLocation) info.docLocation = docLocation;
```

設計細節：

- **OOXML 布林雙形式**：`"1"` / `"true"` 都解析為 `true`、`"0"` / `"false"` 都解析為 `false`；缺則 undefined（不要 default 為 false）
- **`history === false` 是合法值**：要用 `if (history !== undefined)` 而非 `if (history)`、否則 false 會被丟
- **紀律 #21 候選遵守**：空值不掛 key（Sprint 125 揭示的 candidate）

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1028 passed + 1 skipped**（從 1018+1 起、+10 新 Sprint 126 test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 6 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（warning 同前 pre-existing）|
| L4 Odoo backend | **跳過**（無 backend 變動）|

### 5. Unit test 設計（10 個新 test）

| Test | 鎖定行為 |
|---|---|
| w:tgtFrame=_blank → tgtFrame=_blank | 標準 target 視窗 |
| w:history="1" → history=true | OOXML 布林 "1" |
| w:history="0" → history=false（顯式禁止計入歷史）| OOXML 布林 "0"、false 是合法值 |
| w:history="true" / "false" 兩種布林字串同樣解析 | 雙形式支援 |
| w:history 缺 → history 不在 info 內（紀律 #21 候選）| 空值不掛 key |
| w:docLocation 跨文件位置 | docLocation + url 並存 |
| External + anchor 共存（跨文件指定位置）| External URL + anchor 並存（rare 但合法）|
| 五屬性全帶 → 全部出現在 HyperlinkInfo | 完整路徑 |
| rId 存在但 lookup 沒命中 → url undefined、rId 仍保留 | 防禦 broken rels |
| 完全空的 w:hyperlink → 段落 runs 空、hyperlink undefined | 邊界 |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | +12 行（HyperlinkInfo 擴 3 欄位 + JSDoc 擴充）| API 擴充 |
| `static/src/core/ooxml/document/ParagraphParser.ts` | +15 行（parseHyperlinkInfo 加 3 屬性讀取）| 解析邏輯 |
| `tests/unit/PhaseB_Plus.test.ts` | +145 行 / 10 新 test | 鎖定 10 個 hyperlink 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR confirm |
| `docs/sprint126_hyperlink_rels_completeness.md` | 本 audit doc | 紀錄 hyperlink 收口設計 |
| `docs/autonomous_roadmap.md` | cluster 2 (124-126) ✅ + 進度表 Sprint 126 | cluster 2 完成 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + Phase 1 77→78% | 同步 |

### Test 數變動

- Sprint 125 結尾：vitest 1018 + 1 skipped
- Sprint 126 結尾：vitest **1028 + 1 skipped**（+10）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 125 結尾：mean 0.073191
- Sprint 126 結尾：mean **0.073191**（byte-identical、第 6 次連續）

### 規畫書 §0.2 Phase 完成度

- Phase 1 OOXML：77% → **78%**（+1%、1.9 hyperlink rels 完整覆蓋）

---

## Root cause

**為什麼 hyperlink 3 屬性沒早補**：

1. Sprint 1 落地時 focus 主流 4 屬性（rId / url / anchor / tooltip）— 已涵蓋 80% Web 連結需求
2. tgtFrame / history / docLocation 是 Word 桌面版 / 跨文件連結特性、ChienYi 監造文件少用
3. 42 fixture 0 hyperlink → 無 VR trigger
4. Sprint 126 階段 B Phase 1.9 cluster 收尾、補完

**為什麼 history 用 `if (history !== undefined)` 不用 `if (history)`**：

- false 是合法值（user 顯式禁止計入歷史）
- `if (history)` 會把 false 也判為 truthy-false 而漏掛 key
- 揭示了 Sprint 125 紀律 #21 候選的細節：**對 boolean 欄位空集合檢測要用 `!== undefined`、不能用 truthy**

---

## 紀律

### 紀律 #1.a 第 3 次正式應用（Sprint 126）

連續 3 sprint code change 都跑全 VR：

- Sprint 124（dom.ts utility）byte-identical
- Sprint 125（ParagraphParser bookmark capture、首次真實 trigger）byte-identical
- Sprint 126（parseHyperlinkInfo 擴 3 屬性、0 fixture trigger）byte-identical

紀律 #1.a 已穩固、6 次連續 byte-identical（121-126）。

### 紀律 #21 候選跨 sprint 驗證進展 1 → 2

- Sprint 125 揭示「optional 欄位空集合不掛 key」
- Sprint 126 套用：`tgtFrame / history / docLocation` 全部「有值才掛 key」、history 特別處理 false vs undefined
- 跨 sprint 驗證 2 次、待 Sprint 127+ 完成第 3 次可升正式

### 紀律 #18 持續

PR-size 守住：types +12 / parser +15 / test +145 / audit。明示 3 項不在 scope（anchor → bookmark map / visited UI 樣式 / cross-doc resolution）。

---

## 後續

### Sprint 127（階段 B cluster 3 開工）

階段 B Sprint 127-128：Phase 2 字型，**把 FontMetricsAdapter 推到 production**（目前 opt-in、Sprint 64b external 候選 — Claude 自主執行 migrate doc_editor.js 走自家 pipeline）。

注意：Sprint 127 性質與 121-126 不同 — 可能會動 VR mean（FontMetricsAdapter 從 opt-in 變 production = 走過 -2.3% 路徑驗證）。Sprint 121-126 連 6 次 byte-identical 的 cluster 收尾、Sprint 127 開始進「實質改善」階段。

### Sprint 126+ 候選

- DocumentNode 全域 bookmark map（消費 Sprint 125 ParagraphNode.bookmarks）+ hyperlink anchor reverse-lookup（消費 Sprint 126 anchor）— 兩個 sprint 的協同延伸、屬「跨段落 resolution」
- HYPERLINK field（複式 fldChar）與 `<w:hyperlink>` element 統一處理（Sprint 123 揭示候選）
- 早期 Word `<v:line>` / `<v:rect>` 等 VML 連結形式（罕見、屬 Phase 5 候選）

---

## Sprint 126 結尾累積指標

- vitest **1028 passed + 1 skipped**（+10）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 6 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 77% → **78%**
- 21 ADR / 19 條紀律 + 6 子 + 2 候選（#20 集中索引 §0 段 1/3、#21 optional 欄位空值不掛 key 2/3）
- Sprint audit doc 數 125 → **126**
- 階段 B cluster 2 (124-126) **完成**、進入 cluster 3 (127-128) Phase 2 字型

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/ast/types.ts  (+12 行 HyperlinkInfo 擴 3 欄位)
M  addons/dobtor_doc_editor/static/src/core/ooxml/document/ParagraphParser.ts  (+15 行 parseHyperlinkInfo)
M  addons/dobtor_doc_editor/tests/unit/PhaseB_Plus.test.ts  (+145 行 / 10 新 test)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint126_hyperlink_rels_completeness.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 2 ✅ + Sprint 126)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 1 77→78%)
```

無 model / view / ACL / rule 變動。階段 B cluster 2 完成、6 sprint 連跨 byte-identical 紀律 #1.a 穩定驗證。

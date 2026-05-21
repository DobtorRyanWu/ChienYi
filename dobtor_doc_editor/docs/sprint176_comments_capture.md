# Sprint 176 — comments.xml 註解 capture（Phase 5.5）

**日期**：2026-05-22
**類型**：parser（capture-only、Phase 5.5 註解）
**規畫書對應**：§5 階段 D Phase 5.5「註解」
**前置**：決策 C（user 2026-05-21 GO）；user 同意 synthetic fixture
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Phase 5.5 註解：Word 註解（「校閱 → 新增註解」）儲存於 `word/comments.xml`、
document.xml 以 `<w:commentRangeStart/End w:id>` + `<w:commentReference w:id>` 引用。

`comments.xml` 結構與 footnotes.xml 同構（`<w:comment w:id w:author w:date w:initials>`
內含段落 / 表格）。本 sprint 比照 Sprint 145 FootnotesParser 做 CommentsParser capture。

---

## 修法

### 1. `CommentContent` 型別 + `DocumentNode.comments`（types.ts、+22 行）

`id` + `author` / `date` / `initials` + `content: BlockNode[]`。
`DocumentNode.comments: Map<number, CommentContent>` 非 optional、空 Map = 無
comments.xml —— 與 `footnotes` / `endnotes` 同模式（Map-valued part）。

### 2. 新檔 `static/src/core/ooxml/comments/CommentsParser.ts`（+105 行）

`parse(xml) → Map<number, CommentContent>`：走訪 `<w:comments>` 子元素、對每個
`<w:comment>` 解 `w:id`（非數字跳過）+ `w:author`/`w:date`/`w:initials`（缺則不掛）、
重用 `DocumentParser.parseBodyContent` 解析註解內部段落 / 表格。完全比照 FootnotesParser。

### 3. `OoxmlParser` Step 6.5b + `collectComments` helper（+約 20 行）

`collectComments` 走訪 mainDoc rels、找 `REL_TYPE_COMMENTS` part、parse。
`REL_TYPE_COMMENTS` 常數新增。DocumentNode literal 加 `comments`。

### 4. `DocumentParser` lite DocumentNode 建構子補 `comments: new Map()`（+1 行）

因 `comments` 非 optional、DocumentParser 的 standalone DocumentNode 建構子同步補
（比照既有 `footnotes`/`endnotes`）。

### Scope-down（紀律 #18）

- **capture-only**：document.xml 的 `commentRangeStart/End`/`commentReference` 錨點
  wire-up + 右側註解 panel render 留後續 sprint。
- comment 內的巢狀修訂（`<w:ins>`/`<w:del>`）由既有 ParagraphParser 自動處理（Sprint 174）。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1450 → 1459 passed + 1 skipped**（+9 CommentsParser）。涵蓋 id/author/date/initials + 內容段落 / 多則註解 / 缺 author-date-initials / w:id 非數字跳過 / 無 w:id / 空輸入 / XML 失敗 / 非 w:comment 忽略 |
| **L2 VR v14** | frontend + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 36 連）。capture-only、layout/render 不消費 comments → byte-identical（同 footnotes capture archetype） |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.5 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 重建（OoxmlParser 在依賴樹內）。
- flake8：不適用（0 行 Python）。

---

## Root cause

註解自始未被 capture。Phase 5.5「註解」= `comments.xml` 解析。本 sprint 完全比照
Sprint 145 FootnotesParser 的 notes-part archetype（XML part → `Map<id, content>`、
重用 `DocumentParser.parseBodyContent`）—— comments.xml 與 footnotes.xml 同構、
parser 結構幾乎一致。capture-only、layout/render 不消費 → VR byte-identical。

---

## 紀律

- **#1.a / Strategy C**：capture-only、layout/render 不消費 comments → VR byte-identical
  第 36 連（同 Sprint 145-153 capture-only / footnotes archetype）。
- **#14（模組化 + 一致性）**：CommentsParser 自成 `comments/` 子目錄、完全比照
  FootnotesParser；`DocumentNode.comments` 比照 `footnotes`/`endnotes` 的 Map-valued part。
- **#21**：CommentContent 的 author/date/initials 缺則不掛。
- **#18 scope-down**：capture-only、commentRange 錨點 wire-up + panel render 留後續。
- **#8 / 決策 C**：synthetic XML 驗 parser（user 同意、tests/fixtures 無 Phase 5 樣本）。

---

## 後續

- **commentRange 錨點 wire-up**：document.xml 的 `<w:commentRangeStart/End>`/
  `<w:commentReference>` 解析、把 comment id 對應到文字範圍。
- **註解 panel render**：右側註解面板（Portal UI 範疇）。
- **決策 C 可控部分（5.4/5.5/5.6）至此完成**；剩餘為決策 C 大塊（5.1 OMML / 5.2
  SmartArt / 5.3 Charts、需 user 提供真實 fixture）+ 決策 B（OnlyOffice goldens 重生）
  + 小 follow-up（framePr 邊緣項 / 圖片浮水印 render / themeColor→hex）。

---

## Sprint 176 結尾累積指標

- vitest **1459 passed + 1 skipped**（+9）
- VR mean **0.073191**（byte-identical 第 36 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 175 → 176
- 新檔 `comments/CommentsParser.ts`、新型別 `CommentContent`、`DocumentNode.comments`
- **Phase 5.5「註解」capture 完成；決策 C 可控部分（5.4 + 5.5 + 5.6）全數完成**

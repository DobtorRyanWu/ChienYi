# Sprint 177 — commentRange / commentReference 註解錨點 capture（Phase 5.5）

**日期**：2026-05-22
**類型**：parser（capture-only、Phase 5.5 註解錨點、小 follow-up cluster）
**規畫書對應**：§5 階段 D Phase 5.5「註解」
**前置**：Sprint 176（comments.xml 內容 capture）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 176 capture 了 `comments.xml` 的註解**內容**（`DocumentNode.comments`），但
document.xml 端的「哪段文字引用哪則註解」錨點未 capture。本 sprint 補上文件側錨點：
- `<w:commentRangeStart w:id>` / `<w:commentRangeEnd w:id>`：標記被註解的文字範圍
- `<w:r><w:commentReference w:id></w:r>`：註解標記錨點（run 內）

完成後註解系統 capture 端閉合：`comments.xml` 內容 ↔ document.xml 位置。

現況 probe：ParagraphParser 無 commentRange / commentReference case → 完全忽略。

---

## 修法

### 1. `ParagraphNode.commentRefs?`（types.ts、+6 行）

`commentRefs?: number[]` —— 此段落引用的註解 id（去重、升序）。比照 Sprint 125
`ParagraphNode.bookmarks?: string[]`（同為段落層級的錨點 capture）。

### 2. ParagraphParser — 錨點收集（+約 16 行）

- `collectBookmarksFromRun` 更名 `collectRunAnchors`（3 callsites）並擴充：原掃
  `<w:bookmarkStart>`，現同時掃 `<w:commentReference w:id>` → `commentIds` Set。
- 段落子元素 loop 加 `case 'w:commentRangeStart':`（收 `w:id`）+ `case 'w:commentRangeEnd':`
  （純結尾、id 與 Start 相同、不重複收）。
- 段落結束：`commentIds` 非空 → `node.commentRefs = sort(Array.from(...))`（紀律 #21）。
- `collectRunAnchors` 在 `w:r` / hyperlink 內 run / ins-del 內 run 三處皆呼叫
  → commentReference 在這三種包裹下都被收。

### Scope-down（紀律 #18）

- capture 段落層級的 commentRefs（哪段引用哪註解）；註解 panel render、
  commentRange 精確字元範圍（start/end 之間的子範圍）留後續。
- `<w:commentReference>` 視為錨點標記、不產生可見 run（同 bookmarkStart 處理）。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1459 → 1464 passed + 1 skipped**（+5 ParagraphParser）。涵蓋 commentRangeStart + commentReference 收 id / 多 id 升序去重 / 無註解不掛 / w:id 非數字跳過 / hyperlink 內 run 的 commentReference 也收 |
| **L2 VR v14** | frontend + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 37 連）。commentRefs 為 capture-only metadata、layout/render 不消費 → byte-identical |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.5 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 重建（ParagraphParser 在依賴樹內）。
- flake8：不適用（0 行 Python）。

---

## Root cause

Sprint 176 只 capture 註解內容、未 capture 文件側錨點 —— commentRange / commentReference
在 ParagraphParser 無 case 被忽略。本 sprint 比照 Sprint 125 bookmark 錨點 capture
模式（`ParagraphNode.bookmarks`）補 `commentRefs`：複用既有 `collectRunAnchors`
（原 bookmark 掃描器）同時掃 commentReference，段落層級加 commentRangeStart case。
capture-only、layout/render 不消費 → VR byte-identical。

---

## 紀律

- **#1.a / Strategy C**：capture-only、layout/render 不消費 commentRefs → VR byte-identical 第 37 連。
- **#14（DRY + 一致性）**：`commentRefs` 比照 `bookmarks` 段落錨點 capture 模式；
  錨點掃描複用 `collectRunAnchors`（原 bookmark 掃描器、擴充而非另造）。
- **#21**：`commentRefs` 非空才掛 key。
- **#18 scope-down**：段落層級 commentRefs、不做精確字元範圍 / panel render。

---

## 後續

- 註解 panel render（右側註解面板、Portal UI 範疇）。
- commentRange 精確字元範圍（commentRangeStart/End 之間的子範圍標記）。
- 小 follow-up cluster 剩餘：framePr Sprint 171 optional 邊緣項、圖片浮水印 render、
  `<w:background>` themeColor→hex。
- 大塊：決策 B（OnlyOffice goldens 重生）、決策 C 大塊 5.1 OMML / 5.2 SmartArt /
  5.3 Charts（需 user 提供真實 fixture）。

---

## Sprint 177 結尾累積指標

- vitest **1464 passed + 1 skipped**（+5）
- VR mean **0.073191**（byte-identical 第 37 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 176 → 177
- 新欄位 `ParagraphNode.commentRefs?`
- Phase 5.5「註解」capture 端閉合（內容 176 + 錨點 177）

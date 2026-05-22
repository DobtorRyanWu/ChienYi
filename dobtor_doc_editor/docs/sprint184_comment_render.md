# Sprint 184 — 註解 render wire-up（Phase 5.5 收尾）

**日期**：2026-05-23
**類型**：mapper render wire-up（Phase 5.5 註解、線性文字 fallback）
**規畫書對應**：§5 階段 D Phase 5.5「註解（`<w:commentRangeStart>`、右側 panel、回覆、解決狀態）」
**前置**：Sprint 176（comments.xml capture）、Sprint 177（commentRange/Reference 錨點 capture）；決策 C（user 2026-05-21 GO）

---

## Hypothesis

Phase 5.5 註解 capture 端已閉合（Sprint 176 內容 `DocumentNode.comments` +
Sprint 177 錨點 `ParagraphNode.commentRefs`），但兩者都是 capture-only —— 註解
內容從未 render 到輸出。本 sprint 補 render wire-up，收 Phase 5 最後一個 render 缺口。

**render 策略 — 線性文字 fallback**（同 Sprint 180 OMML / 183 SmartArt·Chart、
與 user mc:Fallback 壓縮決策一致）：
- canvas-editor 無 Word 右側註解 panel 的對應 element type。
- 降級策略：在被註解段落的 runs 之後 append `[註解 作者: 內容]` 標記。
- 精確錨點範圍 highlight（`commentRangeStart`→`End` 字元區間）+ 互動式
  panel（回覆 / 解決狀態）留未來 optional sprint。

---

## 修法

### 1. `commentToText`（CommentsParser.ts、+約 35 行）

`commentToText(comment)`：把 `CommentContent.content`（BlockNode[]）攤平為純文字。
- `blocksToText` 遞迴：段落 → 取 `type==='run'` 的 run 文字拼接；表格 →
  遞迴每個 cell 內容。多段落以空白串接。
- 比照 Sprint 180/183 `ommlToLinearText` / `smartArtToText` / `chartToText`，
  render-text 函式放 parser 同檔。

### 2. ToCanvasEditor render wire-up（+約 25 行）

- 新增 instance 欄位 `comments: Map<number, CommentContent>`，`convert()` 開頭
  以 `doc.comments` 重設（比照 Sprint 183 `smartArtsByRId` / `chartsByRId`）。
- `appendParagraph`：runs + math 之後，若 `para.commentRefs` 非空 → 逐 id 查
  `this.comments`，以 `commentToText` 取內容、append
  `[註解 ${author}: ${body}]`（無 author → `[註解: ${body}]`）。
- 查無對應註解 id → 跳過（不 crash、不 emit）。

### 3. 測試（+10）

- `tests/unit/CommentsParser.test.ts`（+5）：`commentToText`（單段落 / 同段落
  多 run / 多段落空白串接 / 表格遞迴 cell / 空內容）。
- `tests/unit/ToCanvasEditor.test.ts`（+5）：被註解段落 append
  `[註解 作者: 內容]`、無 author 變體、多 commentRefs 依序、查無 id 跳過、
  無 commentRefs 段落不受影響。
- `makeDoc` 測試 helper 補 `comments: new Map()`（DocumentNode 必填欄位、
  Sprint 176 加入後測試 helper 未同步、本 sprint 一併修正）。

---

## Result

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | full suite 1641 → **1651 passed + 1 skipped**（+10） |
| L2 VR v14 | ✅ **byte-identical 第 44 連** | rendered 42/42、comparedPages 126、failedPages 0；0/42 baseline fixture 含 `commentRefs` → render 新分支 0 觸發 |
| L3 visual spot check | ✅ 線性文字 fallback | 被註解段落後出現 `[註解 作者: 內容]` 標記 |

- `tsc --noEmit`：2 個 pre-existing error（FontMetrics opentype.js / SettingsParser
  position enum）、**無新增**。
- frontend bundle + VR IIFE bundle 重建（CommentsParser / ToCanvasEditor 在依賴樹）。

---

## 紀律

- **#1.b / Strategy C**：render 新分支只在 `para.commentRefs` 非空時觸發；
  0/42 baseline fixture 含註解錨點 → render 路徑不變 → byte-identical 第 44 連。
- **#1.a**：改 mapper 跑全 42 fixture VR。
- **#14（DRY）**：`commentToText` 比照 `ommlToLinearText` / `smartArtToText` /
  `chartToText` 放 parser 同檔；`comments` 查表比照 Sprint 183 `smartArtsByRId`；
  ToCanvasEditor 複用既有 `appendChars` / `mapRunProps`。
- **#18 scope-down**：線性文字 fallback（非 Word 右側 panel）；精確錨點範圍
  highlight + 回覆 / 解決狀態互動留未來 optional。**與 user mc:Fallback 壓縮
  決策一致**。
- **#14.b 旁支修正**：`makeDoc` 測試 helper 缺 `comments` 必填欄位（Sprint 176
  DocumentNode 加 `comments` 後未同步、tsc 不檢查 test 檔故未爆）；本 sprint
  render wire-up 首次在測試中讀 `doc.comments` 而暴露、一併補正。

---

## 後續

- 註解精確錨點範圍 highlight（`commentRangeStart`→`End`）+ 互動式 panel
  （回覆 / 解決狀態）— 未來 optional sprint。
- **Phase 5 全 6 子功能 render 全數完成**（5.1 OMML / 5.2 SmartArt / 5.3 Charts /
  5.4 追蹤修訂 / 5.5 註解 / 5.6 浮水印背景）。
- 下一步：Phase 6 docx export 對稱性（0% 起步）。

---

## Sprint 184 結尾累積指標

- vitest **1651 passed + 1 skipped**（`npm test` 全套；+10）
- VR mean **0.073191**（byte-identical 第 44 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 183 → **184**
- Phase 5 全 6 子功能 capture + render 全數完成

---

## File-level summary

```
M  static/src/core/ooxml/comments/CommentsParser.ts   commentToText + blocksToText（+約 35）
M  static/src/core/ooxml/mapper/ToCanvasEditor.ts     comments 查表 + commentRefs render（+約 25）
M  tests/unit/CommentsParser.test.ts                  +5 test
M  tests/unit/ToCanvasEditor.test.ts                  +5 test + makeDoc 補 comments 欄位
M  static/src/lib/canvas_editor/canvas-editor-custom.umd.js(.map)  bundle 重建
M  tools/dist/visual_regression_pipeline.iife.js      VR bundle 重建
```

**淨 production code 變動 = +約 60 行**、線性文字 fallback render、VR byte-identical
第 44 連、Phase 5 全 6 子功能 capture + render 全數完成。

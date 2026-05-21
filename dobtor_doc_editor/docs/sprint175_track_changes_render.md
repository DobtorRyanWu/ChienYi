# Sprint 175 — 追蹤修訂 render wire-up（Phase 5.4 收尾）

**日期**：2026-05-22
**類型**：layout + render wire-up（Phase 5.4 追蹤修訂、Strategy C）
**規畫書對應**：§5 階段 D Phase 5.4「追蹤修訂」
**前置**：Sprint 174（`<w:ins>`/`<w:del>` capture → `RunNode.revision`）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 174 把 `<w:ins>`/`<w:del>` capture 進 `RunNode.revision`（capture-only）。
本 sprint 補 render：把 `revision` 從 RunNode 流經 layout 到 Box、CanvasRenderer
依 `Box.revision` 繪追蹤修訂標記（插入底線 / 刪除刪除線），Phase 5.4 收尾。

---

## 修法

### 1. `Box.revision?`（layout/types.ts、+2 行）

`Box` 新增 `revision?: RunRevision`（inline import、同 `imageSrcRect` 模式）。

### 2. BoxBuilder 透傳 `revision`（+約 6 行）

`pushRunItems` 把 `run.revision` 傳入 `pushTextAsBoxes` → `boxOf`。`boxOf` 簽名加
optional `revision` 參數、有值才掛 `box.revision`（紀律 #21、無 revision box 不掛 key）。
numbering prefix 路徑補 `undefined` 參數。

### 3. CanvasRenderer `renderBox` 追蹤修訂裝飾（+14 行）

`renderBox` 裝飾段（`drawTextDecorations` gating 內）新增：
- `box.revision?.type === 'ins'` → 畫底線（baseline + fontSize×0.15）
- `box.revision?.type === 'del'` → 畫刪除線（baseline − fontSize×0.3）
- run 本身已有對應裝飾（underline / strike）時不重畫、避免雙線

刪除文字仍 `fillText` 繪出（markup view：刪除文字加刪除線、不隱藏）。

### Strategy C（紀律 #1.b）

0/42 fixture 含 `<w:ins>`/`<w:del>`（Sprint 174 已 grep 確認）→ 所有 Box 的
`revision` 皆 undefined → renderBox 新分支 0 觸發 → 42 fixture VR byte-identical。
追蹤修訂裝飾只對「真有修訂的 docx」改變輸出。

### Scope-down（紀律 #18）

- 裝飾用 run 既有顏色、不套 per-author 修訂色（Word 行為、留後續 polish）。
- 刪除採 markup view（刪除線、不隱藏）；「最終版」隱藏刪除文字 = accept/reject
  transform 範疇、留後續。
- mapper（ToCanvasEditor、production canvas-editor 路徑）不在本 sprint scope。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1445 → 1450 passed + 1 skipped**（+5 CanvasRenderer 追蹤修訂 render）。涵蓋無 revision → 無裝飾 drawLine / ins → 底線 / del → 刪除線且刪除文字仍繪 / ins 底線在基線下 del 刪除線在基線上 / drawTextDecorations=false 不畫 |
| **L2 VR v14** | VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 35 連）。0 fixture 含修訂 → renderBox 新分支 0 觸發 |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.4 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 不重建（CanvasRenderer / BoxBuilder / layout types 非 frontend bundle 依賴樹）。
- flake8：不適用（0 行 Python）。

---

## Root cause

Sprint 174 capture 後 `revision` 無 render consumer。本 sprint 接通 layout→render
鏈：`revision` 比照 `hyperlink`（既有 RunNode→Box 透傳的 optional metadata）流到
`Box`，renderBox 依 `Box.revision` 繪裝飾、複用既有 underline / strike drawLine 邏輯
（紀律 #14 DRY）。Strategy C：0 fixture 覆蓋 → byte-identical。

Phase 5.4「追蹤修訂」二 sprint 收尾：capture（174）、render（175）。

---

## 紀律

- **#1.b / Strategy C**：revision 只在真有修訂時改輸出、0 fixture → byte-identical 第 35 連。
- **#1.a**：改 layout + render 路徑跑全 42 fixture VR。
- **#14（DRY + 一致性）**：`revision` 透傳比照 `hyperlink` RunNode→Box 模式；裝飾繪製
  複用 renderBox 既有 underline / strike drawLine 邏輯。
- **#21**：`Box.revision` 無值不掛 key。
- **#18 scope-down**：per-author 修訂色 / 刪除隱藏（accept-reject）/ mapper 路徑 留後續。

---

## 後續

- **accept/reject transform**：解析修訂的 AST transform —— Portal UI 範疇、更後期。
- per-author 修訂色、巢狀 ins/del、moveFrom/moveTo、屬性修訂。
- mapper（ToCanvasEditor）追蹤修訂 → production canvas-editor render。
- **Phase 5.5 註解**（`<w:commentRangeStart>` / comments.xml）—— 決策 C 可控部分剩餘項。

---

## Sprint 175 結尾累積指標

- vitest **1450 passed + 1 skipped**（+5）
- VR mean **0.073191**（byte-identical 第 35 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 174 → 175
- **Phase 5.4「追蹤修訂」收尾**（capture 174 / render 175；accept-reject + per-author 色留後續）

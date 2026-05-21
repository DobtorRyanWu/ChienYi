# Sprint 174 — `<w:ins>` / `<w:del>` 追蹤修訂 capture（Phase 5.4）

**日期**：2026-05-21
**類型**：parser（capture-only、Phase 5.4 追蹤修訂）
**規畫書對應**：§5 階段 D Phase 5.4「追蹤修訂」
**前置**：決策 C（user 2026-05-21 GO）；user 同意 synthetic fixture
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Phase 5.4 追蹤修訂：Word「追蹤修訂」的插入 / 刪除標記。
- `<w:ins>`（OOXML §17.13.5.18）：包裹 `<w:r>` 的插入修訂、帶 `w:author`/`w:date`/`w:id`
- `<w:del>`（§17.13.5.14）：包裹 `<w:r>` 的刪除修訂、內含 `<w:delText>`（非 `<w:t>`）

現況 probe：ParagraphParser 段落子元素 loop 處理 `w:r`/`w:fldSimple`/`w:hyperlink`/
`w:bookmarkStart-End`，**無 `w:ins`/`w:del` case → 追蹤修訂內容完全被丟棄**。
`effectiveChildren` 只展開 `mc:AlternateContent`/`w:sdt`、不展開 ins/del。

42/42 fixture 無 `<w:ins>`/`<w:del>`（grep 確認）→ capture 必 VR byte-identical。

---

## 修法

### 1. `RunRevision` 型別 + `RunNode.revision?`（types.ts、+24 行）

`type`（'ins'/'del'）+ `author` / `date`（ISO raw）/ `id`。`RunNode.revision?` 與既有
`RunNode.hyperlink?` 同模式（容器包裹時填入的 optional metadata）。

### 2. ParagraphParser — `<w:delText>` 文字讀取（+2 行）

`parseRun` 的 `w:t` case 改為 `case 'w:t': case 'w:delText':` —— `<w:delText>` 與
`<w:t>` 結構相同（純文字 + xml:space），同樣 `textBuf += textContent`。

### 3. ParagraphParser — `w:ins` / `w:del` 段落子元素 case（+約 20 行）

段落子元素 loop 新增 `case 'w:ins': case 'w:del':`：
- `parseRevision(child, type)` 解析 `w:author`/`w:date`/`w:id`（id 非數字 → 不掛）
- 展平 `effectiveChildren` 中的 `<w:r>`、`parseRun` 後對 `type==='run'` 節點掛 `revision`
- 同時收集 run 內 bookmark（沿用 `collectBookmarksFromRun`）
- revision 物件跨同容器多 run 共用 reference（同 hyperlink linkInfo 模式）

### Scope-down（紀律 #18）

- **capture-only**：render（插入底線 / 刪除刪除線 / 隱藏）留 Sprint 175。
- 只處理 `<w:ins>`/`<w:del>` 直接包裹的 `<w:r>`；巢狀 ins/del、ins/del 內含
  `<w:hyperlink>`、`<w:moveFrom>`/`<w:moveTo>` 移動修訂、`<w:pPrChange>`/`<w:rPrChange>`
  屬性修訂、段落標記修訂（`<w:pPr><w:rPr><w:del/>`）→ 留後續 sprint。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1439 → 1445 passed + 1 skipped**（+6 ParagraphParser）。涵蓋 `<w:ins>` author/date/id / `<w:del>` 文字來自 `<w:delText>` / 無 author 只掛 type / 多 run 共用 revision / 修訂 run 與一般 run 混排順序保留 / w:id 非數字不掛 |
| **L2 VR v14** | frontend + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 34 連）。42 fixture 全無 ins/del → 新 case path 0 觸發 → byte-identical by construction |
| **L3 spot check** | docs 與 §5 階段 D Phase 5.4 一致；audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 重建（ParagraphParser 在依賴樹內）。
- flake8：不適用（0 行 Python）。

---

## Root cause

追蹤修訂自始未被 capture —— ParagraphParser 的段落子元素 loop 無 `w:ins`/`w:del` case，
插入文字與刪除文字（`<w:delText>`）連同 author/date 全部丟棄。本 sprint 補上 case：
ins/del 視為「包裹 run 的容器」（同 hyperlink 模式）、展平 runs 並掛 `revision` metadata。
capture-only、render 留 Sprint 175 —— 與 watermark cluster（172 capture / 173 render）
同分工模式。0 fixture 覆蓋 → VR byte-identical。

---

## 紀律

- **#1.a / Strategy C**：capture-only、0 fixture 覆蓋 → 新 case path 不觸發 →
  42 fixture VR byte-identical 第 34 連（同 Sprint 145-153 / 172 capture archetype）。
- **#22（probe-first）**：開工前 probe 確認 ins/del 現況（無 case → 丟棄）+ grep
  確認 0 fixture 覆蓋 → capture 必 byte-identical、寫 code 前即知。
- **#21**：`revision` optional、`id` 非數字不掛、無 author/date 不掛。
- **#14（一致性）**：`revision` 比照 `hyperlink` 的 RunNode optional metadata 模式；
  ins/del 容器展平比照 `w:hyperlink` 處理。
- **#18 scope-down**：capture-only、只處理直接 `<w:r>`、巢狀 / move / 屬性修訂留後續。
- **#8 / 決策 C**：synthetic XML 驗 parser（user 同意、tests/fixtures 無 Phase 5 樣本）。

---

## 後續

- **Sprint 175**：追蹤修訂 render —— CanvasRenderer / mapper 依 `RunNode.revision`
  繪插入（底線 + author 色）/ 刪除（刪除線）。需 `revision` 流經 layout 到 Box
  或 renderer 端讀取。
- **accept/reject**：解析修訂的 AST transform（accept ins = 保留、accept del = 移除；
  reject 反之）—— 屬 Portal UI 範疇、更後期。
- 巢狀 ins/del、moveFrom/moveTo、pPrChange/rPrChange 屬性修訂。
- 之後 Phase 5.5 註解（`<w:commentRangeStart>` / comments.xml）。

---

## Sprint 174 結尾累積指標

- vitest **1445 passed + 1 skipped**（+6）
- VR mean **0.073191**（byte-identical 第 34 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 173 → 174
- 新型別 `RunRevision`、`RunNode.revision?`
- Phase 5.4「追蹤修訂」capture 完成；render 留 Sprint 175

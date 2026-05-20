# Sprint 164 — bookmark render wire-up probe → honest DEFER

**日期**：2026-05-21
**類型**：probe + scope 重分類（docs-only、0 行 production code）
**規畫書對應**：§5 Phase 1.9 L358 `<w:bookmarkStart>` / `<w:bookmarkEnd>`
**前置**：Sprint 125（bookmark capture-only）、Sprint 160 v1（footnote/endnote stub → DEFER 範式）
**執行**：user 主導互動式 session（非 autopilot loop）

---

## Hypothesis

state.json `phase_1_wire_up_batch.items[sprint:164]` 定義 Sprint 164 = `bookmarkStart-end-render`：
把 Sprint 125 capture 的 bookmark（`ParagraphNode.bookmarks: string[]`）真實接到 render
端——「renderer 在 layout 流內註冊 bookmark anchor、hyperlink 解析能找到 bookmark
target」。

DoD 明確要求**開工前先 probe**（紀律 #22）：確認 canvas-editor / renderer 是否有
anchor 概念；若無真實 consumer，誠實 DEFER、不可硬塞 stub（Sprint 160 v1 失敗模式）。

---

## Method — probe

### 1. canvas-editor element type 盤點

```
grep -oE "ElementType\.[A-Z]+" canvas-editor.umd.min.js | sort -u
→ AREA BLOCK CHECKBOX CONTROL DATE HYPERLINK IMAGE LABEL LATEX LIST
  PAGE RADIO SEPARATOR SUBSCRIPT SUPERSCRIPT TAB TABLE TEXT TITLE
```

**無 `ElementType.BOOKMARK`、無 anchor element type**。`anchor` / `Anchor` 字串在
bundle 內出現處與 bookmark 無關（影像 anchor 定位、vMerge anchor rowspan）。

### 2. canvas-editor hyperlink 能力

`ElementType.HYPERLINK` 的 IElement 僅支援外部 `url` 屬性，**無「文件內錨點跳轉」
（internal anchor navigation）概念**。canvas-editor 渲染到 `<canvas>`、不是 DOM，
`#fragment` 形式的 URL 也無法觸發捲動到錨點。

### 3. mapper `ToCanvasEditor.appendRun`（L265-282）現況

```ts
if (run.hyperlink && (run.hyperlink.url || run.hyperlink.anchor)) {
  const linkEl: CEElement = { type: 'hyperlink', value: '', valueList: innerElements };
  if (run.hyperlink.url) linkEl.url = run.hyperlink.url;   // anchor 案例：什麼都不設
  out.push(linkEl);
}
```

內部 anchor 連結（`HyperlinkInfo.anchor` 有值、`url` 無值）→ 產出的 `hyperlink`
IElement **完全不帶 anchor 資訊**，canvas-editor 收到一個指向虛無的連結。
`ParagraphNode.bookmarks` 在 mapper 端**完全不被消費**。

---

## Result — honest DEFER

§5 L358「bookmark **render 消費**」的真實定義（state.json `true_wireup_definition`）：
「render / mapper 端必須能在 layout 流內註冊 bookmark anchor、hyperlink 解析路徑能
找到 bookmark target」。

此定義**無法在不改動 canvas-editor 的前提下達成**：

- canvas-editor 無 bookmark/anchor element type → 無處可「註冊 anchor」
- canvas-editor hyperlink 無內部跳轉 → 即使 mapper 解析出 target 也無 render 端可消費

任何「現在硬接」的作法都只能：在 mapper 設一個 `linkEl.url = '#' + anchor` 的死連結
（canvas-editor 渲染成可點但點了不動的 hyperlink）。這是 capture 偽裝成 wire-up、
屬 DoD `anti_patterns` 與 Sprint 160 v1 失敗模式，**禁止**。

→ **honest DEFER**。bookmark render 消費的真實前置 = canvas-editor 具備 anchor 概念，
這正是 **decision 2B（Strategy B 直接 patch canvas-editor、排 Sprint 166-170）** 的
工作範疇。

### 變更（docs-only、0 行 production code）

| 檔 | Δ |
|---|---|
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §5 L358 bookmark 改標 `(Phase 1 optional)` + 內聯說明；§1.9 彙整 block 加「第三批（bookmark optional）」 |
| `docs/progress_snapshot.md` | §1 Sprint 164 結尾指標；§3 Phase 1 列註記 |
| `docs/INDEX.md` | 加 sprint164 索引 |
| `docs/sprint164_bookmark_render_defer.md` | 本 audit doc |
| `.antigravity/autopilot/state.json` | current_sprint 164→165、bookmark item status→deferred |

§5 L358 維持 `[ ]`、**不打 `[x]`**（DoD：DEFER 時不動 checkbox）。改標 `(Phase 1 optional)`
後依 Phase 1 Exit Criteria「所有非 `(Phase 1 optional)` 標記的 `[ ]` 已 `[x]`」，
bookmark 不再擋 Phase 1 Exit。

---

## Root cause

**為什麼 bookmark render 一直接不通**：

1. Sprint 125 設計上就是 capture-only——audit doc §後續已明寫「mapper / ToCanvasEditor
   不消費 bookmarks」、render 端消費列為「未來 features」
2. canvas-editor 原始定位是「中文表單系統」、無文件內導覽需求 → 無 anchor 概念
3. 真實 render 消費必須等 canvas-editor 被 patch（decision 2B）才有著力點

**與 footnote/endnote（第二批 Phase 1 optional）的同構性**：footnote/endnote 的 render
依賴 Phase 5.4 渲染管線；bookmark 的 render 依賴 Phase 2 canvas-editor patch。兩者都是
「capture 已完整、render 消費依賴後續 Phase 的基礎建設」——故同樣處理（標 Phase 1
optional、不擋 Exit）。

---

## 紀律

### 紀律 #22（probe-first）正面案例

Sprint 160 v1 沒先 probe footnote/endnote 有無 consumer、直接寫 stub → reverted。
Sprint 164 嚴格遵守 DoD「開工前先 probe」：3 步 probe（element type / hyperlink 能力 /
mapper 現況）在寫任何 code 前完成、提早識別「無真實 consumer」→ 0 行 production code
變動、0 stub、0 revert 風險。

### 紀律 #18（scope 重分類走 user 認可）

bookmark 從 Phase 1 必做項改標 Phase 1 optional = planning doc scope 重分類。
依紀律 #18 經 user 認可後執行（user 於 2026-05-21 互動 session 選「honest DEFER」）。
比照 Sprint 159（commit 85e5e81）/ Sprint 160 v1（commit a20d2f9）的 scope 修正範式。

### 紀律 #8（架構發現也是 sprint 產出）

「canvas-editor 無 bookmark/anchor element type」是本 sprint 的架構發現。docs-only
sprint 無 code 變動、但 probe 結論為 Sprint 165 Phase 1 Exit 與 Sprint 166-170
canvas-editor patch 範疇提供明確輸入——屬有實質產出的 sprint（ADR-020 範式）。

---

## 三層 SOP

| 層 | 結果 |
|---|---|
| L1 vitest | 不適用（docs-only、0 行 .ts/.js 變更、by construction 不變、維持 1361 passed + 1 skipped） |
| L2 VR | 不適用（render 路徑 0 變更、維持 mean 0.073191） |
| L3 spot check | docs 內容自審：§5 L358 + 彙整 block + Exit Criteria 三處一致 |
| L4 Odoo backend | 不適用（無 backend 變更） |

---

## 後續

- **Sprint 165**：Phase 1 Exit re-verify。Group A wire-up 缺口收斂為「instrText done
  （Sprint 160 v2）+ bookmark deferred（本 sprint）+ footnote/endnote deferred」→
  非-optional `[ ]` 應已全 `[x]`、可評估 Phase 1 過 Exit。
- **Sprint 166-170（decision 2B）**：canvas-editor patch 時，bookmark anchor render
  消費應納入——屆時 §5 L358 才有真實 wire-up 條件。
- bookmark 的其他下游（REF / PAGEREF field 解析、PDF export 內部跳轉錨點）見
  [sprint125 audit §後續](sprint125_bookmark_range_coverage.md)。

---

## Sprint 164 結尾累積指標

- vitest 1361 passed + 1 skipped（未動）
- VR mean 0.073191（未動）
- Odoo backend 31 passed（未動）
- Sprint audit doc 162 → 163
- §5 Phase 1.9 bookmark 改標 Phase 1 optional（第三批）
- 0 行 production code 變更

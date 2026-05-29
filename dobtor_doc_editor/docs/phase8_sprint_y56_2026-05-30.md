# Phase 8 Sprint Y56 — 底線/刪除線 forward toggle（補完 B/I/U/S）（2026-05-30）

**性質**：spec sprint（補完 B/I/U/S）+ 順手 flaky sweep。Y51 鎖了粗體完整 toggle（on→off cycle）+ 斜體 forward；Y56 補底線（executeUnderline）、刪除線（executeStrikeout）forward 各一次、完成整組 B/I/U/S 防回歸。另：full suite 浮出 ghn HN.1 flaky（與 J.1 同檔同 pattern、Y54+Y56 兩次重複），順手用 J.1/Y53 同款 expect.poll 硬化（Y43/Y49 的 feature+sweep 節奏）。

**範圍**：新 spec `admin-dobtor-doc-editor-sprint-y56-underline-strike-toggle.spec.ts`（top-level、+~150 行）、ghn HN.1 flaky 硬化（top-level、4 處 fixed-wait+single-read → expect.poll）、新 sprint doc。零 source code 改動（Y51 機制已涵蓋全 8 個格式按鈕）。

---

## 1. 為什麼開這個

Y55 sprint doc Y56 候選第一條：「底線/刪除線 forward toggle 各鎖一次（Y51 機制已涵蓋、補 spec）」。

B/I/U/S 是格式工具列上一組可見的 4 個 toggle 按鈕。Y51 只鎖了 B（完整 cycle）+ I（forward）、留 U/S。Y56 補完——**一組可見按鈕該整組鎖、不只鎖代表性的 2 個**（若日後有人改 executeStrikeout 的 wiring、沒 spec 的 U/S 會 silent 回歸）。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y56.1 test | 新增（top-level、~150 行）：seed content_json 真文字 → 全選 → 點底線 → getValue underline=true + aria-pressed 翻 → 平行測刪除線 |
| sprint doc | 文件 |
| source code | 零改動（Y51 已涵蓋）|

---

## 3. 設計取捨

### 3.1 共用機制下「各鎖一次 forward」仍有防回歸價值

B/I/U/S 比 Y49 的字型/字號更**共用**：四者走同一 `_executeCmd` + 同一個 rangeStyleChange 同步 block（line 835-842 一起讀 `el.bold/italic/underline/strikeout`）。所以機制上 Y51 證過 B/I、U/S 幾乎必然也通。但**各鎖一次 forward 仍值得**：catch「個別 command 名稱被改」「個別按鈕 aria-label/handler 被動」這類 per-button 回歸（共用 block 不會 catch 單一 command 的 wiring 斷裂）。輕量（reuse Y51 fixture + 技術、各多一段斷言）、ROI 高。

### 3.2 為什麼只 forward、不重測 toggle-off

Y51 已用粗體鎖過完整 on→off cycle、證 canvas-editor toggle 語意 + 反向同步在 off 方向也通。U/S 走同機制、**toggle-off 邏輯 B 已涵蓋**、不必每個都重測（且 Y50 注意過 canvas-editor 全選含 newline 時 toggle-off 語意有 fragility、forward 方向最穩）。U/S 各鎖 forward（套用 + active 回寫）即足以證平行 wiring 通。

### 3.3 雙 oracle（沿用 Y51）

- getValue 內容層：`element.underline/strikeout === true`（正向套用生效）
- aria-pressed：按鈕 active 回寫（反向同步 + re-render）

### 3.4 受惠 Y55 global expect timeout

本 spec 的裸 assertion（`toBeVisible()` / `toHaveAttribute()` 無明指 timeout）自動吃 Y55 的 global 15000 expect timeout、高負載下有餘裕。新寫 spec 不必再每個明指 timeout。

---

## 4. 預期 + 實測

**預期**：全選 → 點底線/刪除線 → 套用到選取（getValue）+ 按鈕 aria-pressed 翻 true。

**實測**：
- Y56.1 單跑：1/1 pass (33.4s)、**first run 直接通過**、底線/刪除線 getValue 命中 + aria-pressed 翻 true
- 40-test full suite 連跑（HN.1 硬化前）：38 pass + 2 fail 13.0m（ghn HN.1 + Y26.1、Y56 本身通過）
- HN.1 expect.poll 硬化後 ghn 單跑：3/3 pass (51.7s)
- 40-test full suite 連跑（HN.1 硬化後）：**40/40 pass 11.8m all green** ✓（Y26.1 本 run 未再 flaky；recurs 再做 readiness refactor）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y56-underline-strike-toggle.spec.ts` | 新檔 +~150 行（top-level repo）|
| `admin-dobtor-doc-editor-sprint-ghn.spec.ts` | HN.1 4 處 fixed-wait+single-read → expect.poll（top-level repo、同 J.1/Y53 pattern）|
| `phase8_sprint_y56_2026-05-30.md` | 新檔 |

零 source code 改動。

---

## 6. 教訓

1. **一組可見按鈕該整組鎖、不只代表性的幾個**：B/I/U/S 是 toolbar 一組、Y51 只鎖 B/I、Y56 補 U/S。**可見的一組同類控制、spec 該覆蓋整組**——沒鎖的那幾個會 silent 回歸（共用機制不保證個別 wiring 不被單獨改壞）。
2. **共用機制下「各鎖一次 forward」是輕量防回歸**：B/I/U/S 共用同步 block、機制 Y51 證過；但各鎖一次 forward catch「單一 command/按鈕 wiring 斷裂」（共用 block 不 catch）。**共用機制不等於不必各測、但可只測最小代表性斷言（forward）、不必每個都重跑完整 cycle**。
3. **新 spec 受惠全域設定（Y55）**：Y55 global expect timeout 後、新 spec 裸 assertion 自動有餘裕、不必逐個明指 timeout。**結構性設定的好處是「之後寫的都自動受益」**——這是 config 層修法 vs spec 層逐個改的複利。
4. **flaky triage：recurring + cheap fix 先掃、once + expensive 先記**：本 run full suite 浮 HN.1（recurring：Y54+Y56、cheap：同 J.1 的 expect.poll mechanical fix）+ Y26.1（first occurrence、expensive：helper-level 多斷言 readiness refactor）。**掃 recurring+cheap、defer once+expensive**——不為了「這 run 全綠」硬塞不成比例的 refactor。也印證 Y55：global expect timeout 救不了 HN.1（fixed-wait+single-read 不是 auto-retry assertion）、那類一定要逐個改 expect.poll。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y55 | ✅ |
| **Y56 — 底線/刪除線 forward toggle（補完 B/I/U/S）** | ✅（待 full suite 最終確認、B/I/U/S active toggle 整組鎖定）|

### Sprint Y57 候選

- 字色/背景色 palette 套真選取 spec（executeColor/Highlight + getValue color oracle、獨立 wiring/state/UI、比 U/S 更值得各測）
- 兩端對齊（justify/alignment）toggle（對齊組第 4 個、Y54 測了左中右）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 清除格式 / 複製格式（painter）按鈕 spec
- **Y26 theme cycle readiness refactor（若再 flaky）**：clickThemeCycle 固定 wait + readThemeState 單次讀 → 各斷言改 expect.poll 等期望 themeMode/class（Y56 已 defer、recurs 再做）
- openEditor `waitForTimeout(4000)` → `waitForFunction(window._docEditorCmp)` readiness 等待（24 spec、徹底解 flaky 後續、scope 大）
- in-flight admin-project config 是否該 commit（user 決定、見 Y55 doc）
- 模板模式匯出 PDF/DOCX spec（需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（需 .docx fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）

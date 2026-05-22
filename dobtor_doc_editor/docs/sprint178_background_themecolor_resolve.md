# Sprint 178 — `<w:background>` themeColor → hex 解析（Phase 5.6 follow-up）

**日期**：2026-05-22
**類型**：parser 強化（capture、小 follow-up cluster A）
**規畫書對應**：§5 階段 D Phase 5.6「背景」follow-up
**前置**：Sprint 171（`<w:background>` capture、themeColor raw）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## 第 0 步 — working tree drift 清理（紀律 #14.b）

開工 `git status` 揭 3 個 build artifact 未 commit：`canvas-editor-custom.umd.js`
（+ `.map`）、`visual_regression_v14_report.json`。調查確認：bundle 內含 **Sprint 178
原始碼**（`BackgroundParser.parse(documentXml, themeMap)` + `resolveThemeColor`），
但對應 source（`BackgroundParser.ts` / `OoxmlParser.ts`）**無此變更**、無 Sprint 178
commit / stash / audit doc。

判定：autopilot 在 Sprint 177 commit 後曾跑 Sprint 178、build 出 artifact 後 source
遺失（coexistence_warning「手動與 autopilot 不可同時跑」實際發生）。orphan bundle
與 committed source 不一致 = broken state → `git checkout` 還原 3 檔、working tree
清零後、由本 session 從乾淨 source 重做 Sprint 178（實作與 orphan 設計一致、確認過合理）。

---

## Hypothesis

Sprint 171 capture `<w:background>` 時 themeColor 只存 raw 名稱（scope-down）。
`<w:background w:themeColor="accent1">` 的 docx → `background.color` 為 undefined →
CanvasRenderer 退回預設白底、theme-based 背景失效。本 sprint 補 themeColor → hex
解析、使 theme-based 背景也能 render。

---

## 修法

### `BackgroundParser.parse` 加 `themeMap` 參數（+約 10 行）

`parse(documentXml, themeMap?: ThemeMap)`：當 `<w:background>` 有 `w:themeColor`
且無顯式 `w:color` 時、以 `resolveThemeColor(themeMap, themeColor, themeTint, themeShade)`
解析為具體 hex 寫入 `color`。複用既有 `ThemeResolver.resolveThemeColor`（Phase 4.1、
含 tint/shade 變亮變暗）。`w:color` 已直接給時不覆寫（顯式優先）。

`OoxmlParser` Step 8.4 把既有 `themeMap`（Step 2.6 已解析）傳入 `backgroundParser.parse`。

### Scope-down（紀律 #18）

- themeColor 不在 THEME_COLOR_MAP（罕見、非法名）→ `resolveThemeColor` 契約回
  `'000000'`（沿用既有契約、不另加守衛）。
- `<w:background>` 仍保留 `themeColor` raw 欄位（capture 完整性）。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1464 → 1468 passed + 1 skipped**（+4 BackgroundParser）。涵蓋 themeColor + themeMap → hex / 無 themeMap → color 不解析 / w:color 與 themeColor 並存不覆寫 / themeShade 變暗 |
| **L2 VR v14** | frontend + VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 38 連）。0 fixture 含 `<w:background>` → byte-identical |
| **L3 spot check** | docs / audit / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 重建（OoxmlParser 在依賴樹內）。
- flake8：不適用（0 行 Python）。

---

## Root cause

Sprint 171 把 themeColor scope-down 為 raw capture（未解析），留下「theme-based 背景
render 失效」缺口。本 sprint 用既有 `resolveThemeColor` 補齊 —— BackgroundParser
原為 standalone（無 themeMap），改為接受 optional `themeMap` 參數、由 OoxmlParser
（持有 themeMap）注入。Strategy C：0 fixture 含 `<w:background>` → VR byte-identical。

---

## 紀律

- **#14.b**：開工前發現 orphan build artifact（autopilot Sprint 178 drift）、調查
  確認為 broken state、`git checkout` 還原、working tree 清零後才開工。
- **#1.a**：改 parser 跑全 42 fixture VR（第 38 連）。
- **#14（DRY）**：複用 `ThemeResolver.resolveThemeColor`、不另造 theme 色解析。
- **#18 scope-down**：非法 themeColor 沿用 resolveThemeColor 既有 '000000' 契約。

---

## 後續

- 小 follow-up cluster A 剩餘：圖片浮水印 render（需先擴 WatermarkParser capture
  shape 尺寸）、framePr Sprint 171 optional 邊緣項、註解 panel render。
- 決策 B（OnlyOffice goldens 重生）、決策 C 大塊 5.1/5.2/5.3（需 user fixture）。
- **autopilot 協調**：本次 orphan artifact 證實 coexistence_warning；建議手動 session
  與 autopilot 不同時跑、或 autopilot 暫停期間做手動 sprint。

---

## Sprint 178 結尾累積指標

- vitest **1468 passed + 1 skipped**（+4）
- VR mean **0.073191**（byte-identical 第 38 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 177 → 178
- `<w:background>` themeColor → hex 解析完成（Phase 5.6 背景 follow-up）

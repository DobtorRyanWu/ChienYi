# Phase 8 Sprint Y24 — Row 3 toggle E2E regression spec（2026-05-26）

**性質**：補 Y23 落地的 Row 3 user toggle 對應 regression spec。Y23 sprint doc 末段已列為 Y24 候選、本 sprint 兌現。同 Y16 / Y20 / Y22 「feature 落地後一 sprint 補回歸 spec」motif。
**範圍**：[admin-dobtor-doc-editor-sprint-y24-row3-toggle.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-y24-row3-toggle.spec.ts)（新檔、+~135 行）。零 code 改動。

---

## 1. 為什麼補這個

Y23 加了 user-pref boolean + localStorage 持久化 + menu item，runtime probe 4/4 pass、但沒鎖 E2E。下次有人改 menu config / dispatch case / IIFE hydrate / `t-if` 條件，feature 會無聲壞掉。Y23 sprint doc 已明列 spec 為 Y24 候選；今天兌現。

---

## 2. spec 覆蓋面

單 test「Y24.1 — toggle ON/OFF + localStorage persist after reload」，5 個 step：

| Step | 操作 | 預期 |
|---|---|---|
| 1 | 開 editor（先清 LS） | `.doc-toolbar` count = 0、localStorage `_show_legacy_toolbar` = null |
| 2 | 查看 menu → 顯示舊版工具列 | `.doc-toolbar` visible、LS = `'1'` |
| 3 | 再點 toggle | `.doc-toolbar` 隱藏、LS = `'0'` |
| 4 | 再 toggle ON + `page.reload()` | `.doc-toolbar` visible、LS = `'1'`（持久化還原）|
| 5 | 重開 menu | menu item label `✓ 顯示舊版工具列`（state 同步） |

cleanup 階段把 LS 重置、避免污染其他 spec。

---

## 3. spec 設計取捨

### 3.1 為什麼 step 1 主動清 LS

其他 spec（Y14 / Y20 / Y22）或之前 manual 測試可能留下 LS 殘值。`localStorage.removeItem` 在 editor 開啟前先清掉、確保 step 1「初始 null」斷言穩定。同樣 spec 結束 cleanup 也清。

這也是 spec 之間互不污染的原則 — 任何 spec 動到 user-pref localStorage 都應該結束時還原。

### 3.2 為什麼 step 4 reload 後仍要 waitForTimeout(4000)

reload 觸發 OWL re-mount、canvas-editor 重新 init、IIFE 從 LS 讀 themeMode / recentColors / showLegacyToolbar。`'1'` 經 IIFE 變 `state.showLegacyToolbar = true` 觸發 Row 3 render。4000ms 給 canvas + thumbnails 完整 init（同 Y14 spec 用過的 timeout）。

### 3.3 為什麼用 `:has-text("舊版工具列")` 不用 `:has-text("顯示")`

menubar item 標籤可能含「顯示尺規」「顯示縮圖」「顯示舊版工具列」三個都有「顯示」。`:has-text("舊版工具列")` 唯一定位。

### 3.4 為什麼最後一步驗 menu item label `✓` 標記

不只驗 toolbar visible、也驗 menu label 同步反映 state。確保未來有人改了 toolbar visibility 但忘了改 menu label（或反之）會被抓出。menuConfig 是 getter 每次 render 計算、跟 state 同步應該天然 work、但 spec 顯式驗證。

### 3.5 為什麼沒 spec 「menu 點 toggle 後 menu 自動關」

Y3 既有行為 — `onMenuItemClick` 最後 set `openMenu = null`。是 Y3 layer 的責任、Y23 / Y24 不該重複鎖。同樣的事 Y14.1 spec 一次驗過就夠。

---

## 4. 預期 + 實測

**預期**：Y24.1 spec 1/1 pass、6 條既有 E2E（Y14.1 + Y20.1 + Y22.1 + G.1/HN.1/J.1）不受影響。

**實測**：
- Y24 row 3 toggle spec：1/1 pass (22.2s) ✓
- 完整 7 條 regression：7/7 pass (2.3m) ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y24-row3-toggle.spec.ts` | 新檔、~135 行：1 個 test 含 5 step（toggle on/off + reload persist + menu label ✓）|
| `phase8_sprint_y24_2026-05-26.md` | 新檔（addons subrepo 內）|

零 code 改動。

---

## 6. 教訓

1. **localStorage 共用 spec 之間要主動清**：Y24 是第 4 個會動 LS 的 spec（Y14 / Y20 / Y22 / Y24）。Default `playwright.config.ts` 不 reset storage、若任一 spec 不清就留尾巴給下一個。每個 spec 自己 setup + teardown 動到的 key。下次若 Y25+ 寫 spec 動 LS、複貼此 pattern。
2. **boolean toggle 的 regression spec 模板化**：4-step pattern「初始 → on → off → reload-persist」適用於任何 localStorage-backed boolean toggle。Y9 dark mode / Y19 themeMode / Y23 Row 3 都該套同模板。Y14 / Y19 manual 驗過、沒補 spec；Y20+ 可考慮一次補齊。
3. **menu label ✓ 標記是 visual sync 的 sentinel**：menu item label 的 `✓` 標記 = state 跟 UI 一致的肉眼可見指標。新 sprint 加 boolean toggle 時記得 menu label 同步、spec 一併鎖。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y23 | ✅ |
| **Y24 — Row 3 toggle E2E regression** | ✅（7/7 全綠）|

### Sprint Y25 候選

- localStorage utility（抽 wrapper、Y9 / Y13 / Y19 / Y23 共 4 個 key 都直接寫、值得一致 API）
- Y19 themeMode E2E spec（已 manual 驗、可套 Y24 4-step 模板）
- Y17 / Y18 modal 行為的 E2E spec（文件設定 / 行距 modal 開關 + apply）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 工具 menu 各 action 的 spec 覆蓋

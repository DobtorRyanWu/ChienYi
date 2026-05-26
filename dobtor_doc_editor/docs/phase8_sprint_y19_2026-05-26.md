# Phase 8 Sprint Y19 — auto/light/dark 三段 themeMode（2026-05-26）

**性質**：Y9 dark mode 升級 — 從 boolean toggle 改成三段 themeMode（'auto' | 'light' | 'dark'），跟 system prefers-color-scheme。「跟系統」是現代 OS / 瀏覽器體驗的預期、Y9 二段 toggle 已落後一個世代。
**範圍**：`doc_editor.js`（+~70/-7 行）、新建 sprint doc。零 XML、零 CSS（state.darkMode 仍是 boolean、是 `is-dark-mode` class 的直接 source、`_recomputeDarkMode` 內部維護同步）。

---

## 1. 為什麼開這個

Y9 用 `state.darkMode` boolean + localStorage `dobtor_doc_editor_dark_mode` = '0' | '1'。問題：
- User OS 設定深色模式 / 系統定時切換、文件編輯器卻一直停在自己之前選的、體感斷裂
- 沒有「跟系統」option、user 要切就要手動

現代設計通用三段 toggle（Google Docs / VS Code / Slack 皆然）：
- **auto / 跟系統** — 默認、跟 `prefers-color-scheme`
- **light / 淺色** — 強制 light
- **dark / 深色** — 強制 dark

實作要點：
- 加 `state.themeMode`（user 偏好、persistent）
- 保留 `state.darkMode`（effective rendering flag、driven from themeMode + system pref）
- 加 `matchMedia('(prefers-color-scheme: dark)')` listener、auto 模式時 system 變動觸發 darkMode 重算
- localStorage 新 key + 從 Y9 舊 key 做 migration

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `state.themeMode` | 新 string：user 偏好 'auto' \| 'light' \| 'dark'；IIFE migration 從 Y9 boolean |
| `state.darkMode` | 保留 boolean（XML 既有 `is-dark-mode` class 不動）；改為 `_recomputeDarkMode()` 維護 |
| `setup()` | 加 `matchMedia` listener + 初始 `_recomputeDarkMode` 同步 |
| destroy hook | 解除 matchMedia listener |
| menuConfig「深色模式」 | 改 label `外觀：{跟系統\|淺色\|深色}` + action `view:cycle-theme` |
| `onMenuItemClick` 分派 | `case 'view:toggle-dark'` 移除 → `case 'view:cycle-theme'` 接 `onCycleTheme` |
| 新 methods | `_themeLabel` / `_recomputeDarkMode` / `onCycleTheme` |

零 XML、零 CSS 改動（`t-att-class="{ 'is-dark-mode': state.darkMode }"` 仍 work、所有 `.o_dobtor_doc_editor.is-dark-mode .doc-*` rules 自動套用）。

---

## 3. 設計取捨

### 3.1 為什麼保留 boolean state.darkMode

純粹是為了零 XML / CSS 改動。三段 themeMode 是 user 偏好、`darkMode` 是 effective rendering 用的 boolean — 兩個職責拆開。

替代方案是 XML 改用 `state.themeMode === 'dark' or (state.themeMode === 'auto' and ...)` 但會把 system pref check 散到 template 裡 — 不好維護。

### 3.2 為什麼 localStorage 用新 key

Y9 key 是 `dobtor_doc_editor_dark_mode` 存 '0' / '1'。Y19 改 'auto' / 'light' / 'dark' 三段、覆蓋舊 key 會打到還在跑 Y9 的 user（雖然這個 module 只有我們用、其實沒這風險、但好習慣養著）。

新 key `dobtor_doc_editor_theme_mode`。

Migration logic（IIFE in state init）：
1. 先讀新 key、命中即用
2. 沒有的話讀舊 key、'1' → 'dark'、其他 → 'light'（保守、跟 Y9 行為一致）
3. 兩個都沒、預設 'auto'（新 user）

舊 key 不主動刪除（無痛、未來某 sprint 統一清）。

### 3.3 為什麼 `_recomputeDarkMode` 是 method 不是 getter

OWL `useState` 是 reactive proxy、setter 才會觸發 re-render。getter 模式（`get darkMode() { ... }`）不會 trigger reactive deps。所以實作上：
- themeMode 是 reactive state
- darkMode 是 reactive state（手動同步）
- `_recomputeDarkMode()` 在三個時機呼叫：setup 結束、onCycleTheme、system prefers 變動

### 3.4 為什麼 matchMedia listener 用 `?.()` chain

`window.matchMedia` 在 jsdom 等部分測試環境是 `undefined`、`addEventListener` 在某些舊環境也沒有（Safari < 14 用 `addListener`）。Optional chaining 是「best effort」、unsupported environment 也不 crash、只是失去 auto 模式 system 同步功能（user 仍可手動 toggle）。

### 3.5 cycle 順序 auto → light → dark → auto

跟 macOS / Google Docs UX 對齊。從「自動」開始（最被動）、依次往「強制亮」「強制暗」（最主動）走。循環回 auto 完成 loop。

### 3.6 為什麼用 notification 而不只是 menu label

Cycle 一次 menu 已關（onMenuItemClick 最後 set openMenu=null）、user 看不到 label 變化。Notification 給即時 feedback、~2 秒 toast、不打擾。

### 3.7 為什麼不要 sub-menu（auto / light / dark 三選一）

Sub-menu 需要新 XML / CSS 基礎建設（Y18 sprint doc 已決定 Y19+ 不順帶做）。Cycle button 更小、UX 同樣達成（多按一兩次而已）、cost-benefit 明顯。

---

## 4. 預期 + 實測

**預期**：
- 查看 menu 顯示「外觀：跟系統」（首次）/ 「外觀：淺色」 / 「外觀：深色」（取決於 localStorage）
- 點擊 cycle 順序：auto → light → dark → auto
- themeMode='auto' 時 system 切換 dark → editor 立刻變 dark（無需重整）
- themeMode='light' 強制亮、即使 system 是 dark
- themeMode='dark' 強制暗
- 既有 Y9 dark mode CSS 全部仍 work（is-dark-mode class binding 不變）

**實測**：見 §7 進度。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~70/-7 行：state 加 themeMode（含 migration IIFE）、state.darkMode IIFE 同步調整、setup() 加 matchMedia listener、destroy 加解除、dispatcher 改 1 case、menuConfig label 改 1 行、新 3 methods（_themeLabel / _recomputeDarkMode / onCycleTheme） |
| `phase8_sprint_y19_2026-05-26.md` | 新檔 |

零 XML、零 CSS 改動。回退 = git revert 末段。

---

## 6. 教訓

1. **reactive state 為 effective flag、user 偏好為 source-of-truth**：兩層拆開讓 CSS / XML 完全不動、只改 JS 內部 sync 邏輯。下次任何 user-pref + system-pref 混合的功能都可套此 pattern。
2. **matchMedia listener 比 polling 省**：MediaQueryList 是 OS 主動 push、不需要 setInterval 輪詢。記得 `?.()` chain 應付環境差異。
3. **migrate without breaking**：新 key 不覆蓋舊 key、舊 key 留著做 fallback、有上線老 user 都能無痛升級。
4. **三段 default 預設值要明確列舉、不能靠隱式 fallback**：首版 migration IIFE 寫 `legacy === '1' ? 'dark' : 'light'` — 當 legacy 是 `null`（從沒設過 Y9）也會掉到 'light'、結果新 user 預設根本不是 'auto'。runtime probe 立刻抓到。Fix：明確列 `legacy === '0' → 'light'`、其餘（null/undefined）→ 'auto'。三元 ternary nested 容易漏 case、改 if-else 鏈讓 default 路徑清楚。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y18 | ✅ |
| **Y19 — auto/light/dark 三段 themeMode** | ✅（code 完工、等 runtime 驗證） |

### Sprint Y20 候選

- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、要 customize render 或外掛 module、scope 大）
- 段落間距 / 縮排（沒 public API、scope 大）
- signer-bar 視覺再精簡
- Row 3 hide 改成 user 可 toggle 顯示
- find panel 鍵盤 nav E2E 回歸
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）
- 文件設定 modal 補 page direction getter（canvas-editor patch upstream、low priority）

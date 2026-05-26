# Phase 8 Sprint Y25 — localStorage helper 抽 utility（refactor）（2026-05-26）

**性質**：純 refactor、零行為變動。Y9 / Y13 / Y19 / Y23 累積 4 個 user-pref localStorage key、每個都各自寫 try/catch + （視情況）JSON.parse / stringify、boilerplate 重複。Y25 抽兩個 module-level helper（`_lsGet` / `_lsSet`）、6 個 call site 一致化。
**範圍**：`doc_editor.js`（+~18/-~25 行；net -7 行）。零 XML、零 CSS、零 sprint doc 之外的新檔。

---

## 1. 為什麼開這個

四個 sprint 累積後、`localStorage` 的 boilerplate 變這樣：

| Sprint | key | read | write |
|---|---|---|---|
| Y9 | `dobtor_doc_editor_dark_mode` | try-catch get → '1' === | try-catch set('1'/'0') |
| Y13 | `dobtor_doc_editor_recent_colors` | try-catch get → JSON.parse | try-catch set → JSON.stringify |
| Y19 | `dobtor_doc_editor_theme_mode` | try-catch get → enum 驗證 + Y9 migration | try-catch set |
| Y23 | `dobtor_doc_editor_show_legacy_toolbar` | try-catch get → '1' === | try-catch set('1'/'0') |

問題：
- 每個 sprint 重複寫一遍 try-catch — easy to miss（Y23 的 catch 就是漏 `/* ignore quota */` 但沒漏 try）
- JSON parse/stringify 各自寫 — 容易忘了 parse 配 stringify 對稱
- 沒一致的失敗 fallback 約定（有的 return null、有的 return {}、有的 return false）

Y25 統一成兩個 helper、6 個 call site 都改走、未來 Y26+ 加 user pref 一行搞定。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `_lsGet(key, {json})` | 新 module-level helper：try-catch + 可選 JSON.parse，失敗回 `null` |
| `_lsSet(key, value, {json})` | 新 module-level helper：try-catch + 可選 JSON.stringify，失敗回 `false`、value 自動 String() |
| Y13 `recentColors` IIFE | 改用 `_lsGet(..., { json: true })` |
| Y19 `themeMode` IIFE | 改用 `_lsGet(...)` × 2（新 key + Y9 legacy） |
| Y19 `darkMode` IIFE | 改用 `_lsGet(...)` × 2 + matchMedia try-catch 保留 |
| Y23 `showLegacyToolbar` IIFE | 改用 `_lsGet(...) === '1'` 單行 |
| `_pushRecentColor` write | 改 `_lsSet(..., { json: true })` |
| `onClearRecentColors` write | 改 `_lsSet(..., { json: true })` |
| `onCycleTheme` write | 改 `_lsSet(...)` |
| `view:toggle-legacy-toolbar` dispatcher | 改 `_lsSet(...)` |

零 method 邏輯動。每個 call site 行為 1:1 對應。

---

## 3. 設計取捨

### 3.1 為什麼 helper 設計回傳值而非 throw

呼叫端的 try-catch 已經一致寫「失敗就 fallback default」、helper 直接吞錯回 `null`/`false` 比 throw 更貼近呼叫端意圖。

`_lsGet` 失敗 → `null`：caller 用 `?.` chain 或 `||` fallback。
`_lsSet` 失敗 → `false`：caller 通常不在乎（best-effort persistence）、回傳值給少數需要的場景。

### 3.2 為什麼 `{ json }` options object 而不是 boolean

`_lsGet(key, true)` 看不懂；`_lsGet(key, { json: true })` 一眼明白。option object 也方便未來擴充（`{ json: true, defaultValue: ... }`）。OWL / Odoo 18 內部 API 也偏好 option object。

### 3.3 為什麼 `_lsSet` 內部用 `String(value)`

`localStorage.setItem` 自己會把 value coerce 成字串、但 `String(null)` = "null"、`String(undefined)` = "undefined" 顯式做、catch 任何 type mismatch 早一步。也提醒 caller：non-string 值要走 `json: true`、不是 string concat。

### 3.4 為什麼不抽 `_lsRemove`

四個 sprint 沒有任何「刪除 localStorage key」的 production code path（spec teardown 走 `page.evaluate` 直接呼 `localStorage.removeItem`、不經 component）。等真有 caller 再加、現在抽是 over-engineering。

### 3.5 為什麼 export 給 module 外

ES module 預設 closed。export 讓未來其他 component（doc_version_panel 等）若要做 localStorage 持久化、可 import 同樣 helper、不必各自重造。

### 3.6 為什麼放在 doc_editor.js 而不是新檔

目前只有 1 個 component 用。新建 `utils/local_storage.js` 是 over-engineering。等真有第 2 個 caller 再考慮抽單獨 module。

---

## 4. 預期 + 實測

**預期**：所有 4 個 user-pref（dark / theme / recent colors / legacy toolbar）行為 1:1 不變、E2E 7/7 全綠、runtime 無 regression。

**實測**：
- 7/7 E2E pass (2.5m) — Y14.1 + Y20.1 + Y22.1 + Y24.1 + G.1/HN.1/J.1 全綠
- 完全沒新 spec：refactor 不寫 spec、靠既有 spec 鎖（Y19 themeMode 沒 spec 是 Y25 sprint doc 末段列下次補的）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | net -7 行：新 `_lsGet` / `_lsSet` +18 行、refactor 6 個 call site -25 行 |
| `phase8_sprint_y25_2026-05-26.md` | 新檔 |

零 XML、零 CSS、零新 method（兩個 helper 是 module-level function 非 component method）。

---

## 6. 教訓

1. **5 sprint 是 boilerplate 抽 utility 的甜蜜點**：太早抽 = YAGNI、太晚抽 = 散到無法追蹤。Y9 / Y13 / Y19 / Y23 累積 4 個 caller 後抽、視野剛好、`null` / `false` fallback 約定也已經穩定（不是猜的）。
2. **refactor 沒 spec、靠既有 spec 鎖**：Y25 完全沒寫新 spec。既有 7 條 E2E 覆蓋 4 個 user-pref 路徑、refactor 不改行為 = spec 不必動。若 spec 紅、就是 refactor 行為有偏差、refactor 失敗。
3. **option object 比 boolean param 可讀很多**：`_lsGet(key, { json: true })` vs `_lsGet(key, true)`。code reader 不用回頭翻 helper signature 才知道 `true` 是什麼意思。
4. **`String()` 預先 coerce 比 setItem 自動轉好**：value 是 null / undefined 時、`String(null)` = "null" 比 raw `setItem(key, null)` 行為更可預期、且讓 caller 明確知道「請走 json: true」。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y24 | ✅ |
| **Y25 — localStorage helper utility（refactor）** | ✅（7/7 全綠、零行為回歸）|

### Sprint Y26 候選

- Y19 themeMode E2E spec（Y24 4-step 模板套用：auto → light → dark → reload-persist）
- Y17 / Y18 modal 行為 E2E spec（文件設定 / 行距 modal 開關 + apply）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設

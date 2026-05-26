# Phase 8 Sprint Y26 — themeMode cycle + emulateMedia E2E regression spec（2026-05-26）

**性質**：補 Y19 落地的三段 themeMode 對應 regression spec。Y19 / Y25 都靠 manual probe 驗、沒鎖 E2E。Y26 加 2 個 test：(1) cycle 3 段 + LS 持久化 + reload；(2) auto 模式下 system pref live-sync。
**範圍**：[admin-dobtor-doc-editor-sprint-y26-theme-cycle.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-y26-theme-cycle.spec.ts)（新檔、+~210 行）。零 code 改動。

---

## 1. 為什麼補這個

Y19 三段 themeMode 比 Y23 Row 3 toggle 多兩個獨特行為：
1. **cycle 順序**（auto → light → dark → auto）— 比單純 boolean toggle 多一個維度、要驗轉移順序對
2. **matchMedia change listener live-sync** — auto 模式下 system pref 變動立刻反映、用 `page.emulateMedia({ colorScheme })` CDP 觸發

兩個都是 Y9 / Y23 boolean toggle 沒有的特殊邏輯、值得獨立鎖。Y24 4-step 模板無法涵蓋 → Y26 加 2 個 test。

---

## 2. spec 覆蓋面

### Y26.1 — cycle + LS persist + reload（6 step）

| Step | 操作 | 預期 |
|---|---|---|
| 1 | 開 editor（清 LS、colorScheme=light） | LS=null、no dark class |
| 2 | cycle 1：auto → light | LS=`'light'`、no dark class |
| 3 | cycle 2：light → dark | LS=`'dark'`、dark class ON |
| 4 | cycle 3：dark → auto | LS=`'auto'`、no dark class（system light）|
| 5 | cycle 2 次回 dark + `page.reload()` | LS=`'dark'`、dark class ON（IIFE hydrate）|
| 6 | 重開 menu | label「外觀：深色」 |

### Y26.2 — auto + emulateMedia system pref live-sync（4 step）

| Step | 操作 | 預期 |
|---|---|---|
| 1 | 初始 auto + system=light | LS=null、no dark class |
| 2 | `emulateMedia({ colorScheme: 'dark' })` | LS=null（仍 auto）、dark class ON（live-sync）|
| 3 | `emulateMedia({ colorScheme: 'light' })` | LS=null、no dark class |
| 4 | cycle 至 light + `emulateMedia dark` | LS=`'light'`、no dark class（user 強制 override system）|

step 4 是 emulateMedia 的反向驗證 — 證明 listener 只在 themeMode=`auto` 時才作用、強制 light/dark 時 system pref 無效。

---

## 3. spec 設計取捨

### 3.1 為什麼用 newContext({ colorScheme: 'light' })

Default Playwright context 的 colorScheme 不保證 light、可能跟 host system 走。我們需要 deterministic 起點 → 明確設 `colorScheme: 'light'`。然後 emulateMedia 切到 dark 才有正確的 baseline。

### 3.2 為什麼兩個 test 都各自 newContext

第一個 test 用 `colorScheme: 'light'` 一路跑、不需要切 system pref。第二個 test 需要 emulateMedia 切換、要求乾淨的 context 起點。各自開 newContext 互不污染。

### 3.3 為什麼 step 6（menu label）獨立驗

跟 Y24 spec step 5 同樣 motif — 驗 menu UI 跟 state 同步。`外觀：跟系統` / `外觀：淺色` / `外觀：深色` 三段在 menuConfig getter 內 inline 字串拼接、容易跟 state 不同步。spec 顯式驗。

step 6 只驗 `深色` 即可、不三段都驗（每 cycle 步驟 menu label 一定變、實測上 Y26.1 step 2/3/4 沒驗 menu label 是有意省略、focus 在 LS + class 兩條軸）。

### 3.4 為什麼 Y26.2 step 4 不 reload 驗持久化

Y26.1 已驗 reload-persist 路徑、Y26.2 focus 在 listener 行為。不重複。

### 3.5 為什麼不驗 ✓ 標記

Y24 spec 驗 ✓ 是 boolean toggle 用、Y19 themeMode menu label 不是 ✓ 而是「外觀：{tag}」三段名稱。step 6 驗「深色」字串直接覆蓋 state-UI sync 同樣 goal。

### 3.6 為什麼 wait 400ms 給 emulateMedia

matchMedia change event 是 sync fire、但 OWL re-render 跟 Y19 _recomputeDarkMode 內部 setter 仍需要 microtask。400ms 給 listener + render + DOM update 完整跑完。比 100ms 保險、又不會拖慢 spec 太多。

---

## 4. 預期 + 實測

**預期**：Y26.1 + Y26.2 各 1/1 pass、其他 7 條既有 spec（Y14.1 + Y20.1 + Y22.1 + Y24.1 + G.1/HN.1/J.1）不受影響。

**實測**：
- Y26.1 spec：1/1 pass (46.1s) ✓
- Y26.2 spec：1/1 pass (27.4s) ✓
- 完整 9 條 regression（Y14.1 + Y20.1 + Y22.1 + Y24.1 + Y26.1 + Y26.2 + G.1/HN.1/J.1）：9/9 pass (3.1m) ✓

兩個 test 都 first-pass 綠 — 行為跟 Y19 / Y25 既有的 manual probe 結果完全一致、refactor 沒回歸。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y26-theme-cycle.spec.ts` | 新檔、~210 行：2 個 test 含 cycle + reload + emulateMedia 完整覆蓋 |
| `phase8_sprint_y26_2026-05-26.md` | 新檔（addons subrepo 內） |

零 code 改動。spec 自管 cleanup（清 LS_KEY + LS_LEGACY 雙鍵、避免 Y9 legacy migration 殘留污染後續 spec）。

---

## 6. 教訓

1. **複雜 state 的 spec 拆多個 test 比塞一個 mega-test 好**：cycle 行為 + emulateMedia 行為兩個獨立軸、各自 newContext、互不影響。出錯時 fail 訊息可直接定位「cycle 壞」或「listener 壞」。
2. **CDP emulateMedia 是 Playwright 模擬 OS dark mode 的標準方式**：比 mock matchMedia 或 inject CSS variable 都更貼近真實。Chrome DevTools 用同一個介面、信賴度高。
3. **3-mode state machine 比 boolean toggle 多一個 reload-after-cycle 驗證點**：boolean 只有 2 個 state、reload 不需要拆兩段 cycle；3-mode 要 cycle 兩次（auto → light → dark）才能驗某個 mode 的 reload-persist。Y26.1 step 5 做的就是這個。
4. **spec 自帶雙鍵清除（current + legacy）**：Y19 有 Y9 legacy migration、spec 必須兩個 key 都清才是「全新 user」狀態。下次有 migration 要再加 spec 一律記得清 legacy。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y25 | ✅ |
| **Y26 — themeMode cycle + emulateMedia E2E regression** | ✅（9/9 全綠） |

### Sprint Y27 候選

- Y17 文件設定 modal E2E spec（紙張 / 方向 / margin 改動 + apply 流程）
- Y18 行距 modal E2E spec（preset 按鈕 + 自訂 input + apply）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）

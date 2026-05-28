# Phase 8 Sprint Y44 — 版本面板「還原」restore_version round-trip spec（2026-05-28）

**性質**：純 spec sprint — 鎖版本管理三角最後一條：`DocVersionPanel.restoreVersion` → confirm → rpc `/dobtor_doc/versions/restore` → `restore_version`（**先存「還原前快照」再套用目標內容**）→ `onVersionRestored` notification + 關面板。Y36 鎖讀面板、Y43 鎖寫快照、Y44 鎖還原、三條 path 各鎖一條零重疊。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y44-version-restore.spec.ts`（top-level repo、+~165 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y43 sprint doc Y44 候選第一條：「版本面板『還原版本』spec（`onVersionRestored`、line 3707、restore_version round-trip）」。Y44 兌現。

版本管理 W7-8 P1-1 三條 path：
- **讀**：`onShowVersionPanel` → `.doc-version-panel` 開、列版本（Y36 已鎖）
- **寫**：`onSaveVersion`（Ctrl+Shift+S）→ 新快照（Y43 已鎖）
- **還原**：`DocVersionPanel.restoreVersion` → rpc restore → `onVersionRestored`（Y44 鎖）

還原是三條中**副作用最重**的：`restore_version` 不是單純覆蓋內容、而是**先 `action_save_version` 存「還原前快照（即將回退到 vN）」再 write 目標內容**。這個「還原不丟歷史」invariant 是資料安全核心、最該 spec 鎖死、防 future refactor 把 pre-restore snapshot 省掉。

Y36/Y43 鋪好讀寫 spec、Y44 補還原 = 版本管理三角閉合。Y3/Y35/Y36/Y39/Y40/Y42/Y43 backfill 節奏延續。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y44.1 test | 新增 (top-level、~165 行)：callKw `action_save_version` 建 v1+v2 → 開 editor → 工具 menu → 版本歷史開面板 → 驗列 2 版（降序 v2/v1）→ 定位 v1 列「還原」按鈕 → click → `page.once('dialog')` 接受 confirm + 鎖 confirm 文字含「還原前快照」→ notification「已還原至 v1（當前 v3）」auto-retry → 面板自動關 → `expect.poll` 驗 DB `version_number===3` + `versions_data` 3 筆 + 最新筆 label 含「還原前快照」+「v1」|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼版本 setup 用 callKw `action_save_version` 不用 Ctrl+Shift+S

Y43 已鎖 Ctrl+Shift+S 建快照路徑。Y44 焦點是**還原 UI**、版本建立只是前置。用 callKw 直接 `action_save_version`：
- 精準：不必處理兩次 prompt dialog、不依賴 editor auto-save timing
- 快：省兩次鍵盤 + prompt accept
- 避 race：editor 開啟後的 auto-save 不會干擾「還原前」已凍結的 v1/v2 snapshot

「前置用最省的 API、焦點 path 走 UI」= Y40 bootstrap 用 template content、Y43 用 callKw read 驗 DB 的延伸。

### 3.2 為什麼斷言 server-side 不變量、不斷言 content_html round-trip

還原最直觀的驗證是「內容變回 v1」。但 E2E 斷言 content_html round-trip 不穩、**主動放棄**：
- v1 snapshot 同時凍結 `content_html` + `content_json`；editor 載入走 `content_json`（canvas 格式）
- 還原後 `onVersionRestored` 重載文件 + `executeSetValue(content_json)`、再觸發 auto-save
- auto-save 會用 canvas 當前 render 覆寫 content_html → 若只比 content_html marker 會被 auto-save render 蓋掉、flaky

改斷言 **server-side atomic 不變量**（restore_version 內部一次完成、auto-save 蓋不到）：
1. notification「已還原至 v1（當前 v3）」= `restored_version` + `new_current_version` 直接編碼、證 rpc round-trip 算對
2. `version_number===3` = 還原前快照確實 +1、證「不丟歷史」invariant
3. `versions_data[2].label` 含「還原前快照」+「v1」= 證 pre-restore snapshot 標對回退目標

Y42 教訓「selector 選 page-level > conditional」延伸到斷言層 = **斷言選 server-side atomic > UI-derived 易被後續 mutation 覆蓋的值**。content round-trip 是 backend 邏輯、更適合 unit test；E2E 鎖 UI wiring + 副作用。

### 3.3 為什麼鎖 confirm 文字「還原前快照」

`restoreVersion` 用 `confirm("還原此版本將覆蓋當前內容（會自動建立還原前快照）。確定？")`。spec `expect(confirmMessage).toContain('還原前快照')`：
- 證 confirm 確實彈出（不是 silent 還原）
- 鎖 user-visible promise「會自動建立還原前快照」= 對使用者承諾資料安全、不能 silent 拿掉

Y42 教訓「user-visible 字串都該 spec assert」延伸到 confirm dialog 文字。

### 3.4 為什麼用 `page.once('dialog')` 接受 confirm

`restoreVersion` 的 `confirm()` 若被 Playwright 預設 **dismiss** → 回 false → early return、還原根本不跑。必須 `page.once('dialog', d => d.accept())` 在 click 前註冊。`page.once` 只攔一次、accept 後自動移除、不影響後續可能的 dialog。同 Y43 prompt 處理。

### 3.5 為什麼用 `:has(.doc-version-no ~ /^v1$/)` 定位 v1 列

列表降序（`get_version_list` reverse=True）→ v2 在前、v1 在後。「還原 v1」要點 v1 那列的按鈕、不能用 `.first()`（那是 v2）。用 `page.locator('.doc-version-item', { has: .doc-version-no hasText /^v1$/ })` 鎖含「v1」文字的列、再取其內「還原」按鈕。regex `^v1$` 防 v1 撞 v10／v12 等（本 fixture 雖只 v1/v2、但鎖緊防 future fixture 擴充 silent 誤點）。

Y36 教訓「selector 選 semantic」延伸 = 用版本號語意定位列、不靠位置 index。

---

## 4. 預期 + 實測

**預期**：點 v1「還原」→ confirm → 還原前快照自動存（version 2→3）→ notification「已還原至 v1（當前 v3）」→ 面板關 → DB version_number===3 + versions_data 3 筆。

**實測**：
- Y44.1：1/1 pass (1.1m)
- 31-test full suite 連跑：31/31 pass 13.2m all green ✓（sprint-d Y43 硬化後持續穩定、無 flaky）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y44-version-restore.spec.ts` | 新檔 +~165 行（top-level repo）|
| `phase8_sprint_y44_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 8 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **副作用最重的 path 最該 spec**：還原不是單純覆蓋、而是「先存還原前快照再套用」雙步驟、且 pre-restore snapshot 是資料安全 invariant。**feature 內部副作用越複雜（尤其涉及不可逆的資料覆蓋），spec 越該鎖死那個保護機制**；還原前快照一旦 future refactor 省掉、使用者誤還原就永久丟資料、且不會有任何報錯。
2. **斷言選 server-side atomic、不選 UI-derived 易變值**：content_html round-trip 直觀但被 editor auto-save race 蓋掉、flaky；version_number / versions_data label 是 restore_version 內部一次寫完、auto-save 碰不到。**E2E 斷言要挑「動作的原子副作用」、不挑「會被後續非同步流程覆寫的衍生狀態」**。Y43「assert DB side effect 不只 UI toast」延伸 = 「assert atomic side effect 不選 mutable derived」。
3. **版本管理三角閉合的價值**：Y36（讀面板）+ Y43（寫快照）+ Y44（還原）三條 path 各鎖一條、互不重疊、合起來涵蓋整個 feature lifecycle。**一個 feature 的多條 path 分 sprint 各鎖一條 = 每條都 focused + 高 cohesion、合起來才是完整 contract**；Y22/Y32/Y33/Y38 find/replace 4-entry-point、Y36/Y43/Y44 版本三角都是這個 pattern。
4. **前置用 callKw、焦點走 UI 是穩健 E2E 的常態**：版本建立 callKw、還原走 panel UI。**E2E 不必每步都走 UI**；非焦點的前置（建資料、設狀態）用 callKw 精準快速、把 UI 操作集中在本 sprint 真正要鎖的 path。Y40/Y43/Y44 一致。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y43 | ✅ |
| **Y44 — 版本面板還原 restore_version round-trip spec** | ✅（待 full suite 最終確認、版本管理三角閉合：讀 Y36／寫 Y43／還原 Y44）|

### Sprint Y45 候選

- 版本面板「比對版本」spec（`runDiff`、`diff_versions`、選兩版顯段落 diff）
- 版本面板「預覽版本」spec（`previewVersion`、`get_version_content`、單版預覽 HTML）
- 預覽模式 bound path spec（需 doc 綁 model_id + res_id）
- 「列印」menu item spec
- 「匯入 DOCX」/「匯出 PDF」/「匯出 DOCX」menu item spec
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

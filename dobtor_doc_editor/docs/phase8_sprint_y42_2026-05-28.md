# Phase 8 Sprint Y42 — 檔案 menu「儲存」+ Ctrl+S spec 覆蓋 + Y39 flaky sweep（2026-05-28）

**性質**：純 spec sprint — 鎖核心 save flow 雙 entry point（menu click + Ctrl+S）；連跑 regression Y39 同 Y37 manifest flaky pattern 浮出、順手沿用 auto-retry pattern 修。Y42.1 鎖 statusbar `state.statusMsg` 「已儲存」、Ctrl+S keyboard shortcut 同樣觸發 onSave。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y42-file-save.spec.ts`（top-level repo、+109 行）、Y39.1 spec auto-retry fix（top-level、~5 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y41 sprint doc Y42 候選：「『儲存』menu item + Ctrl+S spec」。Y42 兌現。

`onSave` 是 dobtor_doc_editor 最核心 IO method、wire 到：
- 檔案 menu「儲存」item (line 4834、shortcut `Ctrl+S`)
- 鍵盤 `Control+s` 走 `_onGlobalKey` path（line 4225 dispatcher）
- Auto-save timer (W7-W8 era)
- onbeforeunload 時 force save

3 個 entry point 中 menu click + Ctrl+S 是 user-visible primary 路徑、優先補 spec。Auto-save / onbeforeunload 更內部、留 future。

Y3 ✅ marker 標 onSave 完成、但 30+ sprint 沒 E2E 鎖：core feature 越久沒 spec、bug 越 silent。Y35/Y36/Y39/Y40 backfill 節奏延續。

連跑 14-spec 浮出 Y39.1 flaky（notification 抓 null）— 同 Y37 manifest pattern。順手沿用 auto-retry pattern 修 `expect(locator).toBeVisible({ timeout: 5000 })` 再抓 textContent。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y42.1 test | 新增 (top-level、~109 行)：bootstrap doc → 開 editor → 確認 `.doc-statusbar` 渲染 → 檔案 menu「儲存」item shortcut「Ctrl+S」hint 顯示 → click → `expect(statusbar).toContainText('已儲存')` auto-retry → menu dropdown 關 → Ctrl+S 觸發第二次 → 同樣「已儲存」auto-retry |
| Y39.1 fix | `.first().textContent().catch(=>null)` → `expect(locator).toBeVisible({timeout:5000})` + `textContent()` 同步抓（top-level repo） |
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼選 statusbar 不選 dashboard 卡片

兩個 DOM 點都顯 `state.statusMsg`：
- `.doc-statusbar`：row 7 持續顯示、不依賴 sub-nav tab、page-level visible
- `.doc-dashboard-card:has-text("文件狀態")`：只在 sub-nav「儀表板」tab active 時渲染、預設 tab 是「範本」

選 statusbar 更直接、不依賴 sub-nav 切換、ROI 高。Y3 ✅ 標 dashboard 是另一 feature、Y42 不過度耦合。

### 3.2 為什麼鎖 shortcut hint「Ctrl+S」字串

`menuConfig` line 4815 寫 `shortcut: 'Ctrl+S'`、xml render hint span。spec assert hint contains「Ctrl+S」=:
- 鎖 menu item 結構（user 看得到 shortcut hint）
- 防 future 改 shortcut 名（例如改成 ⌘S Mac 字面）silent regression
- 一行 expect、ROI 高

未 cover：實際按 Ctrl+S 觸發 onSave 是另一 path（dispatcher 中）。step 5 額外鎖鍵盤觸發 = 雙 path 完整 cover。

### 3.3 為什麼 Ctrl+S 鎖在 step 5 不另 test

Y22 / Y20 / Y40 都用「single test 跑完整 cycle」pattern、Y42 沿用：
- step 2-4：menu click path
- step 5：keyboard shortcut path
- step 6：sanity（連續 Ctrl+S 不破 state）

兩 entry point 互相佐證、reuse fixture/bootstrap。獨立 test 要重 fixture（4 秒 openEditor）= ROI 低、cohesion 也低。

### 3.4 為什麼 Y39 fix 同 PR 順手做

Y37 sprint doc 明寫策略：「real-world flaky manifest 後再批次」。Y39 連跑 manifest = 觸發批次條件。順手 fix 1 處（5 行）= 不擴張 scope。

YAGNI 反向 = 等出問題才修；現在出問題 = 該修。

### 3.5 為什麼不測 Ctrl+Shift+S 版本快照

Ctrl+Shift+S line 335 是另一 path（手動建版本快照、寫 `doc.version`）、scope 跟 onSave 不同。Y42 鎖 onSave；版本快照留 Y43+。

Y32 教訓「scope 緊一致」延伸 = 鍵盤組合多但行為不同的、應該 各 spec sprint 鎖一條。

### 3.6 為什麼 spec 注意 statusMsg 可能短暫顯「儲存中」

`auto-retry` `expect(locator).toContainText('已儲存', { timeout: 5000 })`：
- rpc 完成前 statusMsg = 「儲存中...」
- rpc 完成後 statusMsg = 「已儲存」
- toContainText 持續輪詢直到符合 / timeout

如果中途搶在「儲存中」狀態 assert 會 fail；auto-retry 等到「已儲存」自然 pass。Y37 教訓「auto-retry assertion 真正解 timing flaky」延伸。

step 6 加 `await page.waitForTimeout(300)` 等所有 rpc 完成、verify statusMsg 不會 race 卡在「儲存中」。

---

## 4. 預期 + 實測

**預期**：menu「儲存」+ Ctrl+S 雙 path 觸發 onSave、statusbar 顯「已儲存」。

**實測**：
- Y42.1：1/1 pass (34.4s)
- Y39 manifest 修 + 單跑：34.8s pass
- 14-spec 連跑：14/14 pass 5.2m all green ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y42-file-save.spec.ts` | 新檔 +109 行（top-level repo）|
| `admin-dobtor-doc-editor-sprint-y39-file-preview-mode.spec.ts` | 1 處 manifest fix `+expect.toBeVisible / -catch=>null`（top-level repo） |
| `phase8_sprint_y42_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 6 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **core feature 越久沒 spec 越 silent**：onSave 是 dobtor_doc_editor 最核心 IO、Y3 ✅ marker 標完成、但 30+ sprint 沒 E2E 鎖。一旦 onSave 行為微改（rpc URL / payload format / 衝突處理）silent break。**core 路徑優先 spec backfill**、邊緣功能可以等。
2. **flaky manifest 後批次的紀律已成形**：Y37 sweep Y14+Y20、Y38 順手 Y24、Y42 順手 Y39 = 「每次連跑紅一個就修一個」變成 sustainable rhythm。**lazy + reactive 不是懶、是經濟**；沒紅的不動、紅了的順手修、5 個 sprint 後整個 suite robust。
3. **DOM 選擇器選「page-level visible」優於「conditional」**：dashboard 卡片要 sub-nav 切換才渲染、statusbar 持續 visible。**spec 選 conditional element = 多 1 個 setup 步驟 + 多 1 個 race condition**；spec 選 page-level visible element = 直接看到 + 無 setup。Y36 教訓「selector 選 semantic > visual」延伸 = 「selector 選 page-level > conditional」。
4. **shortcut hint 也該 spec**：menu item label 含「Ctrl+S」hint = user-visible promise。spec 順手 assert 1 行 = 鎖 promise、防 future shortcut rename silent regression。**user-visible 字串都該 spec assert**、不只行為。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y41 | ✅ |
| **Y42 — 檔案 menu 儲存 + Ctrl+S spec + Y39 manifest sweep** | ✅（14/14 sprint specs 全綠 5.2m、core save flow 鎖 30+ sprint 後 contract）|

### Sprint Y43 候選

- Ctrl+Shift+S 版本快照 spec（line 335、寫 doc.version）
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

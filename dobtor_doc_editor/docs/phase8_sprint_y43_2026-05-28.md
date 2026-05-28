# Phase 8 Sprint Y43 — Ctrl+Shift+S 版本快照 save path spec + sprint-d overlay flaky sweep（2026-05-28）

**性質**：純 spec sprint — 鎖手動版本快照唯一 entry point（Ctrl+Shift+S）write path：prompt → rpc `/dobtor_doc/save_version` → `version_number +1` + `versions_data` 累積 + notification。連跑 30-test full suite 浮出 sprint-d overlay 兩條 drag/create test flaky（單跑綠、full-suite 高負載紅）、順手沿用 auto-retry pattern（`expect.poll`）硬化。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y43-version-snapshot.spec.ts`（top-level repo、+~155 行）、sprint-d 2 處 `expect.poll` flaky fix（top-level、~30 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y42 sprint doc Y43 候選第一條：「Ctrl+Shift+S 版本快照 spec（line 335、寫 doc.version）」。Y43 兌現。

`onSaveVersion` 是 W7-8 P1-1 era 實作的版本管理 write path、wire 到：
- 鍵盤 `Ctrl/Cmd+Shift+S`（line 335 dispatcher）→ `onSaveVersion()`
- **沒有 menu item**：檔案/工具 menu 只有「版本歷史」(Alt+H、`onShowVersionPanel`) 開**讀**面板、沒有「儲存版本」item

→ Ctrl+Shift+S 是 `onSaveVersion` 的**唯一** entry point。唯一入口沒 spec 鎖 = keyboard handler 一旦被改（dispatcher 條件、shortcut 改名、prompt 拿掉）silent break、且沒有 menu 備援 path 可發現。比一般「有 menu 又有鍵盤」的雙 path 更需要 keyboard spec。

Y36 已鎖版本**面板**（`onShowVersionPanel` 讀路徑、`.doc-version-panel` 開關 + Escape）；Y43 鎖**儲存**（`onSaveVersion` 寫路徑）。讀寫分屬兩條 path、Y36/Y43 各鎖一條、零重疊。Y3/Y35/Y36/Y39/Y40/Y42 backfill 節奏延續。

連跑 30-test full suite（非 Y42 的 14-spec 子集、含舊 abce/d/f/ghn）浮出 sprint-d overlay 兩條 test flaky — 順手沿用 auto-retry pattern 修。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y43.1 test | 新增 (top-level、~155 行)：bootstrap doc（version_number 起始 0）→ 開 editor → `page.once('dialog')` 攔 prompt 接受標籤 → Ctrl+Shift+S → `expect(notification).toBeVisible('版本 v1 已儲存')` auto-retry → 鎖 prompt 文字含「版本標籤」→ callKw read 驗 `version_number===1` + `versions_data[0].label` 命中 → 第二次 Ctrl+Shift+S → 「版本 v2 已儲存」→ `version_number===2` + 2 筆 snapshot 累積 |
| sprint-d fix | test 136（建浮動 field）+ test 183（拖曳 save_field）2 處 fixed `waitForTimeout` + 單次 callKw read → `expect.poll` auto-retry（top-level repo）|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼用 callKw read 驗 DB 持久化、不只看 notification

notification「版本 vN 已儲存」只證明 rpc 回了 `success`，不證明 `version_number` 真的 +1、`versions_data` 真的 append。Y34 教訓「assert 期待值不是 lib 回值」延伸 = **assert 真正的 side effect（DB 持久化），不只 assert UI 回饋**。

Y43 read `version_number`（Integer field、default=0、每存 +1）+ `versions_data`（Json field、每存 append 一筆含 `version_no`/`label`）：
- `version_number===1` / `===2`：鎖遞增邏輯
- `versions_data.length`：鎖累積（不是覆蓋）
- `versions_data[N].label` 命中使用者輸入：鎖 prompt → rpc payload → model write 整條 data flow

### 3.2 為什麼用 `page.once('dialog')` 而非 `page.on`

`onSaveVersion` 用 `window.prompt("請輸入版本標籤（可空白）：")`。Playwright 預設**自動 dismiss** dialog → `prompt()` 回 null → `|| ""` → label 變空白、無法驗 label 持久化。

- `page.once('dialog', d => d.accept(LABEL))`：只攔**一次**、accept 並填指定標籤、自動移除 listener
- `page.on`：持久 handler、兩次 Ctrl+Shift+S 都用同一 callback、要自己管 counter 切換 label

兩次按鍵各 `page.once` 一次 = 每次填不同 label（`Y43 初版定稿` / `Y43 二修`）、驗 `versions_data[0]` ≠ `[1]`、確認不是覆蓋而是 append。`page.once` 是 Playwright 處理「已知次數 dialog 序列」的 idiomatic 寫法。

### 3.3 為什麼鎖 prompt 文字「版本標籤」

prompt message 是 user-visible promise（使用者看到「請輸入版本標籤（可空白）」才知道要填什麼）。spec `expect(promptMessage).toContain('版本標籤')`：
- 鎖 prompt 確實彈出（不是 silent 存空版本）
- 防 future 改 prompt 文字 / 拿掉 prompt 直接存 silent regression

Y42 教訓「user-visible 字串都該 spec assert、不只行為」延伸 = prompt dialog 文字也是 user-visible promise。

### 3.4 為什麼第二次按鍵也鎖（不只測一次）

Y20/Y22/Y40/Y42 都用「single test 跑完整 cycle」pattern、Y43 沿用：
- 第一次 Ctrl+Shift+S：v0 → v1（驗遞增 base case）
- 第二次 Ctrl+Shift+S：v1 → v2（驗 state machine 連跑不卡、`versions_data` append 不覆蓋）

只測一次無法分辨「+1」與「設成 1」；兩次才鎖**遞增**語意 + **累積**語意。reuse fixture/bootstrap（4 秒 openEditor）、ROI 高。Y36 教訓「state machine cycle 完整」延伸。

### 3.5 為什麼 sprint-d flaky fix 同 PR 順手做

Y37 sprint doc 策略：「real-world flaky manifest 後再批次」。Y43 連跑 30-test full suite（比 Y42 的 14-spec 子集更大、含舊 abce/d/f/ghn）= 觸發批次條件。sprint-d 兩條 test 單跑 4/4 綠、full-suite 高負載下紅 = 典型 timing flaky。順手 fix = 不擴張 scope。

Y38「順手 Y24」、Y42「順手 Y39」= 跨 sprint flaky fix 已是常態；紅在哪修在哪、不限本 sprint family。

### 3.6 為什麼 sprint-d 用 `expect.poll` 而非加長 `waitForTimeout`

sprint-d 原寫法：click 建欄位 → `waitForTimeout(2000)` → 單次 callKw read 驗 `layout_mode==='overlay'`；拖曳 → `waitForTimeout(1500)` → 單次 read 驗 `pos_x>120`。問題：`save_field` RPC 在 full-suite 高負載下可能晚於固定 wait → read 抓到 0 row 或 stale pos。

- 加長 fixed wait（2000→5000）：治標、拖慢每次跑、負載更重時又會破
- `expect.poll(async () => callKw(...))`：auto-retry 讀到 row commit / pos 更新才斷言、負載低時快、負載高時自動等

Y37 教訓「auto-retry assertion 真正解 timing flaky」從 DOM notification 延伸到 **callKw DB read** = 同一原則套用到後端持久化驗證。fixed wait + 單次 read 是 flaky 之源、不分 DOM 或 RPC。

---

## 4. 預期 + 實測

**預期**：Ctrl+Shift+S → prompt → 版本快照 +1、notification「版本 vN 已儲存」、DB `version_number` 遞增 + `versions_data` 累積。sprint-d 2 處 `expect.poll` 硬化後 full-suite 不再 flaky。

**實測**：
- Y43.1：1/1 pass (23.9s)
- sprint-d 硬化後單跑：4/4 pass (1.4m)
- 30-test full suite 連跑（硬化前）：28 passed / 2 failed（sprint-d 兩條 overlay flaky）12.8m
- 30-test full suite 連跑（硬化後）：30/30 pass 9.1m all green ✓（sprint-d flaky 消除、且 auto-retry 負載低時更快、總時間 12.8m → 9.1m）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y43-version-snapshot.spec.ts` | 新檔 +~155 行（top-level repo）|
| `admin-dobtor-doc-editor-sprint-d.spec.ts` | 2 處 `waitForTimeout`+單次 read → `expect.poll` auto-retry（top-level repo）|
| `phase8_sprint_y43_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 7 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **唯一 entry point 的 feature 最該 spec**：`onSaveVersion` 只能透過 Ctrl+Shift+S 觸發、沒 menu 備援。**單一入口 = 單點故障**；keyboard dispatcher 一改（條件、shortcut 名、prompt 拿掉）就 silent break、且沒有第二條 path 能在手動操作時撞見。比「menu + 鍵盤雙 path」更需要 spec 鎖。**盤點 feature 時，entry point 越少的越優先 backfill**。
2. **assert side effect 不只 assert UI 回饋**：notification「已儲存」只證 rpc 回 success、不證 DB 真的寫對。Y43 用 callKw read `version_number` + `versions_data` 鎖真正的持久化結果。**UI toast 是 lib/rpc 的自我宣稱、DB read 才是事實**；Y34「assert 期待值不是 lib 回值」延伸到「assert 持久化不是 UI 宣稱」。
3. **auto-retry 不限 DOM、callKw DB read 同樣適用**：Y37 把 notification 從 `waitForTimeout+textContent` 改 `expect.toBeVisible` auto-retry；Y43 把 sprint-d 的 `waitForTimeout+單次 callKw` 改 `expect.poll`。**fixed wait + 單次斷言是 flaky 之源、不分前端 DOM 或後端 RPC**；凡「動作後讀非同步結果」都該 auto-retry。`expect.poll` 是 callKw 版的 `expect(locator).toBeVisible`。
4. **full-suite 比子集更會抓 flaky**：Y42 跑 14-spec 子集全綠、Y43 跑 30-test full suite 才浮出 sprint-d flaky。**flaky 跟負載正相關**；curated 子集跑得快但漏抓、定期跑 full suite（即使慢）才會逼出累積負載下的 timing race。**子集驗功能、full suite 驗 robustness**、兩者都要。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y42 | ✅ |
| **Y43 — Ctrl+Shift+S 版本快照 save path spec + sprint-d overlay flaky sweep** | ✅（待 full suite 最終確認、版本快照唯一入口 write path 鎖 30+ sprint 後 contract）|

### Sprint Y44 候選

- 版本面板「還原版本」spec（`onVersionRestored`、line 3707、restore_version round-trip）
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

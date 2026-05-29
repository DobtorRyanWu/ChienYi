# Phase 8 Sprint Y49 — 格式化工具列字型/字號 selector 雙向同步 spec（2026-05-29）

**性質**：純 spec sprint — 鎖格式化工具列（Y5）字型/字號 select 的雙向同步 loop：selector → canvas（`executeSize`/`executeFont`）+ canvas caret → selector（`rangeStyleChange` listener → `state.activeFontSize`/`activeFontFamily` → select `t-att-value` 回寫）。首次 spec 觸及 canvas 文字選取互動。連跑 36-test full suite 浮出 Sprint F（overlay resize/drag）3 條 flaky（單跑綠、高負載下 save_field RPC 晚於 fixed wait）、順手沿用 Y43 sprint-d 的 `expect.poll` pattern 修。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y49-font-size-sync.spec.ts`（top-level repo、+~135 行）、Sprint F spec 3 處 `expect.poll` flaky fix（top-level）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y48 sprint doc Y49 候選：「字型/字號 selector active state 雙向同步驗證」。Y49 兌現。

格式化工具列（Sprint Y5、`.doc-format-toolbar`）字型/字號 select 是 Google Docs 風常用操作、Y8 加 caret 狀態反映、但 30+ sprint 沒 spec 鎖。**雙向同步是最容易 silent 半壞的 pattern**：
- 只有 selector→canvas 壞：改字號沒效果
- 只有 canvas→selector 壞：游標移到不同字號處 select 不更新（顯示錯誤狀態）

兩個方向各自獨立、任一壞了另一個可能還在動、手動操作不一定撞到 → 最該 spec 同時鎖兩向。

**為什麼跳過列印**：探查 canvas-editor `executePrint` 用 iframe `contentWindow.print()`（非主 `window.print`）→ Playwright override 攔不到、不可靠測、留 future。選可靠的字型/字號先做。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y49.1 test | 新增 (top-level、~135 行)：開 editor → `.doc-format-toolbar` + 字型/字號 select 渲染 → 預設字號=16 → 點 canvas 放游標 + Ctrl+A 全選 → 改字號 select 為 24 → executeSize 套用 → 等同步 settle → 驗 select 停在 24（回寫成功）→ 字型同理（預設→Arial）|
| Sprint F fix | F.1 resize / F.2 clamp / F.3 inspector 3 處 fixed `waitForTimeout`+單次 read → `expect.poll` auto-retry（top-level repo、full-suite 高負載 flaky 修、同 Y43 sprint-d pattern）|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼測「全選後改字號、select 停在新值」= 測完整 loop

關鍵：select 的 `t-att-value="state.activeFontSize"` 由 state 控制。改 select（native change）→ `onFontSizeChange` → `executeSize(24)`。若**雙向同步全通**：executeSize 套用到選取 → caret 起點 element.size=24 → `rangeStyleChange` listener 更新 state.activeFontSize='24' → OWL re-render 保持 select='24'。

若 canvas→state 同步**斷了**：state.activeFontSize 仍 16 → OWL re-render 用 state 把 select **打回 16**。所以「改成 24、等 settle、select 仍是 24」這一個斷言同時證了兩個方向都通。**用 OWL 受控 select 的 re-render 行為當 oracle**：若反向同步壞、select 會被 state 拉回舊值、斷言自然失敗。

### 3.2 為什麼必須先全選文字

`executeSize` 要有作用對象。無選取時 canvas-editor 只設「下次輸入的 pending 樣式」、`rangeStyleChange` 不一定以可讀的 startElement 反映新 size → 反向同步不穩。**全選（Ctrl+A）讓 executeSize 套用到實際 element + caret context 有明確 startElement.size** → 反向同步必觸發。前置動作（選取）是讓被測 loop 進入可觀測態的必要步驟。

### 3.3 為什麼這是第一個碰 canvas 文字選取的 spec

先前所有 spec 避開 canvas 文字互動（find/replace 走面板、Sprint D 走 overlay 拖曳、版本/匯出走 menu）。Y49 必須點 canvas + Ctrl+A。實測 click `.canvas-editor-container canvas` 置中 + `Control+a` 可靠選取（standalone 一次通過）。**canvas 文字互動沒想像中脆**：固定 position click 放游標 + 全選是 canvas-editor 標準鍵盤行為、Playwright 直接支援。這開了後續 indeterminate / 對齊 / 格式按鈕等需要選取的 spec 的路。

### 3.4 為什麼 selectOption 後加 waitForTimeout 再斷言、不用純 auto-retry

雙向同步是「改 select → executeSize → rangeStyleChange → state → re-render」多段非同步。若用 `toHaveValue('24')` auto-retry、它在第一輪 poll 看到 selectOption 剛設的 native '24' 就 pass（**false positive**：還沒等到反向同步可能把它打回 16）。所以先 `waitForTimeout(800)` 讓整個 loop settle（含可能的「打回」）、再斷言終態 = 24。**測「狀態會不會被後續流程改回」時、要等流程跑完再斷言、不能用 auto-retry 搶在中途**。這與 Y43「auto-retry 等狀態到達」相反場景：這裡是「等狀態穩定不再變」。

### 3.5 為什麼字型也測一次

字型（`executeFont`）走獨立 handler（`onFontFamilyChange`）、獨立 state（`activeFontFamily`）、獨立 select。字號通了不代表字型通（兩條平行 wiring）。各測一次 = 兩個 selector 都鎖。ROI：reuse 同一 fixture + selectAllInCanvas helper、多一段斷言。

---

## 4. 預期 + 實測

**預期**：改字號 select→24、字型 select→Arial，雙向同步後 select 停在新值。

**實測**：
- Y49.1：1/1 pass (32.4s)、canvas click+Ctrl+A 全選可靠、字號/字型雙向同步回寫成功
- 36-test full suite 連跑（Sprint F 硬化前）：35 passed / 1 failed（F.1 resize save_field 高負載 flaky）14.7m
- Sprint F 硬化後單跑：3/3 pass (1.7m)
- 36-test full suite 連跑（Sprint F 硬化後）：36/36 pass 11.5m all green ✓（Sprint F flaky 消除）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y49-font-size-sync.spec.ts` | 新檔 +~135 行（top-level repo）|
| `admin-dobtor-doc-editor-sprint-f.spec.ts` | F.1/F.2/F.3 3 處 `expect.poll` flaky fix（top-level repo）|
| `phase8_sprint_y49_2026-05-29.md` | 新檔 |

零 source code 改動 = 第 13 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **雙向同步用「受控元件被拉回舊值」當反向 oracle**：select 的值由 state 控制、改 select 後若反向同步沒更新 state、OWL re-render 會把 select 打回舊值。**測雙向綁定不必各別斷言兩個方向、設計成「改一端、等 settle、看它有沒有被拉回」**：拉回 = 反向斷了、停住 = 兩向都通。一個斷言鎖整個 loop。
2. **測「狀態穩定」要等流程跑完、不能 auto-retry 搶中途**：雙向同步有「可能被打回」的中段、auto-retry 會在打回前的瞬間 false-positive pass。`waitForTimeout` 等 loop 完全 settle 再斷言終態。**auto-retry 適合「等狀態到達」、不適合「驗狀態不會再變」**；後者要等夠久看終態。這是 Y43 auto-retry 原則的反面補充。
3. **canvas 文字選取沒想像中脆**：固定 position click 放游標 + Ctrl+A 全選、Playwright 直接支援、一次通過。**先前避開 canvas 互動是過度保守**；開了這條路、後續 indeterminate / 對齊 / 格式按鈕 active state 等需選取的 spec 都可做。怕脆而不測 ≠ 真的脆。
4. **平行 wiring 各測一次**：字號與字型是兩條獨立 handler/state/select、一條通不證另一條通。**同類但獨立實作的功能各鎖一個最小斷言**、reuse fixture 降成本。Y22/Y32 find/replace 多 entry point、Y49 字型/字號都是這個 pattern。
5. **drag/save_field flaky 是同一家族、修法已模板化**：Sprint F（resize/clamp/inspector）與 Y43 修的 sprint-d（overlay create/drag）同源——「拖曳/輸入 → save_field RPC → 單次 callKw read」在 full-suite 高負載下 RPC 晚於 fixed wait。**同類 flaky 用同一 `expect.poll(讀到期望值才斷言)` pattern 套**、不必每次重想。Sprint D（Y43）、Sprint F（Y49）兩組 overlay drag test 全部 auto-retry 化後、這家族 flaky 應收斂。「每次 full suite 紅一個修一個」rhythm 持續、修法越來越機械化。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y48 | ✅ |
| **Y49 — 格式化工具列字型/字號雙向同步 spec** | ✅（待 full suite 最終確認、首個 canvas 文字選取 spec、開後續格式類 spec 的路）|

### Sprint Y50 候選

- 格式按鈕 B/I/U/S active state 雙向同步（執行 + caret 反映、沿用 Y49 selectAllInCanvas）
- 對齊 align 左/中/右/兩端 active state
- indeterminate state（部分選中時 format toolbar 顯示、需跨樣式選取）
- 模板模式匯出 PDF/DOCX spec（rpc fill_template → LibreOffice → download、需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（file input + TS Parser、需 .docx 上傳 fixture）
- 列印（iframe contentWindow.print、scope 大或留 future）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

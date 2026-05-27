# Phase 8 Sprint Y36 — 工具 menu「版本歷史」面板開關 spec 覆蓋（2026-05-27）

**性質**：純 spec 覆蓋 — 沿用 Y35 pattern。`onShowVersionPanel` + DocVersionPanel component + Escape close handler 早就實作好（W7-W8 P1-1）、但 25+ sprint 沒 E2E 鎖回歸。Y36 補 Y36.1 test：工具 menu → 版本歷史 → `.doc-version-panel` 出現 + dropdown 關閉 + Escape 關 panel + 再開可重複（state machine 不卡）。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y36-tools-version-panel.spec.ts`（top-level repo、+109 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y35 sprint doc Y36 候選第一條：「工具 menu 其他 action spec（版本歷史 / 預覽變數效果）— 沿用 Y35 pattern」。Y36 兌現「版本歷史」第一個。

Y35 教訓「實作 vs spec 差距是 sprint 的暗物質」直接套用：grep 確認 `onShowVersionPanel` 是 line 3571、handler 有 precondition (`state.docId`)、接 `state.showVersionPanel = true`、DOM 由 `<DocVersionPanel>` component 在 line 1203 condition render。所有 piece 都到位、只差 spec assert。

不寫 spec 的風險：
- 未來改 menu wiring（重排 dropdown order / 改 action name）容易 silent 壞掉
- 未來改 onShowVersionPanel 的 precondition / state transition、UI behavior 變了沒人發現
- DocVersionPanel CSS class rename / structure change、Escape handler 拆走、都該 spec 紅

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y36.1 test | 新增 (top-level、~109 行)：bootstrap doc → 開 editor → 工具 menu (nth=5) → 點「版本歷史」→ 驗 `.doc-version-panel` 出現、dropdown 關閉、Escape 關 panel、再開可重複 |
| sprint doc | 新檔 |
| source code | **零改動**（onShowVersionPanel / panel component / Escape handler 早已實作） |

---

## 3. 設計取捨

### 3.1 為什麼驗 toggle 可重複（步驟 6）

state machine bug 最常見 form：「開了一次後 state 卡住、第二次點不開」。`state.showVersionPanel = true` 在 `onShowVersionPanel`、Escape 應該設 false、然後 再次開時應該重新 true。

驗 toggle = 鎖整個 open/close cycle 不破 state、不只驗第一次。Y32 教訓「invariant 雙保險」延伸：state machine 該驗 cycle 不只 single transition。

### 3.2 為什麼不驗 panel 內容（版本列表）

Y36 scope = 鎖開關 wiring（menu → panel state → DOM、Escape → close、再開 reset）。Panel 內部的版本列表 / restore button / diff view 是 W7-W8 P1-1 的 internal、跟工具 menu 介面層無關。spec 保持 scope 緊。

未來 DocVersionPanel 內容該有獨立 spec（W7-W8 era 或之後補）、Y36 不重疊。

### 3.3 為什麼用 `.doc-version-panel` 不 `.doc-version-panel-overlay`

兩個都存在（overlay 是包外層、panel 是核心 UI）。`.doc-version-panel` 更直接代表「panel 本體」、semantic 強。`.doc-version-panel-overlay` 是視覺遮罩層、被視為 implementation detail。

選 spec 用 `.doc-version-panel` = lock 在 user-visible 概念上、未來改 overlay 寫法（例如改用 portal、改 z-index 結構）仍 work。

### 3.4 為什麼 fixture 內容比 Y35 簡單

Y35 fixture 要驗 chars/words 計數、需中英混和。Y36 fixture 只要「開 panel + close + 再開」、內容 trivial 就行（2 段中文段落即可）。fixture 隨 spec 需求最小化。

### 3.5 為什麼 Escape 關後 dropdown 不需再次驗閉

Step 4 已驗 dropdown 在 menu item click 後關閉。Escape 是 panel-only handler、不影響 menu dropdown（dropdown 早就關了）。不重複 assert，scope 緊。

### 3.6 Flaky Y14.1 怎麼處理

11-spec 連跑時 Y14.1 失敗、單跑 pass（33.9s）。原因推測：5.4m 長 regression 中 docker 容器 / DB 狀態累積、Y14 menu keyboard nav 對 timing 敏感（ArrowDown / ArrowRight 之間 wait 太短）。

Y36 不修：Y14 跟 Y36 source 無重疊、且 Y14 單跑穩定 = 真的是 flaky（隨機壞）。記入 Y37 候選「Y14 spec 加 wait 補強 timing robustness」、不擴張本 sprint scope。

---

## 4. 預期 + 實測

**預期**：工具 menu → 版本歷史 → panel 出、Escape 關、再開可重複。

**實測**：
- Y36.1：1/1 pass (47.2s)
- 11-spec regression：10/11 pass — Y14.1 flaky failed、單跑 33.9s pass 確認；其他 10 個（含 Y36.1）都綠
- 視覺驗證：DocVersionPanel 開啟正常、Escape 關閉、再開可 toggle ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y36-tools-version-panel.spec.ts` | 新檔 +109 行（top-level repo）|
| `phase8_sprint_y36_2026-05-27.md` | 新檔 |

零 source code 改動 = 純 spec sprint。

---

## 6. 教訓

1. **state machine 該驗 cycle 不只 transition**：開了關了再開、能 reset 嗎？UI 狀態最常見 bug 是 "first time works, second time stuck"。Y36 step 6 加「再開驗證」鎖 cycle 完整性、防 silent state leak。下次任何 toggle / panel / modal spec 都該加這條。
2. **不擴張 scope 處理 flaky test**：Y14.1 連跑掛、單跑 pass = timing flaky、跟 Y36 無關。寫入 Y37 候選、Y36 收尾不修。混在一起會稀釋 Y36 commit 的 review 焦點、且 Y14 修法（加 wait / 改 selector / Race-condition 拆解）跟 Y36 本身脫鉤。**單一 sprint 解決單一問題**。
3. **CSS selector 選 semantic > visual**：`.doc-version-panel`（panel 本體）勝過 `.doc-version-panel-overlay`（視覺遮罩）。spec 鎖 user-visible 概念、不鎖 implementation detail = 未來改 visual 寫法仍綠。Y32 教訓「assertion 嚴格度按 lib 可控性挑」反向 = 「assertion 鎖點按 user-visible 概念挑」、不貪 implementation 細節。
4. **連兩個純 spec sprint（Y35 + Y36）建立 pattern**：兩個工具 menu action 共用相同骨架（bootstrap → openEditor → menu trigger nth + item :has-text → assert action effect）。下一個（預覽變數效果 / 拼字檢查 if 解 disable）直接套模板、5 分鐘出 sprint。**Pattern 一旦建立、後續 sprint 的 fixed cost 趨近於零**。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y35 | ✅ |
| **Y36 — 工具 menu 版本歷史 spec 覆蓋** | ✅（10/11 sprint specs 全綠、Y14.1 flaky 單跑驗證確認、Y36 無責）|

### Sprint Y37 候選

- Y14 spec 加 wait / timing robustness（解 5.4m 長 regression 累積資源時的 flaky）
- 工具 menu「預覽變數效果」spec（沿用 Y35/Y36 pattern）
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable

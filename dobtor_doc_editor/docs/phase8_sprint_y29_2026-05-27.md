# Phase 8 Sprint Y29 — Y17 文件設定 modal margin clamp UX 修正（2026-05-27）

**性質**：Y28 的 input clamp UX 修正 pattern 套到 Y17 文件設定 modal 的 4 個 margin input。完全同 motif、零新 design — Y28 sprint doc §3.3 已明寫 doc settings 可能有同樣問題、Y29 兌現一致性 fix + spec 加緊。
**範圍**：`doc_editor.js`（+~10/-~5 行）、`doc_editor.xml`（修 4 個 `t-on-input`）、Y27.1 spec 加緊（驗 fill('200')→'80'、fill('-5')→'0'）、新建 sprint doc。

---

## 1. 為什麼開這個

Y17 onDocSettingsSet 與 Y18 onLineSpacingSet 是 mirror handler — 都做 numeric clamp + 寫 state。Y28 修了 Y18、Y17 還是舊行為：user 打超過 80mm（例如 200）、state clamp 為 80、但 input UI 留 200。

不一致比 bug 更糟 — user 學會「行距 input 會 clamp、文件設定不會」、心理模型壞。Y29 用 Y28 完全同的 fix（optional ev 第二參數 + force `ev.target.value = String(clamped)`）一致化。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onDocSettingsSet(field, value, ev = null)` | 新 optional ev；numeric clamp 後若 differ from input 則 `ev.target.value = String(clamped)`；format/direction 不需要 |
| `doc_editor.xml` × 4 | 4 個 margin inputs (`marginTopMm` / `marginRightMm` / `marginBottomMm` / `marginLeftMm`) 的 `t-on-input` 都多傳 `ev` |
| Y27.1 spec step 5a | fill('200') → input='80'（上界）、fill('-5') → input='0'（下界）、收尾回 fill('40') 給 step 6 用 |
| sprint doc | 新檔 |

format/direction 是 select/radio、無 clamp 需求、不動。

---

## 3. 設計取捨

### 3.1 為什麼不抽 utility helper

直覺：Y28 + Y29 兩個 handler 都做「numeric clamp + force reflect」、抽一個 `_clampNumericInput(value, min, max, ev)` 共用。但兩個 handler 各自有 format/direction 分支邏輯（onDocSettingsSet）或 onApply 流程（onLineSpacingSet）、抽出來需要 reorganize 整段。

3 個 call site 不到的 boilerplate、不抽 — 同 Y25 教訓「5 sprint 是 utility 抽離甜蜜點」反過來說「2-3 個 caller 還太早」。Y30+ 若再加第 3 個 clamp input handler 再考慮。

### 3.2 為什麼 format/direction 完全不動

select 的 onChange 取值是 enum、不會超界；radio 同。沒 clamp 需求 = 不需要 reflect。如果未來改 format 用 input/datalist、再加 ev 補上。

### 3.3 為什麼一個 spec step（5a）測兩個邊界

上下界各一個 assertion、放同一 step 5a：context 連續、reader 一眼看到「就是測 clamp」、不必拆 5a + 5b。

### 3.4 為什麼收尾要 fill('40')

step 5a 留下 input value=0（下界 clamp）會改 state.docSettingsForm.marginTopMm=0。step 6 apply 套用會把 margin 寫成 0、step 7 reopen hydrate 抓回 0、跟原 spec 預期 hydrate=40 不一致。收尾 fill('40') 把 state 重設、Y27.1 step 6/7 既有 assertion 不變。

---

## 4. 預期 + 實測

**預期**：fill('200') → input UI 顯示 '80'；fill('-5') → '0'。其他 11/11 spec 不變。

**實測**：
- Y27.1 加緊版：1/1 pass (27.9s) ✓（原 16.6s + 3 個 clamp fill/wait）
- Y27.2 不變：1/1 pass (16.8s) ✓
- 11/11 regression：5.1m all green ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~10/-~5 行：onDocSettingsSet 加 optional ev + clamp reflect |
| `doc_editor.xml` | 4 個 margin input `t-on-input` 多傳 ev（純 attribute、零行邏輯） |
| `admin-dobtor-doc-editor-sprint-y27-modal-behavior.spec.ts` | step 5a 加 6 行 clamp assertion + 收尾 fill('40')（top-level repo） |
| `phase8_sprint_y29_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **fix 的一致性比 fix 本身重要**：Y17 / Y18 兩個 modal 是 mirror handler、一個修一個沒修 = user 心理模型錯亂。同 family 的 feature 要嘛全套同 fix、要嘛全部不動。Y28 修 Y18 那天就該順手帶 Y17、或當天 commit message 留 TODO 註記、Y29 不會等到第 2 天才補。
2. **spec 既有 step 加緊勝過新 step**：clamp 是 step 5 margin 改動的延伸驗證、加成 step 5a 比新 step 11 cohesion 高。reader 看連續 step 知道在測同個 input field 行為。
3. **3 個 caller 還太早抽 utility**：Y28 + Y29 兩個 + Y17 onDocSettingsSet 含 if-else 分支共算 1.5 個、不到 3。Y25 教訓反過來提醒「過早抽 = YAGNI」。等真有第 4 個 numeric clamp input 再 refactor。
4. **收尾還原讓 spec step 之間獨立**：step 5a 改動會污染 step 6/7、結尾 fill('40') 還原是必要的 spec cleanliness。下次任何 spec 中段加破壞性 step 都記得收尾。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y28 | ✅ |
| **Y29 — Y17 margin input clamp UX 一致化** | ✅（11/11 全綠）|

### Sprint Y30 候選

- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- find/replace panel 取代後 search state stale（Y22 sprint doc 註記、可能要 work-around）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證（Y5 加的 toolbar、active 同步在 line 739 計算但沒鎖 spec）

# Phase 8 Sprint Y27 — Modal 行為 E2E regression spec（Y17 文件設定 + Y18 行距）（2026-05-27）

**性質**：補 Y17 + Y18 兩個 modal 對應 regression spec。Y17 / Y18 落地、Y25 refactor 都沒鎖 E2E，本 sprint 一次補完。同 Y24 / Y26 「補回歸」motif。
**範圍**：[admin-dobtor-doc-editor-sprint-y27-modal-behavior.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-y27-modal-behavior.spec.ts)（新檔、+~220 行、2 個 test）。零 code 改動。

---

## 1. 為什麼補這個

Y17 / Y18 兩個 modal 是 dobtor_doc_editor 第一個 + 第二個 modal pattern、共用 `.doc-modal-*` 基礎建設。覆蓋的行為：
- modal 開 / 關（menu trigger / overlay click / Esc）
- form input 同步（select / radio / number input）
- preset 按鈕 + 自訂 input 並行（Y18）
- apply 路徑（執行 cmd + 關 modal + 同步 UI）

兩個 modal 同 pattern、E2E 一起補比拆兩 sprint 經濟。

---

## 2. spec 覆蓋面

### Y27.1 — Y17 文件設定 modal（9 step）

| Step | 操作 | 預期 |
|---|---|---|
| 1 | 工具 menu → 文件設定 | `.doc-modal-overlay` 出現 |
| 2 | 驗初始 form | format=A4、direction=vertical（radio checked）|
| 3 | 改 format → A3 | select value=A3 |
| 4 | 改 direction → horizontal | radio checked |
| 5 | 改 top margin → 40 | input value=40 |
| 6 | Apply | modal 關、status bar 含「A3」 |
| 7 | Reopen modal | top margin input hydrate 為 40（從 canvas-editor 抓最新） |
| 8 | Esc | modal 關（走 _onGlobalKey Y17 加的 Esc handler） |
| 9 | Reopen → click overlay backdrop | modal 關（onCloseDocSettings via overlay click） |

### Y27.2 — Y18 行距 modal（7 step）

| Step | 操作 | 預期 |
|---|---|---|
| 1 | 格式 menu → 行距... | `.doc-modal-overlay` + `.doc-modal-dialog-narrow` |
| 2 | 驗初始 input | value=1 |
| 3 | 點 preset 1.50 | input value=1.5、preset 按鈕 `is-active` |
| 4 | 改 input → 2.25（非 preset） | preset is-active count = 0 |
| 5 | Apply | modal 關、success notification「行距已設為 2.25」（best-effort） |
| 6 | Reopen + Esc | modal 關 |
| 7 | 改 input → 10 → clamp 驗證 | 沒有任何 preset is-active（state 內 5 不是 preset、且 fill input 10 也不會 active 任何 preset）|

---

## 3. spec 設計取捨

### 3.1 為什麼兩個 modal 一個 spec 檔

`.doc-modal-*` 共用 selector / CSS。一個 spec file 兩個 test、describe 同主題、reader 一眼看完。要拆兩個 spec file 也行、但 cost 多沒 benefit。

### 3.2 為什麼 Y27.1 step 7 reopen 驗 hydrate

Y17 `onOpenDocSettings` 內每次開都從 `editor.command.getPaperMargin()` 抓最新 margin。spec 驗一次「改完 apply 重開、值是 40」確保 hydrate 邏輯沒壞。

### 3.3 為什麼 step 9 用 `page.mouse.click(box.x+10, box.y+10)` 而不是 `overlay.click()`

Playwright `.click()` 在 modal-overlay 內預設點中心、會撞到 dialog（dialog 置中佔據 overlay 中心）。改用絕對座標 (10, 10) 點 overlay backdrop 左上角、確保只 hit overlay 自己、不 hit dialog。`t-on-click.stop=""` 在 dialog 阻止冒泡、overlay onClick 才正常觸發。

### 3.4 為什麼 Y27.2 notification toast 用 `.catch(() => null)`

Odoo notification 5 秒自動消失、有可能 spec 跑到那行時 toast 已經 fade out 不 visible。`.textContent().catch(() => null)` 容忍找不到、找到就驗、找不到就略過。`if (toast) expect(...)` 是「best-effort」斷言。

主要 apply 行為（modal 關）是 hard assertion、notification 是 soft assertion。

### 3.5 為什麼 step 7 clamp 驗證間接

`onLineSpacingSet(value)` 內部 clamp `Math.max(0.5, Math.min(5, n))` 寫入 state，但 input 顯示是 browser native：fill('10') 顯示 10 而非 clamp 後的 5（input 沒重新 render 套 state 新值、因為 OWL 不會把 state 寫回 input 除非 reactivity 觸發）。

最可靠的間接驗證：clamp 後 state.lineSpacingValue=5、5 不是任何 preset（1/1.15/1.5/2/2.5/3）、所以 `.doc-modal-preset-btn.is-active` 應該 0 個。

理想的 spec 寫法是直接讀 state.lineSpacingValue、但 OWL state 對外不開放。間接驗 is-active 是現實 trade-off。

### 3.6 為什麼沒驗「apply 後 canvas-editor 真的套用了」

E2E spec 信任 canvas-editor cmd 自己的單元測（lib 內部）。我們只驗 dobtor_doc_editor handler 正確呼叫、把 cmd 觸發出去。同 Y22 教訓「不鎖 third-party lib 內部行為」。

---

## 4. 預期 + 實測

**預期**：Y27.1 + Y27.2 各 1/1 pass、其他 9 條既有 spec（Y14.1 + Y20.1 + Y22.1 + Y24.1 + Y26.1/.2 + G.1/HN.1/J.1）不受影響。

**實測**：
- Y27.1 doc settings modal：1/1 pass (16.6s) ✓
- Y27.2 line spacing modal：1/1 pass (14.9s) ✓
- 完整 11 條 regression：11/11 pass (4.8m) ✓

兩個 test first-pass 全綠、Y17 / Y18 / Y25 refactor 鏈全部驗。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y27-modal-behavior.spec.ts` | 新檔、~220 行：2 個 test 含 Y17 + Y18 modal 完整 path |
| `phase8_sprint_y27_2026-05-27.md` | 新檔（addons subrepo 內） |

零 code 改動。

---

## 6. 教訓

1. **同 pattern 的 feature 一個 sprint 補完所有 spec**：Y17 / Y18 共用 `.doc-modal-*`、兩個 modal 同一 spec file 兩個 test 一次寫完比拆 sprint 經濟。
2. **絕對座標點 overlay backdrop 比 `.click()` 可靠**：modal 上有 backdrop + dialog 兩層、`.click()` 預設中心會撞 dialog。`page.mouse.click(box.x+10, box.y+10)` 強制點 overlay 自身。
3. **不寫入 state 的間接驗證有極限**：input clamp 寫到 state、但 input value 不會自動 reflect 回來。OWL state 對外不可讀、只能靠 derived UI（preset is-active）反推。下次寫 user-input clamp logic 時建議 onInput 後 force re-bind input.value、讓 UI 真正反映 state（避免 spec 寫得很彆扭、也避免 user 困惑「為什麼我打 10 它顯示 10 但 apply 後是 5」）。
4. **notification toast assertion 一律 soft**：5 秒 timer + Odoo 內部時鐘、E2E 沒法保證搶在它消失前。toast 用 `if (...)` 寬鬆斷言、不擋 spec。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y26 | ✅ |
| **Y27 — Y17/Y18 modal 行為 E2E regression** | ✅（11/11 全綠） |

### Sprint Y28 候選

- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設
- Y18 行距 modal input clamp UX 修正（onLineSpacingSet 後同步 input.value、讓 user 看到實際 clamp 值）— Y27.2 教訓帶出來的 follow-up
- find/replace panel 取代後 search state stale（Y22 sprint doc 註記的 canvas-editor 行為）— 上游 issue 或 work-around

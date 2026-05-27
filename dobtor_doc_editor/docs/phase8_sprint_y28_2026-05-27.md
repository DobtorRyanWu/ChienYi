# Phase 8 Sprint Y28 — 行距 modal input clamp UX 修正（2026-05-27）

**性質**：Y27 補 spec 時帶出的 UX bug — Y18 行距 modal user 在 number input 打超出 `[0.5, 5]` 範圍的值（例如 10），`onLineSpacingSet` 內部 clamp state 為 5、但 input UI 仍顯示「10」。User 困惑「我打 10、怎麼套用後變 5」。Y28 加 4 行 fix：input event 觸發 clamp 時、把 input.value 也設成 clamp 後值、user 立刻看到。
**範圍**：`doc_editor.js`（+~8/-~4 行）、`doc_editor.xml`（修 1 個 `t-on-input` 參數）、Y27.2 spec 加緊（驗 input.value 反映 clamp）、新建 sprint doc。

---

## 1. 為什麼開這個

Y27.2 step 7 驗 clamp 時、原本只能驗「state 已 clamp」（透過 preset is-active=0 反推）、無法驗 input UI。因為 OWL `t-att-value` 只寫 attribute、不會覆蓋 user input 的 `.value` property（DOM input element 的 attribute / property 在 user typing 後 diverge、native 行為）。

Y27 sprint doc §3.5 已明寫這是「現實 trade-off、下次 Y28+ 可考慮 onInput 後 force re-bind input.value」。今天兌現。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onLineSpacingSet(value, ev = null)` | 新 optional 第二參數；clamp 後若 `clamped !== n` 且 `ev?.target` 存在、`ev.target.value = String(clamped)` |
| `doc_editor.xml` | `t-on-input="(ev) => this.onLineSpacingSet(ev.target.value)"` → `... (ev.target.value, ev)`（preset button 點擊不傳 ev、不受影響） |
| Y27.2 spec step 7 | 從「驗 is-active=0」加緊為「驗 input.value='5'」+ 補下界 fill('0.1') → 驗 '0.5' |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼 ev 是 optional second param 而不是 split 兩個 method

`onLineSpacingSet(value)` 同時被 input handler 與 preset button click 呼叫。Split 成 `_onLineSpacingInput(ev)` + `_setLineSpacing(value)` 也 work 但兩個 method 容易脫鉤。Optional 第二參數最 minimal、preset 按鈕的呼叫 site 完全不動（`() => this.onLineSpacingSet(preset)` 仍 valid、ev 為 undefined）。

### 3.2 為什麼比較 `String(clamped) !== String(value)` 而不是 `clamped !== n`

`value` 是 user 打進去的字串、可能 "10"、"10.0"、"0.1"。`n = Number(value)` 可能等於 `clamped`（例如 user 打 "5"、clamped 也 5、不需要 reflect）。`String(clamped) !== String(value)` 容錯：
- "10" vs String(5)="5" → 不同、reflect 必要
- "5" vs String(5)="5" → 同、不 reflect
- "5.0" vs "5" → 不同、reflect（user 打 5.0、強制顯示 5；雖然 trivial UI 改變、無傷大雅）

也避免 `0.5 !== Number("0.500")`（其實這條 === true、但顯示上差別仍要 reflect）。

### 3.3 為什麼不對 doc settings modal 的 margin 做同樣處理

Y17 文件設定 modal 的 margin input min=0、max=80。`onDocSettingsSet(field, value)` 內 clamp 後寫 state — 但 t-att-value bind 是 `state.docSettingsForm.marginTopMm`、不是直接從 user input、應該每次 OWL re-render 時都會更新 input.value。實測（Y27.1 沒驗 clamp、所以沒抓出來）：可能也有同樣問題、但 Y28 先 focus 在 Y27 帶出的具體 bug、Y29+ 一併查 doc settings 的 clamp UX。

### 3.4 為什麼 spec 不另開 Y28 spec file

Y27.2 spec 已經有 clamp 那條 step、只是 assertion 弱。加緊 assertion 比新開檔案 cost 低 + 維護面集中。

---

## 4. 預期 + 實測

**預期**：user 打超出 [0.5, 5] 的值，input 立刻顯示 clamp 後值、不留 stale 顯示。

**實測**：
- Y27.2 spec step 7 加緊：fill('10') → input value=5 ✓、fill('0.1') → input value=0.5 ✓
- 11/11 regression：Y14.1 + Y20.1 + Y22.1 + Y24.1 + Y26.1/.2 + Y27.1/.2 + G.1/HN.1/J.1 (3.8m) ✓
- Y27.2 從原 14.9s → 15.3s（多兩條 assertion、~0.4s 增量）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~8/-~4 行：`onLineSpacingSet` signature + clamp-time input.value reflect |
| `doc_editor.xml` | 修 1 個 `t-on-input` 多傳 `ev` |
| `admin-dobtor-doc-editor-sprint-y27-modal-behavior.spec.ts` | step 7 加緊 + 補下界 assertion（top-level repo） |
| `phase8_sprint_y28_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **OWL `t-att-value` 不覆蓋 user-typed input value**：DOM input element 的 attribute / property 在 user typing 後 diverge — `t-att-value` 設 attribute、但 user typing 已經寫了 .value property、後者覆蓋 attribute 在 render 上的效果。要強制 sync 必須手動 set `el.value = ...`。下次任何 reactive form input 帶 clamp / mask / format / 限制邏輯時記得加。
2. **spec 補回歸時帶出的小 UX bug 立刻修勝過記下次**：Y27 補 spec 時發現 clamp UX 問題、立刻 Y28 兌現 < 24 小時內。記下次容易遺漏、且越久越難回想 context。
3. **optional second param 是 polymorphic handler 的乾淨擴充**：原 1-arg 呼叫 site 不用動、新 caller 多傳 ev、舊行為向後相容。比 split method 簡潔。
4. **String() 比 numeric === 比較更安全**：浮點 / 不同字串表達同一數值（"5.0" vs "5"）的處理、用 String() 化齊比較最穩、且 force reflect 時也是 String 值。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y27 | ✅ |
| **Y28 — 行距 modal input clamp UX 修正** | ✅（11/11 全綠、Y27.2 spec 加緊）|

### Sprint Y29 候選

- Y17 文件設定 modal margin input 同類 clamp UX 檢查（可能同樣有 attribute/property diverge 問題、Y28 motif 套上）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- find/replace panel 取代後 search state stale（Y22 sprint doc 註記、可能要 work-around 或 upstream patch）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設

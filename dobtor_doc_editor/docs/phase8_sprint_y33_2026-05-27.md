# Phase 8 Sprint Y33 — find/replace panel nav button 也 disabled（2026-05-27）

**性質**：Y32 follow-up 收尾完整化 — Y32 鎖了「取代」+「全部取代」disabled（findMatchCount === 0 時），上一個/下一個 nav button 仍可點、跟兩顆動作 button 視覺/行為不一致。Y33 補一致：4 顆動作 button（prev/next/取代/全部取代）統一在 0 match 時 disabled、「關閉」按鈕例外（user 仍需可關 panel）。
**範圍**：`doc_editor.xml`（prev/next 各加 `t-att-disabled`、+2 行 attribute + 註解）、`doc_editor.css`（`.doc-find-btn:hover` 加 `:not(:disabled)` + 新增 `:disabled` 樣式）、Y22.1 spec 加 5d step 驗 prev/next disabled + 關閉 button 仍 enabled、新建 sprint doc。

---

## 1. 為什麼開這個

Y32 sprint doc Y33 候選第一條：「『上一個』/『下一個』navigate button 也 disabled（findMatchCount === 0 時、cursor nav UI 完整化）」。Y32 修了取代 button、Y33 兌現 nav button、整個 panel 4 顆動作 button 鎖一致。

不修的話：drain 完 user 看「無結果」、取代灰、但上/下一個還是亮亮的、視覺矛盾、user 可能誤判（「咦是不是還有 match、只是被取代 button 鎖住？」）。一致性是 UI / UX 第一原則：相同條件下、同類元件應有同樣狀態。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `doc_editor.xml` prev button | 加 `t-att-disabled="state.findMatchCount === 0"` |
| `doc_editor.xml` next button | 加 `t-att-disabled="state.findMatchCount === 0"` |
| `doc_editor.xml` close button | **不動**（panel 關閉是獨立操作、不該被 disable） |
| `doc_editor.css` `.doc-find-btn:hover` | 改 `:hover:not(:disabled)` |
| `doc_editor.css` `.doc-find-btn:disabled` | 新增（icon-only button、opacity 0.5、`color: var(--gd-text-muted)`、`cursor: not-allowed`） |
| Y22.1 spec step 5d | drain 完驗 prev + next disabled、驗 close button 仍 enabled |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼「關閉」button 不一起 disable

關閉是 panel 生命週期操作、跟 match 數無關。即使 findText 空 / 0 match、user 仍應能關 panel。Disable 關閉 = trap user 在 panel 內、要按 Esc 才能離開 = 違反「user 永遠能 escape 任何 modal/panel」UX 原則。

明寫在 XML 註解（`<!-- 關閉 button 不 disable：findText 空時 user 應仍能關 panel -->`），未來改動者一眼知道刻意保留。

### 3.2 為什麼 opacity 用 0.5 不是 Y32 的 0.6

`.doc-find-btn`（prev/next/close）是純 icon button、沒文字、視覺密度低。0.5 比 0.6 更能拉開 disabled 跟 normal 差距、避免 user 誤以為「只是 hover 過後的殘影」。

`.doc-find-btn-text`（取代/全部取代）有文字、視覺密度高、0.6 已夠暗。同 family 但兩個 variant 各自微調 opacity 是合理 craft。

### 3.3 為什麼不在 disabled 時也改變 cursor 之外的行為

選 trade-off：「不要做更多」。例如可以把 prev/next disabled 時也 hide tooltip、避免 user 看 tooltip 又點不到的尷尬。但 tooltip 是 OS-level（HTML `title` attribute）、CSS 無法 hide、且 native tooltip 本就被 OS 控制、user 接受度高。不過度工程。

### 3.4 為什麼 spec 加在 5d 不是另起獨立 test

Y22.1 step 5b drain 完已建立「count === 0」的 state、5c 驗取代 button disabled、5d 順勢驗 nav button disabled = 同 state 不同 button 的延伸驗證、cohesion 高。

獨立 test 要重做 fixture setup + drain（多 20s）、零收益。同 step 5d 加 4 行 assertion = ROI 最高。

### 3.5 為什麼 5d 也驗「關閉」button enabled

正向驗證 = 防回歸。如果未來有人圖一致把所有 4 顆 button 都加 disabled（含關閉）、spec 立刻紅。明寫「關閉 should be enabled」鎖刻意設計、不留 silent regression 空間。

Y32 教訓 §3.7 用 force click 驗 disabled UI 不破 state；Y33 用正向驗證 close button 仍 enabled = 同思路、不同切角。

### 3.6 為什麼不加 keyboard shortcut 的 disabled handling

Enter / Shift+Enter 鍵盤觸發 onFindNext / onFindPrev 在 `_onGlobalKey`、不過 button click。Y33 只動 UI button、handler 本身（onFindNext / onFindPrev）已有 `if (!findText) return` 短路保護、即使從鍵盤觸發 0 match 時 noop。

如要進一步「鍵盤也 disable」就要在 `_onGlobalKey` 加 `findMatchCount === 0` 短路、scope creep。留 Y34+ 看是否真有需求。

---

## 4. 預期 + 實測

**預期**：drain foo 3 → 2 → 1 → 0、prev / next button 跟取代 button 一起灰、close button 仍亮。

**實測**：
- Y22.1 加緊（含 5d 4 行 nav button assertion）：1/1 pass (1.9m) — 比 Y32 的 58.7s 慢、E2E 機器負載波動可接受
- 8/8 sprint specs (Y14/Y20/Y22/Y24/Y26.1/Y26.2/Y27.1/Y27.2)：4.7m all green
- 視覺驗證：4 顆動作 button 一致灰、close button 仍可點 ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.xml` | prev + next 各加 1 行 `t-att-disabled`、close 加註解（共 +3 行） |
| `doc_editor.css` | `.doc-find-btn:hover` 加 `:not(:disabled)`、新增 `.doc-find-btn:disabled` 4 行 |
| `admin-dobtor-doc-editor-sprint-y22-replace-keyboard.spec.ts` | step 5d 加 7 行（locator + 3 assertion + 註解）（top-level repo） |
| `phase8_sprint_y33_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **「一致性」是 UI sprint 的 driving force**：Y32 鎖取代 button、Y33 補 nav button 是純為一致 — 沒新增功能、沒修 bug、只把「相同條件下同類元件視覺一致」這個 invariant 鎖滿。沒這個 sprint，user 看到「無結果但 nav button 還亮」會生疑、心理模型受損。一致性 sprint 的 ROI 是「user 心理模型不破」、值得 0.5 天工。
2. **例外要明寫**：4 顆動作 button 一致 disable，但「關閉」要例外（panel escape 需求）。XML 註解 + spec 正向驗證（toBeEnabled）兩處都鎖、未來改動者不會「順手把關閉也 disable 求一致」。例外比規則更需文件化。
3. **同 family CSS 微調 opacity 是 craft 不是 noise**：icon button 0.5 / text button 0.6 看似 nitpick、但 user 視覺接收 icon vs text 的密度不同、要分別校。Y28 教訓「fix 的一致性比 fix 本身重要」反過來說「同 family 不同 variant 的微調也是一致性 craft」、不是「Y32 用 0.6 所以 Y33 也得用 0.6」。
4. **同 step 加 assertion > 新增 step / test**：fixture setup + state arrival 是 E2E 最貴成本、複用 step 5b 完成的 drain state 加 5c (Y32) + 5d (Y33) = 同個 state 鎖兩層 invariant、每 sprint +5-7 行 spec、總體積 / 跑時線性。新增 test = 重做 fixture = 20s+ 浪費。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y32 | ✅ |
| **Y33 — find/replace panel nav button 也 disabled** | ✅（8/8 sprint specs 全綠、4 顆動作 button 一致 + close 例外明寫）|

### Sprint Y34 候選

- 「全部取代」notification「已取代 N 個項目」spec 覆蓋（onReplaceAll 的 count 顯示）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊（修 baseline 或加 sub-nav 切到「範本」前驗證）
- find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable（雖然 handler 已短路、但 UX 完整性可考慮）

# Phase 8 Sprint Y31 — onReplaceOnce 後 cursor navigate next（2026-05-27）

**性質**：Y30 follow-up UX 完整化 — Y30 修好「真正單一替換 + count refresh」、但 cursor 仍停在替換掉的位置（原文已被新字串覆蓋、user 看不到 highlight）。Y31 加 1 行 re-search refresh canvas-editor 內部 search state、cursor 自動跳到剩餘第一個 match、跟 Google Docs / VS Code「替換完自動 navigate next」UX 一致。
**範圍**：`doc_editor.js`（+~7 行）、Y22.1 spec 加緊（從 1 click 取代延伸成 3 click 連續取代、驗 cursor 真的 navigate 而不是卡在原位）、新建 sprint doc。

---

## 1. 為什麼開這個

Y30 把 onReplaceOnce 從「全替換」修成「替換第 0 個 + 算剩餘 count」。功能對了、但 UX 還缺一塊：cursor 留在剛被替換的位置（已是新字串、不再 match）、user 看到「1 / 2」但沒有 highlight 指向「下一個 1 在哪」。

對比 Google Docs / VS Code 「替換」按鈕：點一次 → 第 1 個被替換 + cursor 自動跳第 2 個 → 點再一次 → 第 2 個（新的第 1 個）被替換 + 跳第 3 個 ...。Y31 補這條 navigate-next semantic。

實作很小（1 行 re-search）、但 UX 影響大：user 連續按「取代」清乾淨整份文件 = 自然流程。沒這 fix 的話、user 點完一次要手動按「下一個」才能 navigate。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onReplaceOnce` | flat text count refresh 完、若 count > 0 再 `executeSearch(findText)` 一次、refresh canvas-editor 內部 search 狀態 + cursor 自動跳第一個剩餘 match |
| Y22.1 spec step 5 / 5a / 5b | 從「click 取代 1 次驗 [12]/2」延伸：click 取代 3 次連續、驗序列 `[12]/2 → 1/1 → 無結果` |
| Y22.1 spec step 6 | 改為「3 次取代後 全部取代應 noop（不 crash）」、不再驗主要替換 |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼用 `executeSearch(text)` 而不是 `executeSearchNavigateNext`

兩個都能讓 canvas-editor 內部 cursor 移到剩餘第一個 match。差別：

- `executeSearch(text)`：重新掃描整份文件、建立新的 matchList、cursor 自動定位第 0 個。
- `executeSearchNavigateNext`：在現有 matchList 內前進。如果 matchList stale（剛 replace 過、文件變了），navigate 可能跳到不存在的位置。

Y30 之後文件每次都會變、matchList 必須 refresh。`executeSearch` 同時做 refresh + cursor reset、一招打兩個目標。

### 3.2 為什麼放在 count refresh 之後

順序：replace → count refresh（state 同步）→ re-search（cursor 同步）。

理由：state.findMatchCount 是 UI 直接讀的 reactive 值、優先更新讓 user 看到「1 / 2」立即反映。canvas-editor 內部 cursor 是視覺 highlight、稍後 update 也 ok（user 視覺感受微秒差）。

### 3.3 為什麼 try/catch 包住 re-search

re-search 不會影響 state（state 已經算好）、純粹是 canvas-editor 內部 highlight refresh。失敗也只是少了 highlight、user 仍能看 count + 手動按「下一個」。所以單獨 try/catch 吞錯、不影響主流程。

### 3.4 為什麼 spec 改成 3 click 連續取代

新行為要驗的是「連續 click 取代能自然替換完所有 match」、單一 click 只驗第一步。3 click 是 fixture (3 個 foo) 的全部 path、覆蓋：
- 第 1 click：3 → 2（首次替換 + cursor 跳）
- 第 2 click：2 → 1（cursor 正確指向新第 1、替換 + 跳）
- 第 3 click：1 → 0（最後一個、cursor 不再有目標、UI 顯「無結果」）

如果 cursor 沒 navigate、第 2 click 替換的會是「原本就 replaced 過的位置」、結果亂掉。spec 直接覆蓋這個 path 鎖回歸。

### 3.5 為什麼 step 6 全部取代改 noop 驗證

step 5b 已經 drain 完所有 foo、step 6 click 全部取代 = 沒東西可替換。應該 noop（不 crash）。

Y22 原本 step 6 期望「全部取代後從 2 變 0」、現在前置條件變了（已是 0）。改 step 6 sequence 邏輯一致。

### 3.6 為什麼不也加「取代」按鈕 disabled 條件

Y31 focus 在 cursor navigation。Disabled 條件（findMatchCount === 0 時 button disabled）是另一個獨立 UX 改進、scope 跟 cursor 不重疊、留 Y32+。

---

## 4. 預期 + 實測

**預期**：3 click 連續取代能自然走完 fixture 的 3 個 foo、最後顯「無結果」。

**實測**：
- Y22.1 加緊（含 5/5a/5b）：1/1 pass (42.6s) — 比 Y30 時的 16.4s 慢、因為多 2 次 click + wait（合理）
- 11/11 regression：4.4m all green
- count 序列實測：3 → 2 → 1 → 0（無結果）✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~7 行：count > 0 條件下 re-search refresh |
| `admin-dobtor-doc-editor-sprint-y22-replace-keyboard.spec.ts` | step 5 改成 const replaceBtn + 加 5a/5b 兩 click、step 6 改 noop |
| `phase8_sprint_y31_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **bug 修完不等於 feature 完成**：Y30 修了核心 logic、cursor 仍然沒 navigate；user UX 仍不滿足 expectation（GDocs / VSCode 都會自動跳下一個）。fix 完做一次 user-eye 驗證 = 把實際 click 順序走一遍想像、catch 這種「對但不完整」的差距。
2. **小 fix 大 UX 影響**：1 行 re-search call + count > 0 條件、實作 trivial、但 user 體感從「按一次按一次又按一次又按下一個又按取代...」變成「一直按取代到底」、體驗完全不同。連串高頻 user action 的 micro-friction 累積成大體驗差。
3. **spec 加緊跟著 fix 走**：Y30 鎖第 1 click「[12]/2」、Y31 fix 後加鎖第 2/3 click 序列。spec 隨 feature 完整度線性擴張、每個 sprint 把新 capability 鎖一層、不留 silent regression 空間。
4. **try/catch 包 non-essential UI 操作**：re-search 是 visual nice-to-have、不是 correctness 必要。包 try/catch 讓主流程不被 lib internal error 拖累、UX 還是降級而非崩潰。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y30 | ✅ |
| **Y31 — onReplaceOnce 後 cursor navigate next** | ✅（11/11 全綠、3-click 連續取代 path 完整鎖）|

### Sprint Y32 候選

- 「取代」按鈕 disabled 條件（findMatchCount === 0 時 disabled、防 user 浪費 click）
- 「全部取代」notification「已取代 N 個項目」spec 覆蓋（onReplaceAll 的 count 顯示）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證

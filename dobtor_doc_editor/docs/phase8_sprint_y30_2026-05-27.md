# Phase 8 Sprint Y30 — onReplaceOnce 真正單一替換 + count refresh（2026-05-27）

**性質**：Bug 修復 + UX fix。原本以為的「canvas-editor executeReplace 後 stale state」（Y22 sprint doc 註記）runtime probe 後發現是**完全不同的 bug**：`executeReplace(text)` 不傳 `{ index }` 時是 replaceAll、不是「取代當前一個」。我們的 `onReplaceOnce` 從 Y4 起就是誤命名 + 行為跟 button label「取代」不符（user 點「取代」期待單一替換、實際全替換完）。Y30 改用 `{ index: 0 }` 真正單一替換 + flat text indexOf 算剩餘 count、UI 顯「1 / n-1」連貫。
**範圍**：`doc_editor.js`（+~24/-~3 行）、Y22.1 spec 加緊（驗 `1 / 2` 取代後 count、之前因 stale state 跳過）、新建 sprint doc。

---

## 1. 為什麼開這個

Y22 sprint doc §3.1 註記「canvas-editor 的 executeReplace 後 search state stale」、結論「不鎖中間 count」。Y30 開工想沿用 Y28/Y29 motif 加 re-search refresh、實作後仍然「無結果」。

runtime probe 揭露真相：

```
count after find: 1 / 3        ← user fill foo、看到 3 個 match
count after 取代: 無結果         ← click 取代 → canvas-editor 回 count=0
inputs after 取代: find=foo replace=baz  ← input 沒清
count after refill foo: 無結果   ← 不是 stale state、是文件真的 0 個 foo 了
count of baz: 1 / 3             ← 全部 3 個都換成 baz 了！
```

對照 canvas-editor 原始碼 `replace(payload, option)`：

```js
let matchList = this.getSearchMatchList();
const replaceIndex = option == null ? void 0 : option.index;
if (isNumber(replaceIndex)) {
    // ...replace only that match group
} else {
    // payload 不傳 index → 用整個 matchList = 全部替換
}
```

確認：我們的 `executeReplace(text)` 因為沒傳 `{ index }` 就是全替換、跟 button label「取代」(single) 完全不符。Y4 寫的時候就誤解了 API、Y22 sprint doc §3.1 解讀也錯了（誤以為是 stale state、實際是 replaceAll）。

不修的話 user click「取代」 = click「全部取代」、上面的「全部取代」按鈕變成冗餘 + 心理模型壞。Y30 修。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onReplaceOnce` | `executeReplace(text)` → `executeReplace(text, { index: 0 })`、真正單一替換 |
| `onReplaceOnce` count refresh | 不靠 canvas-editor `getSearchNavigateInfo()`（stale 0）、改用 `flattenElementsToText` + `indexOf` 算剩餘 match 數 |
| Y22.1 spec step 5 | 從「不驗中間 count（lib 行為不鎖）」加緊為「驗 `[12] / 2`」 |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼 `{ index: 0 }` 是「當前 match」

canvas-editor 內部 `matchList = getSearchMatchList()` 是按文件順序 sort 的。index 0 = 文件中第一個 match = user 看到「1 / N」當前 highlight。

替換 index 0 後、新 search 結果（如果再 search）會把原 index 1 推到 index 0、cursor 自動跳下一個。`executeSearch` + `executeReplace({index:0})` loop 等效於「取代當前 → cursor 跳下一個」流程。

User flow 變這樣：click 取代 → 第 1 個被替換 → count 顯「1 / 2」→ click 取代 → 第 1 個（原第 2 個）被替換 → 「1 / 1」→ click 取代 → 最後 1 個被替換 → 「無結果」。每次 click 都消耗 1 個 match、UX 連貫。

### 3.2 為什麼 flat text indexOf 算 count、不靠 canvas-editor

`getSearchNavigateInfo()` 在 replace 後即使再 `executeSearch` 仍可能 stale。flat text indexOf 是 100% 客觀（document 字串 indexOf）、不依賴 canvas-editor 內部 search state。

cost：每次 click 取代 + getValue + walk doc。對小 doc trivial。大 doc（>10k 字）也只是 ms 級。`onReplaceAll` 內部也用同 strategy、reuse pattern。

### 3.3 為什麼 findMatchIndex 固定設 1

精確 cursor position 不可靠取得（canvas-editor 沒 public API、且 replace 後 cursor 位置語意未定）。剩 match 時固定 index=1 給 user 看「1 / n」、按「下一個」按鈕（Y4 既有）會 navigate 到實際下一個。可接受 trade-off。

### 3.4 為什麼不也改 `onReplaceAll`

`onReplaceAll` 是 explicit 「全部取代」、整段 `executeReplace(text)` 在 SAFE_GUARD loop 內、每次替換一群 matches、loop count + flat indexOf 自我終止。已經 work。不動。

實測 Y22.1 step 6「全部取代」仍正確走、step 7 refill foo 後驗「無結果」也仍 pass。Y30 改 onReplaceOnce 只後 Y22.1 變成兩條 path 都鎖：取代後「1 / 2」+ 全部取代後「無結果」。

### 3.5 為什麼不重新命名 button label

「取代」現在真的是單一替換、「全部取代」依舊是 replace all。Y4 button label 並沒誤名、只是 handler 實作沒對齊。Y30 對齊 handler 行為到 label 預期。User-facing 字串零改動。

### 3.6 為什麼 spec 容許 `[12] / 2` 而不只 `1 / 2`

cursor 在第 0 個替換掉後可能跳第 0（新的、原 idx=1）或停留 0（顯示「1」）— canvas-editor 內部行為不擔保。`/[12]\s*\/\s*2/` 容許 1 或 2 開頭、總數必須 2。實測拿到「1 / 2」、但容錯給未來行為微變。

---

## 4. 預期 + 實測

**預期**：
- click 取代 → 替換第 1 個、count 顯「1 / 2」
- click 取代 → 替換第 1 個（原 2）、「1 / 1」  
- click 取代 → 替換最後 1 個、「無結果」

**實測**（runtime probe）：

| 操作 | count 顯示 | 文件 baz 數 |
|---|---|---|
| fill foo | 1 / 3 | 0 |
| click 取代 | **1 / 2** ✓ | 1 |
| refill foo | 1 / 2 ✓ | — |
| count of baz | 1 / 1 ✓ | 1 |

E2E：11/11 pass (5.0m)、包含 Y22.1 加緊版（[12] / 2 assertion）。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~24/-~3 行：onReplaceOnce 改 executeReplace 傳 index + flat text count refresh |
| `admin-dobtor-doc-editor-sprint-y22-replace-keyboard.spec.ts` | step 5 從「不驗中間」加緊為「[12]/2」assertion（top-level repo） |
| `phase8_sprint_y30_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **runtime probe > 文件結論**：Y22 sprint doc §3.1 結論「stale state」漏了真相。Y30 一個 probe 命中根本問題（executeReplace 是 replaceAll）。下次任何「lib 行為」結論前先 probe 看實際 doc / state 變動、不要相信 commit comment 或 sprint doc 對 lib API 的解讀。
2. **lib API 的 default param 容易踩雷**：canvas-editor `replace(payload, option)`、option 可選、`option == null` 走全替換 path。文件沒明寫、原碼才能看出。下次任何 lib API 的 optional config object 都該檢查它 default 是 most-conservative 還是 most-aggressive。
3. **誤名 handler 累積 27 個 sprint 才修**：Y4 命名 `onReplaceOnce` 跟 button label 對齊、但實作走 replaceAll 從 sprint 1 起就 wrong。沒 user 抱怨 + 沒 spec assert = bug 默默活 27 個 sprint。**spec 補回歸不只防退步、也是「主動找實作 vs 預期 gap」的手段**。Y22 spec 補時若敢硬 assert「1 / 2」、bug 立刻曝光、Y22 就修了不必拖到 Y30。
4. **flat text count 是 canvas-editor 內部 state 的 ground truth**：UI count 應該獨立於 lib internal、靠文件實際內容算。`onReplaceAll` 內部本來就是這 pattern、`onReplaceOnce` 沿用一致。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y29 | ✅ |
| **Y30 — onReplaceOnce 真正單一替換 + count refresh** | ✅（11/11 全綠、Y22.1 加緊版鎖回歸）|

### Sprint Y31 候選

- onReplaceOnce 後 navigate 到下一個 match（cursor 跳 next、跟 click「下一個」按鈕一致 UX）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證
- 「取代」按鈕 disabled 條件（findMatchCount === 0 時 user 不該能點）UX 強化

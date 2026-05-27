# Phase 8 Sprint Y34 — onReplaceAll notification count fix + 加 spec 覆蓋（2026-05-27）

**性質**：spec 覆蓋意外揭露 silent bug — Y34 原本只想加 Y22.2 spec 鎖「全部取代」notification 行為（drain N 個 foo 後驗「已取代 3 個項目」+ count 歸零 + 4 button 全 disabled）、實測 notification 顯「已取代 1 個項目」、確認 onReplaceAll 從 Y4 起就誤算 count。Y34 從純 spec sprint 升級為 bug fix + spec、用 pre-scan flat indexOf 算真實 count。
**範圍**：`doc_editor.js`（onReplaceAll +~10 行 pre-scan + 移除 `count++` 寄生在 loop iteration）、Y22 spec 加 Y22.2 test（+~45 行、fresh fixture 驗 happy path）、新建 sprint doc。

---

## 1. 為什麼開這個

Y32 sprint doc Y33 候選列出 5 條、Y33 兌現 nav button disabled、Y34 候選清單仍有「全部取代 notification N 個項目 spec 覆蓋」。看起來純 spec 覆蓋。

開始寫 Y22.2 test 後 first run：
```
Error: expect(received).toMatch(expected)
Expected pattern: /已取代\s*3\s*個項目/
Received string:  "已取代 1 個項目"
```

User fixture 是 3 個 foo、實測替換完文件變 3 個 baz、但 notification 說「1 個」。挖原 code：

```js
for (let i = 0; i < SAFE_GUARD; i++) {
    const flat = flattenElementsToText(data.main || []);
    if (flat.indexOf(this.state.findText) < 0) break;
    this.editor.command.executeSearch(this.state.findText);
    this.editor.command.executeReplace(this.state.replaceText || '');
    count++;
}
```

Y30 已揭露 `executeReplace(text)` 不傳 `{ index }` 就是 replaceAll。所以 loop 通常只跑 1 次：替換全部 3 個 foo、第 2 次 iteration `flat.indexOf` < 0 break、count = 1。

舊版邏輯預設「每 iteration = 替換 1 個」、但實際每 iteration = 替換全部。bug 從 Y4 起跟 onReplaceOnce 一起活了 30 個 sprint、沒 user 抱怨（替換正確、只是 notification 數字錯）+ 沒 spec assert = silent。

Y34 兩件事一起做：
1. 補 spec（Y22.2、fresh fixture 驗 happy path、鎖 notification + count + button invariant）
2. 順手修 bug（pre-scan flat indexOf 算 count）

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onReplaceAll` count 算法 | 從 loop count++ 改成 pre-scan original flat indexOf count needle 次數 |
| 取代 loop | 保留（defensive：lib 萬一沒一次替換完仍 work）、移掉 `count++` |
| Y22.2 test | 新增 (~45 行)：fresh fixture (3 foos)、Ctrl+H 開 → fill foo + baz → click 全部取代 → 驗 notification「已取代 3 個項目」+ count 「無結果」+ 4 button disabled + close enabled |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼 pre-scan 不 post-scan

兩個都能算 count、差別：
- pre-scan：原文 foo 出現次數（user 看到的 N）
- post-scan：替換後文 baz 出現次數（理論等於 pre）

兩個值同（無 edge case）。pre-scan 簡單、replaceText 為空或包含 needle 時也 robust（baz 不含 foo 才能 round-trip）。實作前先掃 + 直接用、不依賴替換後狀態。

### 3.2 為什麼保留 SAFE_GUARD loop

執行替換 loop 是 defensive：lib 萬一某版本沒一次 replaceAll 完整（只替換 highlight 範圍）、loop 多跑幾次補完。Y30 雖確認當前版本是 replaceAll、但保留 loop 防未來 lib 行為微變。

Cost：替換完成後仍 loop 一次（第 2 iteration flat.indexOf < 0 break）= 1 extra getValue + flatten。對小 doc trivial。

### 3.3 為什麼 onReplaceOnce 不需要同樣修

onReplaceOnce 用 `executeReplace(text, { index: 0 })` 真正單一替換（Y30 修）、handler 不算 count、由替換後重 scan 算 findMatchCount 顯示「剩餘 N」。count 來源不同、不受此 bug 影響。

### 3.4 為什麼 spec 用「fresh doc」而不是延續 Y22.1 fixture

Y22.1 drain 完所有 foo、再加 5e/5f/5g/... 跑「全部取代」會卡（count = 0 全部取代是 noop、已被 Y32 spec 鎖過）。要 happy path 必須有 match、所以 fresh fixture。

bootstrap function 本就 reusable、加 Y22.2 test 用相同函數 = ~45 行新 test 含 setup/teardown / 6 assertion、scope 緊。

### 3.5 為什麼 Y22.2 一併驗 Y32+Y33 invariant（4 button disabled）

「全部取代」執行完 count = 0、Y32/Y33 invariant（4 button disabled）應自動成立。Y22.2 順手驗 = 多 paths 入口（不只 drain 3 click、也驗 一次全部取代）達到同個終態、Y32/Y33 invariant 雙保險。

Cost：+5 行 expect。Value：未來改動 onReplaceAll 若忘了把 findMatchCount = 0、Y22.2 立刻紅。

### 3.6 為什麼 spec 加在 Y22 spec file 不是新 file

Y22 spec file 是 find/replace replace mode 主場。Y22.1 鎖「取代」path、Y22.2 鎖「全部取代」path、cohesion 高。新 file 只為一個 test 過度切割。

---

## 4. 預期 + 實測

**預期**：3 個 foo → 全部取代 → notification「已取代 3 個項目」+ count 歸零 + 4 button disabled。

**實測**：
- Y22.1 + Y22.2：2/2 pass (1.4m) — Y22.1 沒被 onReplaceAll 修動到、Y22.2 是新驗證 path
- 9/9 sprint specs (Y14/Y20/Y22.1/Y22.2/Y24/Y26.1/Y26.2/Y27.1/Y27.2)：5.3m all green
- 視覺驗證：notification toast 顯「已取代 3 個項目」(info type、5 秒 fade) ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | onReplaceAll +~10 行（pre-scan needle count）-1 行 (count++)、註解標記 Y34 |
| `admin-dobtor-doc-editor-sprint-y22-replace-keyboard.spec.ts` | 加 Y22.2 test +~45 行（top-level repo） |
| `phase8_sprint_y34_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **想寫 spec、結果先補 bug — 第二次了**：Y30 想沿用 Y28/Y29 motif 加 re-search refresh、實測揭露 onReplaceOnce 是 replaceAll 不是 single replace。Y34 想加 spec 鎖 notification、實測揭露 onReplaceAll count 算錯。兩次都是「Y4 寫的時候就誤解 lib API、沒人寫 spec assert、bug 默默活 30 sprint」。**spec 補回歸的價值不只防退步、更是『現在跑一次就立刻 expose 過去靜默 bug』的探針**。Y4 沒寫 spec 是失誤、Y22 補 spec 時還沒大膽 assert 是第二次失誤、Y34 才補上。
2. **silent bug 共通形式：count++ 假設 vs 實際 1:N**：Y30 是「replaceOnce 假設替換 1 個、實際全替換」、Y34 是「count++ 假設每 iteration 替換 1 個、實際每 iteration 替換 N 個」。共同 pattern = handler 寫法 assume lib API 行為、但沒驗證。下次任何 `for (...) { lib.call(); counter++; }` pattern 都該問「lib.call() 真的每次只動 1 個 unit 嗎？」。
3. **「pre-scan vs post-scan」是 robustness 抉擇、不是性能**：pre-scan 算原文 needle 出現次數 = user 看到的真相。post-scan 算結果 = 跟 needle/replaceText 重疊情況有關（baz 含 foo 就壞）。Robustness 上 pre-scan win、性能上一樣（單一 getValue + flatten）。下次任何 batch operation 想算 N，先用 pre-scan、除非 N 必須來自結果（例如 lib 跳過 invalid）。
4. **spec 寫死「應該是 3」會 expose silent bug**：Y22.2 直接 assert `/已取代\s*3\s*個項目/`、軟 assert `/已取代\s*\d+\s*個項目/` 也能過但不會 expose bug。**spec 應該 assert 期待值不是 lib 回值**、Y22.2 寫死 3 = 立刻紅 = bug 立刻浮。Y29 教訓「3 個 caller 還太早抽 utility」反向 = 「不要把 lib 回值當 ground truth、要自己算 ground truth 來 assert」。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y33 | ✅ |
| **Y34 — onReplaceAll notification count fix + Y22.2 spec** | ✅（9/9 sprint specs 全綠、count 從錯誤的 1 改為正確的 3）|

### Sprint Y35 候選

- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 字數統計實作（_countWords getter 顯示 notification、Y3 plan 候選之一）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable

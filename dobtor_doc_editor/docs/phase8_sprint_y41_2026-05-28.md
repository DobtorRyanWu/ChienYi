# Phase 8 Sprint Y41 — 預覽變數效果 source fix + Y40.1 success path 啟用（2026-05-28）

**性質**：Y40 揭露的 silent bug 修復 sprint — Sprint K 寫的 `onPreviewVariablesClick` 用 `this.editor.command.search()` API、find/replace Y4+ 已 migrate 到 `executeSearch`、Sprint K 沒一起改、預覽變數效果徹底壞 30+ sprint。Y41 probe canvas-editor `CommandAdapt.d.ts` 確認 `executeSearch` 是 public wrapper 且 `ISearchOption.isRegEnable: boolean` 仍支援、改 2 處 `command.search` → `command.executeSearch`、feature 重生。Y40.1 spec 同時 success path 啟用 toggle/cycle 完整 assertion + strict-mode 多 notification 用 `.first()` / 「已清除」前綴防撞。
**範圍**：`doc_editor.js`（2 處 search→executeSearch + 共 ~10 行註解）、`admin-dobtor-doc-editor-sprint-y40-tools-preview-vars.spec.ts`（3 處 selector 強化）、新建 sprint doc。

---

## 1. 為什麼開這個

Y40 sprint doc Y41 候選第一條：「`onPreviewVariablesClick` source fix」。Y41 兌現。

Y40 spec defensive 抓到「預覽失敗：this.editor.command.search is not a function」。Y41 開工先 probe lib：

```bash
grep "executeSearch\|search\b" .../canvas-editor/.../Command.d.ts
# → executeSearch: CommandAdapt['search'];

grep "ISearchOption" .../canvas-editor/.../Search.d.ts
# → isRegEnable?: boolean;
```

確認：
- `executeSearch` 是 public wrapper、`search` 是 internal method（v0.9.x 後不再 expose）
- `ISearchOption.isRegEnable: boolean` 仍支援 regex pattern

Fix = 2 行 rename：`command.search` → `command.executeSearch`。

實測：執行 Y40.1 立刻走 success path、notification「找到 2 個變數（共 3 處）」精準命中 fixture（`{{ project.name }}` × 2 + `{{ doc.id }}` × 1）= Y34 教訓「assert 期待值不是 lib 回值」第二次確認。

但 success path 啟用 toggle/cycle 全段後撞 strict mode：
- step 6 `:has-text("清除")` 同時匹配 「再按一次清除高亮」(success) + 「已清除變數高亮」(clear) → 改用「已清除」前綴
- step 7 cycle `:has-text("找到")` 同時匹配首點 notification（5s 未 fade）+ cycle 新 notification → `.first()`
- step 3 dual-path `.first()` 防同樣問題

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onPreviewVariablesClick` clear path | `command.search(null)` → `command.executeSearch(null)` |
| `onPreviewVariablesClick` highlight path | `command.search("regex", { isRegEnable: true })` → `command.executeSearch(...)` |
| Y40.1 step 3 selector | dual-path 加 `.first()` 防多 notification strict mode |
| Y40.1 step 6 selector | `:has-text("清除")` → `:has-text("已清除")` 避免撞 success notification 結尾「再按一次清除高亮」 |
| Y40.1 step 7 selector | cycle 「找到」selector 加 `.first()` 防首點 + cycle 點同時 visible |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼 fix 只 rename 不改 regex 寫法

`ISearchOption.isRegEnable: boolean` 在 declaration 仍存在、Y41 probe 確認 lib 仍接受。**原 Sprint K 寫的 regex pattern + isRegEnable 是對的、只是 API entrypoint 名稱錯**。

替代方案考慮過 + 拒絕：
- flatten + 多次 indexOf：失去 lib 內建 highlight、需手動畫線 + 散管理 cursor、複雜
- 只 highlight `{{` 字面：用 `executeSearch("{{")` 不傳 isRegEnable、簡化但變數結尾 `}}` 不在高亮中、視覺差

minimal viable fix 2 行 rename 即可、不擴大 scope。

### 3.2 為什麼 Y41 spec selector tighten 跟 Y41 source fix 同 PR

Y40 spec 是 defensive dual-path、走 danger 時 conditional 跳過 toggle/cycle assertion。Y41 fix 後走 success path、conditional 啟用、立刻撞 strict mode = Y40 寫法在 success 狀態下未經實測。

source fix + spec selector 強化是「同個 feature 從 broken → working」transition 的兩面、同 PR 合理。Y32 教訓「scope 緊一致」+ Y36 教訓「state machine cycle 完整」延伸 = **修了 source 後新 path 上的 spec 需求一併滿足**。

### 3.3 為什麼用「已清除」前綴不用更精準的 regex

兩個選擇：
- 文字前綴：`:has-text("已清除")` 鎖開頭、success notification 結尾「再按一次清除高亮」不命中
- regex：`text=/^已清除/` 嚴格錨頭

文字前綴 + `:has-text` 是 Playwright recommended pattern、可讀性比 regex 高、且 effect 同。Y36 教訓「selector 選 semantic > visual」延伸 = 選最 readable 的 selector。

### 3.4 為什麼用 `.first()` 不去重 notification

兩個選擇：
- `.first()`：multiple match 取首個、簡單
- 等首 notification fade 再點 cycle：複雜、依賴 fade timing

`.first()` 是 silent assumption「多個 notification 中第一個就是 cycle 新顯示的（O18 notification 往新疊）」。實測 verify OK。Playwright `.first()` 是 race condition 處理的 idiomatic 寫法。

### 3.5 為什麼 fix 加長註解標 Y40 / Y41

source 加 5 行註解 + 1 行 inline 引用 Y40 / Y41 = future code reader 知道：
- 此 method 從 Sprint K 起活、Y40 揭露壞掉、Y41 修
- 為什麼用 `executeSearch` 不 `search`（不要被「兩 lib API 都存在」誤導 → 後者 internal）
- 跟 find/replace path 一致（建立 cross-method invariant）

註解 cost 5 行、value 後續 sprint 不再迷路。Y3 教訓「為什麼選擇此設計要在 source 註解標」延伸。

### 3.6 為什麼不順手 sweep 整 codebase `command.search`

grep 全 codebase 只 onPreviewVariablesClick 兩處用 `command.search`、其他都用 `executeSearch`。Sprint K 是孤狼、沒其他 caller。**單 method sweep 已 enough、不擴大到全代碼庫**。

Y29 教訓「3 個 caller 還太早抽 utility」延伸 = 「1 個壞 caller 修完即停、不為了一致性掃整 codebase」。但 sprint doc 寫入「lib API migration 須整個 codebase sweep」教訓、下次 lib upgrade 時 lookup。

---

## 4. 預期 + 實測

**預期**：fix 後 Y40.1 走 success path、notification「找到 N 個變數」精準命中 + toggle「已清除」+ cycle 第 3 點再「找到」全綠。

**實測**：
- Y40.1 修 selector + source fix 後：1/1 pass (23.7s) ✓
- notification 內容驗證：「找到 **2** 個變數（共 **3** 處）已高亮。再按一次清除高亮。」精準命中 fixture
- 13-spec 連跑：13/13 pass 4.7m all green ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | 2 處 `command.search` → `command.executeSearch` + ~10 行註解 |
| `admin-dobtor-doc-editor-sprint-y40-tools-preview-vars.spec.ts` | 3 處 selector 強化（top-level repo） |
| `phase8_sprint_y41_2026-05-28.md` | 新檔 |

---

## 6. 教訓

1. **Y40 defensive spec 即是 contract、Y41 fix 自動啟用全段**：Y40 寫的 `if (toastHighlight.includes('找到'))` conditional 在 broken 狀態跳過 toggle/cycle、修好後自動 enter、無需改 spec 結構。**defensive spec 是 forward compatible 的 silent bug contract**、Y40 教訓「defensive spec 把 silent bug 變成 documented warn」具體兌現 = future-proof。
2. **lib API rename 的代價：minimal fix vs sweep**：Sprint K 留下 2 處 `command.search`、Y4+ migrate 到 `executeSearch` 沒 sweep、Y40 expose、Y41 修。**lib API rename 是高風險 silent bug source、`grep <api-name>` 全 codebase 應該是 lib upgrade 的 default sweep**。但已壞了 30+ sprint 也就再忍 1 sprint、現在修一個 caller 即可、不需要為了「萬一未來再有 lib rename」過度設計 sweep workflow。
3. **strict mode violation 是 spec maturity 訊號**：Y40 寫 spec 時 source broken、only danger path notification 出現、無 strict mode 風險；Y41 fix 後 success notification 多了、撞 strict mode = spec coverage 進化的「正向警告」。spec writer 寫時看不到 happy path、修好後撞 strict mode 是 dual-state expected churn。**接受 1-2 round selector tightening 是 normal、不是 spec 寫不好**。
4. **小 fix 大影響**：Y41 改 2 行 source、修復一個 30+ sprint 壞掉的 feature。**bug 影響時間長 ≠ fix 複雜度高**；很多 silent bug 是「1 個字 typo / 1 個 API rename 沒同步」、修起來 trivial、只差「有人 click 一遍」探針去發現。Y40 spec coverage 的價值 = 把這個探針常態化。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y40 | ✅ |
| **Y41 — 預覽變數效果 source fix + Y40.1 success path 啟用** | ✅（13/13 sprint specs 全綠 4.7m、預覽變數效果 30+ sprint 後復活）|

### Sprint Y42 候選

- 預覽模式 bound path spec（Y39 候選保留、需 doc 綁 model_id + res_id）
- 「列印」menu item spec
- 「匯入 DOCX」/「匯出 PDF」/「匯出 DOCX」menu item spec
- 「儲存」menu item + Ctrl+S spec
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

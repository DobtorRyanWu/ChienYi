# Phase 8 Sprint Y10 — Find/replace match count display（Google Docs 風「3 / 12」）（2026-05-26）

**性質**：純 UI 補丁 — 在 Sprint Y4 find panel 加 match count 顯示，補完 Google Docs 風尋找體驗。零既有 method 改動、零 E2E 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~25 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~10 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~17 行）。

---

## 1. 目標

Sprint Y4 完成 find/replace panel + Ctrl+F/H 快捷鍵，但缺 Google Docs 標準的「current / total」match count 顯示 — user 不知總共幾個 match、目前在第幾個。本 sprint 用 canvas-editor 內建 `getSearchNavigateInfo()` 補上。

決策：
- **接 canvas-editor `getSearchNavigateInfo()`**：probe 後確認 return `{ index, count }`、零自寫計數邏輯
- **`index + 1 / count`**：1-based 顯示符合 user 直覺（canvas-editor 內部 0-based）
- **無 match 警示**：「無結果」+ Google red 紅色文字（dark mode 對應淡紅）
- **空查詢隱藏**：`t-if="state.findText"` 整個 span 不渲染、不佔位

---

## 2. 結構

```
.doc-find-replace-panel
  .doc-find-row
    <input.doc-find-input/>
    <span.doc-find-count t-if="findText"/> ★ Sprint Y10
      "3 / 12" 或 "無結果"
    <button.doc-find-btn (prev)/>
    <button.doc-find-btn (next)/>
    <button.doc-find-btn (close)/>
```

---

## 3. 觸發點 — 6 處 call `_updateMatchInfo()`

`getSearchNavigateInfo()` 是 canvas-editor 即時 query API、無 listener event。所以每次「search/navigate 後可能影響 match count」的操作之後手動 call helper 同步 state：

| 操作 | 為什麼要 update |
|---|---|
| `openFindReplace()`（有 findText） | 重開 panel 還原 highlight、要刷 count |
| `closeFindReplace()` | 清高亮、count 歸 0 |
| `onFindTextInput()` | 輸入即時 search、count 隨字串變 |
| `onFindNext()` | navigate 後 index 變、count 不變但要刷 index 顯示 |
| `onFindPrev()` | 同上 |
| `onReplaceOnce()` | 取代後當前 match 消失、count - 1 + 自動跳下一 |
| `onReplaceAll()` | 全部取代後手動歸 0（cmd 已 clear highlight） |

---

## 4. 實作

### 4.1 _updateMatchInfo helper

```js
_updateMatchInfo() {
    try {
        const info = this.editor?.command?.getSearchNavigateInfo?.();
        const count = info?.count ?? 0;
        const idx = info?.index ?? -1;
        this.state.findMatchCount = count;
        this.state.findMatchIndex = (count > 0 && idx >= 0) ? (idx + 1) : 0;
    } catch (e) {
        this.state.findMatchCount = 0;
        this.state.findMatchIndex = 0;
    }
}
```

- canvas-editor 0-based index → UI 1-based
- count = 0 時 index 也設 0（display 用 0 表示「無 match」狀態）
- try/catch 兜底 — getSearchNavigateInfo 在 cmd 未 init 時可能 throw

### 4.2 XML display

```xml
<span class="doc-find-count"
      t-if="state.findText"
      t-att-class="{ 'no-match': state.findMatchCount === 0 }"
      aria-live="polite">
    <t t-if="state.findMatchCount > 0">
        <t t-esc="state.findMatchIndex"/> / <t t-esc="state.findMatchCount"/>
    </t>
    <t t-else="">無結果</t>
</span>
```

- `t-if="state.findText"` 空查詢時整段不渲染（也包括 reserved 空間 — flex layout 自動 reflow）
- `aria-live="polite"` 讓螢幕閱讀器朗讀變動的 count
- 有 match 顯「N / M」、無 match 顯「無結果」+ `no-match` class（紅色警示）

### 4.3 CSS — Y10 + dark mode 對應

```css
.doc-find-count {
    flex: 0 0 auto;
    padding: 0 8px;
    font-size: 12px;
    color: var(--gd-text-muted);
    font-variant-numeric: tabular-nums;   /* 等寬數字、index 變動不抖 */
    min-width: 56px;
    text-align: center;
}
.doc-find-count.no-match {
    color: #d93025;          /* Google red 600 */
}
.is-dark-mode .doc-find-count.no-match {
    color: #f28b82;          /* Google red dark 變體 */
}
```

`font-variant-numeric: tabular-nums` 讓「1 / 4」「2 / 4」⋯index 切換時數字寬度一致、layout 不抖。

---

## 5. 驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| Ctrl+F + 輸入「估」 | 顯「1 / 4」、無 no-match class | ✓ |
| 點下一個（↓） | 顯「2 / 4」 | ✓ |
| 改搜尋「不存在的字串zzz」 | 顯「無結果」、加 no-match class | ✓ |
| 清空 findText | span 整段隱藏（t-if false） | ✓ |

### E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.3m)
```

### vitest

```
Test Files  136 passed | 1 skipped (137)
Tests       2017 passed | 1 skipped (2018)
```

無回歸。

---

## 6. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +25 行：state 2 鍵（findMatchCount/Index）+ _updateMatchInfo helper + 6 處 call site（openFindReplace、closeFindReplace、onFindTextInput、onFindNext、onFindPrev、onReplaceOnce、onReplaceAll 末段）|
| `doc_editor.xml` | +10 行：find-row 內加 `<span class="doc-find-count">` 含 t-if/t-att-class/aria-live 邏輯 |
| `doc_editor.css` | +17 行：`.doc-find-count` + `.no-match` + dark mode 變體 |

零既有 method 改動、零既有 XML 重排、零既有 selector 影響。

---

## 7. 教訓

1. **canvas-editor 無 search-event listener、要手動 call query API**：`rangeStyleChange` 是 listener、但 search 變動沒對應 event。最直接方法 = 每個 search/navigate 操作末段 call `_updateMatchInfo()`，6 處 call site 整齊。
2. **`getSearchNavigateInfo()` API 形狀只能 probe**：canvas-editor lib 是 minified、看不到 type def。先 mcp playwright 跑 `editor.command.executeSearch('xx'); editor.command.getSearchNavigateInfo()` 確認回傳 `{index, count}` 才動手寫。
3. **`font-variant-numeric: tabular-nums` 是 layout 防抖小細節**：「1 / 4」→「12 / 24」時數字寬度不同會讓周圍按鈕跳。tabular-nums 讓所有數字等寬、count 變動 layout 紋風不動。Google Docs / Apple 全用這招。
4. **OWL `t-if="state.xxx"` 配 flex layout 自動 reflow**：不用寫 visibility:hidden 假隱藏、直接 t-if 整段 unrender 是最乾淨的 conditional UI。配 flex 容器自動 reflow、其他元素填補空位。

---

## 8. 進度

| Sprint | 狀態 |
|---|---|
| G-Y9 | ✅ |
| **Y10 — find/replace match count display** | ✅ |

### Sprint Y11 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯示 'Mixed'）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- 24 色 palette dropdown
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內）
- auto/light/dark 三段 toggle
- Dark mode 跟 OS prefers-color-scheme 自動同步

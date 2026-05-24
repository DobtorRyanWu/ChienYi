# Phase 8 Sprint P — Inspector 列表鍵盤導航（↑/↓/Enter/Esc）（2026-05-24）

**性質**：Sprint L 已知限制 §6 第 1 點補完。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js) 加 `onFieldListKeyDown`，[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml) 在 ul 加 keydown + tabindex，CSS 加 `is-focused`。

---

## 1. 痛點

Sprint L 把欄位列表加上去後，user 可以用滑鼠點 row 跳到 control。但：
- 大文件 30+ 欄位、滑鼠拖捲軸 + 點到目標較慢
- 鍵盤使用者（含 accessibility）完全沒導航入口

Sprint P 加標準 list keyboard pattern。

---

## 2. 程式碼變動

### 2.1 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

#### state 加 `focusedListIndex`

```js
focusedListIndex: -1,
// -1 = 沒焦點；0..length-1 = 對應 filteredFieldsList row
```

**focused 與 selected 分離**：
- `focusedListIndex` = 鍵盤標記（藍框、不觸發 locate）
- `selectedFieldId` = 真正選取（紫底、locate + 屬性編輯）

按 Enter 才把 focused 轉為 selected。這是 ARIA listbox 標準模式。

#### `onFieldListKeyDown(ev)` handler

| Key | 行為 |
|---|---|
| `ArrowDown` | focusedListIndex + 1，clamp 到 length-1 |
| `ArrowUp` | focusedListIndex − 1，clamp 到 0 |
| `Home` | focusedListIndex = 0 |
| `End` | focusedListIndex = length − 1 |
| `Enter` | `onFieldListRowClick(focused.id)`（select + locateControl）|
| `Escape` | focusedListIndex = -1，blur ul |

每次方向鍵更新後用 `Promise.resolve().then(() => li.scrollIntoView({ block: "nearest" }))` 確保移動的 row 進入視窗。

#### `onFieldListFilterInput` 連動

filter 變動時 reset `focusedListIndex = -1`，避免指向不存在的 row。

### 2.2 [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

```xml
<ul class="doc-inspector-fields-list-items"
    role="listbox"
    tabindex="0"
    t-on-keydown="onFieldListKeyDown"
    aria-label="欄位列表（鍵盤：↑/↓ 切換、Enter 跳到 control、Esc 取消）">
```

- `tabindex="0"` 讓 ul 可以 Tab 進來接受焦點
- `aria-label` 螢幕閱讀器提示
- 每個 li 加 `is-focused` class（`state.focusedListIndex === fl_index`）

### 2.3 [doc_editor.css](../static/src/css/doc_editor.css)

```css
.doc-inspector-fields-list-item.is-focused {
    outline: 2px solid #0284c7;  /* 藍框 */
    outline-offset: -2px;
}

.doc-inspector-fields-list-item.is-focused.is-selected {
    outline-color: #38bdf8;  /* 同時 focused + selected → 較淺藍框、保留紫底辨識 */
}

.doc-inspector-fields-list-items:focus {
    outline: 1px solid #cbd5e1;  /* ul 本身 focus 時的視覺提示，不擾人 */
    outline-offset: 2px;
}
```

---

## 3. 使用流程

### 情境：純鍵盤導覽

1. Tab 到 inspector 列表 → ul 接受焦點，顯示淡邊框
2. ↓ → 第一個 row 加藍框（focused）
3. ↓↓↓ → 滾到第 4 個 row、藍框跟著移動
4. Enter → 第 4 個 row 變紫底（selected）+ 文件捲到對應 control + 屬性區顯示
5. ↓↓ Enter → 下一個 row select + jump
6. Esc → 焦點清除，藍框消失

### 情境：filter + keyboard

1. 點 filter input、輸入 `partner`
2. 列表縮到 3 row
3. ↓ Enter → 第一個過濾結果 select
4. 清掉 filter → 列表恢復完整，focused 自動 reset 為 -1

### 情境：scrollIntoView

1. 列表 30+ 個 row，max-height 240px 內滾
2. 連續按 ↓ → 每次新 focused row 自動進入視窗
3. block: "nearest" → 不會過度滾動（focused 在視窗內時不動）

---

## 4. 驗證

### L1 manifest hygiene

3 tests 全綠（Sprint P 不動 scanner、純 UI）。

### L0 模組升級

```
Registry loaded in 9.321s
```

0 dobtor 相關 ERROR。

### L1.5 靜態檢查

```
$ node --check doc_editor.js → OK
$ xmllint --noout doc_editor.xml → well-formed
```

### Bundle 驗證

```
$ curl bundle | grep -c "onFieldListKeyDown|focusedListIndex|fieldListFilter|..."
25
```

N/O/P 三 sprint 的新 symbol 都在 bundled assets 內。

---

## 5. 設計取捨

### 5.1 為什麼 focused / selected 分離？

讓鍵盤使用者「移動 cursor 不立即觸發跳轉」—— 想看哪個再按 Enter。如果合一，每按 ↓ 都會 locateControl + 文件跳動，視覺干擾大。

### 5.2 為什麼不做 type-to-search？

filter input 已 cover「打字找」的需求（Sprint O）。在 ul 上加 type-to-search 會與 filter input 重疊、user 困惑。標準 listbox pattern 也是 filter 與導覽分離。

### 5.3 為什麼 `scrollIntoView({ block: "nearest" })` 而非 `"center"`？

`"nearest"` 不會過度滾動 —— 目標在視窗內時不動。`"center"` 每次 ↓ 都把目標滾到中間，視覺跳動劇烈。

### 5.4 為什麼用 outline 而非 border？

outline 不占空間，不會把 row 內容擠歪（border 會把 width 算進去）。selected 用 background-color、focused 用 outline，兩個視覺層獨立。

---

## 6. 已知限制與後續

- **Tab 進去後第一次 ↓ 從 index 0 起**：標準 listbox 模式。若想 user 第一次 ↓ 從目前 selectedFieldId 對應的 row 起，要加邏輯（暫未做）
- **PageUp / PageDown 未實作**：240px max-height 內 list 通常一頁看得完、value 不大
- **Tab 順序**：ul 是 `tabindex="0"`、加進 Tab 順序；可能與其他輸入框順序不直觀，但 Tab 從 inspector 上方 input（filter / cleanup orphan button）下來剛好

---

## 7. 進度更新

| Sprint | 狀態 |
|---|---|
| G 掃描 → 建 record | ✅ |
| H 掃描 → 替換為 control（main 流） | ✅ |
| I manifest hygiene | ✅ |
| J 掃描 → 替換為 control（main + table） | ✅ |
| K 預覽變數 toggle | ✅ |
| L Inspector 欄位列表 + click-to-locate | ✅ |
| M 孤兒 record 標示 + 清理 | ✅ |
| N 復原最近一次掃描並替換 | ✅ |
| O Inspector 列表 search filter | ✅ |
| **P Inspector 列表鍵盤導航** | ✅ |

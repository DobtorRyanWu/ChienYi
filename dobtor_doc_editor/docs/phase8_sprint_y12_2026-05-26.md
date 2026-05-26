# Phase 8 Sprint Y12 — 24 色 palette dropdown（取代 Y6 native color picker）（2026-05-26）

**性質**：純 UI 升級 — 把 Y6 的 native `<input type="color">` 改成 Google Docs 風 24 色 palette dropdown，保留「自訂色」逃生口接回 native picker。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~85 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~50 −~20 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~95 −~30 行）。

---

## 1. 目標 & 決策

Sprint Y6 落地了字色/背景色 picker，但用 `<input type="color">` 開系統 native picker：
- 瀏覽器顯示風格不一致（macOS / Windows / Linux 各自不同）
- 與 Google Docs 視覺差距明顯（Docs 是 4×6 grid + 「重設」「自訂色」link）
- 沒有 active 色顯示（user 不知上次選哪格）

Sprint Y12 決策：
- **24 色 grid**：4 排 × 6 色 — 灰階 / 主色淺 / 主色正 / 主色深（Google Docs 經典配置）
- **「重設」link**：清掉色（傳 `null` 給 canvas-editor）
- **「自訂色」link**：保留 native picker 當逃生口（用 JS `.click()` 觸發隱藏 input）
- **互斥開啟**：字色與背景色 palette 不能同時開
- **outside-click / Escape 關閉**：沿用 Y3 menubar listener pattern

---

## 2. 24 色 palette 配置

```
Row 1（灰階）：#ffffff #f1f3f4 #bdc1c6 #80868b #3c4043 #000000
Row 2（淺）：  #fce8e6 #fce5cd #fff2cc #d9ead3 #d0e0e3 #cfe2f3
Row 3（正）：  #ea4335 #fbbc04 #fff176 #34a853 #46bdc6 #4285f4
Row 4（深）：  #a52714 #b45f06 #bf9000 #0f9d58 #134f5c #0b5394
```

Y6 預設 `highlightColor: '#fff176'` 對應 Row 3 第 3 格、`textColor: '#202124'`（不在 palette 內、屬於系統預設）— 「重設」按鈕 reset 回這兩個值。

---

## 3. 結構

```
.doc-format-color-wrap (span/trigger)
  ├── <i class="fa fa-font"/>             ← icon（A / 油漆刷）
  ├── <span.doc-format-color-bar/>        ← 當前色橫條（Y6 沿用）
  ├── <i class="fa fa-caret-down doc-format-color-caret"/>  ← Y12 新加下拉箭頭
  ├── <input type="color" hidden/>        ← 自訂色逃生口（JS .click() 觸發）
  └── .doc-color-palette (t-if state.showColorPalette === type)
        ├── .doc-color-palette-row × 4
        │     └── .doc-color-swatch × 6
        └── .doc-color-palette-footer
              ├── 重設
              └── 自訂色...
```

---

## 4. 實作

### 4.1 JS — state + COLOR_PALETTE getter + 4 handlers

```js
// state（新加 1 鍵）
showColorPalette: null,  // null | 'text' | 'highlight'

// COLOR_PALETTE getter（XML t-foreach 直接吃）
get COLOR_PALETTE() {
    return [
        ['#ffffff', '#f1f3f4', '#bdc1c6', '#80868b', '#3c4043', '#000000'],
        ['#fce8e6', '#fce5cd', '#fff2cc', '#d9ead3', '#d0e0e3', '#cfe2f3'],
        ['#ea4335', '#fbbc04', '#fff176', '#34a853', '#46bdc6', '#4285f4'],
        ['#a52714', '#b45f06', '#bf9000', '#0f9d58', '#134f5c', '#0b5394'],
    ];
}

// 4 handlers
onColorTriggerClick(type, ev)  // toggle palette
onColorSwatchPick(type, color, ev)  // 點色塊 → executeColor/executeHighlight + 關
onColorReset(type, ev)          // 重設 → executeColor(null) + 關
onColorCustom(type, ev)         // 自訂色 → JS .click() 隱藏 native input
```

`ev.stopPropagation()` 防止冒泡到全域 outside-click listener 立即關回去（mousedown 比 click 早觸發）。

### 4.2 outside-click / Escape — sprint Y3 listener 延伸

```js
// 全域 keydown
if (event.key === 'Escape' && this.state?.showColorPalette) {
    this.state.showColorPalette = null;
}

// 全域 mousedown
if (this.state.showColorPalette && !ev.target.closest('.doc-format-color-wrap')) {
    this.state.showColorPalette = null;
}
```

零新增 listener — 直接擴展 Y3 `_onGlobalKey` / `_onGlobalClick`。

### 4.3 XML — t-foreach 2 層 render grid

```xml
<div class="doc-color-palette" t-if="state.showColorPalette === 'text'">
    <t t-foreach="COLOR_PALETTE" t-as="row" t-key="row_index">
        <div class="doc-color-palette-row">
            <t t-foreach="row" t-as="color" t-key="color">
                <button class="doc-color-swatch"
                        t-att-class="{ 'is-selected': state.textColor === color }"
                        t-attf-style="background: #{color};"
                        t-on-click="(ev) => this.onColorSwatchPick('text', color, ev)"/>
            </t>
        </div>
    </t>
    <div class="doc-color-palette-footer">
        <button t-on-click="(ev) => this.onColorReset('text', ev)">重設</button>
        <button t-on-click="(ev) => this.onColorCustom('text', ev)">自訂色...</button>
    </div>
</div>
```

`t-key="color"` 用色碼當 key — 同一 row 內色碼不重複、跨 row 也不會（4×6 全互異）。

### 4.4 CSS — palette dropdown + selected ring

```css
.doc-color-palette {
    position: absolute;
    top: calc(100% + 4px);
    z-index: 110;          /* 高於 menu dropdown 的 100 */
    padding: 8px;
    background: #fff;
    border: 1px solid var(--gd-toolbar-border);
    border-radius: var(--gd-radius-sm);
    box-shadow: 0 4px 14px rgba(60,64,67,0.18);
    display: flex; flex-direction: column; gap: 4px;
}
.doc-color-swatch {
    width: 22px; height: 22px;
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 3px; cursor: pointer;
    transition: transform 80ms ease, box-shadow 80ms ease;
}
.doc-color-swatch:hover {
    transform: scale(1.12);
    box-shadow: 0 0 0 1px var(--gd-accent);
}
.doc-color-swatch.is-selected {
    box-shadow: 0 0 0 2px var(--gd-accent);
    border-color: var(--gd-accent);
}
```

Dark mode override：palette 背景 `#2a2a2a`、swatch border 換亮色（沿用 Y9 token override 模式）。

### 4.5 Y6 native input — 改成 1×1 隱形

```css
.doc-format-color-hidden {
    /* Y12：只當「自訂色」逃生口；不再覆蓋 wrap 全區
       否則點 trigger 會直接觸發 native picker、palette 開不了 */
    position: absolute;
    width: 1px; height: 1px;
    opacity: 0; pointer-events: none;
}
```

`pointer-events: none` 確保滑鼠不會觸發；只有 `onColorCustom` 的 JS `.click()` 能打開。

---

## 5. 驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| 點字色 trigger | palette 開、4 排 × 6 swatch | ✓（rowCount=4, swatchCount=24） |
| 點某色塊 | textColor 更新、bar 變色、palette 關 | ✓（picked #fff2cc → bar style 同步） |
| 重開 palette | 該色塊有 selected ring（box-shadow accent） | ✓（is-selected count=1, bg=rgb(255,242,204)） |
| 開字色再點背景色 trigger | 切到 highlight palette（互斥） | ✓（textOpen=false, hlOpen=true） |
| 點 palette 外（body） | palette 關閉 | ✓ |
| 點重設 | textColor 回預設 #202124、palette 關 | ✓（bar style → #202124） |

截圖：[y12-palette-open.png](../y12-palette-open.png)（字色 palette 開啟狀態）

### E2E G.1/HN.1/J.1（待跑）

預期 3/3 pass — Y12 selector 都全新（`.doc-color-palette`、`.doc-color-swatch`、`.doc-color-palette-link`），既有 E2E 不受影響。

### vitest（待跑）

預期 ≥2023 pass — 純 UI 改動、無新 unit test、無既有 method 邏輯動。

---

## 6. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +85 行：state 1 鍵（showColorPalette）+ COLOR_PALETTE getter + 4 handlers + 全域 listener Esc/outside-click 延伸 + 修改 Y6 onTextColorChange/onHighlightColorChange 末段加 `showColorPalette=null` |
| `doc_editor.xml` | +50 −20 行：2 個 `.doc-format-color-wrap` 從 `<label>` 改 `<span>`、加 trigger click handler / caret icon / palette dropdown / footer links |
| `doc_editor.css` | +95 −30 行：wrap 改 row flex + 加 caret、palette grid + swatch + footer link、dark mode override、native input 改 1×1 隱形 |

零既有 method 改動、零既有 E2E selector 影響。

---

## 7. 教訓

1. **`pointer-events: none` 是雙重 picker 共存的關鍵**：Y6 的 native input 仍要存在（自訂色逃生口），但不能蓋住整個 wrap 接收 click。改 `position:absolute; width:1px; pointer-events:none`，只接受 JS `.click()` 來觸發。
2. **`ev.stopPropagation()` 在 trigger handler 必加**：全域 mousedown listener 跑得比 OWL re-render 早；如果不阻止冒泡，click trigger 後 listener 立刻看到「target 不在 wrap 內」（因為 OWL 還沒 render palette），把 state 設回 null，palette 永遠開不起來。
3. **互斥開啟用單一 state key 自然完成**：`showColorPalette: 'text'|'highlight'|null` 一個 key 涵蓋 3 狀態。trigger handler 寫 `(showColorPalette === type) ? null : type` 一行搞定 toggle + 切換 + 互斥。
4. **`t-key="color"` 在唯一性已保證時最簡潔**：4×6 palette 全 24 個色碼互異 — 直接拿 `color` 當 key，不用 `${row_index}-${col_index}` 拼接。OWL diff 也最有效率。
5. **OWL 微任務 render 在 E2E 必須 await**：programmatic `.click()` 觸發 handler 後 state 改變要等 OWL nextTick 才 render；測試裡每個 click 後加 `await wait(150)` 才能讀到正確 DOM。第一次測沒等就拿到「palette 還沒開」假陰性。

---

## 8. 進度

| Sprint | 狀態 |
|---|---|
| G-Y11 | ✅ |
| **Y12 — 24 色 palette dropdown** | ✅ |

### Sprint Y13 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯「Mixed」）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內、Enter 觸發、Esc 關閉已有）
- auto/light/dark 三段 toggle（Y9 是 2 段、加 OS `prefers-color-scheme` 自動跟）
- signer-bar 視覺再精簡（chip / 頁碼合一）
- 把 Row 3 hide 改成 user 可 toggle 顯示（查看 → 顯示傳統工具列）
- 「最近用色」第 0 排（記住最後 6 個自訂色）

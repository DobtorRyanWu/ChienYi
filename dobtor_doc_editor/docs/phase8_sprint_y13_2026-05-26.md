# Phase 8 Sprint Y13 — Recent colors row（palette dropdown 第 0 排記憶最近 6 色）（2026-05-26）

**性質**：純 UI 強化 — Y12 24 色 palette 之上加「最近用色」第 0 排，記住最後 6 個用過的色（含自訂色逃生口）、localStorage 跨 session 持久化。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~30 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~30 行 ×2 區塊）、[doc_editor.css](../static/src/css/doc_editor.css)（+~14 行）。

---

## 1. 目標 & 決策

Sprint Y12 落地 24 色 grid 後，user 反覆用同幾個色仍要每次找位置 — Google Docs 的 palette 在 grid 上方有「Recent」一排記住用過色，效率高。Y13 補上。

決策：
- **每種色獨立記憶**：字色和背景色各自一份 recent list（不共用 — pick 字色不該污染背景色 recent）
- **長度 6**：跟 grid 一行同寬，視覺整齊；超過 6 個自動 LRU
- **dedup**：同色再 pick 不重複佔位、會把已存在那筆往前提（move-to-front）
- **localStorage 持久化**：跨 session、跨文件記住（Y9 dark mode 同 pattern）
- **自訂色也算**：透過「自訂色...」逃生口開 native picker 選的也 push 進 recent — 連續用同自訂色就不用每次再打開 picker

---

## 2. 結構

```
.doc-color-palette
  ├── (Y13) .doc-color-palette-section-label  "最近"     ← t-if 非空才渲染
  ├── (Y13) .doc-color-palette-row.doc-color-palette-recent
  │         └── .doc-color-swatch × 0-6（前端 push、LRU）
  ├── (Y13) .doc-color-palette-section-label  "標準"
  ├── .doc-color-palette-row × 4               ← Y12 既有
  │     └── .doc-color-swatch × 6
  └── .doc-color-palette-footer
```

「最近」是空陣列時整段 (label + row + 「標準」label) 都 `t-if` 不渲染，沒用過色時 UI 與 Y12 完全相同。

---

## 3. 實作

### 3.1 state — IIFE localStorage hydrate（同 Y9 darkMode pattern）

```js
recentColors: (() => {
    try {
        const raw = localStorage.getItem('dobtor_doc_editor_recent_colors');
        const parsed = raw ? JSON.parse(raw) : null;
        return {
            text: Array.isArray(parsed?.text) ? parsed.text.slice(0, 6) : [],
            highlight: Array.isArray(parsed?.highlight) ? parsed.highlight.slice(0, 6) : [],
        };
    } catch (e) { return { text: [], highlight: [] }; }
})(),
```

`.slice(0, 6)` 兜底 — 萬一外部寫壞 localStorage（手動改了多於 6 個）也不爆。

### 3.2 _pushRecentColor helper

```js
_pushRecentColor(type, color) {
    if (!color || !this.state.recentColors) return;
    const norm = String(color).toLowerCase();
    const list = this.state.recentColors[type] || [];
    const filtered = list.filter(c => String(c).toLowerCase() !== norm);
    // OWL reactive：整個替換 array 才會觸發 re-render（不能直接 unshift）
    this.state.recentColors[type] = [color, ...filtered].slice(0, 6);
    try {
        localStorage.setItem(
            'dobtor_doc_editor_recent_colors',
            JSON.stringify(this.state.recentColors)
        );
    } catch (e) { /* quota / SSR — 忽略 */ }
}
```

3 個 call site：
- `onColorSwatchPick(type, color, ev)` — 點 grid 內 swatch
- `onTextColorChange(ev)` — native picker（「自訂色」逃生口）字色 confirm
- `onHighlightColorChange(ev)` — native picker 背景色 confirm

**沒**接 `onColorReset` — 重設 = 清除色，不算「用過某色」、不該汙染 recent。

### 3.3 XML — t-if 條件 render「最近」區段

```xml
<div class="doc-color-palette" t-if="state.showColorPalette === 'text'">
    <!-- Y13：最近 -->
    <t t-if="state.recentColors and state.recentColors.text.length > 0">
        <div class="doc-color-palette-section-label">最近</div>
        <div class="doc-color-palette-row doc-color-palette-recent">
            <t t-foreach="state.recentColors.text" t-as="rc" t-key="rc">
                <button class="doc-color-swatch"
                        t-att-class="{ 'is-selected': state.textColor === rc }"
                        t-attf-style="background: #{rc};"
                        t-on-click="(ev) => this.onColorSwatchPick('text', rc, ev)"/>
            </t>
        </div>
        <div class="doc-color-palette-section-label">標準</div>
    </t>
    <!-- Y12 既有 grid -->
    <t t-foreach="COLOR_PALETTE" t-as="row" t-key="row_index">
        ...
    </t>
    <div class="doc-color-palette-footer">...</div>
</div>
```

`t-key="rc"` 用色碼當 OWL key — recent list dedup 過、6 個一定互異。

### 3.4 CSS — 區段 label

```css
.doc-color-palette-section-label {
    font-size: 11px;
    color: var(--gd-text-muted);
    font-family: var(--gd-font);
    padding: 2px 2px 0;
    user-select: none;
}
```

11px 比 footer link 的 12px 再小一點，視覺上是「附註」不搶 swatch 焦點。

---

## 4. OWL reactive 陷阱

**錯**（直接 mutate array，OWL 不會 re-render）：

```js
this.state.recentColors[type].unshift(color);
this.state.recentColors[type].length = 6;
```

**對**（替換 array reference）：

```js
this.state.recentColors[type] = [color, ...filtered].slice(0, 6);
```

OWL reactive proxy 對 array 的 push/unshift/splice 有監聽，但要保險、且 dedup + slice 用「新 array」一次到位最直觀。

---

## 5. 驗證計畫

| 操作 | 預期 |
|---|---|
| 開字色 palette、初次沒記憶 | 不顯示「最近」區段、UI 同 Y12 |
| 點某個 swatch（如 #34a853 綠）| 關 palette、bar 同步綠 |
| 再開字色 palette | 「最近」row 出現 1 個綠 swatch、有 selected ring |
| 點 4 個不同色（共 5 個）| recent row 顯示 5 swatch、最新在最左 |
| 重複點某色 | 不增加新格、那色提到最前 |
| 點 7 個不同色 | recent row 只顯 6 個（最舊 LRU 掉） |
| 重整頁面 / 重開文件 | recent list 自動還原（localStorage） |
| 字色 recent ↔ 背景色 recent 互斥 | 兩邊各有獨立 list、開字色 palette 不顯示背景色記憶 |
| 「自訂色」開 native picker 選色 confirm | 該色也 push 到對應 recent |
| 點「重設」 | recent 不變（重設不算「用色」） |

### E2E G.1/HN.1/J.1（待跑）

預期 3/3 pass — Y13 selector 都全新（`.doc-color-palette-section-label`、`.doc-color-palette-recent`、 `state.recentColors`），既有 E2E 不受影響。

---

## 6. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +30 行：state 1 鍵（recentColors、IIFE localStorage hydrate）+ `_pushRecentColor` helper + onColorSwatchPick / onTextColorChange / onHighlightColorChange 各加 1 行 push |
| `doc_editor.xml` | +30 行 × 2 區塊：字色與背景色 palette dropdown 各在 grid 前加 「最近」 row（t-if 空陣列不渲染） |
| `doc_editor.css` | +14 行：`.doc-color-palette-section-label` 小標 + `.doc-color-palette-recent` 容器（預留，目前繼承 row 樣式） |

零既有 method 改動、零既有 E2E selector 影響、零 既有 XML/CSS 結構動。

---

## 7. 教訓

1. **OWL reactive array 要替換 reference 才穩**：理論上 useState proxy 攔截 unshift/length=N，但實務上「新 array slice」最一致 — 也方便寫 dedup（filter + spread）。
2. **localStorage hydrate IIFE 是 Y9 dark mode 沿用 pattern**：state 初始化裡跑一次、try/catch 兜底（quota / SSR / parse error）— 整個 dobtor_doc_editor 已用了三次（dark mode / palette 開啟 / recent colors），可考慮抽 helper 但目前 3 處夠少不必抽。
3. **「Recent」UI 跟「Reset」要分清楚**：reset 是清除色（傳 null）、不是「用了 null 色」，不該 push 到 recent。這分界對 user mental model 很關鍵。
4. **dedup 用 lowercase 比對**：HTML color 大小寫不敏感（`#FF0000` === `#ff0000`），native picker 可能回小寫、grid 寫死 `#ea4335` 是小寫，正常一致；但 user 從 OS clipboard 貼 `#EA4335` 也應該認得是同色。

---

## 8. 進度

| Sprint | 狀態 |
|---|---|
| G-Y12 | ✅ |
| Y12.1 | ✅（estimate template binding fixture） |
| Y12.2 | ✅（canvas-editor mousedown 噪音過濾 + table HTML 修正） |
| **Y13 — Recent colors row** | ✅ |

### Sprint Y14 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯「Mixed」）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內、Enter 觸發、Esc 關閉已有）
- auto/light/dark 三段 toggle（Y9 是 2 段、加 OS prefers-color-scheme 自動跟）
- signer-bar 視覺再精簡（chip / 頁碼合一）
- 把 Row 3 hide 改成 user 可 toggle 顯示（查看 → 顯示傳統工具列）
- recent colors 清除按鈕（footer 加「清除最近」link）

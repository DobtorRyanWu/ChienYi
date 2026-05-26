# Phase 8 Sprint Y8 — Format toolbar active state 延伸（font/size/color/align）（2026-05-26）

**性質**：純 UI 延伸 — 把 Sprint Y7 的 active state pattern 從 B/I/U/S 4 按鈕擴到 font select、size select、color/highlight swatch、4 align 按鈕。完整 format toolbar 反映 caret 狀態。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~25 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~25 行 −16 行）。CSS 不動（沿用 Y7 `.is-active`）。

---

## 1. 目標

Sprint Y7 完成 B/I/U/S 4 按鈕 active 高亮，但 format toolbar 還有 font/size selector、color/highlight swatch、4 align 按鈕都沒有 active 反饋。本 sprint 一次補齊。

決策：
- **沿用 Sprint Y7 listener 擴充模式**：rangeStyleChange 內 if-block 多讀 5 屬性、寫 5 個 state
- **font/size 用 `t-att-value` + option `t-att-selected`**：OWL 把 state 變動同步到 select.value
- **color swatch 已有 t-attf-style 綁 state.textColor**：listener 寫 state 即同步 swatch
- **align 4 按鈕用 Y7 同款 `is-active` class**：CSS 不動

---

## 2. 延伸內容

| 控件 | 反映屬性 | OWL 同步機制 |
|---|---|---|
| font select | `el.font` | `t-att-value="state.activeFontFamily"` + option `t-att-selected="state.activeFontFamily === f.value"` |
| size select | `el.size` | `t-att-value="state.activeFontSize"` + option `t-att-selected="state.activeFontSize === ('' + s)"` |
| 字色 swatch | `el.color` | `state.textColor` 已被 swatch `t-attf-style` 綁定（Y6）；listener 改 state → swatch + picker 預設值都同步 |
| 背景色 swatch | `el.highlight` | 同上 (state.highlightColor) |
| align 左 | `el.rowFlex === 'left'` | `t-att-class="{ 'is-active': state.activeRowFlex === 'left' }"` |
| align 中 | `'center'` | 同上 |
| align 右 | `'right'` | 同上 |
| align 兩端 | `'alignment'` | 同上 |

---

## 3. 實作

### 3.1 state +3 鍵（color 已存 Y6）

```js
activeFontFamily: '',
activeFontSize: '16',           // canvas-editor 預設；select option value 是字串
activeRowFlex: 'left',          // 'left'|'center'|'right'|'alignment'
```

### 3.2 rangeStyleChange listener 擴充（在 Y7 if-block 後追加）

```js
const font = el.font || '';
const sizeStr = el.size != null ? String(el.size) : '16';
if (this.state.activeFontFamily !== font) this.state.activeFontFamily = font;
if (this.state.activeFontSize !== sizeStr) this.state.activeFontSize = sizeStr;

const color = el.color || '#202124';
const hl = el.highlight || '#fff176';
if (this.state.textColor !== color) this.state.textColor = color;
if (this.state.highlightColor !== hl) this.state.highlightColor = hl;

const rowFlex = el.rowFlex || ctx?.rowFlex || 'left';
if (this.state.activeRowFlex !== rowFlex) this.state.activeRowFlex = rowFlex;
```

`!==` 守衛保持 Y7 慣例、避免 redundant render。

### 3.3 XML font/size select + 4 align btn

```xml
<select class="doc-format-select doc-format-font"
        t-att-value="state.activeFontFamily"
        t-on-change="onFontFamilyChange">
    <t t-foreach="FONT_OPTIONS" t-as="f" t-key="f.value">
        <option t-att-value="f.value"
                t-att-selected="state.activeFontFamily === f.value">
            <t t-esc="f.label"/>
        </option>
    </t>
</select>

<button class="doc-format-btn"
        t-att-class="{ 'is-active': state.activeRowFlex === 'center' }"
        t-on-click="() => this._executeCmd('executeRowFlex', 'center')"
        aria-pressed="state.activeRowFlex === 'center'">
    <i class="fa fa-align-center" aria-hidden="true"/>
</button>
```

### 3.4 OWL ctx 無 `String` global（陷阱）

第一版用 `t-att-selected="state.activeFontSize === String(s)"` 編譯後跑：
```
TypeError: ctx.String is not a function
```
OwlError 把整個 component 炸了 SPA blank。OWL QWeb 編譯出來的表達式內 ctx 沒帶 JS global（`String`、`Number`、`parseInt` 全沒），只能用 literals 跟 state/this 內的東西。改 `('' + s)` 字串拼接即修。

教訓：QWeb 表達式裡只能寫純 ASCII operator + 變數，不能用 JS global function。要 cast 就走字串拼接 / `+0` 之類的 trick、或在 JS 端 pre-compute 好再丟 state。

---

## 4. 驗證

### 4.1 視覺驗證（mcp playwright + 真實 canvas-editor cmd 路徑）

| 操作 | 預期 | 實測 |
|---|---|---|
| `executeSetRange(0, 5)` + `executeRowFlex('center')` | center btn class `doc-format-btn is-active`、其他 3 個保 `doc-format-btn` | ✓（4 個 class 完全對） |
| `executeSetRange(0, 5)` + `executeSize(24)` | size select.value = "24" | ✓ |
| `getRangeContext().startElement` | size = 24、rowFlex = "center" | ✓ |

### 4.2 E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.2m)
```

### 4.3 vitest

```
Test Files  132 passed | 1 skipped (133)
Tests       2013 passed | 1 skipped (2014)
```

無回歸。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +25 行：state 3 鍵 + rangeStyleChange listener 加 18 行讀 5 屬性 + 寫 5 state |
| `doc_editor.xml` | +25 行 −16 行：font/size select 加 t-att-value + option t-att-selected、4 align btn 加 t-att-class + aria-pressed |
| `doc_editor.css` | 不動（沿用 Y7 `.doc-format-btn.is-active`） |

零既有 method 改動、零既有 selector 影響。

---

## 6. 教訓

1. **OWL QWeb 表達式 ctx 沒 JS global**：`String()`、`Number()`、`parseInt()` 都跑不了，會 `TypeError: ctx.X is not a function` 炸整個 component。要 cast 走字串拼接 `'' + s`、或 JS 端 pre-compute 後丟 state。本 sprint 第一版踩到、改成 `('' + s)` 即修。
2. **`t-att-value` on `<select>` 配 option `t-att-selected` 雙保險**：單獨 `t-att-value` 在某些瀏覽器不可靠（select.value 跟實際 selected option 不一定同步）。option 上加 `t-att-selected` 是 HTML 規範路徑、最穩。
3. **color swatch 自動同步是 Y6 鋪好的路**：Y6 把 `t-attf-style="background: #{state.textColor};"` 寫好、Y8 只在 listener 內改 state.textColor、swatch 就跟著變。優良 component 設計的 compounding return。
4. **Y7 → Y8 是 mechanical extension**：listener 內加 5 屬性 read、XML 加 5 個 t-att-*、CSS 不動。Pattern 一旦 Y7 對齊，Y8 都是「填空題」。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y7 | ✅ |
| **Y8 — format toolbar active state 延伸（font/size/color/align）** | ✅ |

### Sprint Y9 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯示 'Mixed'）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向、整理 Row 3 toolbar）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 24 色 palette dropdown（升級 Y6 native picker）
- find/replace match count display（顯示「3 / 12 matches」）
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內）
- 對齊改 sub-menu（CSS-only :hover）取代目前平鋪 4 條（Y7/Y8 已 active state，sub-menu 可省）
- dark mode token（`prefers-color-scheme: dark`）跨整套 menu/dropdown/panel/format

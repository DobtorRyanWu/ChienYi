# Phase 8 Sprint Y6 — 字色 / 背景色 picker（補 Sprint Y5 格式化工具列）（2026-05-26）

**性質**：純 UI 增量 — 在 Sprint Y5 Row 3.5 格式化工具列加 2 個顏色 picker（字色 / 背景色），用 `<input type="color">` 原生 picker 包 Google Docs 風 icon+swatch label。零 E2E selector 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~22 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~22 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~50 行）。

---

## 1. 目標

Sprint Y5 格式化工具列已有 B/I/U/S + align + clear，但 Google Docs 標準工具列還有「文字顏色」+「醒目提示顏色」兩個視覺顯著的控件。canvas-editor `executeColor` / `executeHighlight` 已在 Y4 探過 API、本 sprint 補上。

決策：
- **使用原生 `<input type="color">`**：跨平台、無 dependency、user 拿到 OS 預設 color picker — 比自己畫 24 色 palette dropdown 工程小 10 倍
- **Google Docs 風包裝**：`<label>` wrapper 內 icon + 下方 3px 色條 + 浮在上方的 transparent color input。點任何位置開原生 picker、色條同步當前選色
- **記住上次選色**：state.textColor / state.highlightColor，下次點不重置回預設

---

## 2. 結構

```
.doc-format-toolbar  (Sprint Y5)
  ...
  | sep
  label.doc-format-color-wrap (字色)
    i.fa.fa-font                 ← A 圖示
    span.doc-format-color-bar    ← 3px 色條，bg = state.textColor
    input.doc-format-color-hidden ← type=color，absolute inset:0、opacity:0
  label.doc-format-color-wrap (背景色)
    i.fa.fa-paint-brush          ← 油漆刷圖示
    span.doc-format-color-bar    ← bg = state.highlightColor
    input.doc-format-color-hidden ← type=color、handler executeHighlight
  | sep
  button.doc-format-btn (清除格式)
```

→ 視覺：28×28 button、icon 在上、色條在下，符合 Google Docs 樣式。

---

## 3. 互動

| 動作 | 行為 |
|---|---|
| 點字色 wrap 任何位置 | 透明 input 在上方接到 click → 開 OS 原生 color picker |
| 選色（picker 中 OK） | input 觸發 `input` event → `onTextColorChange(ev)` → `state.textColor = c` + `executeColor(c)` |
| state.textColor 變動 | `t-attf-style="background: #{state.textColor};"` → 色條 swatch 自動同步 |
| 再次開字色 | input value 為記住的 textColor、user 看到上次選的色為 picker 預設值 |

背景色同模式（onHighlightColorChange + executeHighlight）。

---

## 4. 關鍵實作細節

### 4.1 input 浮在上方 opacity:0（hit area trick）

```css
.doc-format-color-hidden {
    position: absolute;
    inset: 0;            /* 撐滿 wrap 28×28 */
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
}
```

label 內的 input 透明、佔滿 wrap、攔截所有 click。Browser 自動連動 label→input 的 click forwarding，但這裡更直接：input 自己接 click。icon + 色條（pointer-events 預設 auto）會被 input 蓋住、用戶看不到差別。

### 4.2 t-attf-style 同步 swatch

```xml
<span class="doc-format-color-bar"
      t-attf-style="background: #{state.textColor};"/>
```

OWL `t-attf-*` 在 attr 內插 `#{...}` 變數（非 t-att-style 整段覆蓋）。state 變動 → re-render → swatch background 跟著變。

### 4.3 顏色預設值的選擇

```js
textColor: '#202124',       // 同 --gd-text，Google Docs 預設
highlightColor: '#fff176',  // Google Docs 預設 highlight 黃
```

選跟既有 CSS token / Google Docs 一致的預設，user 第一次看 swatch 不會以為「為什麼是紅色？」。

### 4.4 為什麼不寫 24 色 palette

Google Docs 是 24 色 grid + 自訂色按鈕。要做：6 列 4 欄 grid + 24 button + open custom color modal + state.activeColor highlight。工程量 5-10×。原生 picker 給用戶完整 16M 色選擇 + 不限平台、本 sprint 80/20 原則用之。

---

## 5. 驗證

### 5.1 視覺驗證（mcp playwright）

| 項 | 預期 | 實測 |
|---|---|---|
| color-wrap 2 個 | 字色 + 背景色 | ✓（2） |
| 28×28 | 與 format-btn 一致 | ✓（28×28） |
| hidden input type=color × 2 | 原生 picker 可開 | ✓ |
| 預設值 | textColor=#202124、highlightColor=#fff176 | ✓ |
| swatch 同步 state | 改 input → bar style.background 跟變 | ✓（改字色為 #e53935 紅 → bar="rgb(229,57,53)"、背景色不動） |
| canvas-editor cmd | executeColor / executeHighlight 均為 function | ✓ |

### 5.2 E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.1m)
```

零 selector 影響（新 class 全為 `.doc-format-color-*`）。

### 5.3 vitest

第一輪：1 fail（`sprint233_num_diff_inspect.test.ts` — autopilot 並行 add/remove 該檔的 race flake、檔已不存在）。
第二輪 clean：

```
Test Files  126 passed | 1 skipped (127)
Tests       2007 passed | 1 skipped (2008)
```

---

## 6. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +22 行：state 2 鍵（textColor / highlightColor）、2 handler（onTextColorChange / onHighlightColorChange）|
| `doc_editor.xml` | +22 行：2 `<label class="doc-format-color-wrap">` 各含 icon + bar + hidden input、插在「清除格式」前 |
| `doc_editor.css` | +50 行：`.doc-format-color-wrap` + `.doc-format-color-bar` + `.doc-format-color-hidden` 樣式 |

零既有 method 改動、零既有 XML 重排、零既有 selector 影響。

---

## 7. 教訓

1. **原生 `<input type="color">` 是低工程量的 80/20 解**：替代自寫 palette dropdown，跨平台、無 dep、user 拿 OS picker（最熟悉）。色條 swatch 用 `t-attf-style` 同步 state.color 就有 Google Docs 視覺。
2. **opacity:0 + absolute inset:0 是 input hit-area 經典作法**：input 浮在上方接 click、UI 顯示用 icon+bar，視覺與互動解耦。
3. **vitest 並行 race flake 在 autopilot 環境是日常**：autopilot 一直 add/remove sprint files、vitest discover 跑時若該檔正好被刪會 fail。處理：再跑一次 clean → 真實 baseline；不要在 Y2/Y3/Y4 之上 add flake-detection 工程。
4. **`t-attf-style` vs `t-att-style`**：本 sprint 用 `t-attf-style="background: #{xxx};"` 在 attr 內插值。記得 Sprint Y2 寫 ruler 也是 `t-att-style` 整段，差別在「整段覆蓋（t-att）vs 文字插值（t-attf）」。

---

## 8. 進度

| Sprint | 狀態 |
|---|---|
| G-Y5 | ✅ |
| **Y6 — 字色 / 背景色 picker** | ✅ |

### Sprint Y7 候選

- 段落格式 modal（行距 / 段距 / 縮排）
- format toolbar active state（粗體在 selection 為粗體時按鈕高亮）— 需 contentChange listener tracking
- 文件設定 modal（紙張 / margin / 方向，取代既有 Row 3 toolbar）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 24 色 palette dropdown（取代 input type=color，更像 Google Docs）
- find/replace match count display（顯示「3 / 12 matches」）
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內）
- 對齊改 sub-menu（CSS-only :hover）取代目前平鋪 4 條
- dark mode token（`prefers-color-scheme: dark`）跨整套 menu/dropdown/panel/format

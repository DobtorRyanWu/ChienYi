# Phase 8 Sprint Y9 — Dark mode toggle（UI shell 深色 + canvas 紙張保白）（2026-05-26）

**性質**：純 CSS 變數 override + 1 state + 1 menu item。零既有 method 改動、零 E2E selector 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~15 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+1 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~70 行）。

---

## 1. 目標

Google Docs 有 dark mode、user 在 Y7-Y8 已要求視覺改造完整化。本 sprint 補上深色 UI shell，使用者可在 menubar「查看 → 深色模式」一鍵切換、localStorage 持久化。

決策：
- **僅深色化 UI shell**：menubar / toolbar / panel / dropdown / inspector / statusbar 全變深；canvas-editor 渲染的紙張 (`<canvas>`) 保持白色 — 維持「列印 WYSIWYG」（user 看到的紙張就是列印出來的樣子）
- **手動 toggle、不走 `@media (prefers-color-scheme)`**：app 內 toggle 更有控制感、避免 user OS dark 但偏好 light 文書編輯的情況
- **localStorage 持久化**：key `dobtor_doc_editor_dark_mode`、'1' = dark / '0' = light
- **複用 Y3 `--gd-*` CSS 變數**：dark 模式 override 一次、所有 UI 元素自動跟著變

---

## 2. 結構

```
查看 menu
  └ 深色模式  (✓ 前綴顯示當前狀態)
       ↓ click
state.darkMode = !state.darkMode + localStorage.setItem
       ↓ OWL re-render
<div class="o_action o_dobtor_doc_editor" t-att-class="{ 'is-dark-mode': state.darkMode }">
       ↓ CSS
.o_dobtor_doc_editor.is-dark-mode { --gd-bg / --gd-text / ... override }
  → menubar / toolbar / panel / dropdown / select / button 全部自動變深
canvas 紙張不變（canvas-editor 內部 hardcoded white、`--gd-paper-bg` 保白）
```

---

## 3. Dark token 配色（Google Material Dark 風）

| token | light | dark |
|---|---|---|
| `--gd-bg` | `#f8f9fa` | `#1f1f1f` |
| `--gd-paper-bg` | `#ffffff` | **`#ffffff`（保白！）** |
| `--gd-toolbar-bg` | `#ffffff` | `#2a2a2a` |
| `--gd-toolbar-border` | `#e5e7eb` | `#3a3a3a` |
| `--gd-text` | `#202124` | `#e8eaed` |
| `--gd-text-muted` | `#5f6368` | `#9aa0a6` |
| `--gd-accent` | `#1a73e8` | `#8ab4f8`（Google blue dark variant）|
| `--gd-accent-soft` | `#e8f0fe` | `#2d3a52` |
| `--gd-hover-bg` | `rgba(60,64,67,0.08)` | `rgba(255,255,255,0.08)` |

---

## 4. CSS 結構

```css
.o_dobtor_doc_editor.is-dark-mode {
    --gd-bg: #1f1f1f;
    --gd-toolbar-bg: #2a2a2a;
    --gd-text: #e8eaed;
    /* ... 9 個 token override */
    background: var(--gd-bg);
    color: var(--gd-text);
}

/* 浮層白底要明確 override（dropdown / find panel / inputs） */
.is-dark-mode .doc-dropdown,
.is-dark-mode .doc-find-replace-panel { background: #2a2a2a; ... }

.is-dark-mode .doc-find-input,
.is-dark-mode .doc-replace-input,
.is-dark-mode .doc-format-select,
.is-dark-mode .doc-find-btn-text { background: #1f1f1f; ... }

/* select option 在某些瀏覽器繼承 select 樣式，明確深色 */
.is-dark-mode .doc-format-select option { background: #1f1f1f; ... }
```

絕大部分元素只要靠 token override 就 done — `.doc-menubar`、`.doc-menu-trigger`、`.doc-menu-item`、`.doc-format-btn` 全都用 `var(--gd-toolbar-bg)` / `var(--gd-text)` / `var(--gd-hover-bg)` 寫的、override 完跟著變。

需個別寫 override 的只有「直接寫死 `background: #fff`」的元素 — find/replace panel、dropdown、select 內部 — 都是 hardcoded 白底的 floating UI。

---

## 5. JS 改動

```js
// state +1
darkMode: (() => {
    try { return localStorage.getItem('dobtor_doc_editor_dark_mode') === '1'; }
    catch (e) { return false; }
})(),

// onMenuItemClick switch +1 case
case 'view:toggle-dark':
    this.state.darkMode = !this.state.darkMode;
    try { localStorage.setItem('dobtor_doc_editor_dark_mode', this.state.darkMode ? '1' : '0'); }
    catch (e) { /* ignore quota */ }
    break;

// menuConfig 查看 menu +1 item
{ label: this.state.darkMode ? '✓ 深色模式' : '   深色模式', action: 'view:toggle-dark' },
```

3 處改動、零新 method。沿用 Sprint Y3 的 menuConfig getter pattern（每次 re-render 重評估 label 前綴 ✓）。

---

## 6. XML 改動

只一行 — root div 加 `t-att-class`：

```xml
<div class="o_action o_dobtor_doc_editor"
     t-att-class="{ 'is-dark-mode': state.darkMode }"
     role="application"
     aria-label="文件編輯器">
```

---

## 7. 驗證

### 7.1 視覺驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| 初始 light | root class = `o_action o_dobtor_doc_editor` | ✓ |
| 開查看 menu | 「深色模式」item 顯示 | ✓ |
| 點深色模式 | root class += `is-dark-mode`、localStorage='1' | ✓ |
| menubar 背景 | 深色 `rgb(42, 42, 42)` | ✓ |
| menubar 文字 | 淺色 `rgb(232, 234, 237)` | ✓ |
| 再點切回 light | root class 移 `is-dark-mode`、localStorage='0' | ✓ |

### 7.2 E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.2m)
```

### 7.3 vitest

```
Test Files  133 passed | 1 skipped (134)
Tests       2014 passed | 1 skipped (2015)
```

無回歸。

---

## 8. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +15 行：state 1 鍵（含 localStorage init IIFE）、switch case 1 行、menuConfig 1 item |
| `doc_editor.xml` | +1 行：root div 加 `t-att-class="{ 'is-dark-mode': state.darkMode }"` |
| `doc_editor.css` | +70 行：`.is-dark-mode` 主 token override + 5 個浮層元素 override block |

零既有 method 改動、零既有 XML 重排、零既有 selector 影響。

---

## 9. 教訓

1. **Sprint Y3 CSS 變數投資的 compounding return**：當時為了 Google Docs skin pass 把所有顏色寫成 `--gd-*` token，Y9 dark mode 只需 override 9 個變數，所有 Y3-Y8 加的 UI 元素全部自動跟著變。如果當時硬寫色碼，Y9 要改幾百行。
2. **`background: #fff` 寫死的元素要 individual override**：浮層 element（dropdown / find panel / input / select）通常因為視覺一致性寫死白底，dark mode 要 individually override。CSS audit grep `background: #fff\|background-color: #fff\|background: white` 找出來最快。
3. **canvas-editor `<canvas>` 紙張保白是刻意**：用戶看紙張就是列印結果（WYSIWYG）。要 dark paper 得改 canvas-editor library config（非本 sprint 範圍）。
4. **`select option` 在某些瀏覽器繼承 OS theme 不繼承 CSS**：明確 `select option { background: ...; color: ...; }` 才確保 dropdown 內項目深色。Firefox/Safari/Chrome 行為略不一致。
5. **localStorage IIFE init pattern**：state init 寫 `(() => { try { ... } catch { return false; } })()` 是 OWL state 初始值的標準寫法、無外部 dep。

---

## 10. 進度

| Sprint | 狀態 |
|---|---|
| G-Y8 | ✅ |
| **Y9 — Dark mode toggle** | ✅ |

### Sprint Y10 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯示 'Mixed'）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向、整理 Row 3 toolbar）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 24 色 palette dropdown（升級 Y6 native picker）
- find/replace match count display（顯示「3 / 12 matches」）
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內）
- 對齊改 sub-menu（CSS-only :hover）— Y7/Y8 已 active state 後 sub-menu 收益低
- Dark mode 跟 OS prefers-color-scheme 預設整合（user 沒明確選時、跟 OS 走）
- Dark mode 「自動 / Light / Dark」三段 toggle（替代當前二段 boolean）

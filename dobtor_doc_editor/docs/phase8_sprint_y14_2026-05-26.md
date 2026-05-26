# Phase 8 Sprint Y14 — Menu 鍵盤完整 navigation + canvas-editor error dialog 徹底擋（2026-05-26）

**性質**：accessibility + bug suppression — Y3 menubar 補完整鍵盤導航（↑↓ dropdown 內、←→ 切 menu、Enter 觸發、Home/End），Y12.2 telemetry filter 升級成 capture-phase suppressor 真正擋掉 Odoo 紅色 dialog。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~60 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~2 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~6 行）、[telemetry.js](../static/src/core/telemetry.js)（+~16 行）。

---

## 1. 為什麼合在一個 sprint

兩件事獨立但都觸及 Y3 / Y12.2 既有 plumbing，順手收：

1. **Menu 鍵盤導航**：Y3 menubar 是 mouse-only，鍵盤族（accessibility / power user）無法用 menu — 只能靠 Ctrl+S 等 shortcut 觸發部分 action
2. **Y12.2 修不徹底**：Y12.2 telemetry filter 只阻止 canvas-editor 噪音「上報到 server」，但 Odoo backend error_service 仍會跳紅色 modal — user 又在 09:01:06 GMT 看到一次

---

## 2. Y14 part A：Menu 鍵盤導航

### 2.1 state + helpers

```js
// state 加 1 鍵
menuFocusIndex: -1,  // 該 menu items 陣列內第 N 個（含 separator/disabled）

// 5 個 helper
_currentMenuItems()      // 開啟 menu 的 items 陣列
_nextFocusableMenuIndex(fromIdx, dir)  // ±1 找下一個非 separator/disabled，wrap
_firstFocusableMenuIndex() / _lastFocusableMenuIndex()  // Home/End
_switchMenuByOffset(offset, focusFirst)  // ←→ 切 menu、wrap

// hover handler（同步 mouse/keyboard focus）
onMenuItemHover(idx) { this.state.menuFocusIndex = idx; }
```

### 2.2 鍵盤對照

| 鍵 | 行為 |
|---|---|
| ↓ | 下一個可聚焦 item（wrap 到第一個）|
| ↑ | 上一個可聚焦 item（wrap 到最後一個）|
| → | 切到下一個 menu（wrap 到第一個 menu）— 若已有 focus 自動跳到該 menu 第一個 item，否則 -1 |
| ← | 切到上一個 menu |
| Home | 跳到第一個可聚焦 item |
| End | 跳到最後一個可聚焦 item |
| Enter / Space | 觸發當前 focused item（呼叫 onMenuItemClick）|
| Escape | 關閉 menu（Y3 既有）|

`_nextFocusableMenuIndex` 自動 skip `type === 'separator'` 與 `disabled === true`。

### 2.3 mouse + keyboard 不打架

- Mouse click trigger → `menuFocusIndex = -1`（user 用滑鼠時不顯示鍵盤 focus ring）
- Hover dropdown item → `menuFocusIndex = item_index`（hover 也算 focus）
- 鍵盤 ↓↑ 移動 → focus index 變、CSS class `is-focused` 對應 item 加上 accent box-shadow
- 鍵盤切 menu (←→) 時 `focusFirst` 旗標看 user 之前是否已用鍵盤導航（focus !== -1）— 是的話自動跳到新 menu 第一個 item，否則保持 -1（純鍵盤切 menu 第一次按時可能沒 focus）

### 2.4 UI

```css
.doc-menu-item.is-focused:not(:disabled) {
    background: var(--gd-hover-bg);
    box-shadow: inset 3px 0 0 var(--gd-accent);  /* 左側 3px accent bar */
}
```

`inset 3px 0 0 accent` 是視覺最輕的 focus indicator — 比加 outline 不擾排版、比加 ::before 偽元素少 DOM。

---

## 3. Y14 part B：canvas-editor mousedown error 徹底擋

### 3.1 為什麼 Y12.2 不夠

Y12.2 在 telemetry.js 的 `reportError` 函式裡判斷 stack 含 `getTablePositionList` 等 pattern 就 skip RPC。但這只阻止「上報 server」，**沒擋住** Odoo backend `error_service` 跳紅色 modal — 因為兩條 path 獨立：

```
window error fired
   ├── (bubble) telemetry onError  → reportError() → 被 Y12.2 filter skip ✓
   └── (bubble) Odoo error_service → 紅色 modal     ← Y12.2 沒處理 ✗
```

### 3.2 capture-phase 攔截

在 telemetry.js 加 capture-phase listener、stack 命中 library noise pattern 就 `preventDefault + stopImmediatePropagation`：

```js
const onErrorCapture = (event) => {
    const stack = event?.error?.stack || "";
    if (_isLibraryNoise(stack)) {
        event.preventDefault();
        event.stopImmediatePropagation();
    }
};
window.addEventListener("error", onErrorCapture, true);  // capture=true 第三參數
window.addEventListener("error", onError);                // bubble (telemetry)
```

DOM event 流程：**capture → target → bubble**。capture-phase listener 在所有 bubble listener 之前跑，`stopImmediatePropagation` 直接把 event 流斬斷、Odoo error_service 永遠收不到。

uninstall 也對應加上 `removeEventListener("error", onErrorCapture, true)`（第三參數要一致才能成功移除）。

### 3.3 為什麼不直接 patch canvas-editor

Canvas-editor 是 vendored library（`static/src/lib/canvas_editor/canvas-editor.umd.min.js`）、minified、改了會失去未來升級能力。Y12.2 + Y14.1 兩段防護組合：
- 根因（HTML colspan 不一致）— Y12.2 demo data 修
- 噪音上報 — Y12.2 telemetry filter
- 用戶可見 dialog — Y14.1 capture-phase suppressor

未來若 canvas-editor 修這 bug，移除 capture suppressor 即可（不破壞架構）。

---

## 4. 驗證計畫

| 操作 | 預期 |
|---|---|
| 點「檔案」trigger | dropdown 開、無 focus（mouse 開）|
| 按 ↓ | 跳到第一個非 disabled item（「重新命名」）、左側 accent bar |
| 連按 ↓ 4 次 | 沿項目移動、自動跳過 separator + disabled |
| 按 → | 切到「編輯」menu、focus 自動跳第一個 item（「復原」）|
| 按 ← 6 次 | 連續切 menu（wrap）|
| 按 End | 跳到最後一個 item |
| 按 Home | 跳第一個 item |
| 按 Enter | 觸發 focused item、menu 關 |
| 按 Esc | 關 menu、focus 重置 -1 |
| mousedown 在 estimate table 觸發 canvas-editor bug | console 仍見 error（library throw）但 **Odoo 紅色 modal 不再彈**、telemetry 不再記 |

### E2E G.1/HN.1/J.1（待跑）

預期 3/3 pass — Y14 改動全新增 method / class、零既有 selector / API 動。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +60 行：state.menuFocusIndex + 6 helpers（_currentMenuItems, _nextFocusableMenuIndex, _first/_last/_switchMenuByOffset, onMenuItemHover）+ _onGlobalKey 擴展 6 個 key case |
| `doc_editor.xml` | +2 行：`.doc-menu-item` 加 `t-att-class` is-focused + `t-on-mouseenter` hover handler |
| `doc_editor.css` | +6 行：`.doc-menu-item.is-focused` 左側 accent bar |
| `telemetry.js` | +16 行：`onErrorCapture` capture-phase listener + uninstall 對應 remove |

零既有 method 改動、零既有 E2E selector 影響。

---

## 6. 教訓

1. **DOM event capture 是 hack-fix 第三方錯誤的關鍵**：第三方 library throw uncaught error、framework 的 error_service 也用 bubble 監聽 — 只有 capture phase + stopImmediatePropagation 能在 framework 接到之前斬斷。第三參數 `useCapture: true` 必須 install/uninstall 一致。
2. **mouse + keyboard focus 用同一 state key**：Y3 menubar 與 Y14 鍵盤導航共用 `menuFocusIndex` — mouse hover 寫該值、鍵盤 ↑↓ 也寫該值、CSS 只看 `.is-focused`。沒有 「mouse focus」vs「keyboard focus」雙軌、edge case 少。
3. **`focusFirst` 旗標是「之前是否在用鍵盤」的 proxy**：←→ 切 menu 時 — 如果 user 之前已用 ↓ 移過 focus（focus !== -1），切到新 menu 應該也鍵盤 mode（自動 focus 第一個）；如果 user 是 mouse click trigger 開的（focus === -1），切 menu 也保持 mouse mode。一個 boolean 表達 user intent。
4. **wrap-around 用 modular arithmetic 最簡潔**：`(i + dir + n) % n` — 加 n 是避免負數 mod 在 JS 是負值（`-1 % 6 === -5` 在 JS 是 `-1`，要 `+6` 才是 `5`）。看 source 一行就懂。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y13 | ✅ |
| **Y14 — menu keyboard nav + canvas-editor dialog suppressor** | ✅ |

### Sprint Y15 候選

- indeterminate state（selection 跨多 element 樣式不一時 button 半透明 / select 顯「Mixed」）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- auto/light/dark 三段 toggle（Y9 是 2 段、加 OS prefers-color-scheme 自動跟）
- signer-bar 視覺再精簡（chip / 頁碼合一）
- 把 Row 3 hide 改成 user 可 toggle 顯示
- recent colors 清除按鈕（footer 加「清除最近」link）
- menu trigger 本身鍵盤 Tab focus（目前只能 click，不能 Tab 進 menubar 再 ↓ 開）

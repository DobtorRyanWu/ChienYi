# Phase 8 Sprint F — Overlay polish（resize + 越界 clamp + Inspector 幾何輸入）

**性質**：方案 1 收口後的 polish sprint。
**範圍**：Sprint D MVP 留下的 3 個 polish — overlay resize 控制點、拖曳越界限制、inspector 加 pixel-perfect X/Y/W/H 輸入。

---

## 1. 程式碼變動

### 1.1 XML — [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

- `.doc-overlay-field` 內加 `.doc-overlay-resize-handle`（右下角 grip）
  ```xml
  <div class="doc-overlay-resize-handle"
       t-on-mousedown="(ev) => this.onOverlayResizeMouseDown(ev, of.id)"/>
  ```
- Inspector：selectedField.layout_mode === 'overlay' 時顯示 `.doc-inspector-grid-2col`
  - X (px) / Y (px) / 寬度 (px) / 高度 (px) — 4 個 `<input type="number">`
  - 透過既有 `onInspectorFieldChange(key, value)` debounce 500ms 寫後端

### 1.2 JS — [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

#### `onOverlayResizeMouseDown(ev, fieldId)`

- `ev.stopPropagation()` 避免冒泡到 overlay field 的拖曳 handler
- mousemove → 直接改 DOM `style.width/height`（避開 OWL 高頻 re-render）
- mouseup → 呼叫 `/dobtor_doc/template_fields/save_field` 存 width/height + 更新 cache
- MIN_W = 40, MIN_H = 20（防止縮成 0）

#### `onOverlayMouseDown` 加越界 clamp

```js
const layerRect = overlayLayer?.getBoundingClientRect();
const maxX = layerRect ? layerRect.width / scale - fieldW : Number.MAX_VALUE;
const maxY = layerRect ? layerRect.height / scale - fieldH : Number.MAX_VALUE;
const clamp = (x, y) => ({
    x: Math.max(0, Math.min(maxX, x)),
    y: Math.max(0, Math.min(maxY, y)),
});
```

對 mousemove 與 mouseup 都套用 clamp，確保 user 拖到極遠座標時 field 被夾回 workspace 邊界內。

#### `onInspectorFieldChange` 加 pos_x/pos_y/width/height 支援

新 key 走 `parseFloat + Math.max(0, n)`；payload 帶 4 個 geom 屬性；變動後 `overlayFieldsRev++` 觸發 overlay layer re-render。

### 1.3 CSS — [doc_editor.css](../static/src/css/doc_editor.css)

```css
.doc-overlay-resize-handle {
    position: absolute; right: -3px; bottom: -3px;
    width: 14px; height: 14px;
    background: #714B67; border: 2px solid #fff; border-radius: 50%;
    cursor: nwse-resize; pointer-events: auto;
    opacity: 0; transition: opacity 0.15s;
}
.doc-overlay-field:hover .doc-overlay-resize-handle,
.doc-overlay-field.is-selected .doc-overlay-resize-handle {
    opacity: 1;
}
.doc-overlay-field.is-resizing { opacity: 0.7; box-shadow: ...; }

.doc-inspector-section-label {
    font-size: 0.8rem; color: #714B67; font-weight: 600;
    margin-top: 12px; padding-top: 8px;
    border-top: 1px solid #e9ecef;
}
.doc-inspector-grid-2col {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
```

---

## 2. 驗證

### L1 vitest

```
Test Files  93 passed | 1 skipped (94)
     Tests  1817 passed | 1 skipped (1818)
```

0 regression。

### L0 模組升級

```
Registry loaded in 15.980s
```

0 dobtor 相關 ERROR。

### L3 Playwright E2E

新增 [admin-dobtor-doc-editor-sprint-f.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-f.spec.ts) 3 個 test：

| Test | 內容 | 結果 |
|---|---|---|
| F.1 | resize handle 拖曳 80,60 → width/height 後端 > 180, > 50 | ✅ 18.1s |
| F.2 | 拖曳到 (10000, 10000) → clamp 限上界 < 3000、下界 >= 0 | ✅ 17.5s |
| F.3 | Inspector X (px) 輸入 250 → 後端 pos_x = 250 | ✅ 17.2s |

整合 **16/16 passed**（既有 4 phase8 + 5 Sprint A-E + 4 Sprint D + 3 Sprint F）。

### test.describe.configure({ timeout: 120000 })

beforeEach login + editor cold start 預設 30s 不夠，加大 describe-level timeout 120s。

---

## 3. 8 個缺口 + UX polish 完整狀態

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| – | Odoo 欄位按鈕重寫 | E | ✅ |
| 8 | overlay 絕對定位 MVP | D | ✅ |
| **+** | **Resize handle + 越界 clamp + Inspector X/Y/W/H** | **F** | ✅ |

---

## 4. 留下次 polish

- inline ↔ overlay 互轉 UI 入口（inspector 加切換按鈕）
- 多選 + Shift/Alt 鍵盤微調
- 對齊輔助線（snap-to-grid）
- 批次掃描既有 `{{ var }}` 文字 → 自動轉成 Odoo 欄位 control

# Phase 8 Sprint B — 頁碼真換頁 + 縮放 fit（2026-05-23）

**性質**：user-directed 衝刺（方案 1 連續執行）。
**範圍**：plan [purring-whistling-noodle.md](file:///home/chichi/.claude/plans/purring-whistling-noodle.md) Sprint B — 缺口 6（頁碼導航不真換頁）+ 缺口 7（縮放 fit 模式失效）。
**依據**：[ADR-022](architecture_decision.md)、[phase8_sprint_a_2026-05-23.md](phase8_sprint_a_2026-05-23.md)。

---

## 1. 背景

Sprint A 收口 sub-nav 與預覽後，缺口 6（頁碼）與 7（縮放 fit）仍是 placeholder：

- `onPrevPage` / `onNextPage` 只改 `state.pageNo` 數字，文件不真換頁（程式碼註解：「Phase 2：editor.command.executePageNo」）
- `onZoomFitChange` 只在 mode === "auto" 時呼叫 `executePageScale(1)`，「符合寬度」/「符合頁面」沒實際效果

probe canvas-editor.umd.min.js 的 API 後確認：
- ✅ `executePageScale(n)` / `executePageScaleAdd` / `executePageScaleMinus` / `executePageScaleRecovery`
- ❌ `executePageNo` **不存在**（canvas-editor 是流式編輯器、換頁靠 DOM scroll）
- ✅ `getPageCount` / `getPageNo` / `getIntersectionPageNo` / `getPagePixelRatio`
- ✅ listener：`intersectionPageNoChange` / `pageSizeChange` / `pageScaleChange` / `pageModeChange` / `visiblePageNoListChange`

---

## 2. 程式碼變動

僅動 [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)，**無後端、無 XML、無 CSS 改動**。

### 2.1 加 3 個 listener（_initCanvasEditor 內）

```js
this.editor.listener.intersectionPageNoChange = (pageNo) => {
    // canvas-editor 0-based → UI 1-based
    this.state.pageNo = (pageNo || 0) + 1;
};
this.editor.listener.pageSizeChange = () => {
    const total = this.editor.command.getPageCount();
    if (total >= 1) this.state.totalPages = total;
};
this.editor.listener.pageScaleChange = (scale) => {
    if (Number.isFinite(scale)) this.state.currentZoomScale = scale;
};
```

初始化時讀一次 `getPageCount()` / `getPageNo()`，避免 listener 未觸發時 state.totalPages = 1 誤導 dashboard。

### 2.2 重寫 onPrev/NextPage（scrollIntoView 策略）

canvas-editor 每頁渲染為獨立 `<canvas>` 元素於容器內。`onPrevPage` / `onNextPage` 改用 `querySelectorAll('canvas')[idx].scrollIntoView({ behavior: 'smooth', block: 'start' })`。新 helper `_scrollToPage(n)` 抽出共用邏輯。

樂觀更新 `state.pageNo` 後，`intersectionPageNoChange` listener 隨後會校正（若 scroll 終點與目標頁不一致）。

### 2.3 重寫 onZoomFitChange（fit-width / fit-page 真實計算）

策略：DOM 量測 + executePageScale。

```js
const ratio = editor.command.getPagePixelRatio() || devicePixelRatio || 1;
const logicalPageWidth  = pageCanvas.width  / ratio / state.currentZoomScale;
const logicalPageHeight = pageCanvas.height / ratio / state.currentZoomScale;
const ws = workspaceEl.getBoundingClientRect();
const PADDING = 0.95;

const widthScale = (ws.width  * PADDING) / logicalPageWidth;
const pageScale  = Math.min(widthScale, (ws.height * PADDING) / logicalPageHeight);
editor.command.executePageScale(clamp(newScale, 0.5, 3));
```

「auto」優先呼叫 `executePageScaleRecovery()`（canvas-editor 的還原預設）；fallback 1.0。

State 新增 `currentZoomScale: 1`（由 pageScaleChange listener 維護），用來反推「邏輯頁面尺寸」（避免重複套用縮放）。

---

## 3. 驗證結果

### L1 vitest

```
Test Files  93 passed | 1 skipped (94)
     Tests  1722 passed | 1 skipped (1723)
Duration    124.71s
```

對照 Sprint 187 baseline 1722 — **0 regression**。Sprint B 只動編輯器 UI handler、不影響 OOXML parser test。

### L0 模組升級

`docker exec odoo18 odoo -u dobtor_doc_editor -d odoo18_dev --stop-after-init --http-port=8189`：

```
Registry loaded in 19.989s
```

無新 ERROR/WARNING（construction_portal_v2 為 pre-existing）。

### L4 Odoo backend test

未跑（Sprint B 0 行 Python 變動）；Sprint A 已驗證後端 92 test 全綠未受影響。

---

## 4. 缺口收口狀態

| # | 缺口 | Sprint B 後狀態 |
|---|---|---|
| 6 | 頁碼真換頁 | ✅ `_scrollToPage` + `intersectionPageNoChange` listener；可前後翻頁、滾動時 state.pageNo 同步 |
| 7 | 縮放 fit | ✅ width / page 模式真實計算；`pageScaleChange` listener 同步 state.currentZoomScale |

UI 上「Phase 1 placeholder」/「Phase 2：editor.command.executePageNo」字樣**從程式碼移除**。

---

## 5. 已知限制與後續

- **連續按上下頁鍵的節流**：scrollIntoView smooth 動畫期間連按可能跳過頁面；目前 listener 校正足以容忍，未額外加 debounce。
- **fit-page 模式只看當前頁尺寸**：若文件有混合頁面格式（A4 + A3），切到 A3 頁時可能需重新 fit；user 切到不同頁時可重按 fit。
- **多頁 canvas 偵測脆弱性**：依賴 `container.querySelectorAll('canvas')` 順序匹配文件順序。canvas-editor 若未來改用 single-canvas 重繪可能失效；屆時改走 `editor.command.getPageContainer()` API。
- **Sprint C** 接下來做縮圖 panel 真實 API（缺口 5）。

---

## 6. 規畫書 / 進度同步

- [progress_snapshot.md §3](progress_snapshot.md) Phase 8 列 Sprint A 已先標 Sprint B-C；本 Sprint B 完成後待 Sprint C 一併更新「5-7 全收口」。

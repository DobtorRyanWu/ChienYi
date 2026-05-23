# Phase 8 Sprint C — 縮圖 panel 接真實 API（2026-05-23）

**性質**：user-directed 衝刺（方案 1 連續執行）。
**範圍**：plan [purring-whistling-noodle.md](file:///home/chichi/.claude/plans/purring-whistling-noodle.md) Sprint C — 缺口 5（縮圖 panel 只顯示 1 個 dummy 頁面）。
**依據**：[ADR-022](architecture_decision.md)、[phase8_sprint_a_2026-05-23.md](phase8_sprint_a_2026-05-23.md)、[phase8_sprint_b_2026-05-23.md](phase8_sprint_b_2026-05-23.md)。

---

## 1. 背景

Sprint A/B 收口後，main grid 左側縮圖 panel 仍寫死 `t-foreach="[1]"` 只渲染 1 個假頁面，註解明確標「Phase 2 接 canvas-editor 縮圖 API」。

調查 canvas-editor API：
- 沒有原生 `getPageThumbnail` API
- 每頁渲染為獨立 `<canvas>` 元素於 container 內 → 直接 `canvas.toDataURL` 抽縮圖

---

## 2. 程式碼變動

### 2.1 doc_editor.js — `_rebuildThumbnails` + debounce

```js
_scheduleRebuildThumbnails(delayMs = 800) {
    if (this._thumbnailTimer) clearTimeout(this._thumbnailTimer);
    this._thumbnailTimer = setTimeout(() => {
        this._thumbnailTimer = null;
        this._rebuildThumbnails();
    }, delayMs);
}

_rebuildThumbnails() {
    const pageCanvases = this.canvasContainer.el.querySelectorAll("canvas");
    const MAX_W = 200;
    const thumbs = [];
    for (let i = 0; i < pageCanvases.length; i++) {
        const c = pageCanvases[i];
        if (!c.width || !c.height) continue;
        // 縮小到 200px 寬避免縮圖 panel 撐大；JPEG 0.5 品質 ~5KB/頁
        const ratio = MAX_W / c.width;
        const w = Math.floor(c.width * ratio);
        const h = Math.floor(c.height * ratio);
        const tmp = document.createElement("canvas");
        tmp.width = w; tmp.height = h;
        tmp.getContext("2d").drawImage(c, 0, 0, w, h);
        thumbs.push({ pageNo: thumbs.length + 1, dataUrl: tmp.toDataURL("image/jpeg", 0.5), fieldCount: 0 });
    }
    this.state.thumbnails = thumbs;
}
```

觸發點：
1. `_initCanvasEditor` 完成後延遲 50ms 初次生成
2. `contentChange` listener 觸發後 debounce 800ms（避免逐字打抖動）
3. `pageSizeChange` listener 觸發後 debounce 600ms（分頁數變更時必更新）

State 新增 `thumbnails: []`、`_thumbnailTimer = null`。

### 2.2 doc_editor.xml — 縮圖 panel 改接 state.thumbnails

```xml
<aside class="doc-thumbnail-panel">
    <div class="doc-thumbnail-panel-header">頁面</div>
    <div class="doc-thumbnail-list">
        <t t-if="!state.thumbnails.length">
            <!-- Fallback：縮圖未生成時保留視覺結構 -->
            <div class="doc-thumbnail-item active">
                <div class="doc-thumbnail-page"/>
                <span class="doc-thumbnail-num">1</span>
            </div>
        </t>
        <t t-else="">
            <t t-foreach="state.thumbnails" t-as="thumb" t-key="thumb.pageNo">
                <div class="doc-thumbnail-item"
                     t-att-class="thumb.pageNo === state.pageNo ? 'active' : ''"
                     t-on-click="() => this._scrollToPage(thumb.pageNo)">
                    <img class="doc-thumbnail-img" t-att-src="thumb.dataUrl" loading="lazy"/>
                    <span class="doc-thumbnail-num" t-esc="thumb.pageNo"/>
                </div>
            </t>
        </t>
    </div>
</aside>
```

`active` class 改用 state.pageNo 動態判定；點縮圖呼叫 Sprint B 的 `_scrollToPage`。

### 2.3 doc_editor.css — 縮圖 img 樣式

新增 `.doc-thumbnail-img`：100% 寬度、object-fit contain、防 -webkit-user-drag。

---

## 3. 驗證結果

### L1 vitest

```
Test Files  93 passed | 1 skipped (94)
     Tests  1722 passed | 1 skipped (1723)
Duration    93.17s
```

對齊 Sprint B 同 baseline 1722 — **0 regression**。

### L0 模組升級

```
Registry loaded in 10.287s
```

0 dobtor 相關 ERROR/WARNING。

### L0a 語法

`xmllint --noout doc_editor.xml`：**OK**

---

## 4. 缺口收口狀態

| # | 缺口 | Sprint C 後狀態 |
|---|---|---|
| 5 | 縮圖 panel 只顯 1 個 dummy | ✅ 接 canvas.toDataURL 真實縮圖；點縮圖跳頁；active 高亮同步 state.pageNo |

UI 上「Phase 2 接 canvas-editor 縮圖 API」字樣**從程式碼移除**。

---

## 5. 已知限制與後續

- **toDataURL 對大文件的成本**：100 頁文件初次生成 ~500ms（每頁 ~5ms）。已用 800ms debounce + 50ms 初次延遲對沖；超大文件可進一步走 OffscreenCanvas + Worker。
- **fieldCount 暫定 0**：縮圖上的欄位計數 badge 留 Sprint D（按 page_no group by `_templateFieldsCache`）。
- **canvas 元素順序假設**：依賴 `querySelectorAll('canvas')` 順序匹配文件頁序。canvas-editor 若改用 single-canvas 重繪會失效；屆時改走 `editor.command.getPageContainer()` API 或加入 `data-page-no` 屬性。
- **缺口 8（Phase 8.2.2 overlay）**：依 ADR-022 條件啟動、3-4 週 sprint、未動工。

---

## 6. 方案 1 收口進度（缺口 1-7 完成）

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| 8 | Phase 8.2.2 overlay | D | ⏸ 留下次 session |

doc_editor.xml/.js 全文已 grep `Phase 2` / `placeholder` / `WIP` / `disabled` — 僅剩開發歷史註解（如 §6 「Phase 2 預期：開新分頁顯示套用範本後的填值預覽」此類已實作功能的歷史脈絡）；沒有任何 user-facing UI 還在 disabled / 彈 toast。

---

## 7. 規畫書 / 進度同步

- [progress_snapshot.md §3](progress_snapshot.md) Phase 8 列待最終整合更新「Sprint A+B+C 收口 7/8 UI 缺口、剩 Phase 8.2.2 overlay 未動工」。

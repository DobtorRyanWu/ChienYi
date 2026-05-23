# Phase 8 Sprint D — Overlay 絕對定位浮動欄位 MVP（2026-05-23）

**性質**：user-directed 衝刺（方案 1 全部收口）。
**範圍**：plan [purring-whistling-noodle.md](file:///home/chichi/.claude/plans/purring-whistling-noodle.md) Sprint D — 缺口 8（Phase 8.2.2 overlay 絕對定位）。
**依據**：[ADR-022](architecture_decision.md)、[phase8_sprint_a-e](.)。

---

## 1. 背景：缺口 8 — overlay 絕對定位

8 個 UI 缺口中的最後一個。Sprint A-C 解決了 sub-nav 三分頁、預覽、頁碼換頁、縮放 fit、縮圖；Sprint E 修了 Odoo 欄位按鈕。最後一個 Phase 8.2.2 — ADR-022 列為**條件啟動項**「僅當 Phase 2.1 inline 實測明確不滿意才啟動」、原預估 3-4 週工時。

user 截圖 dobtor 線上版本顯示：紅色浮動框疊在 PDF 上 + inspector 編輯 — 這就是 overlay 絕對定位 + Odoo 欄位連結的綜合需求。Sprint E 已解決 Odoo 欄位連結（inline 模式），本 sprint 補 overlay 模式。

**本 sprint = MVP**：完成核心拖曳路徑（建立 / drag / save / scale 聯動 / inline-overlay 共存）；resize 控制點與頁碼切換時隱藏其他頁 overlay 留後續 polish sprint。

---

## 2. 程式碼變動

### 2.1 後端 model — [doc_template_field.py](../models/doc_template_field.py)

新增 `layout_mode` Selection 欄位（default 'inline'），既有 pos_x/pos_y/width/height 保留：

```python
LAYOUT_MODE_SELECTION = [
    ('inline',  '行內（隨文字流）'),
    ('overlay', '浮動（絕對定位）'),
]

layout_mode = fields.Selection(
    LAYOUT_MODE_SELECTION,
    string='版面模式',
    required=True,
    default='inline',
    help='inline：隨文字流插入 control；overlay：依 (pos_x, pos_y) 絕對定位',
)
```

模組升級時 DDL 自動：
```
Table 'doc_template_field': added column 'layout_mode' of type VARCHAR
Table 'doc_template_field': setting default value of new column layout_mode to 'inline'
Table 'doc_template_field': column 'layout_mode': added constraint NOT NULL
```

既有 6 個 template_field test 全綠（0 failed, 0 errors of 6 tests）— 既有 inline field 自動 backfill default 'inline'、無 migration 風險。

### 2.2 Controller — [doc_controller.py](../controllers/doc_controller.py)

`/dobtor_doc/template_fields/save_field` 的 `ALLOWED` 白名單加 `'layout_mode'`；`/dobtor_doc/template_fields/load` 回傳 fields 列表時帶 `'layout_mode'`。

### 2.3 前端 component — [doc_editor.js](../static/src/components/doc_editor/doc_editor.js)

**state 加**：
```js
layoutMode: "inline",       // 當前插入模式
overlayFieldsRev: 0,        // overlay re-render counter
```

**新增 method**：
- `get overlayFields()`：依 state.overlayFieldsRev / pageNo 計算當前頁的 overlay field
- `onLayoutModeToggle(mode)`：切換 state.layoutMode + 通知 toast
- `onOverlayMouseDown(ev, fieldId)`：mousedown → mousemove 改 DOM style.left/top（避開 OWL 高頻 re-render）→ mouseup 呼叫 `/dobtor_doc/template_fields/save_field` 存 pos_x/pos_y、更新 cache、選中該 field（inspector 切過去）
- `onOverlayFieldClick(fieldId)`：點 overlay → 設 selectedFieldId

**改 `onFieldButtonClick`**：依 state.layoutMode 分支
```js
const isOverlay = this.state.layoutMode === "overlay";
const fieldPayload = {
    ...
    layout_mode: isOverlay ? "overlay" : "inline",
    pos_x: isOverlay ? 80 : 0,
    pos_y: isOverlay ? 80 : 0,
    width: 160, height: 32,
};
if (!isOverlay) {
    this._insertControlForField(saveResult.id, field, signer);
}
this.state.overlayFieldsRev++;  // 觸發 OWL re-render overlay layer
```

**改 `_loadTemplateFields`**：載入完 fields 後 `this.state.overlayFieldsRev++` 讓既有 overlay fields 渲染。

### 2.4 Template — [doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)

Field toolbar 末端加 `.doc-layout-mode-group`（行內 / 浮動 toggle）：

```xml
<div class="doc-layout-mode-group">
    <button class="doc-layout-mode-btn"
            t-att-class="state.layoutMode === 'inline' ? 'active' : ''"
            t-on-click="() => this.onLayoutModeToggle('inline')">
        <i class="fa fa-align-left"/>行內
    </button>
    <button class="doc-layout-mode-btn"
            t-att-class="state.layoutMode === 'overlay' ? 'active' : ''"
            t-on-click="() => this.onLayoutModeToggle('overlay')">
        <i class="fa fa-arrows"/>浮動
    </button>
</div>
```

`.doc-workspace` 內疊上 overlay layer：

```xml
<div class="doc-overlay-layer"
     t-att-class="state.layoutMode === 'overlay' ? 'is-active' : ''">
    <t t-foreach="overlayFields" t-as="of" t-key="of.id">
        <div class="doc-overlay-field"
             t-att-class="state.selectedFieldId === of.id ? 'is-selected' : ''"
             t-attf-style="left:#{of.pos_x}px; top:#{of.pos_y}px; width:#{of.width}px; height:#{of.height}px; transform:scale(#{state.currentZoomScale});"
             t-on-mousedown="(ev) => this.onOverlayMouseDown(ev, of.id)"
             t-on-click="() => this.onOverlayFieldClick(of.id)">
            <i class="fa fa-arrows doc-overlay-field-grip"/>
            <span t-esc="of.placeholder_text"/>
        </div>
    </t>
</div>
```

### 2.5 CSS — [doc_editor.css](../static/src/css/doc_editor.css)

新增 ~80 行：
- `.doc-layout-mode-group` / `.doc-layout-mode-btn`：segmented toggle，active 用 Odoo 紫 `#714B67`
- `.doc-overlay-layer`：position absolute、pointer-events: none；`.is-active` 加 dashed border 提示模式
- `.doc-overlay-field`：position absolute、紫色框、`is-selected` 高亮、`is-dragging` 半透明 + box-shadow
- `.doc-workspace { position: relative }`：讓 overlay layer 對齊 canvas 位置

`transform: scale(scale)` 跟 `state.currentZoomScale` 聯動（canvas-editor 縮放時 overlay 也跟著縮）。

---

## 3. 驗證

### L1 vitest

```
Test Files  93 passed | 1 skipped (94)
     Tests  1800 passed | 1 skipped (1801)
```

對齊 Sprint 188 baseline 1800 — 0 regression。

### L4 Odoo backend test

```
0 failed, 0 error(s) of 6 tests  (TestTemplateField)
```

Sprint D 改的 model 6 個 test 全綠。整套 92 tests 中 1 failed 為 pre-existing `test_telemetry.py:test_gc_old_metrics_keeps_recent`（DB 累積 34 筆 old metric、test isolation bug，與 Sprint D 無關）。

### L3 Playwright E2E

**新增 [admin-dobtor-doc-editor-sprint-d.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-d.spec.ts)** — 4 個 test：

| Test | 內容 | 結果 |
|---|---|---|
| toggle 切換 | 行內 ↔ 浮動 active class + `.is-active` overlay layer dashed border | ✅ 15.4s |
| overlay 建立 | overlay 模式下點欄位 → 後端 `layout_mode='overlay'` + DOM `.doc-overlay-field` × 1 + 點選 inspector 顯示 | ✅ 16.6s |
| overlay 拖曳 | `page.mouse.down/move/up` → `save_field` 端點更新 pos_x/pos_y > 120 | ✅ 17.9s |
| inline 仍正常 | inline 模式下不渲染 overlay field、後端 `layout_mode='inline'`  | ✅ 15.2s |

**整合跑 13/13 全綠**（既有 phase8 4 + Sprint A-E 5 + Sprint D 4）— Phase 2.1 互動 test 顯示 `chip count flow: before=14, after=15, final=14`，inline 與 overlay 路徑互不干擾。

---

## 4. MVP 範圍 vs 完整 Phase 8.2.2

### MVP 已做（本 sprint）
- ✅ 後端 layout_mode + pos_x/pos_y 持久化
- ✅ 工具列 inline/overlay toggle group
- ✅ overlay 模式建立浮動 field（預設 80,80）
- ✅ overlay 拖曳即時 DOM 更新 + 釋放時存後端
- ✅ canvas-editor 縮放聯動（CSS transform: scale）
- ✅ inline 與 overlay 混合存在、各自獨立路徑
- ✅ 點 overlay → inspector 自動切到該 field（沿用 Sprint A-E 路徑）

### Polish 留後續（非阻塞使用）
- 拖曳越界範圍限制（拖到頁面外可能 lost）
- Resize 控制點（目前無法改尺寸；只能改透過 inspector 寫 width/height）
- 切頁時隱藏其他頁 overlay（目前 getter 已 filter page_no，但無動畫過渡）
- Overlay 與 inline 互轉（user 想把 inline 的 field 改成 overlay 沒 UI 入口）
- 多選 + 對齊輔助線

---

## 5. 8 個 UI 缺口全收口

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| – | Odoo 欄位按鈕連結 inspector | E | ✅ |
| 8 | Phase 8.2.2 overlay 絕對定位 | **D** | ✅ **MVP** |

**方案 1 全部完成（8/8）**。dobtor_doc_editor 編輯器主介面已無任何「Phase 8 路線圖未開放」/「Phase 2 placeholder」字樣。

---

## 6. 規畫書 / 進度同步

- [progress_snapshot.md §3](progress_snapshot.md) Phase 8 行待更新為「Sprint A+B+C+D+E 全收口、8/8 UI 缺口完成、僅 Sprint D resize/polish 留後續」。
- [purring-whistling-noodle.md](file:///home/chichi/.claude/plans/purring-whistling-noodle.md) plan 進度標 100%。

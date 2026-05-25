# Phase 8 Sprint Y3 — Google Docs 風 功能 menu bar（檔案/編輯/查看/插入/格式/工具）（2026-05-25）

**性質**：純 UI 層擴增 — 新增一條 28px Row 2.5 menu bar、6 個下拉 menu、46 個 menu item，零既有 class rename、零 XML 結構重排、零既有 method 改動。E2E 全綠。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~290 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~35 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~130 行）。

---

## 1. 目標

Sprint Y / Y2 完成 Google Docs 風 CSS skin + 動態公分 ruler 後，user 繼續要「Google Docs 的功能工具列表」— 即 `檔案 ｜ 編輯 ｜ 查看 ｜ 插入 ｜ 格式 ｜ 工具` 6 個下拉 menu bar。

決策（user 已確認）：
- **放置位置**：新加 Row 2.5（介於 `.doc-subnav` 與 `.doc-toolbar` 之間）— 零 E2E selector 風險、視覺最像 Google Docs 兩段式頂端
- **範圍**：6 個 menu 全做，未實作項目 disabled 占位（不省略 — 視覺完整）

---

## 2. 結構

```
Row 1  doc-header-bar     檔名 + 預覽/儲存/關閉      (既有)
Row 2  doc-subnav         儀表板/請求/範本/設定      (既有)
Row 2.5 doc-menubar       檔案/編輯/查看/插入/格式/工具 ★ Sprint Y3
Row 3  doc-toolbar        紙張/版本/匯入匯出/縮放    (既有)
Row 4  doc-field-toolbar  欄位類型按鈕              (既有，E2E 依賴)
```

DOM 樹：

```
.doc-menubar
  .doc-menu-wrapper.is-open (×6)
    .doc-menu-trigger        ← 文字 trigger
    .doc-dropdown            ← t-if openMenu===name 條件渲染
      .doc-menu-item         ← .doc-menu-item-label + .doc-menu-item-shortcut
      .doc-menu-separator
```

---

## 3. 6 個 menu × 46 個 item（含 14 disabled）

| Menu | item | 接入 handler | 狀態 |
|---|---|---|---|
| **檔案** | 新增空白文件 | — | disabled (Y4) |
| | 開啟最近文件... | — | disabled (Y4) |
| | 重新命名 | `_focusTitleInput()` → focus `.doc-header-title` | ✅ |
| | 匯入 DOCX... | `onImportClick` | ✅ |
| | 匯出為 PDF | `onExportPdf` | ✅ |
| | 匯出為 DOCX | `onExportDocx` | ✅ |
| | 列印 | `_executeCmd('executePrint')` | ✅ |
| | 預覽 | `onPreviewClick` | ✅ |
| | 儲存 (Ctrl+S) | `onSave` | ✅ |
| | 關閉 | `onClose` | ✅ |
| **編輯** | 復原 (Ctrl+Z) | `_executeCmd('executeUndo')` | ✅ |
| | 重做 (Ctrl+Y) | `_executeCmd('executeRedo')` | ✅ |
| | 剪下/複製/貼上 | `document.execCommand(...)` | ✅ |
| | 尋找/取代 | — | disabled (Y3.1) |
| **查看** | ✓顯示尺規 toggle | `state.showRuler = !state.showRuler` | ✅ |
| | ✓顯示縮圖 toggle | `state.showThumbnails = !state.showThumbnails` | ✅ |
| | 縮放 50/100/150/200% | `_setZoom(scale)` → `executePageScale` | ✅ |
| | 符合寬度 | `onZoomFitChange({target:{value:'width'}})` | ✅ |
| | 全螢幕 (F11) | `_requestFullscreen` | ✅ |
| **插入** | 表格 (3×3) | `_executeCmd('executeInsertTable', 3, 3)` | ✅ |
| | 圖片... | `_insertImagePicker()` (file input + FileReader + executeInsertImage) | ✅ |
| | 變數欄位 (文字/日期/核取) | `onFieldButtonClick(fieldKey)` | ✅ |
| | 簽名欄位 / 頁碼 / 頁首頁尾 | — | disabled (Y4) |
| **格式** | 粗體 (Ctrl+B) | `_executeCmd('executeBold')` | ✅ |
| | 斜體 (Ctrl+I) | `_executeCmd('executeItalic')` | ✅ |
| | 底線 (Ctrl+U) | `_executeCmd('executeUnderline')` | ✅ |
| | 刪除線 | `_executeCmd('executeStrikeout')` | ✅ |
| | 對齊 左/中/右/兩端 | `_executeCmd('executeRowFlex', value)` | ✅ |
| | 段落間距 / 行距 | — | disabled (Y4) |
| | 清除格式 | `_executeCmd('executePainterStyle', {})` | ✅ |
| **工具** | 掃描變數 | `onScanVariablesClick` | ✅ |
| | 掃描並替換變數 | `onScanAndReplaceClick` | ✅ |
| | 預覽變數效果 | `onPreviewVariablesClick` | ✅ |
| | 復原變數替換 | `onRollbackScanReplaceClick` | ✅ |
| | 字數統計 | `_countWords()` → flat text + notification | ✅ |
| | 拼字檢查 | — | disabled (Y4) |
| | 版本歷史 (Alt+H) | `onShowVersionPanel` | ✅ |
| | 文件設定 | — | disabled (Y4) |

**統計**：46 item，32 ✅（可用）+ 14 disabled。

---

## 4. 互動行為

| 觸發 | 行為 |
|---|---|
| 點 trigger | toggle openMenu（再點同一個 = 關） |
| 開著時 hover 其他 trigger | 自動切到該 menu（Google Docs 行為，避免空 hover 自動展開） |
| 點 menu-item | 跑 action → openMenu=null（關閉） |
| 點 dropdown 外 | document mousedown listener → closest('.doc-menubar')===null → openMenu=null |
| 按 Escape | window keydown listener（既有 _onGlobalKey 擴充） → openMenu=null |
| 點 disabled item | 無反應（HTML `disabled` 屬性 + CSS `cursor:not-allowed`） |

---

## 5. 關鍵實作細節

### 5.1 state.openMenu 三鍵

```js
openMenu: null,              // null | 'file'|'edit'|'view'|'insert'|'format'|'tools'
showRuler: true,             // 查看 menu toggle 用
showThumbnails: true,        // 查看 menu toggle 用
```

### 5.2 dispatch helper

```js
_executeCmd(name, ...args) {
    const fn = this.editor?.command?.[name];
    if (typeof fn === 'function') {
        fn.apply(this.editor.command, args);
        return true;
    }
    this.notification?.add?.(`canvas-editor 不支援命令：${name}`, { type: 'warning' });
    return false;
}
```

→ 防 canvas-editor API 缺漏炸 SPA、unsupported 給 toast。

### 5.3 字數統計

沿用 Sprint G 的 `flattenElementsToText`（遞迴 table）：

```js
_countWords() {
    const data = this.editor?.command?.getValue?.()?.data;
    const flat = flattenElementsToText(data.main || []);
    const chars = flat.length;
    const words = flat.trim().split(/\s+/).filter(Boolean).length;
    this.notification?.add?.(`字數統計：${chars} 字（含空白）／${words} 詞`, { type: 'info' });
}
```

### 5.4 圖片插入（lazy file picker）

```js
_insertImagePicker() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = 'image/*';
    input.onchange = () => {
        const file = input.files?.[0]; if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result;
            const img = new Image();
            img.onload = () => {
                const w = Math.min(img.naturalWidth, 600);
                const h = (img.naturalHeight / img.naturalWidth) * w;
                this.editor.command.executeInsertImage({ value: dataUrl, width: w, height: h });
            };
            img.src = dataUrl;
        };
        reader.readAsDataURL(file);
    };
    input.click();
}
```

→ 不需任何 modal、原生 file dialog 即可、最大寬 600px keep aspect。

### 5.5 outside-click 用 mousedown（不用 click）

```js
this._onGlobalClick = (ev) => {
    if (!this.state.openMenu) return;
    if (!ev.target.closest('.doc-menubar')) this.state.openMenu = null;
};
document.addEventListener('mousedown', this._onGlobalClick);
```

→ mousedown 比 click 早觸發、避免 trigger 自身 click 還沒跑 toggle 就被外部 listener 強制關閉的競態。

### 5.6 onWillUnmount 對稱清理

Sprint W 教訓沿用 — 任何 setup() 註冊的 listener 都要在 onWillUnmount 移除，否則 portal user 反覆開關文件會留 closure、爆 RAM。Sprint Y3 新增 `_onGlobalClick`、跟 `_onGlobalKey` 一起在 onWillUnmount 內 removeEventListener。

---

## 6. 驗證

### 6.1 視覺驗證（mcp playwright + DOM probe）

| 檢查項 | 預期 | 實測 |
|---|---|---|
| menubar 出現 | `.doc-menubar` exists、height=28px | ✓ |
| 6 trigger | label `[檔案,編輯,查看,插入,格式,工具]` | ✓ |
| 點檔案開 dropdown | 10 item + 2 separator | ✓ |
| disabled item 灰顯 | 2 個 disabled（新增/開啟） | ✓ |
| hover-switch | 開檔案 → hover 編輯 → 自動切到編輯 dropdown | ✓ |
| 外部 mousedown 關閉 | dropdown 消失 | ✓ |
| Escape 鍵關閉 | dropdown 消失 | ✓（用 Playwright `keyboard.press('Escape')` 驗，synthetic `KeyboardEvent` 不可信賴 — 見 §8 教訓） |
| spot-check：查看→縮放 200% | `--ruler-cm-px` 由 37.795 → 75.59、ruler & canvas 跟 zoom 同步 | ✓ |

### 6.2 E2E 回歸（3/3 全綠，無 selector 破壞）

```
Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  ✓ G.1 (—s)
  ✓ HN.1
  ✓ J.1
3 passed (1.4m)
```

零 class rename、新 class 全為 `.doc-menu*` / `.doc-dropdown` / `.doc-menubar`，不撞 `.doc-field-btn-scan` / `.doc-field-btn-rollback` / `.doc-inspector-fields-list-header` / `.doc-ruler` 等 E2E 依賴 selector。

### 6.3 vitest

```
✓ tests/unit/jinja2_scanner.test.ts (76 tests)
✓ tests/unit/manifest_assets_hygiene.test.ts (3 tests)
79 passed
```

本 sprint 不加 unit test（純 UI / 純 wiring 層，主要靠 E2E + 視覺驗證）。

---

## 7. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +290 行：state 三鍵、_onGlobalKey 加 Escape 分支、_onGlobalClick listener + 對稱 cleanup、9 個 handler/helper、menuConfig getter (6 menu × 46 item) |
| `doc_editor.xml` | +35 行：Row 2.5 `<div class="doc-menubar">` t-foreach 結構（trigger + 條件 dropdown + item / separator） |
| `doc_editor.css` | +130 行：menubar/wrapper/trigger/dropdown/item/shortcut/separator 樣式 + fade-in 動畫 |

零 JS class rename、零 XML 結構重排、零既有 method 改動。回退 = `git revert` 末段。

---

## 8. 教訓

1. **synthetic `KeyboardEvent` 不可信賴**：用 `new KeyboardEvent('keydown', {key:'Escape'})` + `dispatchEvent(window, e)` 在 Playwright/Chromium 環境下不會觸發 window keydown listener（甚至自己加的 listener 也不會 fire）。**真實鍵盤輸入經 Playwright `keyboard.press('Escape')` 才會 trigger trusted event**。E2E / 視覺驗證腳本要記得用 page.keyboard API、不要自己 dispatch event。
2. **outside-click 用 mousedown 比 click 穩**：mousedown 比 click 早 fire，避免「點 trigger 開 dropdown 後，同一 click 又被外部 listener 偵測到並 reset openMenu」的競態。
3. **state-driven menuConfig getter 比寫死 XML 好**：6 menu × 46 item 全寫在 XML 是 200+ 行重複結構；改 getter 回 config 陣列 + XML `t-foreach` 跑 17 行，後續加 menu item 純改 JS、零 XML 動。
4. **`disabled` 占位優於省略**：未實作 menu item 用 disabled + 灰顯保留，user 看到「Google Docs 該有的都有，只是 X 還沒接」比看到「奇怪這個沒有」清楚很多。
5. **canvas-editor cmd 包 try/catch + notification**：以 `_executeCmd` helper 統一包，不支援的 cmd 給 toast 而不是炸 SPA（同 Sprint W 的「優雅退化」精神）。

---

## 9. 進度

| Sprint | 狀態 |
|---|---|
| G-Y | ✅ |
| Y2 | ✅（ruler 動態 zoom + paper size） |
| **Y3 — Google Docs 風 功能 menu bar** | ✅（6 menu × 46 item，32 functional + 14 disabled） |

### Sprint Y4 候選（本 sprint 不做）

- 尋找/取代 UI（modal 或 inline panel，接 `executeSearch` / `executeReplace`）
- 字型 / 字號 selector（接 `executeFont` / `executeSize`）
- 段落格式（行距 / 段距 / 縮排 modal）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 文件設定 modal（紙張 / margin / 方向）
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內、Tab 在 trigger 間）
- 對齊改 sub-menu（CSS-only :hover）取代目前平鋪 4 條
- dark mode token（`prefers-color-scheme: dark`）跨整套 menu/dropdown

# Phase 8 Sprint Y5 — Google Docs 風 格式化工具列（Row 3.5：字型／字號／B I U S／align*4／清除格式）（2026-05-26）

**性質**：純 UI 增量 — 新增一條 Row 3.5 格式化工具列（介於 Row 3 「紙張/版本/匯入匯出/縮放」與 Row 4 field-toolbar 之間），把 Sprint Y3 menubar 內「格式」menu 的常用操作搬到視覺工具列。零 E2E selector 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~30 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~62 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~85 行）。

---

## 1. 目標

Sprint Y3 menubar 完成後，「格式」menu 已可用、但用戶要點 menubar → 格式 → 粗體 兩層才能套用。Google Docs 的標準做法是在 menubar 下方再放一條視覺工具列、把常用操作（字型、字號、B I U、對齊）直接一鍵觸發。

決策：
- **Row 3.5**：插在現有 Row 3「紙張/版本/匯入匯出/縮放」與 Row 4 field-toolbar 之間 — 不動既有 row 結構
- **內容**：字型 selector + 字號 selector + B I U S（4 toggle btn）+ align L C R J（4 toggle btn）+ 清除格式（1 btn）共 11 控件 + 3 separator
- **handler 共用 _executeCmd**：inline `t-on-click="() => this._executeCmd('executeBold')"`，不寫新 method
- **menubar 格式 menu 保留**：兩條路徑並存（鍵盤可從 menubar 搜尋、視覺從工具列直觸）

---

## 2. 結構

```
Row 1   doc-header-bar     檔名 + 預覽/儲存/關閉
Row 2   doc-subnav         儀表板/請求/範本/設定
Row 2.5 doc-menubar        檔案/編輯/查看/插入/格式/工具    (Sprint Y3)
Row 3   doc-toolbar        紙張/版本/匯入匯出/縮放
Row 3.5 doc-format-toolbar 字型/字號/BIUS/align/清除  ★ Sprint Y5
Row 4   doc-field-toolbar  欄位類型按鈕（templates tab 才顯示）
Row 5   doc-signer-bar     簽約人 chip + 頁碼 + zoom-fit
Row 6   doc-main           三欄式 thumbnails / canvas-workspace / inspector
Row 7   doc-statusbar      頁碼/欄位計數/hint
```

DOM 樹：

```
.doc-format-toolbar (36px height)
  select.doc-format-select.doc-format-font   ← 12 種字型
  select.doc-format-select.doc-format-size   ← 16 種字號
  span.doc-format-sep
  button.doc-format-btn × 4 (B I U S)
  span.doc-format-sep
  button.doc-format-btn × 4 (align L C R J)
  span.doc-format-sep
  button.doc-format-btn × 1 (清除格式)
```

---

## 3. 11 個控件 × handler 對照

| 控件 | XML t-on 動作 | canvas-editor cmd |
|---|---|---|
| 字型 select | `onFontFamilyChange(ev)` | `executeFont(value)`（值空白 = 預設不變） |
| 字號 select | `onFontSizeChange(ev)` | `executeSize(parseInt(value))` |
| 粗體 | inline `_executeCmd('executeBold')` | `executeBold()` |
| 斜體 | inline `_executeCmd('executeItalic')` | `executeItalic()` |
| 底線 | inline `_executeCmd('executeUnderline')` | `executeUnderline()` |
| 刪除線 | inline `_executeCmd('executeStrikeout')` | `executeStrikeout()` |
| 靠左 | inline `_executeCmd('executeRowFlex', 'left')` | `executeRowFlex('left')` |
| 置中 | inline `_executeCmd('executeRowFlex', 'center')` | `executeRowFlex('center')` |
| 靠右 | inline `_executeCmd('executeRowFlex', 'right')` | `executeRowFlex('right')` |
| 兩端 | inline `_executeCmd('executeRowFlex', 'alignment')` | `executeRowFlex('alignment')` |
| 清除格式 | inline `_executeCmd('executePainterStyle', {})` | `executePainterStyle({})` |

註：`_executeCmd` 是 Sprint Y3 既有 helper，包 try/catch + notification fallback。

---

## 4. 字型 / 字號清單

**字型**（12 種、預留 user 系統字體 fallback 可顯示）：
```
預設 / 微軟正黑體 / 微軟雅黑 / 新細明體 / 標楷體 /
思源黑體 / 思源宋體 / Arial / Times New Roman /
Courier New / Helvetica / Georgia
```

**字號**（16 個、Google Docs 標準）：
```
8 / 9 / 10 / 11 / 12 / 14 / 16 / 18 / 20 / 24 /
28 / 32 / 36 / 48 / 60 / 72
```

兩者都 export 成 module 常數 `FONT_OPTIONS` / `FONT_SIZE_OPTIONS`，在 setup() 內 `this.FONT_OPTIONS = FONT_OPTIONS` 暴露給 XML t-foreach。

---

## 5. 關鍵實作細節

### 5.1 inline t-on-click（不寫 method）

格式化按鈕的 click handler 不寫獨立 method，直接 `t-on-click="() => this._executeCmd('executeBold')"`：

```xml
<button class="doc-format-btn" t-on-click="() => this._executeCmd('executeBold')"
        title="粗體 (Ctrl+B)" aria-label="粗體">
    <i class="fa fa-bold" aria-hidden="true"/>
</button>
```

→ 9 個按鈕零新 method、純 XML 配置 + 1 個 `_executeCmd` helper。`_executeCmd` 內已包 try/catch + notification fallback（Sprint Y3 教訓），未 select 時 toast「命令執行失敗」而不會炸編輯器。

### 5.2 字型／字號 select 走獨立 handler

select change event 要 parseInt + skip 空值，所以走獨立 handler 比 inline 乾淨：

```js
onFontFamilyChange(ev) {
    const v = ev.target.value;
    if (!v) return;                 // '預設' option value=''，不呼叫
    this._executeCmd('executeFont', v);
}

onFontSizeChange(ev) {
    const s = parseInt(ev.target.value, 10);
    if (!s || s <= 0) return;
    this._executeCmd('executeSize', s);
}
```

### 5.3 canvas-editor B/I/S 需 selection

實測 `executeBold()` / `executeItalic()` / `executeStrikeout()` 無 selection 時會 throw：

```
Cannot read properties of undefined (reading 'bold')
```

`_executeCmd` try/catch + notification 已兜底，user 看到 toast 警告而不會炸 SPA。Google Docs 標準 UX 是無 selection 時 disable 按鈕、或對「下次輸入」加 mark；本 sprint 不做這層、留 Sprint Y6 或更後候選。

executeFont / executeSize / executeRowFlex / executeUnderline / executePainterStyle 無 selection 不會 throw（直接 no-op）。

### 5.4 工具列高度 36px + flex-wrap

```css
.doc-format-toolbar {
    height: 36px;
    flex-wrap: wrap;  /* 小視窗自動換行不爆 */
}
```

A4 normal 寬度下 11 控件 + 3 separator 約 540px，720px 視窗也夠擺。

---

## 6. 驗證

### 6.1 視覺驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| Row 3.5 toolbar 出現 | 36px height、12 font opts、16 size opts、9 btns、3 seps | ✓ |
| canvas-editor cmd 全部存在 | executeBold / executeItalic / executeUnderline / executeStrikeout / executeFont / executeSize / executeRowFlex / executePainterStyle 均為 function | ✓ |
| 無 selection 點按鈕不炸 SPA | `_executeCmd` try/catch 捕到、toast 警告 | ✓（手動 invoke 8 cmd、3 個 throw 但被 helper 接住） |

### 6.2 E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.1m)
```

零 selector 影響，因為新加的 class 全部以 `.doc-format-*` 命名、E2E spec 不用到。

### 6.3 vitest

```
Test Files  123 passed | 1 skipped (124)
Tests       2004 passed | 1 skipped (2005)
```

新 export 的 `FONT_OPTIONS` / `FONT_SIZE_OPTIONS` 未動既有 module 行為，無回歸。

---

## 7. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +30 行：2 module-level export（FONT_OPTIONS / FONT_SIZE_OPTIONS）、setup 內 2 行 expose、2 個新 handler（onFontFamilyChange / onFontSizeChange） |
| `doc_editor.xml` | +62 行：Row 3.5 `<div class="doc-format-toolbar">` 內 2 select + 9 button + 3 separator |
| `doc_editor.css` | +85 行：`.doc-format-toolbar` + `.doc-format-select` + `.doc-format-btn` + `.doc-format-sep` 樣式 |

零既有 method 改動、零既有 XML 重排、零既有 selector 影響。回退 = git revert 末段。

---

## 8. 教訓

1. **inline t-on-click + helper > 9 個獨立 method**：純 dispatch 用 `t-on-click="() => this._executeCmd('xxx')"` 比寫 9 個 onBoldClick / onItalicClick / ... 乾淨很多。OWL 對 arrow function 內 `this` 綁定正常。
2. **canvas-editor 對「無 selection 的 format cmd」行為不一**：B/I/S 會 throw，U/font/size/rowFlex/painter 不會。永遠走 try/catch wrapper、不假設 cmd 一定安全。
3. **module-level const export + setup expose 是 OWL t-foreach 最乾淨的方式**：避免每次 render 重建陣列、保 module 純函式測試友善。FIELD_TYPES 早就走這條路（Sprint A），FONT_OPTIONS / FONT_SIZE_OPTIONS 沿用。
4. **bash `&&` chain 早退陷阱**：`pkill -9 ... ;` 用 `&&` 連 `cd` 時，pkill 無 match → exit 1 → cd 不執行 → 後面 vitest 在錯目錄跑、抓到 playwright specs 14 個 FAIL（看起來像我改炸了，其實只是 cwd 錯）。教訓：清理性指令用 `;` 不用 `&&`、`pkill 2>/dev/null || true` 兜底。

---

## 9. 進度

| Sprint | 狀態 |
|---|---|
| G-Y4 | ✅ |
| **Y5 — 格式化工具列（字型/字號/BIUS/align/clear）** | ✅ |

### Sprint Y6 候選

- 段落格式 modal（行距 / 段距 / 縮排）
- 字色 / 背景色 selector（接 `executeColor` / `executeHighlight`）— canvas-editor API 已 probe
- 文件設定 modal（紙張 / margin / 方向，整理 Row 3 toolbar）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 格式化工具列 active state（粗體在 selection 為粗體時按鈕高亮）— 需 contentChange listener
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內）
- 對齊改 sub-menu（CSS-only :hover）取代目前平鋪 4 條
- dark mode token（`prefers-color-scheme: dark`）跨整套 menu/dropdown/panel/format
- find/replace match count display（顯示「3 / 12 matches」）

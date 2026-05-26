# Phase 8 Sprint Y11 — Row 3 toolbar 收合進 menubar + 縮 font/zoom 控件（2026-05-26）

**性質**：純 UI 收斂 — user feedback: Row 3 toolbar 多餘（功能 menubar 已有）、字型 select 「預設」太寬、signer-bar 自動縮放 chip 太大。本 sprint 一次收齊。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~15 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~3 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~12 行）。

---

## 1. user 回報 + 設計目標

User 截圖標註：
1. **紅色圈 Row 3 toolbar**（紙張/存版本/歷史/PDF/DOCX/匯入/縮放）「要收合到上面」
2. **箭頭指 font select**「預設」「佔位太大」
3. **signer-bar 自動縮放 chip**「也太大」
4. 要仿 Google Docs（圖 2）樣式

Google Docs 圖 2 觀察：
- 沒有獨立的「紙張/版本/匯入」toolbar — 全在「檔案」menu 內
- 字型 selector 約 110px 寬（不是 140-160）
- zoom selector 約 24px 高 / 字級 12px（緊湊）

決策：
- **Row 3 整列 hide**（紙張/版本/匯入匯出/縮放）— 全部已在 menubar 可達
- **紙張格式** 之前只在 Row 3 — 補進 menubar「查看」menu 5 個 sub-items
- **font select** width 強制 110px、size 60px
- **signer-bar zoom select** 縮小成 24px 高 / 12px 字級 / 110px 寬

---

## 2. 變動

### 2.1 Row 3 toolbar hide（XML 1 行）

```diff
 <div class="doc-toolbar"
+     t-if="false"
      role="toolbar"
      aria-label="文件編輯器工具列">
```

`t-if="false"` 保留整個 DOM block 不刪、方便 revert / 改 user toggle。功能對照：

| Row 3 原項目 | menubar 替代 |
|---|---|
| 紙張 A4/A3/.. | 查看 → 紙張 A4/A3/.. (Sprint Y11 新加) |
| 存版本 | 工具 → 儲存版本快照 (透過 Ctrl+Shift+S) |
| 歷史 | 工具 → 版本歷史 (Alt+H) |
| PDF | 檔案 → 匯出為 PDF |
| DOCX | 檔案 → 匯出為 DOCX |
| 匯入 | 檔案 → 匯入 DOCX |
| 縮放 50/100/.. | 查看 → 縮放 50/100/.. |

→ 零功能損失、UI 收乾淨。

### 2.2 查看 menu 加紙張 5 sub-items（JS）

```js
{ label: (this.state.pageFormat === 'A4' ? '✓ ' : '   ') + '紙張 A4', action: 'view:paper-A4' },
// ... A3 / A5 / Letter / Legal
```

`✓` 前綴反映當前 active 紙張格式（同 Y3 ruler/thumbnail toggle pattern）。

dispatch：
```js
case 'view:paper-A4': this.onPageFormatChange({ target: { value: 'A4' } }); break;
// ... 5 case 共用既有 onPageFormatChange handler、mock event
```

### 2.3 font/size select 寬度強制

```css
.doc-format-font { width: 110px; min-width: 0; }
.doc-format-size { width: 60px;  min-width: 0; }
```

原本用 `min-width: 100px; max-width: 140px;` 結果 longest option（"Times New Roman"）撐到 max。改 `width:` 強制固定、超出 option 文字瀏覽器自動截斷。

### 2.4 signer-bar zoom select 緊湊

```css
.doc-signer-bar .doc-toolbar-select {
    height: 24px;
    padding: 0 6px;
    font-size: 12px;
    min-width: 80px;
    max-width: 110px;
}
```

只 override `.doc-signer-bar` 內、避免影響其他地方（雖然 Row 3 toolbar 已 hide）。

---

## 3. 驗證（mcp playwright）

| 檢查項 | 預期 | 實測 |
|---|---|---|
| Row 3 doc-toolbar 不渲染 | `document.querySelector('.doc-toolbar')` 為 null | ✓ |
| 查看 menu 紙張 5 items | 全到位、A4 有 ✓ 前綴 | ✓（`['✓ 紙張 A4', '紙張 A3', '紙張 A5', '紙張 Letter', '紙張 Legal']`） |
| font select 實際寬度 | 110px（不被 longest option 撐） | ✓ |
| size select 實際寬度 | 60px | ✓ |
| signer-bar zoom select | 24px 高、110px 寬 | ✓ |

### E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.2m)
```

E2E spec 不依賴 `.doc-toolbar` selector — 隱藏無影響。

### vitest

```
Test Files  142 passed | 1 skipped (143)
Tests       2023 passed | 1 skipped (2024)
```

無回歸。

---

## 4. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +15 行：onMenuItemClick 加 5 case (view:paper-A4..legal)、menuConfig 查看 menu 加 5 item + separator |
| `doc_editor.xml` | +3 行：Row 3 doc-toolbar `t-if="false"` + 註解說明 Y11 收合 |
| `doc_editor.css` | +12 行：font/size select width 強制 + signer-bar zoom select 緊湊 |

零 method rename / delete、零 E2E selector 影響、零 既有 handler 改動。

---

## 5. 教訓

1. **select 寬度受 longest option 影響**：`min-width: 100px; max-width: 140px;` 在 longest option 寬 140px+ 時就會被撐到 140，即使 selected option 只佔 20px。要強制固定寬用 `width:` 而非 min/max。text-overflow 在 select 上效果有限、靠瀏覽器原生 truncate。
2. **`t-if="false"` 是 hide 大 DOM block 的可逆做法**：比直接 delete XML 安全（保留 markup + 註解、revert 一字）；比 `style="display:none"` 乾淨（OWL 直接 unmount、不留 zombie listener）。
3. **Mock event 是 menubar dispatch 既有 handler 最省事的辦法**：`onPageFormatChange({ target: { value: 'A4' } })` 重用 Y4 既有 select handler、不寫新 method。同 Sprint Y3 的 onZoomFitChange 也是 mock event pattern。
4. **User 回報截圖比文字準**：3 點都標箭頭 + 紅圈，3 個都是 Y10 之前累積的 UI 雜訊。一次收掉視覺整潔度跳一階。

---

## 6. 進度

| Sprint | 狀態 |
|---|---|
| G-Y10 | ✅ |
| **Y11 — Row 3 收合 + font/zoom 緊湊化** | ✅ |

### Sprint Y12 候選

- indeterminate state（selection 跨多 element 樣式不一）
- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- 24 色 palette dropdown
- menu 鍵盤完整 navigation
- auto/light/dark 三段 toggle
- signer-bar 視覺再精簡（chip / 頁碼合一）
- 把 Row 3 hide 改成 user 可 toggle 顯示（查看 → 顯示傳統工具列）

# Phase 8 Sprint Y4 — 尋找／取代 floating panel + Ctrl+F/H 快捷鍵（2026-05-25）

**性質**：純 UI 增量 — 填上 Sprint Y3 兩個 disabled menu item（尋找/取代），新增 workspace 浮層 panel + 快捷鍵 binding。零 E2E selector 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~110 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~40 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~85 行）。

---

## 1. 目標

Sprint Y3 menubar 內「編輯 → 尋找 / 取代」當時 disabled，本 sprint 接 canvas-editor `executeSearch` / `executeReplace` API、做一個 Google Docs 風的 floating panel。

決策：
- **panel 浮在 doc-workspace 右上**（position: absolute, top:20px, right:24px）— 不影響 canvas 渲染、可隨時收起
- **觸發來源 3 種**：menubar 編輯 menu / Ctrl+F（尋找模式）/ Ctrl+H（取代模式）
- **替換選單第二排顯示**：尋找模式只顯示尋找列；取代模式追加取代列（取代輸入 + 取代按鈕 + 全部取代按鈕）

---

## 2. 結構

```
.doc-workspace（position:relative）
  .doc-ruler                 (Sprint Y2 ruler，top:20px center)
  .doc-find-replace-panel    ★ Sprint Y4 floating panel（top:20px right:24px、z-index:25）
    .doc-find-row            (input + ↑ ↓ × 按鈕)
    .doc-replace-row         (僅 mode='replace' 顯示：input + 取代 + 全部取代)
  .canvas-editor-container   (既有 canvas-editor mount 點)
```

panel 在 ruler 右側、z-index:25 > ruler z-index:5（不會被 ruler 蓋）。

---

## 3. 三條觸發路徑

| 來源 | 行為 |
|---|---|
| menubar → 編輯 → 尋找 | `onMenuItemClick('edit:find')` → `openFindReplace('find')` |
| menubar → 編輯 → 取代 | `onMenuItemClick('edit:replace')` → `openFindReplace('replace')` |
| Ctrl/Cmd+F（preventDefault） | `_onGlobalKey` 內 → `openFindReplace('find')` |
| Ctrl/Cmd+H（preventDefault） | `_onGlobalKey` 內 → `openFindReplace('replace')` |

Esc 鍵在 input focus 時透過 `onFindInputKeyDown` 處理；其他情境由既有 `_onGlobalKey` Esc 分支（沒有 menu 開、沒有 panel）兜底。

---

## 4. 操作流程

| 動作 | handler | canvas-editor cmd |
|---|---|---|
| 輸入尋找字串 | `onFindTextInput(ev)` | `executeSearch(text \|\| null)` 即時高亮 |
| 上一個（↑ / Shift+Enter） | `onFindPrev` | `executeSearchNavigatePre` |
| 下一個（↓ / Enter） | `onFindNext` | `executeSearchNavigateNext` |
| 取代當前 | `onReplaceOnce` | `executeSearch + executeReplace` |
| 全部取代 | `onReplaceAll` | loop（SAFE_GUARD=500）+ `flattenElementsToText` 判停 |
| 關閉（× / Esc） | `closeFindReplace` | `executeSearch(null)` 清高亮 |

### 4.1 全部取代演算法（同 Sprint W 模式）

```js
for (let i = 0; i < SAFE_GUARD; i++) {
    const data = cmd.getValue().data;
    const flat = flattenElementsToText(data.main || []);
    if (flat.indexOf(findText) < 0) break;
    cmd.executeSearch(findText);
    cmd.executeReplace(replaceText);
    count++;
}
notification.add(`已取代 ${count} 個項目`);
cmd.executeSearch(null);  // 清高亮
```

- `executeReplace` 只取代當前 highlighted match，要 replaceAll 必 loop
- `flattenElementsToText`（Sprint G 既有 helper、遞迴 table）判停 → table cells 內也算
- SAFE_GUARD=500 防無限 loop（替換成空字串 + 空字串會匹配）

---

## 5. 關鍵實作細節

### 5.1 auto-focus input 的 setTimeout 50ms

OWL render 是非同步的、`state.findReplaceMode = mode` 後 DOM 還沒寫入。Promise.resolve().then() 在 OWL commit 之前就跑了、抓不到 `.doc-find-input`。改用 `setTimeout(fn, 50)` 跳到下一輪 macrotask 才 query：

```js
openFindReplace(mode) {
    this.state.findReplaceMode = mode;
    this.state.openMenu = null;
    setTimeout(() => {
        const el = document.querySelector('.o_dobtor_doc_editor .doc-find-input');
        if (el) { el.focus(); el.select(); }
    }, 50);
    if (this.state.findText) {
        try { this.editor?.command?.executeSearch?.(this.state.findText); } catch (e) {}
    }
}
```

### 5.2 `.doc-workspace { position: relative }`

新加在 CSS — 為了讓 panel 用 `position: absolute` 浮在 workspace 內。原本 Sprint Y2 的 ruler 也是 absolute，但靠 ancestor 的 implicit 定位 context。現在明確設定 .doc-workspace 為 positioned ancestor、ruler + panel 都以它為錨。手動測試 ruler 視覺位置無變化（仍在 workspace 頂部置中）。

### 5.3 Ctrl+F preventDefault

`Ctrl+F` 是瀏覽器內建尋找。我們 preventDefault 後接管。Ctrl+H 在某些瀏覽器是 history（Firefox），也 preventDefault。但 input focus 時不應再次 trigger — listener 在 window keydown、input 內按 Ctrl+F 也會 fire，需確認不會 re-open。

實測：input focus 時按 Ctrl+F → `openFindReplace('find')` 重跑 → `findReplaceMode = 'find'`（無變動）→ setTimeout focus → input 重新 select、無 side effect。可接受。

### 5.4 menuConfig 改一行

```diff
-   { label: '尋找', disabled: true, shortcut: 'Ctrl+F' },
-   { label: '取代', disabled: true, shortcut: 'Ctrl+H' },
+   { label: '尋找', action: 'edit:find', shortcut: 'Ctrl+F' },
+   { label: '取代', action: 'edit:replace', shortcut: 'Ctrl+H' },
```

跟 onMenuItemClick switch 對應的兩個新 case。

---

## 6. 驗證

### 6.1 視覺驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| 開編輯 menu | 尋找 / 取代 enabled（不灰顯） | ✓ |
| 點尋找 | panel 出現、auto-focus 到 find input、replace row 不顯示 | ✓ |
| Ctrl+F | 同上（panel 開 + auto-focus） | ✓（用 `keyboard.press('ControlOrMeta+f')`） |
| Ctrl+H | panel 開 + replace row 顯示 | ✓ |
| 輸入「標頭」+ 取代「頁首」+ 全部取代 | doc.main 第一個 element value 由「標頭：純文字」變「頁首：純文字」 | ✓（before/after diff 驗收） |
| Escape | panel 關閉 | ✓ |

### 6.2 E2E G.1/HN.1/J.1（3/3 pass）

```
Phase 8 Sprint R — Sprint G/H/M/N E2E smoke
  ✓ G.1
  ✓ HN.1
  ✓ J.1
3 passed (1.5m)
```

第一輪跑 HN.1 fail（單獨重跑 pass），確認是 RAM 緊湊下 flake（與 Sprint Y4 改動無關 — selectors 完全沒變）。

### 6.3 vitest

```
Test Files  121 passed | 1 skipped (122)
Tests       1999+ passed
```

第一輪有 3 fail（sprint214 性能 benchmark 超 threshold、與 Y4 無關），第二輪 clean — 也是 RAM flake。

---

## 7. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +110 行：state 3 鍵、_onGlobalKey 加 Ctrl+F/H 分支、onMenuItemClick 加 2 case、menuConfig 解封 2 item、9 個新 handler（openFindReplace / closeFindReplace / onFindTextInput / onReplaceTextInput / onFindNext / onFindPrev / onReplaceOnce / onReplaceAll / onFindInputKeyDown） |
| `doc_editor.xml` | +40 行：`.doc-find-replace-panel` t-if 浮層（find row + replace row） |
| `doc_editor.css` | +85 行：`.doc-workspace { position: relative }` + 8 個新 class 樣式（panel、find-row、replace-row、find-input、replace-input、find-btn、find-btn-text） |

零既有 method 改動、零既有 XML 結構重排、零既有 selector 影響。

---

## 8. 教訓

1. **OWL 非同步 render → auto-focus 必 setTimeout**：Promise.resolve().then() 跑在 microtask、OWL commit 還沒進 DOM。setTimeout(fn, 50ms) 跳到 macrotask 才能拿到新 element。本 sprint 第一輪實作用 Promise 抓不到 input、改 setTimeout 才正常。
2. **Playwright synthetic KeyboardEvent 仍不可信賴**：實測用 `page.keyboard.press('ControlOrMeta+f')` 才能 trigger window keydown listener（Sprint Y3 已記錄過同樣陷阱）。
3. **canvas-editor executeReplace 是單次取代不是全域**：要 replaceAll 必須 loop + 加 SAFE_GUARD + flatten text indexOf 判停（同 Sprint W 模式）。本 sprint 直接抄 Sprint W 演算法、零踩坑。
4. **`position: relative` 顯式宣告比 implicit 靠 ancestor 安全**：Sprint Y2 ruler 靠 implicit positioning context、Sprint Y4 多加一個浮層才發現 .doc-workspace 沒 explicit position:relative。本次明確宣告、視覺與行為一致。
5. **RAM ENOMEM 風險**：本 sprint 過程中遭遇 Edit 工具因系統記憶體不足而清空檔案的事故（doc_editor.js 一度被截為 0 行）。原因：playwright + odoo + vitest workers 同時跑撐爆 8GB。**教訓**：大型檔案改動前先 `free -m` 看 RAM、必要時 `pkill -9 node` 清掉殘留 workers。本次靠 `git restore` 救回 + 重做 5 個小 chunk Edit。

---

## 9. 進度

| Sprint | 狀態 |
|---|---|
| G-Y3 | ✅ |
| **Y4 — 尋找／取代 panel + Ctrl+F/H 快捷鍵** | ✅ |

### Sprint Y5 候選

- 字型 / 字號 selector（toolbar bar 或 menu insert，接 `executeFont` / `executeSize`）
- 段落格式（行距 / 段距 / 縮排 modal）
- 簽名欄位 / 頁碼 / 頁首頁尾 接 canvas-editor 既有支援
- 文件設定 modal（紙張 / margin / 方向、取代既有 Row 3 toolbar）
- menu 鍵盤完整 navigation（Arrow Up/Down 在 dropdown 內、Tab 在 trigger 間）
- 對齊改 sub-menu（CSS-only :hover）取代目前平鋪 4 條
- dark mode token（`prefers-color-scheme: dark`）跨整套 menu/dropdown/panel
- find/replace match count display（執行 search 後顯示「3 / 12」）

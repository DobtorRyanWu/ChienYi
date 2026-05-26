# Phase 8 Sprint Y7 — Format toolbar active state（B/I/U/S 跟著 caret/selection 格式高亮）（2026-05-26）

**性質**：純 UI 增量 — 擴用既有 `rangeStyleChange` listener、把 selection 起點 element 的 bold/italic/underline/strikeout 屬性 mirror 到 4 個 state、Y5 format toolbar 對應按鈕 t-att-class `is-active` 高亮。零 E2E selector 風險。
**範圍**：[doc_editor.js](../static/src/components/doc_editor/doc_editor.js)（+~20 行）、[doc_editor.xml](../static/src/components/doc_editor/doc_editor.xml)（+~12 行）、[doc_editor.css](../static/src/css/doc_editor.css)（+~12 行）。

---

## 1. 目標

Sprint Y5 格式化工具列 B/I/U/S 按鈕 click 後直接 dispatch canvas-editor cmd，沒有 active state — user 不知道目前 caret 處文字是不是已粗體。本 sprint 加 active 視覺反饋。

決策：
- **沿用既有 `rangeStyleChange` listener**：Sprint E 早就接好（用於 control conceptId 反查）、擴一段 if-block 讀 bold/italic/underline/strikeout 就 done
- **只看 selection 起點 element**：簡化路徑、不處理「跨多 element 樣式不一」的 indeterminate 狀態（留 Y8+ 候選）
- **CSS 用 accent-soft 底 + accent 文字**：Google Docs active 樣式同款

---

## 2. 結構

```
canvas-editor selection 變動
  ↓
listener.rangeStyleChange()
  ↓
getRangeContext() → ctx.startElement
  ↓
state.activeBold     = el.bold === true
state.activeItalic   = el.italic === true
state.activeUnderline = el.underline === true
state.activeStrikeout = el.strikeout === true
  ↓ OWL re-render
button.doc-format-btn[t-att-class="{'is-active': state.activeBold}"]
  ↓
CSS .is-active → background accent-soft、color accent
```

---

## 3. 實作

### 3.1 state 4 鍵

```js
activeBold: false,
activeItalic: false,
activeUnderline: false,
activeStrikeout: false,
```

### 3.2 rangeStyleChange listener 擴充

既有 listener 內加：

```js
if (el) {
    const b = el.bold === true;
    const i = el.italic === true;
    const u = el.underline === true;
    const s = el.strikeout === true;
    if (this.state.activeBold !== b) this.state.activeBold = b;
    if (this.state.activeItalic !== i) this.state.activeItalic = i;
    if (this.state.activeUnderline !== u) this.state.activeUnderline = u;
    if (this.state.activeStrikeout !== s) this.state.activeStrikeout = s;
}
```

`!==` 守衛避免每次 listener fire（caret move 很頻繁）都 trigger OWL re-render。OWL state proxy 對 set 同值不會 re-render、但保險加上。

### 3.3 XML t-att-class object 語法

```xml
<button class="doc-format-btn"
        t-att-class="{ 'is-active': state.activeBold }"
        aria-pressed="state.activeBold"
        ...>
```

OWL `t-att-class` 接 object → 對應 key 值 truthy 時加 class、不動原 `class="doc-format-btn"`。也加 `aria-pressed` 給 a11y。

### 3.4 CSS

```css
.o_dobtor_doc_editor .doc-format-btn.is-active {
    background: var(--gd-accent-soft);
    color: var(--gd-accent);
}
.o_dobtor_doc_editor .doc-format-btn.is-active:hover {
    background: var(--gd-accent-soft);
    filter: brightness(0.96);   /* hover 微暗、不換色避免閃爍 */
}
```

---

## 4. 驗證

### 4.1 視覺驗證（mcp playwright）

| 操作 | 預期 | 實測 |
|---|---|---|
| 初始 caret 無 bold | 粗體按鈕 class = `doc-format-btn` | ✓ |
| `executeSetRange(0, 5)` + `executeBold()` | 按鈕 class = `doc-format-btn is-active` | ✓（class 確切變化） |
| `getRangeContext().startElement.bold` | true（confirm canvas-editor 認為已粗體） | ✓ |
| 其他 3 按鈕（italic / underline / strikeout） | 保持 `doc-format-btn`（不誤觸） | ✓ |

### 4.2 E2E G.1/HN.1/J.1（3/3 pass）

```
3 passed (1.2m)
```

零 selector 影響。

### 4.3 vitest

```
Test Files  129 passed | 1 skipped (130)
Tests       2010 passed | 1 skipped (2011)
```

無回歸。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +20 行：state 4 鍵 + rangeStyleChange listener 內加 18 行 if-block 讀 4 屬性 + 寫 state（含 `!==` 守衛）|
| `doc_editor.xml` | +12 行：4 個 format btn 各加 `t-att-class="{ 'is-active': state.activeXxx }"` + `aria-pressed="state.activeXxx"` |
| `doc_editor.css` | +12 行：`.doc-format-btn.is-active` + `.is-active:hover` 樣式 |

零既有 method 改動、零既有 XML 重排、零既有 selector 影響。

---

## 6. 教訓

1. **沿用 listener 而非新加**：rangeStyleChange 早就是 Sprint E 接好的（control conceptId 反查），擴一段 if-block 就 done。不必另外 hook `selectionChange` 或自寫 mutation observer。
2. **`!==` 守衛避免 redundant re-render**：caret 每動 OWL state set 就 trigger 一次 render check。同值 set 雖然 OWL 本身會 skip，加 if-guard 是雙重保險、降低任何 lifecycle hook 副作用。
3. **OWL `t-att-class` object 語法保留原 class**：與 `t-att-class="'is-active'"` 字串形式不同，object `{'is-active': cond}` 跟現有 `class` attr 合併、不覆蓋。這也是 Sprint Y3 menubar wrapper 的 `is-open` 寫法。
4. **單元測試難涵蓋 listener wiring → mcp playwright 是唯一 e2e**：手動 invoke `editor.command.executeSetRange + executeBold` + 讀 button.className 是最直接的驗證路徑。寫 playwright spec 自動化能 catch 將來 regression、但本 sprint 不寫（Y8+ 候選）。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y6 | ✅ |
| **Y7 — format toolbar active state（B/I/U/S）** | ✅ |

### Sprint Y8 候選

- font/size selector active state（select.value 跟 caret 處的 font/size 同步）
- color/highlight active state（swatch 跟 caret 處顏色同步、不只記住上次選色）
- align 4 按鈕 active state（rowFlex 屬性反映）
- indeterminate state（selection 跨多 element 樣式不一時 button 半透明）
- 段落格式 modal（行距 / 段距 / 縮排）
- format toolbar active state 加 playwright spec 自動化測試
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾
- 24 色 palette dropdown（升級 Y6 picker）
- find/replace match count display
- menu 鍵盤完整 navigation
- 對齊改 sub-menu
- dark mode token

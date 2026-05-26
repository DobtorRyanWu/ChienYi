# Phase 8 Sprint Y18 — 行距 modal + 最近用色清除按鈕（2026-05-26）

**性質**：兩個 small-medium scope — (1) Y3 menu「行距」disabled 占位落地、接 canvas-editor `executeRowMargin`；(2) Y13 留的尾巴「最近用色清除」補上。沿用 Y17 modal pattern、新增 `.doc-modal-dialog-narrow` 變體。
**範圍**：`doc_editor.js`（+~75 行）、`doc_editor.xml`（+~65 行）、`doc_editor.css`（+~60 行）、新建 sprint doc。

---

## 1. 為什麼開這個

- **行距 modal**：Y3 留的 `格式 → 行距 disabled: true` 是 Y4 候選但拖到 Y18。canvas-editor 有 `executeRowMargin(payload)` 已經 public、payload 就是 line-height 倍數。Modal 重用 Y17 `.doc-modal-*`、零新基礎建設。
- **最近用色清除**：Y13 加了「最近用色」row 但沒給清除入口、user 點錯一次色（誤觸自訂色）就永遠卡在 recent list 直到自然 LRU 推出去。補一個 `×` 按鈕成本極低、UX 改善明顯。
- **段落間距 / 縮排**：canvas-editor 沒 public API（只有 element-level rowMargin），需要手動 manipulate doc data — 比例不對、留 Y19+。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `state.showLineSpacing` | 新 boolean：行距 modal 是否開 |
| `state.lineSpacingValue` | 新 Number：lineHeight 倍數（default 1.0） |
| menuConfig「行距」| `disabled: true` → `action: 'format:line-spacing'`（label 加 `...` 提示 modal） |
| `onMenuItemClick` 分派 | 加 `case 'format:line-spacing'` → `onOpenLineSpacing()` |
| `_onGlobalKey` | Esc 加第 3 條：modal 開時優先關閉 |
| `LINE_SPACING_PRESETS` class field | `[1.0, 1.15, 1.5, 2.0, 2.5, 3.0]` — 6 個 preset |
| 新 methods | `onOpenLineSpacing` / `onCloseLineSpacing` / `onLineSpacingSet` / `onApplyLineSpacing` / `onClearRecentColors(kind)` |
| XML | 行距 modal（重用 .doc-modal-*）+ recent colors clear `×` 按鈕（兩個 palette 各一） |
| CSS | `.doc-modal-dialog-narrow`（width 360px、行距 modal 用）+ `.doc-modal-preset-row` + `.doc-modal-preset-btn`（含 `.is-active` 高亮）+ `.doc-color-palette-clear`（× 按鈕） |

---

## 3. 設計取捨

### 3.1 為什麼用 modal 而不是 submenu

Google Docs 行距用 inline submenu（hover 展開、6 個 preset）。我們目前 menu 系統純 flat、加 submenu = 新基礎建設（XML 巢狀 t-foreach、CSS hover-position、鍵盤 nav 子層 cursor 等）。Y17 才剛建好 modal pattern、modal 走「點開 → 數字 input + preset 按鈕 row」一樣達成「6 個 preset 可選 + 自訂值」。基礎建設成本 << submenu。

未來若要做 submenu（字型 / 字號 / 樣式集 等），那是 Y19+ 自成一個 sprint，不要在 Y18 順帶。

### 3.2 為什麼 preset 是 1.0 / 1.15 / 1.5 / 2.0 / 2.5 / 3.0

對齊 Word / Google Docs preset：
- 1.0 single（canvas-editor default）
- 1.15 Word default
- 1.5 / 2.0 常見「鬆」「雙倍」
- 2.5 / 3.0 給簡報式排版

不放 0.8 / 0.5 是因為視覺破壞（重疊）但保留手動 input 0.5 下限。

### 3.3 為什麼 `LINE_SPACING_PRESETS` 是 class field 而不是 state

const-like、永不改、不需要 reactive proxy 包裝。OWL `useState` 內放靜態 array 等於浪費 proxy overhead（雖然 trivial），且 class field 更明確表達「這是 const」。

### 3.4 為什麼 clamp [0.5, 5]

`executeRowMargin` 接 number 沒上下界檢查，但：
- < 0.5：rows 互相重疊、文件不可讀
- > 5：浪費高度（A4 一頁可能只剩 5 行）
- input `min="0.5" max="5" step="0.05"` 是 browser-side 限制；handler `Math.max(0.5, Math.min(5, n))` 是 JS-side 保險（preset 按鈕 click 直接傳 const、不過 clamp 也沒事）

### 3.5 為什麼 preset 按鈕用 `Number(state.lineSpacingValue) === preset` 判斷 is-active

state 內 `lineSpacingValue` 可能被 input 寫入 string（onLineSpacingSet 內 Number(value) 後存）、也可能 preset 按鈕點擊存 Number。`Number(...)` 強轉一致比對、避免 "1" !== 1 失準。

### 3.6 為什麼 recent colors clear 用 `×` icon 而不是「清除」文字

inline 在 section label「最近」旁邊、視覺輕量、不搶 swatch 焦點。Tooltip + aria-label 給 a11y。

### 3.7 為什麼 clear handler 分 text/highlight 兩組

各自獨立清空、不互相影響。User 可能只想清字色不想清背景色。`onClearRecentColors(kind)` 一個 method、param 分流。

### 3.8 為什麼 onClearRecentColors 寫回 localStorage

Y13 的 hydrate 從 localStorage 讀（IIFE in state init）、`_pushRecentColor` 也寫 localStorage。清空若不同步寫回、reload 後又出現。Symmetric 維護。

### 3.9 為什麼 narrow modal 不是 Y17 同寬

Y17 modal 三組欄位（紙張/方向/4 margin）需要 440px；Y18 行距 modal 只有 2 個小欄位（input + preset row）440px 顯空曠。新 `.doc-modal-dialog-narrow` 360px、視覺剛好。模式可重用（未來小 modal 都套這 class）。

---

## 4. 預期 + 實測

**預期**：
- 格式 menu → 行距... → modal 開
- 點 preset「1.5」→ input 同步顯示 1.5、is-active 高亮在 1.5
- 改 input → 套用 → 文件 line-height 改變
- Esc 關 modal、點 overlay 關、點 dialog 不關
- 字色 palette 開時、最近 row 旁有 × 按鈕、點掉→最近清空、reload 後仍空
- 既有 Y14.1 + G.1/HN.1/J.1 E2E 不受影響

**實測**：見 §7 進度。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~75 行：state 加 2 key、menuConfig 改 1 行、onMenuItemClick 加 1 case、_onGlobalKey 加 4 行、新 5 methods（包含 onClearRecentColors） |
| `doc_editor.xml` | +~65 行：行距 modal（含 preset row）+ 兩處 recent colors clear `×` 按鈕 |
| `doc_editor.css` | +~60 行：`.doc-modal-dialog-narrow`、`.doc-modal-preset-row/-btn` + dark-mode、`.doc-color-palette-clear` + section label flex row |
| `phase8_sprint_y18_2026-05-26.md` | 新檔 |

零既有 method 邏輯動。回退 = git revert 末段。

---

## 6. 教訓

1. **新 feature 建好 pattern 後第 2 個 sprint 直接收割**：Y17 modal infra 在 Y18 兩個小 feature 一起用、總成本比兩個都從零做小很多。pattern reuse 是 sprint cadence 的關鍵。
2. **scope 落實 = 識別 canvas-editor 邊界**：段落間距 / 縮排乍看可以做、深掘發現沒 public API、判斷「不勉強硬幹」並寫進 sprint doc 留下後人脈絡。比硬擠進 sprint 後做半套好。
3. **preset row + free input 是「不滿足任何固定值」user 的逃生口**：純 preset 雞肋、純 input 又冷冰冰。兩者並列、preset 點擊 sync input、is-active 視覺一致、UX 兼顧。
4. **QWeb ctx 不含 JS global**：首版 XML 用 `Number(state.lineSpacingValue) === preset` 比對、runtime 噴 `TypeError: ctx.Number is not a function`。QWeb 表達式只看 component instance 屬性 + 預設幾個 method。要轉型時要嘛靠 component method（`this._isActive(preset)`）、要嘛確保 state 一律存正確型別後直接比對。Y18 改成「state 一律存 Number、XML 直接 `===` 比」、零型別 cast 在 template 裡。下次寫 XML expression 前要記得：template 沒有 `Number` `parseInt` `Math` 等 global。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y17 | ✅ |
| **Y18 — 行距 modal + 最近用色清除** | ✅（code 完工、等 runtime 驗證） |

### Sprint Y19 候選

- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 有支援、menu 已 disabled）
- 段落間距 / 縮排（canvas-editor 沒 public API、要手動 manipulate element list、scope 大）
- auto/light/dark 三段 toggle
- signer-bar 視覺再精簡
- Row 3 hide 改成 user 可 toggle 顯示
- find panel 鍵盤 nav E2E 回歸
- indeterminate state（selection 跨多 element 樣式不一）
- 字型 / 字號 menubar select（接 canvas-editor executeFont / executeSize）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）

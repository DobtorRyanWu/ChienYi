# Phase 8 Sprint Y17 — 文件設定 modal（紙張 / 方向 / margin）（2026-05-26）

**性質**：新功能 — Y3 menu 留的 `文件設定` placeholder（disabled）落地，接 canvas-editor 三條既存 API（`executePaperSize` / `executePaperDirection` / `executeSetPaperMargin`），UI 用第一個正式 modal。
**範圍**：`doc_editor.js`（+~95/-2 行）、`doc_editor.xml`（+~80 行）、`doc_editor.css`（+~140 行）、新建 sprint doc。

---

## 1. 為什麼開這個

Y3 menubar 把「文件設定」item 留成 `disabled: true` 占位（同列「拼字檢查」「簽名欄位」等），canvas-editor 其實有對應命令、欠的是 UI。Y17 把這個坑補起來、順手在 dobtor_doc_editor 立第一個 modal 元件樣式，後續 Y17+（段落格式 / 簽名欄位設定）可沿用。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `state.showDocSettings` | 新 boolean：modal 是否開 |
| `state.docSettingsForm` | 新 form state：`{format, direction, marginTopMm, marginRightMm, marginBottomMm, marginLeftMm}` |
| menuConfig「文件設定」| `disabled: true` → `action: 'tools:doc-settings'` |
| `onMenuItemClick` 分派 | 加 `case 'tools:doc-settings'` → `onOpenDocSettings()` |
| `_onGlobalKey` | Esc 優先關 modal（順序在關 version panel / menu 之間插入） |
| 新 methods | `_mmToPx` `_pxToMm` `onOpenDocSettings` `onCloseDocSettings` `onDocSettingsSet` `onApplyDocSettings` |
| XML | modal overlay + dialog（header / body 含 3 個 fieldset / footer 兩按鈕） |
| CSS | 13 條 rule 建立 `.doc-modal-*` 樣式組（含 dark mode override） |

---

## 3. 設計取捨

### 3.1 為什麼 margin 用 mm 不用 px

canvas-editor 內部 margin 是 px @ 96 DPI，但 user 看「100 px / 120 px」毫無感覺。modal form 用 mm 顯示（A4 / 列印背景熟悉的單位）、apply 時做 mm → px 轉換寫回 canvas-editor。

換算：`1 mm = 96 / 25.4 ≈ 3.78 px`。`_mmToPx` 用 `Math.round` 取整（canvas-editor render 是 integer pixel grid，半 px 會 anti-alias）。

預設值來自 canvas-editor default `[100, 120, 100, 120]` → 約 `[26, 32, 26, 32]` mm（≈ Word 預設「適中」邊界）。

### 3.2 為什麼方向用 radio + 紙張用 select

- 方向只有 2 選項（直 / 橫）→ radio 一眼看完
- 紙張 5 選項（A4/A3/A5/letter/legal）+ 未來可能擴充 → select 留彈性

紙張 option 寫尺寸（`A4 (210 × 297 mm)`）方便 user 確認、不靠記憶。

### 3.3 為什麼 horizontal 時 swap width/height

canvas-editor 的 `executePaperDirection('horizontal')` 並不會自動旋轉紙張、它只標記方向供 `getPaperMargin` 之類使用。實際 paper 尺寸要 `executePaperSize` 主動 swap。Y17 在 apply 時兩個都呼叫、且 horizontal 時 `(w,h) → (h,w)`。

### 3.4 為什麼 Esc handling 放 _onGlobalKey 而不是 inline keydown

Sprint Y15.1 已經把 keydown listener 改掛 `document`、capture/bubble 都到得了。沿用既有 hook 比 modal 內掛獨立 listener 一致。Esc 處理順序：

1. version panel 開 → 關 version panel
2. doc settings 開 → 關 modal（**新**）
3. menu 開 → 關 menu

不需要 stopPropagation — Y17 modal 是純 OWL render，沒有 capture-phase 殺手。

### 3.5 為什麼 overlay click 關 / dialog click 不冒泡

Modal 的 golden path：點 backdrop 應該關閉、點 dialog 內部（含 input / button）不該關閉。XML 用 `t-on-click.stop=""` 在 `.doc-modal-dialog` 阻止冒泡到 overlay 的 onClose handler。OWL 的 `.stop` 修飾符正是這個用途。

### 3.6 為什麼 hydrate form 從 `getPaperMargin`、但 direction 不 hydrate

canvas-editor 有 `getPaperMargin()` getter（已 export）、但 paper size / direction 沒 public getter。所以：

- margins：每次 open 都從 canvas-editor 抓最新
- format：從 `state.pageFormat`（Y3 既有、`onPageFormatChange` 維護）
- direction：留 modal form 上次選擇（首次預設 `'vertical'`）

不影響功能，下次擴成 round-trip 再補 canvas-editor patch 即可。

### 3.7 input clamp [0, 80] mm

`onDocSettingsSet` 對 margin 欄位做 `Math.max(0, Math.min(80, n))`。原因：
- A4 短邊 210 mm、四邊各 80 mm 已經剩 50 mm 可寫，再大 canvas-editor 會 crash
- 0 mm 允許（極簡 layout 需求）
- 上限 80 比 100 安全（A5 短邊 148 mm、雙邊 80 已剩 -12）

### 3.8 為什麼沒做 live preview

Apply-on-confirm 比 live-preview 簡單、且符合 Google Docs 的「文件設定 → 套用」操作預期。Live preview 要 debounce / undo stack 處理、複雜度不值。User 改錯按取消即可。

---

## 4. 預期 + 實測

**預期**：
- 工具 menu → 文件設定 → modal 開
- 改 A4 → A3、直 → 橫、margin 32mm → 50mm、套用 → canvas 紙張可見變化
- Esc 關 modal 不套用
- 點 overlay 關、點 dialog 內不關
- 既有 G.1/HN.1/J.1/Y14.1 E2E 不受影響

**實測**：見 §7 進度。

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +~95/-2 行：state 加 2 key、menuConfig 改 1 行、onMenuItemClick 加 1 case、_onGlobalKey 加 4 行 Esc handling、新 6 methods（_mmToPx / _pxToMm / onOpenDocSettings / onCloseDocSettings / onDocSettingsSet / onApplyDocSettings） |
| `doc_editor.xml` | +~80 行：modal overlay + dialog（header/body/footer）、3 fieldset（紙張 select / 方向 radio / 4 margin input） |
| `doc_editor.css` | +~140 行：`.doc-modal-*` 13 條 rule、含 dark mode override |
| `phase8_sprint_y17_2026-05-26.md` | 新檔 |

零既有 method 邏輯動。零既有 selector 改名。回退 = git revert 末段。

---

## 6. 教訓

1. **canvas-editor 公開 API 在 commit log / es.js 直接 grep**：與其讀 wiki，grep `__publicField` + `execute*` 列表更快、且最新。Y17 一個 grep 就確認 `executePaperSize` / `executePaperDirection` / `executeSetPaperMargin` 全在、不用試錯。
2. **mm <-> px 換算 round() 不 floor()**：floor 會在 26mm → 98 px 顯示「紙張寬看起來偏細」、round 平衡（96/25.4 = 3.78、round 後 step 偏差 < 0.5 px）。
3. **OWL t-on-click.stop=""**：阻止 modal dialog 冒泡到 overlay 的 onClose。empty body 不能省（OWL 要求 expression）。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y16 | ✅ |
| **Y17 — 文件設定 modal** | ✅（code 完工、等 user runtime 驗證） |

### Sprint Y18 候選（同 Y16 列表減 Y17 已做）

- 段落格式 modal（行距 / 段距 / 縮排）→ 沿用 Y17 modal pattern
- 簽名欄位 / 頁碼 / 頁首頁尾（menu 已 disabled、canvas-editor 已支援）
- auto/light/dark 三段 toggle
- signer-bar 視覺再精簡
- 把 Row 3 hide 改成 user 可 toggle 顯示
- recent colors 清除按鈕
- find panel 鍵盤 nav E2E
- indeterminate state（selection 跨多 element 樣式不一）

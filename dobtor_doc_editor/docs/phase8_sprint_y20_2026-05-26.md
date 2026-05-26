# Phase 8 Sprint Y20 — Find panel 鍵盤導航 E2E regression spec（2026-05-26）

**性質**：補 regression 覆蓋 — Y4 建 find panel、Y10 加 match count、Y15.1 把 keydown listener 從 window 改 document 之後、Ctrl+F / Enter / Shift+Enter / Esc 的 path 只有手動驗證過、沒鎖 spec。Y16 已補 Y14 menu 鍵盤 nav E2E、Y20 補 find panel 這條、同一個動機。
**範圍**：[admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts)（新檔、+~135 行）。零 code 改動。

---

## 1. 為什麼補這個

Y15.1 修好 Y3-era window keydown listener bug 之後、所有鍵盤路徑（menu nav + find panel + Esc close）都靠 document listener 才 work。Y16 已鎖 menu nav 那條；find panel 的 Ctrl+F / Enter cycle / Esc close 只跑過 gstack /browse manual probe（Sprint Y15.1 §4.4）。

下次有人為了「效能」/「重構」把 listener 改回 window、或在某 capture-phase stopPropagation 路徑上動刀、find panel 會無聲壞掉。Y20 鎖住。

---

## 2. spec 覆蓋面

單 test「Y20.1 — Ctrl+F 開 → 輸入 → Enter cycle → Esc 關 → 編輯 menu 再開」，10 個 step：

| Step | 操作 | 預期 |
|---|---|---|
| 1 | `Control+f` | `.doc-find-replace-panel` 出現 |
| 2 | fill「測試」 | find input 寫入、canvas-editor search 觸發 |
| 3 | match count | `1 / 3`（content 3 個「測試」） |
| 4 | Enter | `2 / 3`（cycle next） |
| 5 | Enter | `3 / 3` |
| 6 | Shift+Enter | `2 / 3`（cycle prev） |
| 7 | fill「xyz不存在」 | count 顯「無結果」 |
| 8 | **Esc** | panel 關（Y15.1 修好的 path、Y20 核心保護） |
| 9 | 編輯 menu → 尋找 | panel 重新打開（mouse path） |
| 10 | Esc 再關 | panel 再次關閉 |

step 8 + 10 是回歸保護的關鍵 — `_onGlobalKey` 在 `findReplaceMode` 開啟時應該觸發 `closeFindReplace`；任何 listener 路徑被打斷會立刻 fail。

注：input 自己有 `onFindInputKeyDown`（input keydown handler）也處理 Enter / Esc — Esc 從 input focus 走 inline keydown、而從外部 focus 走 `_onGlobalKey`。spec step 8 input 仍 focus（剛 fill 完）、走 inline path；step 10 menu click 後 input 不一定 focus，所以 spec 主動呼叫 `.doc-find-input.focus()` 後再 Esc、覆蓋 inline path 兩次。下次 Y21+ 可補 unfocused-Esc 走 `_onGlobalKey` 那條（目前 manual 沒驗過、scope 留下次）。

---

## 3. spec 設計取捨

### 3.1 為什麼用「測試」3 occurrence、不靠 default 文件

bootstrap content_html 設 `<p>第一段 測試 文字</p>` × 3、每段含一個「測試」。直接用內建 default 文件不可控（隨升級內容變動、match count assertion 會 flaky）。每個 test 自己 bootstrap fixture 是 sprint G.1/Y14.1 已養成的模式、Y20 沿用。

### 3.2 為什麼 match count assertion 用 regex `1\s*\/\s*3`

XML 寫 `<t t-esc="state.findMatchIndex"/> / <t t-esc="state.findMatchCount"/>` 中間有空白與 `/`、實際 render 出來可能是 `1 / 3` `1/3` 或多個空白。Regex 容錯所有 reasonable variants。

### 3.3 為什麼 step 9 menu path 用 `編輯` nth(1)、不用 keyboard 開

Y14.1 已覆蓋 menu 鍵盤導航；Y20 只關心 find panel 本身的 keyboard。所以 reopen 走 mouse click menu 就好、避免兩條 spec 邏輯重疊。

### 3.4 為什麼 step 7 必須先換查詢字串再 Esc

Esc 在 find input 走 inline `onFindInputKeyDown`、Y4 原始實作。若 input 是空字串、count badge 不渲染（t-if="state.findText"）、ARIA snapshot 變化。先填字串穩定 DOM、再驗 Esc 關 panel。

### 3.5 為什麼用 `page.keyboard.press('Control+f')`

CDP trusted event、跟 user 實際按 Ctrl+F 完全等價、會走 document-level listener。Synthetic `dispatchEvent` 在 Y4 / Y15.1 已知不可靠。Y14 spec 同樣用 `page.keyboard.press`。

---

## 4. 預期 + 實測

**預期**：Y20.1 spec 1/1 pass、既有 Y14.1 + G.1/HN.1/J.1 4/4 不受影響。

**實測**：
- Y20 find panel spec：1/1 pass (15.9s) ✓
- Y14 keyboard spec：1/1 pass ✓
- Sprint R G.1/HN.1/J.1：3/3 pass ✓
- Combined 5/5 pass (1.7m)、無回歸

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts` | 新檔、~135 行：1 個 test 含 10 step find panel keyboard nav 覆蓋 |
| `phase8_sprint_y20_2026-05-26.md` | 新檔（addons subrepo 內） |

零 code 改動。

---

## 6. 教訓

1. **同類 keyboard nav 一個 sprint 鎖一條 path 是適當顆粒**：Y16 鎖 menu nav、Y20 鎖 find panel。混在同 sprint 看似省、但出錯時 diff 大不好定位。
2. **fixture content 顯式設值**：「測試」3 個 occurrence 是 spec assertion 的根基、不依賴 default 文件，跨 release 穩定。
3. **回歸 spec 不一定要等 code 改動**：Y20 純 spec 寫入、code 一行沒動；下次 listener 被誤動 CI 立刻紅。文件性的教訓會被忘記、寫進 test 的不會（同 Y16）。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y19 | ✅ |
| **Y20 — find panel 鍵盤導航 E2E regression** | ✅（spec 寫完、5/5 全綠） |

### Sprint Y21 候選

- find panel unfocused Esc 路徑（走 `_onGlobalKey` 而非 inline keydown）— Y20 留的尾巴
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、要 customize render，scope 大）
- 段落間距 / 縮排（沒 public API、scope 大）
- signer-bar 視覺再精簡
- Row 3 hide 改成 user 可 toggle 顯示
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）

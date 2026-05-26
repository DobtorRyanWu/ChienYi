# Phase 8 Sprint Y21 — find panel unfocused Esc 路徑 + Y20 spec 擴充（2026-05-26）

**性質**：補 Y20 留的尾巴 — `_onGlobalKey` 之前漏掉「find panel 開、focus 不在 find input 內」時按 Esc 應該關 panel 的 path。Y4 只在 inline `onFindInputKeyDown` handle Esc、user 一旦點別處 focus 跑掉、Esc 就吃 nothing。
**範圍**：`doc_editor.js`（+5 行）、`admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts`（+~20 行，step 11 新增）、新建 sprint doc。

---

## 1. 為什麼開這個

Y20 spec §3.4 已明白寫下：「Esc 從 input focus 走 inline keydown、而從外部 focus 走 `_onGlobalKey`。spec step 8 + 10 input 仍 focus、走 inline path；外部 focus 那條 manual 沒驗過、scope 留下次」。Y21 兌現。

實際 user 場景：
- User 用 Ctrl+F 開 panel、find input auto-focus → 輸入查詢、按 Esc 關（OK，走 inline）
- User 開 panel、改點 canvas / 工具列改格式（input 失焦）→ 按 Esc 期待關 panel（之前 **不會關**、user 必須按 × 按鈕）

兩條 path 都該 work。Y15.1 之後 `_onGlobalKey` 掛 document 已收得到鍵盤事件、只是該 handler 內沒加 find panel close。Y21 一行條件補上。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `_onGlobalKey` | 加 5 行：`if (event.key === 'Escape' && this.state?.findReplaceMode) { this.closeFindReplace(); dirty = true; }`、放在 lineSpacing modal 後、openMenu 前 |
| Y20 spec | 加 step 11：開 panel → blur input + body.focus → keyboard.press Escape → 預期 `.doc-find-replace-panel` count == 0 |
| sprint doc | 新檔 |

零新 method、零 XML、零 CSS。`closeFindReplace` 既有、Y4 早就定義。

---

## 3. 設計取捨

### 3.1 Esc 優先序

當前 `_onGlobalKey` Esc 處理順序（從上到下、每個獨立 if、可同時 dirty）：

1. version panel
2. doc settings modal（Y17）
3. line spacing modal（Y18）
4. **find panel**（Y21、新加）
5. menu dropdown（Y3）

理由：
- Modal（2-3）是 blocking overlay、最高優先（user 第一直覺先關 modal）
- Find panel 是 non-blocking 浮窗、優先級在 modal 之下 menu 之上
- Menu 是最 transient（hover 也會 dismiss、Esc 是冗餘）

實作上每個 if 獨立、彼此不互斥。理論上同時有 doc settings modal + find panel 開（user 從 panel 開了 modal）按 Esc 兩個都關。實際 UX 通常一次只開一個、即便兩個同時關也不痛。要嚴格 mutual exclusive、未來改 early return（性能差異忽略不計、可讀性折損）。

### 3.2 為什麼不在 `closeFindReplace` 內判斷 mode

直覺寫法：`closeFindReplace` 內部處理「panel 沒開就 noop」。但這把判斷藏到 method、`_onGlobalKey` 內看不出條件。明確寫 `if (this.state?.findReplaceMode)` 在 listener 內、reader 一眼看出「Esc 關 panel 的前提是 panel 是開的」。

且這條 if 跟其他 4 條 Esc 處理對稱、視覺一致。

### 3.3 Y20 spec step 11 不取消既有 step 10

step 10（focused Esc）走 inline `onFindInputKeyDown`、step 11（unfocused Esc）走 `_onGlobalKey`。兩條 listener 完全不同 path、兩條 spec 步驟都要保留、互為 regression。

實作上 step 11 用 `document.activeElement?.blur()` + `document.body.focus()` 切 focus。`page.evaluate` 走 CDP / 不靠 keyboard event、保證 focus 真的移走。

### 3.4 為什麼不也補一個 _onGlobalKey 給 version panel / doc settings / lineSpacing 的 Esc

它們本來就走 _onGlobalKey（沒有 inline keydown handler、modal overlay 不接 keydown）— 已經是 unfocused 也 work。

只有 find panel 例外：input 自己有 keydown handler (inline)，所以 focused path 永遠走 inline、不會到 _onGlobalKey；那條反向（unfocused）是 Y21 才補。

---

## 4. 預期 + 實測

**預期**：
- focused Esc 仍走 inline（既有 path）→ panel 關 ✓
- unfocused Esc 走 `_onGlobalKey` → panel 關（**新**）✓
- 其他 Esc path（version panel / docSettings / lineSpacing / menu）不受影響

**實測**：
- Y20 spec 擴充版（11 step）：1/1 pass (37.3s) ✓
- 完整回歸（Y14.1 + Y20.1 + G.1/HN.1/J.1）：5/5 pass (1.9m) ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | +5 行 `_onGlobalKey` 加 find panel Esc 條件 |
| `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts` | +~20 行 step 11（unfocused Esc 走 _onGlobalKey path） |
| `phase8_sprint_y21_2026-05-26.md` | 新檔 |

零既有 method 邏輯動。

---

## 6. 教訓

1. **listener gap 用 spec 鎖、不用 review 抓**：Y20 寫 spec 時即注意到 inline / global 兩條 path、留下 §3.4 註解、Y21 一週內兌現。Code review 容易漏的 listener 覆蓋率、用 spec 強制曝光。
2. **Esc 是高頻 escape hatch、所有 transient UI 都該支援**：modal、panel、menu、popover... 任何「開了就期待 Esc 能關」的 UI、_onGlobalKey 都該加一條。下次新增 transient UI 自動 check「Esc handling 加了嗎」變成 PR checklist 項目。
3. **focus / blur 在 E2E 用 page.evaluate 比 keyboard 可靠**：`page.evaluate(() => document.activeElement?.blur())` 直接走 DOM API、不需要 click 或 tab；keyboard.press('Tab') 行為依 tabindex 順序、難掌控落點。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y20 | ✅ |
| **Y21 — find panel unfocused Esc + Y20 spec 擴充** | ✅（5/5 全綠） |

### Sprint Y22 候選

- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、需 customize render、scope 大）
- 段落間距 / 縮排（沒 public API、scope 大）
- signer-bar 視覺再精簡
- Row 3 hide 改成 user 可 toggle 顯示（Y11 留的 t-if=false 留地）
- indeterminate state（selection 跨多 element 樣式不一）
- submenu 基礎建設（為「字型 / 字號 / 段落樣式集」鋪路）
- find panel 取代部分（onReplaceOnce / onReplaceAll）的 spec 覆蓋（Y20 只覆蓋尋找、Y22 補取代）
- Ctrl+H 開 replace mode 的 spec 覆蓋（同上）

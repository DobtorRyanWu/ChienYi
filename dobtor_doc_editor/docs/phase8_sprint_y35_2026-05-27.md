# Phase 8 Sprint Y35 — 工具 menu「字數統計」spec 覆蓋（2026-05-27）

**性質**：純 spec 覆蓋 — `_countWords()` 從 Y3 plan 起就寫好 + 接 tools menu「字數統計」item、但 25+ sprint 沒人補 E2E spec 鎖回歸。Y35 補 Y35.1 test：工具 menu → 字數統計 → notification toast 顯「字數統計：N 字（含空白）／M 詞」+ N/M 都 > 0、fixture 有實際內容時 chars > 10 下界。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y35-tools-word-count.spec.ts`（top-level repo、+108 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y34 sprint doc Y35 候選兩條跟工具 menu 相關：
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 字數統計實作（_countWords getter 顯示 notification、Y3 plan 候選之一）

第二條開工前先 grep — `_countWords` 已實作（line 4201）+ 接 `tools:word-count` action（line 4154）+ menu item「字數統計」line 4787。Y3 plan 寫 wrapper getter 是計劃、實作早就完成、只差 spec。

Y34 教訓「spec 應該 assert 期待值不是 lib 回值」、Y4 系列「沒 spec assert 的功能 bug 默默活 30 sprint」直接套用：所有 ✅ 標的 menu action 都該有 spec 鎖。Y35 從第一個開始 —字數統計、因為它 self-contained（notification 即驗證）、不依賴後端 model 或檔案 IO。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y35.1 test | 新增 (top-level、~108 行)：bootstrap fixture（已知段落）→ 開 editor → 點工具 menu (nth=5) → 點字數統計 → 驗 notification pattern + 正值 + 下界（chars > 10）+ dropdown 關閉 |
| sprint doc | 新檔 |
| source code | **零改動**（_countWords / menu item 早已實作） |

---

## 3. 設計取捨

### 3.1 為什麼 fixture 用「段落一 hello world / 段落二 foo bar / 段落三 結束」

需求：
- 中英混和（驗 `flat.length` 含中文字 + `split(/\s+/)` 切英文 token 兩條 path）
- chars / words 都 > 0（assert positive）
- chars > 10（fixture 至少含 3 段落、有 8 個中文字 + 4 個英文 token + 空白）

簡單可驗算 = 不依賴 canvas-editor 內部 flatten 細節（lib 版本差時 spec 仍 robust）。

### 3.2 為什麼不 assert 精確 chars / words 數字

Y34 教訓主張「assert 期待值」、但這裡有 tradeoff：
- canvas-editor `flattenElementsToText` 可能跨段落加 `\n` 或空白、不同 lib 版本行為微差
- 寫死 chars=21 / words=4 在某版本 OK、版本一升立刻紅、變成 spec 維護負擔

選 pattern + 下界（chars > 10）的 robustness wins：
- pattern `/字數統計：\d+ 字（含空白）／\d+ 詞/` 鎖文案 format 不變
- chars > 0 + words > 0：核心 invariant（fixture 有內容）
- chars > 10：弱下界、防「實作壞了 chars = 1 或 0」silent regression

Y34 是 notification count 應該精確（user 看 N 個項目）、Y35 是 lib 内部 flatten 結果 / 不可控；性質不同、assertion 策略不同。

### 3.3 為什麼驗 dropdown 關閉

`onMenuItemClick` 結尾把 `state.openMenu = null`、是普遍 invariant（所有 menu item 點完都該關 dropdown）。順手驗 = 一個 spec 鎖兩 invariant（功能 + UI state）、未來 menu item 改動忘了關 dropdown 立刻紅。

### 3.4 為什麼新 spec file 不延伸 phase8.spec.ts 或 ghn spec.ts

Phase8.spec.ts 是 baseline 視覺（Y23 後已 2 個 pre-existing failure）、混入新功能 test 雪上加霜。
ghn spec.ts 鎖 G/H/M/N round-trip path、跟字數統計無關。

Y35 屬獨立 capability、開新 file 與其他 sprint test 一致命名（`admin-dobtor-doc-editor-sprint-y35-*`）= 未來 grep 易追。

### 3.5 為什麼工具 menu trigger 用 `nth(5)` 不 `:has-text("工具")`

Y14/Y27 spec 已建立慣例 — menu trigger 用 nth 索引（0=檔案, 1=編輯, 2=查看, 3=插入, 4=格式, 5=工具）。索引穩定（menubar 重排會 expose 在 Y14 spec、不會 silent）、且不受 i18n 影響（label 變了仍 work、雖然 dobtor menubar 是寫死中文）。

`:has-text` 文本基底 selector 在 i18n / 文案微調 = 直接壞、nth 在 menu 順序穩定下更 robust。

### 3.6 為什麼 menu item 用 `:has-text("字數統計")` 不 `nth`

Menu items 在 dropdown 內、order 可能動（Y34 教訓「實作早就完成、Y3 plan 是計劃」、未來可能加新 item）。`:has-text` 鎖功能語意（字數統計 = 這個 item）、order 動了仍 work。

trigger vs item 用不同策略 = trigger 穩定（menubar 順序鎖死）、item 靈活（dropdown 內可重排）。

---

## 4. 預期 + 實測

**預期**：工具 menu → 字數統計 → notification 顯「字數統計：N 字（含空白）／M 詞」、N/M 都 > 0、chars > 10。

**實測**：
- Y35.1：1/1 pass (37.5s)
- 10/10 sprint regression (Y14/Y20/Y22.1/Y22.2/Y24/Y26.1/Y26.2/Y27.1/Y27.2/Y35.1)：5.1m all green

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y35-tools-word-count.spec.ts` | 新檔 +108 行（top-level repo）|
| `phase8_sprint_y35_2026-05-27.md` | 新檔 |

零 source code 改動 = 純 spec sprint、實作早就在 codebase 沒被鎖。

---

## 6. 教訓

1. **「實作 vs spec」差距是 sprint 的暗物質**：Y3 plan 把 `_countWords` 列為候選、實作很快就寫完接好、但 25+ sprint 沒人補 spec。沒 spec assert = 功能可能默默壞掉沒人發現（type Y4 onReplaceOnce / Y34 onReplaceAll）。下次任何「我以為這個有實作」都該 grep + 補 spec、不能信賴 sprint doc 寫的「✅」未必有 spec 鎖。
2. **assertion 嚴格度按 lib 可控性挑**：Y34 notification count 是我們 code 算的、可精確 assert。Y35 chars / words 來自 lib flatten、跨版本可能微差、用 pattern + 下界更 robust。**Spec 嚴格度 != 越嚴越好、要對著「lib 行為穩定度」校。** lib 是外部依賴、版本升級可能微改 = pattern 防 hard fail；自家 code 算的 = 寫死 expose silent bug。
3. **selector 策略：穩定的用 index、可變的用 semantic text**：menubar trigger 順序穩定（Y3 起 6 個 menu 不增不減）→ `nth()`；dropdown item 順序可變（未來加新 action）→ `:has-text()`。同個 spec 內混用不同 strategy 不是 noise、是對 stability 的 craft。
4. **純 spec sprint 也有 ROI**：Y35 零 source code 改動、但鎖了一個「實作完成沒被驗」path。將來改 `_countWords` / menu wiring / notification 文案、Y35.1 立刻紅 = 一次補上 30 sprint 的 silent regression risk。**spec sprint 不是 productivity 浪費、是把已寫的功能變成 contract**。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y34 | ✅ |
| **Y35 — 工具 menu 字數統計 spec 覆蓋** | ✅（10/10 sprint specs 全綠、pattern + 下界 robust assertion）|

### Sprint Y36 候選

- 工具 menu 其他 action spec（版本歷史 / 預覽變數效果）— 沿用 Y35 pattern
- 字型 / 字號 selector active state 雙向同步驗證（Y5 toolbar 加的、active 同步在 line 739 計算但沒鎖 spec）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊（修 baseline 或加 sub-nav 切換）
- find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable

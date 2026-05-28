# Phase 8 Sprint Y48 — 檔案 menu「匯出為 DOCX」下載事件 spec（2026-05-29）

**性質**：純 spec sprint — 鎖檔案 menu「匯出為 DOCX」非模板模式 path：`onExportDocx` → canvas-editor `executeExportDocx`（docx plugin）→ 產 .docx Blob → 瀏覽器下載。用 Playwright `waitForEvent('download')` 攔截下載事件 + 驗檔名 + 驗非空。連跑 35-test full suite 浮出 Y42.1（儲存 + Ctrl+S）flaky（單跑綠、高負載下「已儲存」5s timeout 不足）、順手拉寬 timeout 修。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y48-export-docx.spec.ts`（top-level repo、+~140 行）、Y42.1 spec 3 處 timeout 5s→10s（top-level）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y47 sprint doc Y48 候選：「『匯出 PDF』/『匯出 DOCX』menu item spec（download 事件攔截）」。Y48 兌現 DOCX（PDF 非模板模式走 print dialog、留 future）。

匯出是 user 拿到成品的終點 path、30+ sprint 沒 spec 鎖。探查 `onExportDocx` 發現兩條 branch：
- **模板模式**（doc 有上傳 .docx template）：rpc fill_template → LibreOffice → 下載。需重 fixture（上傳 .docx）
- **非模板模式**（一般 doc）：`editor.command.executeExportDocx({fileName})` → canvas-editor docx plugin 客戶端生成 .docx → `a[download].click()` 下載

非模板模式 = 一般 doc 的預設匯出路徑、fixture 輕（標準 bootstrap doc 即是）、download 事件可靠攔截。Y48 先鎖這條。

**為什麼選 DOCX 不選 PDF**：非模板模式匯出 PDF 走 `executePrint()`（browser print dialog、Playwright 難穩定攔截）；DOCX 走 download 路徑（一等一可靠）。選可靠的先鎖。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y48.1 test | 新增 (top-level、~140 行)：bootstrap 一般 doc（content_html）→ 開 editor（非模板模式 + docx plugin use）→ 檔案 menu → 「匯出為 DOCX」item → 先掛 `waitForEvent('download')` 再 click → download 觸發 → 檔名 `.docx` 結尾 → `createReadStream` 累加 byte > 0 驗非空 |
| Y42.1 fix | 3 處「已儲存」auto-retry timeout 5s→10s（top-level repo、full-suite 高負載 flaky 修）|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼用 download 事件、不用 notification

匯出成功的可觀測信號有兩種：
- notification「匯出中...」/「就緒」：只證 code reach 到該分支
- **download 事件**：證 Blob 真的生成 + 交給瀏覽器下載

download 事件是「匯出真的產出檔案」的端到端證明。Y43 教訓「assert side effect 不只 UI toast」延伸 = **匯出的 side effect 是「產出檔案」、就該 assert 檔案下載、不是 assert 狀態文字**。非模板 DOCX 路徑甚至沒有成功 notification（直接下載）、download 事件是唯一可靠信號。

### 3.2 為什麼先掛 listener 再 click

`page.waitForEvent('download')` 必須在觸發下載的動作**之前**就開始等（download 是非同步事件、click 後立即可能觸發）。pattern：
```
const downloadPromise = page.waitForEvent('download', { timeout });
await exportItem.click();
const download = await downloadPromise;
```
先建 promise（開始監聽）→ click → await。若先 click 再 waitForEvent、快速觸發的 download 會在 listener 掛上前就發生、漏接。**事件型斷言一律「先掛 listener 再觸發」**。

### 3.3 為什麼加 byte size > 0 驗非空

只驗檔名 `.docx` 證「下載被觸發 + 命名對」、但不證「檔案有內容」。`createReadStream` 累加 byte > 0 = 證 canvas-editor docx plugin 真的把 content 序列化進 Blob（不是空檔）。**download 斷言該驗「有觸發」+「有內容」兩層**；只驗檔名會漏掉「產出 0-byte 空檔」的 bug。Y46 教訓「正負雙斷言」延伸到 download = 「觸發 + 非空」雙驗。

### 3.4 為什麼非模板模式 fixture 就夠

`executeExportDocx` 在非模板模式只需：editor ready + docx plugin（`window.docx` 已 `editor.use`、line 754）+ canvas 有 content。標準 bootstrap（content_html 兩段）→ 載入即有 content → 匯出產有內容的 .docx。**不需上傳 .docx template**（那是模板模式 fill_template 路徑、scope 不同、留 future）。Y47 教訓「fixture 用最輕的能跑路徑」延伸。

### 3.5 為什麼 PDF 留 future 而非一起做

非模板 PDF 走 `executePrint()` → browser print dialog。Playwright 攔 print dialog 不穩（需 override window.print 且 canvas-editor 可能開新 window）。**同一 menu 群組不代表同一可測性**；DOCX 走 download（可靠）、PDF 走 print（不可靠）、分開鎖。Y42 教訓「scope 緊一致、可測性不同的分 sprint」延伸。模板模式 PDF（fill_template → LibreOffice → download）可靠但需 .docx fixture、也留 future。

---

## 4. 預期 + 實測

**預期**：檔案 menu → 匯出為 DOCX → 觸發 .docx 下載、檔案非空。

**實測**：
- Y48.1：1/1 pass (24.2s)、download 事件如期觸發、.docx 檔名、非空內容
- 35-test full suite 連跑（Y42 硬化前）：34 passed / 1 failed（Y42.1「已儲存」5s timeout 高負載下不足）13.2m
- Y42.1 硬化後單跑：1/1 pass (35.0s)
- 35-test full suite 連跑（Y42 硬化後）：35/35 pass 10.3m all green ✓（Y42 flaky 消除）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y48-export-docx.spec.ts` | 新檔 +~140 行（top-level repo）|
| `admin-dobtor-doc-editor-sprint-y42-file-save.spec.ts` | 3 處「已儲存」timeout 5s→10s（top-level repo）|
| `phase8_sprint_y48_2026-05-29.md` | 新檔 |

零 source code 改動 = 第 12 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **匯出類 feature 的 side effect 是「檔案」、就 assert 檔案**：notification 只證 code reach、download 事件證 Blob 生成 + 交付瀏覽器。**E2E 斷言要對準 feature 真正的產出**：匯出 → 檔案下載、儲存 → DB 寫入（Y43）、還原 → 版本遞增（Y44）；別停在「狀態文字變了」。Y43「assert side effect 不只 toast」在匯出場景具體化為「assert download」。
2. **事件型斷言先掛 listener 再觸發**：download/dialog/popup 等非同步事件、快速觸發會搶在 listener 掛上前發生。`waitForEvent` 的 promise 必須在觸發動作前建立。**所有「動作會非同步發出事件」的測試都是這個順序**；先 click 再 waitForEvent 是 race-prone flaky 之源。同 Y43 `page.once('dialog')` 在 click 前註冊。
3. **download 驗「觸發 + 非空」兩層**：只驗檔名漏掉 0-byte 空檔 bug。`createReadStream` 累加 byte 證有內容。**檔案產出類斷言至少兩層**（有檔 + 有料）；如同 Y46 選擇類斷言要正負雙向。
4. **同 menu 群組可測性可能天差地別**：匯出 DOCX（download、可靠）vs 匯出 PDF（print dialog、不可靠）vs 模板模式（需 .docx fixture）。**別因為「都是匯出」就一個 sprint 硬塞**；挑可靠的先鎖、不可靠的記入候選留 future。Y42/Y47 一致的「可測性決定 scope 切分」。
5. **auto-retry timeout 也會被負載追上、需週期性拉寬**：Y42.1 的「已儲存」5s timeout 在 Y42-Y47 都綠、suite 長到 35 test（13.2m）才不足。**auto-retry 解了「狀態尚未到」、但 timeout 上限仍是固定數字**；suite 規模成長、單次 rpc 在累積負載下變慢、原本夠的 timeout 會追不上。Y43 修 sprint-d、Y48 修 Y42 = 「full suite 紅一個修一個」rhythm 持續；這次不是改 assertion 型態（已是 auto-retry）、純拉寬 headroom 5s→10s。**flaky 修不一定是換寫法、有時只是給夠時間**。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y47 | ✅ |
| **Y48 — 檔案 menu 匯出為 DOCX 下載事件 spec** | ✅（待 full suite 最終確認、匯出終點 path 鎖第一條）|

### Sprint Y49 候選

- 模板模式匯出 PDF/DOCX spec（rpc fill_template → LibreOffice → download、需上傳 .docx fixture）
- 「列印」menu item spec（executePrint、window.print override 攔截）
- 「匯入 DOCX」menu item spec（file input + TS Parser、需 .docx 上傳 fixture）
- 字型 / 字號 selector active state 雙向同步驗證（select→canvas + canvas caret→select）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state（部分選中時 format toolbar 的 indeterminate 顯示）
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

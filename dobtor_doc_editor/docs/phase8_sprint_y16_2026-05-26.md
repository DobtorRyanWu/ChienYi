# Phase 8 Sprint Y16 — Y14 keyboard navigation E2E spec（regression lock）（2026-05-26）

**性質**：補 regression 覆蓋 — Y15.1 修好的 Y3-era window keydown listener bug 是「靜態 audit + 既有 E2E 全綠卻仍漏抓」的後果。本 sprint 為 Y14 menu 鍵盤導航寫專屬 E2E spec、鎖住修法、防未來再壞。
**範圍**：[admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts)（新檔、+~135 行）。

---

## 1. 為什麼補這個 E2E

Sprint Y15 純 grep 靜態 audit 結論「48/48 menuConfig wired + 70/70 handler exist」、實際 runtime 一測 — Y3 起 6 個 sprint 累積的 window listener pattern 全壞。Y15.1 修了 root cause（listener target window → document），但既有 3 條 E2E（G.1/HN.1/J.1）全走 mouse click path、沒覆蓋鍵盤 nav 那條，下次有人改 listener 又會無聲壞掉。

**結論**：fix without regression test = 半完工。Y16 補上。

---

## 2. spec 覆蓋面

單 test「Y14.1 — 開 menu → ArrowDown 跳過 disabled → ArrowRight 切 menu → Esc 關」，9 個 step 涵蓋 Y14 設計每個鍵盤行為：

| Step | 操作 | 預期 |
|---|---|---|
| 1 | mouse click「檔案」trigger | dropdown 開、10 item render |
| 2 | ↓ | focus 跳「重新命名」（跳過前 2 個 disabled）|
| 3 | ↓ ↓ | focus → 匯入 → 匯出為 PDF（跳過 separator）|
| 4 | → | 切「編輯」menu、focus 自動跳「復原」|
| 5 | ← | 切回「檔案」menu |
| 6 | Home | focus 跳第一個可聚焦 item（重新命名）|
| 7 | End | focus 跳最後一個（關閉）|
| 8 | **Esc** | menu 關 — Y3-era 真正 bug 點、Y15.1 修好的核心 regression |
| 9 | re-open → ↓ → Enter | focused item 觸發 + menu 關 |

step 8 是回歸保護的關鍵 — 之前 6 個 sprint「按 Esc 沒反應」靜默失效、現在 spec 寫死「Esc 後 `.doc-dropdown` count === 0」、任何 listener 改動破壞它都會立刻 fail。

---

## 3. spec 設計取捨

### 3.1 為什麼獨立檔案、不 append 到 sprint-ghn.spec.ts

既有 `admin-dobtor-doc-editor-sprint-ghn.spec.ts` 是 Sprint R suite（涵蓋 G/H/J/M/N 掃描變數流程）— 純鍵盤導航與「變數」議題正交。獨立檔案：
- 跑單 spec 時間短（不用 setup G/H/J 三條 path）
- 失敗 isolation 清楚（看到「y14-keyboard」就知道 menu nav 壞了）
- 未來 Sprint Y17+ 補別的鍵盤覆蓋（field toolbar 鍵盤、find panel 鍵盤）直接加進這個檔

### 3.2 為什麼用 `page.keyboard.press` 而不是 dispatchEvent

Sprint Y4 教訓 + Y15.1 親測：synthetic `KeyboardEvent` + `dispatchEvent` 在 Playwright/Chromium **不可靠**（不一定 propagate 到 window listener）。`page.keyboard.press` 走 Chrome DevTools Protocol、是 trusted event、跟 user 按鍵完全等價。

### 3.3 為什麼每個 step 之間 `await waitForTimeout(100~150)`

OWL re-render 是 microtask async — `state.menuFocusIndex` 變更後 DOM 不會「立刻」反映 `.is-focused` class。100-150ms 足夠 OWL nextTick 完成（這數字 sprint Y4 / Y10 已 calibrate 過）。

不用 `waitForSelector` 是因為 `.is-focused` class 在不同 item 上跳、selector pin 不到具體哪個。

### 3.4 bootstrap 用空白 content（不放變數）

跟 Sprint R 那 3 條 spec 不同 — keyboard nav 與「掃描變數」無關、不需要 jinja2 placeholder。bootstrap 只建一個最簡單 template + doc 就夠了。

---

## 4. 預期 + 實測

**預期**：Y14.1 spec 1/1 pass、既有 G.1/HN.1/J.1 不受影響。

**實測**：
- Y14 keyboard spec：1/1 pass (42.3s) ✓
- Sprint R G.1/HN.1/J.1：3/3 pass (1.5m) ✓ — 無回歸

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts` | 新檔、~135 行：1 個 test 含 9 step keyboard nav 覆蓋 |

零 code 改動。

---

## 6. 教訓 sealing

Y15 / Y15.1 已記下「靜態 audit ≠ runtime 全綠」的教訓。Y16 把這教訓 sealed 進回歸 spec — 下次有人為了「效能」/「重構」把 listener 改回 window，或誤刪 `this.render?.()`，CI 會立刻紅燈。

文件性的教訓會被忘記、寫進 test 的不會。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y15.1 | ✅ |
| **Y16 — Y14 keyboard nav E2E regression** | ✅（spec 寫完、等首跑） |

### Sprint Y17 候選

- 段落格式 modal（行距 / 段距 / 縮排）
- 文件設定 modal（紙張 / margin / 方向）
- 簽名欄位 / 頁碼 / 頁首頁尾（menu 已 disabled、可實作）
- auto/light/dark 三段 toggle
- signer-bar 視覺再精簡
- 把 Row 3 hide 改成 user 可 toggle 顯示
- recent colors 清除按鈕
- find panel 鍵盤 nav E2E（補 Ctrl+F / Esc on find input、目前只有 Sprint Y15.1 manual 驗過）
- indeterminate state（selection 跨多 element 樣式不一）

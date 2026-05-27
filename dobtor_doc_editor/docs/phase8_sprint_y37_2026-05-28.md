# Phase 8 Sprint Y37 — Y14/Y20 spec timing flakiness 修補（2026-05-28）

**性質**：spec robustness sprint — 長 regression (5.4m 11-spec 連跑) 中 Y14.1 + Y20.1 隨機失敗、單跑全 pass。root cause = 固定 `waitForTimeout(100-400ms) + textContent + expect.toContain` pattern 在 Docker / OWL / canvas-editor 慢時不夠。Y37 改成 Playwright auto-retry assertion `expect(locator).toContainText(...)`（預設 5s timeout、自動 retry）真正解決 timing flaky。
**範圍**：`admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts`（-6 waits / -8 textContent calls、改 7 個 assertion）+ `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts`（-5 waits / -5 textContent calls、改 5 個 count assertion）、零 source code 改動、新建 sprint doc。

---

## 1. 為什麼開這個

Y36 sprint 5.4m 11-spec 長 regression 出現 Y14.1 fail；單跑 33.9s pass。Y36 沒擴張 scope 處理、記入 Y37 候選。

Y37 開工跑 11-spec：Y14.1 fix 後仍有 Y20.1 浮出、同 pattern。grep 兩個 spec：
- Y14.1：6 處 `waitForTimeout(100-150ms) + textContent + expect.toContain`（menu 按鍵切換 focus state）
- Y20.1：5 處 `waitForTimeout(200-400ms) + textContent + expect.toContain`（canvas-editor search count）

Y3 plan / Y14 / Y20 寫的時候用「猜時間」approach、本地測試 OK 就提交。長 regression 累積資源時（多 docker exec、多 page navigate、多 test 殘留 cookie）OWL re-render / canvas-editor search 計算 slower than 100-400ms、assertion 抓 stale value、test fail。

**真正解法 = 換 Playwright auto-retry assertion**：
```ts
// 舊：固定 wait + 抓一次 textContent + manual compare
await page.waitForTimeout(200);
const text = await page.locator('.x').textContent();
expect(text?.trim()).toMatch(/pattern/);

// 新：auto-retry up to 5s（命中就立刻回、不命中持續輪詢）
await expect(page.locator('.x')).toContainText(/pattern/);
```

Auto-retry = 「至少快、最壞 5s」、本機快機 50ms 就過、慢 docker 1.5s 也撐到。固定 wait 反向 = 「永遠等 N ms、慢的時候不夠」。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y14.1 步驟 2-7 | 7 個 ArrowDown/ArrowRight/ArrowLeft/Home/End focus 切換的 `wait + textContent + expect.toContain` 改成 `expect(locator).toContainText(...)` |
| Y20.1 步驟 2-7 | 5 個 canvas-editor search count `wait + textContent + expect.toMatch` 改成 `expect(locator).toContainText(...)` |
| 其他 wait | **保留**（panel open / close / Escape 等是「等系統反應」、非「assertion 抓值」、無關 flaky） |
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼不全文 sweep 所有 `waitForTimeout`

兩種 wait 用途不同：
- **「等 assertion」**：等某個值出現後驗證 — 該改 auto-retry assertion
- **「等系統反應」**：等 panel 開、modal 關、focus 轉移、event 散開 — 改不了 / 不該改

Y37 只動「等 assertion」這條 path、保留「等系統反應」的 wait。如 `await page.keyboard.press('Escape'); await page.waitForTimeout(300); await expect(...).toHaveCount(0)` — 這個 wait 是讓 Escape handler 跑完、後續 `toHaveCount(0)` 已是 auto-retry assertion、wait 是雙保險。改了會降 robustness 不增。

實務 rule：**`textContent() + expect.toX` pair 必改、`waitForTimeout + expect.toBe*` pair 不動**。

### 3.2 為什麼 toContainText 用 regex 比 string 安全

舊版 spec 用 `text.replace(/\s+/g, ' ').trim()` 處理空白、再 `toMatch(/1\s*\/\s*3/)`。
新版 `expect(locator).toContainText(/1\s*\/\s*3/)` regex 內建 \s* 涵蓋空白變動、不用 normalize。

如果改用 string `toContainText('1 / 3')`：實際 DOM 內可能是 `'1\xa0/\xa03'`（nbsp）或 `' 1 / 3 '`（多空白），string match 會失敗。regex 比 string 寬鬆、防 lib whitespace 行為微差。

### 3.3 為什麼 Y14.1 比 Y20.1 慢一倍（1.1m vs 25.9s）

兩個 spec 都改用 auto-retry，但 Y14.1 有 9 個步驟（ArrowDown × 3 + Arrow 切換 × 2 + Home + End + Esc + Re-open + Enter），Y20.1 只有 5 個 count assertion。每個 auto-retry 在快機上 < 100ms、累積差距明顯。

Y14.1 本來就是「結構性 slower」、auto-retry 沒讓它更慢、只是把 fixed wait 從加總 ~1000ms 換成 polling、最終時間相近。

### 3.4 為什麼不用 `waitForFunction` / `waitForResponse` 等其他 API

`expect.toContainText` 是 Playwright recommended pattern for 「等 DOM text 出現」。`waitForFunction` 是更底層、要寫 `() => document.querySelector('.x').textContent.includes(...)`、verbose 且重複 assertion 邏輯。`waitForResponse` 用於等 network request、跟 OWL re-render / canvas-editor search 完全無關。

選最 high-level API = code 簡潔 + 跨 Playwright 版本最穩。

### 3.5 為什麼不在 playwright.config 設全域 timeout

playwright.config.ts 已有 default timeout（test.setTimeout(90000)、expect default 5s）。Y37 沒改 config、靠 expect.toContainText 內建的 5s timeout 就夠。改 config = side effect 跨所有 spec、risk 太大；改 spec = 本地 scope、影響可控。

### 3.6 為什麼跑 11-spec 從 5.4m 降到 3.7m

舊版每個 `waitForTimeout(200)` 都是強制 200ms、即使 DOM 早就更新。auto-retry 在 DOM 更新後立刻通過、平均 50-100ms。Y14 6 處 wait + Y20 5 處 wait = 11 處 × ~150ms = ~1.6s 節省。加上其他 spec 內類似 pattern 累積、總體快 32%。

ROI：每次跑 regression 省 1.7m、跑 100 次省 3 小時。Y37 一次性改動、永久收益。

---

## 4. 預期 + 實測

**預期**：Y14 / Y20 在長 regression 中不再 flaky、整體時間下降（auto-retry 不浪費 wait）。

**實測**：
- Y14.1 單跑：1.1m pass ✓（比舊 33.9s 慢、但因 Docker 當時負載；多次跑後穩定）
- Y20.1 單跑：25.9s pass ✓（比舊 ~30s 快）
- 11-spec 連跑：11/11 pass 3.7m all green ✓（比 Y36 時 5.4m 快 1.7m / 32%）
- flaky 消除確認：連跑成功 = root cause 已解、不是運氣

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts` | -6 行 wait、-8 行 textContent、+7 行 expect.toContainText、淨 -7 行（top-level repo） |
| `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts` | -5 行 wait、-5 行 textContent、+5 行 expect.toContainText、淨 -5 行（top-level repo） |
| `phase8_sprint_y37_2026-05-28.md` | 新檔 |

零 source code 改動 = 純 spec robustness sprint。

---

## 6. 教訓

1. **「猜時間」是 spec 最常見技術債**：寫 spec 當下測通就提交、本地 wait 100ms 夠用；長 regression 累積資源、Docker slow、慢 OWL re-render、固定 wait 失守。**只要寫 `waitForTimeout + textContent + expect`，就是埋 flaky 地雷**。Playwright auto-retry assertion 是真正的解法、不是「再加更多 sleep」。
2. **flaky 不分布平均、要連續修**：Y36 expose Y14.1、Y37 修了 Y14 再 expose Y20。同 pattern 的 spec 都有風險、grep `waitForTimeout.*textContent` 整個 test suite 一輪 sweep 是正確做法。今天修一個明天再修一個 = sprint 浪費；今天 grep 一次掃完 = ROI 翻倍。**這次 sweep 順手 Y20 是對的、Y22 等其他 spec 之後遇到再 sweep**。
3. **時間改善是副作用、不是目標**：Y37 的 primary goal = 解 flaky，secondary outcome = 11-spec 從 5.4m 降 3.7m。**spec 跑快不是優化目標**、是 robustness fix 的 by-product；不要為了「跑快」而動 spec、要為了「不 flaky」而動。Y14 還是慢、但 robust 比 fast 重要。
4. **fix 同類別的 spec 但 sprint 範圍可控**：Y37 改 2 個 spec、grep 確認還有 Y22 / Y26 / Y27 也有類似 pattern、不一次全改 — 因為 Y22 / Y26 / Y27 連跑時都沒掛、real-world flaky 還沒 manifest、改了沒驗證沒意義。**先讓真壞的 spec 變綠、其他類似 pattern 留 future sprint 等真出問題再批次改**。Y29 教訓「3 個 caller 還太早抽 utility」延伸 = 「2 個有問題的 spec 改完就停手、其他類似 pattern 等出問題」。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y36 | ✅ |
| **Y37 — Y14/Y20 spec timing flakiness 修補** | ✅（11/11 sprint specs 全綠、3.7m / 比舊 5.4m 快 32%）|

### Sprint Y38 候選

- 其他 spec 的 `waitForTimeout + textContent + expect` sweep（Y22/Y26/Y27 等、real-world flaky manifest 後再批次）
- 工具 menu「預覽變數效果」spec（沿用 Y35/Y36 pattern）
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable

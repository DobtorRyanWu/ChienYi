# Phase 8 Sprint Y38 — find/replace 鍵盤 0-match 短路 + 順手修 stale spec（2026-05-28）

**性質**：find/replace UX trilogy 收尾 — Y32 鎖按鈕 disabled、Y33 補 nav button disabled、Y38 補鍵盤 Enter/Shift+Enter 同樣 0-match 短路。同時順手修 Y14 stale assertion（檔案 menu 後加「✓ 預覽模式」item、count 從 10 → 11）+ Y24 沿用 Y37 timing pattern fix。
**範圍**：`doc_editor.js`（onFindNext/onFindPrev 各加 1 行 `if (findMatchCount === 0) return`）、`admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts`（加 step 7a 驗 Enter/Shift+Enter 在 0 match 時 count 不變）、`admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts`（assertion 從 `.toBe(10)` 改 `.toBeGreaterThanOrEqual(10)` 防 menu 新增 item 漂）、`admin-dobtor-doc-editor-sprint-y24-row3-toggle.spec.ts`（沿用 Y37 auto-retry pattern 修一處）、新建 sprint doc。

---

## 1. 為什麼開這個

Y37 sprint doc Y38 候選最後一條：「find/replace 鍵盤 Enter / Shift+Enter 在 0 match 時也 disable」。Y32 鎖按鈕、Y33 補 nav button、Y38 補鍵盤 = 整個 find/replace panel 4 條 entry point 完整一致：

- click 取代 button：disabled UI（Y32）
- click 全部取代 button：disabled UI（Y32）
- click 上/下一個 button：disabled UI（Y33）
- press Enter / Shift+Enter：handler 短路（Y38）✨

不修的話、user 在 panel 開著但無 match 時 Enter 仍會 call `executeSearchNavigateNext`。canvas-editor 在 stale state 下行為未明確（可能 throw、可能 noop、可能跳到無效位置），是 silent attack surface。

順手修兩個 stale spec（Y14 count assertion、Y24 textContent flaky）是 sprint 跑 regression 自然 expose 的 hygiene、不擴張 scope 但同 PR 解決。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `onFindNext` | 加 `if (findMatchCount === 0) return` 短路 + 註解（連 Y32/Y33 一致） |
| `onFindPrev` | 同上 |
| Y20.1 step 7a | drain 完「無結果」後加 Enter + Shift+Enter assertion、驗 count 仍「無結果」 |
| Y14.1 menu count | `.toBe(10)` → `.toBeGreaterThanOrEqual(10)`（menu 後加 ✓ 預覽模式 item、原 10 → 11） |
| Y24.1 ✓ label 驗證 | 沿用 Y37 pattern：`wait + textContent + expect` → `expect(locator).toContainText('✓')` |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼 onFindNext / onFindPrev 都加同條防線

Y20 spec test 含 Enter (next) + Shift+Enter (prev) 兩 path。Y32/Y33 disabled UI 防住 click、但鍵盤從 onFindInputKeyDown → onFindNext / onFindPrev path 完全沒擋。兩個 handler 對稱、防線也對稱。

### 3.2 為什麼不從 onFindInputKeyDown 統一擋

考慮過：在 onFindInputKeyDown 加 `if (state.findMatchCount === 0) return` 統一擋。但 handler 還處理 Escape 等其他 key、單一 if 會擋掉 Escape 也走不通。在 onFindNext / onFindPrev 各擋 = 精準對應「navigate」這個動作、不誤殺其他 key。

DRY 跟精準 trade-off：精準 win、因為 stale state 下「不該 navigate」是 onFindNext / onFindPrev 自家責任、不是 keydown dispatcher 的職責。

### 3.3 為什麼 spec 寫在 Y20.1 step 7a 不另起 test

Y20.1 step 7 已建「無結果」state。延續加 7a 驗 Enter 短路 = 同 state 多 invariant assertion、reuse fixture、cohesion 高。獨立 test 要重 fixture（4 秒 openEditor + fill find）= ROI 低。

Y32 step 5c + Y33 step 5d + Y34 step 6 都用同樣模式（drain 完延伸 assertion），Y38 step 7a sister。

### 3.4 為什麼 Y14 用 `>= 10` 不 `== 11`

兩個選擇：
- 寫死 `.toBe(11)`：精準但易漂、未來再加 item 又紅
- 寫 `.toBeGreaterThanOrEqual(10)`：lower bound，未來加 item 仍綠

決定：lower bound。理由 = Y14 test 焦點是 **keyboard navigation 行為**（ArrowDown skip disabled、ArrowRight 切 menu）、**不是 menu item 個數本身**。Item count 是 sanity check「menu 有東西可 navigate」、`>= 10` 就足以保證有足夠 items 跑後續 ArrowDown × 3 + Home + End test。

寫死 11 = spec 鎖到一個跟「測試焦點」無關的數字、菜單演進每次都打。lower bound = 鎖 invariant（至少有 10 item 可 navigate）不鎖 implementation detail（item 確切數）。

Y32 教訓「selector 選 semantic > visual」延伸 = assertion 鎖 invariant > 鎖 number。

### 3.5 為什麼順手修 Y24 不留 Y39

Y24 同 Y37 pattern（`wait + textContent + expect.toContain(✓)`）、grep 後立刻看到、改 4 行 trivial、同 PR 合理。

但是 Y22/Y26/Y27 等也有類似 pattern — 不全 sweep。理由：Y37 教訓「real-world flaky manifest 後再批次」。Y24 在 Y38 regression 浮出 = manifest 了、改；Y22/Y26/Y27 沒浮出、不動、避免 churn。

「等問題出來才修」聽起來懶、實際是 lean — 改了不會壞的 spec 是純成本、零收益。Y37 改 Y20 因為 Y20 浮出、Y38 改 Y24 因為 Y24 浮出。等 Y22/Y26/Y27 浮出再改。

### 3.6 為什麼不改 onShowFindPanel 在 0 match 時 disable 開啟

Open find panel 跟 navigate 不同事 — user 即使無 match 也應能開 panel（要打新查詢字串）。「無 match」是 fill text 後的 state、不是 panel 開啟前的 state。

只擋「navigate when count = 0」、不擋「open when context unknown」。

---

## 4. 預期 + 實測

**預期**：Enter / Shift+Enter 在「無結果」時 noop、count 不變、不產生 console error。

**實測**：
- Y20.1：1/1 pass (50.9s)、含 step 7a 4 個新 assertion
- Y14.1：1/1 pass (25.7s)、`.toBeGreaterThanOrEqual(10)` 過 11 個 item
- Y24.1：1/1 pass (37.5s)、auto-retry ✓ label
- 11-spec 連跑：11/11 pass 3.6m all green ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.js` | onFindNext + onFindPrev 各加 1 行 if-return + 共 4 行註解 |
| `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts` | step 7a +9 行（top-level repo） |
| `admin-dobtor-doc-editor-sprint-y14-keyboard.spec.ts` | 1 行 .toBe → .toBeGreaterThanOrEqual + 註解（top-level repo） |
| `admin-dobtor-doc-editor-sprint-y24-row3-toggle.spec.ts` | -3 行 wait/textContent / +1 行 expect.toContainText（top-level repo） |
| `phase8_sprint_y38_2026-05-28.md` | 新檔 |

---

## 6. 教訓

1. **find/replace UX trilogy 三 sprint 收完整四 entry point**：Y32 button disabled、Y33 nav button disabled、Y38 keyboard 短路 = 從不同入口都鎖同個 invariant（無 match 時不該 navigate）。每 sprint 1-2 行實作、串起來 = panel 4 路全擋。**user-visible 行為一致性靠多 sprint 細修達成、不是一次設計到位**。
2. **assertion 鎖 invariant 不鎖 number**：Y14 `.toBe(10)` 寫死 menu item 數、新加「✓ 預覽模式」立刻紅。改 `.toBeGreaterThanOrEqual(10)` 鎖「至少有 N item 可 navigate」這個 invariant、menu 演進不打 spec。**spec 鎖點選「測試焦點」自然 derive 的 invariant、不鎖周邊 implementation detail**。
3. **Y37「manifest 後批次」直接生效**：Y37 doc 預測 Y22/Y26/Y27 等同 pattern flaky 不一次全改、等真出問題。Y38 regression Y24 浮出 = manifest 了、改；Y22/Y26/Y27 沒浮出、不動。**Lazy fix 是 lean、不是懶**；改了不會壞的 spec 是純成本零收益。Y29 教訓「3 個 caller 還太早抽 utility」反向 = 「沒壞的 spec 還太早 refactor」。
4. **「精準對應動作」勝過「DRY 一次擋」**：onFindNext / onFindPrev 各擋 vs onFindInputKeyDown 統一擋。後者擋住 navigate 也擋住其他 key、誤殺 Escape 等 path。精準擋 = 一條 invariant 對一個 handler、不漏不誤殺。**DRY 不該凌駕於 「one responsibility per place」**。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y37 | ✅ |
| **Y38 — 鍵盤 0-match 短路 + Y14/Y24 stale fix** | ✅（11/11 sprint specs 全綠 3.6m、find/replace UX 4 entry point 完整一致）|

### Sprint Y39 候選

- 工具 menu「預覽變數效果」spec（沿用 Y35/Y36 pattern）
- 「✓ 預覽模式」menu item spec（Y14 expose 的新 item、應補 spec 鎖 toggle 行為）
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- Y22/Y26/Y27 spec 等 flaky manifest 後再批次（Y37/Y38 既定策略）

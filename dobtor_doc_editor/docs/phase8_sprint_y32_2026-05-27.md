# Phase 8 Sprint Y32 — 取代/全部取代 button disabled 條件（2026-05-27）

**性質**：Y30/Y31 find/replace trilogy 收尾 UX 強化 — 當 `findMatchCount === 0`（顯「無結果」），「取代」+「全部取代」兩顆 button 應 disabled、防 user 浪費 click + 視覺明確告知「沒東西可取代」。實作 trivial（XML 加 `t-att-disabled`、CSS 加 `:disabled` 樣式）、UX 完成度大躍進。
**範圍**：`doc_editor.xml`（2 個 button +3 行 attribute）、`doc_editor.css`（+~9 行 disabled 樣式 + hover 加 `:not(:disabled)` 防護）、Y22.1 spec 加緊（drain 完驗兩個 button disabled、force click 驗 noop）、新建 sprint doc。

---

## 1. 為什麼開這個

Y31 收尾教訓裡寫到「取代」按鈕 disabled 條件「scope 跟 cursor 不重疊、留 Y32+」。Y32 兌現。

User flow：fill `foo` → count = 3、可取代 → 連續 click 3 次取代 → count = 0「無結果」 → button 仍可 click、handler short-circuit return（因為 `findMatchCount === 0` 沒 match 可換）、但 visual 沒任何反饋、user 不知道為什麼按沒反應、可能繼續按或誤以為壞掉。

Disabled 直接告知「此時無法用」：
- 視覺：灰底、降透明度（opacity 0.6）、`cursor: not-allowed`
- 行為：actionability 阻止 click 觸發 handler
- 心理模型：跟 Office / GDocs / VSCode 取代 panel 一致（empty find 或 0 match 時 disable）

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `doc_editor.xml` | 「取代」+「全部取代」加 `t-att-disabled="state.findMatchCount === 0"` |
| `doc_editor.css` | `.doc-find-btn-text:hover` → `.doc-find-btn-text:hover:not(:disabled)`；新增 `.doc-find-btn-text:disabled`（灰底 + opacity + not-allowed） |
| Y22.1 spec step 5c | drain 完後驗兩個 button 皆 `toBeDisabled()` |
| Y22.1 spec step 6 | 改 force click 全部取代、驗仍「無結果」（state 沒變壞） |
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼用 `findMatchCount === 0` 而不是 `!findText || findMatchCount === 0`

兩個條件等價：findText 空時 `_updateMatchInfo` 會把 findMatchCount 設 0。所以單一條件 `findMatchCount === 0` 已含 findText 空的 case，don't repeat yourself。

### 3.2 為什麼用 OWL `t-att-disabled` 不是 JS push state

OWL 對 boolean 屬性的 `t-att-disabled`：true → render `disabled`、false → 不 render attribute。直接綁 reactive state 最簡、reactive 一變就自動 re-render。寫 JS push 是反 OWL pattern、徒增 churn。

### 3.3 為什麼 hover 改 `:hover:not(:disabled)`

原本 `:hover` 沒防護 disabled、disabled button hover 時還是會變底色 → 視覺矛盾（既看起來 disabled、又有 hover 反饋）。`:not(:disabled)` 防護避免這種「半 disabled」視覺。

Y28 / Y29 文件設定 / 行距 modal 的 input 沒有 disabled state（永遠可編輯）、所以沒這問題。但 Y32 是第一個 disabled state、CSS 防護要補。

### 3.4 為什麼 CSS 用 opacity + 灰底而不是純灰底

純灰底（`color: muted; background: hover-bg`）跟 hover 顏色撞色、user 可能誤判 disabled = hover。加 opacity 0.6 拉開視覺差距、跟 hover 區隔。

Tradeoff：opacity 全 element 變淡、不只字、也包含 border / padding。實測視覺 ok（按鈕本就小、整體變淡 read 為 disabled 而非 hover）。

### 3.5 為什麼 spec 用 `force click` 而不是 expect click 失敗

Playwright 對 disabled element 的 `.click()` 預設會等 actionability、最後 timeout 失敗。要驗「即使 user 硬點也不破壞 state」要繞 actionability、用 `{ force: true }`。

force click 等同瀏覽器繞過 disabled 跳直接派發 click event。如果 handler 短路（`if (!findText) return`）正確、state 不變。如果 handler 有 bug、會看到 count 變動 / crash。是 defensive verification。

### 3.6 為什麼不 disable 上一個 / 下一個 button

Y31 doc 已寫「scope 跟 cursor 不重疊、留 Y32+」。但 Y32 focus 在 replace button、cursor nav button 是另一個 path（user 想 navigate 也是 0 個 match 時也該 disable）。

決定：Y32 只動 replace button、cursor nav 留 Y33。理由：
- scope 緊一致：Y31 已是 cursor 工作、Y32 是 button enable state；連續 sprint 各鎖一塊
- nav button 跟 replace button visual 不同（icon vs text）、CSS 改動 path 不一樣、混在一起雜
- 用實體切割 sprint = 每個 sprint 可獨立 review / revert

### 3.7 為什麼 step 6 留 force click 驗 noop 而不是直接刪

Defensive verification 思路：disabled UI 是「user 應該無法操作」、但 force click（程式驅動 / accessibility 工具 / 鍵盤）可能繞過。驗「即使繞過 disabled、handler 也不會把 state 弄壞」 = 防 attack surface、不只防一般 user。

Cost：1 行 force click + 1 行 assertion。Value：未來改 handler logic 時、disabled UI 失守的 fallback 仍 work。

---

## 4. 預期 + 實測

**預期**：fill foo (count=3) → 連 3 click 取代 → 「無結果」 → 兩 button disabled → force click 全部取代 → 仍「無結果」。

**實測**：
- Y22.1 加緊（含 5c 兩 button disabled + step 6 force click）：1/1 pass (58.7s) — 比 Y31 的 42.6s 慢 16s、合理（多 4 行 assertion + force click + wait）
- 7/7 sprint specs (Y14/Y20/Y22/Y24/Y26/Y27)：2.6m all green
- 25/27 broader regression：2 pre-existing phase8 baseline failure (`.doc-toolbar` 預設隱藏、Y23 default `showLegacyToolbar=false` 後 baseline 未更新)、跟 Y32 無關、留 Y33 修
- 視覺驗證：disabled button 灰底 + opacity + not-allowed cursor ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `doc_editor.xml` | 「取代」+「全部取代」各加 3 行（含 title attribute、`t-att-disabled` 條件、註解） |
| `doc_editor.css` | hover 加 `:not(:disabled)`、新增 `:disabled` 5 行（color/bg/border/cursor/opacity） |
| `admin-dobtor-doc-editor-sprint-y22-replace-keyboard.spec.ts` | step 5c 加 3 行 disabled assertion、step 6 改 force click + assertion（top-level repo） |
| `phase8_sprint_y32_2026-05-27.md` | 新檔 |

---

## 6. 教訓

1. **disabled UI 是「告知 + 阻止」雙重職責**：純視覺 disable（灰顯）告訴 user「現在不能用」、actionability disabled 阻止 click。少哪個都不完整 — 純視覺 user 可能還是按、純 disabled attribute 沒視覺反饋 user 不知道為什麼按沒反應。Y32 兩個都做。
2. **disable hover 是 disabled state 的隱形地雷**：第一次加 disabled state、若不防護 `:hover:not(:disabled)`、視覺會「半 disabled」(灰底 + hover 變色)、user 誤判。CSS hover 規則 retrofit `:not(:disabled)` = 加 disabled feature 時必做的 sweep。
3. **force click 驗 defensive boundary**：disabled UI 是 UX 層的 guard、handler 短路是 logic 層的 guard。兩層都有 = 即使 UI guard 被繞（程式 / 工具）也 ok。spec 同時驗兩層 = 確認 defense-in-depth。
4. **連續 sprint 把 UX 推進到「跟業界一致」**：Y30 修核心邏輯（單一替換）、Y31 補 cursor 自動跳、Y32 補 disabled 防誤點。三個 sprint 各 1-10 行實作、UX 從「能用」躍到「跟 GDocs/VSCode 體驗一致」。每個 sprint 看似 trivial、串起來就是完整的功能 polish。Y4 寫了 button 但 UX 不完整、27+ sprint 後才補齊 — 提早設 spec rigor 可以早一兩年補完整。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y31 | ✅ |
| **Y32 — 取代/全部取代 button disabled 條件** | ✅（7/7 sprint specs 全綠、disabled UI + force click defense 雙鎖）|

### Sprint Y33 候選

- 「上一個」/「下一個」navigate button 也 disabled（findMatchCount === 0 時、cursor nav UI 完整化）
- 「全部取代」notification「已取代 N 個項目」spec 覆蓋（onReplaceAll count 顯示）
- 工具 menu 各 action 的 spec 覆蓋（字數統計 / 版本歷史 / 預覽變數效果）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- 字型 / 字號 selector active state 雙向同步驗證

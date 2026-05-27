# Phase 8 Sprint Y39 — 檔案 menu「預覽模式」precondition spec 覆蓋（2026-05-28）

**性質**：純 spec 覆蓋 — Y38 修 Y14 stale count assertion 時 expose 檔案 menu 後加「✓ 預覽模式」item、實作完成 30+ sprint 沒 spec 鎖。Y39 補 Y39.1：unbound doc（fixture 不綁 model_id/res_id）點預覽模式 → warning notification path、state 不變、label 不切 ✓ prefix。沿用 Y35/Y36 純 spec sprint pattern。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y39-file-preview-mode.spec.ts`（top-level repo、+121 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y38 跑 11-spec regression 時 Y14.1 失敗 = `expect(itemCount).toBe(10)` 得 11。當下修法 = `.toBeGreaterThanOrEqual(10)` 鎖 invariant。深挖原因：檔案 menu 有新 item「✓ 預覽模式」、`onTogglePreviewMode` handler 在 line 2492+、`state.previewMode` 在 line 186、wiring 在 line 4205、menu config 在 line 4814 — 完整實作早就 in code、但 30+ sprint 沒 spec 鎖。

Y35/Y36 教訓「實作 vs spec 差距是 sprint 的暗物質」直接 echo：
- Y35 補字數統計 spec（_countWords 從 Y3 起未鎖）
- Y36 補版本歷史 spec（onShowVersionPanel 從 W7-W8 起未鎖）
- Y39 補預覽模式 spec（onTogglePreviewMode 從 [unknown sprint] 起未鎖）

Y38 sprint doc Y39 候選明寫：「『✓ 預覽模式』menu item spec（Y14 expose 的新 item、應補 spec 鎖 toggle 行為）」。Y39 兌現。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y39.1 test | 新增 (top-level、~121 行)：bootstrap unbound doc → 開 editor → 檔案 menu → 預覽模式 item → unbound 走 warning notification path → 驗 toast 顯「未綁定」+「預覽模式」、dropdown 關、再開 menu label 仍無 ✓ prefix（state 不變） |
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼測 unbound path 不測 bound path

`onTogglePreviewMode` 兩條 path：
- **unbound**：doc 無 model_id / res_id → warning notification + state 不變 + return
- **bound**：呼 `/dobtor_doc/preview_content_json` 後端 rpc 渲染 → executeSetValue 渲染後 json → state.previewMode = true → success notification

unbound fixture 簡單（callKw create 不指定 model_id）、test 自包；bound 要建 model_id + 找實際 record + 渲染 — fixture 複雜、且依賴後端 render 邏輯（jinja2 等）、易脆。

選 unbound = ROI 高、鎖核心 invariant（precondition guard 起作用）；bound 留 Y40+ 真有人測再補。

Y32 教訓「scope 緊一致」+ Y29 教訓「3 個 caller 還太早抽 utility」延伸 = 「2 條 path 先鎖容易的、難的留 future sprint」。

### 3.2 為什麼用 `not.toContainText(/^\s*✓/)` 不 `not.toContainText('✓')`

`'   預覽模式（編輯器內顯示實際值）'` 含正常文字 `預覽模式`、不含 ✓；`'✓ 預覽模式...'` 開頭有 ✓ + 空白。

如果只用 `not.toContainText('✓')`、未來 label 在其他地方加 ✓（例如 tooltip 等）會誤 fail。`^\s*✓` regex 鎖「label 開頭是否有 ✓ prefix」精準對應 state.previewMode 渲染邏輯。

### 3.3 為什麼 step 6 重開 menu 再驗

第一次開 menu 時 OWL re-render 完整、`previewModeItem.click()` 後 dropdown 關閉、`state.previewMode` 變化（如果生效會 true）、menu items unmount。重開 menu = 新 render 才能看到「label 更新後實際樣貌」。

不重開只查 stale DOM 可能 race condition。reopen + assertion = 鎖「state 真實落地」、防 silent state mutation。

Y36 教訓「state machine 該驗 cycle 不只 transition」直接套用。

### 3.4 為什麼 unbound warning 比靜默回傳好

對照其他 menu action handler：
- 字數統計：直接算、不檢查 precondition
- 版本歷史：檢查 `state.docId` 未存檔時顯「請先儲存文件」warning
- 預覽模式：檢查 model_id + res_id、unbound 時顯「未綁定」warning

三個都用 notification 通知 user「為什麼沒生效」、不靜默返回 = 一致 UX。Y39 spec 同時驗證這個 UX 慣例（warning notification 存在）+ 防禦 invariant（state 不變）。

### 3.5 為什麼不 spec lock notification 的 type（warning vs success）

`.o_notification` 有 type class（`.o_notification.text-bg-warning`、`.o_notification.text-bg-success`）、可以更精準驗 type。但：
- 文案已含明確語意（「未綁定」明顯是錯誤狀態）
- type class 是 Odoo notification service 的 implementation、未來改 class naming spec 易壞
- ROI 低、漏這條也不會掩蓋真 bug

選文案 contains 驗證、不鎖 CSS type。Y36 教訓「selector 選 semantic > visual」+ Y38 教訓「鎖 invariant 不鎖 implementation detail」延伸。

---

## 4. 預期 + 實測

**預期**：unbound doc 點預覽模式 → warning 顯「未綁定」+「預覽模式」、state 不切 true、menu label 無 ✓ prefix。

**實測**：
- Y39.1：1/1 pass (26.1s)
- 12-spec 連跑 (Y14/Y20/Y22.1/Y22.2/Y24/Y26.1/Y26.2/Y27.1/Y27.2/Y35.1/Y36.1/Y39.1)：12/12 pass 4.4m all green ✓

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y39-file-preview-mode.spec.ts` | 新檔 +121 行（top-level repo） |
| `phase8_sprint_y39_2026-05-28.md` | 新檔 |

零 source code 改動 = 純 spec sprint（第 4 次連續純 spec：Y35 + Y36 + Y37 robustness + Y39）。

---

## 6. 教訓

1. **stale spec 是發現「實作 vs spec 暗物質」的金礦**：Y14 `.toBe(10)` 失敗 expose 新「✓ 預覽模式」item、Y38 修 spec 順手記入 Y39 候選、Y39 兌現補 spec。**spec 失敗的 root cause 分兩種：bug 或 feature drift；後者就是補 spec 的機會**。下次任何 spec stale 失敗、grep 一下找出新 feature、開 sprint 補。
2. **precondition guard 是 spec 友善的 path**：unbound path 走 warning return = 顯式 fail、好 assert；bound path 走 rpc + render = 多 dependency、易脆。**新功能寫好 spec 一定先測 precondition fail path**（fixture 簡單）、bound success path 留 future（fixture 複雜）。ROI 不對等、不該並進。
3. **連續 4 sprint 純 spec 建立『spec backfill』節奏**：Y35（字數統計）→ Y36（版本歷史）→ Y37（timing robustness）→ Y38 一半 + Y39（預覽模式）= 5 sprint 全 spec 或 spec-heavy、零 source 改動 / 微量 source 改動。**這個節奏暴露 dobtor_doc_editor codebase 的 silent capability gap = 「實作齊全但無 spec contract」**。Y3 ✅ marker 是「實作完成」、不是「有 spec」。下次盤點 ✅ 都該 grep 確認是否真有 spec assert。
4. **Y39 候選回到實裝 feature - spec coverage 的 sustained 配對**：Y32+Y33+Y38 都有 source 改動、Y35+Y36+Y39 純 spec。實作跟 spec 像 hash 表的兩條 hash function — 寫實作不寫 spec = silent bug；寫 spec 不寫實作 = 假試驗。dobtor_doc_editor 30+ sprint 後、 spec coverage 還在追、source 也還在加。**這是健康狀態**、不該被視為偷懶；長期 ratio = 每 N source 改動配 ~M spec sprint。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y38 | ✅ |
| **Y39 — 檔案 menu 預覽模式 precondition spec** | ✅（12/12 sprint specs 全綠 4.4m、`onTogglePreviewMode` unbound path 鎖回歸）|

### Sprint Y40 候選

- 預覽模式 bound path spec（需 doc.document 綁 model_id + res_id；fixture 複雜）
- 工具 menu「預覽變數效果」spec（沿用 Y35/Y36 pattern）
- 「列印」menu item spec（檔案 menu、沿用 Y35-Y39 pattern）
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- Y22/Y26/Y27 spec 等 flaky manifest 後再批次

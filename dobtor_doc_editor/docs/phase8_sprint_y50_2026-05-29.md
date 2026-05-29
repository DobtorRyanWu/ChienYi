# Phase 8 Sprint Y50 — 格式按鈕 aria-pressed a11y source fix（2026-05-29）

**性質**：source fix sprint — Y50 原想鎖格式按鈕 B/I/U/S active state 雙向同步、探查時揭露 silent a11y bug：8 個 toggle 按鈕（B/I/U/S + 對齊 4）的 `aria-pressed="state.activeBold"` 漏了 `t-att-` 前綴 → OWL 當字面字串渲染（aria-pressed 永遠 = 字串 "state.activeBold"、非 true/false）→ 螢幕閱讀器拿到無效 pressed 狀態。Y50 修 source（8 處）+ spec 鎖 a11y 屬性動態正確。
**範圍**：`doc_editor.xml`（8 處 `aria-pressed` → `t-att-aria-pressed` ternary）、新 spec file `admin-dobtor-doc-editor-sprint-y50-format-btn-active.spec.ts`（top-level repo、+~110 行）、新建 sprint doc。

---

## 1. 為什麼開這個

Y49 sprint doc Y50 候選第一條：「格式按鈕 B/I/U/S active state 雙向同步（沿用 Y49 selectAllInCanvas）」。動手探查時揭露兩個發現：

1. **aria-pressed 字面字串 bug**（本 sprint 修）：XML `aria-pressed="state.activeBold"` 漏 `t-att-` 前綴。OWL 對無 `t-att-` 前綴的屬性當**靜態字面**處理 → 渲染出 `aria-pressed="state.activeBold"`（字面表達式字串、非求值）。E2E 實測 received `"state.activeBold"`。8 個按鈕（粗體/斜體/底線/刪除線 + 靠左/置中/靠右/兩端對齊）全中。
2. **格式按鈕完整 active toggle E2E 不可靠**（留 future）：toolbar 按鈕 click 會 collapse canvas 文字選取（按鈕是普通 OWL `<button>`、沒 mousedown preventDefault）、`executeBold` 對空 range 操作（診斷 `boldCount:0` + `rangeCtx:null`）→ 完整「選取→套用→caret 回寫」E2E 在 Playwright 不穩。

Y50 聚焦修發現 1（a11y bug、清楚 + 高價值 + 可穩定 spec），發現 2 記入候選。同 Y40 揭露 command.search → Y41 修的節奏：spec 探查揭露 silent bug、source fix 跟上。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `doc_editor.xml` source fix | 8 處 `aria-pressed="EXPR"` → `t-att-aria-pressed="EXPR ? 'true' : 'false'"`（B/I/U/S + 對齊 4）|
| Y50.1 test | 新增 (top-level、~110 行)：開 editor → 驗 B/I/U/S aria-pressed 為動態 'false'（非字面 "state.activeBold"）+ 負向防回歸 + 對齊組（靠左預設 'true'、置中 'false'）|
| sprint doc | 新檔 |

---

## 3. 設計取捨

### 3.1 為什麼用 `EXPR ? 'true' : 'false'` 不用 `t-att-aria-pressed="EXPR"`

OWL `t-att-X="falsy"` 會**移除屬性**（false/null/''/undefined → 不加 attribute）。若直接 `t-att-aria-pressed="state.activeBold"`、未啟用時 aria-pressed 屬性消失。但 toggle 按鈕的 a11y 最佳實踐是 **aria-pressed 永遠 present**（true/false 都要有、螢幕閱讀器才知道「這是 toggle 按鈕、目前未按」）。

`state.activeBold ? 'true' : 'false'` 求值出字串 'true'/'false'（都 truthy）→ 屬性永遠 present 且動態。比「falsy 時消失」更符合 a11y 規範。

### 3.2 為什麼 spec 不鎖完整 active toggle（只鎖 aria-pressed 動態性）

探查確認格式按鈕完整雙向同步 E2E 不穩：
- toolbar 按鈕 click → canvas 失焦 → 選取 collapse → `executeBold` 對空 range 無效（診斷實證 `boldCount:0`、`rangeCtx:null`）
- 即使用鍵盤 Ctrl+B 保住選取、`rangeStyleChange` listener mutate state 在 OWL reactivity 外、不觸發 render（同 Y15.1 window-listener bug）、按鈕視覺不即時更新

所以「選取→套用→active 回寫」整段 E2E 在 Playwright 不可靠。**但 a11y 屬性的「動態 vs 字面」是 render 時就決定的、不依賴 canvas 互動**：開 editor 即可驗 aria-pressed='false'（動態）vs "state.activeBold"（字面 bug）。spec 鎖這個可穩定驗的部分、完整 toggle 留 future（需 source 改 + 投查 selection/render）。

**spec scope 跟著可測性走**：能穩定驗的（a11y 屬性正確性）鎖、不穩的（canvas 選取互動）誠實留 future。Y48「可測性決定 scope」延伸。

### 3.3 為什麼順手連對齊 4 個一起修

grep `aria-pressed="` 全 XML 8 處：4 格式 + 4 對齊、**同一個漏 t-att- 前綴的 bug**。Y41 教訓「lib API rename / 同類 bug 該整批掃」延伸 = 同一 root cause 的 8 處一次修完、不留 4 個。spec 順手驗對齊組（靠左預設 'true' 證 ternary 求值對、不是無腦填 'false'）。

### 3.4 為什麼這是 source fix 不是純 spec

Y43-Y49 連續 7 個純 spec sprint。Y50 探查揭露真 bug、minimal fix（8 行屬性前綴）價值明確（a11y 合規）、且不修的話 spec 無法鎖（aria-pressed 永遠字面字串）。**spec backfill 的副產品就是揭露 silent bug；揭露了該修就修**、不為了「保持純 spec 紀錄」而擱置真 bug。同 Y41（Y40 揭露後修 source）。

### 3.5 為什麼用 selective staging 提交

working tree 的 doc_editor.xml 有 in-flight L2-v2 alias panel 改動（非本 sprint）。`git apply --cached` 只 stage 本 sprint 的 8 處 aria-pressed hunk、不連帶提交 in-flight 工作。Y32 起所有碰 source 的 sprint 都這樣（Y34/Y38/Y41）。

---

## 4. 預期 + 實測

**預期**：修後 8 個 toggle 按鈕 aria-pressed 動態（'false' 預設、靠左對齊 'true'）、不再是字面 "state.activeBold"。

**實測**：
- 修前 E2E：aria-pressed received "state.activeBold"（字面字串、bug 實證）
- 修 + 升級模組後 Y50.1 單跑：1/1 pass (56.9s)、B/I/U/S aria-pressed='false'、靠左 'true'、置中 'false'
- 37-test full suite 連跑：37/37 pass 11.1m all green ✓（source fix 無回歸、a11y 屬性修復鎖定）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `static/src/components/doc_editor/doc_editor.xml` | 8 處 `aria-pressed` → `t-att-aria-pressed` ternary（selective staging）|
| `admin-dobtor-doc-editor-sprint-y50-format-btn-active.spec.ts` | 新檔 +~110 行（top-level repo）|
| `phase8_sprint_y50_2026-05-29.md` | 新檔 |

---

## 6. 教訓

1. **OWL 漏 `t-att-` 前綴 = silent 字面字串、a11y/動態屬性全失效**：`aria-pressed="state.X"` 沒 `t-att-` 就是字面字串 "state.X"、不求值。**動態屬性必加 `t-att-`**；漏寫不會報錯、屬性照渲染、只是值是表達式原文。a11y 屬性（aria-*）特別容易中招（不像 class 有 t-att-class 慣例提醒）。grep `aria-\w*="state\|aria-\w*="[a-z]*\.` 可掃出這類漏寫。
2. **toggle 按鈕 aria-pressed 該永遠 present**：用 `EXPR ? 'true' : 'false'` 不用裸 `t-att-X="EXPR"`（後者 falsy 時屬性消失）。**aria-pressed/aria-checked 等 toggle 狀態屬性、未啟用時也要 present='false'**、螢幕閱讀器才知道是 toggle。
3. **canvas 互動的可測性邊界**：Y49 字型/字號 select「通過」其實靠 native select 值保留、不是真反向同步證明（診斷發現 toolbar click collapse 選取、executeBold boldCount=0）。**canvas-editor 的 selection 在 toolbar 按鈕 click 時會丟失**（按鈕沒 mousedown preventDefault）→ 依賴「選取後套用格式」的 E2E 不穩。**誠實標記可測性邊界、不為了交付硬寫不穩 spec**；能穩驗的部分（a11y 屬性）鎖、不穩的留 future。
4. **spec 探查是 silent bug 探針、揭露了就修**：Y50 本想純 spec、探查揭露 aria-pressed bug → 轉 source fix。**spec backfill 的最大價值常常不是 spec 本身、而是寫 spec 時被迫真的去點/檢查每個元素、撞出沒人發現的 silent bug**。Y30 onReplaceOnce、Y34 onReplaceAll、Y40 command.search、Y50 aria-pressed 都是這樣被探針撞出來的。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y49 | ✅ |
| **Y50 — 格式按鈕 aria-pressed a11y source fix** | ✅（待 full suite 最終確認、8 toggle 按鈕 a11y 屬性修復 + 鎖）|

### Sprint Y51 候選

- 格式按鈕完整 active toggle 雙向同步（需先修 source：按鈕 mousedown preventDefault 保住 canvas 選取 + rangeStyleChange listener 加 this.render() 觸發即時更新；再 spec）
- 對齊 align 完整 active toggle（同上 source 前置）
- indeterminate state（部分選中、需跨樣式選取 + 上述 source 前置）
- 模板模式匯出 PDF/DOCX spec（rpc fill_template → LibreOffice → download、需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（file input + TS Parser、需 .docx 上傳 fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

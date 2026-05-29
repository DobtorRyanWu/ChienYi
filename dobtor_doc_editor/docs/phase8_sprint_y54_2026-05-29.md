# Phase 8 Sprint Y54 — 對齊按鈕完整 active toggle 雙向同步 spec（2026-05-29）

**性質**：純 spec sprint — 鎖對齊按鈕（靠左/置中/靠右/兩端）的完整 active toggle。Y50 鎖過對齊 aria-pressed 動態性（靠左預設 'true'、置中 'false'）；Y51 修 source 讓格式工具列點按保住 canvas 選取（`.doc-format-toolbar` editor-component + 8 按鈕含對齊 4 個 `mousedown.prevent`）。但沒 spec 鎖對齊的**完整 toggle**：全選 → 點置中 → `executeRowFlex('center')` 套到選取列 → caret rowFlex 反向同步 → `state.activeRowFlex='center'` → 置中 aria-pressed 翻 'true'、靠左翻 'false'（互斥組）。Y54 補。

**範圍**：新 spec `admin-dobtor-doc-editor-sprint-y54-align-toggle.spec.ts`（top-level、+~155 行）、新 sprint doc。零 source code 改動（Y51 已修、Y54 通過即反證涵蓋）。

---

## 1. 為什麼開這個

Y53 sprint doc Y54 候選第一條：「對齊 align 完整 active toggle spec（Y51 機制已修、補鎖 + getValue rowFlex oracle + aria-pressed 對齊組翻）」。

Y51 把 source 修對了（對齊 4 個按鈕跟 B/I/U/S 是同一批 8 個、一起拿到 editor-component + mousedown.prevent），但只 spec 鎖了 B/I/U/S 的完整 toggle（Y51.1）。對齊只在 Y50 鎖過 aria-pressed 預設值、沒鎖「點下去真的對齊 + 狀態翻」。沿用 Y51/Y52 驗證的真選取技術一次補完。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y54.1 test | 新增（top-level、~155 行）：seed content_json 真文字 → 全選 → 點置中 → getValue rowFlex='center' + 對齊組 aria-pressed（置中 true/靠左 false）→ 平行測靠右 |
| sprint doc | 新檔 |
| source code | **零改動**（Y51 已修） |

---

## 3. 設計取捨

### 3.1 為什麼能直接 spec、不用改 source

對齊 4 個按鈕在 Y51 跟 B/I/U/S 同批拿到 `editor-component`（容器層）+ `mousedown.prevent`（按鈕層）。所以「全選 → 點對齊 → 保住選取 → executeRowFlex 套用 → 反向同步」整條在 Y51 就已修好、只是沒 spec 鎖。Y54 spec **一次通過即反證 Y51 容器層 fix 涵蓋對齊組**（同 Y52 反證涵蓋 font/size select）——容器層修一次、整條 `.doc-format-toolbar` 受益。

### 3.2 雙 oracle：getValue rowFlex（正向）+ 對齊組 aria-pressed（反向 + 互斥）

- **getValue rowFlex（內容層、正向）**：`getValue().data.main` element 真有 `rowFlex='center'` → 證 executeRowFlex 套到真選取的列。
- **對齊組 aria-pressed（按鈕層、反向 + 互斥）**：置中 aria-pressed 翻 'true'、**且靠左翻 'false'**。鎖反向同步（caret rowFlex → state.activeRowFlex → re-render）+ 互斥組切換。

### 3.3 互斥組 toggle 要鎖「新的 on + 舊的 off」

對齊不像 B/I/U/S 各自獨立 boolean——它是 radio-style 互斥（left/center/right/justify 只有一個 active、由單一 `state.activeRowFlex` 字串決定）。所以 spec 不只鎖「點置中 → 置中 active」、還要鎖「**靠左同時變 inactive**」：證 state.activeRowFlex 是單值切換、aria-pressed 全組正確反映（不會出現兩個都 'true' 的壞狀態）。靠右那段同理（靠右 on + 置中 off）。

### 3.4 自我診斷 getValue oracle（Y51「先驗證」延伸）

不確定 rowFlex 存在 element 還是 row 層、getValue 怎麼回。所以 `rowFlexDist` helper 回 rowFlex 分佈、斷言訊息帶 `實得 ${JSON.stringify(dist)}`：**first run 若 oracle 位置猜錯、error 直接印出實際分佈、不必另寫 probe**。實測一次通過＝rowFlex 確實在 main element 上、executeRowFlex 套到選取。把「先驗證再 assert」內建進斷言訊息、first run 兼當 probe。

---

## 4. 預期 + 實測

**預期**：全選 → 點置中 → 選取列 rowFlex='center'、置中 aria-pressed 翻 true、靠左翻 false；靠右同理。

**實測**：
- Y54.1 單跑：1/1 pass (38.8s)、**first run 直接通過**（rowFlex oracle 位置猜對＝在 main element 上）、getValue rowFlex='center'/'right' + 對齊組 aria-pressed 互斥切換正確
- 39-test full suite 連跑：35 pass + 4 fail **16.9m**（基線 ~11m、本 run 慢 ~50%＝機器高負載）。**Y54 通過**、fail 4 個是 abce Sprint E / sprint-d 行內↔浮動 / ghn HN.1 / Y47.1
- 4 個 fail 重跑（5-file batch）：又只剩 abce A.2/C + sprint-d:136 fail（**再次換一組**）、原 4 個多數轉綠 → 確認 load-induced rotating flaky、非 deterministic 破壞
- **關鍵觀察**：本 run Sprint E **仍 fail despite Y53 已硬化到 10s**、sprint-d 是 Y43 就硬化過的 → **極端負載下連硬化過的 test 也超時**。per-test 硬化降機率、但贏不過任意機器負載；更槓桿的修法是 global timeout（列 Y55）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y54-align-toggle.spec.ts` | 新檔 +~155 行（top-level repo）|
| `phase8_sprint_y54_2026-05-29.md` | 新檔 |

零 source code 改動。

---

## 6. 教訓

1. **互斥組 toggle 要鎖「新的 on + 舊的 off」**：對齊是 radio-style 互斥（單一 state.activeRowFlex 決定）、不像 B/I/U/S 各自獨立。**spec 鎖互斥組不能只驗「點的那個變 active」、要同時驗「原本 active 的變 inactive」**——否則放過「兩個同時 true」的壞狀態。獨立 boolean 組（B/I/U/S）vs 互斥組（對齊）spec 重點不同。
2. **自我診斷 oracle 讓 first run 兼當 probe**：不確定資料結構（rowFlex 在 element 還 row）時、把實際值塞進斷言失敗訊息（`實得 ${JSON.stringify(...)}`）。猜對就過、猜錯 error 直接印結構、不必先寫 probe 再寫 spec。Y51「先驗證再 assert」的低成本版。
3. **容器層 source fix 涵蓋整條 toolbar**：Y51 的 editor-component 加在 `.doc-format-toolbar`、Y52 反證涵蓋 font/size select、Y54 反證涵蓋對齊組。**修在容器層的 fix、每補一個元件的 spec 就多一筆涵蓋反證**；一次修對、整條受益、後續只是補 spec 鎖。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y53 | ✅ |
| **Y54 — 對齊按鈕完整 active toggle spec** | ✅（待 full suite 最終確認、對齊組互斥 toggle 鎖定）|

### Sprint Y55 候選

- **global timeout 硬化（高優先、比 per-test 槓桿）**：playwright.config.ts 拉高 global `expect` / `actionTimeout`，給所有 assertion 在高負載下統一餘裕。Y51/Y52/Y54 連 3 次 full suite rotating flaky、Y53 per-test 硬化只在輕負載達綠、重負載連硬化過的 test 也超時 → per-test 打地鼠贏不過任意負載、global timeout 一改全 test 受益（注意：別動 workers=1、那是避 storageState race）
- 底線/刪除線 forward toggle 各鎖一次（Y51 機制已涵蓋、補 spec；同 Y51 斜體 pattern）
- 字色/背景色 palette 套真選取 spec（executeColor/Highlight、沿用真選取技術 + getValue color oracle）
- 兩端對齊（justify/alignment）toggle（對齊組第 4 個、Y54 已測 3 個方向）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 清除格式 / 複製格式（painter）按鈕 spec
- 若 full suite 又浮新 flaky、同款 pattern 再補（Y53 延續）
- 模板模式匯出 PDF/DOCX spec（需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（需 .docx fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）

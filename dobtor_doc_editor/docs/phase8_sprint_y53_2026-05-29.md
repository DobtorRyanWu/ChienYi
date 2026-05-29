# Phase 8 Sprint Y53 — full-suite timing flaky 批次硬化（2026-05-29）

**性質**：flaky 硬化批次 sprint（無 feature）— Y51、Y52 連續兩次 38-test full suite 各浮出 3 個 fail、且**兩次的 3 個是「會換」的**（Y51 run = abce Sprint E / ghn J.1 / Y20；Y52 run = Y20 / Y35 / Y44），3 者單跑全綠。rotating red set = 高負載 timing flaky 的鐵證（deterministic 破壞會固定打到同一組）。Y53 不加 feature、專門硬化已觀察到的 5 個 flaky test，沿用 Y43/Y48/Y49 的硬化 pattern。

**範圍**：5 個 spec 各針對性硬化（`y20-find-keyboard`、`y35-tools-word-count`、`y44-version-restore`、`abce`、`ghn`、top-level）、新 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

連兩次 full suite 各 3 個 rotating red。**rotating red 會侵蝕 regression gate 的核心價值**：這整串 sprint 的意義就是「綠 suite 鎖行為」；若每跑必紅 3 個隨機 test，真正的 regression 會淹沒在 flaky noise 裡、分辨不出「這次紅是真破壞還是又 flaky」。Y43/Y49 都在 feature sprint 順手硬化過 flaky（save_field/drag 家族、expect.poll），但這次浮出的 5 個是 heterogeneous、量較大、且已連兩 sprint 重複 → 值得一個專門 sprint 把地基修穩、再往上疊 spec。

---

## 2. 範圍

| Spec | flaky 根因 | 修法 |
|---|---|---|
| `y35-tools-word-count` | 固定 `waitForTimeout(800)` + 單次 `textContent()`（無重試）→ toast 晚於 800ms 出現讀到 null | 改 `toBeVisible({timeout:8000})` auto-retry 等 toast 出現再讀 |
| `ghn` J.1 | 固定 `waitForTimeout(5500)` + 單次 `search_read`（無重試）→ 4 save + 4 替換 + autoSave 晚於 5500ms 讀到不足 4 筆 | 改 `expect.poll` 重試讀到 4 筆（records + controlCount 各一）|
| `y44-version-restore` | 2-RPC restore 鏈（存還原前快照→apply）+ notification/panel auto-retry timeout 太短 | menu 2000→5000、panel 3000→6000、notification 5000→10000 |
| `y20-find-keyboard` | Ctrl+F / menu 開 panel 的 `toBeVisible(2000)` 高負載下太短 | 3 處 panel-visible 2000→5000 |
| `abce` Sprint E | DocFieldPickerDialog 載欄位 RPC、`toBeVisible(5000)` 太短 | dialog 5000→10000 |
| sprint doc | 文件 | 新檔 |
| source code | — | **零改動** |

---

## 3. 設計取捨

### 3.1 兩類 flaky 根因 + 對應修法

硬化前先把 5 個 flaky 的根因歸成兩類：

- **(a) fixed-wait + single-read（最危險）**：`waitForTimeout(固定值)` 後做**單次** read（`textContent()` / `callKw search_read`）、**無重試窗口**。高負載下實際完成晚於固定值就直接讀到 null/不足、斷言失敗。Y35（notification 單讀）、J.1（search_read 單讀）屬此。**修法 = 換成 auto-retry**：`toBeVisible`（等元素出現）或 `expect.poll`（重試讀 DB 到期望值）。這是 Y43/Y49 save_field 家族的同款修法。
- **(b) auto-retry timeout 太短**：本來就用 `toBeVisible({timeout})` / `expect.poll`、但 timeout 設太緊（2000/3000/5000）、高負載下 UI render / 多段 RPC 比單跑慢就超時。Y44（2-RPC restore）、Y20（Ctrl+F panel）、Sprint E（dialog RPC）屬此。**修法 = 拉高 timeout**（auto-retry 只會等到條件成立、拉高不拖慢正常 case、只給慢 case 餘裕）。

### 3.2 為什麼 fixed-wait + single-read 是最危險的 flaky 形態

`waitForTimeout(N)` + 單次 read 沒有任何「沒到就再等」的機制：N 太短就 100% fail、N 夠長就過、但 N 是猜的、且高負載下「夠長」會變。auto-retry（`toBeVisible` / `expect.poll`）相反：**只要在 timeout 內條件成立就立刻往下、正常 case 不變慢、慢 case 有餘裕**。所以 fixed-wait + single-read 應一律改 auto-retry、不是把 N 調更大（調大只是把 flaky 機率降低、沒消除、還拖慢所有 case）。

### 3.3 為什麼不能保證根除（誠實標記）

flaky 是機率性 + rotating：硬化已觀察到的 5 個、降低它們的 fail 機率，但 **one full-suite run 全綠不是「根除」的證明**（下次可能換別的 test 在別的慢點 flaky）。Y53 的目標是**把已知最常 flaky 的點補實**、把 rotating red 收斂；若之後又浮出新的、同款 pattern 再補（Y43→Y49→Y53 的延續節奏）。不誇大成「flaky 已解決」。

### 3.4 為什麼專門 sprint、不混 feature

5 個 heterogeneous flaky、各要讀懂 + 針對修、量比 Y43/Y49 順手一個家族大。且 suite 可靠性是其它所有 spec 的地基——地基在抖時先疊新 spec 只會讓「這次紅是真是假」更難判。先用一個 sprint 修穩。

---

## 4. 預期 + 實測

**預期**：5 個 flaky 點補實後、full-suite rotating red 收斂；5 個 test 單跑仍綠（硬化只放寬、不改邏輯）。

**實測**：
- 5 spec（11 test）單跑：11/11 pass (3.3m) → 硬化未破壞既有行為
- 38-test full suite 連跑：**38/38 pass 11.0m all green** ✓ — rotating red 收斂（連兩次 35/38 → 硬化後 38/38）。注意：one green run 是最強即時 signal、非「根除」證明（flaky 機率性+rotating、見 3.3）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y35-tools-word-count.spec.ts` | toast auto-retry（top-level）|
| `admin-dobtor-doc-editor-sprint-ghn.spec.ts` | J.1 expect.poll ×2（top-level）|
| `admin-dobtor-doc-editor-sprint-y44-version-restore.spec.ts` | 3 處 timeout 拉高（top-level）|
| `admin-dobtor-doc-editor-sprint-y20-find-keyboard.spec.ts` | 3 處 panel-visible timeout 拉高（top-level）|
| `admin-dobtor-doc-editor-sprint-abce.spec.ts` | dialog timeout 拉高（top-level）|
| `phase8_sprint_y53_2026-05-29.md` | 新檔 |

零 source code 改動。

---

## 6. 教訓

1. **rotating red set = flaky 鐵證**：連兩次 full suite 各 3 紅、但兩次的 3 個「會換」（5 個不同 test 輪流中）→ 一定是 flaky、不是 deterministic 破壞（後者會固定打同一組）。**判斷一組 red 是真破壞還是 flaky、先看「跨 run 是否會換」+「單跑是否綠」**，不必每個都深挖。
2. **flaky 分兩類、修法不同**：(a) fixed-wait + single-read → 換 auto-retry/poll；(b) auto-retry timeout 太短 → 拉高 timeout。**先分類再修**、別一律拉 timeout（對 (a) 沒用、對所有 case 拖慢）。
3. **fixed-wait + single-read 是最危險 flaky 形態**：沒有「沒到再等」機制、N 是猜的、高負載下「夠長」會變。**這種 pattern 一律改 auto-retry**（`toBeVisible` / `expect.poll`）、正常 case 不變慢、慢 case 有餘裕。寫新 spec 時就別再用 fixed-wait + single-read。
4. **flaky 侵蝕 regression gate signal、值得專門 sprint**：每跑必紅幾個隨機 test 會讓「真 regression」無法分辨。**綠 suite 是鎖行為的地基、地基抖了先修穩再疊**。但硬化是降機率、非根除（rotating + 機率性）；誠實標「收斂中」不誇大「已解決」。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y52 | ✅ |
| **Y53 — full-suite timing flaky 批次硬化** | ✅（待 full suite 最終確認、5 個最常 flaky 點補實、rotating red 收斂）|

### Sprint Y54 候選

- 對齊 align 完整 active toggle spec（Y51 機制已修、補鎖 + getValue rowFlex oracle + aria-pressed 對齊組翻）
- 底線/刪除線 forward toggle、字色/背景色套真選取（沿用 Y51/Y52 真選取技術）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 清除格式 / 複製格式（painter）按鈕 spec
- 若 full suite 又浮新 flaky、同款 pattern 再補（Y53 延續）
- 模板模式匯出 PDF/DOCX spec（需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（需 .docx fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）

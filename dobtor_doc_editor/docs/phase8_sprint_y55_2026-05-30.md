# Phase 8 Sprint Y55 — global expect timeout 結構性 flaky 硬化（2026-05-30）

**性質**：結構性 flaky 硬化 sprint（playwright.config.ts 一行 config 改動、無 feature、無 spec）— Y53 per-test 硬化的升級版。Y51/Y52/Y54 連 3 次 full suite 出現 rotating timing flaky；Y53 per-test 硬化只在輕負載（11m run）達綠、Y54 重負載（16.9m run、慢 ~50%）下**連已硬化的 test 也超時**（Sprint E 已硬化到 10s 仍 fail、sprint-d 是 Y43 就硬化過的仍 fail）。結論：per-test 打地鼠贏不過任意機器負載。Y55 改 global `expect` timeout 5000→15000、一改全 test 受益。

**範圍**：`playwright.config.ts` 加 `expect: { timeout: 15000 }`（top-level）、新 sprint doc。零 source、零 spec 邏輯改動。

---

## 1. 為什麼開這個

Y54 sprint doc Y55 最高優先候選。3 次 full suite 證據 + Y54 的決定性發現：

| Run | 結果 | runtime | 備註 |
|---|---|---|---|
| Y51 | 35/38 | ~11m | Sprint E / J.1 / Y20 |
| Y52 | 35/38 | 13.1m | Y20 / Y35 / Y44（換一組）|
| Y53（per-test 硬化後）| 38/38 ✓ | 11.0m | 輕負載達綠 |
| Y54 | 35/39 | **16.9m** | Sprint E（已硬化 10s）/ sprint-d（Y43 硬化過）/ HN.1 / Y47（重負載、連硬化的也超時）|

Y54 的 16.9m（基線 ~11m、慢 50%）說明：機器高負載下、per-test 硬化過的 timeout（10s）也不夠。**per-test 逐個 bump 是打地鼠**——每次換一組 flaky、且贏不過任意負載峰值。需要結構性的、一改全 test 受益的修法。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| `playwright.config.ts` | top-level 加 `expect: { timeout: 15000 }`（預設 5000 → 15000）|
| sprint doc | 新檔 |
| source / spec 邏輯 | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼 global expect timeout 是對的槓桿（不是 per-test timeout）

要分清兩個 timeout：

- **per-test timeout**（test 整體）：dobtor admin spec 都自設 90-180s（`describe.configure` + `setTimeout`）、**遠大於實際需要、不是 flaky 元兇**。
- **expect timeout**（單一 assertion auto-retry 上限）：Playwright 預設 **5000ms**。flaky 失敗的 assertion 幾乎都是 `toBeVisible` / `toContainText` / `toHaveCount` 用這個預設 5000——重負載下 UI render / RPC 晚於 5s 就 fail（**不是** test 整體 90s 超時）。

所以對的槓桿是 **global expect timeout**：一次給「所有未明指 timeout 的 assertion」餘裕、不必逐 spec 改。5000→15000 = 3× headroom。

### 3.2 為什麼 per-assertion 明指的 timeout 不受影響（與 Y53 互補）

per-assertion 明指 `{ timeout: N }`（如 Y53 把 Y44 notification 改 10000、Y20 panel 改 5000）會 **override** global 預設。所以：
- Y53 那些明指 bump **仍有效、保留**。
- global 15000 只套用到**沒明指 timeout 的 assertion**（大量 `toBeVisible()` / `toContainText()` 裸呼叫）。

兩者互補：Y53 補了「明指但太短」的點、Y55 補了「用預設 5000 的所有裸 assertion」。

### 3.3 為什麼 15000、不更高

- **passing case 不變慢**：auto-retry assertion 條件成立**即往下**、只有 failing case 才吃滿 timeout。所以拉高不拖慢正常跑。
- **failing case（真 bug）才等到 15s**：太高（如 30000）會拖慢真失敗 surface、且 90s test timeout 會被更少 assertion 吃掉。15s 在重負載（慢 50%）下給 ~2× 餘裕、夠用又不過頭。

### 3.4 為什麼不動 workers=1

`workers: 1` + `fullyParallel: false` 是刻意的（Odoo session 共用 storageState、序列跑避 race）。flaky 的解法是給 timeout 餘裕、**不是加 worker 並行**（並行會引入 storageState race、更糟）。

### 3.5 誠實：仍非根除、且有更徹底的後續

- global timeout 拉高是**降機率 + 結構槓桿**、比 per-test 大很多、但**仍非根除**（機率性、極端負載峰值仍可能超 15s）。
- 更徹底的後續（Y56+）：把每個 spec 的 `openEditor` 裡 `waitForTimeout(4000)` 固定等待改成 **readiness 訊號等待**（`waitForFunction(() => window._docEditorCmp)` 自適應負載）。但那是 24 個 spec 的 openEditor copy 都要改、scope 大、留後續。Y55 先用 1 行 config 拿最大槓桿。

---

## 4. 預期 + 實測

**預期**：global expect timeout 15000 後、重負載下 rotating flaky 收斂；config 改動不破壞任何既有 test。

**實測**：
- config 載入驗證（Y54 單跑）：1/1 pass (35.8s) → config 語法正確、不破壞載入
- 39-test full suite 連跑：**39/39 pass 11.6m all green** ✓
- **誠實標記**：本 run runtime 11.6m（回到基線、vs Y54 的 16.9m）＝機器負載也緩解了 → **無法把「全綠」單獨歸因於 config 改動 vs 負載減輕**。但 global timeout 拉高是嚴格有益的結構性餘裕（passing case 不吃 timeout、failing case 才等滿）、對未來重負載 run 是對的方向。非根除（仍機率性、見 3.5）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `playwright.config.ts` | `expect: { timeout: 15000 }`（top-level repo）|
| `phase8_sprint_y55_2026-05-30.md` | 新檔 |

零 source / spec 邏輯改動。

---

## 6. 教訓

1. **per-test 硬化贏不過任意機器負載、global timeout 才是結構槓桿**：Y53 逐個 bump 只在輕負載達綠、重負載（Y54 16.9m）連硬化過的 test 也超時。**flaky 連續多 sprint rotating、就別再逐個 bump（打地鼠）、改 config 層一次給所有 assertion 餘裕**。
2. **分清 per-test timeout vs expect timeout**：per-test（90s）遠大於需要、不是 flaky 元兇；expect（預設 5000）才是裸 assertion 超時的真因。**調 flaky 要調對 timeout**——是單一 assertion 的 expect timeout、不是 test 整體 timeout。
3. **config 層一改全受益 vs spec 層逐個改**：global expect timeout 一行套用全 test（含未明指的裸 assertion）、per-assertion 明指仍 override（互補不衝突）。**有「全域預設」可調時、先調預設、再針對例外明指**、別反過來逐個明指。
4. **passing case 不吃 timeout、所以拉高預設是低成本**：auto-retry 條件成立即往下、只有 failing case 才等滿。**拉高 expect 預設不拖慢正常跑、只給慢/失敗 case 餘裕**——這類「只在壞路徑付代價」的調整可以放心做。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y54 | ✅ |
| **Y55 — global expect timeout 結構性 flaky 硬化** | ✅（待 full suite 最終確認、config 層一改全 test 受益）|

### Sprint Y56 候選

- 底線/刪除線 forward toggle 各鎖一次（Y51 機制已涵蓋、補 spec）
- 字色/背景色 palette 套真選取 spec（executeColor/Highlight + getValue color oracle）
- 兩端對齊（justify/alignment）toggle（對齊組第 4 個）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 清除格式 / 複製格式（painter）按鈕 spec
- openEditor `waitForTimeout(4000)` → `waitForFunction(window._docEditorCmp)` readiness 等待（24 spec、徹底解 flaky 的後續、scope 大）
- 模板模式匯出 PDF/DOCX spec（需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（需 .docx fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）

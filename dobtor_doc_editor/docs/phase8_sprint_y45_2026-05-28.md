# Phase 8 Sprint Y45 — 版本面板「比對版本」diff_versions 段落級 diff spec（2026-05-28）

**性質**：純 spec sprint — 鎖版本面板進階分析能力第一條：`toggleCompareMode` → `pickForCompare` → `runDiff` → rpc `/dobtor_doc/versions/diff` → `diff_versions` difflib 段落級比對。比對是「唯讀分析」path、與還原（寫）互補。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y45-version-diff.spec.ts`（top-level repo、+~150 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y44 sprint doc Y45 候選第一條：「版本面板『比對版本』spec（`runDiff`、`diff_versions`、選兩版顯段落 diff）」。Y45 兌現。

版本管理三角（Y36 讀面板 / Y43 寫快照 / Y44 還原）閉合後、面板還有兩條進階能力沒鎖：**比對**（`runDiff`）+ **單版預覽**（`previewVersion`）。Y45 先補比對：

- 比對是**唯讀分析** path（讀兩版 snapshot → difflib → 顯 opcodes）、不改任何狀態、與還原（寫）互補
- `diff_versions` 內含實質演算邏輯（HTML→段落 lines → `difflib.SequenceMatcher` → opcodes），不是單純 CRUD wiring — 演算正確性最該 spec 鎖

Y3/Y35/Y36/Y39/Y40/Y42/Y43/Y44 backfill 節奏延續。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y45.1 test | 新增 (top-level、~150 行)：callKw 建 v1（共同段+原始段）+ v2（共同段+修改段）→ 開 editor → 工具 menu 開面板 → 點「比對版本」進 compare mode（驗 checkbox 出現）→ 勾 v1+v2 列（regex 定位）→ `.doc-version-diff` 出現 → 標題含 v1+v2 → opcodes 至少 1 `.diff-equal`（共同段）+ 1 `.diff-replace`（差異段）|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼 fixture 刻意「差一段、共一段」

`diff_versions` 把 content_html 拆段落 lines、跑 `difflib.SequenceMatcher`。fixture：
- v1 = `共同第一段落` + `原始第二段落 AAA`
- v2 = `共同第一段落` + `修改後第二段落 BBB`

difflib 對 `[共同, 原始]` vs `[共同, 修改]` 必產：**1 個 equal**（共同段）+ **1 個 replace**（原始↔修改）。spec 斷言兩種 op 都出現 = 一次鎖死兩件事：
- `.diff-equal` 存在 → 證 difflib 抓得到「相同段落」(line-level 對齊正確、不是整段當 replace)
- `.diff-replace` 存在 → 證 difflib 抓得到「差異段落」(不是漏報成 equal)

「差一段共一段」是能同時驗 equal + replace 的最小 fixture。Y40 教訓「fixture 設計成可精準斷言期待值」延伸。

### 3.2 為什麼 diff 比 restore 更不受 editor auto-save 干擾

Y44 主動放棄 content_html round-trip 斷言（editor auto-save race）。Y45 diff 沒這問題：
- `diff_versions` 讀的是 **versions_data 內凍結的 snapshot content_html**（透過 `get_version_content` → `_find_version_entry`）
- editor auto-save 只改 **current** `doc.content_html`、碰不到已凍結的 v1/v2 snapshot

所以 diff 結果完全由 callKw 設定的 snapshot content 決定、deterministic。**讀凍結快照 = 天然 auto-save-proof**；這也是為什麼比對適合做 spec（穩定）、而 restore 的 content round-trip 不適合（current 會被覆寫）。

### 3.3 為什麼版本 setup 用 callKw 直接寫 content + action_save_version

Y44 同理：焦點是比對 UI、版本建立只是前置。callKw `write(content_html)` + `action_save_version` 精準設定每版內容、避開 editor 互動的不確定性。要讓 diff 有意義必須兩版 content 不同、callKw 是唯一能精準控制 snapshot content 的方式（editor 內編輯文字 fragile）。

### 3.4 為什麼勾 checkbox 用版本號定位列、不用 .first()

列表降序 [v2, v1]。compare mode 下每列一個 checkbox。要「勾 v1 + v2」必須各自定位、`.first()`（=v2）不夠。用 `page.locator('.doc-version-item', { has: .doc-version-no /^v1$/ })` 鎖含版本號的列、再取列內 checkbox。regex `^v1$` 防 future fixture 擴充時 v1 撞 v10。Y44 同款 selector 策略。

### 3.5 為什麼斷言 op class 存在、不斷言 op 文字內容

`.diff-equal` / `.diff-replace` 是 `getDiffOpClass` 映射的 class（diff engine 分類結果）、比「未變動／修改」中文 label 更接近演算本質。斷言 class 存在 = 鎖「difflib 分類正確」；不額外斷言段落文字（那是 fixture echo、ROI 低）。Y36 教訓「selector 選 semantic」延伸 = 斷言選「演算分類」不選「顯示文字」。

---

## 4. 預期 + 實測

**預期**：比對版本 → 勾 v1+v2 → diff 區顯 v1↔v2 + opcodes 含 equal（共同段）+ replace（差異段）。

**實測**：
- Y45.1：1/1 pass (32.5s)
- 32-test full suite 連跑：32/32 pass 15.6m all green ✓（含 Y36/Y43/Y44/Y45 版本管理全 path、sprint-d 持續穩定）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y45-version-diff.spec.ts` | 新檔 +~150 行（top-level repo）|
| `phase8_sprint_y45_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 9 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **含演算邏輯的 path 比 CRUD wiring 更該 spec**：`diff_versions` 不是單純讀寫、而是 HTML→段落→difflib→opcodes 的演算。**feature 內含真正演算法（diff/排序/計算）的、spec 要用「可精準預期結果的 fixture」鎖演算正確性**，不只鎖「rpc 有回」。Y34 onReplaceAll count、Y35 字數統計、Y45 diff 都是這類「演算正確性 spec」。
2. **讀凍結快照天然 auto-save-proof**：Y44 restore 的 content round-trip 被 editor auto-save race 卡、放棄斷言；Y45 diff 讀的是凍結 snapshot、editor 怎麼動都不影響。**E2E 挑「讀不可變資料」的 path 做斷言最穩**；同一 feature 內，讀凍結態 > 讀 current 態（後者會被並行流程 mutate）。
3. **最小 fixture 同時驗多個分類**：「差一段共一段」用最少內容同時逼出 equal + replace 兩種 opcode。**設計 fixture 時想「最小輸入能覆蓋幾個 code path」**；2 段落 fixture 覆蓋 difflib 的 equal + replace 兩分支、比堆一大段內容 ROI 高。
4. **面板能力分 path 逐 sprint 鎖**：版本面板 = 讀(Y36) + 寫快照(Y43) + 還原(Y44) + 比對(Y45) + 預覽(Y46 候選)。**一個複合 component 的多個 action 各鎖一條 spec、每條 focused**；累積起來才是整個 panel 的完整 contract。Y36/Y43/Y44/Y45 是同一 component 的漸進 backfill。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y44 | ✅ |
| **Y45 — 版本面板比對版本 diff_versions 段落級 diff spec** | ✅（待 full suite 最終確認、版本面板比對唯讀分析 path 鎖）|

### Sprint Y46 候選

- 版本面板「預覽版本」spec（`previewVersion`、`get_version_content`、單版 HTML 預覽渲染 `.doc-version-preview`）
- 預覽模式 bound path spec（需 doc 綁 model_id + res_id）
- 「列印」menu item spec
- 「匯入 DOCX」/「匯出 PDF」/「匯出 DOCX」menu item spec
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

# Phase 8 Sprint Y46 — 版本面板「預覽版本」previewVersion 單版內容渲染 spec（2026-05-28）

**性質**：純 spec sprint — 鎖版本面板最後一條 path：`previewVersion` → rpc `/dobtor_doc/versions/get` → `get_version_content` 回指定版凍結 snapshot 的 content_html → `.doc-version-preview` 渲染。版本面板五條 path（讀/寫/還原/比對/預覽）全 spec 收尾。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y46-version-preview.spec.ts`（top-level repo、+~140 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y45 sprint doc Y46 候選第一條：「版本面板『預覽版本』spec（`previewVersion`、`get_version_content`、單版 HTML 預覽渲染 `.doc-version-preview`）」。Y46 兌現。

版本面板（DocVersionPanel）共 5 條 user action path：
- **讀面板**：`onShowVersionPanel` → 開面板列版本（Y36）
- **寫快照**：`onSaveVersion`（Ctrl+Shift+S）（Y43）
- **還原**：`restoreVersion` → restore_version（Y44）
- **比對**：`runDiff` → diff_versions（Y45）
- **預覽**：`previewVersion` → get_version_content（Y46）← 本 sprint

Y46 補上最後一條 = 整個版本面板 component 的 5 條 path 全 spec、形成完整 contract。預覽是「唯讀單版」path、與比對（唯讀雙版）並列。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y46.1 test | 新增 (top-level、~140 行)：callKw 建 v1（AAA marker）+ v2（BBB marker、current=BBB）→ 開 editor → 工具 menu 開面板 → 點 v1 列「預覽」按鈕 → `.doc-version-preview` 出現 → 標題「v1 預覽」→ `.doc-version-preview-html` 含 AAA-MARK、不含 BBB-MARK |
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼建兩版不同 marker + 預覽舊版

預覽最該證的是「顯示的是**指定那一版**、不是 current、不是別版」。fixture：
- v1 = `AAA-MARK`、v2 = `BBB-MARK`、current 內容 = BBB（v2 之後沒再改）

預覽 v1 → 斷言 `.doc-version-preview-html` **含 AAA、不含 BBB** = 一次鎖死：
- 含 AAA：`get_version_content(1)` 回的是 v1 snapshot
- 不含 BBB：沒誤抓 current(=BBB) 或 v2

若只建一版、預覽顯內容、無法分辨「顯的是 v1 還是 current」（兩者同內容）。**要證 selector 正確必須讓正確答案與錯誤答案內容不同**。Y45「差一段共一段」同理 = fixture 設計成能 disambiguate。

### 3.2 為什麼預覽能斷言 content marker、Y44 還原卻不能

Y44 restore 主動放棄 content_html round-trip（editor auto-save 會用 canvas render 覆寫 current）。Y46 預覽可以斷言 content、因為：
- 預覽讀的是 **versions_data 凍結 snapshot**（`get_version_content` → `_find_version_entry`）、渲染在 panel 自己的 `.doc-version-preview-html`、**不經過 canvas-editor**
- editor auto-save 改的是 current doc、碰不到 snapshot、也碰不到 panel 預覽區

**「讀凍結態 + 渲染在獨立 DOM」= content 斷言安全**；Y44 restore 是「寫回 current + 經 canvas executeSetValue」= content 會被覆寫。同 feature 不同 path、content 可斷言性天差地別。Y45 diff 同屬「讀凍結態」可斷言陣營。

### 3.3 為什麼用 `not.toContainText('BBB-MARK')` 加強

只斷言「含 AAA」證了「有 v1 內容」、但沒排除「同時混入別版」。加 `not.toContainText('BBB-MARK')` = 證預覽區**只**顯 v1、不是 current 或全版串接。**正向斷言證「該有的有」、負向斷言證「不該有的沒有」**；對「選對版本」這種 selector 正確性、兩個方向都要。

### 3.4 為什麼版本 setup 仍走 callKw

Y44/Y45 一致：焦點是預覽 UI、版本建立是前置。callKw `write(content_html)` + `action_save_version` 精準控制每版 snapshot content（要 disambiguate 必須精準設不同 marker）、避開 editor 編輯 fragile。

### 3.5 為什麼預覽不會撞到 diff 區（同一 DOM 位置）

XML：`<t t-if="state.diffResult">...diff...</t><t t-elif="state.previewContent">...preview...</t>` — diff 與 preview 共用同一條件渲染位置、互斥。fresh 開面板 → 無 diffResult → 點預覽 → 走 elif 顯 `.doc-version-preview`。Y46 不進 compare mode、所以 diffResult 永遠 null、preview 正常顯。**spec path 單純（不混 compare）= 不會踩到互斥條件**。

---

## 4. 預期 + 實測

**預期**：點 v1「預覽」→ `.doc-version-preview` 顯「v1 預覽」+ 內容含 AAA、不含 BBB。

**實測**：
- Y46.1：1/1 pass (25.5s)
- 33-test full suite 連跑：33/33 pass 10.4m all green ✓（版本面板 5 path Y36/Y43/Y44/Y45/Y46 全綠 + sprint-d 持續穩定）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y46-version-preview.spec.ts` | 新檔 +~140 行（top-level repo）|
| `phase8_sprint_y46_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 10 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **版本面板 5 條 path 全 spec 收尾**：Y36 讀 + Y43 寫 + Y44 還原 + Y45 比對 + Y46 預覽 = 一個 component 的所有 user action 各鎖一條、合成完整 contract。**複合 component 的 spec 不必一個 sprint 塞滿、逐 path 漸進 backfill、每條 focused**；五個 sprint 後整個 panel 行為全鎖、任一 path regression 都會被抓。這是「core feature 越久沒 spec 越 silent」的系統性解法。
2. **content 可斷言性取決於資料來源不是 feature**：同一版本面板、預覽（讀凍結 snapshot + 獨立 DOM）可斷言 content marker、還原（寫 current + 經 canvas）不可。**判斷一個 E2E 能不能斷言內容、要看「資料是凍結還是會被並行流程 mutate」+「渲染是否經過會覆寫的中間層」**、不是看 feature 名稱。Y44/Y45/Y46 三條相鄰 path 正好示範這個判準。
3. **disambiguate fixture 是 selector 正確性 spec 的核心**：要證「選對版本」、正確答案與錯誤答案內容必須不同（v1=AAA / current=BBB）。**fixture 設計的第一問是「如果 selector 錯了會怎樣、我的斷言抓得到嗎」**；同內容 fixture 抓不到「選錯版本」bug。Y45「差一段」、Y46「兩版不同 marker」都是為 disambiguate 而設計。
4. **正向+負向雙斷言鎖 selector**：含 AAA（該有的有）+ 不含 BBB（不該有的沒有）。**選擇類 feature（選版本/選欄位/選 tab）的 spec 該雙向斷言**、只正向會漏掉「多選/串接/混入」bug。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y45 | ✅ |
| **Y46 — 版本面板預覽版本 previewVersion spec** | ✅（待 full suite 最終確認、版本面板 5 條 path 全 spec 收尾：讀 Y36／寫 Y43／還原 Y44／比對 Y45／預覽 Y46）|

### Sprint Y47 候選

- 預覽模式 bound path spec（需 doc 綁 model_id + res_id、Y39 鎖 unbound、補 bound 成功 path）
- 「列印」menu item spec
- 「匯入 DOCX」/「匯出 PDF」/「匯出 DOCX」menu item spec
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

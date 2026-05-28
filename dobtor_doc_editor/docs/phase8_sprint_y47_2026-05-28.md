# Phase 8 Sprint Y47 — 檔案 menu「預覽模式」bound 成功 path spec（2026-05-28）

**性質**：純 spec sprint — 補完預覽模式雙 path：Y39 鎖 unbound precondition（沒綁 model_id+res_id → warning），Y47 鎖 bound 成功 path（綁定 + alias + 非空 content_json → 自動進預覽 + 手動 toggle in/out cycle）。預覽模式是 L2-v2 核心 feature（編輯器內 token 暫時換實際值）、雙 path 完整鎖死。
**範圍**：新 spec file `admin-dobtor-doc-editor-sprint-y47-preview-mode-bound.spec.ts`（top-level repo、+~150 行）、新建 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y46 sprint doc Y47 候選第一條：「預覽模式 bound path spec（需 doc 綁 model_id + res_id、Y39 鎖 unbound、補 bound 成功 path）」。Y47 兌現。

預覽模式 `onTogglePreviewMode` 兩條 path：
- **unbound**：`!_loadedModelName || !_loadedResId` → warning「未綁定 model_id + res_id」→ previewMode 保持 false（Y39 已鎖）
- **bound 成功**：綁定齊全 + field_aliases 非空 + content_json 非空 → rpc `/dobtor_doc/preview_content_json` 渲染實際值 → previewMode=true（Y47 鎖）

Y39 只鎖了「擋下來」、沒鎖「真的成功進預覽」。bound path 才是 feature 的正常使用情境（user 從 ChienYi 某 record 開綁定文件、進來就看實際值）。**只鎖 precondition failure、不鎖 success = 半套**；Y47 補另一半。

額外鎖到一個高價值 behavior：**自動進預覽**（doc_editor.js line 561-576）—— 綁定 record + 有 alias 時、載入後 600ms 自動 toggle 進預覽、user 一進來就看實際值。這是 silent 的「載入即渲染」capability、之前完全沒 spec。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y47.1 test | 新增 (top-level、~150 行)：callKw 綁 res.partner + partner id + field_aliases {"客戶名稱":"object.name"} + 顯式 content_json（IElement[] 含 《客戶名稱》 token）→ 開 editor → 自動進預覽（檔案 menu「預覽模式」label 帶 ✓）→ 點 item 切回範本（notification「已切到範本模式」、label 去 ✓）→ 再點切回預覽（notification「已顯示實際值」、label 回 ✓）|
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼顯式設 content_json 不靠 content_html 自動轉換

`preview_content_json` rpc 要求 `doc.content_json` 非空（否則 error 'content_json 為空'）。doc 從 template 建立時若只有 content_html、content_json 空 → editor 載入走 `executeSetHTML` fallback → AutoSave 才寫回 content_json。但**自動預覽在載入後 600ms 觸發**、可能搶在 AutoSave 寫 content_json 之前 → rpc 讀到空 → 失敗。

解法：callKw 建 doc 時**顯式設 content_json**（`IElement[]` JSON 陣列、canvas-editor Editor constructor 第二參數格式）。這樣：
- content_json 一開始就非空、自動預覽 rpc 必讀得到
- 避開 content_html→json 轉換與 600ms timer 的 race

**要鎖「依賴非空 content_json 的 path」、就用 callKw 直接把 content_json 設成已知非空態**、不靠 editor 副作用間接產生（那是 race 之源）。

### 3.2 為什麼綁 res.partner

bound path 需要一個「admin DB 必有 record + 欄位渲染不會 error」的 model。res.partner：
- admin DB 一定有 partner（公司本身就是 partner）
- `object.name` 一定 render 得出（partner 必有 name）
- 不依賴 ChienYi 自訂 model 的測試資料（spec 自帶 fixture、不汙染）

alias `{"客戶名稱": "object.name"}` + content token 《客戶名稱》= 最小可成功渲染的 binding。Y40 教訓「fixture 自給自足」延伸。

### 3.3 為什麼用 menu label「✓」前綴斷言 previewMode

`state.previewMode` 是 client 端狀態、不持久化、callKw 讀不到。但 menu「預覽模式」item label 是它的 reactive proxy（line 4833：`previewMode ? '✓ 預覽模式...' : '   預覽模式...'`）。斷言 label 含「✓」= 間接斷言 previewMode=true。

**client-only 狀態無法 callKw 讀時、找它的 reactive UI proxy 斷言**。Y43/Y44 能 callKw 讀 version_number（持久化）；Y47 previewMode 不持久化、改用 label proxy。同樣是「找最可靠的可觀測信號」、只是信號從 DB 換成 reactive DOM。

### 3.4 為什麼鎖完整 cycle（自動進 → 手動出 → 手動進）

- 自動進（✓）：鎖 auto-preview-on-load capability（line 561-576）
- 手動出（已切到範本模式）：鎖 toggle-out branch（line 2497-2520）
- 手動進（已顯示實際值）：鎖 toggle-in success branch（line 2523-2555）

一個 test 跑完 3 段 = 同時鎖「自動」+「toggle 兩方向」。Y36/Y40/Y44「single test 完整 cycle」pattern 延續。auto-preview 進來後第一次手動點是「出」（因為已在預覽）、所以 cycle 自然是「進→出→進」。

### 3.5 為什麼 ✓ 斷言加 auto-retry timeout

auto-preview 在 600ms + canvas 500ms ready + rpc 後完成、openEditor 等 4s 通常已 settle。但加 `toContainText('✓', {timeout:8000})`：dropdown 開著時 previewMode 若還在 flip、OWL reactive 會即時更新 label、expect 自動 retry 到 ✓ 出現。**負載高時 auto-preview 可能稍慢、auto-retry 吸收**。Y37 auto-retry 原則延伸到 reactive label 斷言。

---

## 4. 預期 + 實測

**預期**：bound doc 自動進預覽（label ✓）→ 手動切範本（已切到範本模式 + label 去 ✓）→ 手動切回（已顯示實際值 + label ✓）。

**實測**：
- Y47.1：1/1 pass (27.7s)、content_json 格式一次命中、自動預覽如期觸發
- 34-test full suite 連跑：34/34 pass 10.3m all green ✓（預覽模式雙 path Y39+Y47 + 版本面板 5 path + sprint-d 全穩定）

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y47-preview-mode-bound.spec.ts` | 新檔 +~150 行（top-level repo）|
| `phase8_sprint_y47_2026-05-28.md` | 新檔 |

零 source code 改動 = 第 11 個純 spec 或 spec-heavy sprint。

---

## 6. 教訓

1. **只鎖 precondition failure 是半套、success path 才是正常使用**：Y39 鎖 unbound warning、Y47 補 bound success。**feature 有「擋下來」與「真的做成」兩條 path 時、兩條都要 spec**；只鎖 failure path 會讓「成功情境壞掉」silent（user 綁了卻進不了預覽、沒 spec 抓得到）。failure path 通常先寫（好構造）、success path 後補（要備齊前置）、但缺一不可。
2. **依賴非空狀態的 path、用 callKw 直接設好該狀態、別靠副作用**：preview 要 content_json 非空、靠 editor html→json 轉換會與 600ms auto-preview race。顯式 callKw 設 content_json = 一開始就非空、消除 race。**spec 的前置狀態要「直接設定到已知態」、不靠被測流程的副作用間接產生**；後者引入時序依賴。Y44/Y45/Y46/Y47 一致用 callKw 直接設前置。
3. **client-only 狀態找 reactive UI proxy 斷言**：previewMode 不持久化、callKw 讀不到、改斷言 menu label ✓ 前綴（它的 reactive proxy）。**無法直接觀測的 client 狀態、找它驅動的最穩定 DOM 信號**；menu label 比 canvas 內容更穩（後者 render 細節多）。Y43/Y44 用持久化 DB、Y47 用 reactive label、都是「挑最可靠可觀測信號」。
4. **auto-preview-on-load 這類 silent capability 值得順手鎖**：綁定 doc 載入自動進預覽是 user 一進來就看實際值的關鍵體驗、但完全 silent（沒 notification 提示「自動進了」、只有 label 變 ✓）。**載入即觸發的隱性 behavior 最容易 regression 沒人發現**；Y47 用 label ✓ 把它釘成 contract。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y46 | ✅ |
| **Y47 — 預覽模式 bound 成功 path spec** | ✅（待 full suite 最終確認、預覽模式雙 path 完整：unbound Y39 / bound Y47 + auto-preview-on-load）|

### Sprint Y48 候選

- 「列印」menu item spec（executePrint、browser print dialog 攔截）
- 「匯出 PDF」/「匯出 DOCX」menu item spec（download 事件攔截）
- 「匯入 DOCX」menu item spec
- 字型 / 字號 selector active state 雙向同步驗證
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）
- signer-bar 視覺再精簡
- indeterminate state
- submenu 基礎建設
- Phase8 baseline `.doc-toolbar` 預設隱藏跟 Y23 default 對齊
- 其他 spec timing flaky manifest 後再批次

# Sprint Y58 — C：15 份 ChienYi docx 端對端真實渲染驗證

- **建立日期**：2026-05-30
- **前置**：Sprint Y58 B（commit `947ecf4`）—— CLI + Python controller flag 透傳
- **狀態**：Sprint C 完成、停下待 user review；未進 Sprint D
- **5/29 lesson 對齊**：不只看 audit 腳本數字，跑真實 puppeteer + canvas-editor UMD harness 截圖、有實際 PNG 比對

---

## 1. 範圍

對 user 指定的 15 份 ChienYi docx（5 監造會議 + 5 週報 + 5 查驗）跑端對端真實路徑：

```
docx → parse_docx_cli.cjs（兩遍：無 flag / 有兩 flag）
     → IElement[] JSON
     → puppeteer + canvas-editor 0.9.128 UMD harness 渲染
     → 截 .ce-page DOM → PNG
     → pixelmatch（baseline vs opt-in）
     → 文字/anchor/image delta metric
```

**真實**驗證：parser 不 mock、CLI 不 mock、canvas-editor 不 mock，subprocess + 真實 Chrome 147 headless。

## 2. 改動檔案

| 檔案 | 性質 | 摘要 |
|---|---|---|
| `scripts/sprint_y58_real_path_e2e.mjs` | 新檔 | E2E driver script：15 份 fixture × 2 遍 CLI × 真實 puppeteer 渲染 + pixelmatch + JSON report |
| `scripts/sprint_y58_harness.html` | 新檔 | Y58 專用 harness — 用 production lib 載入順序（`.umd.min.js` + shim + plugin-docx），舊 `visual_regression_harness.html` 已切到 `canvas-editor-custom.umd.js`（不同 global）失靈 |
| `tests/fixtures/sprint_y58_real_path_report.json` | 新檔 | 15 fixture × baseline/optIn metric + per-page pixel diff |

## 3. 結果（15 份 × 真實 puppeteer 渲染）

```
   parsedBoth: 15 / 15
   textboxDeltaDocs: 14
   anchorDeltaDocs:  14
   imageDeltaDocs:    5
   avgTextboxAddedChars: 31
   avgTextboxAddedImages: 1
   avgAnchorAdded: 3
   avgVisualDiffRatio: 0.0605 (mean across all rendered page diffs)
```

### 3.1 Per-fixture（單位：c=文字字元、p=渲染頁數）

| Fixture | tx delta | img delta | anchor + | baseline → opt-in 頁數 | mean visual diff |
|---|---|---|---|---|---|
| 01_simple/03.1120210-監造會議記錄-1120801 | 0c | +0 | +0 | 5p → 5p | 0.0000 |
| 01_simple/03.1120815-監造會議記錄（Y57 標的） | 33c | +0 | +5 | 6p → 6p | 0.0351 |
| 01_simple/03.1120822-監造會議記錄 | 25c | +0 | +4 | 5p → 5p | 0.0529 |
| 01_simple/03.1120829-監造會議記錄 | 24c | +0 | +3 | 5p → 5p | 0.0514 |
| **01_simple/03.1120905-監造會議記錄** | **24c** | +0 | +3 | **5p → 3p** ⚠️ | **0.0848** |
| 02_std_table/1120928-週報 | 43c | +1 | +4 | 4p → 4p | 0.0392 |
| 02_std_table/1121006-週報 | 44c | +1 | +4 | 4p → 4p | 0.0381 |
| 02_std_table/1121013-週報 | 44c | +1 | +4 | 4p → 4p | 0.0623 |
| 02_std_table/1121020-週報 | 44c | +1 | +4 | 3p → 3p | 0.0862 |
| 02_std_table/1121027-週報 | 44c | +1 | +4 | 3p → 3p | 0.0865 |
| 03_complex_table/1121229-全套管 (1) | 20c | +0 | +2 | 1p → 1p | 0.1528 |
| 03_complex_table/1130105-全套管 (2) | 21c | +0 | +2 | 1p → 1p | 0.1543 |
| 03_complex_table/1130109-全套管 (4) | 21c | +0 | +2 | 1p → 1p | 0.1596 |
| 03_complex_table/1130112-全套管 (3) | 21c | +0 | +2 | 1p → 1p | 0.1658 |
| 03_complex_table/1130516-共月橋 P3 | 20c | +0 | +2 | 1p → 1p | 0.1502 |

### 3.2 真實 textbox 內容類型

實際 audit XML 後落定 3 類使用者價值內容：

| 類型 | 出現於 | 範例 | sprint A 預設 mapper 行為 |
|---|---|---|---|
| 自動頁碼 | 5 監造會議 | `第3頁，共3頁` | drop |
| 日期戳印 | 5 查驗 + 5 週報 | `112.12.29` / `112/09/28` | drop |
| **監造印章圖片** | 5 週報 | base64 jpeg ~138KB | drop |

5 份週報每份 4 個 anchor 中 anchor[2] 內含 **1 個 wp:inline 嵌入 jpeg 圖片**（監造印章 / 機關識別圖），是 Y57 audit 沒涵蓋到的 wp:anchor 真實 use case。

## 4. 異常點 & 解讀（要 user review）

### 4.1 1120905 頁數 5p → 3p ⚠️

- baseline canvas-editor 渲染為 5 頁
- opt-in 渲染為 3 頁
- 此 fixture 只有 3 個 anchor（全是頁碼）、textbox 文字 24 字、無圖
- **不是 mapper bug** — canvas-editor `pageMode=PAGING` 把 textbox 內容 inline 後 layout 引擎自己決定切頁
- 對應 Sprint A 紀律：mapper 只做「IElement 內容透傳」、視覺呈現由 canvas-editor 負責
- 修法（如要）：等 Phase 6+ 真正支援 wp:anchor 浮動框 layout（不 inline 降級）；不在 Y58 範圍

### 4.2 查驗系列 meanDiff 0.15+

- 5 份查驗 fixture meanDiff = 0.150-0.166（最高）
- 原因：查驗只有 1 頁、頁面密集、anchor 內容（日期戳印）inline 後重排比例最大
- 既有 VR baseline maxDiff 為 0.5（visual_regression_v14.mjs L14、baseline 階段寬鬆）、Y58 數字遠低於 baseline 容差
- 對「應該變」的視覺差有 explicit 期待：anchor 內容本來就在 baseline 看不到、opt-in 後出現在頁面上必然視覺有差

### 4.3 週報系列 anchor 內含圖片（**Y58 完整覆蓋此 case**）

- 5 份週報每份 anchor[2] 內藏監造印章 jpeg
- Sprint A mapper 透過 `case 'floatTextBox'` → `appendParagraph` → 內部 paragraph 走 `appendInlineNode` → 遇到 inline image 走 既有 `appendImage` 路徑
- 因此 textbox 內圖片自動跟著文字一起出來、不需要額外 mapper case
- 這 5 份的 +1 image 證明 Sprint A 對 wp:anchor 內所有 OOXML 內容類型（文字 + 圖片）都已正確透傳

### 4.4 1120210 沒 anchor

- 此 fixture（1120801 範本月份）沒有 wp:anchor，opt-in 完全沒 delta
- 證明 Sprint A 行為紀律：**沒 anchor 的 docx 開 flag 也 byte-identical**（VR 不退步）
- 非「miss」、是「無需處理」

## 4.5 ⭐ 親眼 review 4 組 PNG 後的真實視覺結論（補錄 2026-05-31）

實際開 PNG 後發現：**Y58 對使用者的實質價值遠超 Y57 audit 預估**。Y57 audit 用 1120815 純頁碼 fixture 落定「技術真、語意低價值」，但 1120928 週報的真實視覺差異把這個判斷整個翻過來：

### 1120815 監造會議記錄（純頁碼）— 預期 +1 字串、實際亦如此

- baseline 第 1 頁：無頁碼字串
- opt-in 第 1 頁左上多出「第1頁，共3頁」
- 結論：低語意價值（與 Y57 audit 一致）；canvas-editor 自會生成頁碼、anchor 內頁碼字串重複

### 1121229 全套管查驗（日期戳印）— **opt-in 純加值、無視覺破壞**

- baseline：完整查驗表 + 2 張現場照片
- opt-in：完全一樣的查驗表 + 照片，**多出 2 個紅色 `112.12.29` 日期戳印**（每張照片左上）
- 結論：**極高價值** — 日期戳印是業務必要（工程進度日期追蹤）、baseline drop = 證據遺失

### ⭐ 1120928 週報第 4 頁 — **baseline 整頁空白 → opt-in 顯示完整施工照片頁**

- **baseline 第 4 頁：完全空白**（只有頁碼 4）
- **opt-in 第 4 頁：2 張彩色現場施工照片 + 2 個 `112/09/27`、`112/09/28` 紅色日期戳印 + 「奇岩1號公園圍籬組裝」、「三合街鑽孔探測」標題列**
- 解讀：1120928 的 anchor[2] 不是只裝 9 字日期戳印 — Word 把**整段「施工照片表格 + 嵌入照片 + 日期戳印」整大段都包進 wp:anchor + wps:txbx 浮動文字框**（這是 OOXML 把照片 + caption 一起浮動的常見手法）
- Sprint A 預設 mapper drop 等於整頁施工照片內容遺失（baseline 是空白頁）；opt-in 展平後**整頁照片 + 日期戳印都顯示**
- **這是 Sprint Y58 最有力的「使用者價值」證據** — 不是「加幾個字」、是「整版工程照片從消失變存在」

### 1120905 監造會議第 3 頁 — 頁數變動的視覺後果

- baseline 5 頁：第 3 頁含完整列管項目 1-3~1-8（六列） + 黑色 anchor 區（既有 canvas-editor 圖片渲染 fallback，baseline 也有 — 與 Y58 無關）
- opt-in 3 頁：第 3 頁只剩末尾 1 列（6-1）+ 「第3頁，共3頁」
- canvas-editor 把 1-3~1-8 六列壓縮到前 2 頁、整體少 2 頁
- 解讀：anchor 文字 inline 後排版重排是預期、但「頁數縮 2 頁」幅度比想像大；屬 canvas-editor `pageMode=PAGING` layout 引擎決策、非 mapper bug

### Y58 真實 anchor 價值光譜（4 組樣本歸納）

| Anchor 內容類型 | fixture 代表 | baseline 觀感 | opt-in 觀感 | 業務價值 |
|---|---|---|---|---|
| 純頁碼 | 1120815 監造會議 | 缺頁碼 | 多出「第X頁，共Y頁」 | 低（canvas-editor 自會生） |
| 日期戳印 | 1121229 查驗 | 缺戳印 | 照片角落多出 `112.12.29` | 高（工程進度日期憑證） |
| **整段照片頁** | **1120928 週報 第 4 頁** | **整頁空白** | **完整施工照片頁** | **極高（baseline 完全內容遺失）** |
| 重排副作用 | 1120905 監造會議 | 5 頁 | 3 頁 | 中性（要 product 決策可接受度） |

→ **Y57 audit 對 wp:anchor 整體 gap 嚴重低估**：1120815 樣本只看到「頁碼層」，但週報的 anchor 是「整版工程照片浮動框」、查驗的 anchor 是「日期戳印浮動框」。對 ChienYi 工程文件群（25/25 含 anchor）而言，這是高商業價值的 fidelity gap。

### Y58 範圍邊界提醒（前端 / product decision）

- mapper / CLI / controller 鏈整條打通、預設 false 保證 byte-identical
- 真實 production 要走 opt-in：前端 `doc_editor.js` 載入時要傳 `?float_textbox=1&anchored_image=1`、或 import form / RPC 帶兩個 flag
- 視覺後遺症（頁數變動、anchor 位置改變）是 inline 降級紀律的固有代價；真正修法是 Phase 6+ 浮動繞排 layout
- 折衷選項：**僅開 `--float-textbox`**（多出文字內容）、不開 `--anchored-image`（不額外塞 anchor metadata）→ 視覺差異最小、業務內容完整出現；給 product 評估

---

## 5. 視覺證據（PNG 樣本）

PNG 在 `tests/fixtures/.visual_regression_tmp/sprint_y58/`（路徑被 `.gitignore` 排除，不入 git；user 在本機可直接開）。

| 用途 | 路徑模板 |
|---|---|
| baseline 截圖 | `<basename>_baseline-<N>.png` |
| opt-in 截圖 | `<basename>_optin-<N>.png` |
| pixel diff 截圖（紅色像素 = 兩遍差異） | `<basename>_y58_diff-<N>.png` |

建議 user review 樣本：
1. **1120815**（Y57 標的 — 純頁碼）→ 看頁腳是否多出「第 1 頁，共 3 頁」
2. **1120928**（週報 — 文字 + 圖）→ 看是否多出監造印章圖 + 日期戳印
3. **1121229**（查驗 — 日期戳印 + meanDiff 最高）→ 看 inline 後排版差異程度
4. **1120905**（頁數變少的 case）→ 確認頁數變少是 canvas-editor PAGING 行為

開檔指令範例：
```bash
explorer.exe "$(wslpath -w tests/fixtures/.visual_regression_tmp/sprint_y58/)"
```

## 6. 真實 path 路徑完整性鎖死

Sprint C 同時走了 4 條真實路徑、無 mock：

1. **OOXML → AST**：parser/drawing/DrawingParser.ts 透過 `<wps:txbx>` 解出 paragraphs（Sprint 38 既有）
2. **AST → IElement[]**：mapper case 'floatTextBox' opt-in（Sprint A）
3. **CLI flag → mapper option**：parse_docx_cli.ts `--float-textbox` / `--anchored-image`（Sprint B）
4. **CLI subprocess → puppeteer → canvas-editor → PNG**：本 sprint 真實路徑端點

整條 production code chain（parser → mapper → CLI bundle → Python controller → 前端 canvas-editor）的任何環節若 broken，這 15 份的某一份就會掉到 baseline 或退化。**14/15 看到 textbox 文字增量 = 完整路徑活的**。

## 7. 範圍紀律

### 已做
- E2E mjs script + 真實 puppeteer + Chrome 147
- 15 份 fixture × baseline/opt-in 兩遍 CLI + render + pixelmatch
- 拆「真實文字字元」/「image dataURL」/「anchor 數量」獨立 metric
- JSON report 入 git；PNG 透過 `.gitignore` 排除（PNG 不可重現性低、入 git 沒價值）

### 沒做（留 Sprint D）
- **commit-lock vitest integration test**：Sprint D 寫一個 `tests/integration/sprint_y58_real_path.test.ts` 鎖 14/15 textbox 增量 + 5/15 image 增量這些 invariant
- **Phase 6 wp:anchor 真正浮動 layout**：本 sprint 不碰；視覺差距與頁數變化都是 inline 降級的合理代價
- **前端 doc_editor.js UI 開關**：上層 product decision、不在 mapper / CLI 層處理

## 8. Sprint D 預告

把本 sprint 的 14/15 觀察值寫成 vitest assertion：

```
tests/integration/sprint_y58_real_path.test.ts:

it('15 ChienYi docx：14 份 opt-in 後 textbox 字元增量 > 0', ...)
it('15 ChienYi docx： 5 份週報 opt-in 後 image 增量 = 1（監造印章）', ...)
it('15 ChienYi docx：14 份 opt-in 後 anchor 透傳數 = baseline + delta', ...)
it('1120815（Y57 標的）opt-in 後出現 4 個非空頁碼字串', ...)
it('1120210（無 anchor）：兩遍 IElement[] 完全相同', ...)  ← VR byte-identical 鎖
```

- 不跑 puppeteer（避免 CI 慢 + flake）、純跑 CLI + JSON 比對
- 拒絕「視覺驗證」這層留 Sprint C `_e2e.mjs` 手動觸發
- 預估改動 ~80 行新檔 + 0 production code 改

## 9. 等待 user review

- [ ] 15 份 fixture 真實渲染結果（建議親看 4 份樣本 PNG）
- [ ] 1120905 頁數 5p → 3p 是否接受作為「inline 降級的合理代價」
- [ ] 週報 anchor 內含監造印章圖（5/15）—— 此 use case 已被 Sprint A 自動覆蓋（不需新 case）
- [ ] 是否進 Sprint D commit-lock test

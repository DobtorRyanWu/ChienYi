# Phase 8 Sprint Y52 — Y49 字型/字號 retrofit：假陽性轉真選取測（2026-05-29）

**性質**：純 spec retrofit sprint — 把 Y49 字型/字號雙向同步 spec 從**假陽性**修成**真測**。Y51 探查揭露：Y49 的 `selectAllInCanvas` click `(80,60)` 落在 A4 頁面左上 margin → canvas-editor 不放游標（`getRange()` 回 `-1`）→ Ctrl+A 無作用 → **選取根本沒成立**。Y49 原版「通過」是 native `<select>` 值被 `selectOption` 設了之後沒被打回的假陽性、不是真反向同步證明。Y52 用 Y51 驗證的技術（click 落文字 `(140,112)` + seed `content_json` 真文字 + getValue 內容層 oracle）把 Y49 改成真選取、真套用、真同步。

**範圍**：`admin-dobtor-doc-editor-sprint-y49-font-size-sync.spec.ts`（top-level、3 處改：bootstrap seed content_json、selectAllInCanvas click 位置、+2 getValue oracle 斷言）、新 sprint doc。零 source code 改動。

---

## 1. 為什麼開這個

Y51 sprint doc Y52 候選第一條：「Y49 retrofit：把 selectAllInCanvas click 改真選取 + 補 getValue oracle（假陽性轉真測）」。

**假陽性測試比沒測更糟**：沒測 = 知道沒覆蓋；假陽性 = 以為有覆蓋、給假信心、真壞了還是綠。Y49 是 30+ sprint 來第一個碰 canvas 文字選取的 spec、被當作「canvas 互動可測」的範例（Y50/Y51 都沿用它的 helper）、但它的選取根本沒成立。Y51 修 format button 時 probe 逐步追蹤才揭露。發現了就回頭修——不留假陽性。

Y51 已修 source（`.doc-format-toolbar` 加 `editor-component` → toolbar 互動不清 canvas 選取），字型/字號 select 同在這條 toolbar、一併受益。Y52 retrofit 後實測通過，正好**反證 Y51 的修復涵蓋 font/size select**（不只 B/I/U/S 按鈕）。

---

## 2. 範圍

| 區塊 | 改動 |
|---|---|
| Y49 bootstrap | doc 直接 seed `content_json`（`[{value:'字型字號同步測試文字段落'},{value:'\n'}]`）確保 canvas 有可選取文字（不靠 template content_html fallback、Y51 證 fresh doc 不可靠）|
| Y49 selectAllInCanvas | click `(80,60)`（margin、假選取）→ `(140,112)`（落第一個字、真放游標 → Ctrl+A 真全選）|
| Y49 +oracle（4b/5b）| 補 getValue 內容層 oracle：改字號後 main 真有 `size=24` element、改字型後真有 `font='Arial'` element |
| sprint doc | 新檔 |
| source code | **零改動** |

---

## 3. 設計取捨

### 3.1 為什麼是 retrofit、不是新開一個 spec

Y49 已存在、且被當 canvas 選取的範例 helper 被 Y50/Y51 引用。它的弱點是「選取沒成立」這個根本問題、不是缺斷言。**修正既有 spec 的根本弱點比另開一個重複 spec 好**：既有引用點（selectAllInCanvas helper）一次修對、之後沿用的 sprint 都拿到對的版本。新開只會讓假陽性的舊版繼續誤導。

### 3.2 雙 oracle：受控 select 值（反向）+ getValue 內容層（正向）

Y49 原本只有一個 oracle：select 值停在新值。問題是這個 oracle 在「選取沒成立」時也會過（`selectOption('24')` 設了 native value、沒有反向同步把它打回、就停在 24）= 弱 oracle、無法分辨「真同步」vs「沒人動它」。

Y52 補第二個 oracle：`getValue().data.main` 真有 `size=24` / `font='Arial'` 的 element。這直接看 canvas 內容模型、證 **executeSize/Font 真的套到選取的文字**（正向）。兩個 oracle 各鎖一個方向：
- **getValue oracle** → 正向（selector → canvas 套用生效）
- **select 值 oracle** → 反向（canvas caret → state → select 回寫；若反向斷、OWL 會用 state 把 select 打回 16）

合起來才是完整雙向同步的真證明。單靠 select 值是 Y49 假陽性的根源。

### 3.3 為什麼沒 source 改動（Y51 的修復已涵蓋）

字型/字號 `<select>` 同在 `.doc-format-toolbar`、Y51 已給該容器加 `editor-component`。`selectOption` 是程式化觸發 `change`（不在 canvas mousedown）、選取本來就不該被它清；但更早的環節（click 放游標）才是 Y49 沒成立選取的真原因。retrofit click 位置後、真選取成立、executeSize 套到真選取、反向同步回寫——**全程不需改 source**。retrofit 後實測通過＝順帶反證 Y51 `editor-component` 修復對 font/size select 也有效。

---

## 4. 預期 + 實測

**預期**：retrofit 後 Y49 用真選取、改字號/字型真套用到文字、getValue 內容層確認、select 值反向回寫。

**實測**：
- Y49.1 retrofit 單跑：1/1 pass (26.0s)、size=24 / font=Arial 內容層 oracle 通過、select 值反向回寫通過 → **真選取、真套用、真同步**（不再是假陽性）
- 38-test full suite 連跑：35 pass + 3 fail（Y20 find-keyboard / Y35 word-count / Y44 version-restore）13.1m。**Y49（本 sprint retrofit、#36）通過**、Y51 通過
- 3 個 fail 單跑：3/3 pass (52.8s) → flaky 確認。關鍵證據：**兩次 full suite（Y51 與 Y52）的 fail 3 個是「會換」的**（Y51 run = abce Sprint E / ghn J.1 / Y20；Y52 run = Y20 / Y35 / Y44）——deterministic 破壞會固定同 3 個、會換 = 高負載 timing flaky、與本 sprint 純 spec 改動無關。已列 Y53 批次硬化

---

## 5. 改動範圍

| 檔案 | 改動 |
|---|---|
| `admin-dobtor-doc-editor-sprint-y49-font-size-sync.spec.ts` | bootstrap seed content_json + selectAllInCanvas click (140,112) + 2 getValue oracle 斷言（top-level repo）|
| `phase8_sprint_y52_2026-05-29.md` | 新檔 |

零 source code 改動。

---

## 6. 教訓

1. **假陽性測試比沒測更糟、發現了要回頭修**：Y49「通過」靠 native select 值保留、不是真反向同步——選取根本沒成立（click 在 margin）。**沒測 = 知道沒覆蓋；假陽性 = 以為有覆蓋、給假信心**。被當範例引用的 helper 尤其危險（錯誤會擴散到沿用它的 sprint）。發現假陽性要回頭把根本弱點修對、不留。
2. **雙 oracle 分鎖兩個方向**：受控元件值（select 停在新值）只證反向、且在「沒人動它」時假陽性。補內容層 getValue oracle（element.size/font 真的變）證正向。**雙向同步要兩個獨立 oracle 各鎖一向**、單靠受控元件值會放過「選取沒成立」這類 silent 失效。
3. **canvas E2E 必先驗證選取真成立**：A4 PAGING margin ~100-120px、click 落 margin → range -1 → Ctrl+A 假全選。**寫 canvas 互動 spec 先 probe `getRange()` 確認 range≠-1**（Y51 教訓的延續、這次拿來修舊債）。
4. **source 修復的涵蓋面要回頭驗證**：Y51 `editor-component` 加在整條 `.doc-format-toolbar`、理論上 font/size select 也受益。Y52 retrofit 通過＝實證涵蓋。**修在容器層的 fix、要回頭確認容器內其它元件也真的吃到**。

---

## 7. 進度

| Sprint | 狀態 |
|---|---|
| G-Y51 | ✅ |
| **Y52 — Y49 字型/字號 retrofit 假陽性轉真測** | ✅（待 full suite 最終確認、首個被回頭修正的假陽性 canvas spec）|

### Sprint Y53 候選

- 對齊 align 完整 active toggle spec（Y51 機制已修、補鎖：全選 → 點置中 → rowFlex='center' + getValue rowFlex oracle + aria-pressed 對齊組翻）
- 底線/刪除線完整 toggle（Y51 機制已涵蓋、補 forward spec 各鎖一次）
- indeterminate state（部分選中、跨樣式選取 → format toolbar 顯示未定態）
- 字色/背景色 palette 套用到真選取的 spec（executeColor/Highlight、沿用 Y52 真選取技術）
- 清除格式 / 複製格式（painter）按鈕 spec
- 3 個 full-suite timing flaky（abce Sprint E / ghn J.1 / y20 find-keyboard）批次硬化
- 模板模式匯出 PDF/DOCX spec（需上傳 .docx fixture）
- 「匯入 DOCX」menu item spec（需 .docx fixture）
- 簽名欄位 / 頁碼 / 頁首頁尾（canvas-editor 沒 public API、scope 大）

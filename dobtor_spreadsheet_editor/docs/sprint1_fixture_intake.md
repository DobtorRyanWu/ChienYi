# Sprint 1 — Fixture Intake（ChienYi 實檔收集 + Golden 產生）

**日期**：2026-06-07
**Phase**：0（基建）→ 收尾
**對齊**：規劃書 §6 測試體系 + 附錄 A Phase 0 任務「收集 50 份真實台灣商業 xlsx」

---

## Root cause（開工前假設）

Sprint 0 建好 fixture 目錄骨架（8 類空夾 + golden/）與 `generate_golden.sh`，但 **0 份實檔**。
Phase 1 Parser 開發需要 golden 基準（cell value JSON + 渲染 PNG）才能寫 round-trip 測試，否則無從驗證還原度。
假設：ChienYi `工程資料/` 內的真實估驗/契約/變更 xlsx 足以填滿 8 類測試分類。

## 修法（實際做的事）

ETL 式三步，全程在 WSL host（openpyxl 3.1.5）+ container（python-calamine）：

1. **盤點去重**：`工程資料/磺港溪A標 + B標` 遞迴找 xlsx，排除 `~$` 暫存與 >5MB 照片型施工日誌
   → 776 全量 → 507 去重候選（by basename，取最小檔）
2. **特徵掃描**：openpyxl 逐檔抽 7 維特徵（sheets / merged / charts / cf / formulas / numfmts / maxcells）
   → 409 成功掃描（~98 檔載入失敗，多為舊版/受保護）→ `/tmp/sse_features.tsv`
3. **8 類分流**：貪婪分配 + **家族去重**（檔名去日期數字後同前綴每類限 1-2 份，避免管制表日期變體灌爆）
   → 48 份複製進 `tests/fixtures/<cat>/`（檔名清理：去空格/括號避免 golden script 字串插值破裂）
4. **Golden 產生**：`generate_golden.sh` 全 8 類 → 48×(PNG via LibreOffice headless + cells.json via calamine)

## 分流結果

| 類 | 目標 | 實收 | 代表檔 |
|---|---|---|---|
| 01_simple_formula | 8 | 8 | 單價分析、議價後會計室調整 |
| 02_merged_cells | 8 | 8 | A管制表(43 sheet/3424 合併)、水利處督導表 |
| 03_number_format | 6 | 6 | B標四變明細(27 自訂格式) |
| 04_conditional_format | 6 | **5** | 土單(cf4)、預定進度天天表 |
| 05_multi_sheet | 5 | 5 | A管制表、5變數量計算(38 sheet/29k 公式) |
| 06_chart | 5 | 5 | 北投進度 S 曲線、自主檢查統計 |
| 07_pivot | 4 | **1** | 土方統計(唯一含 pivotCache) |
| 08_chienyii_business | 10 | 10 | 契約詳細表(16 sheet/65548 公式)、估驗差異表、變更金額分析 |
| **合計** | **50** | **48** | |

## 三層 SOP 結果

- **L1 vitest**：跳過（本 sprint 0 程式碼變動、純資料 + docs）；既有 2/2 不受影響
- **L2 visual regression**：N/A（Parser 未開展、VR pipeline Phase 4+ 才接）
- **L3 人工檢查**：
  - 48 份 golden 全產出（48 PNG + 48 JSON）、`grep` 無 calamine 失敗
  - 旗艦契約詳細表 cells.json = 16 sheet（與原檔 sheet 數一致）、首 sheet 505 列
  - PNG 經 LibreOffice 確認非錯誤輸出（契約詳細表 PNG 214KB）

## 負面結果（結構價值，紀律 #4）

1. **04 CF + 07 pivot 無法用實檔填滿**（缺 1+3=4 份）
   - **事實**（非猜測）：409 掃描檔中僅 **6 份有條件格式、1 份有 pivotCache、3 份有 chart**
   - **根因**：營造監造文件以表格/公式/合併格為主，幾乎不用 colorScale/dataBar/pivot — 這是文件本質，非收集不力
   - **對策**：Sprint 2 用通用 OOXML 測試檔（GitHub `python-openpyxl`/`SheetJS` 測試集）或合成最小 CF/pivot fixture 補滿；README 原本就標註 01/04 類可用通用模板
2. **PNG golden 僅首 sheet**：LibreOffice `--convert-to png` 對多 sheet 活頁簿只渲染第一張
   - 影響 05/08 多 sheet 檔的 VR 覆蓋；cell value JSON 不受影響（calamine 讀全 sheet）
   - 對策：Phase 4 VR 接入時改用「每 sheet 匯出」或 headless Calc script
3. **管制表日期變體**：同一活頁簿有數十個日期版本 — 家族去重已限每類 1-2 份，但 02 仍含 2-3 個 1141113 變體（fam 鍵的「-勇」後綴差異）；可接受（最豐富的合併格樣本）

## 產物

- `tests/fixtures/{01..08}/*.xlsx`（48）+ `tests/fixtures/{01..08}/golden/*.{png,cells.json}`（96）
- 掃描中繼檔：`/tmp/sse_features.tsv`、`/tmp/sse_plan.tsv`（非 git 追蹤）

## 下一步（Sprint 2）

1. 補 04×1 + 07×3 通用/合成 fixture → 達 50
2. ADR-001（不 fork o-spreadsheet）/ ADR-002（OOXML parser 邊界）編號簽核
3. Phase 0 Exit review → 開 Phase 1 SpreadsheetML Parser（sheet1.xml + sharedStrings + styles.xml 解析）

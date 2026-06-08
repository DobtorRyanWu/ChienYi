# Sprint 34 — colorScale CF 編譯（Phase 4.1）

**日期**：2026-06-08｜**Phase**：4

## 修法（cf_compiler.ts）
- `compileColorScale`：CF colorScale（cfvo + colors）→ o-spreadsheet **ColorScaleRule**
  - minimum = cfvo[0]+colors[0]、maximum = cfvo[last]+colors[last]、midpoint = 3色時 cfvo[1]+colors[1] 否則 null
  - cfvo type 映射：min/max→value、num→number、percent→percentage、percentile→percentile、formula→formula
  - **color 為 RGB 整數**（o-spreadsheet colorNumberString(threshold.color) 確認；parseInt(resolveColor 去 alpha,16)）
- OConditionalFormat.rule 改 union（OCellIsRule | OColorScaleRule）

## 三層 SOP
- L1 vitest **580 passed**（+2：3色 min/mid/max RGB 整數、2色 midpoint null + num value；openpyxl 產 colorScale 匯入編譯）
- L2 Playwright（openpyxl 產 colorscale.xlsx、E1:E20=5..100、紅→percentile50黃→綠）：
  **COLORSCALE_GRID_MOUNTED errs=none**、無 o_error_dialog；**截圖確認平滑紅橙黃綠漸層**
- L3 tsc 乾淨、build、docker -u 升級無誤

## 結果
CF 編譯三型：cellIs（S29）+ containsText（S29）+ **colorScale 2/3 色（S34）**。
ChienYi 無 colorScale 資料 → 用 openpyxl 合成 fixture 驗證。

## 待解
- dataBar/iconSet 編譯（o-spreadsheet 有 DataBarRule/IconSetRule）；duplicateValues/expression（無直接對應）

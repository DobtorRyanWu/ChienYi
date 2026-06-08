# Sprint 37 — dataBar CF 編譯（Phase 4.1）

**日期**：2026-06-08｜**Phase**：4

## 修法（cf_compiler.ts）
- dataBar → o-spreadsheet **DataBarRule**：`{type:'DataBarRule', color: RGB 整數}`（color = colorToNumber(dataBar.color)）
  bar 長度由 CF range 值自動推算（rangeValues 省略）
- OConditionalFormat.rule union 加 ODataBarRule

## 三層 SOP
- L1 vitest **602 passed**（+1：dataBar→DataBarRule RGB 整數色；openpyxl 產 databar 匯入編譯）
- L2 Playwright（openpyxl databar.xlsx、B1:B20=3..60、藍色 638EC6）：
  **DATABAR_GRID_MOUNTED errs=none**；**截圖確認藍色長條隨值遞增**
- L3 tsc 乾淨、build、docker -u 升級無誤

## CF 編譯進度（5 型中 4 型）
cellIs（S29）+ containsText（S29）+ colorScale（S34）+ **dataBar（S37）**。
iconSet 待解（o-spreadsheet IconSetRule 的 icons/inflectionPoint 結構在 minified bundle 無法精準取得，
避免 #ERROR 暫不編譯）。duplicateValues/expression 無 o-spreadsheet 直接對應。

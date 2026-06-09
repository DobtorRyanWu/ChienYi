# Sprint 48 — CSV 檔支援（新能力，超出原規劃 xlsx-only）

**日期**：2026-06-09｜**Phase**：擴充

## 內容
除 xlsx 外，新增 **.csv** 上傳→預覽→可編輯 o-spreadsheet。

## 修法
- `csv_parser.ts`：
  - `parseCsv`：RFC 4180（雙引號包覆含逗號/換行、"" 跳脫、CRLF、去 BOM、無結尾換行不漏）
  - `csvToOSpreadsheetData`：單一工作表、純值（o-spreadsheet 自動辨識數字）
  - `csvToHtmlPreview`：HTML table 預覽（前 500 列）
- `index.ts`：importCsvToOSpreadsheetData / importCsvToHtmlPreview 進入點
- OWL `xlsx_import.js`：偵測 .csv 副檔名 → **UTF-8 解碼（亂碼時 fallback Big5，台灣舊檔）** → 路由預覽/開啟
- 模板 accept `.xlsx,.csv,.xls`；CSV 隱藏「下載 xlsx round-trip」

## 三層 SOP
- L1 vitest **666 passed**（+8 csv：逗號/引號/CRLF/BOM/無結尾換行/空欄、轉 WorkbookData）
- L2 Playwright（sample.csv 含引號逗號中文）：**CSV_PREVIEW_OK=1 + CSV_GRID_MOUNTED errs=none**；
  **截圖確認「鋼筋, 含運」成單格、中文、數字右對齊**
- L3 tsc/build/升級無誤

## 待解
- CSV→xlsx 下載（目前 CSV 不提供 round-trip 下載）；分隔符偵測（目前僅逗號，未支援 Tab/分號）

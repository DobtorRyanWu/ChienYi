# Sprint 39 — Excel Tables（§1.11）+ numeric entity 修復

**日期**：2026-06-08｜**Phase**：1 / 5

## Excel Tables（§1.11）
- `table_parser.ts`：tableN.xml → ParsedTable（ref/totalsRowShown/tableStyleInfo name/showRowStripes/...）
- `table_compiler.ts`：resolveSheetTables（worksheet rels→table part）→ o-spreadsheet table
  `{range, type:'static', config:{hasFilters, totalRow, firstColumn, lastColumn, numberOfHeaders:1, bandedRows, bandedColumns, styleId}}`
  - o-spreadsheet styleId 與 Excel 同名（TableStyleMedium9 等）→ 直接對映
- to_ospreadsheet/index：每 sheet resolveSheetTables → sheet.tables

## numeric character reference 解碼修復（連帶 bug）
table fixture（openpyxl）用 inline string + `&#NNNN;` 編碼中文 → 顯示 `&#38917;&#27425;`。
fast-xml-parser 不解 numeric reference（真實 Excel 多寫 UTF-8 故潛伏）。
→ `xml_util.textOf` 加 `decodeNumericEntities`（`&#NNNN;`/`&#xHHHH;`）。提取率 99.998% 不受影響（real 檔無 &#）。

## 三層 SOP
- L1 vitest **618 passed**（+table 解析/匯入、numeric entity A1=項次）
- L2 Playwright（openpyxl table.xlsx）：**TABLE_GRID_MOUNTED errs=none**；
  **截圖確認表頭 項次/名稱/金額（中文修復）+ 帶狀列 + 篩選按鈕 + TableStyleMedium9**
- L3 tsc 乾淨、build、docker -u 升級無誤

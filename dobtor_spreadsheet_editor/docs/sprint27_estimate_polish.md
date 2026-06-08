# Sprint 27 — 估驗表欄寬/數字格式/縮排 + 修 format inline bug（Phase 8）

**日期**：2026-06-08｜**Phase**：8

## 修法（bridge _build_estimate_workbook_data）
- **欄寬**：cols sizes（項目編號72/說明300/單位48/數值欄84-110 px）→ 說明欄完整可讀
- **數字格式**：D-J 數值/金額欄套 `#,##0.00`（千分位）
- **層級縮排**：說明欄依 item_no 點數加全形空白前綴

## 揭示並修正：o-spreadsheet format 是 inline 字串非 id-pool
初版套 `cell.format=1`（id）+ `formats:{1:'#,##0.00'}` → **D-J 全 #ERROR**。
查 o_spreadsheet.js：`getItemId(cell.format, data.formats)` → **載入時把 cell.format（字串）intern 成 id**。
故輸入的 cell.format 應為**格式字串**、formats 池留空（o-spreadsheet 自建）。
- bridge：`cell.format = "#,##0.00"`、`formats: {}`
- **連帶修 `to_ospreadsheet.ts`（匯入路徑同 bug）**：移除 formatPool、`oCell.format = numFmtCode`（字串）、`formats: {}`
  （ChienYi 格式多含 `_` 被 isOSpreadsheetSafeFormat 擋掉、從未真套過 format，故此 bug 潛伏至今）

## 三層 SOP
- L1 vitest 551 passed（to_ospreadsheet 測試改 inline format 斷言）
- L2 Playwright：generate GENERATE_GRID_MOUNTED（#ERROR 消失、數字+千分位+寬說明欄）；
  import standalone GRID_MOUNTED 無回歸
- L3 tsc 乾淨、build 通過、docker -u 升級無誤

## 結果
| | 前 | 後 |
|---|---|---|
| format | id-pool → #ERROR | **inline 字串、正常** |
| 說明欄 | 窄（截斷） | 寬 300px 完整 |
| 數值 | 無格式 | #,##0.00 千分位 |

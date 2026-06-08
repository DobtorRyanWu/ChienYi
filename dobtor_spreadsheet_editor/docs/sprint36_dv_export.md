# Sprint 36 — DV 匯出回 xlsx（Phase 6 §6.2）

**日期**：2026-06-08｜**Phase**：6

## 修法
- `dv_writer.ts`：DataValidation[] → `<dataValidations><dataValidation type operator allowBlank sqref><formula1/><formula2/></dataValidation>`
- `xlsx_writer.ts`：WriteSheet.dataValidations；sheetXml 在 conditionalFormatting 後寫 DV
- `index.exportXlsxFromBuffer`：每 sheet 帶 ws.dataValidations

## 三層 SOP
- L1 vitest **594 passed**（+1：匯出檔 re-parse 仍得 isValueInList）
- L2 openpyxl：匯出自檢表 → **DV 數 4**；LibreOffice 開啟 ✓
- L3 tsc 乾淨、build 通過

## 結果
DV 雙向：xlsx → 解析（§1.8 S35）→ 編譯 o-spreadsheet（§4.2 S35）→ 匯出回 xlsx（S36）。

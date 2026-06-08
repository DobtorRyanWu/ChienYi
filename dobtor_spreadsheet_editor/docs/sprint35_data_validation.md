# Sprint 35 — Data Validation（§1.8 解析 + §4.2 編譯）

**日期**：2026-06-08｜**Phase**：1 / 4

## 緣由
真實 ChienYi 自檢表/自主檢查統計含 4 個 `type="list"` 下拉（inline `"opt1,opt2,opt3"`）。
本 sprint 補 DV 解析 + 編譯到 o-spreadsheet（下拉在可編輯試算表生效）。

## 修法
- `dv_parser.ts`（§1.8）：worksheet `<dataValidations>` → DataValidation[]（type/operator/ranges(sqref)/formula1/formula2/allowBlank）
- `worksheet_parser.ts`：ParsedWorksheet 加 dataValidations + parseDataValidations
- `dv_compiler.ts`（§4.2）：DataValidation → o-spreadsheet dataValidationRules
  - list inline（`"a,b,c"`）→ **isValueInList**（逗號分割、displayStyle arrow）
  - list 範圍（`$X$1:$X$5`）→ **isValueInRange**
  - whole/decimal/date + operator → isBetween/isEqual/isGreaterThan
- `to_ospreadsheet.ts`：OSheet.dataValidationRules = compileDataValidations(ws.dataValidations, sheetId)

## 三層 SOP
- L1 vitest **593 passed**（+6：list inline 分割/range/whole between/id 前綴 + 真實自檢表 isValueInList）
- L2 Playwright：自檢表（4 DV + chart）匯入開啟 **errs=none、無 o_error_dialog** → o-spreadsheet 接受 DV rules
- L3 tsc 乾淨、build、docker -u 升級無誤

## 結果
ChienYi 自檢表下拉清單在可編輯 o-spreadsheet 生效（值清單分割正確）。

## 待解
- custom / textLength（無 operator）型別未編譯；DV 匯出回 xlsx（Phase 6）

# Sprint 29 — CF 編譯到 o-spreadsheet（Phase 4.1）

**日期**：2026-06-08｜**Phase**：4

## Root cause
§1.7 已**解析** CF（ConditionalFormatting[]），但 to_ospreadsheet 的 conditionalFormats 一直是 `[]`
——匯入的 xlsx 條件格式在可編輯試算表不顯示。本 sprint 補**編譯**。

## 修法
- 新 `cf_compiler.ts`：CF AST → o-spreadsheet conditionalFormats
  - **CellIsRule**：cellIs operator（equal/greaterThan/between… → Equal/GreaterThan/Between…）+ formulas→values + dxf→style
  - **containsText 系列**：containsText/notContains/beginsWith/endsWith → o-spreadsheet operator + text 值
  - dxfId → dxf → style（bold/italic/strike/underline + textColor + fillColor，theme 解析具體 RGB；CF dxf 填色慣例取 bgColor）
  - 超大範圍夾到 sheet maxRow/maxCol（避免 D1:D1048576）；id 帶 sheet 前綴
  - colorScale/dataBar/iconSet/duplicateValues/expression v1 不編譯（o-spreadsheet 無直接對應/色彩格式待確認）
- `to_ospreadsheet.ts`：buildSheet 建 ThemeResolver → `conditionalFormats: compileConditionalFormats(...)`

## 三層 SOP
- L1 vitest **558 passed**（+7 cf_compiler：cellIs Equal/Between 雙值/containsText/dup 略過/範圍夾取/id 前綴 + 真實土單匯入產生 CellIsRule）
- L2 Playwright（土單含 CF）：**CF_GRID_MOUNTED errs=none**、無 o_error_dialog → o-spreadsheet 接受編譯的 CF
- L3 tsc 乾淨、build 通過、docker -u 升級無誤

## 結果
| | 前 | 後 |
|---|---|---|
| 匯入 CF | 解析但 conditionalFormats=[] | **編譯成 CellIsRule、o-spreadsheet 渲染** |

## 待解
- colorScale/dataBar/iconSet（o-spreadsheet 有 ColorScaleRule/DataBarRule/IconSetRule，色彩/threshold 格式待對；ChienYi 無此資料）
- duplicateValues/expression（o-spreadsheet 無直接對應）
- CF 匯出回 xlsx（Phase 6 §6.2）尚未做

# Sprint 45 — 會計負數紅字 [Red]（§2.3）+ numFmt 寬容套用

**日期**：2026-06-09｜**Phase**：2

## 重要發現（修正錯誤假設）
初判 o-spreadsheet 支援 [Red] 格式 token（grep 誤判）→ 直接餵會計格式 → **#ERROR**。
page.evaluate 探測 formatValue：**o-spreadsheet 格式引擎不支援 [Red]**（"Unknown token at [Red]"），
亦不支援 `_` padding / `\` 跳脫的完整會計格式。

## 修法
- `to_ospreadsheet.ts`：
  - `toSafeNumberFormat(code)`：取**正數段**、去 `_X`/`\X`/`[...]` token → 純數字格式（如 `#,##0.00`）；否則 undefined
  - `hasRedNegativeFormat(code)`：負數段（第 2 段）含 [Red]
  - 負值 + [Red] 負數段 → **靜態紅字 textColor #FF0000**（o-spreadsheet 不支援格式色彩）
- `style_resolver.ts`（連帶修，Excel 相容）：cellXf 自身 numFmtId≠0 時直接採用，
  不因省略 applyNumberFormat 而忽略（openpyxl 等工具常省略；Excel/calamine 寬容）

## 三層 SOP
- L1 vitest **653 passed**（會計 [Red] 負數→0.00+紅字、[$NT$]→#,##0.00、"元"→無格式）；提取率 **99.998% 不變**
- L2 Playwright（accounting.xlsx）：**ACCOUNTING_GRID_MOUNTED errs=none**；
  **截圖確認 B1=1,234.50（黑）、B2=-678.90（紅）、B5=-12,345.67（紅）、無 #ERROR**
- L3 tsc 乾淨、build、docker -u 升級無誤

## 結果
ChienYi 會計格式：正數千分位、**負數紅字**、無 #ERROR。numFmt 寬容套用順帶讓 openpyxl 類檔的格式生效。

## 待解
- 紅字為靜態（依匯入時值）；編輯改成負值不會自動變紅（o-spreadsheet 格式引擎限制）。

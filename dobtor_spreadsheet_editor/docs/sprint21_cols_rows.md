# Sprint 21 — 欄寬/列高回寫（版面保真，Phase 6）

**日期**：2026-06-07｜**Phase**：6

## 修法
- `worksheet_parser.ts`：擷取 row `ht`（customHeight=1）→ `ParsedWorksheet.rowHeights: Map<row,pt>`
- `xlsx_writer.ts`：`WriteSheet.cols`（min/max/width 字元）+ `rowHeights` → 寫 `<cols>`（dimension 後、sheetData 前）+ row `ht customHeight`；**只有列高的空列也寫出**（rowSet = 有cell ∪ 有列高）
- `index.ts` exportXlsxFromBuffer：傳 ws.cols（有 width 者）+ ws.rowHeights

## 三層 SOP
- L1 vitest 551 passed（+2：欄寬/列高 round-trip）
- L2 openpyxl：export 11309 → 自訂欄寬 9 / 列高 6、**C欄寬 4.25、第1列高 30.75**（與源檔一致）
- L3 tsc 乾淨、build 通過、docker -u 升級重啟無誤

## 待解
- 隱藏欄/列、bestFit、outline 未回寫；sheetFormatPr 預設寬高未寫

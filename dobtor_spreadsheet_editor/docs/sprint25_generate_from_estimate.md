# Sprint 25 — 從估驗工項產生試算表（Phase 8）

**日期**：2026-06-08｜**Phase**：8（ChienYi 整合）

## Root cause
前面都是 xlsx → 試算表（匯入方向）。估驗工作常需把**既有工項資料**直接變成可編輯試算表，
不必先有 xlsx 檔。本 sprint 補反向：估驗 line_ids → 可編輯 o-spreadsheet。

## 架構決策
WorkbookData 是純 JSON dict → **直接在 bridge Python 建構**（不需 TS bundle），server-side 建記錄 +
回傳開啟動作。最簡、可測、無 client-side 依賴。

## 修法（bridge payment_estimate.py）
- `_SSE_COLUMNS`：10 欄（項目編號/說明/單位/契約數量/核定數量/單價/本次估驗數量/金額/累計數量/金額）
- `_build_estimate_workbook_data()`：標題列 + 粗體表頭 + line_ids（依 sequence）資料列 → WorkbookData
  （cells {ref:{content,style}}、styles {1:{bold}}、數字以 repr 寫 content 由 o-spreadsheet 解析）
- `action_generate_spreadsheet()`：建 spreadsheet.spreadsheet（回掛 payment_estimate_id）→ 回傳
  action_spreadsheet_oca 開啟動作
- view：header 加「從工項產生試算表」按鈕（type=object, invisible="not line_ids"）

## 三層 SOP
- L1：N/A（純 Python/XML）；既有 vitest/standalone Playwright 不受影響
- L2 Playwright E2E（估驗 33、181 工項）：GENERATE_BUTTON_VISIBLE → **GENERATE_GRID_MOUNTED**
  → DB spreadsheet id19「第17次估驗計價 工項試算表」payment_estimate_id=33
  截圖：標題粗體 + 粗體表頭 + 181 工項資料（數字正確、右對齊）
- L3 docker -u 升級無誤

## 雙向整合全貌
- xlsx → 可編輯試算表（匯入，S15-18）
- **估驗工項 → 可編輯試算表（產生，本 sprint）**
- 可編輯試算表 → xlsx（匯出，S19-21）
- 全部回掛估驗（S23）

## 待解
- 產生的試算表為值（非公式）；可後續讓金額欄=數量×單價公式
- 樹狀縮排/分層樣式、欄寬未套（v1 純表格）

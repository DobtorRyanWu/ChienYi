# Sprint 23 — 估驗 context 帶入 + 試算表回掛（Phase 8）

**日期**：2026-06-08｜**Phase**：8（ChienYi 整合）

## Root cause
Sprint 22 的「匯入估驗試算表」開的是通用 UI、未帶 estimate context，匯入的試算表也未關聯估驗。
本 sprint 讓匯入的試算表回掛到該估驗、估驗表單顯示關聯試算表。

## 修法
### bridge 模組 dobtor_spreadsheet_editor_chienyi
- `models/spreadsheet_spreadsheet.py`：擴 `spreadsheet.spreadsheet` 加 `payment_estimate_id`（many2one, ondelete set null）
- `models/payment_estimate.py`：`spreadsheet_ids`(one2many) + `spreadsheet_count`(compute) + `action_open_spreadsheets`
- `views/payment_estimate_views.xml`：匯入按鈕 `context="{'sse_create_vals': {'payment_estimate_id': id}}"`
  + 「關聯試算表」smart button（spreadsheet_count）

### 通用元件（保持業務無關）
- `xlsx_import.js`：開 o-spreadsheet 建記錄時，併入 **命名空間 context `sse_create_vals`** 的欄位
  （`{name, spreadsheet_raw, ...ctx.sse_create_vals}`）。通用元件只轉發 vals dict、不知業務欄位名，
  避免 default_* 污染。

## 三層 SOP
- L1：N/A（Python/XML + JS 元件；vitest 主模組 551 不受影響）；standalone Playwright 無回歸（GRID_MOUNTED + DOWNLOAD_OK）
- L2 Playwright E2E（bridge spec 完整鏈）：
  估驗 5 → BRIDGE_BUTTON_VISIBLE → 開匯入 → 上傳 → 開 o-spreadsheet
  → **DB 驗證 spreadsheet id 11 payment_estimate_id=5（回掛成立）**
  → 回估驗 → **BRIDGE_LINKED_SMART_BUTTON_VISIBLE「關聯試算表」**（截圖顯示 ⊞2 關聯試算表）
- L3 docker -u 升級無誤、payment_estimate_id 欄位建立

## 流程
估驗計價 →「匯入估驗試算表」→ 解析 → 開 o-spreadsheet（建記錄 + 回掛估驗）→
估驗「關聯試算表」smart button → 開回掛的試算表

## 負面結果 / 待解（紀律 #4）
- **巢狀開啟 transient 錯誤**：估驗→匯入→開 o-spreadsheet（3 層巢狀 action）後出現 Odoo 錯誤對話框
  （server log 為 session `b''` / 資源載入，非本模組邏輯；standalone 開啟正常 GRID_MOUNTED）。
  試算表仍正確建立+回掛；建議從「關聯試算表」smart button（top-level action）開啟回掛試算表。
  → 後續查 OCA spreadsheet 多層 action / ImageFileStore 空 res 問題。

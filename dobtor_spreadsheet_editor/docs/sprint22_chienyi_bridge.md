# Sprint 22 — 持久化 + ChienYi 估驗計價整合（Phase 8）

**日期**：2026-06-08｜**Phase**：8（ChienYi 整合）

## 架構決策（紀律：乾淨模組）
通用編輯器 `dobtor_spreadsheet_editor` **保持與業務無關**；ChienYi 整合放**獨立 bridge 模組**
`dobtor_spreadsheet_editor_chienyi`（比照 `dobtor_doc_editor_chienyi` 既有模式），避免把
construction_payment 依賴塞進通用編輯器。

## 修法
- 新模組 `dobtor_spreadsheet_editor_chienyi`：depends [dobtor_spreadsheet_editor, construction_payment]
- `views/payment_estimate_views.xml`：inherit `construction_payment.view_payment_estimate_form`，
  header 加 `<button type="action" name="%(dobtor_spreadsheet_editor.action_xlsx_import)d" string="匯入估驗試算表"/>`

## 持久化
- 「在 o-spreadsheet 開啟」已建 `spreadsheet.spreadsheet` 記錄（OCA、**DB 持久化**，出現在 Spreadsheets 清單）。
  本 sprint 不需額外持久化層；估驗匯入入口即接此流程。

## 三層 SOP
- L1：N/A（純 view/manifest，無 TS 變動；主模組 vitest 551 不受影響）
- L2 Playwright E2E（`admin-dobtor-sse-estimate-bridge.spec.ts`）：
  開 payment.estimate(id 5) → **BRIDGE_BUTTON_VISIBLE「匯入估驗試算表」** → 點擊 →
  **BRIDGE_OPENED_IMPORT**（url action-348/5/action-548）→ Xlsx 匯入 file input 出現
  截圖：按鈕與既有「開啟線上文件」(doc bridge) 並列
- L3：docker -i 安裝無誤、module installed、view 載入

## 流程
估驗計價記錄 →「匯入估驗試算表」→ Xlsx 高保真匯入（解析 → 預覽 → 可編輯 o-spreadsheet / 下載 xlsx）

## 待解
- 按鈕開的是通用匯入 UI、未帶 estimate context（v1）；後續可傳 default_estimate_id 並把匯入的試算表
  回掛到該估驗記錄（spreadsheet ↔ estimate 關聯）。

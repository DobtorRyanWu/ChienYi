# Sprint 24 — 修巢狀開啟 o-spreadsheet 錯誤（Phase 8 收尾）

**日期**：2026-06-08｜**Phase**：8

## Root cause（兩個疊加 bug）
Sprint 23 揭示：估驗→匯入→開 o-spreadsheet（3 層巢狀）出現 Odoo 錯誤對話框。Playwright pageerror 拆出兩因：
1. **`Error: Component is destroyed`**：`openInOSpreadsheet` 的 `finally { state.opening=false }` 在
   `await doAction` 導航**銷毀本元件後**才跑 → 對已銷毀元件設 state。
2. **`Cannot find component "Dropdown"`**：o-spreadsheet 在深層巢狀 action 掛載時 asset/子元件載入失敗。

## 修法
### `xlsx_import.js`
- 移除 `finally`；在 `doAction` **前**重置 `state.opening`，錯誤只在 catch 重置（不再 post-destroy 碰 state）
- `doAction(action, { clearBreadcrumbs: true })`：o-spreadsheet 以 **top-level 開啟**（等同 standalone），
  避開深層巢狀 asset/元件載入問題

### bridge view
- `//div[@class='oe_title']` → `//div[hasclass('oe_title')]`（消 Odoo 18「Error-prone @class」警告）

## 三層 SOP
- L1：standalone Playwright 無回歸（GRID_MOUNTED + DOWNLOAD_OK，URL 變 top-level action_spreadsheet_oca）
- L2 Playwright bridge 完整鏈：BUTTON_VISIBLE → OPENED_IMPORT → **GRID_MOUNTED（巢狀修好）** → LINKED_SMART_BUTTON
- L3 docker -u 升級無誤、@class 警告消除

## 結果
| | Sprint 23 | Sprint 24 |
|---|---|---|
| 巢狀開啟 o-spreadsheet | ❌ ERRDIALOG | ✅ GRID_MOUNTED |
| Component is destroyed | ❌ | ✅ 修掉 |
| @class 警告 | ⚠️ | ✅ hasclass |

剩餘 console error `@dobtor_d...`（doc_editor 模組未在 bundle）為他模組既有問題、不阻斷。

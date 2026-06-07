# Sprint 16 — o-spreadsheet 可編輯對接（Phase 4.5）

**日期**：2026-06-07
**Phase**：4.5（產品化）
**對齊**：規劃書 §結論「parser → ConcreteStyle → o-spreadsheet model commands」

---

## Root cause（開工前假設）

Sprint 15 的 Odoo UI 只有唯讀 HTML 預覽。要「可編輯」，需把解析結果餵進 o-spreadsheet。
假設：產 o-spreadsheet WorkbookData JSON，交給 **OCA 既有的 spreadsheet 記錄 + 開啟 action**
（不自己掛 o-spreadsheet store，避免 v18 store API 風險），即可得可編輯試算表——真正「繼承 OCA」。

## 調查（o-spreadsheet / OCA 事實）

- OCA SpreadsheetRenderer：`import * as spreadsheet from "@odoo/o-spreadsheet"`；`new Model(load(record.spreadsheet_raw), {...})`
- `spreadsheet.spreadsheet`：`spreadsheet_raw` 型別 **serialized（JSON）**、必填僅 `name` + `owner_id`(有預設)
- 開啟 action：`{type:"ir.actions.client", tag:"action_spreadsheet_oca", params:{spreadsheet_id, model}}`
- WorkbookData schema（o_spreadsheet.js 確認）：sheets[id/name/colNumber/rowNumber/cells/merges/cols/rows]、
  top-level styles/formats/borders；style 欄位 bold/italic/strikethrough/underline/fontSize/textColor/fillColor/
  align(left|center|right)/verticalAlign(top|middle|bottom)/wrapping(overflow|wrap|clip)

## 修法（實際做的事）

### `to_ospreadsheet.ts`（轉換器，核心）
- `buildOSpreadsheetData(sheets, ss, styles, theme)` → 正規化 WorkbookData
  - **styles/formats 池化**（JSON 去重 → 1-based id，cell 以 id 參照）
  - ConcreteStyle → o-spreadsheet OStyle（色彩 `#hex`、align/vAlign/wrapping 映射）
  - content：用**萃取值**（resolveCellValueStyled）非原始公式 → 避免 o-spreadsheet 函數覆蓋率落差致 #BAD_EXPR
  - 數字 + 非日期非 General → 套 format；merges/cols(0-based 寬度)/colNumber/rowNumber
  - **邊框 v1 不輸出**（正規化形狀待瀏覽器驗證；無邊框仍正常渲染）
- `index.ts`：`importXlsxToOSpreadsheetData(buffer)` 解析全 sheet → WorkbookData

### OWL（`xlsx_import.js/xml`）
- 加「**在 o-spreadsheet 開啟（可編輯）**」按鈕：
  `importXlsxToOSpreadsheetData` → `orm.create("spreadsheet.spreadsheet", [{name, spreadsheet_raw}])`
  → `action.doAction(action_spreadsheet_oca, {spreadsheet_id, model})` → **OCA 編輯器開啟、載入我方資料**

## 三層 SOP 結果

- **L1 vitest**：**534 passed**（unit 200 + integration 334）
  - `to_ospreadsheet.test.ts`（8）：頂層結構、sheet 維度、content（string/數字）、**style 池 id 參照**
    （bold/textColor/fillColor/align/verticalAlign/wrapping）、**format 池**、merges、cols 0-based、樣式去重
    + 真實契約詳細表 16 sheet → 全 cell 的 style/format id 指向有效池項
- **L2 Odoo**：`-u` 升級 + 重啟無誤；bundle 含 importXlsxToOSpreadsheetData；OCA `spreadsheet.spreadsheet`
  create 權限/必填欄位已確認
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過

## Playwright E2E 驗證（已通過 ✅）

`tests/playwright/tests/admin-dobtor-spreadsheet-xlsx.spec.ts`（admin/admin inline login）：
1. 開 action-548 → 上傳 `估驗數量差異說明表再造11309.xlsx` → **HTML 預覽 iframe 出現、table 可見** ✅
2. 點「在 o-spreadsheet 開啟」→ **`OPEN_RESULT=GRID_MOUNTED`**、URL 跳 `action_spreadsheet_oca`
   → **o-spreadsheet 可編輯網格掛起、載入我方資料**（標題合併/粗體藍/置中、工程名稱、sheet 分頁）✅

→ 證明 o-spreadsheet `load()` **接受我方 WorkbookData**，整條 Phase 4.5 端到端可運作。

### 揭示並修正：自訂格式 #ERROR
首跑發現一格 `#ERROR`：套 Excel 自訂格式 `"第"\ #\ "次估驗附表"\ `（含 `\`/CJK 字面）的 cell，
o-spreadsheet format 引擎吃不下 → #ERROR。
**修正**：`isOSpreadsheetSafeFormat`（只放行純數字格式 `/^[#0,.%\s]+$/`），其餘跳過顯示原始數字。
重跑 → #ERROR 消失、該格顯示 `13`。

> 採「建 OCA 記錄 → 開 OCA action」而非自掛 o-spreadsheet store，把渲染交給 OCA 既有可運作的渲染器。

## 對齊進度

| 項目 | 狀態 |
|---|---|
| ConcreteStyle 對接層 | 🟢 |
| xlsx → o-spreadsheet WorkbookData 轉換器 | 🟢 本 sprint（單元驗證） |
| 建 OCA 記錄 → 開 OCA 編輯器 | 🟢 已 wire（待瀏覽器確認） |
| 邊框 / 公式 round-trip / 持久化回寫 xlsx | ⚪ 後續 |

## 下一步（Sprint 17）

- user 瀏覽器點「在 o-spreadsheet 開啟」→ 回報結果；若 load() 報錯，依錯誤調 WorkbookData schema
- 補邊框（確認正規化形狀後）
- 公式 round-trip（Phase 3）/ 匯出回 xlsx（Phase 6, openpyxl）

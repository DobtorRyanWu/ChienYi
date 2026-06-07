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

## 誠實限制（紀律 #1/#4）

- **轉換器已單元驗證**（schema 依 o-spreadsheet 文件格式 + 真實檔池 id 一致性）。
- **「開啟可編輯」未經瀏覽器驗證**：本環境 chrome-devtools MCP 無法啟動、且不便改測試帳號憑證，
  無法 dogfood。o-spreadsheet `load()` 是否完全接受我方 WorkbookData（版本遷移/必填鍵/邊框）需 user
  點按確認；若報錯，OWL 已加 in-UI error 顯示確切訊息（不會白屏）。
- 採「建 OCA 記錄 → 開 OCA action」而非自掛 o-spreadsheet store，把渲染風險交給 OCA 既有可運作的渲染器。

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

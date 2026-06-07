# Sprint 15 — Phase 4.5 Odoo UI 整合

**日期**：2026-06-07
**Phase**：4.5（產品化基礎建設）
**緣由**：模組已安裝但 `application:False` + 無 views/assets → Odoo 後台看不到、用不到。本 sprint 讓它可見可用。

---

## Root cause（開工前假設）

Sprint 0-14 全是 TS parser / 樣式引擎 / VR 管線（vitest 測試），**從未接進 Odoo UI**。
manifest `application:False`、`data`/`assets` 全註解 → 雖 installed 但零 UI surface。
假設：加入口函式 + OWL client action + manifest 掛載即可在 Odoo 開出「上傳 xlsx → 預覽」介面。

## 修法（實際做的事）

### parser 入口（`index.ts`）
- `importXlsxToHtmlPreview(buffer, sheetIndex=0)` → `{ sheets[], activeSheet, html }`
  - 串完整鏈：PackageReader → Workbook/SharedStrings/Styles/Theme → WorksheetParser → renderWorksheetHtml
  - 無 styles part fallback 空 styleSheet；sheetIndex 夾到合法範圍
- 移除舊 `importXlsx` stub；rollup 重 build → UMD bundle 暴露 `window.DobtorSpreadsheetEditor.importXlsxToHtmlPreview`

### Odoo OWL client action
- `static/src/components/xlsx_import/xlsx_import.js`：`XlsxImportAction`（registry `actions` tag `dobtor_spreadsheet_editor.import`）
  - file input → `file.arrayBuffer()` → `lib.importXlsxToHtmlPreview` → state.html
  - sheet 分頁 buttons → 重渲染指定 sheet；bundle 未就緒 / 解析失敗有 error 提示
- `xlsx_import.xml`：OWL 模板（檔案選擇 + sheet 分頁 + **iframe srcdoc 預覽**，隔離樣式）

### manifest
- `application: True`（出現在 App 主畫面）
- `data: ['views/menu.xml']`（root 選單「試算表匯入」→「Xlsx 匯入預覽」client action）
- `assets.web.assets_backend`：**bundle 先於 OWL component 載入**（component 依賴 window 全域）

## 三層 SOP 結果

- **L1 vitest**：**526 passed**（unit 192 + integration 334）
  - `import_entry.test.ts`（3）：契約詳細表 16 sheet → sheet 清單 + 首 sheet HTML、指定 sheetIndex、越界夾值
  - smoke 改測 `importXlsxToHtmlPreview` 為函式（取代移除的 importXlsx stub）
- **L2 Odoo 安裝驗證**：
  - `docker exec odoo18 odoo -u dobtor_spreadsheet_editor --stop-after-init` → menu.xml 載入無誤、0.95s、無模組錯誤
  - `docker restart odoo18` 後 DB 驗證：
    - `ir_act_client` tag=`dobtor_spreadsheet_editor.import`「Xlsx 高保真匯入」✅
    - `ir_ui_menu`：menu_dobtor_spreadsheet_root「試算表匯入」（root）+ menu_xlsx_import「Xlsx 匯入預覽」✅
    - module state=installed、無 asset 編譯錯誤
- **L3 人工檢查**：`tsc --noEmit` 乾淨、`rollup build` 通過、bundle 含 importXlsxToHtmlPreview

## 使用方式

Odoo 主畫面 → **試算表匯入** App → **Xlsx 匯入預覽** → 上傳 .xlsx →
解析（cell 值 + 樣式 + 合併格 + number format）→ iframe 預覽，多 sheet 可分頁切換。

## 對齊進度

| 項目 | 狀態 |
|---|---|
| ConcreteStyle 對接層 | 🟢（Sprint 10） |
| parser → HTML 預覽入口 | 🟢 本 sprint |
| Odoo application + 選單 + client action | 🟢 本 sprint |
| OWL 預覽（iframe） | 🟢 本 sprint |
| → o-spreadsheet model commands（可編輯） | ⚪ 後續 |

## 負面結果 / 待解（紀律 #4）

1. **預覽為唯讀 HTML**：iframe srcdoc 渲染 html_render 結果，非可編輯試算表。要可編輯需餵
   o-spreadsheet model commands（ConcreteStyle 對接層已備、待後續 sprint）。
2. **bundle 全量載入 assets_backend**：fflate + fast-xml-parser 打進 bundle，每次後台載入；
   後續可改 lazy-load（依 doc_editor lazy_loader 模式）。
3. **無 root App icon**：未設 web_icon → App 主畫面用預設圖示；可後補 static/description/icon.png。
4. **無 server-side 持久化**：純前端解析預覽，未存任何 model；持久化 / 與 ChienYi 業務模組整合為 Phase 8。

## 下一步（Sprint 16）

- **o-spreadsheet model commands 對接**：ConcreteStyle + cell value → setCellContent/updateCellFormat/addMerge
  → 在 OCA spreadsheet 內開出可編輯的高保真 xlsx（取代唯讀 iframe）
- 或 App icon + lazy-load bundle（產品化細節）

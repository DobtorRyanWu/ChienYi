# o-spreadsheet 能力審計（Phase 0）

**審計日期**：2026-06-07
**目標**：盤點 OCA `spreadsheet_oca` + Odoo 原生 `o-spreadsheet` 18.0.48 的能力與缺口，作為 Phase 1-7 開發決策依據

---

## 1. Bundle 基本資訊

| 項目 | 值 |
|---|---|
| **庫名稱** | `@odoo/o-spreadsheet` |
| **版本** | `18.0.48` |
| **Build 日期** | 2025-11-12T14:38:16Z |
| **Build hash** | `d1efb0b98` |
| **來源** | github.com/odoo/o-spreadsheet（Odoo 維護的 fork） |
| **Bundle 路徑（container 內）** | `/usr/lib/python3/dist-packages/odoo/addons/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js` |
| **Bundle 大小** | 2.8 MB minified |
| **OCA 模組路徑** | `/mnt/d/work/odoo18-docker/3rd-party/spreadsheet-18.0/spreadsheet_oca/` |
| **OCA 版本** | 18.0.1.3.0 |

---

## 2. Public Exports（plugin 擴展接口）

從 `o_spreadsheet.js` 末段 `export { ... }` 統計到的所有 public exports：

### 2.1 Plugin 基類
- `CorePlugin` — 核心 plugin 基類（資料層、會被 revision 記錄）
- `UIPlugin` — UI plugin 基類（顯示層、不會記錄）
- `Registry` — 通用 registry 類（可建自訂註冊表）
- `registries` — 多個內建 registry 的 namespace（含 `cellRegistry`、`functionRegistry`、`chartRegistries` 等）

### 2.2 Model / Spreadsheet
- `Model` — spreadsheet model 本體（dispatch commands、訂閱 events）
- `Spreadsheet` — React-like Component（OWL）
- `Revision` — 修訂物件
- `DispatchResult` / `CommandResult` — command 結果類型
- `coreTypes` / `readonlyAllowedCommands` — 型別 / 唯讀可用 commands

### 2.3 Formula API ★（Phase 3 主要對接點）
- `addFunction(name, descr)` — **註冊自訂公式函數**（補 Excel 缺失函數的核心 API）
- `astToFormula` / `parse` / `tokenize` / `compile` / `compileTokens` / `parseTokens` / `iterateAstNodes` / `convertAstNodes` / `functionCache`
- `EvaluationError` / `CellErrorType` / `invalidateCFEvaluationCommands` / `invalidateDependenciesCommands` / `invalidateEvaluationCommands`

### 2.4 Chart API（Phase 5 主要對接點）
- `AbstractChart` — chart 基類（繼承可實作自訂 chart）
- `AbstractCellClipboardHandler` / `AbstractFigureClipboardHandler`
- `addRenderingLayer` — 新增渲染層（用於自訂繪圖）

### 2.5 Pivot API（Phase 5）
- `PivotRuntimeDefinition` — pivot 定義基類
- `SpreadsheetPivotTable` — pivot table

### 2.6 i18n / 環境
- `setTranslationMethod` / `setDefaultSheetViewSize`
- `__info__` — 版本資訊物件

### 2.7 其他工具
- `helpers` / `hooks` / `links` / `stores` / `components` / `constants`
- `SPREADSHEET_DIMENSIONS` / `tokenColors` / `findCellInNewZone` / `load`

**結論**：API 完整度遠超預期，**addFunction 直接可用**，Plugin / Chart / Pivot 都有公開基類可繼承。**策略 (d) Hybrid 完全可行，不需要 fork**。

---

## 3. Commands（Model.dispatch 目標）

從 bundle 內 string literal 統計到的核心 commands（部分截錄）：

### 3.1 Cell / Content
- `SET_VALUES` — 設定 cell 值
- `UPDATE_CELL` / `UPDATE_CELL_POSITION` — 更新 cell（值、格式、樣式）
- `CLEAR_CELL` / `CLEAR_CELLS` / `CLEAR_FORMATTING` / `CLEAR_CONTENT`
- `DELETE_CELL` / `DELETE_CONTENT`

### 3.2 Sheet / Structure
- `CREATE_SHEET` / `DELETE_SHEET` / `HIDE_SHEET` / `SHOW_SHEET` / `RENAME_SHEET` / `MOVE_SHEET` / `DUPLICATE_SHEET`
- `ADD_COLUMNS_ROWS` / `REMOVE_COLUMNS_ROWS` / `RESIZE_COLUMNS_ROWS` / `HIDE_COLUMNS_ROWS` / `UNHIDE_COLUMNS_ROWS` / `MOVE_COLUMNS_ROWS`
- `FREEZE_COLUMNS` / `FREEZE_ROWS` / `UNFREEZE_COLUMNS` / `UNFREEZE_ROWS`

### 3.3 Style
- `SET_FORMATTING` — 套樣式（color、bold、border、numFmt 等）
- `SET_BORDER` / `CLEAR_FORMATTING`
- `ADD_MERGE` / `REMOVE_MERGE`

### 3.4 Conditional Formatting / Data Validation
- `ADD_CONDITIONAL_FORMAT` / `REMOVE_CONDITIONAL_FORMAT` / `MOVE_CONDITIONAL_FORMAT` / `CHANGE_CONDITIONAL_FORMAT_PRIORITY`
- `ADD_DATA_VALIDATION_RULE` / `REMOVE_DATA_VALIDATION_RULE`

### 3.5 Pivot / Chart / Image / Figure / Table
- `ADD_PIVOT` / `UPDATE_PIVOT` / `INSERT_PIVOT` / `RENAME_PIVOT` / `REMOVE_PIVOT`
- `CREATE_CHART` / `UPDATE_CHART`
- `CREATE_IMAGE` / `CREATE_FIGURE` / `UPDATE_FIGURE` / `DELETE_FIGURE` / `SELECT_FIGURE`
- `CREATE_TABLE` / `CREATE_TABLE_STYLE` / `UPDATE_TABLE`

### 3.6 Named Ranges
- `ADD_RANGE` / `REMOVE_RANGE`
- `CREATE_NEW_RANGE` (definedNames)

### 3.7 Selection / View
- `SELECT_CELL` / `MOVE_RANGES`

**結論**：Phase 4（CF/Validation）、Phase 5（Pivot/Chart/Image）所需的 commands 全部存在，**XlsxModelBridge 可純粹用 `model.dispatch()` 實作，無需 monkey-patch**。

---

## 4. Chart Types（重要修正！）

bundle 內偵測到的 chart types：

```
area, bar, combo, doughnut, gauge, line, pie, scatter, waterfall
```

**共 9 種**——比規劃書原假設的 3 種多很多。

### 4.1 Excel → o-spreadsheet chart 對照（修正版）

| Excel chart type | o-spreadsheet 對應 | 處理策略 |
|---|---|---|
| `bar` / `column` | `bar`（依 barDir 區分） | 原生支援 |
| `line` | `line` | 原生支援 |
| `pie` | `pie` | 原生支援 |
| `doughnut` | `doughnut` | 原生支援 |
| `area` | `area` | 原生支援 |
| `scatter` | `scatter` | 原生支援 |
| `combo` | `combo` | 原生支援 |
| `radar` | `line`（降級） | Phase 5 降級 |
| `bubble` | `scatter`（降級） | Phase 5 降級 |
| `stock` | `line`（降級） | Phase 5 降級 |
| `surface` | 不支援 | 顯示警告 + placeholder |
| `funnel` | 不支援 | 顯示警告 + placeholder |

**結論**：Excel 15+ chart types 中**直接對應 7 種、降級 3 種、不支援 2 種** = 涵蓋率 85%，遠優於規劃書原估的 60%。

---

## 5. OCA spreadsheet_oca 加值層

從 `/mnt/d/work/odoo18-docker/3rd-party/spreadsheet-18.0/spreadsheet_oca/`：

### 5.1 Python 模型
- `spreadsheet.abstract` — 抽象基類，定義 `spreadsheet_binary_data` (Binary) + `spreadsheet_raw` (Serialized) + `spreadsheet_revision_ids` (One2many)；多人協作 Bus message routing
- `spreadsheet.spreadsheet` — 主 doc model；繼承 `mail.thread`；含 owner/contributor/reader permission matrix；`create_document_from_attachment()` 是 xlsx 上傳入口（但只解 ZIP 存 raw、不解析）
- `spreadsheet.oca.revision` — revision log（`commands` JSON、type = REMOTE_REVISION / SNAPSHOT / ...）
- `spreadsheet.spreadsheet.import.mode` — 匯入模式（new / add 兩種）
- `spreadsheet.spreadsheet.tag` — kanban 標籤
- `ir.model` / `ir.websocket` 擴展

### 5.2 JS Bundle 擴展（`static/src/spreadsheet/bundle/`）
- `spreadsheet_action.esm.js` — 主 action entry
- `spreadsheet_renderer.esm.js` — SpreadsheetComponent wrapper
- `filter.esm.js` / `filter_panel_datasources.esm.js` — global filter UI（Odoo-model-bound）
- `chart_panels.esm.js` / `chart_panel.esm.js` — chart 側邊面板
- `odoo_panels.esm.js` — Odoo-specific 側邊面板
- `spreadsheet_controlpanel.esm.js` — top control bar
- `image_file_store.esm.js` — Odoo attachment 整合
- 共 8 個 JS + 1 個 XML template（30 KB）

### 5.3 Bundle 掛鉤點
OCA 透過 `web.assets_backend` + `spreadsheet.o_spreadsheet` 兩個 bundle 注入：
```python
'spreadsheet.o_spreadsheet': [
    'spreadsheet_oca/static/src/spreadsheet/bundle/spreadsheet.xml',
    'spreadsheet_oca/static/src/spreadsheet/bundle/image_file_store.esm.js',
    'spreadsheet_oca/static/src/spreadsheet/bundle/filter.esm.js',
    # ... 8 files total
]
```

我們的 `dobtor_spreadsheet_editor` 採同模式：xlsx parser bundle 注入 `spreadsheet.o_spreadsheet`，與 OCA 並存。

---

## 6. 環境驗證結果

| 工具 | 狀態 | 版本 |
|---|---|---|
| openpyxl（Python） | ✓ container 已裝 | 3.1.2 |
| python-calamine（Python） | ✓ container 已裝 | (匯入 ok) |
| libreoffice（WSL host） | ✓ 可用於 golden 產生 | 24.2.7.2 |
| libreoffice（container） | ✗ 未裝 | — |
| node / npm | (待 Phase 0 第二週 npm install 確認) | — |

**結論**：Golden PNG 產生在 WSL host 跑（已有 LibreOffice 24）、cell value golden JSON 用 container 內 python-calamine 跑。

---

## 7. 缺口清單（confirmed gaps，作為 Phase 1-7 工作項）

### 7.1 xlsx 匯入（核心缺口）
- ❌ Workbook / Worksheet parser（OCA 只解 ZIP 不解 XML）
- ❌ SharedStrings parser
- ❌ Styles parser（xf cascade、numFmts、dxfs）
- ❌ Formula parser（R1C1、shared formula、structured ref）
- ❌ ConditionalFormatting parser（5 大 rule types）
- ❌ DataValidations parser
- ❌ PivotCache / PivotTable parser
- ❌ Chart parser（DrawingML）
- ❌ Drawing / Image parser

### 7.2 Excel 公式覆蓋率
- ⚠️ o-spreadsheet 18.0.48 內建約 ~50 函數（待 Phase 3.1 用 grep 精確統計）
- ❌ Excel 400+ 函數差距：須在 plugin 層用 `addFunction` 補齊
- ChienYi 必須 30 個：IFERROR、SUMPRODUCT、DATEDIF、INDIRECT、VLOOKUP/XLOOKUP、WORKDAY、TEXTJOIN 等

### 7.3 Number Format（台灣 locale）
- ⚠️ 內建格式 0-49 應已支援（待 Phase 2.3 確認）
- ❌ 自訂格式（id ≥ 164）解析
- ❌ 條件色彩 `[紅色]` / `[Red]`
- ❌ Locale token `[$-404]`
- ❌ 中華民國年（民國紀年 `e` token）
- ❌ 台灣會計格式（`_($* #,##0.00_);[Red](#,##0.00)`）

### 7.4 CJK 欄寬
- ⚠️ 使用 `ctx.measureText()` → CJK 累積誤差 15-25%（同 dobtor_doc_editor 已驗證問題）
- Phase 2.5 用 Unicode block 查表法補救
- Phase 7 升級 HarfBuzz WASM

### 7.5 不支援（Phase 8+ 評估）
- Excel `radar` / `bubble` / `stock` chart（降級至 line/scatter）
- Excel `surface` / `funnel` chart（不支援）
- Excel VBA / 巨集（Odoo 整體無 VBA 對等概念）
- Sparklines（Excel 2010+ 擴展、選做）
- Slicers（pivot 互動篩選、選做）

---

## 8. 對 Phase 規劃的影響

**修正項**（基於本審計）：

1. **Phase 5 Chart Mapping 工作量下調**：原估 2-3 個月、實際 1.5-2 個月即可（chart type 涵蓋率 85% 而非 60%）
2. **Phase 3 公式 shim 工作量維持**：addFunction API 直接可用，但 Excel 函數總量仍是 400+，shim 工作量無法省
3. **Phase 4 CF/Validation 工作量下調**：commands 已全部就緒，僅須做 parser + compiler，原估 1-1.5 個月可壓到 1 個月
4. **不需要 fork o-spreadsheet 的信心提升**：所有需要的擴展點都是 public API

**未變項**：
- Phase 1（Parser）2-3 個月維持
- Phase 2（Style / NumberFormat / CJK）1-1.5 個月維持
- Phase 3（Formula）3-4 個月維持
- Phase 6（Export）1-2 個月維持
- Phase 7（效能）持續

**結論**：總時程 12-18 個月區間維持，但**樂觀情境向 12 個月靠攏**。

---

**Audit 完成日**：2026-06-07
**下次審計**：Phase 1 完成後（預估 M3）重審內建函數清單與 commands 完整對應

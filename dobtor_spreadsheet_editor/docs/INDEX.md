# Sprint Audit Index

Sprint 進度索引（沿用 dobtor_doc_editor 的 INDEX.md 模式）。

## 約定

- 每個 sprint commit 配一份 `sprint<N>_<topic>.md` audit 文件，記錄：
  - **Root cause**：開工前對問題的假設
  - **修法**：實際做的事 + diff hash
  - **三層 SOP 結果**：L1 vitest / L2 visual regression / L3 人工檢查
  - **負面結果有結構價值**：失敗也要 documented，紀律 #4
- 本檔提供主題分群導航，不是流水帳

## Phase 0（Sprint 0-3）

| Sprint | Topic | Audit Doc |
|---|---|---|
| 0 | 模組骨架 + build pipeline + o-spreadsheet API 審計 + Phase 0 文件群 | (本批次無單獨 audit doc、彙整於 capability_audit.md) |
| 1 | Fixture 48 份收集（A+B 標實檔、8 類分流）+ 48×golden 產生 | [sprint1_fixture_intake.md](sprint1_fixture_intake.md) |
| 2 | （待開工）04/07 稀少類補滿 + ADR-001/002 簽核 | — |
| 3 | （待開工）Phase 0 Exit review | — |

## Phase 1（Sprint 2+）— OOXML SpreadsheetML Parser

| Sprint | Topic | Audit Doc |
|---|---|---|
| 2 | §1.1 PackageReader（OPC 容器：zip/Content_Types/rels 相對路徑）+ §1.2 units（EMU/pt/px/欄寬） | [sprint2_package_reader_units.md](sprint2_package_reader_units.md) |
| 3 | §1.3 WorkbookParser（sheets/state/definedNames/view/calcPr/r:id 解析）+ §1.4 SharedStringsParser（rich text run + _xHHHH_ 解碼）+ xml_util 共用層 | [sprint3_workbook_sharedstrings.md](sprint3_workbook_sharedstrings.md) |
| 4 | §1.6 WorksheetParser（cell type/value/公式/mergeCells/freeze/cols）+ cell_ref + **golden 提取率比對 98.53%（排除日期 99.998%）** | [sprint4_worksheet_extraction.md](sprint4_worksheet_extraction.md) |
| 5 | §1.5 StylesParser（numFmts/fonts/fills/borders/cellXfs/cellStyleXfs/dxfs）+ color（rgb/theme/tint/indexed）+ 內建格式表 + isDateNumberFormat（日期缺口偵測 100%） | [sprint5_styles_parser.md](sprint5_styles_parser.md) |

## Phase 2 — Cell Rendering & Text Metrics

| Sprint | Topic | Audit Doc |
|---|---|---|
| 6 | §2.3 最小版：Excel 日期序號 → YYYY-MM-DD（number_format + value_resolver）→ **提取率 98.53%→99.998%** | [sprint6_date_minimal.md](sprint6_date_minimal.md) |
| 7 | §2.1 StyleResolver：xf cascade 攤平（cellXf + cellStyleXf 繼承 + applyX 旗標 → ResolvedStyle）+ corpus 健全性 48 | [sprint7_style_resolver.md](sprint7_style_resolver.md) |
| 8 | §1.9 ThemeParser（clrScheme 12 色 + fontScheme）+ §2.2 ThemeResolver（theme 索引 0/1 互換 + indexed 56 色 + HSL tint）→ 具體 RGB | [sprint8_theme_resolver.md](sprint8_theme_resolver.md) |

## Phase 2/3 — Number Format 渲染

| Sprint | Topic | Audit Doc |
|---|---|---|
| 13 | §2.3 number format 完整渲染（#0?,. 千分位/小數、% 百分比、[$貨幣]、"字面"、會計負數、多段；僅顯示用、不動提取）| [sprint13_number_format.md](sprint13_number_format.md) |

## Phase 3 ★ — Formula Engine Compatibility

(待 sprint 開展後填入)

## Phase 4 — Conditional Formatting & Data Validation

| Sprint | Topic | Audit Doc |
|---|---|---|
| 9 | §1.7 CFParser（cellIs/expression/duplicateValues + colorScale/dataBar/iconSet/containsText/top10）+ 整合進 WorksheetParser + dxfId 連結 corpus 48 | [sprint9_cf_parser.md](sprint9_cf_parser.md) |

## Phase 4.5 — 產品化基礎建設

| Sprint | Topic | Audit Doc |
|---|---|---|
| 10 | ConcreteStyleResolver：StyleResolver + ThemeResolver → ConcreteStyle（font/fill/border 全具體 RGB）+ fillBackgroundColor + 端到端 corpus 48 | [sprint10_concrete_style.md](sprint10_concrete_style.md) |

## Phase 5 — Pivot / Chart / Drawing

(待 sprint 開展後填入)

## Phase 6 — Export 對稱性

| Sprint | Topic | Audit Doc |
|---|---|---|
| 19 | **匯出回 xlsx**：xlsx_writer（fflate 打 OOXML：值/公式/合併/多sheet/sharedStrings/minimal styles）+ exportXlsxFromBuffer + OWL 下載按鈕；round-trip 值一致 >99.9%、下載檔 openpyxl+LibreOffice 驗證 | [sprint19_xlsx_export.md](sprint19_xlsx_export.md) |
| 20 | **樣式回寫（高保真匯出）**：StyleSheetBuilder（ConcreteStyle → styles.xml fonts/fills/borders/numFmts/cellXfs 池）+ WorksheetParser 收空白樣式格 → 邊框/粗體/填色/numFmt round-trip；openpyxl 驗下載檔含樣式 | [sprint20_style_writeback.md](sprint20_style_writeback.md) |
| 21 | **欄寬/列高回寫**：WorksheetParser 擷取 row ht + ws.cols → xlsx_writer 寫 `<cols>`/row `ht`；openpyxl 驗 C欄寬 4.25/第1列高 30.75 round-trip | [sprint21_cols_rows.md](sprint21_cols_rows.md) |

## Phase 4 VR pipeline（跨 Phase 基礎建設）

| Sprint | Topic | Audit Doc |
|---|---|---|
| 11 | VR 管線：pixel_compare（pixelmatch 原語）+ html_render（model→HTML）+ render_png（puppeteer）+ baseline（45-88% vs LibreOffice，管線就緒） | [sprint11_vr_pipeline.md](sprint11_vr_pipeline.md) |
| 12 | 全 sheet render（dimension 全範圍，移除 60×40 截斷）+ scaleToMatch（分離尺寸假性差異）→ **content diff 降到 11.7-20.4%** | [sprint12_full_sheet_vr.md](sprint12_full_sheet_vr.md) |
| 14 | 字型保真：font_map（Excel 字型 → metric-compatible 替換 Carlito/Liberation + CJK 回退鏈）→ content diff 11.4-19.3% | [sprint14_font_fidelity.md](sprint14_font_fidelity.md) |
| 15 | **Phase 4.5 Odoo UI**：importXlsxToHtmlPreview 入口 + OWL client action（上傳→解析→iframe 預覽 + sheet 分頁）+ manifest application/menu/assets | [sprint15_odoo_ui.md](sprint15_odoo_ui.md) |
| 16 | **o-spreadsheet 對接**：to_ospreadsheet 轉換器（ParsedWorksheet → WorkbookData，styles/formats 池化）+ importXlsxToOSpreadsheetData + OWL「在 o-spreadsheet 開啟」（建 OCA spreadsheet 記錄→開 OCA 編輯器）+ **Playwright E2E 實證 GRID_MOUNTED** | [sprint16_ospreadsheet.md](sprint16_ospreadsheet.md) |
| 17 | **邊框對接**：ConcreteBorder → o-spreadsheet border 池（{style,color}、Excel style 映射、double→medium）+ Playwright 驗證邊框渲染、無 #ERROR | [sprint17_borders.md](sprint17_borders.md) |
| 18 | **公式 round-trip**：hybrid（安全公式餵公式即時運算、CHOOSE 等 fallback cached）+ 45 函數白名單（對 o_spreadsheet.js 確認）+ Playwright 驗證複價/小計正確運算、無 #BAD_EXPR | [sprint18_formula_roundtrip.md](sprint18_formula_roundtrip.md) |

## Phase 7 — 效能與大檔

(待 sprint 開展後填入)

## Phase 8 — ChienYi 業務整合

| Sprint | Topic | Audit Doc |
|---|---|---|
| 22 | **ChienYi bridge**：獨立模組 dobtor_spreadsheet_editor_chienyi，payment.estimate 表單加「匯入估驗試算表」按鈕 → 開 Xlsx 匯入；Playwright 驗證按鈕可見+開啟（通用編輯器保持業務無關） | [sprint22_chienyi_bridge.md](sprint22_chienyi_bridge.md) |
| 23 | **估驗回掛**：bridge 擴 spreadsheet.spreadsheet+payment_estimate_id、estimate one2many+smart button；通用元件命名空間 context `sse_create_vals` 轉發；Playwright 驗證回掛+smart button | [sprint23_estimate_link.md](sprint23_estimate_link.md) |
| 24 | **修巢狀開啟**：Component-is-destroyed（doAction 後不碰 state）+ clearBreadcrumbs top-level 開啟 + @class→hasclass；巢狀 GRID_MOUNTED、standalone 無回歸 | [sprint24_nested_open_fix.md](sprint24_nested_open_fix.md) |
| 25 | **從估驗工項產生試算表**：bridge Python 建 WorkbookData（標題+粗體表頭+工項列）→ 回掛試算表 + 開啟；Playwright 估驗33→181工項 GRID_MOUNTED | [sprint25_generate_from_estimate.md](sprint25_generate_from_estimate.md) |
| 26 | **產生的估驗試算表用即時公式**：金額欄 =F*G / =F*I、小計 SUM 列（粗體）；Playwright 驗證 H=193.12*408.7=78928.144 即時計算 | [sprint26_estimate_formulas.md](sprint26_estimate_formulas.md) |
| 27 | **估驗表 polish + 修 format bug**：欄寬/千分位/層級縮排；揭示 o-spreadsheet format 為 inline 字串（非 id-pool）→ 修 bridge + to_ospreadsheet 匯入路徑（潛伏 bug）；#ERROR 消失 | [sprint27_estimate_polish.md](sprint27_estimate_polish.md) |
| 28 | **估驗表視覺**：表頭填色置中(D9E1F2)、數字右對齊、小計填色(FCE4D6)、凍結首兩列(panes xSplit/ySplit)；GRID_MOUNTED | [sprint28_estimate_visual.md](sprint28_estimate_visual.md) |

## Phase 3 — Formula

| Sprint | Topic | Audit Doc |
|---|---|---|
| 33 | **公式 shim + 白名單擴充**：CHOOSE functionRegistry shim（Odoo asset）+ 白名單 45→~90（word-boundary 確認）；Playwright CHOOSE_REGISTERED=true | [sprint33_formula_shim.md](sprint33_formula_shim.md) |

## Phase 4 — CF/DV 編譯

| Sprint | Topic | Audit Doc |
|---|---|---|
| 29 | **CF 編譯到 o-spreadsheet**：cf_compiler（cellIs→CellIsRule + containsText + dxf 樣式 + 範圍夾取）整合 to_ospreadsheet；土單 CF_GRID_MOUNTED 無錯誤 | [sprint29_cf_compiler.md](sprint29_cf_compiler.md) |
| 30 | **CF 匯出回 xlsx**：cf_writer（CF blocks→<conditionalFormatting>、dxfs→<dxfs>）整合 xlsx_writer/exportXlsxFromBuffer；openpyxl 讀到 2 CF 範圍、LibreOffice 開啟 | [sprint30_cf_export.md](sprint30_cf_export.md) |

## Phase 5 — Chart/Drawing

| Sprint | Topic | Audit Doc |
|---|---|---|
| 31 | **Chart 解析**：chart_parser（type/series/cat/val/title）+ drawing_parser（anchor+chart rId）+ chart_compiler（→o-spreadsheet figure）；修 rel.resolvedTarget；自檢表 CHART_GRID_MOUNTED | [sprint31_chart_parser.md](sprint31_chart_parser.md) |
| 32 | **Chart 匯出回 xlsx**：原始 drawing/chart/media parts 直通複製 + 重建 worksheet→drawing rel + Content_Types；openpyxl 讀到 chart 物件、自家 re-parse 得 figure | [sprint32_chart_export.md](sprint32_chart_export.md) |
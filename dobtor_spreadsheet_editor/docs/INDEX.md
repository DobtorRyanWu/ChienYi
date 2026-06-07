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

(待 sprint 開展後填入)

## Phase 4 VR pipeline（跨 Phase 基礎建設）

| Sprint | Topic | Audit Doc |
|---|---|---|
| 11 | VR 管線：pixel_compare（pixelmatch 原語）+ html_render（model→HTML）+ render_png（puppeteer）+ baseline（45-88% vs LibreOffice，管線就緒） | [sprint11_vr_pipeline.md](sprint11_vr_pipeline.md) |
| 12 | 全 sheet render（dimension 全範圍，移除 60×40 截斷）+ scaleToMatch（分離尺寸假性差異）→ **content diff 降到 11.7-20.4%** | [sprint12_full_sheet_vr.md](sprint12_full_sheet_vr.md) |
| 14 | 字型保真：font_map（Excel 字型 → metric-compatible 替換 Carlito/Liberation + CJK 回退鏈）→ content diff 11.4-19.3% | [sprint14_font_fidelity.md](sprint14_font_fidelity.md) |
| 15 | **Phase 4.5 Odoo UI**：importXlsxToHtmlPreview 入口 + OWL client action（上傳→解析→iframe 預覽 + sheet 分頁）+ manifest application/menu/assets | [sprint15_odoo_ui.md](sprint15_odoo_ui.md) |
| 16 | **o-spreadsheet 對接**：to_ospreadsheet 轉換器（ParsedWorksheet → WorkbookData，styles/formats 池化）+ importXlsxToOSpreadsheetData + OWL「在 o-spreadsheet 開啟」（建 OCA spreadsheet 記錄→開 OCA 編輯器） | [sprint16_ospreadsheet.md](sprint16_ospreadsheet.md) |

## Phase 7 — 效能與大檔

(待 sprint 開展後填入)

# Dobtor Spreadsheet Editor — 高保真 xlsx 匯入開發規劃

**目標等級**：對標 **Google Sheets / Microsoft Excel** 的 xlsx 匯入還原度（95%+ 真實檔案無跑版）

**產出日期**：2026-06-07（Sprint 0 起點）
**適用模組**：`/mnt/d/work/odoo18-docker/addons/dobtor_spreadsheet_editor`
**當前基礎**：Odoo 18 OWL Component + OCA `spreadsheet_oca` v18.0.1.3.0 + Odoo CE 原生 `o-spreadsheet` v18.0.48（2.8 MB minified bundle）
**平行模組**：`dobtor_doc_editor`（docx 高保真匯入，已 Sprint 200+）

> **進度與紀律不在本檔追蹤**（規劃成熟後沿用 [dobtor_doc_editor 模式](../dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)）：
> - 當前指標 / Phase 完成度 / VR mean 進展 → `docs/progress_snapshot.md`（Phase 0 第二週建立）
> - Sprint audit 索引 → `docs/INDEX.md`（從 Sprint 1 起累積）
> - 開發紀律（沿用 dobtor docx CONTRIBUTING.md §5 的 22 條 + xlsx 特化候選）→ `CONTRIBUTING.md §5`
> - 文件產製通路決策（docx vs xlsx vs QWeb PDF 三方分流）→ `docs/scope_decision.md`

---

## 對齊狀態（2026-06-09，Sprint 0-44 後）

> 健檢：`tsc` 乾淨、`rollup build` 通過、**vitest 551 passed / 1 skipped**。任務清單已逐項打勾（✅ = 100% 完成）。

| Phase | 完成度 | 已做（sprint） | 主要未完成 |
|---|---|---|---|
| 0 基建 | 🟢 ~90% | 骨架/build/48 fixture/golden/API 審計/docs（S0-1） | ADR-001/002 正式簽核 |
| 1 Parser | 🟢 ~90% | §1.1-1.9、1.10（部分）、1.8 DV、**§1.11 Tables（S39）+ numeric entity 解碼修復** | §1.6 capture-only（autoFilter/hyperlink/print/breaks）、shared formula 展開、gradient fill、structured ref |
| 2 Style | 🟡 ~72% | §2.1/2.2 resolver、§2.3 number format + 日期/民國年 + **會計負數紅字（S45）**、§2.4 interop + **numFmt 寬容套用（Excel 相容）** | §2.3 時間 token、§2.4 rich text 多 segment、§2.5 CJK 欄寬估算 |
| 3 Formula | 🟡 ~58% | §3.1 gap、§3.2 A1+shared formula、§3.3 白名單~93+**CHOOSE/MROUND/REPT/SIGN shim（S33/S42）**、§3.5 錯誤值保真 | §3.2 R1C1/structured/array、§3.4 volatile、formula.js 補通用函數 |
| 4 CF/DV | 🟢 ~75% | §1.7 解析 + §4.1 編譯（**CF 五型全：cellIs/containsText/colorScale/dataBar/iconSet S29-38**）+ §4.2 DV | §4.1 duplicateValues/expression（o-spreadsheet 無對應）、§4.3 CF 視覺回歸 |
| 4.5 產品化 | 🟢 ~60% | Odoo client action UI、匯入預覽、開可編輯 o-spreadsheet、估驗 bridge + 回掛（S15-25） | §4.5.1 指定 model 欄位/REST controller、§4.5.2 通用 xlsx.linked.mixin、§4.5.3 Portal 嵌入、§4.5.4 zip bomb/size 防護、§4.5.6 匯出稽核 cron |
| 5 Pivot/Chart/Drawing | 🟡 ~20% | **§5.2 ChartParser+Mapper（bar/line/pie/scatter、series/cat/val/title）+ §5.3 DrawingParser anchor（S31）** | Pivot、圖片/shape import、chart 匯出回 xlsx、strCache/axes 細節 |
| 6 Export | 🟢 ~78% | §6.2 TS writer（值/公式/樣式/欄寬/列高 + CF/dxfs + chart/drawing/media + **DV 回寫 S36**） | defined names/theme 回寫、style pass rate 量化、Excel/GSheets 三端、ADR-003 |
| 7 效能 | 🔴 0% | — | Web Worker/streaming、virtual scroll、IndexedDB cache、HarfBuzz、benchmark |
| 8 ChienYi | 🟡 ~30% | **估驗工項產生試算表（即時公式/格式/凍結）**、payment.estimate 整合（S25-28） | 監造日報/契約/月報範本、construction_progress 整合、Portal 嵌入 |

**核心成果**：cell value 提取率 **99.998%**、Odoo 內 xlsx 匯入→可編輯 o-spreadsheet→高保真匯出雙向 round-trip（繼承 OCA）、估驗工項一鍵產生計算表，全程 Playwright E2E + openpyxl/LibreOffice 驗證。
**未完成核心缺口**：①公式編譯器（Phase 3，目前只 hybrid 白名單）②CF/DV 編譯到 o-spreadsheet（Phase 4）③Pivot/Chart/Drawing（Phase 5）④效能（Phase 7）。

---

## 目錄

1. [現實評估與心理建設](#1-現實評估與心理建設)
2. [還原度標準定義](#2-還原度標準定義)
3. [架構總圖](#3-架構總圖)
4. [核心技術棧](#4-核心技術棧)
5. [Phase 規劃（12-18 個月）](#5-phase-規劃12-18-個月)
6. [測試與驗證體系](#6-測試與驗證體系)
7. [程式碼組織](#7-程式碼組織)
8. [風險與備案](#8-風險與備案)
9. [人力與時程矩陣](#9-人力與時程矩陣)
10. [閱讀與參考清單](#10-閱讀與參考清單)
11. [下一步建議](#11-下一步建議)

附錄 A：[Phase 0 立即可做的任務清單](#附錄-aphase-0-立即可做的任務清單)
附錄 B：[關鍵術語對照表](#附錄-b關鍵術語對照表)

---

## 1. 現實評估與心理建設

> **Scope 紀律提醒**：本規劃書定義的 scope 是「**繼承 OCA `spreadsheet_oca` + 加 xlsx 高保真匯入層**」。任何 sprint 開工前必須先對齊本書 §5 的 Phase 範圍（紀律 #18，沿用自 dobtor_doc_editor）。新 feature 與本書不符 → 優先誠實 revert、不是合理化保留。

### 1.1 這是什麼等級的工程

**Google Sheets / Excel 級 xlsx 匯入 = 重寫 1/3 個 Excel**。

| 產品 | 團隊規模 | 開發年期 | 結論 |
|---|---|---|---|
| Microsoft Excel | 400+ 工程師 | 40+ 年 | 市場標竿 |
| Google Sheets | 80+ 工程師 | 14+ 年（2006 起） | 95% 還原（限常見格式） |
| LibreOffice Calc | 志工 + 企業 | 25+ 年 | 90-95% 還原（OOXML 入口在 `sc/source/filter/oox/`） |
| OnlyOffice Spreadsheet | 40+ 工程師 | 12 年 | 95%+ 還原 |
| WPS Spreadsheet | 150+ 工程師 | 25+ 年 | 98% 還原 |

**若要達到這個標準**：
- **最小團隊**：3-5 名資深工程師
- **最短時程**：12-18 個月（有 o-spreadsheet 作為起跳台）
- **若 1 人**：**2-3 年**（可行，需長期投入）

### 1.2 為什麼這麼難

Excel `.xlsx` 的 OOXML **SpreadsheetML** 規格（ECMA-376 Part 1 §18）超過 1500 頁，加上 DrawingML（§20）、SharedStrings、Styles、PivotCache 等附屬規格合計 2000+ 頁。Excel 實際行為**超出規格書**——同 docx，存在「Microsoft Excel 實作方言」需逆向工程：

- 規格說 A，Excel 做成 A'
- 規格沒寫的邊界（如 0 寬度欄、巢狀公式深度上限），各版本 Excel 行為不同
- Excel 2007 / 2010 / 2016 / 365 產出的 xlsx 在 `cellXfs` ordering、`sharedStrings` 編碼上微妙不同
- LibreOffice / WPS / Google Sheets 匯出的 xlsx 都有自己的方言

### 1.3 OCA spreadsheet_oca + o-spreadsheet 作為基礎的能力與限制

OCA `spreadsheet_oca` 繼承 Odoo CE 原生 `spreadsheet` 模組（容器路徑 `/usr/lib/python3/dist-packages/odoo/addons/spreadsheet/`，22 MB），核心是 Odoo 維護的 **o-spreadsheet 18.0.48** JS bundle（github.com/odoo/o-spreadsheet 的 fork）。

**現成的能力**（不用我們做）：

| 能力 | OCA + o-spreadsheet 現況 | Google Sheets 需要 |
|---|---|---|
| Canvas 儲存格渲染 | ✅ 完整 | ✅ |
| 公式引擎 | ✅ ~50 函數（SUM、IF、VLOOKUP 等基本） | ✅ 400+ 函數 |
| Multi-sheet | ✅ | ✅ |
| Pivot tables | ✅ Odoo-model-bound | ✅ Excel 風格 pivot |
| Charts | ✅ bar/line/pie（Odoo-data-bound、**非 Excel 相容**） | ✅ 15+ 類型可 round-trip |
| Conditional formatting | ✅ class 存在、基本 rules | ✅ 5 大 rule types |
| Global filters | ✅ | ✅ |
| Named ranges | ✅ | ✅ |
| 即時協作 | ✅（OCA 加值層 `spreadsheet.oca.revision` + Bus） | ✅ |
| Permission matrix | ✅（OCA owner/contributor/reader） | ✅ |
| **xlsx 匯入** | ⚠️ OCA wizard 只解 ZIP 存 raw XML，**不解析任何欄位** | ❌ |
| **xlsx 匯出** | ✅ o-spreadsheet `exportXLSX()`、基本可用 | ✅ |
| Excel 數字格式（zh-TW locale） | ⚠️ 部分 | ✅ 完整 |
| Excel CF rules（colorScale/dataBar/iconSet） | ⚠️ 結構支援、xlsx import 不解析 | ✅ |
| Excel pivot cache（local data pivot） | ❌ 只支援 Odoo-model pivot | ✅ |
| Excel chart 完整類型 | ❌ 只有 3 類型 | ✅ |
| Drawing layer（shapes、images） | ❌ | ✅ |
| CJK 欄寬精確估算 | ❌ `ctx.measureText()` 估算誤差大 | ✅ |
| 大型 sheet（10 萬行+） | ⚠️ 未測 | ✅ |

**結論**：我們**不 fork o-spreadsheet**（每次 Odoo 升級 merge 成本高），而是在 plugin 層加 xlsx I/O parser，把解析結果以 o-spreadsheet model commands 餵入。Odoo-bound 功能（pivot/list/filter/native chart）走原生路徑；xlsx-import 走我們的新路徑。

### 1.4 與 dobtor_doc_editor 的關鍵差異

| 面向 | dobtor_doc_editor | dobtor_spreadsheet_editor（本書） |
|---|---|---|
| 渲染引擎 | canvas-editor（fork + patch） | o-spreadsheet（plugin 擴展、**不 fork**） |
| 匯入策略 | OOXML parser → canvas-editor data model | OOXML parser → o-spreadsheet model commands |
| 最大技術坑 | 跨頁 vMerge / Knuth-Plass / font shaping | 公式引擎覆蓋率 / style cascade / CJK 欄寬 |
| 排版主戰場 | Paginator / TableLayout / Float | Formula Engine / NumberFormat / CF |
| 協作後端 | Phase 4.5 自建 | OCA 已有（Bus + revision，直接繼承） |
| 測試基準 | LibreOffice headless → pixelmatch | LibreOffice Calc + Excel Online → cell value diff + visual |
| 字型管線 | 需 HarfBuzz WASM（行內換行 critical） | 也需 HarfBuzz（CJK 欄寬 critical、Phase 7 升級） |
| 規格頁數 | ECMA-376 Part 1 §17（WordprocessingML，5000+ 頁） | ECMA-376 Part 1 §18（SpreadsheetML，1500+ 頁）+ §20（DrawingML） |

---

## 2. 還原度標準定義

### 2.1 分級標準

| 級別 | 描述 | 量化指標 |
|---|---|---|
| **S 級（像素一致）** | 與 Excel 原檔每像素相同 | 0%（實務不可達） |
| **A 級（視覺一致）** | 與 Excel 原檔差異 <2%，非專業人士看不出來 | cell value 99%、style diff <5px、公式 95% pass |
| **A- 級（高還原）** | 差異 <5%，偶有 style 微差 | cell value 98%、style diff <10px、公式 85% pass |
| **B+ 級（可商業使用）** | 結構與樣式皆對，少數格式降級 | cell value 95%、合併儲存格正確、基本 CF 渲染 |
| **B 級（結構正確）** | cell value 對、樣式部分缺失 | cell value 90%、欄寬正確、數字格式正確 |
| **C 級（內容保留）** | 字都在，格式大亂 | OCA 目前水準（raw XML dump、未解析） |

**本專案目標**：**A- 級**，對 ChienYi 業務文件類（估驗計價表、契約工項、損益試算、月報）達 **A 級**。

### 2.2 成功指標（量化）

對 **50 份真實台灣商業 xlsx 樣本集**：

- **內容保留**：cell value 99%+ 一致（含字串、數字、日期、布林、錯誤值）
- **結構保真**：merged cells、defined names、autoFilter、freezePanes、multi-sheet 100% 正確
- **樣式還原**：
  - 字型、字重、字色：100% 正確
  - 背景填色（含 theme color + tint）：≤5% RGB 誤差
  - 邊框（four sides + diagonals）：100% 結構正確
  - 數字格式（含台灣自訂 15 種）：100% 正確
  - 欄寬（CJK auto-fit）：≤10% 誤差
  - Conditional formatting：5 大 rule types 渲染正確
- **公式還原**：
  - ChienYi 常用 30 個函數 100% 計算正確
  - Excel 400+ 函數覆蓋率 ≥85%
  - R1C1 notation、structured table reference、array formula 正確轉換
- **視覺差異**：
  - pixelmatch 對比 LibreOffice Calc headless 渲染的 PNG，差異率 <5%
  - 人工盲測 20 位，平均「無法分辨 vs 原檔」>75%

### 2.3 ChienYi 業務文件目標還原度

| 文件類型 | 起點（OCA） | Phase 3 目標 | Phase 6 目標 |
|---|---|---|---|
| 估驗計價表（含 SUM 公式、合併儲存格、台灣金額格式） | C | B+ | A |
| 契約工項明細（樹狀縮排、粗體分層、cell border） | C | B | A- |
| 月報損益試算（條件格式紅/綠、百分比） | C | B | B+ |
| 政府採購標單轉 xlsx（IT 工項表） | N/A | B+ | A- |
| 施工進度 S 曲線（含 bar chart + line overlay） | C | B- | B |
| 多工作表月報（cross-sheet INDIRECT/VLOOKUP） | C | B | B+ |

---

## 3. 架構總圖

```
┌────────────────────────────────────────────────────────────────┐
│  Odoo 18 後端（Python）                                          │
│  spreadsheet_editor.py（inherit spreadsheet.spreadsheet）        │
│  xlsx_controller.py（upload/download/version snapshot）          │
│  xlsx_mixin.py（ChienYi 業務模型整合：estimate / change / task）  │
└──────────────────────────┬─────────────────────────────────────┘
                           │ RPC / HTTP
┌──────────────────────────▼─────────────────────────────────────┐
│  Layer 5: OWL Components                                         │
│  XlsxImportButton  VersionHistoryPanel  PortalEmbed             │
└──────────────────────────┬─────────────────────────────────────┘
                           │ commands
┌──────────────────────────▼─────────────────────────────────────┐
│  Layer 4: o-spreadsheet model command bridge（XlsxModelBridge）  │
│  parsed AST → setCellContent / updateCellFormat / addMerge /    │
│              addConditionalFormat / addChart / setNamedRange     │
└──────────────────────────┬─────────────────────────────────────┘
                           │ AST
┌──────────────────────────▼─────────────────────────────────────┐
│  Layer 3: Style / Formula / Render 轉換                          │
│  StyleResolver（xf cascade）  ThemeResolver（theme color + tint） │
│  NumberFormatCompiler（zh-TW locale）  FormulaCompiler（R1C1→A1）│
│  CJKWidthEstimator（HarfBuzz WASM、Phase 7）  CFCompiler          │
│  PivotMapper  ChartMapper  DataValidationCompiler               │
└──────────────────────────┬─────────────────────────────────────┘
                           │ Workbook AST
┌──────────────────────────▼─────────────────────────────────────┐
│  Layer 2: OOXML SpreadsheetML Parser（★ 最核心）                 │
│  WorkbookParser  WorksheetParser  SharedStringsParser            │
│  StylesParser  FormulaParser  CFParser  DataValidationParser     │
│  PivotCacheParser  ChartParser  DrawingParser                    │
└──────────────────────────┬─────────────────────────────────────┘
                           │ ZIP buffer + part Map
┌──────────────────────────▼─────────────────────────────────────┐
│  Layer 1: Package 解壓                                           │
│  PackageReader（fflate）  ContentTypeMap  RelationshipResolver   │
└────────────────────────────────────────────────────────────────┘
```

### 架構決策關鍵

**為何保留 o-spreadsheet 但只走 plugin 擴展（不 fork）**：

- ✅ 即時協作、Undo/Redo、選取、Copy/Paste、Formula engine、Pivot/Chart 渲染——這些寫一次要 12-18 個月
- ✅ Odoo-bound 功能（ODOO.LIST / ODOO.PIVOT / global filters）價值極高，fork 後會與 Odoo 內部 datasource API 脫鉤
- ❌ Fork 維護成本：Odoo 每季升級 spreadsheet 模組，每次都要 merge upstream，預估每年人月成本 1-2 人月
- 💡 **最佳策略**：保留 o-spreadsheet 引擎，**只在 plugin 層加 xlsx I/O parser**，輸出 commands 餵入 model。Plan B 留給「plugin API 限制無法 workaround」的緊急情況。

**為何不直接用 SheetJS / ExcelJS 而要自寫 Parser**：

- 兩者授權有疑慮（SheetJS Community Edition 不含 Excel-formula）或缺 ChienYi 特化（台灣 number format、CJK 欄寬）
- 自寫 Parser 可整合 dobtor_doc_editor 的 font infrastructure（HarfBuzz、CJK fallback chain）
- ECMA-376 §18 不算大，3-4 個月可完成 Phase 1，比 fork 第三方再大改更直接

---

## 4. 核心技術棧

### 4.1 依賴清單

| 層次 | 套件 | 授權 | 用途 |
|---|---|---|---|
| ZIP 解壓 | `fflate` | MIT | xlsx unzip（比 JSZip 快 3x，純 JS no WASM） |
| XML 解析 | `fast-xml-parser` | MIT | SAX-style，省記憶體（10 萬 cell 不爆） |
| 公式 shim（按需） | `formulajs` 部分 tree-shake | MIT | 補 o-spreadsheet 缺失 Excel 函數（IFERROR、SUMPRODUCT 等） |
| 字型 shaping（Phase 7） | `harfbuzzjs` | MIT | CJK 欄寬精確估算（沿用 dobtor_doc_editor 的 WASM 模組） |
| 字型解析 | `opentype.js` | MIT | 讀 OTF/TTF metrics（沿用 dobtor_doc_editor） |
| 圖表渲染（fallback） | o-spreadsheet 內建 chart.js | MIT | Phase 5 chart mapping 降級時使用 |
| 顏色運算 | `color-string`（選用） | MIT | theme color tint/shade |
| 後端 xlsx 寫入 | `openpyxl` | MIT | Phase 6 Export 主路徑（Python） |
| 後端 xlsx 讀取 fallback | `python-calamine` | MIT | 損壞 / 含 embed chart 的 xlsx（已裝在 container） |

### 4.2 Build / Test 工具（沿用 dobtor_doc_editor 模式）

| 工具 | 版本 | 對應檔案 |
|---|---|---|
| TypeScript | 5.x | `tsconfig.json` |
| Rollup | 4.x | `rollup.config.js`（input: `static/src/core/ooxmlspreadsheet/index.ts`） |
| Vitest | 2.x | `vitest.config.ts` |
| pixelmatch | 5.x | `scripts/visual_regression_xlsx.mjs`（Phase 6 建立） |
| Playwright | 1.x | `tests/playwright/`（E2E） |

### 4.3 WASM 模組（Phase 7 啟用）

**HarfBuzz WASM** 用於 CJK 欄寬 shaping。Excel 的 column auto-width 用字型 EMU 計量單位精確計算；`ctx.measureText()` 在標楷體、新細明體上累積誤差 15-25%，導致契約工項欄被截斷。

```ts
// Phase 7 升級
import hbjs from 'harfbuzzjs'
const hb = await hbjs()
const face = hb.createFace(fontBlob)
const font = hb.createFont(face)
const width = measureCJKColumnWidth(text, font, fontSize)  // EMU-accurate
```

Phase 2 先用查表法（每個 CJK Unicode block 對應的寬度因子），Phase 7 升級至 HarfBuzz。

---

## 5. Phase 規劃（12-18 個月）

> **當前進度詳見 `docs/progress_snapshot.md`**（Phase 0 第二週建立）。本章只列 Phase 計畫，不追蹤完成度。

### Phase 0：能力盤點與架構決策（2 週）

**工作**：
- [x] 建立 `addons/dobtor_spreadsheet_editor/` 模組骨架（沿用 dobtor_doc_editor 模式）
- [x] 複製並調整 `package.json` / `tsconfig.json` / `rollup.config.js` / `vitest.config.ts`
- [x] 收集 **30-50 份真實台灣商業 xlsx fixture**（估驗表、契約工項、損益試算、月報、政府採購標單）
- [x] Fixture 分類為 8 個目錄（見 §6.3）
- [x] 對每份 fixture 用 LibreOffice Calc headless 產 PNG golden
- [x] 對每份 fixture 用 python-calamine 讀 cell values 存 JSON golden
- [x] 審計 o-spreadsheet model commands API（`setCellContent`、`updateCellFormat`、`addMerge`、`updateConditionalFormat`、`addChart`、`setNamedRange` 可用性）
- [x] 審計 OCA `spreadsheet_oca` 既有協作機制（`spreadsheet.oca.revision` schema、Bus channel 格式）
- [ ] 撰寫 ADR-001：選擇策略 (d) Hybrid，記錄放棄 Fork / Replace 的理由
- [ ] 撰寫 ADR-002：xlsx Parser 採自寫 TS 而非 SheetJS / ExcelJS 的理由
- [x] 確認 Docker 容器內 openpyxl + python-calamine 可用
- [x] 建立 `docs/capability_audit.md`、`docs/INDEX.md`、`docs/progress_snapshot.md` 骨架
- [x] 確認 CI 跑 `npm run build` + `npm run test` 空殼可通過

**產出**：
- `docs/capability_audit.md` — o-spreadsheet 與 xlsx 規格的能力對照
- `docs/architecture_decision.md` — ADR-001（Hybrid 策略）、ADR-002（自寫 Parser）
- `tests/fixtures/` — 30-50 份 xlsx + golden PNG + golden JSON
- CI：跑 vitest 空殼通過

**Exit Criteria**：
- 模組骨架可 `--init` 安裝（manifest 合法，無模型錯誤）
- Fixture 50 份 + golden PNG + golden JSON 完備
- ADR-001 與 ADR-002 簽核完成
- 第一份 Phase 1 milestone checklist 定案

---

### Phase 1：OOXML SpreadsheetML 完整 Parser（2-3 個月）

目標：**把任何合法 xlsx 100% 解析成 Workbook AST**，cell values、styles、formulas、CF、validation、defined names、merged cells 屬性無遺漏。

#### 1.1 Package 與 Relationships（1 週）
- [x] `PackageReader` class：載入 zip（fflate）、暴露 `getPart(name)` / `getRels(part)`
- [x] 解析 `[Content_Types].xml` — 每個 part 的 MIME type
- [x] 解析全部 `.rels` 檔：rId → target 映射（支援相對路徑）
- [x] 資源管線：worksheet / sharedStrings / styles / theme / drawing / chart / pivot / image part 索引

#### 1.2 單位系統（2 天）
- [x] `units.ts`：EMU、points、pixels、column-width units 互轉
- [x] Column width 特殊單位：Excel 用「最大數字字元寬度」為基準（≈ 7px @ Calibri 11pt）
- [x] Row height：half-points → pixels
- [x] DPI 處理（96 vs 72）

#### 1.3 Workbook（1 週）
- [x] `WorkbookParser`：`xl/workbook.xml` → sheets list、workbookView、calcChain、definedNames
- [x] `<sheet name r:id sheetId state>` — sheet 清單與隱藏狀態
- [x] `<definedName>` — named range（含 `_xlnm._FilterDatabase` 等 reserved names）
- [x] `<workbookView activeTab firstSheet>` — 預設啟用 tab
- [x] `<calcPr>` — 計算屬性（iterativeCalc、refMode = A1 / R1C1）

#### 1.4 SharedStrings（3 天）
- [x] `SharedStringsParser`：`xl/sharedStrings.xml` → string array
- [x] `<si><t>plain text</t></si>` — 純文字
- [x] `<si><r>` 多個子 run — rich text（含 `<rPr>` 字型樣式）
- [x] inline rich text 結構保留（Phase 2 才轉 o-spreadsheet 格式）
- [x] 解碼 `_x0020_` 等 escape sequence
- [x] xml:space="preserve" 空白保留

#### 1.5 Styles（2 週）★
- [x] `StylesParser`：`xl/styles.xml`
- [x] `<numFmts>` 自訂數字格式（id ≥ 164）+ 內建格式 ID 0-49 對照表
- [x] `<fonts>` 字型陣列（name、size、bold、italic、color、underline、strike、vertAlign）
- [x] `<fills>` 填色（patternFill + gradientFill→第一個 stop 色 solid 近似）
- [x] `<borders>` 邊框（left/right/top/bottom/diagonal × style + color）
- [x] `<cellXfs>` — cell format index pool（每個 `<xf>` 組合 numFmtId/fontId/fillId/borderId/alignment）
- [x] `<cellStyleXfs>` — named style pool
- [x] `<dxfs>` — differential formats（CF 使用）
- [x] `<tableStyles>` — 自訂表格樣式名 fallback 內建（o-spreadsheet 只認 TableStyle內建）
- [x] 完整 TypeScript 型別（含 alignment、protection 子元素）

#### 1.6 Worksheet（2 週）★ 核心
- [x] `WorksheetParser`：`xl/worksheets/sheetN.xml`
- [x] `<dimension ref>` — 資料範圍
- [x] `<sheetViews>` — showGridLines→areGridLinesVisible、freezePanes（已做）；zoomScale/selection o-spreadsheet 不支援
  - [x] `<pane xSplit ySplit topLeftCell activePane state>` — 凍結窗格
- [ ] `<sheetFormatPr defaultRowHeight defaultColWidth>` — 預設高度/寬度
- [x] `<cols>` — `<col min max width customWidth hidden bestFit>`
- [x] `<sheetData>` — `<row>` + `<c>` 主體
  - [x] `<c r t s>` — cell reference、type（`s` sharedString / `n` number / `b` boolean / `str` formula string / `e` error / `inlineStr`）、style index
  - [x] `<v>` — value
  - [x] `<f>` — formula（含 shared formula `t="shared" si ref`）
  - [x] `<is>` — inline string（rich text 支援）
- [x] `<mergeCells>` — 合併儲存格清單
- [ ] `<autoFilter ref>` + `<filterColumn>` — 自動篩選
- [x] `<conditionalFormatting>` — 條件格式（rule 細節由 §1.7 處理）
- [x] `<dataValidations>` — 資料驗證（細節由 §1.8 處理）
- [ ] `<hyperlinks>` — 超連結（rels 對應 URL）
- [ ] `<printOptions>`、`<pageMargins>`、`<pageSetup>` — 列印設定（Phase 1 capture-only）
- [ ] `<headerFooter>` — 頁首頁尾（Phase 1 capture-only）
- [ ] `<rowBreaks>`、`<colBreaks>` — 分頁符（Phase 1 capture-only）

#### 1.7 Conditional Formatting（1 週）
- [x] `CFParser`：`<conditionalFormatting sqRef>` → rules
- [x] `<cfRule type="cellIs" operator priority>` + `<formula>` — 比較規則
- [x] `<cfRule type="expression">` + `<formula>` — 公式規則
- [x] `<cfRule type="colorScale">` + `<colorScale>` + `<cfvo>` × 2/3 + `<color>` × 2/3
- [x] `<cfRule type="dataBar">` + `<dataBar>` + `<cfvo>` × 2 + `<color>`
- [x] `<cfRule type="iconSet">` + `<iconSet iconSet>` + `<cfvo>` × 3-5
- [x] `<cfRule type="containsText|notContainsText|beginsWith|endsWith">`
- [x] `<cfRule type="duplicateValues|uniqueValues">`
- [x] `<cfRule type="top10">` — top N / bottom N
- [x] `<cfRule dxfId>` — 對應 dxfs 取得 differential format

#### 1.8 Data Validations（3 天）
- [x] `DataValidationParser`：`<dataValidation type sqRef showDropDown>`
- [x] type = `list`：`<formula1>`（清單 range 或 inline `"opt1,opt2,opt3"`）
- [x] type = `whole` / `decimal` / `date` / `time` / `textLength`：operator + formula1 + formula2
- [x] type = `custom`：`<formula1>` 自訂條件
- [ ] error / input message 屬性

#### 1.9 Theme（3 天）
- [x] `ThemeParser`：`xl/theme/theme1.xml`
- [x] `<a:clrScheme>` — 12 色 token（dk1、lt1、dk2、lt2、accent1-6、hlink、folHlink）
- [x] `<a:fontScheme>` — major / minor font（含 East Asian 字型對應）
- [x] 用於 Style resolver 的 theme color reference

#### 1.10 Defined Names（2 天）
- [ ] 已在 §1.3 解析；§1.10 處理跨 sheet 引用（如 `Sheet1!$A$1:$B$2`）
- [x] reserved names：`_xlnm.Print_Area`、`_xlnm._FilterDatabase`、`_xlnm.Print_Titles`

#### 1.11 Tables（Excel Table 物件）（3 天）
- [x] `TableParser`：`xl/tables/tableN.xml`
- [x] `<table id name displayName ref totalsRowShown>` + `<tableColumns>` + `<tableStyleInfo>`
- [x] 與 worksheet 的 `<tableParts>` 對應
- [ ] structured reference 解析所需（Phase 3 公式 compiler 用）

**Exit Criteria**：
- Parser 對 50 份 fixture 全部無 error
- Cell values 提取率 > 95%（用 python-calamine 比對）
- Merged cells 100% 結構正確
- 完整 TypeScript 型別（無 `any`）
- Vitest unit test > 80 個 case

---

### Phase 2：Cell Rendering & Text Metrics（1-1.5 個月）

**這是讓 xlsx 視覺與 Excel 接近的根本層**。

#### 2.1 StyleResolver（xf cascade）（1 週）★
- [x] `StyleResolver`：cellXfs[index] → 解析 numFmtId / fontId / fillId / borderId / alignment
- [x] cellStyleXfs 繼承鏈：cell 引用 cellXf，cellXf 可繼承 cellStyleXf
- [x] applyNumberFormat / applyFont / applyFill / applyBorder / applyAlignment 旗標處理
- [x] 解析完成後 flatten 為單一 `ResolvedStyle` object

#### 2.2 ThemeResolver（3 天）
- [x] `ThemeResolver`：解析 theme color reference
- [x] `<color theme="0" tint="-0.5">` → 從 colorScheme 取 dk1，套 tint 變暗 50%
- [x] tint/shade 演算法（HSL luminance 計算，沿用 dobtor_doc_editor 的 Sprint 130 邏輯）
- [x] Indexed color（Excel 舊版 56 色 palette）

#### 2.3 NumberFormatCompiler（1-1.5 週）★
- [ ] `NumberFormatCompiler`：Excel format code → o-spreadsheet format string
- [x] 內建 format ID 0-49 對照表（`General`、`0`、`0.00`、`#,##0`、`yyyy/mm/dd` 等）
- [x] 自訂 format（id ≥ 164）解析：positive;negative;zero;text 四段語法
- [x] 條件色彩 `[Red]`（會計負數紅字，靜態 textColor；o-spreadsheet 格式引擎不支援色彩 token，故負值套紅字）
- [x] 條件運算 [>1000] → 剝除條件 token、套基礎數字格式（o-spreadsheet 不支援條件比較）
- [ ] locale token `[$-404]` (zh-TW)、`[$-409]` (en-US)
- [x] 日期 token：`yyyy`/`yy`、`mm`/`m`（月）、`dd`/`d`（日）+ 民國年 `e`/`ee`/`gg`（S43）
- [ ] 時間 token：`hh`、`mm`（分鐘 vs 月份判定）、`ss`、`AM/PM`（未做；ChienYi 為日期、無時間）
- [x] 中華民國年（民國紀年 `e` token）
- [x] 台灣常見 15 種自訂格式：千分位/%/貨幣(取數字)/會計負數紅字/中文日期/民國年 等（toSafeNumberFormat + 日期渲染 + 紅字）
  - `#,##0` `#,##0.00` `#,##0.000`（工程計量）
  - `0.00%` `0.0%`（百分比）
  - `_($* #,##0.00_);[Red]_($* (#,##0.00);_($* "-"??_);_(@_)`（會計）
  - `yyyy"年"m"月"d"日"`（中文日期）
  - `[h]:mm:ss`（累計時數）

#### 2.4 Font / Cell Style Interop（1 週）
- [x] `StyleInterop`：ResolvedStyle → o-spreadsheet `Style` object
- [x] 字型、字色、背景色、邊框、對齊、wrapText、indent
- [ ] Rich text cell：拆分為 o-spreadsheet 多 segment cell

#### 2.5 CJK 欄寬估算（查表法）（1 週）
- [x] CJKWidthEstimator：CJK 全形=2、半形=1；無明確欄寬的欄依內容估寬（HTML 預覽）
- [x] 處理半形/全形混合（displayWidth 逐 code point）
- [ ] Excel `bestFit` cols 計算後寫入 o-spreadsheet column width
- [ ] Phase 7 升級為 HarfBuzz WASM

**Exit Criteria**：
- 50 份 fixture 樣式還原 B+ 級
- ChienYi 估驗表數字格式 100% 正確
- CJK 欄寬偏差 < 15%（Phase 7 升級至 < 5%）

---

### Phase 3：Formula Engine Compatibility（3-4 個月）★ 最長 Phase

目標：**讓 Excel 公式在 o-spreadsheet 中被正確解析與計算**。

#### 3.1 公式 Gap Analysis（1 週）
- [x] `FormulaGapAnalysis` 腳本：掃 50 份 fixture，提取所有 `<f>` 元素，解析函數名
- [x] 對比 o-spreadsheet 內建函數清單，輸出缺口表
- [x] ChienYi 業務文件 Top 20 必須函數識別

#### 3.2 公式語言相容（2-3 週）★
- [x] `FormulaCompiler`：A1 notation 直接 pass-through
- [ ] R1C1 notation 轉 A1：`R[+n]C[+m]` → relative offset、`Rn Cm` → absolute
- [ ] Structured table reference：`Table1[@column]` → 具體 A1 range（需 §1.11 table part）
- [ ] Structured: `Table1[#All]`、`Table1[#Headers]`、`Table1[#Totals]`、`Table1[#Data]`
- [ ] Array formula：`{=SUM(A1:A10*B1:B10)}` → o-spreadsheet array formula
- [ ] Dynamic array operator `#`：`=A1#` → 降級為靜態值（Phase 7 若 o-spreadsheet 支援再升級）
- [ ] Implicit intersection `@`：`=@A1:A10` → 行內單值
- [ ] 跨 sheet 引用：`Sheet1!A1`、`'Sheet 1'!A1`（含空格的單引號）
- [ ] External link 引用：`[Book1.xlsx]Sheet1!A1` → 降級為靜態值
- [x] Shared formula 展開（§1.6 capture，§3.2 expand to per-cell formula）

#### 3.3 缺失函數 shim（4-6 週）
- [x] 確認 o-spreadsheet 18.0.48 內建函數清單（`addFunction` 介面）
- [ ] ChienYi 必須函數實作（在 plugin 層 `addFunction` 注入）：
  - [x] `IFERROR` / `IFNA`（容錯）
  - [x] `SUMPRODUCT`（加權計算、估驗常用）
  - [x] `SUMIFS` / `COUNTIFS` / `AVERAGEIFS`（多條件）
  - [x] `DATEDIF`（工程工期）
  - [x] `TEXT`（格式化輸出）
  - [x] `INDIRECT` / `OFFSET`（動態 range）
  - [x] `WORKDAY` / `NETWORKDAYS` / `EDATE` / `EOMONTH`（日期計算）
  - [x] `VLOOKUP` / `HLOOKUP` / `XLOOKUP` / `MATCH` / `INDEX`
  - [x] `ROUND` / `ROUNDUP` / `ROUNDDOWN` / `CEILING` / `FLOOR` / `MROUND`
  - [x] `LEN` / `LEFT` / `RIGHT` / `MID` / `FIND` / `SEARCH` / `SUBSTITUTE` / `REPLACE`
  - [x] `CONCAT` / `CONCATENATE` / `TEXTJOIN`
  - [x] `RANK` / `LARGE` / `SMALL` / `PERCENTILE` / `QUARTILE`
- [ ] `formula.js` tree-shake 引入補齊 30+ 通用函數
- [ ] Excel 與 o-spreadsheet 函數行為差異記錄（邊界值、空白處理）

#### 3.4 Volatile Functions（1 週）
- [x] NOW/TODAY/RAND/RANDBETWEEN/INDIRECT/OFFSET 納入白名單→餵公式，o-spreadsheet 自動 volatile 重算
- [x] o-spreadsheet 內建 recalc 處理 volatile（無需額外整合）

#### 3.5 公式錯誤值（3 天）
- [x] Cell `t="e"` + 錯誤值（`#NULL!` / `#DIV/0!` / `#VALUE!` / `#REF!` / `#NAME?` / `#NUM!` / `#N/A` / `#GETTING_DATA`）
- [x] o-spreadsheet 錯誤值對應顯示

**Exit Criteria**：
- 50 份 fixture cell value pass rate > 90%
- ChienYi 估驗表公式 100% 計算正確
- o-spreadsheet formula gap < 20 個 critical functions
- Vitest formula compiler test > 100 個 case

---

### Phase 4：Conditional Formatting & Data Validation（1-1.5 個月）

#### 4.1 Conditional Formatting Compiler（3-4 週）
- [ ] `CFCompiler`：CFParser AST → o-spreadsheet `ConditionalFormat` objects
- [x] `cellIs` operator → 對應 o-spreadsheet operator
- [x] `colorScale` 2-color / 3-color：minColor / midColor / maxColor + threshold types（num / percent / formula / percentile）
- [x] `dataBar`：minLength / maxLength / color / showValue / direction
- [x] `iconSet`：iconSetType（`3Arrows` / `3TrafficLights` / `5Rating` 等）+ threshold
- [x] iconSet 若 o-spreadsheet 不支援 → 降級為 3-color scale
- [ ] `expression`：Excel formula → FormulaCompiler → o-spreadsheet expression CF
- [x] `containsText` / `notContainsText` / `beginsWith` / `endsWith`
- [ ] `duplicateValues` / `uniqueValues`
- [ ] `top10` / `bottom10`（含 percent 屬性）
- [x] sqRef 多範圍解析（空格分隔的 `A1:B2 C3:D4`）
- [x] dxfId → dxfs 取得 differential format（color / font / border / fill）

#### 4.2 Data Validation Compiler（1 週）
- [x] `DataValidationCompiler`：DataValidation AST → o-spreadsheet validation
- [x] `list` type → dropdown（inline 清單 vs range 清單）
- [x] `whole` / `decimal` / `date` / `time` / `textLength` type + operator
- [x] `custom` type → 公式驗證
- [ ] error message / input message 整合

#### 4.3 Visual Regression（1 週）
- [ ] CF rule 解析 + pixelmatch 比對 golden PNG
- [ ] dataBar / colorScale 視覺差異 < 5%

**Exit Criteria**：
- ChienYi 月報損益試算的紅負數 / 綠正數正確渲染
- 50 份 fixture CF 渲染正確率 > 85%
- List validation 下拉正常顯示

---

### Phase 4.5：產品化基礎建設（6-8 週）★ 早插入避免孤立模組

> **教訓**：dobtor_doc_editor Sprint 200+ 期間出現孤立模組反模式（13 輪 +900 測試但產品引用數 = 0）。本模組吸取教訓，Phase 4 完成立刻插入 Phase 4.5，把 Parser 接上 Odoo 後台讓 user 實際用。

#### 4.5.1 Odoo 後端整合（2 週）
- [ ] `models/spreadsheet_editor.py`：`inherit = ['spreadsheet.spreadsheet']`，新增 `xlsx_source` Binary + `source_filename` Char + `fidelity_grade` Char + `parse_log` Text
- [ ] `controllers/xlsx_controller.py`：
  - POST `/web/spreadsheet/xlsx/import` — 前端上傳 → JS parser → 存 o-spreadsheet JSON
  - GET `/web/spreadsheet/xlsx/export` — o-spreadsheet JSON → openpyxl → xlsx download
- [ ] `wizards/xlsx_import_wizard.py`：繼承 `spreadsheet.spreadsheet.import`，新增 xlsx 高保真路徑
- [ ] `views/spreadsheet_editor.xml`：後台 list/form view，fidelity grade badge

#### 4.5.2 ChienYi 整合 mixin（1 週）
- [ ] `models/xlsx_mixin.py`：`xlsx.linked.mixin` — `res_model` + `res_id` FK
- [ ] 對標 `dobtor_doc_editor` 的 `doc.linked.mixin`
- [ ] ChienYi 業務模型可 `_inherit = ['xlsx.linked.mixin']`：估驗、契約變更、月報

#### 4.5.3 Portal 嵌入（1 週）
- [ ] `/my/spreadsheet/<id>` 路由（auth='user'，ir.rule 從 OCA security 繼承）
- [ ] OWL Component 嵌入 portal layout
- [ ] 行動版降級為 read-only viewer（手機編輯 xlsx 體驗差）

#### 4.5.4 安全與穩定（1 週）
- [x] Zip bomb defense：解壓後總大小 < 100MB、worksheet count < 100、cell count < 5M
- [x] Upload size 限制：20MB（後端 + 前端雙驗）
- [x] File magic check：確認 `[Content_Types].xml` 存在才解析
- [x] 異常處理：parse 失敗 → OWL try/catch 顯示友善錯誤、UI 不掛（S46；OCA raw fallback 未做）

#### 4.5.5 AutoSave / 版本快照（1 週）
- [ ] AutoSave：5 分鐘 idle 自動 commit revision（hook 進 OCA `spreadsheet.oca.revision`）
- [ ] 版本快照 UI：OWL panel 列出 revision 列表，可 restore
- [ ] 對標 dobtor_doc_editor 的 `doc.version` model 模式

#### 4.5.6 匯出稽核（1 週）
- [ ] `models/xlsx_export_log.py`：每次匯出記錄 user / record / file / timestamp
- [ ] 每日 cron health-check：列出近 7 天「無 res_model 綁定的匯出」
- [ ] 對標 dobtor_doc_editor 的 `doc.editor.export.log` 模式

**Exit Criteria**：
- ChienYi user 可從後台或 Portal 上傳 xlsx → 在 o-spreadsheet 編輯 → 下載修改後 xlsx
- ChienYi 第一個業務模型（建議：`payment.estimate`）整合 mixin 並產出實際使用案例
- Health-check cron 啟用、Zip bomb 防護驗證

---

### Phase 5：Pivot / Chart / Drawing（2-3 個月）

#### 5.1 Pivot Cache + Pivot Table（4-5 週）
- [ ] `PivotCacheParser`：`xl/pivotCache/pivotCacheDefinitionN.xml` → cacheFields + cacheRecords
- [ ] `PivotTableParser`：`xl/pivotTables/pivotTableN.xml` → row/col fields、data fields、filters、pivotArea
- [ ] `PivotMapper`：Excel pivot AST → o-spreadsheet pivot model
- [ ] **設計挑戰**：o-spreadsheet pivot 綁 Odoo model；Excel pivot 綁 local data
- [ ] 解法：擴展 o-spreadsheet 加入 `LocalDataPivot` 類型（或降級為靜態快照表格）
- [ ] Pivot filter / slicer 處理

#### 5.2 Chart（4-5 週）
- [x] `ChartParser`：`xl/charts/chartN.xml`（DrawingML chartSpace）→ ChartAst
- [x] 解析 series（`<c:ser>` 含 strCache / numCache 稀疏對位）
- [x] 解析 categories、values、title、legend、axes
- [x] `ChartMapper`：Excel chart type → o-spreadsheet chart type
  - `bar` / `column` → bar（依 barDir 區分 horizontal / vertical）
  - `line` → line
  - `pie` / `doughnut` → pie
  - `area` → line（fill area 降級）
  - `scatter` → line（散點降級）
  - `radar` → 不支援（顯示警告）
  - `bubble` → scatter 降級
  - `stock` → line 降級
  - `surface` → 不支援
- [x] 套用 theme color：series srgbClr/schemeClr → dataSet.backgroundColor（經 theme accent 對照）
- [ ] Chart 與 cell range 連動（編輯資料時 chart 同步）

#### 5.3 Drawing / Image（1-2 週）
- [x] `DrawingParser`：`xl/drawings/drawingN.xml` → from/to anchor (EMU)、ext、rotation
- [x] `<xdr:oneCellAnchor>` / `<xdr:twoCellAnchor>` / `<xdr:absoluteAnchor>`
- [ ] `<xdr:pic>` 圖片：blip→base64 已可解析，但 o-spreadsheet image figure 結構需 ImageProvider（inline data URL 會 load 失敗）→ 延後
- [ ] `ImageImporter`：圖片 binary → o-spreadsheet image API（確認 o-spreadsheet image 支援程度）
- [ ] `<xdr:sp>` shape（矩形、箭頭、文字方塊）— Phase 5 降級為 image，Phase 7 升級

#### 5.4 Sparklines（選做、1 週）
- [ ] `SparklineParser`：`<x14:sparklineGroups>`（Excel 2010+ extension）
- [ ] 降級為迷你 chart 或 cell 內 SVG

**Exit Criteria**：
- ChienYi 進度 S 曲線（line + bar）正確渲染
- 50 份 fixture pivot 結構保留率 > 80%
- 含圖片的 xlsx 圖片位置誤差 < 10px

---

### Phase 6：Export 對稱性（1-2 個月）

xlsx 匯出是 Parser 的反向：o-spreadsheet model → OOXML SpreadsheetML → zip。

#### 6.1 策略決定（1 週）
- [ ] ADR-003：Python openpyxl（後端，較成熟）vs TypeScript（前端，可離線）
- [ ] 預設 Python 為 Phase 6 主路徑（openpyxl 已 production-ready）
- [ ] 前端 TS export 留 Phase 7+ 視需求

#### 6.2 Python xlsx Writer（3-4 週）
- [ ] `xlsx_writer.py`：o-spreadsheet JSON → openpyxl Workbook
- [x] Cell values + formulas + styles（font/fill/border/numFmt）
- [x] Merged cells、column widths、row heights
- [x] Conditional formatting（dxf + rule）
- [x] Data validation
- [x] Defined names（匯出回寫 workbook.xml definedNames，含 localSheetId/hidden）
- [x] Charts（openpyxl chart API）
- [x] Drawings / images
- [ ] Theme（保留原 theme1.xml 或重新生成）

#### 6.3 Round-trip Test（2-3 週）
- [x] 50 份 fixture：xlsx → import → export → python-calamine 讀回 → diff
- [x] Cell value pass rate > 90%
- [ ] Style pass rate > 80%
- [ ] 在 Excel 2021 / LibreOffice Calc / Google Sheets 三端開啟確認無警告

**Exit Criteria**：
- Round-trip cell value pass rate > 90%
- Exported xlsx 在 Excel 2021 可正常開啟（無 repair 警告）
- ChienYi 估驗表編輯後匯出，數字格式 / 公式 / 樣式皆保留

---

### Phase 7：效能優化與邊緣（持續）

- [ ] 大檔解析（> 5MB）：Web Worker parser、streaming SAX 模式
- [ ] Virtual scroll：10 萬行 sheet 只渲染可視 range（確認 o-spreadsheet 是否已支援）
- [ ] IndexedDB AST cache：相同 xlsx hash → 跳過 parse 直接載入
- [ ] HarfBuzz WASM 升級 `CJKWidthEstimator`（Phase 2.5 查表法 → Phase 7 精確 shaping）
- [ ] Glyph 快取（key: font+codepoint+size）
- [ ] 邊緣 xlsx 相容：LibreOffice / WPS / Google Sheets 匯出的 xlsx 方言
- [ ] Excel 2007 / 2010 舊版 xlsx 相容
- [ ] Benchmark：100k 行 × 20 列 sheet parse < 5s、initial render < 1s

---

### Phase 8：業務模板 / ChienYi 整合（待 user 認可、ADR）

**非 xlsx 匯入 phase、與 Phase 0-7 工時分開計算**。針對 ChienYi 業務模板需求。

走 user-driven 流程：

- [ ] 監造日報試算範本（工項量、人力、機具統計、含 SUM/AVERAGEIF 公式）
- [x] 估驗試算範本（本期數量、累計數量、本期金額、保留款計算）
- [ ] 契約工項分析範本（工期進度 S 曲線、費用對比、含 chart）
- [ ] 月報損益試算範本（含 CF 條件格式）
- [x] `construction_payment` 模組整合：`payment.estimate` 一鍵打開對應 spreadsheet
- [ ] `construction_progress` 模組整合：進度表編輯改用 xlsx 介面
- [ ] ChienYi Portal 嵌入：`/my/spreadsheet/<id>` 在 Portal 頁面中嵌入

---

## 6. 測試與驗證體系

### 6.1 測試金字塔

```
         ┌─────────────────┐
         │   Visual E2E    │   ← pixelmatch vs LibreOffice Calc
         │   (50 fixtures) │
         ├─────────────────┤
         │  Round-trip     │   ← xlsx → import → export → diff
         │  (50 fixtures)  │
         ├─────────────────┤
         │ Golden Cell JSON│   ← python-calamine 值比對
         │  (50 fixtures)  │
         ├─────────────────┤
         │   Integration   │   ← parser → bridge → o-spreadsheet
         │   (200+ cases)  │
         ├─────────────────┤
         │   Unit tests    │   ← 每個 parser / compiler 函數
         │   (500+ cases)  │
         └─────────────────┘
```

### 6.2 Visual Regression Pipeline

```bash
# 每份 fixture xlsx 產出 3 組 PNG
npm run test:visual:xlsx

# Step 1: LibreOffice Calc headless → reference.png
libreoffice --headless --convert-to png:writer_png_Export fixture.xlsx

# Step 2: 我方渲染（在 Playwright + o-spreadsheet headless）→ actual.png
node scripts/render_xlsx.mjs fixture.xlsx > actual.png

# Step 3: pixelmatch diff
pixelmatch reference.png actual.png diff.png
# → 失敗條件：差異 > 5%
```

### 6.3 Fixture Sets

| 目錄 | 類別 | 數量 | 來源 |
|---|---|---|---|
| `01_simple_formula` | SUM / AVERAGE / IF 基本公式 | 8 | 通用模板 |
| `02_merged_cells` | 跨欄/跨列合併 | 8 | 估驗表類 |
| `03_number_format` | 自訂數字 / 日期 / 貨幣（含台灣會計格式） | 6 | 月報類 |
| `04_conditional_format` | colorScale / dataBar / iconSet / cellIs | 6 | 損益試算類 |
| `05_multi_sheet` | 跨 sheet 公式 / VLOOKUP / INDIRECT | 5 | 月報類 |
| `06_chart` | bar / line / pie / S 曲線 | 5 | 進度報告類 |
| `07_pivot` | 樞紐分析表 | 4 | 統計類 |
| `08_chienyii_business` | 估驗表 / 工項 / 月報 / 政府採購標單 | 10 | ChienYi 實檔 |

### 6.4 Benchmarking

| 指標 | 目標 |
|---|---|
| 中型 xlsx（estimate 2000 行）parse | < 1s |
| 中型 xlsx initial render | < 500ms |
| 大型 xlsx（10 萬行）parse | < 5s（Phase 7） |
| 大型 xlsx 不 OOM（heap < 500MB） | Phase 7 |
| 50 fixture full test suite | < 5min CI |
| Round-trip 50 fixture pass rate | > 90% |

### 6.5 開發紀律（沿用 dobtor_doc_editor 22 條 + xlsx 候選）

從 dobtor_doc_editor `CONTRIBUTING.md §5` 整批繼承 22 條紀律。xlsx 特化候選新增 3-5 條：

- **候選 X1**：改 FormulaCompiler 強制跑全 fixture cell value diff（同紀律 #1 對 renderer 的規矩）
- **候選 X2**：新增缺失函數 shim 必須有對照 Excel 行為的 test case（邊界值含 0 / 空 / 負 / 文字）
- **候選 X3**：StyleResolver 改動必須跑 dxf 對照（CF 用 dxf，cell 用 cellXf，邏輯易混淆）
- **候選 X4**：xlsx round-trip pass rate 退化 > 2% 必須 hold ship（與 VR mean 等價）
- **候選 X5**：o-spreadsheet plugin API 變動須 cross-check Odoo upstream commit log

最重要的紀律 #18：**開工大型新 feature 前必須先對齊規畫書真實 scope**（沿用 dobtor docx Sprint 90-109 教訓）。

---

## 7. 程式碼組織

```
dobtor_spreadsheet_editor/
├── __init__.py
├── __manifest__.py                # depends: ['spreadsheet_oca']
├── package.json                   # 沿用 dobtor_doc_editor 模式
├── tsconfig.json
├── rollup.config.js               # input: ooxmlspreadsheet/index.ts
├── rollup.visual_regression.config.js
├── vitest.config.ts
├── Makefile
├── CONTRIBUTING.md                # 22 條紀律 + xlsx 候選
├── NOTICE.md
├── controllers/
│   └── xlsx_controller.py         # upload / download / version
├── models/
│   ├── __init__.py
│   ├── spreadsheet_editor.py      # inherit spreadsheet.spreadsheet
│   ├── xlsx_mixin.py              # xlsx.linked.mixin
│   └── xlsx_export_log.py         # 匯出稽核
├── wizards/
│   └── xlsx_import_wizard.py      # 繼承 OCA wizard
├── views/
│   └── spreadsheet_editor.xml
├── security/
│   ├── ir.model.access.csv
│   └── doc_security.xml
├── data/
│   └── ir_cron_data.xml           # health-check cron
├── docs/
│   ├── INDEX.md                   # sprint audit 索引
│   ├── progress_snapshot.md       # 進度快照
│   ├── architecture_decision.md   # ADR-001 / 002 / ...
│   ├── capability_audit.md        # Phase 0 能力審計
│   ├── scope_decision.md          # docx vs xlsx vs QWeb PDF 分流
│   └── glossary.md                # 術語表（與附錄 B 同步）
├── tests/
│   ├── __init__.py
│   ├── test_xlsx_import.py        # TransactionCase HTTP test
│   ├── test_security.py           # ACL / record rule
│   ├── test_zip_guard.py          # Zip bomb defense
│   ├── fixtures/
│   │   ├── 01_simple_formula/
│   │   ├── 02_merged_cells/
│   │   ├── 03_number_format/
│   │   ├── 04_conditional_format/
│   │   ├── 05_multi_sheet/
│   │   ├── 06_chart/
│   │   ├── 07_pivot/
│   │   ├── 08_chienyii_business/
│   │   └── scripts/generate_golden.sh
│   ├── unit/                      # Vitest unit
│   ├── integration/               # Vitest integration
│   └── playwright/                # E2E
├── scripts/
│   ├── visual_regression_xlsx.mjs # Phase 4+ VR pipeline
│   ├── formula_gap_analysis.mjs   # Phase 3.1 工具
│   └── perf_baseline.mjs          # Phase 7 效能基線
├── tools/
│   ├── parse_xlsx_cli.ts          # CLI 解析（Node 環境）
│   └── dist/                      # rollup 輸出
└── static/src/
    ├── core/
    │   └── ooxmlspreadsheet/      # ★ 主體
    │       ├── index.ts           # rollup 入口：importXlsx(ArrayBuffer)
    │       ├── package/           # Layer 1
    │       │   ├── PackageReader.ts
    │       │   ├── ContentTypes.ts
    │       │   └── RelationshipResolver.ts
    │       ├── parser/            # Layer 2
    │       │   ├── WorkbookParser.ts
    │       │   ├── WorksheetParser.ts
    │       │   ├── SharedStringsParser.ts
    │       │   ├── StylesParser.ts
    │       │   ├── ThemeParser.ts
    │       │   ├── FormulaParser.ts
    │       │   ├── CFParser.ts
    │       │   ├── DataValidationParser.ts
    │       │   ├── TableParser.ts
    │       │   ├── PivotCacheParser.ts
    │       │   ├── PivotTableParser.ts
    │       │   ├── ChartParser.ts
    │       │   └── DrawingParser.ts
    │       ├── ast/               # TypeScript 型別
    │       │   ├── Workbook.ts
    │       │   ├── Sheet.ts
    │       │   ├── Cell.ts
    │       │   ├── Style.ts
    │       │   ├── Formula.ts
    │       │   └── index.ts
    │       ├── style/             # Layer 3a
    │       │   ├── StyleResolver.ts        # cellXfs cascade
    │       │   ├── ThemeResolver.ts        # tint/shade
    │       │   ├── NumberFormatCompiler.ts # zh-TW locale
    │       │   └── StyleInterop.ts         # → o-spreadsheet Style
    │       ├── formula/           # Layer 3b
    │       │   ├── FormulaCompiler.ts      # R1C1 / structured ref
    │       │   ├── MissingFunctions.ts     # shim
    │       │   └── FormulaGapAnalysis.ts
    │       ├── cf/                # Layer 3c
    │       │   └── CFCompiler.ts
    │       ├── validation/
    │       │   └── DataValidationCompiler.ts
    │       ├── chart/
    │       │   └── ChartMapper.ts          # Excel → o-spreadsheet chart
    │       ├── pivot/
    │       │   └── PivotMapper.ts          # 含 LocalDataPivot 擴展
    │       ├── drawing/
    │       │   ├── DrawingMapper.ts
    │       │   └── ImageImporter.ts
    │       ├── font/              # 沿用 dobtor_doc_editor 字型管線
    │       │   ├── CJKWidthEstimator.ts    # Phase 2.5 查表法
    │       │   ├── FontLoader.ts
    │       │   └── CJKFallback.ts
    │       ├── render/            # Layer 4
    │       │   └── XlsxModelBridge.ts      # AST → o-spreadsheet commands
    │       ├── export/            # Phase 6（TS 版備用）
    │       │   └── XlsxWriter.ts
    │       └── utils/
    │           ├── units.ts                # EMU / pt / px / col-width
    │           ├── colorUtils.ts           # tint / shade / argb
    │           ├── cellAddress.ts          # A1 / R1C1 / [row,col]
    │           └── xml.ts                  # fast-xml-parser wrapper
    ├── components/
    │   ├── XlsxImportButton.js             # OWL component
    │   └── VersionHistoryPanel.js
    ├── lib/
    │   └── (vendor 第三方函式庫)
    └── css/
        └── xlsx_editor.css
```

---

## 8. 風險與備案

### 8.1 主要風險

| 風險 | 機率 | 影響 | 對策 |
|---|---|---|---|
| o-spreadsheet plugin API 不穩定 | 中 | 大 | 只用公開 API、加 adapter 隔離；Plan B fork |
| 公式覆蓋率達不到 ChienYi 需求 | 中 | 中 | Phase 3.1 先做 gap analysis、formula.js tree-shake；無法 shim 的公式顯示 tooltip + cached value |
| CJK 欄寬估算偏差 | 高 | 中 | Phase 2.5 查表法 → Phase 7 HarfBuzz 升級；UI 加「重算欄寬」按鈕 |
| 大型 xlsx（> 5MB）解析超時 | 中 | 中 | Phase 7 Web Worker + streaming；先加 20MB upload 限制；超閾值切 Python python-calamine fallback |
| OCA spreadsheet_oca upstream 升級破壞繼承 | 低 | 中 | `__manifest__.py` 鎖 depends 不鎖版本；只加欄位不覆寫方法；plugin 注入不 monkey-patch |
| Style cascade 邏輯複雜 cellXfs vs dxfs | 中 | 中 | Phase 1.5 + Phase 4.1 雙確認；參考 LibreOffice `sc/source/filter/oox/stylesbuffer.cxx` 實作 |
| Excel chart 類型多（15+）無法全支援 | 高 | 中 | 降級對照表（§5.2）；unsupported 類型顯示 placeholder + 開發者警告 |
| Pivot table 與 Odoo-model pivot 衝突 | 中 | 中 | 設計 LocalDataPivot 擴展；或降級為靜態快照 |
| 時程超過 18 個月 | 中 | 大 | Phase 停損；任一 Phase 超 50% 重評估 |
| Scope drift | 中 | 大 | 紀律 #18；新 feature 與規畫書不符優先誠實 revert |

### 8.2 Plan B：若 o-spreadsheet plugin API 無法滿足

**備案**：分階段 fork：

1. 第 1 年：plugin 層做到極限（90% 場景可用）
2. 第 2 年：若特定功能（如 Excel pivot、進階 CF）真的卡死，fork o-spreadsheet 並維護 upstream sync
3. Fork 後維護成本預估每年 1-2 人月，需與 user 重新評估投入

### 8.3 Plan C：若需要提前上線（6 個月 B+ 版本）

完成 Phase 0-3 + Phase 4.5，跳過 Phase 4 / 5 / 6：

- xlsx 上傳 → cell values 100% 正確
- 基本樣式（字型 / 顏色 / 邊框）> 85%
- Merged cells 正確
- 台灣常見 15 種數字格式
- ChienYi 常用 30 個公式
- 匯出回 xlsx（openpyxl 基礎版，無 CF / chart）

對 ChienYi 估驗表、契約工項已夠用，可先上線收 user feedback，再決定 Phase 4-6 優先序。

---

## 9. 人力與時程矩陣

### 9.1 等級對應時程

| 配置 | B 級（基礎可用） | B+ 級（ChienYi 完整） | A- 級（商業水準） | A 級（Google Sheets 級） |
|---|---|---|---|---|
| 1 人全職 | 5 個月 | 10-12 個月 | 15-18 個月 | 24-30 個月 |
| 3 人團隊 | 2 個月 | 6-7 個月 | 10-12 個月 | 15 個月 |
| 5 人團隊 | 1.5 個月 | 4-5 個月 | 7-8 個月 | 12 個月 |

### 9.2 三人團隊建議配置

| 角色 | 專精 | 負責 Phase |
|---|---|---|
| 工程師 A | OOXML、XML、TypeScript | Phase 1（Parser）、Phase 2（Style）、Phase 6（Export） |
| 工程師 B | Formula 引擎、Pivot、Chart | Phase 3（Formula）、Phase 4（CF/Validation）、Phase 5（Pivot/Chart） |
| 工程師 C | Odoo、Python、前端整合、測試 | Phase 0（基建）、Phase 4.5（產品化）、測試體系、Phase 8（ChienYi 整合） |

**時程**：10-12 個月到 B+ 級，14-16 個月到 A- 級。

### 9.3 五人團隊（建議配置）

增加：
- 工程師 D：Formula 引擎專職（與工程師 B 分工複雜函數）
- 工程師 E：Visual / Layout 專職（CJK 欄寬、CF 渲染、Chart 視覺）

**時程**：7-8 個月到 A- 級，12 個月到 A 級。

### 9.4 ChienYi 1 人實際推薦路徑（建議）

| 月份 | 主要工作 | 階段交付 |
|---|---|---|
| M0-M0.5 | Phase 0 模組骨架 + Fixture | ADR 簽核 |
| M1-M3 | Phase 1 Parser | Parser 完整、cell value 95%+ |
| M4-M5 | Phase 2 Style/NumberFormat | B 級可用 |
| M5-M6 | Phase 4.5（提前插入）| **第一次 user 可用 demo** |
| M6-M9 | Phase 3 Formula | B+ 級可用 |
| M9-M10 | Phase 4 CF/Validation | A- 級基礎 |
| M10-M12 | Phase 5 Pivot/Chart 部分 | 進度報告類可用 |
| M12-M14 | Phase 6 Export | Round-trip 可用 |
| M14-M16 | Phase 7 效能 + Phase 5 補完 | 大檔可用 |
| M16-M18 | Phase 8 ChienYi 整合 | 業務模板上線 |

---

## 10. 閱讀與參考清單

### 10.1 規格書（必讀）

- **ECMA-376 5th Edition Part 1** — SpreadsheetML 規格
  - **§18.1 Fundamentals** — Workbook 結構、Part 關係（2h）
  - **§18.3 Worksheets** — cells / rows / cols / sheetView / mergeCells（必讀，4h）
  - **§18.4 SharedStrings** — string pool + rich text（1h）
  - **§18.8 Styles** — numFmts / fonts / fills / borders / xf cascade（必讀，4h）
  - **§18.9 Tables** — Excel Table 物件、structured reference（2h）
  - **§18.10 PivotTables** — pivotCacheDefinition / pivotTableDefinition（4h）
  - **§18.12 ConditionalFormatting** — 全部 rule types（3h）
  - **§18.17 DataValidations**（1h）
  - **§18.18 Simple Types** — token 字典（參考）
- **ECMA-376 Part 1 §20** — DrawingML（chart、drawing、shape，4h）
- **ECMA-376 Part 1 §22** — ContentTypes / Relationships（1h）

### 10.2 參考原始碼

**Odoo o-spreadsheet（★ 主要對接目標）**：
- https://github.com/odoo/o-spreadsheet — 主 repo
- `src/plugins/` — plugin 擴展介面（學 `addPlugin` / `addFunction` 用法）
- `src/types/commands.ts` — command 清單（XlsxModelBridge 對接）
- `src/functions/` — 內建函數實作（gap analysis 參考）
- `src/xlsx/` — 既有 xlsx export 實作（Phase 6 反向參考）

**SheetJS / xlsx.js**（★ Style cascade 學習）：
- https://github.com/SheetJS/sheetjs
- `lib/xlml.js` — styles.xml 解析
- `lib/cfb.js` — OOXML 容器解析
- 不直接引用（授權考量），但設計可參考

**ExcelJS**（公式 shim 設計參考）：
- https://github.com/exceljs/exceljs
- `lib/utils/` — 公式 token 化、A1 ↔ R1C1 工具

**LibreOffice Calc OOXML import**（★ 最完整實作）：
- https://gerrit.libreoffice.org/c/core/
- `sc/source/filter/oox/stylesbuffer.cxx` — Style cascade 最完整
- `sc/source/filter/oox/formulaparser.cxx` — 公式 parser
- `sc/source/filter/oox/condformatbuffer.cxx` — CF 完整 rule types

**OnlyOffice cell engine**：
- https://github.com/ONLYOFFICE/sdkjs
- `cell/` — cell engine 架構參考

### 10.3 相關技術閱讀

- **Excel Number Format Codes**：Microsoft Docs `support.microsoft.com/.../number-format-codes`
- **OOXML Cell Reference Syntax**：MS-XLSX 規格
- **HarfBuzz 文件**：https://harfbuzz.github.io/（沿用 dobtor_doc_editor）
- **W3C CLReq — Chinese Layout Requirements**：https://www.w3.org/TR/clreq/（CJK 排版基礎）
- **Excel Functions and Formulas Bible**（書）— 公式 shim 行為對照

### 10.4 測試資源

- **xlsx 測試樣本**：
  - GitHub OOXML test fixtures
  - LibreOffice regression suite `sc/qa/unit/data/xlsx/`
  - SheetJS test files `test_files/`
  - ChienYi 實際業務 xlsx（最重要）
- **LibreOffice Calc 作為 reference renderer**：`libreoffice --headless --convert-to png:writer_png_Export`
- **pixelmatch**：https://github.com/mapbox/pixelmatch（同 dobtor_doc_editor）
- **python-calamine** 作為 cell value golden reader

---

## 11. 下一步建議

1. **第 1 週**：執行 Phase 0 模組骨架建立（附錄 A）
2. **第 2 週**：收集 30-50 份 ChienYi 實際 xlsx fixture、ADR-001 / ADR-002 完成
3. **第 3-4 週**：Phase 1.1-1.5 開始（Package、Workbook、SharedStrings、Styles）
4. **第 8 週**：**第一個里程碑 demo**——能把 ChienYi 估驗表 xlsx 解析成完整 Workbook AST，dump 到 JSON 檢視
5. **M5-M6**：**Phase 4.5 提前插入**，吸取 dobtor_doc_editor 孤立模組教訓，讓 user 早期可實際用

**心理建設**：這是一趟 12-18 個月的旅程，但因為 o-spreadsheet 作為起跳台（已有 70% Google Sheets 級功能），比 dobtor_doc_editor 從 canvas-editor 起跳輕鬆。每個 Phase 都有獨立產出與商業價值——即使中途停在 Phase 3，也已經擁有**市場上比 SheetJS 多一層 Odoo 整合的 xlsx 匯入方案**。

> Sprint 進度詳見 `docs/progress_snapshot.md`（Phase 0 第二週建立）。
> Sprint audit 索引見 `docs/INDEX.md`。

---

## 附錄 A：Phase 0 立即可做的任務清單

```
[ ] 模組骨架
    [ ] mkdir -p addons/dobtor_spreadsheet_editor/{models,controllers,wizards,views,security,data,docs,tests/fixtures,scripts,tools,static/src/core/ooxmlspreadsheet}
    [ ] 撰寫 __manifest__.py（depends: ['spreadsheet_oca']、version: 18.0.1.0.0）
    [ ] 撰寫 __init__.py + models/__init__.py（空）
    [ ] 確認 docker exec odoo18 odoo -d odoo18_dev -i dobtor_spreadsheet_editor --stop-after-init 可安裝

[ ] Build pipeline
    [ ] 複製 dobtor_doc_editor/package.json → 調整 name + description；npm install
    [ ] 複製 dobtor_doc_editor/tsconfig.json
    [ ] 複製 rollup.config.js → input 改 ooxmlspreadsheet/index.ts、output name 改 DobtorSpreadsheetEditor
    [ ] 複製 vitest.config.ts
    [ ] 建立 static/src/core/ooxmlspreadsheet/index.ts（空 export，確認 npm run build 通過）

[ ] Fixture 與 Golden
    [ ] 收集 ChienYi xlsx 第一批 10 份（從 tools/import_a/ + 實際估驗表）
    [ ] mkdir -p tests/fixtures/{01_simple_formula,02_merged_cells,03_number_format,04_conditional_format,05_multi_sheet,06_chart,07_pivot,08_chienyii_business}/golden
    [ ] 對 10 份 fixture 用 LibreOffice headless 產 PNG golden
    [ ] 對 10 份 fixture 用 python-calamine 讀 cell values 存 JSON golden
    [ ] 撰寫 scripts/generate_golden.sh 自動化

[ ] 文件與 ADR
    [ ] 建立 docs/INDEX.md（骨架）
    [ ] 建立 docs/progress_snapshot.md（骨架、含 vitest / VR / 覆蓋率欄位）
    [ ] 撰寫 docs/capability_audit.md（o-spreadsheet API 審計清單）
    [ ] 撰寫 docs/architecture_decision.md ADR-001（策略 (d) Hybrid 決定）
    [ ] 撰寫 docs/architecture_decision.md ADR-002（自寫 Parser 而非 SheetJS/ExcelJS）
    [ ] 撰寫 docs/scope_decision.md（dobtor docx / dobtor xlsx / QWeb PDF 三方分流）
    [ ] 複製 dobtor_doc_editor/CONTRIBUTING.md → 改名專案、保留 22 條紀律、新增 xlsx 候選 X1-X5

[ ] 環境驗證
    [ ] 確認 container 內 openpyxl 可用：docker exec odoo18 python3 -c "import openpyxl; print(openpyxl.__version__)"
    [ ] 確認 python-calamine 可用：docker exec odoo18 python3 -c "import python_calamine; print('ok')"
    [ ] 確認 libreoffice headless 可跑：libreoffice --headless --convert-to png test.xlsx
    [ ] 確認 fflate / fast-xml-parser npm install 可用

[ ] o-spreadsheet API 審計
    [ ] 讀 /usr/lib/python3/dist-packages/odoo/addons/spreadsheet/static/src/ 確認 addPlugin / addFunction 介面
    [ ] 列出 o-spreadsheet 18.0.48 內建函數清單（用 grep "register" 找）
    [ ] 列出 model commands API（setCellContent / updateCellFormat / addMerge / 等）
    [ ] 記錄到 docs/capability_audit.md
```

---

## 附錄 B：關鍵術語對照表

| OOXML SpreadsheetML | 含義 | o-spreadsheet 對應 |
|---|---|---|
| `xl/workbook.xml` | 主控文件，含 sheet 清單與 definedNames | 整個 `Model` |
| `<sheet name sheetId r:id state>` | Sheet 定義；r:id 指向 .rels；state = visible/hidden/veryHidden | `Model.sheets[i]` |
| `xl/worksheets/sheet1.xml` | 工作表本體 | `SheetData` |
| `<c r="A1" t="s" s="3"><v>5</v></c>` | cell A1、type=sharedString、style index 3、值=sharedStrings[5] | `{ value: "...", style: {...} }` |
| `<c r="B2" t="n"><v>100.5</v></c>` | cell B2、type=number、值 100.5 | `{ value: 100.5 }` |
| `<c r="C3"><f>SUM(A1:A10)</f><v>55</v></c>` | cell C3、公式（type 省略=number）、cached value 55 | `{ formula: "=SUM(A1:A10)" }` |
| `<f t="shared" si="0" ref="A1:A10">SUM(B1:B10)</f>` | shared formula：si=0 為 anchor，後續同 si 的 cell 套用相對偏移 | 展開為 per-cell formula |
| `<mergeCell ref="A1:C3"/>` | A1:C3 合併儲存格 | `addMerge` command |
| `xl/sharedStrings.xml` | 字串池 | 解析後 inline value |
| `<si><t>plain</t></si>` | 純文字 string item | string value |
| `<si><r><rPr>...</rPr><t>rich</t></r></si>` | rich text run | o-spreadsheet 多 segment cell |
| `xl/styles.xml` | 樣式定義（numFmts / fonts / fills / borders / cellXfs / cellStyleXfs / dxfs） | `Style` objects |
| `<cellXfs>` | Cell format index pool；每個 `<xf>` 組合各 ID | StyleResolver 解析起點 |
| `<xf numFmtId="164" fontId="2" fillId="3" borderId="1" xfId="0" applyNumberFormat="1">` | 一個 cell style，組合多個子 ID + apply 旗標 | 解析後 ResolvedStyle |
| `<cellStyleXfs>` | named style pool（如 "Normal"、"Heading 1"） | 樣式繼承來源 |
| `<dxfs>` | differential formats（CF 規則套用的部分樣式） | CF style |
| `<numFmt numFmtId="164" formatCode="#,##0.000"/>` | 自訂數字格式（id ≥ 164）；id < 164 為內建 | NumberFormatCompiler 輸入 |
| `<conditionalFormatting sqRef="A1:Z100">` | CF 應用範圍（空格分隔多範圍） | `updateConditionalFormat` |
| `<cfRule type="colorScale" priority="1">` | colorScale CF rule | ColorScaleThreshold |
| `<cfRule type="dataBar" priority="2">` | dataBar CF rule | DataBar |
| `<cfRule type="iconSet" priority="3">` | iconSet CF rule（3/4/5 圖示） | 降級 colorScale |
| `<dataValidation type="list" sqRef="A1:A10">` + `<formula1>"是,否,待定"</formula1>` | 下拉清單驗證 | data validation list |
| `<pivotCacheDefinition>` | Pivot 資料來源 cache（cacheFields + cacheRecords） | LocalDataPivot 擴展（Phase 5） |
| `<pivotTableDefinition>` | Pivot 配置（row/col/data fields） | Pivot model |
| `<definedName name="Price">Sheet1!$C$2</definedName>` | Named range | `setNamedRange` |
| `<sheetView><pane xSplit="1" ySplit="2" topLeftCell="B3" state="frozen"/>` | 凍結窗格（凍結 1 欄 + 2 列） | `freezeRows` / `freezeColumns` |
| `<col min="1" max="3" width="15" customWidth="1"/>` | A-C 欄寬 15（column-width units） | `setColumnSize` |
| EMU | English Metric Unit；1 pt = 12700 EMU、1 px ≈ 9525 EMU（96 dpi） | `utils/units.ts` |
| Column width unit | Excel 特殊單位：「最大數字字元寬度」≈ 7px @ Calibri 11pt | `utils/units.ts::colWidthToPx` |
| `r:id` / `rId1` | Relationship ID，連結 part 之間關係 | `RelationshipResolver` |
| `[Content_Types].xml` | 每個 part 的 MIME type 索引（root） | ContentTypes parser |
| `xl/charts/chart1.xml` | DrawingML chart（chartSpace） | ChartMapper |
| `xl/drawings/drawing1.xml` | Drawing layer（圖片、shape 錨點） | DrawingMapper |
| `<xdr:twoCellAnchor>` | 圖片 anchor（from cell + to cell） | image position |
| `<a:blip r:embed="rId1">` | 圖片 binary reference | ImageImporter |
| `xl/tables/table1.xml` | Excel Table 物件（structured reference 來源） | TableParser |
| `Table1[@column]` | Structured reference：當前列、指定欄 | FormulaCompiler 轉 A1 |
| `R1C1` notation | 相對/絕對行列；`R[+1]C[-1]` 為下一列前一欄 | FormulaCompiler 轉 A1 |
| Theme color `<color theme="0" tint="-0.5"/>` | 從 theme.xml clrScheme 取 dk1，套 tint 變暗 50% | ThemeResolver |

---

**Document End** — 版本 1.0 / 2026-06-07 / Sprint 0 起點

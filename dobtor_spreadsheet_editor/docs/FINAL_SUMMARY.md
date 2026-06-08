# dobtor_spreadsheet_editor — 最終總結（Sprint 0-44）

**日期**：2026-06-08
**分支**：`dobtor-spreadsheet-editor-phase1-2`（已 push 至 `chichi0718/chienyi-addons`）
**定位**：Odoo 18 模組，繼承 OCA `spreadsheet_oca` + o-spreadsheet 18.0.48，做 xlsx 高保真匯入 / 可編輯 / 匯出。

---

## 1. 健檢（收尾狀態）

| 項目 | 狀態 |
|---|---|
| TypeScript typecheck | 🟢 乾淨（無 any 洩漏） |
| Rollup build | 🟢 通過 |
| vitest | 🟢 **643 passed / 1 skipped**（VR baseline 手動） |
| Playwright E2E | 🟢 **16 個情境全綠**（每個都有截圖視覺實證） |
| cell value 提取率 vs calamine golden | 🟢 **99.998%**（702909/702925） |
| 規劃書任務打勾 | **131 項**（健檢起點 85 → +46） |
| 旗艦檔 capstone（契約詳細表 16 sheet/6.5 萬公式） | 🟢 預覽 1.3s、可編輯開啟 20.8s、無錯誤 |

---

## 2. 已完成功能（皆有真實 ChienYi 資料驗證）

### Parser（Phase 1，~90%）
- §1.1 PackageReader（OPC/zip/rels 相對路徑解析，resolvedTarget）
- §1.2 units（EMU/pt/px/欄寬）
- §1.3 WorkbookParser、§1.4 SharedStringsParser（rich text + _xHHHH_ + **numeric entity &#NNNN; 解碼**）
- §1.5 StylesParser（numFmts/fonts/fills/borders/cellXfs/cellStyleXfs/dxfs）
- §1.6 WorksheetParser（cell/公式/合併/freeze/cols/列高/**dataValidations**/CF）
- §1.7 CFParser（cellIs/expression/colorScale/dataBar/iconSet/containsText/dup/top10）
- §1.8 **DataValidationParser**、§1.9 ThemeParser、§1.10 defined names（部分）、§1.11 **Tables**

### 樣式與渲染（Phase 2，~68%）
- §2.1 StyleResolver（xf cascade + applyX）、§2.2 ThemeResolver（theme 0/1 互換 + HSL tint + indexed）
- §2.3 number format 渲染（千分位/%/貨幣/會計負數/字面）+ **日期格式碼/民國年渲染（預覽+編輯一致，114年12月10日）**
- §2.4 ConcreteStyle → o-spreadsheet Style interop

### 公式（Phase 3，~58%）
- §3.1 gap analysis、§3.2 A1 passthrough + **shared formula 展開（契約表 6.5 萬公式即時運算）**
- §3.3 白名單 ~93 函數 + **CHOOSE / MROUND / REPT / SIGN functionRegistry shim**
- §3.5 **錯誤值保真**（type=e → 保留 #N/A/#REF! 原貌）

### CF / DV（Phase 4，~75%）
- §4.1 **CF 五型編譯全完成**：cellIs / containsText / colorScale / dataBar / iconSet（皆截圖實證）
- §4.2 **DV 編譯**：list→isValueInList、range→isValueInRange、whole→isBetween

### Chart / Table（Phase 5，~20%）
- §5.2 ChartParser + ChartMapper（bar/line/pie/scatter、series/cat/val/title → o-spreadsheet figure）
- §5.3 DrawingParser（anchor + chart rId）

### Export（Phase 6，~78%）
- §6.2 TS xlsx_writer：值/公式/樣式（font/fill/border/numFmt）/欄寬/列高/合併
  + **CF/dxfs 回寫** + **DV 回寫** + **chart/drawing/media 直通**
- §6.3 round-trip：openpyxl + LibreOffice 三方驗證

### Phase 4.5 產品化 + Phase 8 ChienYi 整合（~60% / ~30%）
- Odoo client action（匯入預覽 iframe + 「在 o-spreadsheet 開啟」可編輯）
- bridge `dobtor_spreadsheet_editor_chienyi`：估驗計價「匯入估驗試算表」+「**從工項產生試算表**」
  （即時公式/千分位/表頭填色/凍結）+ 回掛估驗（payment_estimate_id + smart button）

### 雙向 round-trip 完成的特性
xlsx ↔ 可編輯 o-spreadsheet：值 / 公式 / 樣式 / 合併 / 邊框 / 欄寬列高 / **CF / DV / chart / 圖片**。

---

## 3. 已知限制 / 刻意未做（附理由）

| 項目 | 理由 |
|---|---|
| **autoFilter** → o-spreadsheet filter | 需以 table 承載 → 會對管制表 11 處範圍強加帶狀樣式，**視覺回歸風險** |
| **R1C1 / array formula / hyperlinks** | ChienYi 檔幾乎無（0-2 個）→ 純合成、無真實價值 |
| **Pivot（§5.1）** | o-spreadsheet pivot 綁 Odoo model、與 Excel local-data pivot 不相容 → 需重大改 o-spreadsheet |
| **效能（Phase 7）** | Web Worker / 虛擬卷動 / IndexedDB cache → 重大基礎建設，未驗證有迫切需求 |
| **CF duplicateValues / expression 編譯** | o-spreadsheet 無直接對應規則（解析保留、匯出 round-trip，但不在編輯端顯示） |
| **chart 編輯後回寫** | 目前直通原始 chart parts；o-spreadsheet 改資料範圍不反映回匯出 |
| **gradient fill / tableStyles 細節** | 罕見，未解析 |
| 巢狀深層開啟 transient | 已用 clearBreadcrumbs 解（S24） |

---

## 4. 後續 Roadmap（若再啟動）

**短期（小、有界）**
- ~~MROUND/REPT/SIGN shim~~ ✅ S42、~~日期/民國年渲染~~ ✅ S43
- 時間 token（hh/mm/ss）、會計負數 [Red] 顏色（§2.3 剩餘）
- autoFilter → o-spreadsheet filter（需先確認不破壞視覺）

**中期**
- chart 編輯回寫 xlsx（ChartAst → chartN.xml）
- R1C1 → A1 轉換（若遇 R1C1 模式檔）
- 大檔效能（已建基準 S44：可編輯開啟 20.8s）：lazy sheet / 快速模式（只展開可視 sheet shared formula）

**長期**
- Pivot（需擴 o-spreadsheet LocalDataPivot 或降級靜態快照）
- Phase 7 完整效能基礎建設

---

## 5. 模組結構

```
addons/
├── dobtor_spreadsheet_editor/              # 通用 xlsx 高保真引擎（業務無關）
│   ├── static/src/core/ooxmlspreadsheet/   # parser/compiler/writer（~30 檔）
│   ├── static/src/components/xlsx_import/  # OWL client action
│   ├── static/src/spreadsheet_functions/   # CHOOSE/MROUND/REPT/SIGN shim
│   ├── tests/{unit,integration}/           # 629 vitest
│   └── docs/                               # sprint0-41 audit + INDEX + 本檔
└── dobtor_spreadsheet_editor_chienyi/      # ChienYi bridge（估驗計價整合）
tests/playwright/tests/                     # 16 個 admin E2E（在 odoo18-docker repo）
```

**驗證方法論**：每 sprint 三層 SOP — L1 vitest（含真實 fixture corpus）→ L2 Playwright E2E + openpyxl/LibreOffice 三方 → L3 tsc/build/docker 升級。CF/chart/table/colorScale/dataBar/iconSet 每型都有 o-spreadsheet 截圖視覺實證。

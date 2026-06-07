# Architecture Decision Records (ADR)

本檔記錄 dobtor_spreadsheet_editor 的關鍵架構決策。每筆 ADR 含：背景、決策、理由、後果、替代方案。

格式參考 dobtor_doc_editor `docs/architecture_decision.md`。

---

## ADR-001：採 Hybrid 策略（不 fork、不 replace o-spreadsheet）

**日期**：2026-06-07
**狀態**：Accepted
**決策者**：規劃書作者 + user 確認

### 背景

新模組 dobtor_spreadsheet_editor 要對標 Google Sheets / Excel 級 xlsx 高保真匯入。起點是 OCA `spreadsheet_oca` 18.0.1.3.0，後者繼承 Odoo CE 原生 `spreadsheet` 模組（含 Odoo 維護的 `@odoo/o-spreadsheet` v18.0.48 JS bundle，2.8 MB）。

o-spreadsheet 已具備約 70% Google Sheets 級功能（formula engine、pivot、chart、CF、multi-sheet）。但 xlsx 匯入完全未實作（OCA wizard 只解 ZIP 存 raw XML、不解析）。

我們有三條策略路線可選：

| 策略 | 描述 | 風險 |
|---|---|---|
| (a) 擴充 o-spreadsheet（plugin 層） | 在公開 API 上加 xlsx parser + 注入 commands | API 限制 |
| (b) Fork o-spreadsheet | 直接改 fork 內部程式碼 | upstream sync 成本每年 1-2 人月 |
| (c) Replace o-spreadsheet | 整個換掉、自寫渲染引擎 | 失去 Odoo-bound 整合（ODOO.LIST/PIVOT/FILTER） |
| **(d) Hybrid**（推薦） | 走 (a)、為 Odoo-bound 與 xlsx 兩路徑分離設計 | 限制可規避；無需 fork |

### 決策

**採策略 (d) Hybrid**：
- 保留 o-spreadsheet 作為渲染引擎
- 不 fork、不 replace
- 在 plugin 層加 xlsx I/O parser（OOXML SpreadsheetML → o-spreadsheet model commands）
- Odoo-bound 功能（pivot/list/filter/native chart）走原生 OCA + Odoo 路徑
- xlsx-import / xlsx-export 走我們的新路徑

### 理由

Sprint 0 API 審計（見 `capability_audit.md`）證實：

- `addFunction` 直接可用（補 Excel 缺失公式的核心 API）
- `CorePlugin` / `UIPlugin` 為公開基類（可繼承擴展）
- `Registry` 公開（可建自訂註冊表）
- Commands 完整：`ADD_MERGE` / `ADD_CONDITIONAL_FORMAT` / `ADD_DATA_VALIDATION_RULE` / `CREATE_CHART` / `CREATE_IMAGE` / `ADD_PIVOT` 等全部存在
- Chart types 已支援 9 種（area/bar/combo/doughnut/gauge/line/pie/scatter/waterfall）—— 比預期樂觀

→ 所有需要的擴展點都是 public API，**fork 沒有必要**。

Fork 成本：每次 Odoo quarterly release（18.0.49、18.0.50 ...）都要 merge upstream，估每年 1-2 人月。

策略 (d) Hybrid 比 (a) 純擴充多了「Odoo-bound 路徑分離」設計，預留了 Excel 風格的 local-data pivot（與 Odoo-model pivot 並存）擴展空間。

### 後果

**正面**：
- OCA `spreadsheet_oca` upstream 升級不會破壞我們（manifest 只鎖 depends 不鎖版本）
- 與 Odoo Enterprise `spreadsheet_edition` 路徑不衝突（不依賴付費版功能）
- xlsx 路徑單獨可測試、可降級、可關閉

**負面**：
- 若 o-spreadsheet 某些功能（如 Excel-style pivot）需要 internal API 才能做到，可能需 Plan B fork
- Excel-only 風格（如 dynamic array `#` operator）若 o-spreadsheet 不支援，只能降級為靜態值

### 替代方案的理由

- **(b) Fork**：被否決——年成本 1-2 人月 vs 預期收益不成比例
- **(c) Replace**：被否決——失去 Odoo-bound 整合（ODOO.LIST / ODOO.PIVOT / global filters），是 ChienYi 後續整合的核心
- **(a) 純擴充**：策略 (d) 是 (a) 的 superset，更具彈性

### 退場條件

若 18 個月內因 plugin API 限制無法達到 A- 級，啟動 Plan B：分階段 fork（先 partial fork 受限功能、最後完整 fork）。詳見規劃書 §8.2。

---

## ADR-002：xlsx Parser 自寫 TypeScript 而非用 SheetJS / ExcelJS

**日期**：2026-06-07
**狀態**：Accepted
**決策者**：規劃書作者

### 背景

xlsx Parser 是 Phase 1 主交付。市場上有兩個成熟方案：

| 函式庫 | 授權 | 完整度 | 缺點 |
|---|---|---|---|
| SheetJS (xlsx.js) | Apache-2.0 (CE) | 高 | Pro 版才含 Excel formula 完整解析、CE 版受限 |
| ExcelJS | MIT | 中-高 | Pivot / 進階 CF 不完整、純 JS 速度普通 |
| **自寫 TS** | — | 高（但要做） | 開發成本 2-3 個月（Phase 1） |

### 決策

**Phase 1 自寫 TypeScript Parser**，不引用 SheetJS / ExcelJS。

但 **`formulajs` 可按需 tree-shake 引用作為 Phase 3 missing function shim** —— 因為它是純 function library，不影響 Parser 架構。

### 理由

1. **授權與 IP 自主**：SheetJS CE 版功能受限；Pro 版商業授權。自寫 100% LGPL-3，與模組授權一致
2. **ChienYi 特化**：台灣 number format（民國紀年、會計格式）、CJK 欄寬精確估算，無第三方支援
3. **與 dobtor_doc_editor font infrastructure 整合**：HarfBuzz WASM、CJK fallback chain 已在 dobtor_doc_editor 驗證、可直接複用
4. **OOXML §18 規格規模可控**：1500 頁、3 個月 Phase 1 可完成
5. **避免抽象層膨脹**：第三方庫 → 自寫 wrapper → o-spreadsheet 三層 indirection，debug 困難
6. **不依賴外部維護節奏**：ExcelJS 主作者離職、SheetJS 商業化爭議大

### 後果

**正面**：
- 完全控制 parser 行為、可針對 ChienYi fixture 調優
- TypeScript 嚴格型別、易維護
- 與 dobtor_doc_editor 共用基礎建設

**負面**：
- Phase 1 不能用「現成」省工
- 邊界 case（如損壞 xlsx、版本相容）需要時間累積
- Round-trip 對稱性需 Phase 6 才驗證（不像引用 SheetJS 立即可 round-trip）

### 替代方案的退場條件

若 Phase 1 第二月時 parser 進度落後 30% 以上、且時程壓力高，可考慮：
- **fallback A**：引 ExcelJS 做底層 ZIP/XML 解析、自寫 style/formula compiler 包在上層
- **fallback B**：引 SheetJS CE 做 basic cell 讀取、自寫 style/formula/CF 補強

但 Phase 1 必須先嘗試完全自寫至少 4 週、確認真的卡死才啟動 fallback。

---

## ADR-003：（保留）xlsx Export 採 Python openpyxl 而非前端 TypeScript

**日期**：2026-06-07
**狀態**：Pending（Phase 6 開工前確認）

### 背景

Phase 6 Export 對稱性需要把 o-spreadsheet model JSON 寫回 xlsx。可選：

- **Python openpyxl**（後端）：成熟、container 已裝、寫入時 Server 算力可用
- **TypeScript 自寫**（前端）：純前端、離線可用、無 server round-trip

### 決策（暫定）

**Phase 6 主路徑採 Python openpyxl**。前端 TS 路徑留 Phase 7+ 視需求。

### 理由

- openpyxl 已 production-ready、生態成熟
- ChienYi 主要場景為「Portal 上編輯 → 下載 xlsx」，server round-trip 可接受
- 前端 TS Export 開發成本高、收益僅在離線場景
- 若需離線編輯，可選 Phase 7 補做

### 待 Phase 6 開工前重新確認

- openpyxl 對 Conditional Formatting / chart 寫入完整度
- 若 openpyxl 不支援某些 Phase 4-5 已 import 的 feature，需評估前端補強或降級

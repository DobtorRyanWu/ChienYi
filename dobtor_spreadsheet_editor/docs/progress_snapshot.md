# 進度快照（Progress Snapshot）

**最後更新**：2026-06-07（Sprint 16）

## 當前指標一覽

| 指標 | 值 | 目標 | 狀態 |
|---|---|---|---|
| 當前 Phase | 1+2 + VR + Phase 4.5（預覽 + o-spreadsheet 對接） | — | in_progress |
| Sprint 編號 | 16 | — | — |
| vitest unit tests | 200 / 200 passed | > 500（Phase 1+ 後） | 🟢 |
| vitest integration | 334 / 334 passed（+ VR baseline skipIf 手動） | > 200 | 🟢 **達標** |
| vitest 總計 | 534 / 534 passed（+1 VR skipped） | — | 🟢 |
| **Odoo 整合** | 選單掛 OCA Spreadsheets 底下；HTML 預覽 + 「在 o-spreadsheet 開啟（可編輯）」 | — | 🟢 預覽已驗；可編輯待瀏覽器確認 |
| number format 渲染 | 千分位/貨幣/百分比/會計負數/字面，13 測試 | — | 🟢 |
| **VR content diff**（純內容） | **11.4% / 12.4% / 19.3%**（字型保真後） | <5%（終極） | 🟡 收斂中（餘為佈局 metrics） |
| **cell value 提取率（vs calamine golden）** | **99.998%（702909/702925）** | > 95% | 🟢 **超標** |
| 殘餘未命中 | 16（皆 calamine 未解 _x000D_ 的 golden 缺陷、本 parser 值正確） | — | 🟢 |
| Visual regression mean | content diff 11.4-19.3%（字型保真後；餘為佈局 metrics） | < 5% diff | 🟡 收斂中 |
| Round-trip cell value pass rate | — | > 90% | ⚪ Phase 6+ 才有 |
| Fixture 收集 | 48 / 50 | 50 | 🟡 缺 04 CF×1 + 07 pivot×3（營造文件本質稀少，待通用 OOXML 補） |
| Golden artifacts | 48 / 48（96 檔：PNG + JSON）| 48 | 🟢 全數產出、0 calamine 失敗 |
| TypeScript typecheck | pass | pass | 🟢 |
| Rollup build | pass | pass | 🟢 |

## Phase 完成度

| Phase | 任務數 | 完成 | 進度 |
|---|---|---|---|
| Phase 0（基建） | 10 | 8 | 80% |
| Phase 1（Parser） | 80+ | 8 | 10%（§1.1-1.7 + §1.9）；§1.8/1.10/1.11 待做 |
| Phase 2（Style） | 30+ | 3 | 10%（§2.1 StyleResolver + §2.2 ThemeResolver + §2.3 日期最小版） |
| Phase 3（Formula）★ | 60+ | 0 | 0% |
| Phase 4（CF/Validation） | 30+ | 0 | 0% |
| Phase 4.5（產品化） | 25+ | 5 | 20%（ConcreteStyle + HTML 預覽入口 + Odoo UI + to_ospreadsheet 轉換器 + OCA 記錄對接） |
| Phase 5（Pivot/Chart） | 40+ | 0 | 0% |
| Phase 6（Export） | 15+ | 0 | 0% |
| Phase 7（效能） | 10+ | 0 | 0% |
| Phase 8（ChienYi 整合） | (待認可) | — | — |

## Phase 0 Sprint 0 完成項

- [x] 模組骨架建立（manifest、__init__、目錄樹）
- [x] Build pipeline 就緒（package.json、tsconfig、rollup、vitest）
- [x] npm install 完成（193 packages）
- [x] Smoke test 通過（2/2 vitest pass、rollup build pass）
- [x] o-spreadsheet API 審計（addFunction / CorePlugin / 30+ commands / 9 chart types 確認）
- [x] capability_audit.md 撰寫
- [x] Fixture 目錄結構 + generate_golden.sh script
- [x] docs/ 骨架（INDEX、progress_snapshot、glossary）

## Phase 1 Sprint 1 完成項（2026-06-07）

- [x] 收集 ChienYi 實檔 fixture 48 份（A標+B標，從工程資料 776 xlsx 去重 507 → openpyxl 特徵掃描 409 → 8 類分流）
  - 08_chienyii_business 10 / 02_merged_cells 8 / 01_simple_formula 8 / 03_number_format 6 / 05_multi_sheet 5 / 06_chart 5 / 04_conditional_format 5 / 07_pivot 1
- [x] 跑 generate_golden.sh 產 48×(PNG+JSON) golden、0 calamine 失敗
- [x] 旗艦檔（契約詳細表 16 sheet / 65k 公式）cell value golden 完整 16 sheet

## Phase 0 殘餘待辦（Sprint 2-3）

- [ ] 04_conditional_format 補 1 份 + 07_pivot 補 3 份（ChienYi 實檔稀少 → 用通用 OOXML 測試檔或合成 fixture）
- [ ] 撰寫 ADR-001 / ADR-002（scope_decision.md / architecture_decision.md 已存在、需補 ADR 編號）
- [ ] docker exec 安裝模組驗證
- [ ] Phase 0 Exit review → 進入 Phase 1 Parser

## 環境驗證結果（Sprint 0）

| 工具 | 版本 | 用途 |
|---|---|---|
| openpyxl | 3.1.2 | Phase 6 xlsx 寫入 |
| python-calamine | (匯入 ok) | Cell value golden reader / 損壞 xlsx fallback |
| libreoffice（WSL host） | 24.2.7.2 | Golden PNG 產生 |
| @odoo/o-spreadsheet | 18.0.48（2025-11-12 build d1efb0b98）| 渲染引擎 |
| OCA spreadsheet_oca | 18.0.1.3.0 | 多人協作 + xlsx upload wizard |
| TypeScript | 5.x | Parser 開發 |
| Rollup | 4.x | bundle 打包 |
| Vitest | 2.1.9 | 測試 |

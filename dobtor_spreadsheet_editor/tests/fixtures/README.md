# Test Fixtures

50 份真實台灣商業 xlsx 樣本（Sprint 0 收集中）。

## 分類目錄

| 目錄 | 類別 | 目標份數 | 來源 |
|---|---|---|---|
| `01_simple_formula/` | SUM / AVERAGE / IF 基本公式 | 8 | 通用模板 + GitHub OOXML test files |
| `02_merged_cells/` | 跨欄/跨列合併 | 8 | 估驗表類 |
| `03_number_format/` | 自訂數字 / 日期 / 貨幣（台灣會計格式） | 6 | 月報類 |
| `04_conditional_format/` | colorScale / dataBar / iconSet / cellIs | 6 | 損益試算類 |
| `05_multi_sheet/` | 跨 sheet 公式 / VLOOKUP / INDIRECT | 5 | 月報類 |
| `06_chart/` | bar / line / pie / S 曲線 | 5 | 進度報告類 |
| `07_pivot/` | 樞紐分析表 | 4 | 統計類 |
| `08_chienyii_business/` | 估驗表 / 工項 / 月報 / 政府採購標單 | 10 | ChienYi 實檔（最重要） |

## Golden artifacts

每份 `.xlsx` 對應產出兩種 golden 放在 `<category>/golden/`：

- `<name>.png` — LibreOffice Calc headless 渲染（pixelmatch VR 基準）
- `<name>.cells.json` — python-calamine 讀 cell values（cell value diff 基準）

## 產生 golden

```bash
bash scripts/generate_golden.sh                 # 全部分類
bash scripts/generate_golden.sh 08_chienyii_business  # 單一分類
```

依賴：
- WSL host：LibreOffice 24+（已驗證 24.2.7.2）
- Docker container `odoo18`：python-calamine（已驗證）

## 進度（Sprint 1，2026-06-07）

實際收集 **48 / 50**（全數 ChienYi A標+B標實檔，來源 `工程資料/`）：

| 目錄 | 目標 | 實收 | 備註 |
|---|---|---|---|
| 01_simple_formula | 8 | 8 | 單價分析、議價調整、總表 |
| 02_merged_cells | 8 | 8 | 管制表、督導表、動員統計、送審管制、監工日報 |
| 03_number_format | 6 | 6 | 變更明細（27 種自訂格式） |
| 04_conditional_format | 6 | **5** | ⚠️ 缺 1：營造文件 CF 稀少 |
| 05_multi_sheet | 5 | 5 | 管制表(43 sheet)、5變數量計算(38 sheet) |
| 06_chart | 5 | 5 | 進度 S 曲線、自主檢查統計 |
| 07_pivot | 4 | **1** | ⚠️ 缺 3：ChienYi 僅土方統計 1 份含 pivotCache |
| 08_chienyii_business | 10 | 10 | 契約詳細表(16 sheet/65k 公式)、估驗差異表、變更金額分析 |

- [x] 收集 48 份實檔（檔名已清理：去空格/括號）
- [x] 跑 generate_golden.sh 產 48×(PNG + JSON)、0 calamine 失敗
- [ ] 04 補 1 + 07 補 3（通用 OOXML 測試檔或合成 fixture）
- [ ] commit fixtures 與 golden 至 git

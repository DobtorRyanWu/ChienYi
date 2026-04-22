# 模組整合清理指南
# ====================
# 創建日期: 2024-12
# 版本: 1.0

## 📋 整合摘要

本次整合將以下模組的功能合併到核心模組中：

| 被整合模組 | 整合到 | 說明 |
|------------|--------|------|
| contract_changed | contract_pay_item | 契約變更審批流程 |
| project_pay_item | contract_pay_item | BOQ 工項管理（功能完全重複） |
| sheet_pay_item | (刪除) | 依賴不存在的模型 |
| dailyrecord | DAILY | 人機項目管理（已被取代） |
| daily_record | DAILY | 施工日誌舊版本（已被取代） |
| PayItem | contract_pay_item | 舊版工項管理（已被取代） |
| sheetPayItem | contract_pay_item | 舊版設計變更工項（已被取代） |

## ✅ 新增功能

`contract_pay_item` 模組新增：
- `contract.change.record` 模型 - 契約變更記錄管理
- `contract.change.reject.wizard` - 拒絕原因輸入視窗
- 完整的審批流程（草稿 → 已提交 → 審核中 → 已批准/已拒絕）
- 變更編號自動生成（格式：{專案ID}-CHG-{序號}）

## 🗑️ 需要刪除的項目

### 資料夾（7個）
1. `project_pay_item/` - 功能已在 contract_pay_item 中
2. `sheet_pay_item/` - 依賴不存在的模型
3. `contract_changed/` - 已整合到 contract_pay_item
4. `dailyrecord/` - 已被 DAILY 取代
5. `daily_record/` - 已被 DAILY 取代
6. `PayItem/` - 已被 contract_pay_item 取代
7. `sheetPayItem/` - 已被 contract_pay_item 取代

### 孤立檔案（2個）
1. `project_project_extend.py` - 重複（已在 test_standard/models/ 中）
2. `test_standard_key.py` - 重複（已在 test_standard/models/ 中）

## ⚠️ 重要提醒

1. **備份優先**：執行刪除前請先備份整個 addons 目錄
2. **資料庫**：如果已安裝過被刪除的模組，需要先從 Odoo 中卸載
3. **依賴檢查**：確保沒有其他自定義模組依賴這些被刪除的模組

## 📝 手動清理步驟

如果不使用批次腳本，請依序執行以下操作：

```powershell
# 1. 進入 addons 目錄
cd D:\work\odoo18-docker\addons

# 2. 刪除重複模組資料夾
Remove-Item -Recurse -Force project_pay_item
Remove-Item -Recurse -Force sheet_pay_item
Remove-Item -Recurse -Force contract_changed
Remove-Item -Recurse -Force dailyrecord
Remove-Item -Recurse -Force daily_record
Remove-Item -Recurse -Force PayItem
Remove-Item -Recurse -Force sheetPayItem

# 3. 刪除孤立檔案
Remove-Item -Force project_project_extend.py
Remove-Item -Force test_standard_key.py
```

## 🔄 更新後的模組結構

```
addons/
├── base_geoengine/          # OCA - 地理引擎
├── base_system/             # 系統安裝套件
├── contract_pay_item/       # ★ 已整合 (v2.0.0)
│   ├── models/
│   │   ├── contract_pay_item_key.py
│   │   ├── contract_pay_item.py
│   │   ├── contract_pay_item_history.py
│   │   └── contract_change_record.py  ← 新增
│   ├── views/
│   │   ├── contract_pay_item_xml_import_views.xml
│   │   └── contract_change_record_views.xml  ← 新增
│   └── security/
│       └── ir.model.access.csv  ← 新增
├── DAILY/                   # 施工日誌（主要模組）
├── dms/                     # OCA - 文件管理
├── dms_field/               # OCA - DMS 欄位
├── ErrorRecord/             # 缺失改善
├── file/                    # 檔案管理
├── image/                   # 圖片管理
├── inspection/              # 自主檢查記錄
├── inspection_type/         # 自主檢查類型
├── project_construction/    # 營建專案管理
├── project_id/              # 專案識別碼
├── project_key/             # OCA - 專案識別碼基礎
├── project_main/            # 專案管理擴展（建議與 project_construction 合併）
├── project_report/          # 通報單
├── project_workspace/       # 專案工作區
├── ReviewApplication/       # 送審管制
├── template_setting/        # 樣板設定
├── test_record/             # 檢試驗記錄
├── test_standard/           # 檢試驗項目
└── web_leaflet_lib/         # 地圖函式庫
```

## 🚀 更新後操作

1. 重啟 Odoo 容器
2. 更新模組：`contract_pay_item`
3. 檢查功能是否正常

---
文件結束

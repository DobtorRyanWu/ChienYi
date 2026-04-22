# 工程監造與施工協作管理系統

> Odoo 18 Construction Supervision & Collaboration Management System

[![Odoo Version](https://img.shields.io/badge/Odoo-18.0-blue.svg)](https://www.odoo.com)
[![License](https://img.shields.io/badge/License-LGPL--3-green.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Modules](https://img.shields.io/badge/Modules-22-orange.svg)](#模組清單)

---

## 系統簡介

本系統是基於 **Odoo 18** 開發的工程監造與施工協作管理平台，專為設計監造單位與施工廠商之間的協作而設計。支援**一般式**與**預約式**兩種工程類型，涵蓋從工程規劃、施工管理、品質控制到驗收結案的完整生命週期。

### 核心特色

- **多公司架構**：設計監造單位與施工廠商完全隔離
- **雙模式支援**：一般式工程與預約式工程
- **完整工作流程**：計畫 → 施工 → 驗收 → 結案
- **品質追蹤**：NCR、自主檢查、缺失改善、檢試驗
- **財務管理**：估驗計價、請款、成本分析
- **稽核合規**：操作軌跡記錄、審核流程

---

## 系統架構

```
                           ┌─────────────────────────────────────┐
                           │   construction_supervision_base     │
                           │         (核心基礎模組)               │
                           └─────────────────┬───────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              │                              │                              │
    ┌─────────▼─────────┐         ┌──────────▼──────────┐        ┌─────────▼─────────┐
    │   一般式工程模組    │         │     通用功能模組     │        │   預約式工程模組    │
    └─────────┬─────────┘         └──────────┬──────────┘        └─────────┬─────────┘
              │                              │                              │
    • construction_general         • construction_daily_log      • construction_reservation
    • construction_quality         • construction_payment        • construction_notification_slip
      (general.self.inspection)    • construction_progress       • construction_quality
                                   • construction_partner          (reservation.self.inspection)
                                   • construction_equipment
                                   • construction_contract_change
                                   • construction_test
                                   • construction_review
                                   • construction_photo
                                   • construction_portal
                                   • construction_template
                                   • construction_cost_analysis
                                   • construction_price_library
                                   • construction_batch
                                   • construction_timeline
                                   • construction_acceptance
                                   • construction_audit
```

---

## 模組清單

### 核心模組

| 模組 | 名稱 | 說明 |
|------|------|------|
| `construction_supervision_base` | 核心基礎模組 | 工程案件主檔、契約工項、文件管理、多公司架構 |

### 功能模組

| 模組 | 名稱 | 說明 | 依賴 |
|------|------|------|------|
| `construction_daily_log` | 施工日誌 | 日誌表單、天氣記錄、四態工作流程 | base |
| `construction_payment` | 計價與請款 | 估驗計價、工項驗收、請款管理 | base |
| `construction_quality` | 品質管理 | NCR缺失、自主檢查、缺失改善 | base |
| `construction_notification_slip` | 通報單管理 | 預約式工程通報單與驗收 | base |
| `construction_contract_change` | 契約變更 | 變更單、金額/數量/工期追蹤 | base |
| `construction_partner` | 工程單位管理 | 單位分類、證照、技術聯絡人 | base, contacts |
| `construction_equipment` | 人機管理 | 機具設備、維護請求、MTBF/MTTR | base, daily_log, maintenance |
| `construction_test` | 檢試驗管理 | 檢試驗項目、管制記錄 | base |
| `construction_review` | 送審管制 | 材料送審、審查結果、廠驗 | base |
| `construction_photo` | 照片管理 | 工程照片、GPS追蹤、標籤分類 | base |
| `construction_portal` | Portal 入口 | 承包廠商前台、自主檢查、缺失改善 | portal, base, quality, photo |
| `construction_progress` | 進度表管理 | 進度規劃、差異分析 | base, daily_log |
| `construction_template` | 樣板設定 | 文件樣板管理 | base |
| `construction_cost_analysis` | 成本分析 | 成本報表、損益追蹤 (DB View) | base, payment |
| `construction_price_library` | 價格庫管理 | 標準單價、匯入精靈 | base |
| `construction_batch` | 批次操作 | 批次下載精靈 | base, daily_log, payment |
| `construction_timeline` | 時程控制 | Timeline視圖、計時器、差異分析 | base, hr_timesheet |
| `construction_acceptance` | 驗收與結案 | 初驗、正驗、缺失追蹤、結案 | base, payment |
| `construction_audit` | 稽核模組 | 操作軌跡記錄 | base |
| `construction_general` | 一般式工程 | 一般式專用功能 | base, quality |
| `construction_reservation` | 預約式工程 | 預約式專用功能 | notification_slip, quality |

---

## 模組詳細資訊

### 1. construction_supervision_base

> 核心基礎模組 - 必須最先安裝

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | base, project, hr_timesheet, contacts, mail |

**模型清單**：
- `supervision.project` - 工程案件主檔
- `supervision.document` - 工程文件
- `supervision.review.comment` - 審查意見
- `project.task` (擴展) - 契約工項
- `res.company` (擴展) - 公司類型

**主要功能**：
- 工程案件主檔管理（繼承 project.project）
- 契約工項管理（繼承 project.task）
- 工程文件管理與審核流程
- 多公司架構支援（設計監造/施工廠商）
- 資料隔離與權限控制

---

### 2. construction_daily_log

> 施工日誌管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, hr_timesheet |

**模型清單**：
- `daily.log.sheet` - 施工日誌表單
- `daily.log.line` - 施工日誌明細
- `daily.log.weather` - 每日天氣紀錄

**主要功能**：
- 參考 hr_timesheet_sheet 的 Sheet 聚合模式
- 四態工作流程：新建 → 草稿 → 待審核 → 已核准
- 每日天氣紀錄（上午/下午）
- 多公司資料隔離
- 與 hr_timesheet 整合

---

### 3. construction_payment

> 計價與請款管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `payment.estimate` - 估驗計價
- `payment.estimate.line` - 估驗計價明細
- `work.acceptance` - 工項驗收單
- `work.acceptance.line` - 工項驗收明細
- `payment.claim` - 請款單

**主要功能**：
- 分期估驗計畫與累計追蹤
- 工項驗收流程
- 請款單管理
- 預算 vs 實際對比分析
- 獨立設計（不依賴 purchase 模組）

---

### 4. construction_quality

> 品質管理模組

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Quality |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `supervision.defect` - NCR 缺失管理
- `self.inspection.type` - 自主檢查類型
- `general.self.inspection` - 一般式自主檢查
- `reservation.self.inspection` - 預約式自主檢查
- `reservation.defect.improvement` - 預約式缺失改善

**主要功能**：
- NCR 狀態流程：open → investigating → action_taken → verified → closed
- 自主檢查類型管理
- 照片附件上傳
- 逾期追蹤與警示

---

### 5. construction_notification_slip

> 通報單管理（預約式工程）

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `reservation.notification.slip` - 通報單
- `reservation.notification.slip.line` - 通報單明細
- `notification.acceptance` - 通報單驗收
- `notification.acceptance.line` - 通報單驗收明細

**主要功能**：
- 預約式工程通報單管理
- 預算追蹤（planned vs actual）
- 完整狀態機與驗收流程
- 數量驗證與約束

---

### 6. construction_contract_change

> 契約變更管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base |

**模型清單**：
- `contract.change.order` - 契約變更單
- `contract.change.order.line` - 契約變更明細

**主要功能**：
- 參考 OCA project_version 設計
- 金額/數量/工期變更追蹤
- 工項新增、修改、刪除變更類型
- 自動套用變更至工項與專案
- 累計變更追蹤

---

### 7. construction_partner

> 工程相關單位管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | contacts, construction_supervision_base |

**模型清單**：
- `supervision.partner.category` - 工程單位分類標籤
- `partner.license` - 廠商證照資料
- `partner.technical.contact` - 技術聯絡人
- `res.partner` (擴展)

**主要功能**：
- 工程單位分類標籤（樹狀結構）
- 廠商證照資料管理與過期提醒
- 技術聯絡人管理
- 支援業主、施工廠商、監造單位、設計單位、政府部門等

---

### 8. construction_equipment

> 人機管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Equipment |
| **依賴** | maintenance, construction_supervision_base, construction_daily_log |

**模型清單**：
- `supervision.equipment.category` - 機具設備分類
- `supervision.equipment` - 機具設備
- `supervision.equipment.request` - 設備維護請求
- `daily.log.man.machine` - 施工日誌人機記錄

**主要功能**：
- 參考 Odoo 18 maintenance 模組設計
- MTBF/MTTR 效能指標自動計算
- 設備維護請求與看板工作流
- 施工日誌人機記錄

---

### 9. construction_test

> 檢試驗管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Test |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `supervision.test.standard` - 檢試驗項目
- `supervision.test.record` - 檢(試)驗管制記錄

**主要功能**：
- 檢試驗項目管理（試驗工項/材料設定）
- 依據方法與規範要求
- 材料進場、取樣、試驗結果判定
- 自動計算取樣率

---

### 10. construction_review

> 送審管制

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Review |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `supervision.review.application` - 送審管制

**主要功能**：
- 材料型錄、樣品、測試報告送審追蹤
- 審查結果管理（合格/條件式通過/不合格）
- 廠驗與取樣試驗管理
- 送審日期追蹤

---

### 11. construction_photo

> 照片管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, mail |

**模型清單**：
- `supervision.photo` - 工程照片
- `supervision.photo.tag` - 照片標籤

**主要功能**：
- 工程照片上傳與管理
- 照片標籤分類系統
- GPS 位置記錄與追蹤
- 來源追蹤（施工日誌、自主檢查、缺失改善等）

---

### 12. construction_portal

> Portal 入口

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Portal |
| **依賴** | portal, construction_supervision_base, construction_quality, construction_photo |

**模型清單**：
- `supervision.project` (擴展) - 新增 Portal 統計欄位
- `general.self.inspection` (擴展) - Portal 填表功能
- `supervision.defect` (擴展) - Portal 改善提交
- `supervision.photo` (擴展) - Portal 上傳功能

**主要功能**：
- 承包廠商 Portal 用戶前台介面
- 工程案件瀏覽與統計
- 自主檢查表填寫
- 缺失改善說明提交
- 工程照片上傳

**Portal 路由**：
- `/my/construction` - 工程案件列表
- `/my/construction/{id}` - 工程詳情
- `/my/construction/{id}/inspections` - 自主檢查
- `/my/construction/{id}/defects` - 缺失列表
- `/my/construction/{id}/photos` - 照片管理

---

### 13. construction_progress

> 進度表管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, construction_daily_log |

**模型清單**：
- `progress.schedule` - 進度表
- `progress.schedule.line` - 進度表明細

**主要功能**：
- 每周、每兩周、自訂三種計算模式
- 累計進度自動計算
- 實際進度從施工日誌自動帶入
- 差異分析（超前/正常/落後狀態）

---

### 14. construction_template

> 樣板設定

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base |

**模型清單**：
- `document.template` - 文件樣板

**主要功能**：
- 支援多種樣板類型（施工日誌、自主檢查、缺失改善、進度表、估驗計價表等）
- 系統預設樣板與專案自訂樣板
- 多層級樣板優先順序
- Excel/Word 樣板格式支援

---

### 15. construction_cost_analysis

> 成本分析

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction |
| **依賴** | construction_supervision_base, construction_payment |

**模型清單**：
- `cost.analysis.report` - 成本分析報表 (DB View)
- `cost.analysis.summary` - 成本分析摘要 (DB View)

**主要功能**：
- 契約金額 vs 實際執行金額分析
- 各工項損益計算
- 按專案彙總
- 執行率與估驗率追蹤
- 使用資料庫視圖實作，即時計算

---

### 16. construction_price_library

> 價格庫管理

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base |

**模型清單**：
- `price.library.category` - 價格庫分類
- `price.library.item` - 價格庫項目
- `price.library.item.history` - 價格變更歷史
- `price.library.import.wizard` - 匯入精靈

**主要功能**：
- 樹狀分類結構
- 標準工項單價管理
- 自動記錄價格變更歷史
- 批次匯入契約工項

---

### 17. construction_batch

> 批次操作

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, construction_daily_log, construction_payment |

**模型清單**：
- `batch.download.wizard` - 批次下載精靈

**主要功能**：
- 施工日誌、自主檢查表、估驗計價表、檢試驗記錄批次下載
- 日期區間篩選
- 格式選擇（PDF/Excel）
- ZIP 壓縮打包下載

---

### 18. construction_timeline

> 時程控制

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Supervision |
| **依賴** | construction_supervision_base, hr_timesheet |

**模型清單**：
- `project.task` (擴展 timeline)
- `account.analytic.line` (擴展)
- `hr.timesheet.time.control.mixin`

**主要功能**：
- 參考 OCA project_timeline 和 hr_timesheet_time_control 設計
- Timeline 甘特圖視圖
- 施工計時器（開始/結束施工計時）
- 時程差異分析
- 工時記錄整合

---

### 19. construction_acceptance

> 驗收與結案

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction |
| **依賴** | construction_supervision_base, construction_payment, mail |

**模型清單**：
- `acceptance.preliminary` - 初驗
- `acceptance.final` - 正驗
- `acceptance.defect` - 驗收缺失
- `project.closure` - 結案處理

**主要功能**：
- 初驗（工程竣工後的初次驗收）
- 正驗（初驗缺失改善後的正式驗收）
- 驗收缺失追蹤（改善期限與進度管理）
- 結案處理（保固期設定與管理）

---

### 20. construction_general

> 一般式工程專用

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/General |
| **依賴** | construction_supervision_base, construction_quality, mail |

**模型清單**：
- `general.defect.improvement` - 一般式缺失改善
- `general.progress.report` - 進度報告
- `general.realtime.profit` - 即時損益

**主要功能**：
- 一般式工程專屬管理功能
- 自主檢查擴展
- 缺失改善
- 進度報告
- 即時損益計算

---

### 21. construction_reservation

> 預約式工程專用

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Reservation |
| **依賴** | construction_notification_slip, construction_quality |

**模型清單**：
- `reservation.notification.slip` (擴展)
- `reservation.self.inspection` (擴展)
- `reservation.defect.improvement` (擴展)

**主要功能**：
- 整合通報單與品質管理
- 從自主檢查缺失項目自動建立缺失改善記錄

---

### 22. construction_audit

> 稽核模組

| 項目 | 內容 |
|------|------|
| **版本** | 18.0.1.0.0 |
| **分類** | Construction/Audit |
| **依賴** | construction_supervision_base |

**模型清單**：
- `audit.trail` - 操作軌跡
- `audit.trail.mixin` - 稽核 Mixin

**主要功能**：
- 追蹤建立、修改、狀態變更、刪除等操作
- 記錄操作者、時間、來源記錄、變更前後的值
- Mixin 模式供其他模型繼承

---

## 安裝指南

### 系統需求

- Odoo 18.0
- Python 3.10+
- PostgreSQL 14+

### 安裝步驟

1. 將模組放置於 Odoo addons 目錄
2. 更新應用程式清單
3. 依序安裝模組

### 建議安裝順序

```bash
# 1. 安裝核心模組（必須最先）
construction_supervision_base

# 2. 安裝基礎功能模組
construction_daily_log
construction_payment
construction_quality

# 3. 安裝其餘模組（依需求）
construction_notification_slip  # 預約式工程
construction_contract_change
construction_partner
construction_equipment
construction_test
construction_review
construction_photo
construction_portal        # Portal 入口
construction_progress
construction_template
construction_cost_analysis
construction_price_library
construction_batch
construction_timeline
construction_acceptance
construction_audit

# 4. 安裝工程類型專用模組
construction_general      # 一般式工程
construction_reservation  # 預約式工程
```

---

## 官方模組依賴

| 模組 | 用途 |
|------|------|
| `base` | Odoo 核心 |
| `project` | 專案管理 |
| `hr_timesheet` | 工時表 |
| `contacts` | 聯絡人管理 |
| `mail` | 郵件與 Chatter |
| `maintenance` | 設備維護 |
| `portal` | Portal 入口 |

---

## 授權條款

本專案採用 [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0) 授權條款。

---

## 技術文件

詳細技術規格請參閱：[工程監造與施工協作管理系統 - Odoo 模組技術規格書.md](docs/technical-specs/工程監造與施工協作管理系統%20-%20Odoo%20模組技術規格書.md)

---

## 聯絡資訊

如有問題或建議，請透過 GitHub Issues 提出。

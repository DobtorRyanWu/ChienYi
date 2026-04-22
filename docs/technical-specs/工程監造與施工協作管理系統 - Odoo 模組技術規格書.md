# 工程監造與施工協作管理系統 - Odoo 模組技術規格書

> **版本**: 5.3
> **日期**: 2025-12-31
> **適用 Odoo 版本**: 18

---

## 一、系統概述

### 1.1 系統定位

「工程監造與施工協作管理系統」是一套基於 Odoo 18 平台開發的公共工程管理解決方案，採用**多公司架構**，整合政府工程法規與實務流程，提供**設計監造單位**與**施工廠商**的協作平台。

#### 1.1.1 業務角色定義

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           工程專案關係架構                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                         ┌───────────────┐                               │
│                         │   政府機關     │                               │
│                         │   (業主/客戶)  │                               │
│                         └───────┬───────┘                               │
│                                 │                                        │
│               ┌─────────────────┴─────────────────┐                     │
│               │ 發包標案                           │                     │
│               │                                   │                     │
│               ▼                                   ▼                     │
│   ┌───────────────────┐               ┌───────────────────┐            │
│   │   設計監造單位     │               │    施工廠商        │            │
│   │   (系統使用者)     │               │    (系統使用者)    │            │
│   │                   │               │                   │            │
│   │ ・審查施工成果    │  ─審核通過──► │ ・承接工項執行     │            │
│   │ ・執行工項分配    │               │ ・登錄工程記錄     │            │
│   │ ・驗收施工項目    │  ◄─提交審查─  │ ・只看自己工項     │            │
│   │ ・向業主請款      │               │ ・向業主請款       │            │
│   │   (服務費)        │               │   (工程款)         │            │
│   └───────────────────┘               └───────────────────┘            │
│               │                                   │                     │
│               │          請款對象                  │                     │
│               └─────────────────┬─────────────────┘                     │
│                                 ▼                                        │
│                         ┌───────────────┐                               │
│                         │   政府機關     │                               │
│                         │   (付款方)     │                               │
│                         └───────────────┘                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

| 角色 | 系統使用 | 職責 | 請款對象 |
|------|----------|------|----------|
| **政府機關** | 否 (客戶) | 發包設計監造標案、發包施工標案、核定付款 | - |
| **設計監造單位** | 是 (res.company) | 審查施工成果、分配工項給廠商、執行驗收、向政府請款服務費 | 政府機關 |
| **施工廠商** | 是 (res.company) | 承接分配工項、執行施工、登錄工程記錄、提交審查、向政府請款工程款 | 政府機關 |

#### 1.1.2 多公司架構設計

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Odoo 多公司架構 (Multi-Company)                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     工程標案 (supervision.project)               │    │
│  │                                                                   │    │
│  │  業主: 政府機關 (res.partner)                                     │    │
│  │  管理公司: 設計監造單位 (res.company)                             │    │
│  │  契約廠商: [廠商A, 廠商B, 廠商C] (res.company)                     │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     契約工項 (project.task)                       │    │
│  │                                                                   │    │
│  │  工項 A-1 ──► assigned_company_id = 廠商A                        │    │
│  │  工項 A-2 ──► assigned_company_id = 廠商A                        │    │
│  │  工項 B-1 ──► assigned_company_id = 廠商B                        │    │
│  │  工項 C-1 ──► assigned_company_id = 廠商C                        │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     資料隔離 (Record Rules)                       │    │
│  │                                                                   │    │
│  │  施工廠商 A 登入 ──► 只能看到 assigned_company_id = 廠商A 的工項  │    │
│  │  施工廠商 B 登入 ──► 只能看到 assigned_company_id = 廠商B 的工項  │    │
│  │  設計監造登入 ──► 可看到所有工項，可分配、可驗收                   │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Odoo 18 基礎模組映射

本系統基於以下 Odoo 18 官方模組進行擴展開發：

| 官方模組 | 本系統對應 | 說明 |
|----------|-----------|------|
| `project` | 工程標案主檔 | project.project → 工程案件 |
| `project.task` | 工項/工作任務 | 契約工項、施工項目 (含廠商分配) |
| `hr_timesheet` | 施工日誌基礎 | account.analytic.line → 工時/日誌紀錄 |
| `project_account` | 成本追蹤 | 分析帳戶整合 |
| `base` (multi-company) | 多公司架構 | res.company 公司隔離、權限控制 |
| `contacts` | 聯絡人管理 | res.partner → 業主/廠商管理 |
| `maintenance` | 設備管理 | 人機管理基礎 |

> **注意**: 本系統不使用 `purchase` 模組，驗收與請款流程為自訂設計。

#### 擴展模組參考設計

| 參考模組 | 設計模式應用 | 本系統功能 |
|----------|-------------|-----------|
| `hr_timesheet_sheet` | Sheet 聚合模式 + 2D 矩陣視圖 + 審核流程 | 施工日誌表單 |
| `hr_timesheet_day_week` | 日期維度計算 | 日誌統計分析 |
| `document_knowledge` | ir.attachment 擴展 + 版本控制 | 檔案管理 |
| `account_budget_oca` | 預算 vs 實際追蹤 + 達成率計算 | 契約預算與估驗實際 |

#### 預算 vs 實際追蹤設計 (v5.1)

> **設計參考**: `account_budget_oca` - OCA 預算管理模組
> - planned_amount (計畫/預算) vs practical_amount (實際)
> - 透過 account.analytic.line 追蹤實際執行
> - percentage (達成率) 用於對比分析

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    預算 vs 實際追蹤架構 (v5.1)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    契約工項 (預算層)                              │    │
│  │                                                                   │    │
│  │  一般式工程:                                                      │    │
│  │    契約工項 → planned_qty / planned_price → planned_amount       │    │
│  │                                                                   │    │
│  │  預約式工程:                                                      │    │
│  │    工程範疇量預估 → planned_qty / planned_price → planned_amount │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              │ (實際執行)                                │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    實際執行 (account.analytic.line)              │    │
│  │                                                                   │    │
│  │  施工日誌記錄 → 實際完成數量/金額                                  │    │
│  │  驗收單記錄 → 實際驗收數量/金額                                    │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              │ (估驗請款)                                │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    估驗請款 (實際請款層)                          │    │
│  │                                                                   │    │
│  │  估驗計價 → actual_qty × unit_price → actual_amount              │    │
│  │  請款單 → 基於實際驗收結果向業主請款                              │    │
│  │                                                                   │    │
│  │  對比: actual_amount vs planned_amount → completion_rate          │    │
│  │                                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

| 類型 | 預算來源 | 實際來源 | 說明 |
|------|----------|----------|------|
| **一般式** | 契約工項 (planned_qty × unit_price) | 估驗計價 (actual_qty × unit_price) | 契約價量為預算上限 |
| **預約式** | 工程範疇量預估 | 通報單實際執行量 | 範疇預估為預算框架 |

#### 多公司架構核心設計 (v5.0)

| 模型 | 多公司欄位 | 說明 |
|------|-----------|------|
| `supervision.project` | `company_id` (管理公司)、`contractor_company_ids` (承包廠商) | 專案層級的公司關聯 |
| `project.task` | `assigned_company_id` (承包公司) | 工項分配給特定廠商 |
| `daily.log.sheet` | `company_id` | 施工日誌依公司隔離 |
| `payment.claim` | `company_id`、`claim_type` (服務費/工程款) | 向業主請款單據 |

#### 核心實體映射圖

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Odoo 18 官方模組 → 工程監造系統 (v5.0 多公司架構)       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  project.project ─────────────────► supervision.project                  │
│  (專案)                              (工程標案)                           │
│      │                                    │                              │
│      ├─ account_id ───────────────────────┼─► 分析帳戶 (成本追蹤中心)    │
│      ├─ company_id ───────────────────────┼─► 管理公司 (設計監造單位)    │
│      │                                    │                              │
│      └─ task_ids ────────────────► project.task (契約工項)               │
│                                           │                              │
│                                    assigned_company_id ─► 承包廠商       │
│                                           │                              │
│                                           ├──► 一般式: 施工項目          │
│                                           └──► 預約式: 通報單工項        │
│                                                                          │
│  account.analytic.line ───────────► construction.daily.log.line          │
│  (工時表行)                          (施工日誌行)                         │
│      │                                    │                              │
│      └─ 透過 Sheet 模式 ──────────► construction.daily.log.sheet         │
│         (hr_timesheet_sheet 參考)    (施工日誌表單 - 依 company_id 隔離)  │
│                                                                          │
│  res.company ────────────────────► 多公司架構                            │
│  (公司)                              │                                   │
│      ├─ 設計監造單位 ────────────────┼─► 管理專案、審查驗收、請服務費    │
│      └─ 施工廠商 ────────────────────┴─► 承接工項、登錄記錄、請工程款    │
│                                                                          │
│  (自訂) ─────────────────────────► work.acceptance                       │
│  不使用 purchase 模組                (工項驗收單 - 獨立設計)              │
│                                                                          │
│  (自訂) ─────────────────────────► payment.claim                         │
│  不使用 purchase 模組                (請款單 - 向業主請款)                │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                    擴展模組映射                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  res.partner ─────────────────────► supervision.partner                  │
│  (聯絡人)                            (業主/廠商聯絡人)                    │
│      │                                    │                              │
│      ├─ category_id ──────────────────────┼─► 政府機關/監造/施工分類     │
│      └─ parent_id/child_ids ──────────────┴─► 組織階層 (總公司→分公司)  │
│                                                                          │
│  maintenance.equipment ───────────► supervision.equipment                │
│  (設備)                              (機具設備)                           │
│      │                                    │                              │
│      ├─ category_id ──────────────────────┼─► 挖掘機/裝載機/塔吊分類     │
│      ├─ maintenance_ids ──────────────────┼─► 維護保養請求               │
│      └─ MTBF/MTTR ────────────────────────┴─► 設備效能指標               │
│                                                                          │
│  ir.attachment ───────────────────► supervision.document                 │
│  (附件)                              (工程文件)                           │
│      │                                    │                              │
│      └─ res_model + res_id ───────────────┴─► 跨模組文件集中管理         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 工程類型

本系統支援兩種工程執行模式：

| 類型 | 技術名稱 | 說明 | 適用情境 |
|------|----------|------|----------|
| **一般式** | `general` | 傳統單一工程案件管理 | 單一地點、固定工期的標準工程案件 |
| **預約式** | `reservation` | 多通報單工程管理 | 跨多地點、分批執行的維護/修繕工程 |

#### 一般式與預約式差異對照

```
┌─────────────────────┬─────────────────────┬─────────────────────┐
│       功能模組       │      一般式         │      預約式         │
├─────────────────────┼─────────────────────┼─────────────────────┤
│ 工程主檔            │ 單一工程案件        │ 主契約 + 多通報單   │
│ 契約工項            │ ✓                   │ ✓                   │
│ 進度表              │ ✓                   │ ✓                   │
│ 施工日誌            │ 依契約工項          │ 依通報單            │
│ 通報單管理          │ ✗                   │ ✓ (核心功能)        │
│ 自主檢查            │ 獨立模組            │ 通報單內子功能      │
│ 缺失改善            │ 獨立模組            │ 通報單內子功能      │
│ 進度報告            │ ✓                   │ ✗                   │
│ 即時損益            │ ✓                   │ ✗                   │
│ 估驗計價            │ 全聯下載            │ 僅第一聯            │
│ 送審管制            │ ✓                   │ ✓                   │
│ 檢(試)驗管制        │ ✓                   │ ✓                   │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

### 1.4 核心設計原則

| 原則 | 說明 |
|------|------|
| 流程驅動 (Workflow-based) | 所有文件與作業皆透過狀態機控制審查、簽核流程 |
| 多方協作 | 監造、施工、機關在同一系統即時協作 |
| 可追溯性 | 完整版本控制、操作軌跡、稽核紀錄 |
| 法規對齊 | 符合政府採購法、工程施工查核作業要點等規範 |
| 模式彈性 | 同一系統支援一般式與預約式兩種工程執行模式 |

### 1.5 系統架構概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                      工程監造協作管理系統                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  機關承辦人  │  │  監造單位   │  │  施工廠商   │                  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
│         │                │                │                         │
│         ▼                ▼                ▼                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  Portal / Web Interface                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     核心業務模組                              │   │
│  │  ┌─────────────────────────────────────────────────────┐    │   │
│  │  │ 共用模組                                              │    │   │
│  │  │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │    │   │
│  │  │ │工程主檔 │ │契約工項 │ │進度表   │ │文件管理 │    │    │   │
│  │  │ └─────────┘ └─────────┘ └─────────┘ └─────────┘    │    │   │
│  │  │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │    │   │
│  │  │ │材料試驗 │ │送審管制 │ │估驗計價 │ │驗收管理 │    │    │   │
│  │  │ └─────────┘ └─────────┘ └─────────┘ └─────────┘    │    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  │                                                               │   │
│  │  ┌───────────────────────┐  ┌───────────────────────┐       │   │
│  │  │ 一般式專用模組         │  │ 預約式專用模組        │       │   │
│  │  │ ┌─────────┐           │  │ ┌─────────┐          │       │   │
│  │  │ │施工日誌 │(依契約工項)│  │ │通報單管理│ (核心)   │       │   │
│  │  │ └─────────┘           │  │ └─────────┘          │       │   │
│  │  │ ┌─────────┐           │  │ ┌─────────┐          │       │   │
│  │  │ │自主檢查 │           │  │ │施工日誌 │(依通報單) │       │   │
│  │  │ └─────────┘           │  │ └─────────┘          │       │   │
│  │  │ ┌─────────┐           │  │ ┌─────────┐          │       │   │
│  │  │ │缺失改善 │           │  │ │自主檢查 │(通報單內) │       │   │
│  │  │ └─────────┘           │  │ └─────────┘          │       │   │
│  │  │ ┌─────────┐           │  │ ┌─────────┐          │       │   │
│  │  │ │進度報告 │           │  │ │缺失改善 │(通報單內) │       │   │
│  │  │ └─────────┘           │  │ └─────────┘          │       │   │
│  │  │ ┌─────────┐           │  │                       │       │   │
│  │  │ │即時損益 │           │  │                       │       │   │
│  │  │ └─────────┘           │  │                       │       │   │
│  │  └───────────────────────┘  └───────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    基礎設施模組                               │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │   │
│  │  │ 工作流程引擎   │  │ 權限與稽核    │  │ 工程類型切換  │    │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、角色與權限模型 (RBAC) - 多公司架構

### 2.1 公司類型定義 (v5.0)

> **多公司架構說明**: 系統使用者分為「設計監造單位」與「施工廠商」兩種公司類型，
> 政府機關僅作為業主/客戶角色 (res.partner)，不直接使用系統。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         公司類型架構 (res.company)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  res.company                                                             │
│      │                                                                   │
│      ├─► company_type = 'supervision' (設計監造單位)                     │
│      │       ├─ 可建立工程專案                                           │
│      │       ├─ 可分配工項給施工廠商                                      │
│      │       ├─ 可審查施工提交的文件/記錄                                 │
│      │       ├─ 可執行驗收                                               │
│      │       └─ 可向業主請款 (服務費)                                     │
│      │                                                                   │
│      └─► company_type = 'contractor' (施工廠商)                          │
│              ├─ 只能看到分配給自己的工項                                  │
│              ├─ 只能操作自己公司的記錄                                    │
│              ├─ 提交文件/記錄給監造審查                                   │
│              └─ 可向業主請款 (工程款)                                     │
│                                                                          │
│  res.partner (業主 - 非系統使用者)                                       │
│      └─► partner_type = 'authority' (政府機關)                           │
│              ├─ 作為工程案件的業主欄位                                    │
│              └─ 作為請款單的付款對象                                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

| 公司類型 | 技術名稱 | 說明 | 資料存取範圍 |
|----------|----------|------|--------------|
| **設計監造單位** | `company_type='supervision'` | 專案管理公司 | 專案全部資料 |
| **施工廠商** | `company_type='contractor'` | 承包施工公司 | 僅自己公司分配的工項與相關記錄 |

### 2.2 角色定義 (群組)

| 角色 | 技術名稱 | 適用公司類型 | 主要職責 |
|------|----------|-------------|----------|
| 系統管理者 | `group_supervisor_admin` | 全部 | 帳號管理、流程設定、權限維護 |
| 監造主管 | `group_supervision_manager` | 設計監造 | 專案管理、工項分配、驗收核定 |
| 監造工程師 | `group_supervision_engineer` | 設計監造 | 文件審查、監造日報、缺失開立 |
| 廠商主管 | `group_contractor_manager` | 施工廠商 | 請款申請、文件提送核准 |
| 廠商工程師 | `group_contractor_engineer` | 施工廠商 | 施工記錄、文件填寫、缺失改善 |

### 2.3 權限矩陣 (含公司隔離)

```
功能模組              系統管理  監造主管  監造工程師  廠商主管  廠商工程師
──────────────────────────────────────────────────────────────────────────
工程主檔 - 建立        ✓         ✓          -          -          -
工程主檔 - 檢視        ✓         ✓          ✓          ✓*         ✓*
工程主檔 - 修改        ✓         ✓          -          -          -
──────────────────────────────────────────────────────────────────────────
工項 - 分配廠商        -         ✓          -          -          -
工項 - 檢視全部        ✓         ✓          ✓          -          -
工項 - 檢視(限己方)    -         -          -          ✓*         ✓*
──────────────────────────────────────────────────────────────────────────
文件 - 提送            -         -          -          ✓          ✓
文件 - 審查            -         ✓          ✓          -          -
文件 - 檢視全部        ✓         ✓          ✓          -          -
文件 - 檢視(限己方)    -         -          -          ✓*         ✓*
──────────────────────────────────────────────────────────────────────────
施工日誌 - 填寫        -         -          -          ✓          ✓
施工日誌 - 審核        -         ✓          ✓          -          -
施工日誌 - 檢視全部    ✓         ✓          ✓          -          -
施工日誌 - 檢視(限己方) -        -          -          ✓*         ✓*
──────────────────────────────────────────────────────────────────────────
監造日報 - 填寫        -         ✓          ✓          -          -
監造日報 - 檢視        ✓         ✓          ✓          ✓          ✓
──────────────────────────────────────────────────────────────────────────
驗收 - 辦理            -         ✓          ✓          -          -
驗收 - 缺失改善        -         -          -          ✓          ✓
──────────────────────────────────────────────────────────────────────────
請款 - 服務費申請      -         ✓          -          -          -
請款 - 工程款申請      -         -          -          ✓          -
請款 - 檢視(限己方)    -         ✓          ✓          ✓*         ✓*
──────────────────────────────────────────────────────────────────────────

* 標記 ✓* 表示透過 Record Rules 限制只能存取自己公司的資料
```

### 2.4 資料隔離規則 (Record Rules)

```python
# security/ir.rules.xml

# 施工廠商工項隔離規則
<record id="rule_contractor_task_access" model="ir.rule">
    <field name="name">Contractor: Access assigned tasks only</field>
    <field name="model_id" ref="project.model_project_task"/>
    <field name="domain_force">[
        '|',
        ('assigned_company_id', '=', False),  # 未分配的工項
        ('assigned_company_id', '=', user.company_id.id)  # 分配給自己公司
    ]</field>
    <field name="groups" eval="[(4, ref('group_contractor_manager')),
                                 (4, ref('group_contractor_engineer'))]"/>
</record>

# 施工廠商日誌隔離規則
<record id="rule_contractor_daily_log_access" model="ir.rule">
    <field name="name">Contractor: Access own company daily logs</field>
    <field name="model_id" ref="model_daily_log_sheet"/>
    <field name="domain_force">[('company_id', '=', user.company_id.id)]</field>
    <field name="groups" eval="[(4, ref('group_contractor_manager')),
                                 (4, ref('group_contractor_engineer'))]"/>
</record>

# 請款單公司隔離規則
<record id="rule_payment_claim_company" model="ir.rule">
    <field name="name">Payment Claim: Access own company only</field>
    <field name="model_id" ref="model_payment_claim"/>
    <field name="domain_force">[('company_id', '=', user.company_id.id)]</field>
    <field name="groups" eval="[(4, ref('group_contractor_manager')),
                                 (4, ref('group_supervision_manager'))]"/>
</record>
```

### 2.5 res.company 擴展

```python
class ResCompany(models.Model):
    _inherit = 'res.company'

    company_type = fields.Selection([
        ('supervision', '設計監造單位'),
        ('contractor', '施工廠商'),
    ], string='公司類型', required=True, default='contractor',
       help='決定此公司在工程管理系統中的角色')

    # 證照資訊
    contractor_license = fields.Char('營造業登記證號')
    contractor_grade = fields.Selection([
        ('A', '甲級'),
        ('B', '乙級'),
        ('C', '丙級'),
    ], string='營造廠商等級')

    # 專案關聯
    supervised_project_ids = fields.One2many(
        'supervision.project', 'company_id', '管理的專案',
        help='此公司作為設計監造單位管理的專案')

    contracted_project_ids = fields.Many2many(
        'supervision.project', 'project_contractor_company_rel',
        'company_id', 'project_id', string='承包的專案',
        help='此公司作為施工廠商參與的專案')
```

---

## 三、業務流程與階段

### 3.1 工程生命週期

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  籌備   │───▶│  施工   │───▶│  竣工   │───▶│  驗收   │───▶│  結案   │
│  階段   │    │  階段   │    │  階段   │    │  階段   │    │  封存   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │              │
     ▼              ▼              ▼              ▼              ▼
  開工申報      日常監造       竣工申報       初驗/正驗      文件封存
  文件核定      施工紀錄       結算準備       缺失改善       稽核調閱
```

### 3.2 階段一：施工前計畫階段 (Pre-Construction)

#### 3.2.1 開工申報流程

**必要文件清單**:
| 序號 | 文件類型 | 提送者 | 審查者 | 核定者 |
|------|----------|--------|--------|--------|
| 1 | 工地人員名冊 | 施工廠商 | 監造單位 | 機關 |
| 2 | 工程預定進度表 | 施工廠商 | 監造單位 | 機關 |
| 3 | 剩餘資源處理計畫書 | 施工廠商 | 監造單位 | 機關 |
| 4 | 施工計畫書 | 施工廠商 | 監造單位 | 機關 |
| 5 | 品質計畫書 | 施工廠商 | 監造單位 | 機關 |
| 6 | 職業安全衛生管理計畫書 | 施工廠商 | 監造單位 | 機關 |
| 7 | 工程保險證明 | 施工廠商 | 監造單位 | 機關 |
| 8 | 材料設備送審資料 | 施工廠商 | 監造單位 | 機關 |

**文件狀態流程**:
```
草稿 (draft) → 已提送 (submitted) → 審查中 (reviewing) 
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              補正 (revision)     建議核定 (recommend)   退件 (rejected)
                    │                    │
                    ▼                    ▼
              已提送 (submitted)   核定 (approved) → 鎖定
```

#### 3.2.2 監造審查機制

```python
# 審查意見資料結構
class SupervisionReviewComment(models.Model):
    _name = 'supervision.review.comment'
    
    document_id = fields.Many2one('supervision.document')
    item_no = fields.Integer('審查項次')
    review_item = fields.Char('審查項目')
    review_result = fields.Selection([
        ('pass', '符合'),
        ('revision', '補正'),
        ('reject', '不符合')
    ])
    comment = fields.Text('審查意見')
    reviewer_id = fields.Many2one('res.users')
    review_date = fields.Datetime()
```

### 3.3 階段二：施工階段 (Construction)

#### 3.3.1 施工廠商日常作業

> **設計參考**: `hr_timesheet_sheet` 模組的 Sheet 聚合模式
> **核心概念**: 日誌表單 (Sheet) 聚合多日的日誌行 (Line)，支援 2D 矩陣視圖和審核流程

**施工日誌架構** (三層結構):

```
┌─────────────────────────────────────────────────────────────────┐
│                    施工日誌表單 (Sheet)                          │
│                   daily.log.sheet                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ 期間: 2024-12-02 ~ 2024-12-08 (一週)                       │  │
│  │ 員工: 張三 (工地主任)                                      │  │
│  │ 狀態: draft → confirm → done                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ 2D 矩陣視圖 (x2many_2d_matrix widget)                      │  │
│  │                                                             │  │
│  │            │ Mon 12/2 │ Tue 12/3 │ Wed 12/4 │ ...          │  │
│  │  ─────────┼──────────┼──────────┼──────────┼────          │  │
│  │  工項 A    │    ✓     │    ✓     │    ✓     │              │  │
│  │  工項 B    │    ✓     │          │    ✓     │              │  │
│  │  人力統計  │   15人   │   18人   │   20人   │              │  │
│  │  機具統計  │   3台    │   3台    │   4台    │              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ 日誌行 (Lines) - 繼承 account.analytic.line                 │  │
│  │ daily.log.line                                              │  │
│  │ [date, project_id, task_id, employee_id, unit_amount, ...]  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**施工日誌表單 (Sheet)**:

> **多公司隔離** (v5.0): 施工廠商只能看到自己公司的日誌記錄

```python
class DailyLogSheet(models.Model):
    """施工日誌表單 - 參考 hr_timesheet_sheet 設計"""
    _name = 'daily.log.sheet'
    _description = '施工日誌表單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    # === 基本資訊 ===
    name = fields.Char('名稱', compute='_compute_name', store=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)
    project_type = fields.Selection(related='project_id.project_type', store=True)

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company', '填報公司', required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'contractor')]",
        help='施工廠商公司，用於資料隔離')

    # 關聯工項 (用於隔離驗證)
    task_ids = fields.Many2many(
        'project.task', string='關聯工項',
        domain="[('assigned_company_id', '=', company_id)]",
        help='此日誌記錄的工項必須是分配給此公司的')

    # 預約式專用
    notification_slip_id = fields.Many2one(
        'notification.slip', '所屬通報單',
        domain="[('project_id', '=', project_id)]")

    # === 期間 (參考 hr_timesheet_sheet) ===
    date_start = fields.Date('開始日期', required=True, index=True)
    date_end = fields.Date('結束日期', required=True, index=True)
    sheet_range = fields.Selection([
        ('daily', '每日'),
        ('weekly', '每週'),
        ('monthly', '每月'),
    ], string='期間範圍', default='daily', required=True)

    # === 填表人 ===
    employee_id = fields.Many2one('hr.employee', '填表人', required=True)
    user_id = fields.Many2one('res.users', '使用者', related='employee_id.user_id')
    department_id = fields.Many2one('hr.department', '部門', related='employee_id.department_id')

    # === 日誌行 (聚合多日紀錄) ===
    line_ids = fields.One2many('daily.log.line', 'sheet_id', '日誌明細')
    matrix_line_ids = fields.One2many(
        'daily.log.sheet.line', 'sheet_id', '矩陣行',
        compute='_compute_matrix_lines',
        help='用於 2D 矩陣視圖顯示')

    # === 統計 ===
    total_worker_count = fields.Integer('總人力', compute='_compute_totals', store=True)
    total_equipment_count = fields.Integer('總機具', compute='_compute_totals', store=True)

    # === 天氣 (每日填寫) ===
    weather_ids = fields.One2many('daily.log.weather', 'sheet_id', '天氣紀錄')

    # === 狀態流程 (參考 hr_timesheet_sheet) ===
    state = fields.Selection([
        ('new', '新建'),
        ('draft', '草稿'),
        ('confirm', '待審核'),
        ('done', '已核准'),
    ], string='狀態', default='new', tracking=True)

    # === 審核資訊 ===
    reviewer_id = fields.Many2one('res.users', '審核者', tracking=True)
    review_date = fields.Datetime('審核時間')
    review_policy = fields.Selection([
        ('supervisor', '監造主管'),
        ('authority', '機關承辦'),
    ], string='審核政策', default='supervisor')
    can_review = fields.Boolean('可審核', compute='_compute_can_review')

    # === 狀態動作 (參考 hr_timesheet_sheet) ===
    def action_draft(self):
        """重設為草稿"""
        self.write({'state': 'draft'})

    def action_confirm(self):
        """提交審核"""
        self._check_sheet_validity()
        self.write({'state': 'confirm'})

    def action_done(self):
        """審核通過"""
        self._check_can_review()
        self.write({
            'state': 'done',
            'reviewer_id': self.env.uid,
            'review_date': fields.Datetime.now(),
        })

    def action_refuse(self):
        """審核退回"""
        self._check_can_review()
        self.write({'state': 'draft'})


class DailyLogLine(models.Model):
    """施工日誌行 - 繼承 account.analytic.line"""
    _name = 'daily.log.line'
    _description = '施工日誌明細'
    _inherits = {'account.analytic.line': 'analytic_line_id'}

    # === 關聯原生工時表 ===
    analytic_line_id = fields.Many2one(
        'account.analytic.line', '工時行', required=True, ondelete='cascade',
        auto_join=True)

    # === Sheet 關聯 ===
    sheet_id = fields.Many2one('daily.log.sheet', '日誌表單', ondelete='cascade')
    sheet_state = fields.Selection(related='sheet_id.state')

    # === 日誌專用欄位 ===
    day_week = fields.Selection([
        ('0', '週一'), ('1', '週二'), ('2', '週三'),
        ('3', '週四'), ('4', '週五'), ('5', '週六'), ('6', '週日'),
    ], string='星期', compute='_compute_day_week', store=True)

    # === 施工項目 ===
    work_item_id = fields.Many2one('project.task', '施工項目',
                                    domain="[('project_id.supervision_project_id', '=', project_id)]")
    completion_qty = fields.Float('完成數量')
    completion_unit = fields.Char('單位')

    # === 人機材 ===
    worker_count = fields.Integer('人力數')
    equipment_count = fields.Integer('機具數')
    material_note = fields.Text('材料說明')

    @api.depends('date')
    def _compute_day_week(self):
        """計算星期幾 (參考 hr_timesheet_day_week)"""
        for rec in self:
            if rec.date:
                rec.day_week = str(rec.date.weekday())
            else:
                rec.day_week = False
```

**施工日誌天氣** (每日紀錄):
```python
class DailyLogWeather(models.Model):
    """每日天氣紀錄"""
    _name = 'daily.log.weather'
    _description = '施工日誌天氣'

    sheet_id = fields.Many2one('daily.log.sheet', '日誌表單', required=True, ondelete='cascade')
    date = fields.Date('日期', required=True)
    weather_am = fields.Selection([
        ('sunny', '晴'), ('cloudy', '陰'), ('rainy', '雨')
    ], string='上午天氣')
    weather_pm = fields.Selection([
        ('sunny', '晴'), ('cloudy', '陰'), ('rainy', '雨')
    ], string='下午天氣')

    # === 工期資訊 ===
    approved_duration = fields.Integer('核定工期', readonly=True)
    cumulative_duration = fields.Integer('累計工期', compute='_compute_duration')
    remaining_duration = fields.Integer('剩餘工期', compute='_compute_duration')

    # === 進度資訊 ===
    planned_progress = fields.Float('預定進度 (%)', readonly=True)
    actual_progress = fields.Float('實際進度 (%)')
    has_progress_change = fields.Boolean('今日有進度變更', default=False)
```

#### 3.3.2 監造單位作業

**監造日報/週報**:
```python
class SupervisionDailyReport(models.Model):
    _name = 'supervision.daily.report'
    
    project_id = fields.Many2one('supervision.project')
    report_date = fields.Date('報表日期')
    report_type = fields.Selection([
        ('daily', '日報'), ('weekly', '週報')
    ])
    
    # 監造內容
    inspection_summary = fields.Text('監造工作摘要')
    safety_check = fields.Text('安全衛生檢查')
    quality_check = fields.Text('品質檢查')
    
    # 檢驗停留點 (Hold Point)
    hold_point_ids = fields.One2many('supervision.hold.point')
    
    # 缺失紀錄
    defect_ids = fields.One2many('supervision.defect')
    
    # 會議紀錄
    meeting_ids = fields.One2many('supervision.meeting')
```

**抽查紀錄**:
```python
class SupervisionInspection(models.Model):
    _name = 'supervision.inspection'
    
    inspection_type = fields.Selection([
        ('construction', '施工抽查'),
        ('safety', '安衛抽查'),
        ('quality', '品質抽查'),
        ('material', '材料抽查')
    ])
    inspection_date = fields.Datetime()
    inspector_id = fields.Many2one('res.users')
    
    # 檢查項目
    checklist_ids = fields.One2many('supervision.checklist.item')
    
    # 結果
    result = fields.Selection([
        ('pass', '合格'), ('fail', '不合格'), ('conditional', '有條件通過')
    ])
    
    # 缺失關聯
    defect_ids = fields.One2many('supervision.defect')
```

### 3.4 階段三：竣工階段 (Completion)

**竣工文件清冊檢核**:
```python
class CompletionDocumentChecklist(models.Model):
    _name = 'completion.document.checklist'
    
    project_id = fields.Many2one('supervision.project')
    
    # 自動檢查必要文件
    def check_required_documents(self):
        required_types = [
            'completion_drawing',      # 竣工圖
            'completion_settlement',   # 竣工結算
            'quality_certificate',     # 品質證明
            'test_report',            # 試驗報告
            'warranty_certificate',   # 保固書
        ]
        missing = []
        for doc_type in required_types:
            if not self.env['supervision.document'].search([
                ('project_id', '=', self.project_id.id),
                ('document_type', '=', doc_type),
                ('state', '=', 'approved')
            ]):
                missing.append(doc_type)
        return missing
```

### 3.5 階段四：驗收階段 (Acceptance)

**驗收流程**:
```
辦理初驗 → 缺失紀錄 → 限期改善 → 改善確認 → 辦理正驗 → 驗收合格
     │                      │
     ▼                      ▼
  無缺失              改善前後照片
  直接正驗              比對確認
```

**驗收缺失追蹤**:
```python
class AcceptanceDefect(models.Model):
    _name = 'acceptance.defect'
    
    acceptance_id = fields.Many2one('project.acceptance')
    defect_no = fields.Char('缺失編號')
    description = fields.Text('缺失說明')
    location = fields.Char('位置')
    
    # 責任歸屬
    responsible_party = fields.Selection([
        ('contractor', '施工廠商'),
        ('subcontractor', '分包商')
    ])
    responsible_user_id = fields.Many2one('res.users')
    
    # 期限
    deadline = fields.Date('改善期限')
    
    # 照片
    before_photo_ids = fields.Many2many('ir.attachment', relation='defect_before_photo')
    after_photo_ids = fields.Many2many('ir.attachment', relation='defect_after_photo')
    
    # 狀態
    state = fields.Selection([
        ('open', '待改善'),
        ('improving', '改善中'),
        ('submitted', '已提送'),
        ('confirmed', '已確認'),
        ('closed', '結案')
    ])
```

### 3.6 階段五：結案與封存

**結案處理**:
```python
class ProjectClosure(models.Model):
    _name = 'project.closure'
    
    project_id = fields.Many2one('supervision.project')
    closure_date = fields.Date('結案日期')
    
    # 決算資料
    settlement_amount = fields.Float('決算金額')
    settlement_document_id = fields.Many2one('supervision.document')
    
    # 監造報告
    supervision_report_id = fields.Many2one('supervision.document')
    
    # 封存
    is_archived = fields.Boolean('已封存')
    archive_date = fields.Datetime('封存時間')
    
    def action_archive(self):
        """封存所有相關文件，設為唯讀"""
        self.project_id.state = 'closed'
        self.project_id.document_ids.write({'is_locked': True})
        self.is_archived = True
        self.archive_date = fields.Datetime.now()
```

---

## 四、核心模組設計

### 4.1 模組清單與相依性 (v5.2)

#### Odoo 18 官方模組依賴

```
# 官方模組 (必須安裝)
project                 # 專案管理核心
├── project_account    # 專案會計 (分析帳戶)
└── hr_timesheet       # 工時表 (施工日誌基礎)

base                    # 多公司架構核心
├── res.company        # 公司管理 (設計監造/施工廠商)
└── ir.rule            # 資料隔離規則

contacts                # 聯絡人管理 (業主/聯絡人)
├── base               # res.partner 核心
└── mail               # 郵件追蹤

maintenance             # 設備維護 (人機管理)
├── mail               # 郵件追蹤
└── 設計模式: MTBF/MTTR 效能指標

# 注意: 本系統不使用 purchase 模組
# 驗收與請款流程為自訂設計
```

> **v5.0 重要變更**: 移除 `project_purchase`、`purchase_stock` 依賴，
> 驗收流程改為自訂的 `work.acceptance` 模組，
> 請款流程新增自訂的 `payment.claim` 模組。

#### OCA 社群模組參考 (v5.2 新增)

```
# project-18.0 (時間計畫與版本控制)
project_timeline              # Timeline 視圖
├── planned_date_start/end   # Datetime 計畫時間
└── 設計模式: 計算欄位 + 約束驗證

project_timesheet_time_control  # 時間控制
├── hr.timesheet.time_control.mixin
├── button_start_work / button_end_work
└── 設計模式: running domain + 計時器

project_version              # 版本追蹤
├── project.version          # 版本主檔
├── version_id               # task 關聯版本
└── 設計模式: 工程契約變更基礎

# account-budgeting-18.0 (預算追蹤)
account_budget_oca           # 預算管理
├── planned_amount / practical_amount
└── 設計模式: 預算 vs 實際對比
```

#### 工程監造專用模組

```
construction_supervision_base           # 基礎模組
├── depends: project, project_account, hr_timesheet, contacts
├── supervision_project               # 工程主檔 (繼承 project.project + 多公司)
├── supervision_task                  # 契約工項 (繼承 project.task + 廠商分配)
├── supervision_document              # 文件管理
├── supervision_company               # 公司類型擴展 (res.company)
└── supervision_workflow              # 工作流程引擎
│
construction_daily_log                  # 施工日誌模組
├── depends: hr_timesheet, construction_supervision_base
├── daily_log_sheet                   # 日誌表單 (+ 公司隔離)
├── daily_log_line                    # 日誌行 (繼承 account.analytic.line)
└── daily_log_statistics              # 統計分析
│
construction_notification_slip          # 通報單模組 (預約式)
├── depends: construction_supervision_base
├── notification_slip                 # 通報單
├── notification_slip_line            # 通報單明細
└── notification_acceptance           # 通報單驗收
│
# ============ 一般式專用模組 ============
construction_general                    # 一般式工程模組
├── depends: construction_supervision_base
├── general_self_inspection           # 自主檢查 (獨立模組)
├── general_defect_improvement        # 缺失改善 (獨立模組)
├── general_progress_report           # 進度報告
└── general_realtime_profit           # 即時損益
│
# ============ 預約式專用模組 ============
construction_reservation                # 預約式工程模組
├── depends: construction_notification_slip
├── reservation_self_inspection       # 自主檢查 (通報單內)
└── reservation_defect                # 缺失改善 (通報單內)
│
# ============ 共用模組 ============
construction_quality                    # 品質管理 (共用)
├── depends: construction_supervision_base
├── quality_checklist                 # 自主檢查表樣板
├── quality_test                      # 試驗管理
└── quality_defect                    # 缺失管理 (NCR)
│
# ============ v5.0 計價與請款模組 (不依賴 purchase) ============
construction_payment                    # 計價與請款模組 (共用)
├── depends: construction_supervision_base
├── work_acceptance                   # 工項驗收 (自訂設計)
├── payment_estimate                  # 估驗計價 (+ 公司隔離)
├── payment_claim                     # 請款單 (向業主請款)
└── payment_settlement                # 決算管理
│
# ============ v5.2 契約變更與時程控制模組 ============
construction_contract_change            # 契約變更模組 (參考 project_version)
├── depends: construction_supervision_base
├── contract_change_order             # 契約變更單
├── contract_change_order_line        # 變更明細
└── 支援金額/數量/工期變更追蹤
│
construction_timeline                   # 時程控制模組 (參考 project_timeline)
├── depends: construction_supervision_base, hr_timesheet
├── task_timeline                     # Timeline 視圖支援
├── task_time_control                 # 開始/結束計時
└── schedule_variance                 # 時程差異分析
│
# ============ v5.2.1 補充模組 ============
construction_progress                   # 進度表模組
├── depends: construction_supervision_base, construction_daily_log
├── progress_schedule                 # 進度表
├── progress_schedule_line            # 進度表明細
└── 支援每周/每兩周/自訂計算模式
│
construction_template                   # 樣板設定模組
├── depends: construction_supervision_base
├── document_template                 # 文件樣板
└── 支援專案專屬/公司預設/系統預設
│
construction_cost_analysis              # 成本分析模組
├── depends: construction_supervision_base, construction_payment
├── cost_analysis_report              # 成本分析報表 (資料庫視圖)
└── cost_analysis_summary             # 成本分析摘要
│
construction_price_library              # 價格庫模組
├── depends: construction_supervision_base
├── price_library_category            # 價格庫分類
├── price_library_item                # 價格庫項目
├── price_library_item_history        # 價格變更歷史
└── price_library_import_wizard       # 匯入精靈
│
construction_batch                      # 批次操作模組
├── depends: construction_supervision_base
└── batch_download_wizard             # 批次下載精靈
│
construction_acceptance                 # 驗收模組 (共用)
├── depends: construction_payment
├── acceptance_preliminary            # 初驗
└── acceptance_final                  # 正驗
│
construction_audit                      # 稽核模組 (共用)
└── audit_trail                       # 操作軌跡
│
# ============ 擴展模組 ============
construction_partner                    # 工程單位管理 (參考 contacts)
├── depends: contacts, construction_supervision_base
├── supervision_partner_category       # 工程單位分類標籤
├── partner_license                    # 廠商證照資料
└── partner_technical_contact          # 技術聯絡人
│
construction_equipment                  # 人機管理 (參考 maintenance)
├── depends: maintenance, construction_supervision_base
├── supervision_equipment_category     # 機具設備分類
├── supervision_equipment              # 機具設備
├── supervision_equipment_request      # 維護請求
└── daily_log_man_machine              # 施工日誌人機記錄
│
construction_test                       # 檢試驗管理
├── depends: construction_supervision_base
├── supervision_test_standard          # 檢試驗項目
└── supervision_test_record            # 檢(試)驗記錄
│
construction_review                     # 送審管制
├── depends: construction_supervision_base
└── supervision_review_application     # 送審管制
│
construction_photo                      # 照片管理
├── depends: construction_supervision_base
├── supervision_photo                  # 工程照片
└── supervision_photo_tag              # 照片標籤
```

#### 模組相依性圖 (v5.0)

```
                         Odoo 18 官方模組
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
    ▼                        ▼                        ▼
 project              hr_timesheet               contacts
 project_account                                 maintenance
    │                        │                        │
    │        ┌───────────────┴────────────────────────┘
    │        │
    │        ▼
    │   base (multi-company)
    │   ├── res.company (公司類型: supervision/contractor)
    │   └── ir.rule (資料隔離)
    │        │
    └────────┴───────────────┐
                             ▼
              construction_supervision_base
              (工程主檔 + 契約工項 + 廠商分配)
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         eng_daily      eng_notif      eng_general / eng_reservation
           _log          _slip         (依工程類型)
        (公司隔離)                           │
              │              │              │
              └──────┬───────┴──────────────┘
                     ▼
         eng_quality / eng_payment / eng_acceptance / eng_audit
                            │
                            ├── work_acceptance (自訂驗收)
                            └── payment_claim (向業主請款)
```

### 4.2 工程主檔 (supervision_project)

> **設計模式**: 繼承 `project.project`，擴展工程監造專用欄位
> **分析帳戶**: 自動繼承 project 的 `account_id`，用於成本追蹤
> **多公司架構** (v5.0): 支援設計監造管理、多施工廠商承包

```python
class SupervisionProject(models.Model):
    """工程標案主檔 - 繼承 Odoo 18 project.project"""
    _name = 'supervision.project'
    _description = '工程案件主檔'
    _inherits = {'project.project': 'project_id'}  # 委派繼承
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # === 關聯原生專案 ===
    project_id = fields.Many2one(
        'project.project', '專案', required=True, ondelete='cascade',
        auto_join=True, help='關聯 Odoo 原生專案，自動繼承分析帳戶')

    # === 基本資料 (擴展) ===
    code = fields.Char('工程編號', required=True, copy=False, index=True)

    # === 工程類型 ===
    project_type = fields.Selection([
        ('general', '一般式'),
        ('reservation', '預約式'),
    ], string='工程類型', required=True, default='general', tracking=True,
       help='一般式: 單一工程案件管理; 預約式: 多通報單工程管理')

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company', '管理公司', required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'supervision')]",
        help='負責管理此專案的設計監造單位')

    contractor_company_ids = fields.Many2many(
        'res.company', 'project_contractor_company_rel',
        'project_id', 'company_id', string='承包廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='參與此專案的施工廠商公司')

    # === 業主資訊 (v5.0 調整) ===
    authority_id = fields.Many2one(
        'res.partner', '業主/主辦機關', required=True,
        domain="[('partner_type', '=', 'authority')]",
        help='政府機關，為請款對象')

    # 契約資訊 (工程專用擴展)
    contract_no = fields.Char('契約編號')
    contract_amount = fields.Float('契約金額')
    contract_start_date = fields.Date('契約開工日')
    contract_end_date = fields.Date('契約完工日')
    contract_duration = fields.Integer('契約工期(日)', compute='_compute_duration')

    # === 人員資訊 (簡化) ===
    supervision_engineer_id = fields.Many2one('res.users', '監造工程師',
        domain="[('company_id', '=', company_id)]")

    # 工程位置
    location = fields.Char('工程地點')
    latitude = fields.Float('緯度')
    longitude = fields.Float('經度')

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('preparing', '籌備中'),
        ('pending_approval', '待核定'),
        ('construction', '施工中'),
        ('completion', '已竣工'),
        ('acceptance', '驗收中'),
        ('closed', '已結案'),
        ('suspended', '停工'),
        ('terminated', '終止')
    ], default='draft', tracking=True)

    # === 關聯 ===
    document_ids = fields.One2many('supervision.document', 'project_id', '相關文件')
    daily_log_ids = fields.One2many('construction.daily.log', 'project_id', '施工日誌')
    supervision_report_ids = fields.One2many('supervision.daily.report', 'project_id', '監造報表')
    defect_ids = fields.One2many('supervision.defect', 'project_id', '缺失紀錄')
    estimate_ids = fields.One2many('payment.estimate', 'project_id', '估驗計價')
    claim_ids = fields.One2many('payment.claim', 'project_id', '請款單')  # v5.0 新增

    # === 預約式專用關聯 ===
    notification_slip_ids = fields.One2many(
        'reservation.notification.slip', 'project_id', '通報單',
        help='僅預約式工程使用，用於管理多地點分批施工')
    notification_slip_count = fields.Integer('通報單數量', compute='_compute_notification_slip_count')

    # === 進度 ===
    planned_progress = fields.Float('預定進度 (%)', compute='_compute_progress')
    actual_progress = fields.Float('實際進度 (%)')
    progress_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後')
    ], compute='_compute_progress_status')

    # === 廠商分配輔助方法 ===
    def action_assign_contractor(self):
        """開啟工項分配廠商精靈"""
        return {
            'type': 'ir.actions.act_window',
            'name': '分配工項給廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_project_id': self.id}
        }
```

#### 4.2.1 契約工項擴展 (廠商分配 + 預算追蹤 + 時間計畫)

> **多公司架構** (v5.0): 工項可分配給特定施工廠商
> **預算追蹤** (v5.1): 契約工項為預算，實際執行為實際，參考 account_budget_oca
> **時間計畫** (v5.2): 參考 project_timeline, project_timesheet_time_control 模組

```python
class ProjectTask(models.Model):
    """契約工項 - 擴展 project.task 支援廠商分配、預算追蹤與時間計畫"""
    _name = 'project.task'
    _inherit = ['project.task', 'hr.timesheet.time_control.mixin']

    # === 廠商分配 (v5.0) ===
    assigned_company_id = fields.Many2one(
        'res.company', '承包廠商', index=True,
        domain="[('company_type', '=', 'contractor'), "
               "('id', 'in', parent.contractor_company_ids.ids)]",
        help='此工項分配給哪家施工廠商執行')

    assignment_date = fields.Date('分配日期')
    assigned_by_id = fields.Many2one('res.users', '分配人')

    # === 預算欄位 (v5.1 - 契約價量) ===
    # 參考 account_budget_oca: planned_amount
    item_no = fields.Char('工項編號')
    planned_qty = fields.Float('契約數量', help='契約預估數量 (預算)')
    unit = fields.Char('單位')
    unit_price = fields.Float('契約單價', help='契約預估單價')
    planned_amount = fields.Float(
        '契約金額', compute='_compute_planned_amount', store=True,
        help='planned_qty × unit_price (預算上限)')

    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        for task in self:
            task.planned_amount = task.planned_qty * task.unit_price

    # === 實際執行欄位 (v5.1) ===
    # 參考 account_budget_oca: practical_amount (從 analytic line 彙總)
    actual_qty = fields.Float(
        '實際完成數量', compute='_compute_actual_amounts', store=True,
        help='從估驗計價彙總 (已核定)')
    actual_amount = fields.Float(
        '實際請款金額', compute='_compute_actual_amounts', store=True,
        help='actual_qty × unit_price')

    # === 對比分析 (v5.1) ===
    # 參考 account_budget_oca: percentage
    completion_rate = fields.Float(
        '完成率 (%)', compute='_compute_actual_amounts', store=True,
        help='actual_amount / planned_amount × 100')
    budget_status = fields.Selection([
        ('under', '低於預算'),
        ('on_budget', '符合預算'),
        ('over', '超出預算'),
    ], string='預算狀態', compute='_compute_actual_amounts', store=True)

    @api.depends('estimate_line_ids.state', 'estimate_line_ids.current_qty',
                 'planned_amount', 'unit_price')
    def _compute_actual_amounts(self):
        """彙總實際執行數量與金額 (僅計算已核定的估驗)"""
        for task in self:
            approved_lines = task.estimate_line_ids.filtered(
                lambda l: l.estimate_id.state == 'approved')
            task.actual_qty = sum(approved_lines.mapped('current_qty'))
            task.actual_amount = task.actual_qty * task.unit_price

            if task.planned_amount:
                task.completion_rate = (task.actual_amount / task.planned_amount) * 100
                if task.completion_rate < 95:
                    task.budget_status = 'under'
                elif task.completion_rate <= 100:
                    task.budget_status = 'on_budget'
                else:
                    task.budget_status = 'over'
            else:
                task.completion_rate = 0.0
                task.budget_status = False

    # === 時間計畫欄位 (v5.2 - 參考 project_timeline) ===
    planned_date_start = fields.Datetime(
        '預定開始時間', compute='_compute_planned_date_start',
        store=True, readonly=False, precompute=True,
        help='工項預定開始時間 (Timeline 視圖用)')
    planned_date_end = fields.Datetime(
        '預定完成時間', compute='_compute_planned_date_end',
        store=True, readonly=False, precompute=True,
        help='工項預定完成時間 (Timeline 視圖用)')

    @api.depends('date_assign')
    def _compute_planned_date_start(self):
        """如未設定預定開始時間，以分配日期為預設值"""
        for task in self.filtered(lambda x: not x.planned_date_start and x.date_assign):
            if not task.planned_date_end or task.planned_date_end >= task.date_assign:
                task.planned_date_start = task.date_assign

    @api.depends('date_end')
    def _compute_planned_date_end(self):
        """如未設定預定完成時間，以結束日期為預設值"""
        for task in self.filtered(lambda x: not x.planned_date_end and x.date_end):
            if not task.planned_date_start or task.planned_date_start <= task.date_end:
                task.planned_date_end = task.date_end

    @api.constrains('planned_date_start', 'planned_date_end')
    def _check_planned_dates(self):
        """預定完成時間必須晚於預定開始時間"""
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                if task.planned_date_end < task.planned_date_start:
                    raise ValidationError('預定完成時間必須晚於預定開始時間')

    # === 實際執行時間 (v5.2 - 參考 project_timesheet_time_control) ===
    actual_date_start = fields.Datetime('實際開始時間', tracking=True)
    actual_date_end = fields.Datetime('實際完成時間', tracking=True)
    actual_duration = fields.Float(
        '實際工期(小時)', compute='_compute_actual_duration', store=True)

    @api.depends('actual_date_start', 'actual_date_end')
    def _compute_actual_duration(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                delta = task.actual_date_end - task.actual_date_start
                task.actual_duration = delta.total_seconds() / 3600
            else:
                task.actual_duration = 0.0

    # === 時間控制 (v5.2 - 參考 hr.timesheet.time_control.mixin) ===
    show_time_control = fields.Selection(
        [('start', '開始'), ('stop', '停止')],
        compute='_compute_show_time_control',
        help='顯示時間控制按鈕類型')

    @api.model
    def _relation_with_timesheet_line(self):
        """與工時記錄的關聯欄位"""
        return 'task_id'

    def button_start_work(self):
        """開始施工計時"""
        self.ensure_one()
        if not self.actual_date_start:
            self.actual_date_start = fields.Datetime.now()
        return {
            'context': {'default_task_id': self.id, 'default_project_id': self.project_id.id},
            'name': '開始施工',
            'res_model': 'hr.timesheet.switch',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
        }

    def button_end_work(self):
        """結束施工計時"""
        self.ensure_one()
        self.actual_date_end = fields.Datetime.now()
        # 結束 running timesheet lines
        running_lines = self.env['account.analytic.line'].search([
            ('task_id', '=', self.id),
            ('unit_amount', '=', 0),
            ('date_time', '!=', False),
        ])
        return running_lines.button_end_work()

    # === 時程對比分析 (v5.2) ===
    schedule_variance = fields.Float(
        '時程差異(天)', compute='_compute_schedule_variance', store=True,
        help='負值=超前, 正值=落後')
    schedule_status = fields.Selection([
        ('ahead', '超前'),
        ('on_schedule', '正常'),
        ('delayed', '落後'),
    ], string='時程狀態', compute='_compute_schedule_variance', store=True)

    @api.depends('planned_date_end', 'actual_date_end', 'assignment_state')
    def _compute_schedule_variance(self):
        """計算時程差異 (實際完成日 vs 預定完成日)"""
        for task in self:
            if task.planned_date_end and task.actual_date_end:
                delta = (task.actual_date_end - task.planned_date_end).days
                task.schedule_variance = delta
                if delta < -1:
                    task.schedule_status = 'ahead'
                elif delta <= 1:
                    task.schedule_status = 'on_schedule'
                else:
                    task.schedule_status = 'delayed'
            elif task.planned_date_end and task.assignment_state == 'in_progress':
                # 執行中：與今天比較
                today = fields.Datetime.now()
                delta = (today - task.planned_date_end).days
                task.schedule_variance = delta if delta > 0 else 0
                task.schedule_status = 'delayed' if delta > 0 else 'on_schedule'
            else:
                task.schedule_variance = 0.0
                task.schedule_status = False

    # === 契約變更關聯 (v5.2) ===
    change_order_id = fields.Many2one(
        'contract.change.order', '契約變更單',
        help='此工項由哪次契約變更新增/修改')

    # === 估驗明細關聯 ===
    estimate_line_ids = fields.One2many(
        'payment.estimate.line', 'task_id', '估驗明細',
        help='此工項的所有估驗記錄')

    # === 狀態追蹤 ===
    assignment_state = fields.Selection([
        ('unassigned', '未分配'),
        ('assigned', '已分配'),
        ('in_progress', '執行中'),
        ('completed', '已完成'),
        ('accepted', '已驗收'),
    ], string='分配狀態', default='unassigned', compute='_compute_assignment_state', store=True)

    @api.depends('assigned_company_id', 'stage_id')
    def _compute_assignment_state(self):
        for task in self:
            if not task.assigned_company_id:
                task.assignment_state = 'unassigned'
            elif task.stage_id.is_closed:
                task.assignment_state = 'accepted'
            elif task.stage_id.name == '已完成':
                task.assignment_state = 'completed'
            elif task.stage_id.name == '進行中':
                task.assignment_state = 'in_progress'
            else:
                task.assignment_state = 'assigned'

    def action_assign_to_contractor(self, company_id):
        """分配工項給廠商"""
        self.ensure_one()
        self.write({
            'assigned_company_id': company_id,
            'assignment_date': fields.Date.today(),
            'assigned_by_id': self.env.uid,
        })

    @api.constrains('assigned_company_id')
    def _check_contractor_in_project(self):
        """驗證分配的廠商必須在專案承包廠商列表中"""
        for task in self:
            if task.assigned_company_id:
                project = task.project_id.supervision_project_id
                if project and task.assigned_company_id not in project.contractor_company_ids:
                    raise ValidationError(
                        f'廠商 {task.assigned_company_id.name} 不在此專案的承包廠商列表中')
```

### 4.3 文件管理 (supervision_document)

```python
class SupervisionDocument(models.Model):
    _name = 'supervision.document'
    _description = '工程文件'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('文件名稱', required=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)
    
    # 文件分類
    document_type = fields.Selection([
        # 開工文件
        ('personnel_list', '工地人員名冊'),
        ('schedule', '工程預定進度表'),
        ('waste_plan', '剩餘資源處理計畫書'),
        ('construction_plan', '施工計畫書'),
        ('quality_plan', '品質計畫書'),
        ('safety_plan', '職業安全衛生管理計畫書'),
        ('insurance', '工程保險'),
        ('material_approval', '材料設備送審'),
        # 施工文件
        ('daily_log', '施工日誌'),
        ('supervision_report', '監造報表'),
        ('test_report', '試驗報告'),
        ('inspection_record', '檢驗紀錄'),
        # 竣工文件
        ('completion_drawing', '竣工圖'),
        ('completion_settlement', '竣工結算'),
        ('supervision_final_report', '監造報告書'),
        # 其他
        ('meeting_minutes', '會議紀錄'),
        ('correspondence', '往來函文'),
        ('other', '其他'),
    ], required=True)
    
    document_category = fields.Selection([
        ('pre_construction', '施工前'),
        ('construction', '施工中'),
        ('completion', '竣工'),
        ('acceptance', '驗收'),
    ], compute='_compute_category', store=True)
    
    # 版本控制
    version = fields.Integer('版本', default=1)
    parent_id = fields.Many2one('supervision.document', '前一版本')
    child_ids = fields.One2many('supervision.document', 'parent_id', '後續版本')
    is_current = fields.Boolean('當前版本', default=True)
    
    # 附件
    attachment_ids = fields.Many2many('ir.attachment', string='附件檔案')
    
    # 簽核追蹤
    submitter_id = fields.Many2one('res.users', '提送者')
    submit_date = fields.Datetime('提送時間')
    reviewer_id = fields.Many2one('res.users', '審查者')
    review_date = fields.Datetime('審查時間')
    approver_id = fields.Many2one('res.users', '核定者')
    approve_date = fields.Datetime('核定時間')
    
    # 審查意見
    review_comment_ids = fields.One2many('supervision.review.comment', 'document_id')
    
    # 狀態
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('revision', '補正中'),
        ('recommended', '建議核定'),
        ('approved', '已核定'),
        ('rejected', '退件'),
    ], default='draft', tracking=True)
    
    is_locked = fields.Boolean('已鎖定', default=False)
    
    # === 動作 ===
    def action_submit(self):
        """提送文件"""
        self.write({
            'state': 'submitted',
            'submitter_id': self.env.uid,
            'submit_date': fields.Datetime.now(),
        })
    
    def action_review(self):
        """開始審查"""
        self.write({
            'state': 'reviewing',
            'reviewer_id': self.env.uid,
        })
    
    def action_request_revision(self):
        """退回補正"""
        self.write({'state': 'revision'})
        # 建立新版本
        new_version = self.copy({
            'version': self.version + 1,
            'parent_id': self.id,
            'state': 'draft',
            'is_current': True,
        })
        self.is_current = False
        return new_version
    
    def action_recommend(self):
        """建議核定"""
        self.write({
            'state': 'recommended',
            'review_date': fields.Datetime.now(),
        })
    
    def action_approve(self):
        """核定"""
        self.write({
            'state': 'approved',
            'approver_id': self.env.uid,
            'approve_date': fields.Datetime.now(),
            'is_locked': True,
        })
```

### 4.4 通報單管理 (reservation_notification_slip) - 預約式專用

> **適用範圍**: 僅預約式工程使用
>
> **預算追蹤** (v5.1): 預約式工程的預算以「工程範疇量預估」為基礎
> - estimated_amount (預估金額) = 預算 (planned_amount)
> - settlement_amount (結算金額) = 實際 (actual_amount)
> - 參考 account_budget_oca 設計模式

通報單是預約式工程的核心管理單位，每張通報單代表一個施工地點/批次，包含獨立的工期、預算、自主檢查及缺失改善。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    預約式工程預算追蹤 (v5.1)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  工程標案 (主契約)                                                        │
│  └── 工程範疇量預估 (scope_estimate)                                     │
│       ├── 項目 A: planned_qty × unit_price → planned_amount (預算)      │
│       ├── 項目 B: planned_qty × unit_price → planned_amount (預算)      │
│       └── ...                                                           │
│                                                                          │
│  通報單 (實際執行)                                                        │
│  └── 通報單明細 (slip_line)                                              │
│       ├── 項目 A: actual_qty × unit_price → actual_amount (實際)        │
│       ├── 項目 B: actual_qty × unit_price → actual_amount (實際)        │
│       └── ...                                                           │
│                                                                          │
│  彙總: 各通報單 actual_amount → 與 scope_estimate planned_amount 對比   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**通報單狀態流程圖** (參考 work.acceptance 設計):
```
┌─────────────────────────────────────────────────────────────────────┐
│                         通報單生命週期                               │
│                                                                      │
│  ┌────────┐    提交     ┌────────┐    驗收    ┌────────┐           │
│  │  草稿   │───────────▶│  執行中 │──────────▶│ 已驗收  │           │
│  │ draft  │            │in_progress│         │ accepted│           │
│  └────────┘            └────────┘           └────────┘           │
│       │                     │                    │                  │
│       │       取消          │      取消          │                  │
│       └──────────┬─────────┴────────────────────┘                  │
│                  ▼                                                  │
│            ┌────────┐                                              │
│            │  取消   │                                              │
│            │ cancel │                                              │
│            └────────┘                                              │
└─────────────────────────────────────────────────────────────────────┘
```

```python
class ReservationNotificationSlip(models.Model):
    """
    通報單 (預約式專用)

    設計特點:
    - 狀態機制與驗收流程
    - 數量追蹤與驗證約束
    """
    _name = 'reservation.notification.slip'
    _description = '通報單 (預約式專用)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'slip_no asc'

    # === 基本資料 ===
    name = fields.Char('通報單名稱', compute='_compute_name', store=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True,
                                  domain=[('project_type', '=', 'reservation')])
    slip_no = fields.Integer('通報單次', required=True)

    # 編製資訊
    compiler_id = fields.Many2one('res.users', '編製人員')
    location = fields.Char('工程地點', required=True)

    # === 日期與工期 ===
    survey_date = fields.Date('工程會勘日期')
    planned_start_date = fields.Date('預定開工日期')
    planned_end_date = fields.Date('預定完工日期', compute='_compute_planned_end_date', store=True)
    planned_duration = fields.Integer('預定工期(日曆天)')
    actual_start_date = fields.Date('實際開工日期')
    actual_end_date = fields.Date('實際竣工日期')
    actual_duration = fields.Integer('實際使用工期', compute='_compute_actual_duration')
    overdue_days = fields.Integer('逾期天數', compute='_compute_overdue_days')
    proposal_countdown = fields.Integer('提案結束天數倒數', compute='_compute_countdown')

    # === 預算與結算 (v5.1) ===
    # 參考 account_budget_oca: planned_amount vs practical_amount
    estimated_amount = fields.Float(
        '預估金額 (預算)',
        help='本通報單的預算金額，參考工程範疇量預估')
    settlement_amount = fields.Float(
        '結算金額 (實際)', compute='_compute_settlement_amount', store=True,
        help='本通報單的實際結算金額，由明細彙總')
    budget_variance = fields.Float(
        '預算差異', compute='_compute_settlement_amount', store=True,
        help='settlement_amount - estimated_amount')
    budget_variance_rate = fields.Float(
        '差異率 (%)', compute='_compute_settlement_amount', store=True,
        help='(settlement_amount / estimated_amount - 1) × 100')

    @api.depends('detail_line_ids.actual_amount')
    def _compute_settlement_amount(self):
        for slip in self:
            slip.settlement_amount = sum(slip.detail_line_ids.mapped('actual_amount'))
            slip.budget_variance = slip.settlement_amount - slip.estimated_amount
            if slip.estimated_amount:
                slip.budget_variance_rate = (slip.settlement_amount / slip.estimated_amount - 1) * 100
            else:
                slip.budget_variance_rate = 0.0

    design_summary = fields.Text('設計概述')
    completion_summary = fields.Text('完工概述')

    # === 狀態 (參考 work.acceptance 三態設計) ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('in_progress', '執行中'),
        ('accepted', '已驗收'),
        ('cancel', '取消'),
    ], string='通報單狀態', default='draft', tracking=True,
       help='參考 work.acceptance: draft → accept → cancel')

    work_status = fields.Selection([
        ('pending', '待施工'),
        ('working', '施工中'),
        ('completed', '已竣工'),
        ('accepted', '已驗收'),
    ], string='施作狀態', compute='_compute_work_status')

    # === 驗收數量追蹤 (參考 work.acceptance qty 設計) ===
    acceptance_id = fields.Many2one('notification.acceptance', '驗收單',
                                     help='關聯的驗收單據')

    # === 詳細表項目關聯 ===
    detail_line_ids = fields.One2many('reservation.notification.slip.line', 'slip_id', '詳細表項目')

    # === 子功能關聯 ===
    daily_log_sheet_ids = fields.One2many('daily.log.sheet', 'notification_slip_id', '施工日誌表單')
    inspection_ids = fields.One2many('reservation.self.inspection', 'slip_id', '自主檢查')
    defect_ids = fields.One2many('reservation.defect.improvement', 'slip_id', '缺失改善')
    estimate_count = fields.Integer('已估驗次數', compute='_compute_estimate_count')

    @api.depends('slip_no', 'location')
    def _compute_name(self):
        for rec in self:
            rec.name = f'第{rec.slip_no}次通報單 - {rec.location or ""}'

    @api.depends('planned_start_date', 'planned_duration')
    def _compute_planned_end_date(self):
        for rec in self:
            if rec.planned_start_date and rec.planned_duration:
                rec.planned_end_date = rec.planned_start_date + timedelta(days=rec.planned_duration)
            else:
                rec.planned_end_date = False

    # === 動作方法 (參考 work.acceptance) ===
    def action_submit(self):
        """提交通報單，進入執行中狀態"""
        for rec in self:
            if not rec.detail_line_ids:
                raise ValidationError('請先填寫詳細表項目')
            rec.write({'state': 'in_progress'})

    def action_accept(self):
        """驗收通報單"""
        for rec in self:
            # 驗證：所有工作項目都已完成
            if any(line.qty_remaining > 0 for line in rec.detail_line_ids):
                raise ValidationError('尚有未完成的工作項目')
            rec.write({'state': 'accepted'})

    def action_cancel(self):
        """取消通報單"""
        for rec in self:
            if rec.state == 'accepted':
                raise ValidationError('已驗收的通報單無法取消')
            rec.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """重設為草稿 (僅限取消狀態)"""
        for rec in self:
            if rec.state != 'cancel':
                raise ValidationError('僅取消狀態可重設為草稿')
            rec.write({'state': 'draft'})


class ReservationNotificationSlipLine(models.Model):
    """
    通報單詳細表項目

    設計說明 (v5.1): 預算 vs 實際追蹤
    - estimated_qty/estimated_amount = 預算 (planned)
    - actual_qty/actual_amount = 實際執行
    - 參考 account_budget_oca 設計模式
    """
    _name = 'reservation.notification.slip.line'
    _description = '通報單詳細表項目'

    slip_id = fields.Many2one('reservation.notification.slip', '通報單', required=True, ondelete='cascade')

    # === 工項關聯 (v5.1) ===
    scope_item_id = fields.Many2one(
        'project.task', '範疇項目',
        domain="[('project_id.supervision_project_id', '=', parent.project_id)]",
        help='關聯工程範疇量預估的項目')

    # 從範疇項目帶出
    item_no = fields.Char('項次', related='scope_item_id.item_no', store=True)
    description = fields.Char('項目說明', related='scope_item_id.name', store=True)
    unit = fields.Char('單位', related='scope_item_id.unit', store=True)
    unit_price = fields.Float('單價', related='scope_item_id.unit_price', store=True)

    # === 預算欄位 (預估需求) ===
    # 參考 account_budget_oca: planned_amount
    planned_qty = fields.Float('預估數量 (預算)')
    planned_amount = fields.Float(
        '預估金額 (預算)', compute='_compute_planned_amount', store=True)

    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        for line in self:
            line.planned_amount = line.planned_qty * line.unit_price

    # === 實際執行欄位 ===
    # 參考 account_budget_oca: practical_amount
    actual_qty = fields.Float('實際完成數量')
    actual_amount = fields.Float(
        '實際金額', compute='_compute_actual_amount', store=True)

    @api.depends('actual_qty', 'unit_price')
    def _compute_actual_amount(self):
        for line in self:
            line.actual_amount = line.actual_qty * line.unit_price

    # === 對比分析 ===
    completion_rate = fields.Float(
        '完成率 (%)', compute='_compute_variance', store=True)
    variance = fields.Float(
        '差異金額', compute='_compute_variance', store=True)

    @api.depends('planned_amount', 'actual_amount')
    def _compute_variance(self):
        for line in self:
            line.variance = line.actual_amount - line.planned_amount
            if line.planned_amount:
                line.completion_rate = (line.actual_amount / line.planned_amount) * 100
            else:
                line.completion_rate = 0.0

    # === 驗收追蹤 ===
    qty_accepted = fields.Float('已驗收數量', default=0.0)
    qty_remaining = fields.Float(
        '待驗收數量', compute='_compute_acceptance', store=True)

    @api.depends('actual_qty', 'qty_accepted')
    def _compute_acceptance(self):
        for line in self:
            line.qty_remaining = line.actual_qty - line.qty_accepted

    @api.constrains('qty_accepted', 'actual_qty')
    def _check_qty_accepted(self):
        """驗證約束：驗收數量不得超過實際完成數量"""
        for rec in self:
            if rec.qty_accepted > rec.actual_qty:
                raise ValidationError(
                    f'項目 {rec.item_no}: 驗收數量 ({rec.qty_accepted}) '
                    f'不得超過實際完成數量 ({rec.actual_qty})'
                )
```

#### 4.4.1 預約式自主檢查 (通報單內)

```python
class ReservationSelfInspection(models.Model):
    _name = 'reservation.self.inspection'
    _description = '預約式自主檢查 (通報單內)'
    _inherit = ['mail.thread']

    slip_id = fields.Many2one('reservation.notification.slip', '所屬通報單', required=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', related='slip_id.project_id', store=True)

    # 檢查資訊
    inspection_no = fields.Char('編號')
    inspection_type_id = fields.Many2one('self.inspection.type', '自主檢查類型', required=True)
    sub_project_name = fields.Char('分項工程名稱')
    inspection_date = fields.Date('檢查日期', required=True)
    inspection_location = fields.Char('檢查位置')

    # 廠商資訊
    contractor_name = fields.Char('承攬廠商')
    subcontractor_name = fields.Char('協力廠商')

    # 檢查時機
    inspection_timing = fields.Selection([
        ('hold_point', '查驗停留點'),
        ('before', '施工前檢查'),
        ('during', '施工中檢查'),
        ('after', '施工完成檢查'),
    ], string='檢查時機')

    # 檢查結果
    inspector_id = fields.Many2one('res.users', '填表人', default=lambda self: self.env.uid)
    photo_ids = fields.Many2many('ir.attachment', string='檢查照片')
    has_defect = fields.Boolean('是否有缺失', default=False)

    # 檢查項目
    checklist_ids = fields.One2many('reservation.self.inspection.item', 'inspection_id', '檢查項目')


class ReservationSelfInspectionItem(models.Model):
    _name = 'reservation.self.inspection.item'
    _description = '預約式自主檢查項目'

    inspection_id = fields.Many2one('reservation.self.inspection', '自主檢查', required=True, ondelete='cascade')
    stage = fields.Selection([
        ('stage1', '第一查驗階段'),
        ('stage2', '第二查驗階段'),
        ('stage3', '第三查驗階段'),
    ], string='查驗階段')

    check_item = fields.Char('檢查項目')
    design_standard = fields.Text('設計圖說、規範之管理標準(定性定量)')
    actual_result = fields.Text('實際檢查情形')
    check_result = fields.Selection([
        ('pass', '檢查合格'),
        ('defect', '有缺失需改正'),
        ('na', '無此項目'),
    ], string='檢查成果')
    note = fields.Text('備註')
```

#### 4.4.2 預約式缺失改善 (通報單內)

```python
class ReservationDefectImprovement(models.Model):
    _name = 'reservation.defect.improvement'
    _description = '預約式缺失改善 (通報單內)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    slip_id = fields.Many2one('reservation.notification.slip', '所屬通報單', required=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', related='slip_id.project_id', store=True)

    # 基本資訊
    record_no = fields.Char('紀錄表編號', required=True)
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety_env', '安衛及環境清潔檢查'),
    ], string='檢查類型', required=True)

    # 單位資訊
    discovery_unit = fields.Char('發現單位')
    improvement_unit = fields.Char('執行改善單位')

    # 日期
    notification_date = fields.Date('通知改善日期')
    deadline = fields.Date('限定完成改善日期')
    closure_date = fields.Date('結案日期')

    # 缺失內容
    defect_description = fields.Text('缺失具體情形', required=True)
    defect_cause = fields.Text('缺失發生原因')
    improvement_action = fields.Text('矯正措施')
    prevention_action = fields.Text('預防措施')

    # 照片
    defect_photo_ids = fields.Many2many('ir.attachment', 'defect_photo_rel', string='缺失照片')
    improvement_photo_ids = fields.Many2many('ir.attachment', 'improvement_photo_rel', string='改善後照片')

    # 確認
    confirmer_id = fields.Many2one('res.users', '確認人')
    confirm_date = fields.Date('確認日期')

    # 狀態 (監造視角)
    state = fields.Selection([
        ('conform', '符合要求'),
        ('corrected', '已矯正'),
        ('uncorrected', '未矯正'),
        ('overdue', '逾時未矯正'),
        ('other', '其他'),
    ], string='缺失狀態', default='uncorrected', tracking=True)

    # 編號前綴設定
    supervision_prefix = fields.Char('監造編號前綴')
    contractor_prefix = fields.Char('營造編號前綴')
```

#### 4.4.3 通報單驗收 (notification_acceptance) - 預約式專用

> **設計說明**: 獨立設計的工作驗收流程，不依賴 purchase 模組

```python
class NotificationAcceptance(models.Model):
    """
    通報單驗收單

    設計特點:
    - 狀態機制: draft → accept → cancel
    - 數量追蹤與驗證
    - 驗收與發票整合
    """
    _name = 'notification.acceptance'
    _description = '通報單驗收單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # === 基本資料 ===
    name = fields.Char('驗收單號', required=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('notification.acceptance'))
    slip_id = fields.Many2one('reservation.notification.slip', '通報單', required=True,
                               domain=[('state', '=', 'in_progress')])
    project_id = fields.Many2one('supervision.project', '所屬工程',
                                  related='slip_id.project_id', store=True)

    # === 驗收資訊 ===
    acceptance_date = fields.Date('驗收日期', required=True, default=fields.Date.today)
    acceptance_type = fields.Selection([
        ('preliminary', '初驗'),
        ('final', '正驗'),
        ('partial', '部分驗收'),
    ], string='驗收類型', required=True, default='final')

    # === 驗收人員 ===
    acceptor_id = fields.Many2one('res.users', '驗收人員', default=lambda self: self.env.uid)
    witness_ids = fields.Many2many('res.users', string='會同人員')

    # === 驗收明細 (參考 work.acceptance) ===
    line_ids = fields.One2many('notification.acceptance.line', 'acceptance_id', '驗收明細')

    # === 金額彙總 ===
    total_accepted_amount = fields.Float('驗收總金額', compute='_compute_totals', store=True)

    # === 驗收結果 ===
    has_defect = fields.Boolean('是否有缺失', default=False)
    defect_description = fields.Text('缺失說明')
    defect_ids = fields.One2many('reservation.defect.improvement', 'acceptance_id', '驗收缺失')

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='驗收資料')
    photo_ids = fields.Many2many('ir.attachment', 'acceptance_photo_rel', string='驗收照片')

    # === 狀態 (參考 work.acceptance 三態設計) ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('accept', '已驗收'),
        ('cancel', '取消'),
    ], string='狀態', default='draft', tracking=True,
       help='參考 work.acceptance 狀態設計')

    @api.depends('line_ids.accepted_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_accepted_amount = sum(rec.line_ids.mapped('accepted_amount'))

    # === 動作方法 (參考 work.acceptance) ===
    def action_accept(self):
        """確認驗收"""
        for rec in self:
            if not rec.line_ids:
                raise ValidationError('請先填寫驗收明細')
            # 更新通報單明細的 qty_accepted
            for line in rec.line_ids:
                if line.slip_line_id:
                    line.slip_line_id.qty_accepted += line.qty_accepted
            # 更新通報單狀態
            if all(sl.qty_remaining <= 0 for sl in rec.slip_id.detail_line_ids):
                rec.slip_id.write({
                    'state': 'accepted',
                    'acceptance_id': rec.id,
                })
            rec.write({'state': 'accept'})

    def action_cancel(self):
        """取消驗收"""
        for rec in self:
            if rec.state != 'draft':
                # 回退 qty_accepted
                for line in rec.line_ids:
                    if line.slip_line_id:
                        line.slip_line_id.qty_accepted -= line.qty_accepted
            rec.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """重設為草稿"""
        self.write({'state': 'draft'})


class NotificationAcceptanceLine(models.Model):
    """
    通報單驗收明細

    設計參考: work.acceptance 數量追蹤
    """
    _name = 'notification.acceptance.line'
    _description = '通報單驗收明細'

    acceptance_id = fields.Many2one('notification.acceptance', '驗收單', required=True, ondelete='cascade')
    slip_line_id = fields.Many2one('reservation.notification.slip.line', '通報單項目', required=True)

    # 關聯欄位
    item_no = fields.Char('項次', related='slip_line_id.item_no')
    description = fields.Char('項目說明', related='slip_line_id.description')
    unit = fields.Char('單位', related='slip_line_id.unit')
    unit_price = fields.Float('單價', related='slip_line_id.unit_price')

    # === 數量追蹤 (參考 work.acceptance) ===
    qty_to_accept = fields.Float('待驗收數量', related='slip_line_id.qty_remaining')
    qty_accepted = fields.Float('本次驗收數量', required=True)
    accepted_amount = fields.Float('驗收金額', compute='_compute_amount', store=True)

    # 驗收結果
    acceptance_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '條件式合格'),
        ('fail', '不合格'),
    ], string='驗收結果', default='pass')
    note = fields.Text('備註')

    @api.depends('qty_accepted', 'unit_price')
    def _compute_amount(self):
        for rec in self:
            rec.accepted_amount = rec.qty_accepted * rec.unit_price

    @api.constrains('qty_accepted', 'qty_to_accept')
    def _check_qty(self):
        """驗證約束 (參考 work.acceptance)"""
        for rec in self:
            if rec.qty_accepted > rec.qty_to_accept:
                raise ValidationError(
                    f'項目 {rec.item_no}: 驗收數量 ({rec.qty_accepted}) '
                    f'不得超過待驗收數量 ({rec.qty_to_accept})'
                )
            if rec.qty_accepted < 0:
                raise ValidationError('驗收數量不得為負數')
```

### 4.5 缺失管理 (supervision_defect) - 一般式專用

```python
class SupervisionDefect(models.Model):
    _name = 'supervision.defect'
    _description = '缺失管理 (NCR)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('缺失編號', required=True, copy=False, 
                       default=lambda self: self.env['ir.sequence'].next_by_code('supervision.defect'))
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)
    
    # 缺失來源
    source = fields.Selection([
        ('inspection', '抽查發現'),
        ('daily_check', '日常檢查'),
        ('preliminary_acceptance', '初驗'),
        ('final_acceptance', '正驗'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ])
    source_reference = fields.Reference([
        ('supervision.inspection', '抽查紀錄'),
        ('project.acceptance', '驗收紀錄'),
    ], '來源單據')
    
    # 缺失內容
    defect_type = fields.Selection([
        ('quality', '品質缺失'),
        ('safety', '安全缺失'),
        ('environmental', '環境缺失'),
        ('schedule', '進度缺失'),
        ('documentation', '文件缺失'),
    ])
    severity = fields.Selection([
        ('minor', '輕微'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ])
    description = fields.Text('缺失說明', required=True)
    location = fields.Char('發生位置')
    found_date = fields.Date('發現日期', default=fields.Date.today)
    
    # 責任
    responsible_party = fields.Selection([
        ('contractor', '施工廠商'),
        ('subcontractor', '分包商'),
        ('supplier', '供應商'),
    ])
    responsible_user_id = fields.Many2one('res.users', '負責人')
    deadline = fields.Date('改善期限')
    
    # 開立者
    issuer_id = fields.Many2one('res.users', '開立者', default=lambda self: self.env.uid)
    issue_date = fields.Datetime('開立時間', default=fields.Datetime.now)
    
    # 改善
    improvement_description = fields.Text('改善說明')
    improvement_date = fields.Datetime('改善時間')
    
    # 照片
    before_photo_ids = fields.Many2many('ir.attachment', 'defect_before_rel', string='改善前照片')
    after_photo_ids = fields.Many2many('ir.attachment', 'defect_after_rel', string='改善後照片')
    
    # 確認
    confirmer_id = fields.Many2one('res.users', '確認者')
    confirm_date = fields.Datetime('確認時間')
    confirm_comment = fields.Text('確認意見')
    
    # 狀態
    state = fields.Selection([
        ('open', '待改善'),
        ('improving', '改善中'),
        ('submitted', '待確認'),
        ('confirmed', '已確認'),
        ('closed', '結案'),
        ('overdue', '逾期'),
    ], default='open', tracking=True)
    
    # 逾期檢查
    is_overdue = fields.Boolean('已逾期', compute='_compute_overdue')
    
    @api.depends('deadline', 'state')
    def _compute_overdue(self):
        for rec in self:
            if rec.state in ('open', 'improving') and rec.deadline:
                rec.is_overdue = rec.deadline < fields.Date.today()
            else:
                rec.is_overdue = False
```

### 4.6 估驗計價與請款 (payment_estimate / payment_claim)

> **設計說明** (v5.0): 不使用 purchase 模組，自訂估驗與請款流程
> - 估驗計價：監造審查施工成果後產生的估驗資料
> - 請款單：向業主（政府機關）請款的正式單據
> - 支援設計監造與施工廠商分別向業主請款

#### 4.6.1 估驗計價 (payment_estimate)

**估驗計價流程**:
```
┌─────────────────────────────────────────────────────────────────────┐
│                       估驗計價分期管理                               │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 第1期估驗│→ │ 第2期估驗│→ │ 第N期估驗│→ │ 尾款結算 │            │
│  │ Period 1 │  │ Period 2 │  │ Period N │  │  Final   │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│       ↓             ↓             ↓             ↓                   │
│  累計: 20%     累計: 50%     累計: 80%     累計: 100%              │
└─────────────────────────────────────────────────────────────────────┘
```

```python
class PaymentEstimate(models.Model):
    """
    估驗計價

    設計說明 (v5.0): 不依賴 purchase 模組，獨立設計
    - 分期估驗計畫與累計追蹤
    - 施工廠商提交，監造審查
    """
    _name = 'payment.estimate'
    _description = '估驗計價'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'estimate_no asc'

    name = fields.Char('估驗期次', required=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company', '提送公司', required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'contractor')]",
        help='提送此估驗的施工廠商')

    # === 估驗期間 ===
    period_start = fields.Date('起始日期')
    period_end = fields.Date('截止日期')
    estimate_no = fields.Integer('期次', required=True)
    is_final = fields.Boolean('是否為尾款', default=False)

    # === 關聯驗收單 ===
    acceptance_ids = fields.Many2many('work.acceptance', string='關聯驗收單',
                                       help='此次估驗涵蓋的驗收單')

    # === 金額 ===
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # 計價項目
    line_ids = fields.One2many('payment.estimate.line', 'estimate_id', '計價明細')

    # === 合計 (參考 invoice_plan 累計設計) ===
    subtotal = fields.Monetary('本期估驗金額', compute='_compute_totals', store=True)
    cumulative_amount = fields.Monetary('累計估驗金額', compute='_compute_totals', store=True)
    contract_total = fields.Monetary('契約總價', related='project_id.contract_amount')
    completion_rate = fields.Float('估驗進度 (%)', compute='_compute_totals', store=True,
                                    help='累計估驗金額 / 契約總價')
    retention = fields.Monetary('保留款', compute='_compute_totals', store=True)
    retention_rate = fields.Float('保留款比例 (%)', default=5.0)
    payable_amount = fields.Monetary('應付金額', compute='_compute_totals', store=True)

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='佐證資料')

    # === 簽核 ===
    submitter_id = fields.Many2one('res.users', '提送者')
    submit_date = fields.Datetime('提送日期')
    reviewer_id = fields.Many2one('res.users', '審查者')
    review_date = fields.Datetime('審查日期')
    review_comment = fields.Text('審查意見')
    approver_id = fields.Many2one('res.users', '核定者')
    approve_date = fields.Datetime('核定日期')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('revision', '補正'),
        ('recommended', '建議核定'),
        ('approved', '已核定'),
        ('paid', '已撥付'),
    ], default='draft', tracking=True)

    @api.depends('line_ids.current_amount', 'line_ids.cumulative_amount', 'retention_rate', 'contract_total')
    def _compute_totals(self):
        """計算合計 (參考 invoice_plan)"""
        for rec in self:
            rec.subtotal = sum(rec.line_ids.mapped('current_amount'))
            rec.cumulative_amount = sum(rec.line_ids.mapped('cumulative_amount'))
            rec.retention = rec.subtotal * (rec.retention_rate / 100)
            rec.payable_amount = rec.subtotal - rec.retention
            if rec.contract_total:
                rec.completion_rate = (rec.cumulative_amount / rec.contract_total) * 100
            else:
                rec.completion_rate = 0.0

    @api.constrains('estimate_no')
    def _check_estimate_no(self):
        """驗證期次連續性"""
        for rec in self:
            prev_count = self.search_count([
                ('project_id', '=', rec.project_id.id),
                ('estimate_no', '<', rec.estimate_no),
                ('state', '!=', 'draft'),
            ])
            if rec.estimate_no > 1 and prev_count < rec.estimate_no - 1:
                raise ValidationError('估驗期次必須連續，請先完成前期估驗')


class PaymentEstimateLine(models.Model):
    """
    估驗計價明細

    設計說明 (v5.1):
    - 關聯契約工項 (task_id) 用於預算追蹤
    - 實際完成數量 → 用於計算 task 的 actual_qty
    - 契約數量/單價來自工項的預算欄位
    """
    _name = 'payment.estimate.line'
    _description = '估驗計價明細'

    estimate_id = fields.Many2one('payment.estimate', '估驗單', required=True, ondelete='cascade')

    # === 工項關聯 (v5.1) ===
    task_id = fields.Many2one(
        'project.task', '契約工項', required=True,
        domain="[('assigned_company_id', '=', parent.company_id)]",
        help='關聯契約工項，用於預算 vs 實際追蹤')

    # 從工項帶出 (預算資料)
    item_no = fields.Char('項次', related='task_id.item_no', store=True)
    description = fields.Char('項目說明', related='task_id.name', store=True)
    unit = fields.Char('單位', related='task_id.unit', store=True)

    # === 預算欄位 (從工項帶出) ===
    planned_qty = fields.Float('契約數量', related='task_id.planned_qty',
                                help='契約預算數量')
    unit_price = fields.Float('契約單價', related='task_id.unit_price')
    planned_amount = fields.Float('契約金額', related='task_id.planned_amount',
                                   help='契約預算金額 (上限)')

    # === 實際完成欄位 ===
    previous_qty = fields.Float('前期累計數量')
    current_qty = fields.Float('本期完成數量', required=True,
                                help='本期實際完成數量')
    cumulative_qty = fields.Float('累計完成數量', compute='_compute_amounts', store=True)

    current_amount = fields.Float('本期金額', compute='_compute_amounts', store=True)
    cumulative_amount = fields.Float('累計金額', compute='_compute_amounts', store=True)

    # === 對比分析 ===
    completion_rate = fields.Float('完成率 (%)', compute='_compute_amounts', store=True,
                                    help='cumulative_amount / planned_amount × 100')
    over_budget = fields.Boolean('超出預算', compute='_compute_amounts', store=True)

    @api.depends('previous_qty', 'current_qty', 'unit_price', 'planned_amount')
    def _compute_amounts(self):
        for line in self:
            line.cumulative_qty = line.previous_qty + line.current_qty
            line.current_amount = line.current_qty * line.unit_price
            line.cumulative_amount = line.cumulative_qty * line.unit_price

            if line.planned_amount:
                line.completion_rate = (line.cumulative_amount / line.planned_amount) * 100
                line.over_budget = line.cumulative_amount > line.planned_amount
            else:
                line.completion_rate = 0.0
                line.over_budget = False

    @api.constrains('cumulative_qty', 'planned_qty')
    def _check_over_estimate(self):
        """警告：累計數量超過契約數量"""
        for line in self:
            if line.cumulative_qty > line.planned_qty:
                # 超估警告 (不阻擋，但記錄)
                line.message_post(
                    body=f'警告：累計估驗數量 ({line.cumulative_qty}) 超過契約數量 ({line.planned_qty})')
```

#### 4.6.2 工項驗收 (work_acceptance)

> **設計說明** (v5.0): 獨立設計驗收流程，不依賴 purchase 模組

```python
class WorkAcceptance(models.Model):
    """
    工項驗收單

    設計說明 (v5.0): 監造驗收施工廠商完成的工項
    - 驗收通過後，廠商可提交估驗計價
    - 支援部分驗收
    """
    _name = 'work.acceptance'
    _description = '工項驗收單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('驗收單號', required=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('work.acceptance'))
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)

    # === 多公司架構 (v5.0) ===
    contractor_company_id = fields.Many2one(
        'res.company', '施工廠商', required=True,
        domain="[('company_type', '=', 'contractor')]",
        help='被驗收的施工廠商')

    # === 驗收資訊 ===
    acceptance_date = fields.Date('驗收日期', required=True, default=fields.Date.today)
    acceptance_type = fields.Selection([
        ('partial', '部分驗收'),
        ('final', '完工驗收'),
    ], string='驗收類型', required=True, default='partial')

    # === 驗收人員 (監造單位) ===
    acceptor_id = fields.Many2one('res.users', '驗收人員',
                                   default=lambda self: self.env.uid,
                                   domain="[('company_id.company_type', '=', 'supervision')]")

    # === 驗收明細 ===
    line_ids = fields.One2many('work.acceptance.line', 'acceptance_id', '驗收明細')

    # === 驗收結果 ===
    has_defect = fields.Boolean('有缺失', compute='_compute_has_defect', store=True)
    defect_ids = fields.One2many('supervision.defect', 'acceptance_id', '驗收缺失')

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='驗收資料')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('inspecting', '檢驗中'),
        ('pending_fix', '待改善'),
        ('accepted', '已驗收'),
        ('rejected', '退回'),
    ], default='draft', tracking=True)

    # === 動作方法 ===
    def action_start_inspection(self):
        """開始檢驗"""
        self.write({'state': 'inspecting'})

    def action_accept(self):
        """驗收通過"""
        self._check_defects_resolved()
        self.write({'state': 'accepted'})
        # 更新工項狀態
        for line in self.line_ids:
            line.task_id.assignment_state = 'accepted'

    def action_request_fix(self):
        """要求改善"""
        self.write({'state': 'pending_fix'})

    def action_reject(self):
        """驗收退回"""
        self.write({'state': 'rejected'})


class WorkAcceptanceLine(models.Model):
    """工項驗收明細"""
    _name = 'work.acceptance.line'
    _description = '工項驗收明細'

    acceptance_id = fields.Many2one('work.acceptance', '驗收單', required=True, ondelete='cascade')
    task_id = fields.Many2one('project.task', '工項', required=True,
                              domain="[('assigned_company_id', '=', parent.contractor_company_id)]")

    # === 數量追蹤 ===
    contract_qty = fields.Float('契約數量')
    completed_qty = fields.Float('完成數量')
    accepted_qty = fields.Float('驗收數量')

    # === 驗收結果 ===
    acceptance_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '有條件合格'),
        ('fail', '不合格'),
    ], string='驗收結果', default='pass')
    note = fields.Text('備註')
```

#### 4.6.3 請款單 (payment_claim)

> **設計說明** (v5.0): 向業主（政府機關）請款的正式單據
> - 設計監造單位：請服務費
> - 施工廠商：請工程款
> - 請款對象統一為業主

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         請款流程架構 (v5.0)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────┐                    ┌───────────────────┐         │
│  │   設計監造單位     │                    │    施工廠商        │         │
│  │                   │                    │                   │         │
│  │  服務費請款單     │                    │  工程款請款單     │         │
│  │  claim_type =     │                    │  claim_type =     │         │
│  │  'service_fee'    │                    │  'construction'   │         │
│  │                   │                    │                   │         │
│  └─────────┬─────────┘                    └─────────┬─────────┘         │
│            │                                        │                   │
│            └────────────────┬───────────────────────┘                   │
│                             ▼                                           │
│                    ┌───────────────┐                                    │
│                    │   政府機關     │                                    │
│                    │   (業主)       │                                    │
│                    │               │                                    │
│                    │  接收請款單   │                                    │
│                    │  核准付款     │                                    │
│                    └───────────────┘                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

```python
class PaymentClaim(models.Model):
    """
    請款單

    設計說明 (v5.0):
    - 統一向業主（政府機關）請款
    - 支援服務費（監造）和工程款（廠商）兩種類型
    - 基於估驗計價或驗收單產生
    """
    _name = 'payment.claim'
    _description = '請款單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('請款單號', required=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('payment.claim'))
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company', '請款公司', required=True,
        default=lambda self: self.env.company,
        help='提出請款的公司（設計監造或施工廠商）')

    # === 請款類型 ===
    claim_type = fields.Selection([
        ('service_fee', '服務費'),      # 設計監造單位
        ('construction', '工程款'),     # 施工廠商
    ], string='請款類型', required=True,
       compute='_compute_claim_type', store=True, readonly=False)

    @api.depends('company_id')
    def _compute_claim_type(self):
        for claim in self:
            if claim.company_id.company_type == 'supervision':
                claim.claim_type = 'service_fee'
            else:
                claim.claim_type = 'construction'

    # === 請款對象 (業主) ===
    authority_id = fields.Many2one(
        'res.partner', '請款對象', required=True,
        related='project_id.authority_id', store=True,
        help='政府機關，為付款方')

    # === 請款基礎 ===
    estimate_ids = fields.Many2many(
        'payment.estimate', string='關聯估驗單',
        domain="[('company_id', '=', company_id), ('state', '=', 'approved')]",
        help='此請款單基於哪些已核定的估驗單')

    acceptance_ids = fields.Many2many(
        'work.acceptance', string='關聯驗收單',
        domain="[('contractor_company_id', '=', company_id), ('state', '=', 'accepted')]")

    # === 金額 ===
    currency_id = fields.Many2one('res.currency',
                                   default=lambda self: self.env.company.currency_id)
    claim_amount = fields.Monetary('請款金額', required=True)
    retention_amount = fields.Monetary('保留款', default=0.0)
    net_amount = fields.Monetary('實付金額', compute='_compute_net_amount', store=True)

    @api.depends('claim_amount', 'retention_amount')
    def _compute_net_amount(self):
        for claim in self:
            claim.net_amount = claim.claim_amount - claim.retention_amount

    # === 期次資訊 ===
    claim_period = fields.Integer('請款期次')
    period_start = fields.Date('起始日期')
    period_end = fields.Date('截止日期')

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='請款文件')
    invoice_number = fields.Char('發票號碼')
    invoice_date = fields.Date('發票日期')

    # === 簽核流程 ===
    submitter_id = fields.Many2one('res.users', '提送者')
    submit_date = fields.Datetime('提送日期')
    approver_id = fields.Many2one('res.users', '核准者')
    approve_date = fields.Datetime('核准日期')
    payment_date = fields.Date('付款日期')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('approved', '已核准'),
        ('paid', '已付款'),
        ('rejected', '退回'),
    ], default='draft', tracking=True)

    # === 動作方法 ===
    def action_submit(self):
        """提送請款"""
        self.write({
            'state': 'submitted',
            'submitter_id': self.env.uid,
            'submit_date': fields.Datetime.now(),
        })

    def action_approve(self):
        """核准請款"""
        self.write({
            'state': 'approved',
            'approver_id': self.env.uid,
            'approve_date': fields.Datetime.now(),
        })

    def action_mark_paid(self):
        """標記已付款"""
        self.write({
            'state': 'paid',
            'payment_date': fields.Date.today(),
        })

    def action_reject(self):
        """退回請款"""
        self.write({'state': 'rejected'})

    @api.constrains('estimate_ids', 'company_id')
    def _check_estimate_company(self):
        """驗證估驗單歸屬公司"""
        for claim in self:
            for estimate in claim.estimate_ids:
                if estimate.company_id != claim.company_id:
                    raise ValidationError(
                        f'估驗單 {estimate.name} 不屬於 {claim.company_id.name}')
```

### 4.6.4 契約變更管理 (contract_change_order) - v5.2

> **設計參考**: `project_version` 模組 - 專案版本追蹤
> - project.version：專案版本管理
> - version_id：任務關聯特定版本
>
> **擴展設計**: 工程契約變更比軟體版本更複雜，需追蹤金額、數量、工期等變更

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         契約變更追蹤架構                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐      ┌──────────────────────────────────────────┐ │
│  │ supervision.    │ 1:N  │         contract.change.order            │ │
│  │    project      │─────→│  (契約變更單)                            │ │
│  │                 │      │  - 變更編號、原因、類型                  │ │
│  │ 原始契約金額     │      │  - 變更金額 (增減)                       │ │
│  │ 原始工期         │      │  - 變更工期 (增減)                       │ │
│  │                 │      │  - 累計金額、累計工期                    │ │
│  └─────────────────┘      └───────────────┬──────────────────────────┘ │
│                                           │ 1:N                         │
│                                           ▼                             │
│                           ┌──────────────────────────────────────────┐ │
│                           │  contract.change.order.line              │ │
│                           │  (變更明細)                              │ │
│                           │  - change_type: add/modify/delete        │ │
│                           │  - 原數量/單價 → 新數量/單價             │ │
│                           │  - 差異金額計算                          │ │
│                           └───────────────┬──────────────────────────┘ │
│                                           │                             │
│                                           ▼                             │
│                           ┌──────────────────────────────────────────┐ │
│                           │           project.task                   │ │
│                           │  (契約工項)                              │ │
│                           │  - change_order_id: 關聯變更單           │ │
│                           │  - 變更後的 planned_qty/unit_price       │ │
│                           └──────────────────────────────────────────┘ │
│                                                                          │
│  計算流程:                                                              │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐      │
│  │ 原始契約   │ ─→ │ 變更單 1   │ ─→ │ 變更單 2   │ ─→ │ 現行契約   │      │
│  │ 金額/工期  │    │ 增減金額   │    │ 增減金額   │    │ 累計金額   │      │
│  └───────────┘    └───────────┘    └───────────┘    └───────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

```python
class ContractChangeOrder(models.Model):
    """
    契約變更單

    設計說明 (v5.2): 參考 project_version 但擴展工程契約變更需求
    - 追蹤金額、數量、工期變更
    - 支援新增、修改、刪除工項
    - 累計計算當前契約狀態
    """
    _name = 'contract.change.order'
    _description = '契約變更單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, create_date'

    # === 基本資訊 ===
    name = fields.Char('變更編號', required=True, copy=False, tracking=True)
    sequence = fields.Integer('次序', default=10, help='變更順序')
    project_id = fields.Many2one(
        'supervision.project', '所屬工程', required=True, ondelete='cascade',
        index=True)

    # === 變更原因與類型 ===
    change_type = fields.Selection([
        ('design_change', '設計變更'),
        ('quantity_adjustment', '數量調整'),
        ('price_adjustment', '單價調整'),
        ('duration_change', '工期變更'),
        ('scope_addition', '新增工項'),
        ('scope_deletion', '刪除工項'),
        ('other', '其他變更'),
    ], string='變更類型', required=True, tracking=True)

    change_reason = fields.Text('變更原因', required=True)
    change_description = fields.Text('變更說明')

    # === 日期 ===
    application_date = fields.Date('申請日期', default=fields.Date.today)
    approval_date = fields.Date('核定日期', tracking=True)
    effective_date = fields.Date('生效日期', help='變更生效起算日')

    # === 金額變更 ===
    original_contract_amount = fields.Float(
        '變更前契約金額', compute='_compute_original_amounts', store=True)
    change_amount = fields.Float(
        '本次變更金額', compute='_compute_change_totals', store=True,
        help='正值=增加, 負值=減少')
    new_contract_amount = fields.Float(
        '變更後契約金額', compute='_compute_new_amounts', store=True)
    change_amount_rate = fields.Float(
        '變更比率 (%)', compute='_compute_change_totals', store=True)

    # === 工期變更 ===
    original_duration = fields.Integer(
        '變更前工期(日)', compute='_compute_original_amounts', store=True)
    change_duration = fields.Integer(
        '本次變更工期(日)', help='正值=展延, 負值=縮短')
    new_duration = fields.Integer(
        '變更後工期(日)', compute='_compute_new_amounts', store=True)

    # === 變更明細 ===
    line_ids = fields.One2many(
        'contract.change.order.line', 'change_order_id', '變更明細',
        copy=True)

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('rejected', '退回'),
        ('cancelled', '作廢'),
    ], default='draft', tracking=True)

    # === 關聯文件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='附件')
    document_ids = fields.Many2many(
        'supervision.document', string='相關文件',
        help='設計變更圖說、會議紀錄等')

    @api.depends('project_id', 'sequence')
    def _compute_original_amounts(self):
        """計算變更前金額與工期 (前一筆變更的累計或原始契約)"""
        for order in self:
            project = order.project_id
            if not project:
                order.original_contract_amount = 0.0
                order.original_duration = 0
                continue

            # 找前一筆已核定變更單
            prev_orders = self.search([
                ('project_id', '=', project.id),
                ('state', '=', 'approved'),
                ('sequence', '<', order.sequence),
            ], order='sequence desc', limit=1)

            if prev_orders:
                order.original_contract_amount = prev_orders.new_contract_amount
                order.original_duration = prev_orders.new_duration
            else:
                # 無前一筆，使用原始契約
                order.original_contract_amount = project.contract_amount
                order.original_duration = project.contract_duration

    @api.depends('line_ids.change_amount')
    def _compute_change_totals(self):
        """計算本次變更總金額與比率"""
        for order in self:
            order.change_amount = sum(order.line_ids.mapped('change_amount'))
            if order.original_contract_amount:
                order.change_amount_rate = (
                    order.change_amount / order.original_contract_amount) * 100
            else:
                order.change_amount_rate = 0.0

    @api.depends('original_contract_amount', 'change_amount',
                 'original_duration', 'change_duration')
    def _compute_new_amounts(self):
        """計算變更後金額與工期"""
        for order in self:
            order.new_contract_amount = (
                order.original_contract_amount + order.change_amount)
            order.new_duration = order.original_duration + order.change_duration

    # === 動作 ===
    def action_submit(self):
        """提送審查"""
        self.write({'state': 'submitted'})

    def action_approve(self):
        """核定變更"""
        self.write({
            'state': 'approved',
            'approval_date': fields.Date.today(),
        })
        # 更新工項
        self._apply_changes_to_tasks()
        # 更新專案契約金額與工期
        self._update_project_contract()

    def action_reject(self):
        """退回"""
        self.write({'state': 'rejected'})

    def _apply_changes_to_tasks(self):
        """將變更應用到工項"""
        for line in self.line_ids:
            if line.change_line_type == 'add':
                # 新增工項
                self.env['project.task'].create({
                    'project_id': self.project_id.project_id.id,
                    'name': line.item_name,
                    'item_no': line.item_no,
                    'planned_qty': line.new_qty,
                    'unit': line.unit,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                })
            elif line.change_line_type == 'modify' and line.task_id:
                # 修改工項
                line.task_id.write({
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                })
            elif line.change_line_type == 'delete' and line.task_id:
                # 標記刪除 (不實際刪除，保留歷史)
                line.task_id.write({
                    'active': False,
                    'change_order_id': self.id,
                })

    def _update_project_contract(self):
        """更新專案契約金額與工期"""
        project = self.project_id
        project.write({
            'contract_amount': self.new_contract_amount,
            # 工期可能需要更新 contract_end_date
        })
        if self.change_duration and project.contract_end_date:
            from datetime import timedelta
            new_end = project.contract_end_date + timedelta(days=self.change_duration)
            project.contract_end_date = new_end


class ContractChangeOrderLine(models.Model):
    """
    契約變更明細

    記錄每個工項的變更內容：新增、修改、刪除
    """
    _name = 'contract.change.order.line'
    _description = '契約變更明細'

    change_order_id = fields.Many2one(
        'contract.change.order', '變更單', required=True, ondelete='cascade')
    project_id = fields.Many2one(
        'supervision.project', '所屬工程',
        related='change_order_id.project_id', store=True)

    # === 變更類型 ===
    change_line_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('delete', '刪除'),
    ], string='變更類型', required=True, default='modify')

    # === 工項資訊 ===
    task_id = fields.Many2one(
        'project.task', '原工項',
        domain="[('project_id.supervision_project_id', '=', project_id)]",
        help='修改/刪除時選擇原工項')
    item_no = fields.Char('工項編號')
    item_name = fields.Char('工項名稱')
    unit = fields.Char('單位')

    # === 原金額/數量 (修改/刪除時) ===
    original_qty = fields.Float('原數量')
    original_unit_price = fields.Float('原單價')
    original_amount = fields.Float(
        '原金額', compute='_compute_amounts', store=True)

    # === 新金額/數量 (新增/修改時) ===
    new_qty = fields.Float('新數量')
    new_unit_price = fields.Float('新單價')
    new_amount = fields.Float(
        '新金額', compute='_compute_amounts', store=True)

    # === 差異計算 ===
    qty_change = fields.Float(
        '數量變化', compute='_compute_amounts', store=True)
    price_change = fields.Float(
        '單價變化', compute='_compute_amounts', store=True)
    change_amount = fields.Float(
        '金額變化', compute='_compute_amounts', store=True,
        help='正值=增加, 負值=減少')

    # === 備註 ===
    note = fields.Text('備註')

    @api.depends('original_qty', 'original_unit_price',
                 'new_qty', 'new_unit_price', 'change_line_type')
    def _compute_amounts(self):
        for line in self:
            line.original_amount = line.original_qty * line.original_unit_price
            line.new_amount = line.new_qty * line.new_unit_price
            line.qty_change = line.new_qty - line.original_qty
            line.price_change = line.new_unit_price - line.original_unit_price

            if line.change_line_type == 'add':
                line.change_amount = line.new_amount
            elif line.change_line_type == 'delete':
                line.change_amount = -line.original_amount
            else:  # modify
                line.change_amount = line.new_amount - line.original_amount

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """選擇工項時帶入原資料"""
        if self.task_id:
            self.item_no = self.task_id.item_no
            self.item_name = self.task_id.name
            self.unit = self.task_id.unit
            self.original_qty = self.task_id.planned_qty
            self.original_unit_price = self.task_id.unit_price
            # 預設新值 = 原值
            self.new_qty = self.task_id.planned_qty
            self.new_unit_price = self.task_id.unit_price
```

#### 4.6.5 SupervisionProject 契約變更關聯擴展

```python
class SupervisionProject(models.Model):
    """工程標案 - 契約變更關聯 (v5.2 擴展)"""
    _inherit = 'supervision.project'

    # === 契約變更 (v5.2 - 參考 project_version) ===
    change_order_ids = fields.One2many(
        'contract.change.order', 'project_id', '契約變更單')
    change_order_count = fields.Integer(
        '變更次數', compute='_compute_change_order_count')

    # === 累計金額追蹤 ===
    original_contract_amount = fields.Float(
        '原始契約金額', help='初始契約金額 (不含變更)')
    current_contract_amount = fields.Float(
        '現行契約金額', compute='_compute_current_contract', store=True,
        help='原始金額 + 累計變更金額')
    total_change_amount = fields.Float(
        '累計變更金額', compute='_compute_current_contract', store=True)
    change_rate = fields.Float(
        '累計變更比率 (%)', compute='_compute_current_contract', store=True)

    # === 累計工期追蹤 ===
    original_duration = fields.Integer(
        '原始工期(日)', help='初始契約工期')
    current_duration = fields.Integer(
        '現行工期(日)', compute='_compute_current_contract', store=True)
    total_duration_change = fields.Integer(
        '累計工期變更(日)', compute='_compute_current_contract', store=True)

    @api.depends('change_order_ids.state')
    def _compute_change_order_count(self):
        for project in self:
            project.change_order_count = len(
                project.change_order_ids.filtered(lambda o: o.state == 'approved'))

    @api.depends('change_order_ids.state', 'change_order_ids.change_amount',
                 'change_order_ids.change_duration', 'original_contract_amount',
                 'original_duration')
    def _compute_current_contract(self):
        """計算現行契約金額與工期"""
        for project in self:
            approved = project.change_order_ids.filtered(
                lambda o: o.state == 'approved')

            project.total_change_amount = sum(approved.mapped('change_amount'))
            project.total_duration_change = sum(approved.mapped('change_duration'))

            project.current_contract_amount = (
                project.original_contract_amount + project.total_change_amount)
            project.current_duration = (
                project.original_duration + project.total_duration_change)

            if project.original_contract_amount:
                project.change_rate = (
                    project.total_change_amount / project.original_contract_amount) * 100
            else:
                project.change_rate = 0.0
```

### 4.7 稽核軌跡 (audit_trail)

```python
class AuditTrail(models.Model):
    _name = 'audit.trail'
    _description = '操作軌跡'
    _order = 'create_date desc'
    
    # 操作資訊
    user_id = fields.Many2one('res.users', '操作者', required=True)
    action_date = fields.Datetime('操作時間', default=fields.Datetime.now)
    
    # 操作內容
    model_name = fields.Char('模組')
    record_id = fields.Integer('記錄ID')
    record_name = fields.Char('記錄名稱')
    
    action_type = fields.Selection([
        ('create', '新增'),
        ('write', '修改'),
        ('unlink', '刪除'),
        ('state_change', '狀態變更'),
        ('approve', '核定'),
        ('reject', '退件'),
        ('download', '下載'),
        ('print', '列印'),
    ])
    
    # 變更內容
    old_values = fields.Text('變更前')
    new_values = fields.Text('變更後')
    
    # 關聯工程
    project_id = fields.Many2one('supervision.project', '所屬工程')
    
    # IP 資訊
    ip_address = fields.Char('IP位址')
```

### 4.8 工程相關單位管理 (supervision_partner)

> **設計參考**: `contacts` 官方模組 - res.partner 擴展與分類標籤
> - 階層結構：parent_id / child_ids (總公司 → 分公司 → 項目部)
> - 分類標籤：category_id (Many2many，多維度標籤)
> - 商業欄位委託：commercial_partner_id

**舊系統資料表對應**:
- `member` → 專案成員與權限
- `subscription` → 使用者帳號資訊

**工程相關單位分類架構**:
```
┌─────────────────────────────────────────────────────────────────────┐
│                      工程相關單位分類標籤體系                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ├── 業主 (Owner)                                                    │
│  │   ├── 政府機關                                                   │
│  │   ├── 國營事業                                                   │
│  │   └── 民間企業                                                   │
│  │                                                                   │
│  ├── 施工廠商 (Contractor)                                          │
│  │   ├── 總承包商 (甲級/乙級/丙級)                                  │
│  │   ├── 專業分包商                                                 │
│  │   │   ├── 土建分包                                               │
│  │   │   ├── 機電分包                                               │
│  │   │   └── 裝修分包                                               │
│  │   └── 材料/設備供應商                                            │
│  │                                                                   │
│  ├── 監造單位 (Supervision)                                         │
│  │   ├── 建築監造                                                   │
│  │   ├── 結構監造                                                   │
│  │   └── 機電監造                                                   │
│  │                                                                   │
│  ├── 設計單位 (Design)                                              │
│  │   ├── 建築師事務所                                               │
│  │   ├── 結構技師事務所                                             │
│  │   └── 機電技師事務所                                             │
│  │                                                                   │
│  └── 政府部門 (Government)                                          │
│      ├── 主管機關                                                   │
│      ├── 消防單位                                                   │
│      └── 環保單位                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

```python
class SupervisionPartnerCategory(models.Model):
    """
    工程單位分類標籤

    設計參考: res.partner.category
    - 支援樹狀階層分類
    - parent_path 優化 child_of 搜尋
    """
    _name = 'supervision.partner.category'
    _description = '工程單位分類標籤'
    _parent_store = True
    _order = 'name'

    name = fields.Char('標籤名稱', required=True, translate=True)
    color = fields.Integer('顏色索引', default=0)
    parent_id = fields.Many2one('supervision.partner.category', '上層分類', ondelete='cascade')
    child_ids = fields.One2many('supervision.partner.category', 'parent_id', '子分類')
    parent_path = fields.Char(index=True, unaccent=False)
    active = fields.Boolean('啟用', default=True)

    partner_ids = fields.Many2many(
        'res.partner',
        'supervision_partner_category_rel',
        'category_id', 'partner_id',
        string='相關單位'
    )

    _sql_constraints = [
        ('unique_name_parent', 'unique(name, parent_id)', '同層級下標籤名稱不可重複'),
    ]

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError('不可建立遞迴分類')


class ResPartner(models.Model):
    """
    擴展 res.partner - 工程相關單位欄位

    設計參考: contacts 模組
    - 階層結構 (parent_id / child_ids)
    - 商業欄位委託 (commercial_partner_id)
    """
    _inherit = 'res.partner'

    # === 工程單位類型 ===
    construction_partner_type = fields.Selection([
        ('owner', '業主'),
        ('contractor', '施工廠商'),
        ('supervision', '監造單位'),
        ('design', '設計單位'),
        ('government', '政府部門'),
        ('supplier', '供應商'),
    ], string='工程單位類型', tracking=True)

    # === 分類標籤 ===
    supervision_category_ids = fields.Many2many(
        'supervision.partner.category',
        'supervision_partner_category_rel',
        'partner_id', 'category_id',
        string='工程分類標籤'
    )

    # === 廠商等級 (施工廠商專用) ===
    contractor_grade = fields.Selection([
        ('grade_a', '甲級'),
        ('grade_b', '乙級'),
        ('grade_c', '丙級'),
    ], string='營造廠商等級')

    # === 資質證照 ===
    license_ids = fields.One2many('partner.license', 'partner_id', '證照資料')
    license_count = fields.Integer('證照數量', compute='_compute_license_count')

    # === 專案關聯 ===
    project_ids = fields.Many2many(
        'supervision.project',
        string='參與專案',
        compute='_compute_project_ids'
    )
    project_count = fields.Integer('專案數量', compute='_compute_project_count')

    # === 評鑑資訊 ===
    performance_rating = fields.Float('工程表現評分', default=0.0)
    quality_score = fields.Float('品質評分', default=0.0)
    safety_score = fields.Float('安全評分', default=0.0)
    schedule_adherence = fields.Float('進度遵守率 (%)', default=100.0)

    # === 技術聯絡人 ===
    technical_contact_ids = fields.One2many(
        'partner.technical.contact', 'partner_id', '技術聯絡人'
    )

    @api.depends('license_ids')
    def _compute_license_count(self):
        for partner in self:
            partner.license_count = len(partner.license_ids)


class PartnerLicense(models.Model):
    """廠商證照資料"""
    _name = 'partner.license'
    _description = '廠商證照資料'

    partner_id = fields.Many2one('res.partner', '廠商', required=True, ondelete='cascade')

    name = fields.Char('證照名稱', required=True)
    license_type = fields.Selection([
        ('business', '營業執照'),
        ('construction', '營造業登記證'),
        ('architect', '建築師執照'),
        ('engineer', '技師執照'),
        ('safety', '安全衛生證照'),
        ('environment', '環保證照'),
        ('other', '其他'),
    ], string='證照類型', required=True)

    license_no = fields.Char('證照字號')
    issue_date = fields.Date('發證日期')
    expiry_date = fields.Date('有效期限')
    is_expired = fields.Boolean('已過期', compute='_compute_is_expired', store=True)

    attachment_ids = fields.Many2many('ir.attachment', string='證照影本')

    @api.depends('expiry_date')
    def _compute_is_expired(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_expired = rec.expiry_date and rec.expiry_date < today


class PartnerTechnicalContact(models.Model):
    """技術聯絡人"""
    _name = 'partner.technical.contact'
    _description = '技術聯絡人'

    partner_id = fields.Many2one('res.partner', '所屬單位', required=True, ondelete='cascade')

    name = fields.Char('姓名', required=True)
    role = fields.Selection([
        ('project_manager', '專案經理'),
        ('site_manager', '工地主任'),
        ('safety_officer', '安全衛生人員'),
        ('quality_officer', '品管人員'),
        ('technician', '技術人員'),
        ('supervisor', '監造人員'),
    ], string='角色', required=True)

    phone = fields.Char('電話')
    mobile = fields.Char('手機')
    email = fields.Char('電子郵件')

    # 專業證照
    license_type = fields.Char('專業證照類型')
    license_no = fields.Char('證照字號')

    active = fields.Boolean('在職', default=True)
```

### 4.9 人機管理 (supervision_equipment)

> **設計參考**: `maintenance` 官方模組
> - 設備分類 (maintenance.equipment.category)
> - 維護請求與工作流 (maintenance.request)
> - MTBF/MTTR 效能指標

**舊系統資料表對應**:
- `dailyRecord.manMachineItems` → 工地人員及機具管理
- `dailyRecord.manMachineUsage` → 人機使用情況

**設備分類架構**:
```
┌─────────────────────────────────────────────────────────────────────┐
│                         機具設備分類體系                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ├── 土方機械                                                       │
│  │   ├── 挖掘機                                                     │
│  │   ├── 裝載機                                                     │
│  │   └── 推土機                                                     │
│  │                                                                   │
│  ├── 起重設備                                                       │
│  │   ├── 塔式起重機                                                 │
│  │   ├── 履帶式起重機                                               │
│  │   └── 汽車起重機                                                 │
│  │                                                                   │
│  ├── 混凝土設備                                                     │
│  │   ├── 混凝土攪拌車                                               │
│  │   ├── 混凝土泵車                                                 │
│  │   └── 混凝土振動棒                                               │
│  │                                                                   │
│  ├── 運輸設備                                                       │
│  │   ├── 傾卸車                                                     │
│  │   └── 平板車                                                     │
│  │                                                                   │
│  └── 其他設備                                                       │
│      ├── 發電機                                                     │
│      ├── 空壓機                                                     │
│      └── 抽水機                                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

```python
class EquipmentCategory(models.Model):
    """
    機具設備分類

    設計參考: maintenance.equipment.category
    """
    _name = 'supervision.equipment.category'
    _description = '機具設備分類'
    _order = 'name'

    name = fields.Char('分類名稱', required=True, translate=True)
    color = fields.Integer('顏色索引', default=0)
    note = fields.Html('說明', translate=True)

    # 設備關聯
    equipment_ids = fields.One2many('supervision.equipment', 'category_id', '設備列表')
    equipment_count = fields.Integer('設備數量', compute='_compute_equipment_count')

    # 預設屬性定義 (Odoo 18 Properties)
    equipment_properties_definition = fields.PropertiesDefinition('設備屬性定義')

    # 預設責任人
    default_technician_id = fields.Many2one('res.users', '預設負責技師')

    @api.depends('equipment_ids')
    def _compute_equipment_count(self):
        for category in self:
            category.equipment_count = len(category.equipment_ids)


class SupervisionEquipment(models.Model):
    """
    機具設備

    設計參考: maintenance.equipment
    - 設備追蹤與序號管理
    - MTBF/MTTR 效能指標
    - 動態屬性 (Properties)
    """
    _name = 'supervision.equipment'
    _description = '機具設備'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('設備名稱', required=True, tracking=True)
    active = fields.Boolean('啟用', default=True)

    # === 分類與識別 ===
    category_id = fields.Many2one('supervision.equipment.category', '設備分類',
                                   required=True, tracking=True)
    serial_no = fields.Char('機身號/序號', copy=False, tracking=True)
    model = fields.Char('型號')

    # === 動態屬性 (參考 maintenance 18.0) ===
    equipment_properties = fields.Properties(
        '設備規格',
        definition='category_id.equipment_properties_definition',
        copy=True
    )

    # === 位置追蹤 ===
    location = fields.Char('目前位置')
    project_id = fields.Many2one('supervision.project', '所屬工程')

    # === 擁有者資訊 ===
    owner_type = fields.Selection([
        ('own', '自有'),
        ('rent', '租賃'),
        ('subcontract', '協力廠商'),
    ], string='設備來源', default='own')
    owner_partner_id = fields.Many2one('res.partner', '擁有者/出租方')

    # === 技術規格 (舊系統欄位) ===
    capacity = fields.Char('容量/馬力')
    operator_name = fields.Char('操作人員')

    # === 日期追蹤 ===
    effective_date = fields.Date('啟用日期')
    warranty_date = fields.Date('保固到期日')
    scrap_date = fields.Date('報廢日期')

    # === 成本資訊 ===
    cost = fields.Float('設備成本/租金')
    daily_rate = fields.Float('日租金')

    # === 維護相關 (參考 maintenance) ===
    technician_id = fields.Many2one('res.users', '負責技師')
    maintenance_request_ids = fields.One2many(
        'supervision.equipment.request', 'equipment_id', '維護請求'
    )
    maintenance_count = fields.Integer('維護次數', compute='_compute_maintenance_stats')

    # === 效能指標 (MTBF/MTTR) ===
    expected_mtbf = fields.Integer('預期 MTBF (天)', default=365,
                                    help='平均故障間隔時間')
    mtbf = fields.Float('實際 MTBF (天)', compute='_compute_maintenance_stats', store=True)
    mttr = fields.Float('MTTR (天)', compute='_compute_maintenance_stats', store=True,
                        help='平均修復時間')
    estimated_next_failure = fields.Date('預計下次故障', compute='_compute_maintenance_stats')
    latest_failure_date = fields.Date('最近故障日期', compute='_compute_maintenance_stats')

    _sql_constraints = [
        ('unique_serial_no', 'unique(serial_no)', '機身號/序號不可重複'),
    ]

    @api.depends('maintenance_request_ids.stage_id.done',
                 'maintenance_request_ids.close_date',
                 'maintenance_request_ids.request_date')
    def _compute_maintenance_stats(self):
        """計算 MTBF/MTTR (參考 maintenance 模組)"""
        for equipment in self:
            # 只計算已完成的糾正性維護
            done_requests = equipment.maintenance_request_ids.filtered(
                lambda r: r.maintenance_type == 'corrective' and r.stage_id.done
            )
            equipment.maintenance_count = len(done_requests)

            if done_requests:
                # MTTR = 平均修復時間
                total_repair_days = sum(
                    (r.close_date - r.request_date).days
                    for r in done_requests if r.close_date and r.request_date
                )
                equipment.mttr = total_repair_days / len(done_requests)

                # 最近故障日期
                equipment.latest_failure_date = max(
                    r.request_date for r in done_requests if r.request_date
                )

                # MTBF = (最近故障 - 啟用日期) / 故障次數
                if equipment.effective_date and equipment.latest_failure_date:
                    days_in_service = (equipment.latest_failure_date - equipment.effective_date).days
                    equipment.mtbf = days_in_service / len(done_requests)
                    # 預計下次故障
                    equipment.estimated_next_failure = (
                        equipment.latest_failure_date + timedelta(days=equipment.mtbf)
                    )
                else:
                    equipment.mtbf = 0
                    equipment.estimated_next_failure = False
            else:
                equipment.mttr = 0
                equipment.mtbf = 0
                equipment.latest_failure_date = False
                equipment.estimated_next_failure = False


class EquipmentRequestStage(models.Model):
    """維護請求階段 (參考 maintenance.stage)"""
    _name = 'supervision.equipment.request.stage'
    _description = '維護請求階段'
    _order = 'sequence, id'

    name = fields.Char('階段名稱', required=True, translate=True)
    sequence = fields.Integer('排序', default=20)
    fold = fields.Boolean('看板摺疊', default=False)
    done = fields.Boolean('完成標記', default=False)


class SupervisionEquipmentRequest(models.Model):
    """
    設備維護請求

    設計參考: maintenance.request
    - 糾正性維護 (corrective) / 預防性維護 (preventive)
    - 循環維護排程
    """
    _name = 'supervision.equipment.request'
    _description = '設備維護請求'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, schedule_date asc'

    name = fields.Char('維護主題', required=True)
    equipment_id = fields.Many2one('supervision.equipment', '設備',
                                    required=True, ondelete='restrict')
    category_id = fields.Many2one(related='equipment_id.category_id', store=True)
    project_id = fields.Many2one(related='equipment_id.project_id', store=True)

    # === 維護類型 ===
    maintenance_type = fields.Selection([
        ('corrective', '糾正性維護'),
        ('preventive', '預防性維護'),
    ], string='維護類型', default='corrective', required=True)

    # === 日期 ===
    request_date = fields.Date('請求日期', default=fields.Date.today, tracking=True)
    schedule_date = fields.Datetime('排定時間')
    close_date = fields.Date('完成日期', readonly=True)
    duration = fields.Float('預計耗時 (小時)')

    # === 優先級與狀態 ===
    priority = fields.Selection([
        ('0', '低'),
        ('1', '一般'),
        ('2', '高'),
        ('3', '緊急'),
    ], string='優先級', default='1')

    stage_id = fields.Many2one(
        'supervision.equipment.request.stage', '階段',
        default=lambda self: self.env['supervision.equipment.request.stage'].search([], limit=1),
        tracking=True, group_expand='_group_expand_stage_ids'
    )
    kanban_state = fields.Selection([
        ('normal', '正常'),
        ('blocked', '阻擋'),
        ('done', '完成'),
    ], string='看板狀態', default='normal')

    # === 指派 ===
    user_id = fields.Many2one('res.users', '負責技師', tracking=True)
    owner_user_id = fields.Many2one('res.users', '請求者',
                                     default=lambda self: self.env.uid)

    # === 描述 ===
    description = fields.Html('問題描述')

    # === 循環維護 (預防性專用) ===
    recurring_maintenance = fields.Boolean('循環維護')
    repeat_interval = fields.Integer('重複間隔', default=1)
    repeat_unit = fields.Selection([
        ('day', '天'),
        ('week', '週'),
        ('month', '月'),
        ('year', '年'),
    ], string='重複單位', default='month')
    repeat_until = fields.Date('重複至')

    @api.model
    def _group_expand_stage_ids(self, stages, domain, order):
        return stages.search([], order=order)

    def write(self, vals):
        """階段完成時自動處理"""
        if 'stage_id' in vals:
            new_stage = self.env['supervision.equipment.request.stage'].browse(vals['stage_id'])
            if new_stage.done:
                vals['close_date'] = fields.Date.today()
                vals['kanban_state'] = 'normal'
        return super().write(vals)


class DailyLogManMachine(models.Model):
    """
    施工日誌 - 人機管理

    對應舊系統: dailyRecord.manMachineItems / manMachineUsage
    """
    _name = 'daily.log.man.machine'
    _description = '施工日誌人機管理'

    daily_log_id = fields.Many2one('daily.log.sheet', '施工日誌',
                                    required=True, ondelete='cascade')
    project_id = fields.Many2one(related='daily_log_id.project_id', store=True)

    # === 人員管理 ===
    record_type = fields.Selection([
        ('personnel', '人員'),
        ('equipment', '機具'),
    ], string='記錄類型', required=True)

    # 人員欄位
    personnel_type = fields.Selection([
        ('supervisor', '監造人員'),
        ('site_manager', '工地主任'),
        ('safety_officer', '安衛人員'),
        ('quality_officer', '品管人員'),
        ('skilled_worker', '技術工人'),
        ('general_worker', '一般工人'),
    ], string='人員類型')
    personnel_count = fields.Integer('人數')

    # 機具欄位
    equipment_id = fields.Many2one('supervision.equipment', '機具設備')
    equipment_name = fields.Char('機具名稱')  # 若無建檔則手填
    equipment_capacity = fields.Char('規格容量')
    equipment_count = fields.Integer('數量')
    equipment_hours = fields.Float('使用時數')

    note = fields.Text('備註')
```

### 4.10 檢試驗管理 (test_management)

> **舊系統資料表對應**:
> - `testStandard` → 檢試驗項目管理
> - `testRecord` → 檢(試)驗管制

```python
class TestStandard(models.Model):
    """
    檢試驗項目管理

    對應舊系統: testStandard
    """
    _name = 'supervision.test.standard'
    _description = '檢試驗項目'
    _inherit = ['mail.thread']

    name = fields.Char('項目名稱', required=True)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)

    # === 檢驗項目資訊 ===
    material = fields.Char('試驗工項/材料', required=True,
                           help='舊系統欄位: material')
    describe = fields.Text('依據之方法',
                           help='舊系統欄位: describe')
    norm = fields.Text('規範之要求',
                       help='舊系統欄位: norm')
    standard = fields.Text('頻率及下限',
                           help='舊系統欄位: standard')
    unit = fields.Char('檢查單位',
                       help='舊系統欄位: unit')

    # === 取樣規則 ===
    sampling_size = fields.Char('取樣大小')
    sampling_conditions = fields.Text('檢驗頻率條件',
                                       help='舊系統欄位: conditions (a~f 參數規則)')

    # === 契約工項關聯 ===
    pay_item_ids = fields.Many2many(
        'project.contract.item',
        string='關聯契約工項',
        help='舊系統欄位: payItems'
    )

    # === 檢驗記錄 ===
    test_record_ids = fields.One2many('supervision.test.record', 'standard_id', '檢驗記錄')
    test_record_count = fields.Integer('檢驗次數', compute='_compute_test_record_count')

    @api.depends('test_record_ids')
    def _compute_test_record_count(self):
        for rec in self:
            rec.test_record_count = len(rec.test_record_ids)


class TestRecord(models.Model):
    """
    檢(試)驗管制記錄

    對應舊系統: testRecord
    """
    _name = 'supervision.test.record'
    _description = '檢(試)驗管制記錄'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'in_site_date desc'

    name = fields.Char('編號', copy=False)
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)
    standard_id = fields.Many2one('supervision.test.standard', '檢試驗項目', required=True,
                                   help='舊系統欄位: standard')

    # === 材料關聯 (舊系統: payItem) ===
    material_name = fields.Char('材料名稱', related='standard_id.material', store=True)
    contract_item_id = fields.Many2one('project.contract.item', '契約工項')

    # === 進場記錄 (舊系統欄位) ===
    in_site_date = fields.Date('進場日期', help='舊系統欄位: inSiteDate')
    in_site_quantity = fields.Float('進場數量', help='舊系統欄位: inSiteQuantity')
    in_site_sum_quantity = fields.Float('累計進場', compute='_compute_cumulative',
                                         store=True, help='舊系統欄位: inSiteSumQuantity')

    # === 取樣記錄 (舊系統欄位) ===
    sample_date = fields.Date('取樣日期', help='舊系統欄位: sampleDate')
    sample_quantity = fields.Float('取樣數量', help='舊系統欄位: sampleQuantity')
    sample_sum_quantity = fields.Float('累計取樣', compute='_compute_cumulative',
                                        store=True, help='舊系統欄位: sampleSumQuantity')
    sample_rate = fields.Float('取樣率 (%)', compute='_compute_sample_rate',
                               help='舊系統欄位: sampleRate')

    # === 抽驗人員 ===
    member_ids = fields.Many2many('res.users', string='抽驗及會同人員',
                                   help='舊系統欄位: member')

    # === 檢驗結果 ===
    result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
        ('pending', '待判定'),
    ], string='抽試驗結果', help='舊系統欄位: result')

    # === 歸檔編號 ===
    archive_number = fields.Char('歸檔編號', help='舊系統欄位: archiveNumber')

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='檢驗報告')

    @api.depends('in_site_quantity')
    def _compute_cumulative(self):
        """計算累計數量"""
        for rec in self:
            # 查詢同專案同標準的所有記錄
            prev_records = self.search([
                ('project_id', '=', rec.project_id.id),
                ('standard_id', '=', rec.standard_id.id),
                ('in_site_date', '<=', rec.in_site_date),
                ('id', '!=', rec.id),
            ])
            rec.in_site_sum_quantity = sum(prev_records.mapped('in_site_quantity')) + rec.in_site_quantity
            rec.sample_sum_quantity = sum(prev_records.mapped('sample_quantity')) + rec.sample_quantity

    @api.depends('sample_sum_quantity', 'in_site_sum_quantity')
    def _compute_sample_rate(self):
        for rec in self:
            if rec.in_site_sum_quantity:
                rec.sample_rate = (rec.sample_sum_quantity / rec.in_site_sum_quantity) * 100
            else:
                rec.sample_rate = 0
```

### 4.11 送審管制 (review_application)

> **舊系統資料表對應**: `reviewApplication`

```python
class ReviewApplication(models.Model):
    """
    送審管制

    對應舊系統: reviewApplication
    """
    _name = 'supervision.review.application'
    _description = '送審管制'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expected_review_date asc'

    name = fields.Char('材料名稱', required=True, help='舊系統欄位: name')
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True)

    # === 契約資訊 (舊系統欄位) ===
    no = fields.Char('契約詳細表項次', help='舊系統欄位: no')
    number = fields.Float('契約數量', help='舊系統欄位: number')
    amount = fields.Float('金額', help='舊系統欄位: amount')

    # === 送審日期 (舊系統欄位) ===
    expected_review_date = fields.Date('送審-預定日期',
                                        help='舊系統欄位: expectedReviewDate')
    final_review_date = fields.Date('送審-實際日期',
                                     help='舊系統欄位: finalReviewDate')

    # === 送審資料 (舊系統欄位) ===
    has_catalog = fields.Boolean('型錄', help='舊系統欄位: hasCatalog')
    has_demo = fields.Boolean('樣品', help='舊系統欄位: hasDemo')
    has_related_test_report = fields.Boolean('相關測試報告',
                                              help='舊系統欄位: hasRelatedTestReport')
    has_subcontractor = fields.Boolean('協力廠商資料',
                                        help='舊系統欄位: hasSubcontractor')
    others = fields.Text('其他送審資料', help='舊系統欄位: others')

    # === 審查 (舊系統欄位) ===
    review_date = fields.Date('審查日期', help='舊系統欄位: reviewDate')
    final_review_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '條件式通過'),
        ('fail', '不合格'),
    ], string='審查結果', help='舊系統欄位: finalReviewResult')

    # === 廠驗 (舊系統欄位) ===
    is_factory_inspection = fields.Boolean('是否廠驗',
                                           help='舊系統欄位: isFactoryInspection')
    factory_inspection_date = fields.Date('廠驗日期',
                                          help='舊系統欄位: factoryInspectionDate')

    # === 取樣試驗 (舊系統欄位) ===
    is_test = fields.Boolean('是否取樣試驗', help='舊系統欄位: isTest')
    test_unit = fields.Char('預定試驗單位', help='舊系統欄位: testUnit')

    # === 歸檔 (舊系統欄位) ===
    archive_number = fields.Char('歸檔編號', help='舊系統欄位: archiveNumber')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已送審'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('rejected', '退件'),
    ], string='狀態', default='draft', tracking=True)

    # === 附件 ===
    attachment_ids = fields.Many2many('ir.attachment', string='送審文件')
```

### 4.12 照片管理 (photo_management)

> **舊系統資料表對應**: `image`
>
> **設計參考**: `document_knowledge` - ir.attachment 擴展

```python
class SupervisionPhoto(models.Model):
    """
    工程照片管理

    對應舊系統: image
    設計參考: document_knowledge 模組 ir.attachment 擴展
    """
    _name = 'supervision.photo'
    _description = '工程照片'
    _inherit = ['mail.thread']
    _order = 'shot_at desc'

    name = fields.Char('照片說明', help='舊系統欄位: description')
    project_id = fields.Many2one('supervision.project', '所屬工程', required=True,
                                  help='舊系統欄位: project')

    # === 照片檔案 ===
    attachment_id = fields.Many2one('ir.attachment', '照片檔案', required=True)
    image = fields.Binary('預覽圖', related='attachment_id.datas')
    extension = fields.Char('副檔名', help='舊系統欄位: extension')

    # === 拍攝資訊 (舊系統欄位) ===
    shot_at = fields.Datetime('拍攝日期', help='舊系統欄位: shotAt')
    gps_location = fields.Char('GPS位置', help='舊系統欄位: gpsLocation')

    # === 來源追蹤 (舊系統欄位) ===
    source_model = fields.Selection([
        ('daily_log', '施工日誌'),
        ('inspection', '自主檢查'),
        ('defect', '缺失改善'),
        ('test', '檢試驗'),
        ('acceptance', '驗收'),
        ('other', '其他'),
    ], string='來源分類', help='舊系統欄位: sourceModel')
    source_id = fields.Integer('來源記錄ID', help='舊系統欄位: source')

    # === 標籤 (舊系統欄位: tags) ===
    tag_ids = fields.Many2many('supervision.photo.tag', string='標籤')

    # === 上傳者 ===
    creator_id = fields.Many2one('res.users', '上傳者',
                                  default=lambda self: self.env.uid,
                                  help='舊系統欄位: creator')


class SupervisionPhotoTag(models.Model):
    """照片標籤"""
    _name = 'supervision.photo.tag'
    _description = '照片標籤'

    name = fields.Char('標籤名稱', required=True, translate=True)
    color = fields.Integer('顏色索引', default=0)

    _sql_constraints = [
        ('unique_name', 'unique(name)', '標籤名稱不可重複'),
    ]
```

### 4.13 進度表管理 (progress_schedule) - v5.2.1 補充

> **對應舊系統**: 進度表功能 (最新/列表/新增進度表/更新進度表)
> **業務說明**: 管理工程預定進度與實際進度，支援每周/每兩周/自訂計算模式

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           進度表管理架構                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  supervision.project                                                     │
│         │                                                                │
│         │ 1:N                                                            │
│         ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              progress.schedule (進度表)                          │    │
│  │  - version: 版本號                                               │    │
│  │  - change_date: 變更時間                                         │    │
│  │  - calculation_mode: 每周/每兩周/自訂                            │    │
│  │  - duration_extension: 累計工期展延                              │    │
│  │  - state: draft → active → archived                             │    │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │ 1:N                                      │
│                               ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │          progress.schedule.line (進度表明細)                     │    │
│  │  - date_start / date_end: 時間區間                               │    │
│  │  - planned_progress: 預定進度                                    │    │
│  │  - cumulative_planned: 累計預定進度                              │    │
│  │  - actual_progress: 實際進度 (從日誌帶入)                        │    │
│  │  - cumulative_actual: 累計實際進度                               │    │
│  │  - variance: 超前(+) / 落後(-)                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  計算流程:                                                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐                    │
│  │ 選擇計算模式 │ ─→ │ 自動產生區間 │ ─→ │ 填寫預定進度 │                    │
│  │ 每周/每兩周  │    │ 日期明細    │    │ 累計自動計算 │                    │
│  └────────────┘    └────────────┘    └────────────┘                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

```python
class ProgressSchedule(models.Model):
    """
    進度表

    對應舊系統：進度表 (最新頁面/列表頁面)
    業務說明：
    - 每個專案可有多版進度表，最新一版為使用中
    - 支援每周、每兩周、自訂三種計算模式
    - 實際進度從施工日誌自動帶入
    """
    _name = 'progress.schedule'
    _description = '進度表'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'version desc'

    # === 基本資訊 ===
    name = fields.Char('名稱', compute='_compute_name', store=True)
    project_id = fields.Many2one(
        'supervision.project', '所屬工程', required=True,
        ondelete='cascade', index=True)
    version = fields.Integer('版本', default=1, required=True, tracking=True)
    change_date = fields.Date('變更時間', required=True, default=fields.Date.today)

    # === 工期資訊 (從專案帶入) ===
    start_date = fields.Date(
        '開工日期', related='project_id.contract_start_date', store=True)
    original_end_date = fields.Date(
        '原定完工日期', related='project_id.contract_end_date')
    duration_extension = fields.Integer('累計工期展延(日)', default=0)
    adjusted_end_date = fields.Date(
        '調整後完工日期', compute='_compute_adjusted_end_date', store=True)
    approved_duration = fields.Integer(
        '核定工期', related='project_id.contract_duration')

    @api.depends('original_end_date', 'duration_extension')
    def _compute_adjusted_end_date(self):
        for rec in self:
            if rec.original_end_date:
                rec.adjusted_end_date = rec.original_end_date + timedelta(
                    days=rec.duration_extension)
            else:
                rec.adjusted_end_date = False

    # === 計算模式 ===
    calculation_mode = fields.Selection([
        ('weekly', '每周'),
        ('biweekly', '每兩周'),
        ('custom', '自訂'),
    ], string='計算模式', default='weekly', required=True)

    # === 進度明細 ===
    line_ids = fields.One2many(
        'progress.schedule.line', 'schedule_id', '進度明細', copy=True)

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '使用中'),
        ('archived', '已歸檔'),
    ], default='draft', tracking=True)

    @api.depends('project_id', 'version')
    def _compute_name(self):
        for rec in self:
            if rec.project_id:
                rec.name = f'{rec.project_id.name} - 進度表 v{rec.version}'
            else:
                rec.name = f'進度表 v{rec.version}'

    # === 動作 ===
    def action_generate_lines(self):
        """根據計算模式自動產生進度區間"""
        self.ensure_one()
        if not self.start_date or not self.adjusted_end_date:
            raise ValidationError('請先設定開工日期與完工日期')

        # 清除現有明細
        self.line_ids.unlink()

        lines = []
        current_date = self.start_date

        if self.calculation_mode == 'weekly':
            interval = 7
        elif self.calculation_mode == 'biweekly':
            interval = 14
        else:
            # 自訂模式不自動產生
            return True

        sequence = 1
        while current_date < self.adjusted_end_date:
            end_date = min(current_date + timedelta(days=interval - 1),
                          self.adjusted_end_date)
            lines.append({
                'schedule_id': self.id,
                'sequence': sequence,
                'date_start': current_date,
                'date_end': end_date,
            })
            current_date = end_date + timedelta(days=1)
            sequence += 1

        self.env['progress.schedule.line'].create(lines)
        return True

    def action_add_line(self):
        """新增一筆自訂時間區間 (自訂模式)"""
        self.ensure_one()
        max_seq = max(self.line_ids.mapped('sequence') or [0])
        self.env['progress.schedule.line'].create({
            'schedule_id': self.id,
            'sequence': max_seq + 1,
        })

    def action_activate(self):
        """設為使用中 (其他版本自動歸檔)"""
        self.ensure_one()
        # 將同專案其他進度表歸檔
        self.search([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
            ('state', '=', 'active'),
        ]).write({'state': 'archived'})
        self.write({'state': 'active'})

    def action_archive(self):
        """歸檔"""
        self.write({'state': 'archived'})

    def action_create_new_version(self):
        """建立新版本"""
        self.ensure_one()
        max_version = max(self.search([
            ('project_id', '=', self.project_id.id)
        ]).mapped('version') or [0])

        new_schedule = self.copy({
            'version': max_version + 1,
            'change_date': fields.Date.today(),
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': new_schedule.id,
            'view_mode': 'form',
        }


class ProgressScheduleLine(models.Model):
    """
    進度表明細

    每一行代表一個時間區間的進度規劃與執行狀況
    """
    _name = 'progress.schedule.line'
    _description = '進度表明細'
    _order = 'sequence, date_start'

    schedule_id = fields.Many2one(
        'progress.schedule', '進度表', required=True, ondelete='cascade')
    project_id = fields.Many2one(
        'supervision.project', '所屬工程',
        related='schedule_id.project_id', store=True)
    sequence = fields.Integer('序號', default=10)

    # === 時間區間 ===
    date_start = fields.Date('開始日期')
    date_end = fields.Date('結束日期')
    period_display = fields.Char('期間', compute='_compute_period_display')

    @api.depends('date_start', 'date_end')
    def _compute_period_display(self):
        for line in self:
            if line.date_start and line.date_end:
                line.period_display = f"{line.date_start.strftime('%m/%d')} - {line.date_end.strftime('%m/%d')}"
            else:
                line.period_display = ''

    # === 預定進度 ===
    planned_progress = fields.Float('預定進度 (%)', digits=(5, 2))
    cumulative_planned = fields.Float(
        '累計預定進度 (%)', compute='_compute_cumulative_planned',
        store=True, digits=(5, 2))

    @api.depends('schedule_id.line_ids.planned_progress', 'sequence')
    def _compute_cumulative_planned(self):
        for line in self:
            prev_lines = line.schedule_id.line_ids.filtered(
                lambda l: l.sequence <= line.sequence)
            line.cumulative_planned = sum(prev_lines.mapped('planned_progress'))

    # === 實際進度 ===
    actual_progress = fields.Float(
        '實際進度 (%)', digits=(5, 2),
        help='可手動填寫或從施工日誌自動帶入')
    cumulative_actual = fields.Float(
        '累計實際進度 (%)', compute='_compute_cumulative_actual',
        store=True, digits=(5, 2))

    @api.depends('schedule_id.line_ids.actual_progress', 'sequence')
    def _compute_cumulative_actual(self):
        for line in self:
            prev_lines = line.schedule_id.line_ids.filtered(
                lambda l: l.sequence <= line.sequence)
            line.cumulative_actual = sum(prev_lines.mapped('actual_progress'))

    # === 差異分析 ===
    variance = fields.Float(
        '超前(+)/落後(-)', compute='_compute_variance',
        store=True, digits=(5, 2))
    variance_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
    ], string='進度狀態', compute='_compute_variance', store=True)

    @api.depends('cumulative_planned', 'cumulative_actual')
    def _compute_variance(self):
        for line in self:
            line.variance = line.cumulative_actual - line.cumulative_planned
            if line.variance > 1:
                line.variance_status = 'ahead'
            elif line.variance < -1:
                line.variance_status = 'delayed'
            else:
                line.variance_status = 'on_track'

    def action_sync_from_daily_log(self):
        """從施工日誌同步實際進度"""
        for line in self:
            if not line.date_start or not line.date_end:
                continue
            # 查找該區間內有進度變更的日誌
            logs = self.env['daily.log.sheet'].search([
                ('project_id', '=', line.project_id.id),
                ('date', '>=', line.date_start),
                ('date', '<=', line.date_end),
                ('has_progress_change', '=', True),
            ])
            if logs:
                # 取最後一筆的進度值
                latest_log = logs.sorted('date', reverse=True)[0]
                line.actual_progress = latest_log.actual_progress
```

### 4.14 樣板設定管理 (document_template) - v5.2.1 補充

> **對應舊系統**: 樣板設定功能 (施工日誌第一聯/第二聯、自主檢查、缺失改善等樣板)
> **業務說明**: 管理各類報表輸出樣板，支援上傳自訂樣板

```python
class DocumentTemplate(models.Model):
    """
    文件樣板

    對應舊系統：樣板設定
    業務說明：
    - 管理各類報表輸出樣板 (Excel/Word)
    - 支援系統預設樣板與專案自訂樣板
    - 可上傳、下載、測試樣板
    """
    _name = 'document.template'
    _description = '文件樣板'
    _order = 'template_type, project_id, id'

    name = fields.Char('樣板名稱', required=True)

    template_type = fields.Selection([
        ('daily_log_1', '施工日誌-第一聯'),
        ('daily_log_2', '施工日誌-第二聯'),
        ('self_inspection', '自主檢查表'),
        ('defect_improvement', '缺失改善'),
        ('defect_control', '缺失改善管制表'),
        ('review_control', '送審管制表'),
        ('test_control', '檢(試)驗管制表'),
        ('progress_report', '進度報告'),
        ('estimate_report', '估驗計價表'),
        ('acceptance_report', '驗收報告'),
    ], string='樣板類型', required=True, index=True)

    # === 樣板檔案 ===
    attachment_id = fields.Many2one('ir.attachment', '樣板檔案')
    file_name = fields.Char('檔案名稱', related='attachment_id.name')
    file_data = fields.Binary('檔案內容', related='attachment_id.datas')

    # === 適用範圍 ===
    is_default = fields.Boolean(
        '系統預設', default=False,
        help='系統預設樣板，所有專案可用')
    project_id = fields.Many2one(
        'supervision.project', '專屬專案',
        help='若指定專案，則僅該專案使用此樣板；留空則為通用樣板')
    company_id = fields.Many2one(
        'res.company', '適用公司',
        default=lambda self: self.env.company)

    # === 狀態 ===
    active = fields.Boolean('啟用', default=True)

    # === 欄位對照 (進階) ===
    field_mapping = fields.Text(
        '欄位對照表',
        help='樣板欄位與系統欄位的對照，JSON 格式')

    _sql_constraints = [
        ('unique_default_type',
         'unique(template_type, is_default, company_id)',
         '每種樣板類型只能有一個系統預設'),
    ]

    # === 動作 ===
    def action_download_template(self):
        """下載樣板"""
        self.ensure_one()
        if not self.attachment_id:
            raise ValidationError('尚未上傳樣板檔案')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'self',
        }

    def action_download_default_template(self):
        """下載預設樣板"""
        self.ensure_one()
        # 返回系統內建的預設樣板
        default_templates = {
            'daily_log_1': 'construction_supervision_base/static/templates/daily_log_1.xlsx',
            'daily_log_2': 'construction_supervision_base/static/templates/daily_log_2.xlsx',
            # ... 其他預設樣板
        }
        template_path = default_templates.get(self.template_type)
        if template_path:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/{template_path}',
                'target': 'self',
            }
        raise ValidationError('此類型尚無預設樣板')

    def action_test_template(self):
        """測試樣板 (產生測試檔案)"""
        self.ensure_one()
        if not self.attachment_id:
            raise ValidationError('請先上傳樣板檔案')
        # TODO: 實作樣板測試邏輯
        # 1. 讀取樣板
        # 2. 填入測試資料
        # 3. 產生並下載測試檔案
        return True

    @api.model
    def get_template_for_report(self, template_type, project_id=None):
        """取得報表樣板 (優先順序：專案專屬 > 公司預設 > 系統預設)"""
        domain = [('template_type', '=', template_type), ('active', '=', True)]

        # 1. 優先找專案專屬樣板
        if project_id:
            template = self.search(domain + [('project_id', '=', project_id)], limit=1)
            if template:
                return template

        # 2. 找公司預設樣板
        template = self.search(
            domain + [('project_id', '=', False),
                     ('company_id', '=', self.env.company.id)],
            limit=1)
        if template:
            return template

        # 3. 找系統預設樣板
        template = self.search(
            domain + [('is_default', '=', True)], limit=1)
        return template
```

### 4.15 成本分析報表 (cost_analysis) - v5.2.1 補充

> **對應舊系統**: 成本分析功能
> **業務說明**: 分析契約金額與實際執行的差異，計算損益

```python
class CostAnalysisReport(models.Model):
    """
    成本分析報表

    對應舊系統：成本分析
    業務說明：
    - 分析契約金額 vs 實際執行金額
    - 計算各工項損益
    - 支援多維度分析 (按工項/按廠商/按月份)
    """
    _name = 'cost.analysis.report'
    _description = '成本分析報表'
    _auto = False  # 資料庫視圖
    _order = 'project_id, item_no'

    # === 基本資訊 ===
    project_id = fields.Many2one('supervision.project', '工程案件', readonly=True)
    task_id = fields.Many2one('project.task', '契約工項', readonly=True)
    item_no = fields.Char('工項編號', readonly=True)
    item_name = fields.Char('工項名稱', readonly=True)
    unit = fields.Char('單位', readonly=True)
    company_id = fields.Many2one('res.company', '承包廠商', readonly=True)

    # === 契約金額 (預算) ===
    contract_qty = fields.Float('契約數量', readonly=True, group_operator='sum')
    contract_price = fields.Float('契約單價', readonly=True)
    contract_amount = fields.Float('契約金額', readonly=True, group_operator='sum')

    # === 實際執行 ===
    actual_qty = fields.Float('實際數量', readonly=True, group_operator='sum')
    actual_amount = fields.Float('實際金額', readonly=True, group_operator='sum')

    # === 差異分析 ===
    qty_variance = fields.Float('數量差異', readonly=True, group_operator='sum')
    amount_variance = fields.Float('金額差異', readonly=True, group_operator='sum')
    variance_rate = fields.Float('差異率 (%)', readonly=True)

    # === 損益分析 ===
    profit_loss = fields.Float('損益', readonly=True, group_operator='sum')
    profit_loss_rate = fields.Float('損益率 (%)', readonly=True)

    def init(self):
        """建立資料庫視圖"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    t.id AS id,
                    t.id AS task_id,
                    sp.id AS project_id,
                    t.assigned_company_id AS company_id,
                    t.item_no,
                    t.name AS item_name,
                    t.unit,

                    -- 契約金額
                    t.planned_qty AS contract_qty,
                    t.unit_price AS contract_price,
                    t.planned_amount AS contract_amount,

                    -- 實際執行
                    t.actual_qty,
                    t.actual_amount,

                    -- 差異分析
                    (t.actual_qty - t.planned_qty) AS qty_variance,
                    (t.actual_amount - t.planned_amount) AS amount_variance,
                    CASE
                        WHEN t.planned_amount > 0
                        THEN ((t.actual_amount - t.planned_amount) / t.planned_amount * 100)
                        ELSE 0
                    END AS variance_rate,

                    -- 損益分析 (契約金額 - 實際成本)
                    (t.planned_amount - t.actual_amount) AS profit_loss,
                    CASE
                        WHEN t.planned_amount > 0
                        THEN ((t.planned_amount - t.actual_amount) / t.planned_amount * 100)
                        ELSE 0
                    END AS profit_loss_rate

                FROM project_task t
                LEFT JOIN project_project pp ON t.project_id = pp.id
                LEFT JOIN supervision_project sp ON sp.project_id = pp.id
                WHERE t.planned_amount > 0 OR t.actual_amount > 0
            )
        """ % self._table)


class CostAnalysisSummary(models.Model):
    """
    成本分析摘要

    按專案彙總的成本分析
    """
    _name = 'cost.analysis.summary'
    _description = '成本分析摘要'
    _auto = False
    _order = 'project_id'

    project_id = fields.Many2one('supervision.project', '工程案件', readonly=True)
    project_name = fields.Char('工程名稱', readonly=True)

    # 契約總金額
    total_contract_amount = fields.Float('契約總金額', readonly=True)
    # 變更金額
    total_change_amount = fields.Float('變更金額', readonly=True)
    # 現行契約金額
    current_contract_amount = fields.Float('現行契約金額', readonly=True)

    # 實際執行
    total_actual_amount = fields.Float('實際執行金額', readonly=True)
    execution_rate = fields.Float('執行率 (%)', readonly=True)

    # 估驗金額
    total_estimate_amount = fields.Float('估驗金額', readonly=True)
    estimate_rate = fields.Float('估驗率 (%)', readonly=True)

    # 損益
    profit_loss = fields.Float('預估損益', readonly=True)
    profit_loss_rate = fields.Float('損益率 (%)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sp.id AS id,
                    sp.id AS project_id,
                    pp.name AS project_name,

                    -- 契約金額
                    COALESCE(sp.original_contract_amount, sp.contract_amount) AS total_contract_amount,
                    COALESCE(sp.total_change_amount, 0) AS total_change_amount,
                    COALESCE(sp.current_contract_amount, sp.contract_amount) AS current_contract_amount,

                    -- 實際執行
                    COALESCE(SUM(t.actual_amount), 0) AS total_actual_amount,
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount) > 0
                        THEN (COALESCE(SUM(t.actual_amount), 0) /
                              COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS execution_rate,

                    -- 估驗金額
                    COALESCE((
                        SELECT SUM(pe.total_amount)
                        FROM payment_estimate pe
                        WHERE pe.project_id = sp.id AND pe.state = 'approved'
                    ), 0) AS total_estimate_amount,
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount) > 0
                        THEN (COALESCE((
                            SELECT SUM(pe.total_amount)
                            FROM payment_estimate pe
                            WHERE pe.project_id = sp.id AND pe.state = 'approved'
                        ), 0) / COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS estimate_rate,

                    -- 損益
                    (COALESCE(sp.current_contract_amount, sp.contract_amount) -
                     COALESCE(SUM(t.actual_amount), 0)) AS profit_loss,
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount) > 0
                        THEN ((COALESCE(sp.current_contract_amount, sp.contract_amount) -
                               COALESCE(SUM(t.actual_amount), 0)) /
                              COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS profit_loss_rate

                FROM supervision_project sp
                LEFT JOIN project_project pp ON sp.project_id = pp.id
                LEFT JOIN project_task t ON t.project_id = pp.id
                GROUP BY sp.id, pp.name
            )
        """ % self._table)
```

### 4.16 價格庫管理 (price_library) - v5.2.1 補充

> **對應舊系統**: 價格庫功能
> **業務說明**: 管理工程常用工項的標準單價，可快速匯入契約

```python
class PriceLibraryCategory(models.Model):
    """
    價格庫分類

    工項價格的分類管理 (例如：土方工程、結構工程、裝修工程)
    """
    _name = 'price.library.category'
    _description = '價格庫分類'
    _parent_store = True
    _order = 'sequence, name'

    name = fields.Char('分類名稱', required=True, translate=True)
    code = fields.Char('分類編號')
    sequence = fields.Integer('排序', default=10)

    parent_id = fields.Many2one(
        'price.library.category', '上層分類',
        index=True, ondelete='cascade')
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        'price.library.category', 'parent_id', '子分類')

    item_ids = fields.One2many(
        'price.library.item', 'category_id', '價格項目')
    item_count = fields.Integer('項目數', compute='_compute_item_count')

    @api.depends('item_ids')
    def _compute_item_count(self):
        for category in self:
            category.item_count = len(category.item_ids)


class PriceLibraryItem(models.Model):
    """
    價格庫項目

    標準工項單價資料
    """
    _name = 'price.library.item'
    _description = '價格庫項目'
    _order = 'category_id, item_no'

    # === 基本資訊 ===
    name = fields.Char('項目名稱', required=True, index=True)
    item_no = fields.Char('項目編號', index=True)
    description = fields.Text('項目說明')

    category_id = fields.Many2one(
        'price.library.category', '分類',
        required=True, index=True)

    # === 規格與單位 ===
    unit = fields.Char('單位', required=True)
    specification = fields.Char('規格')

    # === 價格資訊 ===
    unit_price = fields.Float('單價', required=True, digits=(12, 2))
    price_date = fields.Date('價格日期', default=fields.Date.today,
        help='此單價的有效日期')
    price_source = fields.Char('價格來源',
        help='例如：公共工程價格資料庫、廠商報價')

    # === 成本組成 (選填) ===
    material_cost = fields.Float('材料費')
    labor_cost = fields.Float('工資')
    equipment_cost = fields.Float('機具費')
    overhead_cost = fields.Float('管理費及利潤')

    @api.constrains('material_cost', 'labor_cost', 'equipment_cost',
                   'overhead_cost', 'unit_price')
    def _check_cost_breakdown(self):
        for item in self:
            total = (item.material_cost + item.labor_cost +
                    item.equipment_cost + item.overhead_cost)
            if total > 0 and abs(total - item.unit_price) > 0.01:
                raise ValidationError(
                    f'成本組成合計 ({total}) 與單價 ({item.unit_price}) 不符')

    # === 狀態 ===
    active = fields.Boolean('啟用', default=True)

    # === 歷史價格 ===
    history_ids = fields.One2many(
        'price.library.item.history', 'item_id', '價格歷史')

    def write(self, vals):
        """記錄價格變更歷史"""
        if 'unit_price' in vals:
            for item in self:
                if item.unit_price != vals['unit_price']:
                    self.env['price.library.item.history'].create({
                        'item_id': item.id,
                        'old_price': item.unit_price,
                        'new_price': vals['unit_price'],
                        'change_date': fields.Date.today(),
                    })
        return super().write(vals)


class PriceLibraryItemHistory(models.Model):
    """價格變更歷史"""
    _name = 'price.library.item.history'
    _description = '價格變更歷史'
    _order = 'change_date desc'

    item_id = fields.Many2one(
        'price.library.item', '價格項目',
        required=True, ondelete='cascade')
    old_price = fields.Float('變更前單價')
    new_price = fields.Float('變更後單價')
    change_date = fields.Date('變更日期')
    change_reason = fields.Char('變更原因')


class PriceLibraryImportWizard(models.TransientModel):
    """
    價格庫匯入精靈

    將價格庫項目匯入契約工項
    """
    _name = 'price.library.import.wizard'
    _description = '價格庫匯入精靈'

    project_id = fields.Many2one(
        'supervision.project', '目標工程', required=True)
    item_ids = fields.Many2many(
        'price.library.item', string='選擇項目')

    def action_import(self):
        """執行匯入"""
        self.ensure_one()
        tasks = []
        for item in self.item_ids:
            tasks.append({
                'project_id': self.project_id.project_id.id,
                'name': item.name,
                'item_no': item.item_no,
                'unit': item.unit,
                'unit_price': item.unit_price,
                'planned_qty': 0,  # 數量需另外填寫
            })
        created = self.env['project.task'].create(tasks)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created.ids)],
            'name': '已匯入的工項',
        }
```

### 4.17 批次操作精靈 (batch_wizard) - v5.2.1 補充

> **對應舊系統**: 批次操作功能 (批次下載日誌等)
> **業務說明**: 提供批次下載、批次處理等功能

```python
class BatchDownloadWizard(models.TransientModel):
    """
    批次下載精靈

    支援批次下載施工日誌、估驗計價表等
    """
    _name = 'batch.download.wizard'
    _description = '批次下載精靈'

    download_type = fields.Selection([
        ('daily_log', '施工日誌'),
        ('self_inspection', '自主檢查表'),
        ('estimate', '估驗計價表'),
        ('test_record', '檢試驗記錄'),
    ], string='下載類型', required=True, default='daily_log')

    # 日誌下載選項
    log_format = fields.Selection([
        ('first', '第一聯'),
        ('second', '第二聯'),
        ('both', '全部'),
    ], string='日誌格式', default='both')

    # 日期範圍
    date_from = fields.Date('開始日期')
    date_to = fields.Date('結束日期')

    # 目標記錄
    daily_log_ids = fields.Many2many(
        'daily.log.sheet', string='施工日誌')
    estimate_ids = fields.Many2many(
        'payment.estimate', string='估驗計價')

    project_id = fields.Many2one('supervision.project', '工程案件')

    def action_download(self):
        """執行批次下載"""
        self.ensure_one()

        if self.download_type == 'daily_log':
            return self._download_daily_logs()
        elif self.download_type == 'estimate':
            return self._download_estimates()
        # ... 其他類型

    def _download_daily_logs(self):
        """下載施工日誌"""
        logs = self.daily_log_ids
        if not logs and self.project_id:
            domain = [('project_id', '=', self.project_id.id)]
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            if self.date_to:
                domain.append(('date', '<=', self.date_to))
            logs = self.env['daily.log.sheet'].search(domain)

        if not logs:
            raise ValidationError('沒有符合條件的日誌可下載')

        # 產生壓縮檔
        # TODO: 實作批次下載邏輯
        # 1. 為每筆日誌產生 PDF/Excel
        # 2. 打包成 ZIP
        # 3. 回傳下載連結

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'已選擇 {len(logs)} 筆日誌，正在準備下載...',
                'type': 'info',
            }
        }
```

---

## 五、工作流程引擎設計

### 5.1 通用審核流程

```python
class ApprovalWorkflow(models.AbstractModel):
    _name = 'approval.workflow.mixin'
    _description = '審核流程混入類'
    
    # 審核配置
    approval_type = fields.Selection([
        ('single', '單層審核'),
        ('two_level', '兩層審核'),  # 監造 → 機關
        ('three_level', '三層審核'),  # 主管 → 監造 → 機關
    ])
    
    # SLA 設定
    sla_hours = fields.Integer('審查時限(小時)')
    sla_deadline = fields.Datetime('審查期限', compute='_compute_sla')
    sla_status = fields.Selection([
        ('normal', '正常'),
        ('warning', '即將逾期'),
        ('overdue', '已逾期'),
    ], compute='_compute_sla_status')
    
    @api.depends('submit_date', 'sla_hours')
    def _compute_sla(self):
        for rec in self:
            if rec.submit_date and rec.sla_hours:
                rec.sla_deadline = rec.submit_date + timedelta(hours=rec.sla_hours)
            else:
                rec.sla_deadline = False
    
    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.sla_deadline or rec.state in ('approved', 'rejected'):
                rec.sla_status = 'normal'
            elif now > rec.sla_deadline:
                rec.sla_status = 'overdue'
            elif now > rec.sla_deadline - timedelta(hours=4):
                rec.sla_status = 'warning'
            else:
                rec.sla_status = 'normal'
```

### 5.2 狀態可視化 (紅黃綠燈)

```python
class ProjectDashboard(models.Model):
    _name = 'project.dashboard'
    
    project_id = fields.Many2one('supervision.project')
    
    # 狀態燈號
    document_status = fields.Selection([
        ('green', '正常'), ('yellow', '待處理'), ('red', '逾期')
    ], compute='_compute_status')
    
    schedule_status = fields.Selection([
        ('green', '超前/正常'), ('yellow', '輕微落後'), ('red', '嚴重落後')
    ], compute='_compute_status')
    
    defect_status = fields.Selection([
        ('green', '無缺失'), ('yellow', '有缺失'), ('red', '逾期未改善')
    ], compute='_compute_status')
    
    payment_status = fields.Selection([
        ('green', '正常'), ('yellow', '待審'), ('red', '逾期')
    ], compute='_compute_status')
```

---

## 六、資料模型關聯圖

### 6.1 整體架構

```
                              ┌──────────────────┐
                              │ res.partner      │
                              │ (機關/監造/廠商) │
                              └────────┬─────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────┐     ┌─────────────────┐       ┌─────────────────┐
│ supervision.project │     │ supervision     │       │ audit           │
│                     │     │ .document       │       │ .trail          │
│ - 工程基本資料      │     │                 │       │                 │
│ - 契約資訊          │     │ - 文件類型      │       │ - 操作軌跡      │
│ - project_type      │     │ - 版本控制      │       │ - 變更紀錄      │
│   (general/         │     │ - 審核流程      │       │                 │
│    reservation)     │     │                 │       │                 │
└──────────┬──────────┘     └─────────────────┘       └─────────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
[一般式]       [預約式]
```

### 6.2 一般式資料模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                        一般式工程 (general)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  supervision.project (project_type='general')                        │
│         │                                                            │
│         ├──────────────────┬──────────────────┬──────────────────┐  │
│         │                  │                  │                  │  │
│         ▼                  ▼                  ▼                  ▼  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │construction │  │general.self │  │general.     │  │general.     ││
│  │.daily.log   │  │.inspection  │  │defect       │  │progress     ││
│  │             │  │             │  │             │  │.report      ││
│  │(依契約工項) │  │(獨立模組)   │  │(獨立模組)   │  │             ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
│         │                                                            │
│         ├──────────────────┬──────────────────┐                     │
│         ▼                  ▼                  ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │payment      │  │project      │  │general.     │                 │
│  │.estimate    │  │.acceptance  │  │realtime     │                 │
│  │             │  │             │  │.profit      │                 │
│  │(全聯下載)   │  │             │  │             │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 預約式資料模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                       預約式工程 (reservation)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  supervision.project (project_type='reservation')                    │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ reservation.notification.slip (通報單 - 核心)                │    │
│  │                                                              │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ 通報單 #1        通報單 #2        通報單 #3    ...    │  │    │
│  │  │ - 工程地點A      - 工程地點B      - 工程地點C         │  │    │
│  │  │ - 預定工期       - 預定工期       - 預定工期          │  │    │
│  │  │ - 預估金額       - 預估金額       - 預估金額          │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  │         │                                                    │    │
│  │         ├───────────────┬───────────────┬───────────────┐   │    │
│  │         ▼               ▼               ▼               ▼   │    │
│  │  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────┐│    │
│  │  │construction│   │reservation│   │reservation│   │detail ││    │
│  │  │.daily.log  │   │.self      │   │.defect    │   │.line  ││    │
│  │  │            │   │.inspection│   │.improvement│  │       ││    │
│  │  │(依通報單)  │   │(通報單內) │   │(通報單內) │   │       ││    │
│  │  └───────────┘   └───────────┘   └───────────┘   └───────┘│    │
│  └─────────────────────────────────────────────────────────────┘    │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────┐  ┌─────────────┐                                   │
│  │payment      │  │project      │                                   │
│  │.estimate    │  │.acceptance  │                                   │
│  │             │  │             │                                   │
│  │(僅第一聯)   │  │             │                                   │
│  └─────────────┘  └─────────────┘                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.4 共用模組關聯

```
┌───────────────────────────────────────────────────────────────┐
│                        共用模組                                │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │contract     │  │schedule     │  │submission   │           │
│  │.item        │  │(進度表)     │  │.control     │           │
│  │(契約工項)   │  │             │  │(送審管制)   │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │test.control │  │file.        │  │worker.      │           │
│  │(檢試驗管制) │  │management   │  │equipment    │           │
│  │             │  │(檔案管理)   │  │(人機管理)   │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │cost.        │  │price.       │  │map.         │           │
│  │analysis     │  │library      │  │search       │           │
│  │(成本分析)   │  │(價格庫)     │  │(地圖檢索)   │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## 七、API 與整合介面

### 7.1 Portal 介面 (施工廠商/監造單位)

```python
# controllers/portal.py
class SupervisionPortal(CustomerPortal):
    
    @http.route('/my/projects', type='http', auth='user', website=True)
    def portal_my_projects(self):
        """廠商/監造查看所屬工程"""
        partner = request.env.user.partner_id
        projects = request.env['supervision.project'].search([
            '|', '|',
            ('contractor_id', '=', partner.id),
            ('supervision_company_id', '=', partner.id),
            ('authority_id', '=', partner.id),
        ])
        return request.render('supervision_portal.portal_projects', {
            'projects': projects,
        })
    
    @http.route('/my/projects/<int:project_id>/documents', type='http', auth='user', website=True)
    def portal_project_documents(self, project_id):
        """查看工程文件"""
        project = request.env['supervision.project'].browse(project_id)
        # 權限檢查
        self._check_project_access(project)
        return request.render('supervision_portal.portal_documents', {
            'project': project,
            'documents': project.document_ids,
        })
```

### 7.2 XML-RPC API (外部系統整合)

```python
# 範例：外部系統提送施工日誌
import xmlrpc.client

url = 'https://your-odoo.com'
db = 'supervision_db'
username = 'contractor@example.com'
password = 'api_key_here'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

# 建立施工日誌
daily_log_id = models.execute_kw(db, uid, password,
    'construction.daily.log', 'create', [{
        'project_id': 1,
        'date': '2025-12-31',
        'weather': 'sunny',
        'worker_count': 15,
        'state': 'draft',
    }]
)

# 提送
models.execute_kw(db, uid, password,
    'construction.daily.log', 'action_submit', [[daily_log_id]]
)
```

---

## 八、部署架構建議

### 8.1 Docker Compose 配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  odoo:
    image: odoo:18.0
    depends_on:
      - db
    ports:
      - "8069:8069"
    volumes:
      - odoo-web-data:/var/lib/odoo
      - ./addons:/mnt/extra-addons
      - ./config:/etc/odoo
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=odoo_password

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_PASSWORD=odoo_password
      - POSTGRES_USER=odoo
    volumes:
      - odoo-db-data:/var/lib/postgresql/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl

volumes:
  odoo-web-data:
  odoo-db-data:
```

### 8.2 多租戶配置 (CorPAAS)

```python
# config/odoo.conf
[options]
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo_password
dbfilter = ^%h$
proxy_mode = True
```

---

## 九、開發時程與優先順序

### 9.1 Phase 1 - MVP (8-10 週)

| 模組 | 工時 | 優先級 |
|------|------|--------|
| supervision_base | 1 週 | P0 |
| supervision_project | 2 週 | P0 |
| supervision_document | 2 週 | P0 |
| supervision_workflow | 2 週 | P0 |
| 基礎權限設定 | 1 週 | P0 |

**MVP 交付目標**:
- 工程案件建立與管理
- 開工文件提送/審查/核定流程
- 基礎 RBAC 權限控制

### 9.2 Phase 2 - 施工階段功能 (6-8 週)

| 模組 | 工時 | 優先級 |
|------|------|--------|
| construction_daily_log | 2 週 | P1 |
| supervision_report | 2 週 | P1 |
| supervision_inspection | 1 週 | P1 |
| quality_defect (NCR) | 2 週 | P1 |

### 9.3 Phase 3 - 計價與驗收 (6-8 週)

| 模組 | 工時 | 優先級 |
|------|------|--------|
| payment_estimate | 3 週 | P2 |
| acceptance_management | 2 週 | P2 |
| project_closure | 1 週 | P2 |
| audit_trail | 1 週 | P2 |

### 9.4 Phase 4 - Portal 與整合 (4-6 週)

| 模組 | 工時 | 優先級 |
|------|------|--------|
| Portal 介面 | 3 週 | P3 |
| 報表產出 | 2 週 | P3 |
| API 整合 | 1 週 | P3 |

---

## 十、附錄

### A. 參考法規

1. 政府採購法
2. 公共工程施工品質管理作業要點
3. 工程施工查核作業要點
4. 營造業法
5. 職業安全衛生法

### B. 文件類型代碼表

| 代碼 | 名稱 | 階段 |
|------|------|------|
| DOC-PL-001 | 工地人員名冊 | 施工前 |
| DOC-PL-002 | 工程預定進度表 | 施工前 |
| DOC-PL-003 | 剩餘資源處理計畫書 | 施工前 |
| DOC-PL-004 | 施工計畫書 | 施工前 |
| DOC-PL-005 | 品質計畫書 | 施工前 |
| DOC-PL-006 | 職業安全衛生管理計畫書 | 施工前 |
| DOC-PL-007 | 工程保險 | 施工前 |
| DOC-PL-008 | 材料設備送審 | 施工前 |
| DOC-EX-001 | 施工日誌 | 施工中 |
| DOC-EX-002 | 監造日報 | 施工中 |
| DOC-EX-003 | 試驗報告 | 施工中 |
| DOC-CP-001 | 竣工圖 | 竣工 |
| DOC-CP-002 | 竣工結算 | 竣工 |
| DOC-CP-003 | 監造報告書 | 竣工 |

### C. 狀態轉換規則

```
文件狀態轉換:
draft → submitted (施工廠商)
submitted → reviewing (監造單位)
reviewing → revision | recommended (監造單位)
revision → submitted (施工廠商)
recommended → approved | revision (機關)
approved → [locked]

缺失狀態轉換:
open → improving (施工廠商認領)
improving → submitted (施工廠商提送改善)
submitted → confirmed | open (監造確認)
confirmed → closed (結案)
```

---

## 八、選單與頁面設計 (v5.2)

### 8.1 系統選單結構

```
工程監造系統 (主選單)
├── 📊 儀表板 (Dashboard)
│   ├── 專案總覽儀表板
│   └── 我的工作儀表板
│
├── 📁 工程專案
│   ├── 工程案件列表 (supervision.project)
│   ├── 新增工程專案
│   └── 專案設定
│       ├── 基本資料
│       ├── 契約資訊
│       ├── 成員權限管理
│       └── 承包廠商管理 (v5.0)
│
├── 📋 契約管理
│   ├── 契約工項 (project.task)
│   ├── 設計變更 / 契約變更單 (v5.2)
│   └── 進度表 (progress.schedule)
│
├── 📝 施工日誌
│   ├── 日誌列表 (daily.log.sheet)
│   ├── 新增日誌
│   ├── 日誌統計分析
│   └── 批次下載
│
├── 📑 通報單管理 (預約式)
│   ├── 通報單列表 (reservation.notification.slip)
│   ├── 新增通報單
│   └── 通報單明細
│
├── ✅ 品質管理
│   ├── 自主檢查
│   │   ├── 檢查類型管理
│   │   ├── 檢查表樣板
│   │   └── 檢查記錄
│   ├── 缺失改善
│   │   ├── 缺失記錄列表
│   │   └── 缺失追蹤
│   └── 檢(試)驗管制
│       ├── 檢驗項目管理
│       └── 檢驗記錄
│
├── 📤 送審管制
│   ├── 送審項目列表 (review.application)
│   ├── 新增送審項目
│   └── 下載管制表
│
├── 💰 估驗計價
│   ├── 估驗單列表 (payment.estimate)
│   ├── 提出估驗計價
│   ├── 請款單管理 (v5.0)
│   └── 決算管理
│
├── 🔧 驗收管理
│   ├── 工項驗收 (work.acceptance)
│   ├── 初驗管理
│   └── 正驗管理
│
├── 🏗️ 人機管理
│   ├── 人員/機具項目
│   └── 施工日誌人機記錄
│
├── 📷 照片管理
│   ├── 施工照片
│   ├── 地圖檢索
│   └── 照片標籤
│
├── 📂 檔案管理
│   ├── 檔案列表
│   └── 資料夾管理
│
├── 📊 報表中心
│   ├── 進度報告
│   ├── 即時損益分析 (一般式)
│   └── 成本分析
│
└── ⚙️ 系統設定
    ├── 樣板設定
    ├── 自主檢查類型
    ├── 檢驗項目預設
    └── 稽核軌跡
```

### 8.2 主要頁面與業務作用

| 頁面 | 模型 | 業務作用 | 主要使用者 |
|------|------|----------|------------|
| **專案儀表板** | project.dashboard | 顯示專案整體狀態燈號、待辦事項、進度概況 | 監造/廠商 |
| **工程案件列表** | supervision.project | 管理所有工程標案，篩選查詢 | 監造 |
| **工程專案設定** | supervision.project | 維護專案基本資料、契約資訊、成員權限 | 監造 |
| **契約工項** | project.task | 管理契約價目表、設計變更、工項分配給廠商 | 監造 |
| **契約變更單** | contract.change.order | 追蹤契約金額/數量/工期變更 (v5.2) | 監造 |
| **進度表** | progress.schedule | 管理預定進度與實際進度比較 | 監造/廠商 |
| **施工日誌** | daily.log.sheet | 每日施工記錄、天氣、進度、人機使用 | 廠商 |
| **日誌統計分析** | daily.log.statistics | 彙整施工日誌統計數據 | 監造/廠商 |
| **通報單** | reservation.notification.slip | 預約式工程的施工批次管理 | 監造/廠商 |
| **自主檢查** | self.inspection | 施工品質自主檢查記錄 | 廠商 |
| **自主檢查類型** | self.inspection.type | 管理檢查表類型與樣板 | 監造 |
| **缺失改善** | defect.improvement | 追蹤施工缺失與改善狀態 | 監造/廠商 |
| **檢驗項目管理** | test.standard | 管理檢驗項目、規範、頻率 | 監造 |
| **檢(試)驗記錄** | test.record | 記錄材料進場、取樣、試驗結果 | 廠商 |
| **送審管制** | review.application | 管理材料型錄、樣品、廠驗送審 | 廠商 |
| **估驗計價** | payment.estimate | 提出工程款估驗請款 | 廠商 |
| **請款單** | payment.claim | 向業主正式請款單據 (v5.0) | 監造/廠商 |
| **工項驗收** | work.acceptance | 監造驗收廠商完成的工項 | 監造 |
| **人機管理** | supervision.equipment | 管理施工人員與機具設備 | 廠商 |
| **施工照片** | supervision.photo | 管理施工照片、GPS、標籤 | 廠商 |
| **檔案管理** | supervision.document | 管理工程文件、圖說、函文 | 監造/廠商 |
| **樣板設定** | document.template | 管理各類報表樣板 | 監造 |
| **稽核軌跡** | audit.trail | 查詢系統操作記錄 | 監造 |

### 8.3 舊系統 vs 新設計對照表

#### 一般式功能對照

| 舊系統功能 | 新系統對應 | 狀態 | 說明 |
|------------|------------|------|------|
| 專案儀錶板 | project.dashboard | ✅ 已設計 | 新增多公司視角 |
| 契約工項 | project.task | ✅ 已設計 | 新增預算追蹤 (v5.1) |
| 設計變更 | contract.change.order | ✅ 已設計 | 擴展為完整變更單 (v5.2) |
| 進度表 | progress.schedule | ✅ 已設計 | v5.3 新增完整模型 |
| 施工日誌 | daily.log.sheet | ✅ 已設計 | 完整對應 |
| 日誌統計表 | daily.log.statistics | ✅ 已設計 | 內嵌於日誌模組 |
| 送審管制 | review.application | ✅ 已設計 | 完整對應 |
| 基本資料 | supervision.project | ✅ 已設計 | 整合至專案設定 |
| 成員權限管理 | res.users + ir.rule | ✅ 已設計 | Odoo 原生 + 擴展 |
| 自主檢查類型 | self.inspection.type | ✅ 已設計 | 完整對應 |
| 檢驗項目管理 | test.standard | ✅ 已設計 | 完整對應 |
| 人機管理 | supervision.equipment | ✅ 已設計 | 參考 maintenance 模組 |
| 樣板設定 | document.template | ✅ 已設計 | v5.3 新增完整模型 |
| 檢(試)驗管制 | test.record | ✅ 已設計 | 完整對應 |
| 檔案管理 | ir.attachment | ✅ 已設計 | Odoo 原生 + 擴展 |
| 估驗計價 | payment.estimate | ✅ 已設計 | 新增預算對比 (v5.1) |
| 成本分析 | cost.analysis.report | ✅ 已設計 | v5.3 新增報表視圖 |
| 價格庫 | price.library.item | ✅ 已設計 | v5.3 新增完整模型 |
| 地圖檢索 | supervision.photo | ✅ 已設計 | GPS 整合 |
| 施工照片 | supervision.photo | ✅ 已設計 | 完整對應 |

#### 預約式功能對照

| 舊系統功能 | 新系統對應 | 狀態 | 說明 |
|------------|------------|------|------|
| 通報單管理 | reservation.notification.slip | ✅ 已設計 | 核心功能完整 |
| 通報單明細 | reservation.notification.slip.line | ✅ 已設計 | 新增預算追蹤 (v5.1) |
| 預約式施工日誌 | daily.log.sheet (slip_id) | ✅ 已設計 | 關聯通報單 |
| 預約式自主檢查 | reservation.self.inspection | ✅ 已設計 | 通報單內自主檢查 |
| 預約式缺失改善 | reservation.defect.improvement | ✅ 已設計 | 通報單內缺失改善 |

### 8.4 設計完整性檢討

#### ✅ 已完善的設計

1. **核心業務流程**：工程主檔、契約工項、施工日誌、估驗計價
2. **多公司架構** (v5.0)：監造/廠商分離、資料隔離
3. **預算追蹤** (v5.1)：計畫 vs 實際對比
4. **時程控制** (v5.2)：Timeline 視圖、計時器
5. **契約變更** (v5.2)：金額/數量/工期變更追蹤
6. **進度表管理** (v5.3)：每周/每兩周/自訂模式、累計進度自動計算
7. **樣板設定** (v5.3)：多層級樣板優先順序、支援上傳測試
8. **成本分析** (v5.3)：工項損益分析、專案摘要報表
9. **價格庫** (v5.3)：分類管理、價格歷史、匯入精靈
10. **批次操作** (v5.3)：批次下載精靈

#### ✅ v5.3 補充完成 (原需補充項目)

| 項目 | 模型 | 狀態 |
|------|------|------|
| 進度表 | progress.schedule | ✅ 已完成 |
| 樣板設定 | document.template | ✅ 已完成 |
| 成本分析 | cost.analysis.report | ✅ 已完成 |
| 價格庫 | price.library.item | ✅ 已完成 |
| 批次操作 | batch.download.wizard | ✅ 已完成 |

#### 📋 設計覆蓋率

- **一般式功能**：19/19 (100%)
- **預約式功能**：5/5 (100%)
- **整體覆蓋率**：100% ✅

### 8.5 未來優化建議

#### 8.5.1 使用者體驗優化建議

| 項目 | 舊系統問題 | 優化建議 |
|------|------------|----------|
| 按鈕順序 | 取消/確認按鈕順序不一致 | 統一為「取消 \| 確認」順序 |
| 刪除確認 | 刪除提示視窗格式不統一 | 統一使用 Odoo 確認對話框 |
| 欄位名稱 | 「本期完成數量」vs「本日完成數量」不一致 | 統一術語命名規範 |
| 累計進度 | 需手動計算 | 改為自動計算 |
| 批次下載 | 分散在各功能 | 整合至報表中心 |

#### 8.5.2 新增功能建議

1. **Timeline 甘特圖視圖**：視覺化工項時程
2. **行動裝置 APP**：工地現場填報
3. **GPS 自動定位**：照片自動 GPS 標記
4. **通知提醒**：逾期、待審核提醒
5. **電子簽核**：數位簽章整合
6. **BI 儀表板**：進階數據分析

---

## 版本紀錄

| 版本 | 日期 | 變更說明 |
|------|------|----------|
| 1.0 | 2025-12-31 | 初版建立 - 一般式設計監造施工 |
| 2.0 | 2025-12-31 | 新增預約式設計監造施工支援 |
| 3.0 | 2025-12-31 | 整合 Odoo 18 架構與 OCA 擴充模組設計模式 |
| 4.0 | 2025-12-31 | 完善欄位設計、新增關聯資訊模組 (聯絡人、設備、試驗、送審、照片) |
| 5.0 | 2025-12-31 | 多公司架構 (監造/廠商分離)、移除 purchase 依賴、自訂驗收與請款模組 |
| 5.1 | 2025-12-31 | 預算追蹤機制 - 參考 account_budget_oca (planned vs actual) |
| 5.2 | 2025-12-31 | 時程控制 (project_timeline) + 契約變更管理 (project_version) |
| 5.3 | 2025-12-31 | 補充完整：進度表、樣板設定、成本分析、價格庫、批次操作 |

### 版本演進摘要

```
v1.0 ─→ v2.0 ─→ v3.0 ─→ v4.0 ─→ v5.0 ─→ v5.1 ─→ v5.2 ─→ v5.3
  │       │       │       │       │       │       │       │
一般式  預約式  Odoo18  欄位    多公司  預算    時程    100%
                架構    完善    架構    追蹤    控制    覆蓋
```

### 主要里程碑

| 版本 | 核心變更 | 參考模組 |
|------|----------|----------|
| **v5.0** | 多公司架構、資料隔離、自訂驗收請款 | - |
| **v5.1** | 預算 vs 實際追蹤、完成率計算 | account_budget_oca |
| **v5.2** | Timeline 視圖、計時器、契約變更單 | project_timeline, project_version |
| **v5.3** | 進度表、樣板、成本分析、價格庫 | - |

### 模組總數

- **核心模組**：22 個
- **舊系統覆蓋率**：100% (24/24 功能)

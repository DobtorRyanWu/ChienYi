# ChienYi Portal v10 — 設計規格書

> 給 Claude Code 的完整 context，基於 v1.0.0 乾淨版 + 後端欄位審計結果

---

## 1. 專案概述

ChienYi（匠心科技）工程監造管理系統的現場施工人員 Portal。
單一角色：現場施工人員，手機操作，工地環境。
Prototype：React JSX (chienyi-portal-v10.jsx)，28 個元件，淺色模式。

技術方案：方法 A（QWeb + vanilla JS）
- 所有頁面走 controller request.render() 完整 server render
- 互動邏輯用 vanilla JS（IIFE），querySelector + addEventListener
- 不用 OWL、不用 jQuery、不需要 build 工具
- 新增一支 static/src/js/portal_v10.js 處理前端互動

設計原則：
- 任務導向：工人想「我現在要做什麼」
- 老人/視力友善：最小正文 14px、觸控目標 44px+
- 不寫死 Selection：全部從 fields_get 拉
- 一般式/預約式共用 5-tab 導航，差異用 project_type t-if 切換

---

## 2. 正確起點：v1.0.0 乾淨版

路徑：D:\work\odoo18-docker\addons\construction_portal
版本：18.0.1.0.0（從 ChienYi-18.0 repo 拉入）

### 檔案結構（實際確認）

```
construction_portal/
├── __manifest__.py           ← depends: portal + 3 modules
├── controllers/
│   └── portal.py             ← 1 支, 426 行, 繼承 CustomerPortal
├── models/
│   ├── general_self_inspection.py
│   ├── project_project.py
│   ├── supervision_defect.py
│   ├── supervision_photo.py
│   └── supervision_project.py
├── views/
│   ├── portal_templates.xml
│   ├── portal_inspection_templates.xml
│   ├── portal_defect_templates.xml
│   └── portal_photo_templates.xml
├── static/src/css/
│   └── portal_mobile.css
└── security/
    └── security.xml
```

### 現有 13 條路由（全在 portal.py）

```
_prepare_home_portal_values()              → Portal /my 首頁計數器
_get_construction_projects_domain()        → 工人可存取的工程 domain

/my/construction                           → 工程列表
/my/construction/<pid>                     → 工程詳情
/my/construction/<pid>/inspections         → 自主檢查列表
/my/construction/<pid>/inspection/new      → 新增自主檢查表單
/my/construction/inspection/create         → 自主檢查提交 POST
/my/construction/inspection/<iid>          → 自主檢查詳情
/my/construction/<pid>/defects             → 缺失列表
/my/construction/defect/<did>              → 缺失詳情
/my/construction/defect/<did>/improve      → 缺失改善提交 POST
/my/construction/<pid>/photos              → 照片列表
/my/construction/<pid>/photo/upload        → 照片上傳 POST
/my/construction/<pid>/photo/upload-form   → 照片上傳表單
/my/construction/photo/<phid>              → 照片詳情
```

### 現有 depends

```python
'depends': ['portal', 'construction_supervision_base', 'construction_quality', 'construction_photo']
```

### 不存在的東西（Claude Code 不要引用）

- portal_workbench.py / WorkbenchPortal
- views/workbench/*.xml / views/mobile/*.xml / views/admin/*.xml
- portal_pc.py / portal_admin.py / portal_import.py
- portal_mobile_v2.css / portal_workbench.css / portal_mobile_v2.js
- cy_base_layout.xml / portal_mobile_app_shell
- _get_accessible_projects() / _is_mobile() / _get_cross_project_summary()
- 任何 --cy-* CSS 變數

---

## 3. 後端欄位審計：v10 prototype vs 實際 model

### 3.1 v10 有但後端沒有（需決定刪或加）

| v10 欄位 | 說明 | 建議 |
|---------|------|------|
| severity (minor/major/critical) | 缺失嚴重度 | supervision.defect 沒有。Portal 先不顯示 |
| progressPct | 工程進度% | supervision.project 沒有直接欄位，從 progress.schedule 算。controller 計算後傳入 template |
| designUnit | 設計單位 | supervision.project 沒有。Portal 先不顯示 |
| safetyOfficer | 安全衛生人員 | supervision.project 沒有。Portal 先不顯示 |
| projectManager | 專案經理 | supervision.project 沒有明確 PM 欄位。Portal 先不顯示 |
| workStatus | 通報單施作狀態 | slip 的 state 已經涵蓋(draft/submitted/approved/in_progress/completed)，不需要獨立 workStatus |

### 3.2 後端有但 v10 缺漏（Portal 應該顯示）

**施工日誌 (daily.log.sheet + daily.log.line)**
- 14天自動鎖定：is_locked, days_since_log → 超過14天日誌應顯示唯讀
- 累計數量：daily.log.line.cumulative_qty (computed) → 工人需要看
- 完工率：daily.log.line.completion_rate (computed) → 同上
- 超出契約警示：daily.log.line.is_over_contract → 超量應警告
- 問題標記：has_issue, issue_description → 現場問題記錄
- 技術人員需求：has_technician_requirement → 是否需要技師
- 每週排程：construction.weekly.schedule → 本週進度的真實來源

**自主檢查 (general.self.inspection)**
- 檢查人員：inspector_id → 指派給誰
- 監造人員：supervisor_id → 監造方確認人
- 承包廠商：contractor_company_id, contractor_name → 哪家承包商
- 綜合結果：overall_result (pass/conditional_pass/fail)

**缺失改善 (supervision.defect)**
- 責任單位/人員：responsible_company_id, responsible_user_id → 誰負責改善
- 根本原因：root_cause → 原因分析
- 驗證階段：verifier_id, verify_date, verify_result → 改善後驗證
- 開放天數：days_open (computed) → 持續多久

**通報單 (reservation.notification.slip)**
- 實際工期：actual_start_date, actual_end_date, actual_duration
- 逾期：overdue_days, overdue_display
- 結算金額：settlement_amount
- 驗收單：notification.acceptance model（完整驗收流程）

**預約式缺失 (reservation.defect.improvement)**
- 罰款：is_fined, fine_amount, fine_note → 罰款機制
- 發現/改善單位：discovery_unit, improvement_unit
- 缺失原因：defect_cause

### 3.3 欄位名稱對齊

| v10 用法 | 後端實際 | 注意 |
|---------|---------|------|
| safety 4個 Boolean 有/無 | safety_pre_work_education 等 Selection [('yes','有'),('no','無')] | 結果一樣但型別是 Selection 不是 Boolean |
| 缺失照片 before/after | supervision.defect: before_photo_ids / after_photo_ids (M2M) | 一般式 ✓ |
| 缺失照片 before/during/after | reservation.defect.improvement: photo_ids One2many, 用 photo_stage 區分 | 預約式用 photo_stage='before/during/after' |
| 工項單位 (手動輸入) | daily.log.line.unit: related='work_item_id.unit' | 自動帶入不需手動填 |

---

## 4. 工程類型差異

### 一般式 (general)
```
supervision.project (project_type='general')
├── daily.log.sheet（施工日誌）
├── general.self.inspection（自主檢查，掛在工程下）
├── supervision.defect（缺失 NCR，掛在工程下）
├── supervision.photo（照片）
└── supervision.document（檔案）
```

### 預約式 (reservation)
```
supervision.project (project_type='reservation')
├── daily.log.sheet（日誌，同一般式）
├── supervision.photo（照片，同一般式）
├── supervision.document（檔案，同一般式）
└── reservation.notification.slip（通報單）× N
    ├── reservation.self.inspection（檢查，掛在通報單下）
    └── reservation.defect.improvement（缺失，掛在通報單下）
```

---

## 5. 遷移規劃

### 新增 depends

```python
'depends': [
    'portal',
    'construction_supervision_base',
    'construction_quality',
    'construction_photo',
    'construction_daily_log',           # 新增
    'construction_notification_slip',   # 新增
],
```

### 檔案變動

```
construction_portal/
├── controllers/
│   └── portal.py              ← 擴充 13 → ~35 條路由
├── views/
│   ├── portal_templates.xml            ← 重寫（首頁 HUD 導航）
│   ├── portal_inspection_templates.xml ← 重寫
│   ├── portal_defect_templates.xml     ← 重寫
│   ├── portal_photo_templates.xml      ← 重寫
│   ├── portal_daily_log_templates.xml  ← 新增
│   ├── portal_slip_templates.xml       ← 新增
│   ├── portal_document_templates.xml   ← 新增
│   └── portal_settings_templates.xml   ← 新增
├── static/src/css/
│   └── portal_mobile.css      ← 重寫（--wb-* 色彩系統）
├── static/src/js/
│   └── portal_v10.js          ← 新增（vanilla JS）
└── __manifest__.py            ← 更新
```

### 新增路由

```
# 施工日誌（4條）
/my/construction/<pid>/daily-logs
/my/construction/<pid>/daily-log/<lid>
/my/construction/<pid>/daily-log/new
/my/construction/daily-log/create          POST

# 通報單（4條，預約式）
/my/construction/<pid>/slips
/my/construction/<pid>/slip/<sid>
/my/construction/<pid>/slip/new
/my/construction/slip/create               POST

# 檔案管理（2條）
/my/construction/<pid>/documents
/my/construction/<pid>/document/upload     POST

# 設定（4條）
/my/construction/settings
/my/construction/switch-project
/my/construction/new-project
/my/construction/create-project            POST
```

---

## 6. 各頁面欄位規格（含審計修正）

### 6.1 首頁

HUD（固定頂部）：
- DAY: computed (today - project.contract_start_date).days
- 工程名稱: project.name
- Avatar: request.env.user.name[:1] → 設定頁
- 資源列: 進度%(controller算) / ＋快速新增 / 待改缺失 count

事件通知卡片：controller 查 defects(is_overdue + state=open) 和 inspections(state=draft)
本週進度：從 construction.weekly.schedule 查當週排程
每日任務：4 項日常（controller 從當天記錄算狀態）
通報單區塊：t-if project_type=='reservation'

底部導航 5 tabs（<a href> 整頁跳轉）

### 6.2 施工日誌

來源 model：daily.log.sheet + daily.log.line + daily.log.weather

| 前端 | 後端欄位 | 元件 | 審計備註 |
|------|---------|------|---------|
| 天氣上午 | weather_am | select（fields_get 7項） | |
| 天氣下午 | weather_pm | select | |
| 工項名稱 | line.work_item_id | select(project.task) + 自行輸入 | |
| 今日數量 | line.daily_qty | number | |
| 累計數量 | line.cumulative_qty | 唯讀顯示 | ★ v10缺漏，要加 |
| 完工率 | line.completion_rate | 唯讀顯示 | ★ v10缺漏，要加 |
| 超出契約 | line.is_over_contract | 紅色警告 | ★ v10缺漏，要加 |
| 施作位置 | line.location | text | |
| 施工說明 | line.work_description | textarea | |
| 問題標記 | line.has_issue | checkbox | ★ v10缺漏 |
| 問題說明 | line.issue_description | textarea(條件顯示) | ★ v10缺漏 |
| 工作摘要 | work_summary | textarea | |
| 安全衛生 | safety_pre_work_education 等 | Selection yes/no 按鈕 | 型別是 Selection 不是 Boolean |
| 技術人員 | has_technician_requirement | Selection yes/no | ★ v10缺漏 |
| 14天鎖定 | is_locked, days_since_log | 超過14天顯示唯讀 | ★ v10缺漏，前端要處理 |
| 單位 | line.unit (related) | 唯讀，自動從工項帶入 | v10原設計讓手動填，應改唯讀 |

### 6.3 自主檢查

一般式：general.self.inspection + general.self.inspection.item
預約式：reservation.self.inspection + reservation.self.inspection.item

| 前端 | 後端 | 元件 | 審計備註 |
|------|------|------|---------|
| 檢查類型 | inspection_type_id | select（帶入 checklist） | |
| 檢查位置 | inspection_location | text | |
| 檢查時機 | inspection_timing | select 4項 | |
| 檢查人員 | inspector_id | 唯讀（自動=當前用戶） | ★ v10缺漏 |
| 承包廠商 | contractor_company_id | 唯讀（自動帶入） | ★ v10缺漏 |
| 檢查項目 | checklist_ids items | 按 stage 分群三按鈕 | |
| item.check_item | check_item | 顯示 | |
| item.design_standard | design_standard | 顯示 | |
| item.actual_result | actual_result | text input | |
| item.check_result | check_result | pass/defect/na 三按鈕 | |
| 綜合結果 | overall_result | 自動計算或手動 | ★ v10缺漏 |
| 照片 | photo_ids | file input + 預覽 | |
| 備註 | note | textarea | |

### 6.4 缺失改善

一般式：supervision.defect
預約式：reservation.defect.improvement

**一般式提報模式：**
| 前端 | 後端 | 元件 |
|------|------|------|
| 缺失類型 | defect_type | select 5項(fields_get) |
| 說明 | description | textarea |
| 位置 | location | text |
| 缺失來源 | source | select 7項 |
| 改善期限 | deadline | date |
| 現場照片 | before_photo_ids | file input |

**一般式改善模式：**
| 前端 | 後端 | 元件 | 審計備註 |
|------|------|------|---------|
| 責任單位 | responsible_company_id | 唯讀或 select | ★ v10缺漏 |
| 改善說明 | improvement_description | textarea | |
| 矯正措施 | corrective_action | textarea | |
| 預防措施 | preventive_action | textarea | |
| 根本原因 | root_cause | textarea | ★ v10缺漏 |
| 改善後照片 | after_photo_ids | file input | |
| 開放天數 | days_open | 唯讀顯示 | ★ v10缺漏 |

**預約式差異：**
- check_type (2項) 取代 defect_type (5項)
- record_type (2項) 取代 source (7項)
- 3階段照片用 photo_ids One2many + photo_stage 區分
- 額外：is_fined, fine_amount（罰款）★ v10缺漏
- 額外：defect_cause（缺失原因）★ v10缺漏

### 6.5 照片中心

model：supervision.photo

| 前端 | 後端 | 元件 |
|------|------|------|
| 說明 | description | text |
| 分類 | category | select 11項(fields_get) |
| 施工階段 | construction_phase | select 5項(fields_get) |
| 來源 | source_model | select 7項(fields_get) |
| 位置 | location_description | text |
| GPS | latitude, longitude | 自動取得 |
| 拍攝時間 | shot_at | datetime |

篩選面板：source_model + category + shot_date

### 6.6 通報單

model：reservation.notification.slip + slip.line

| 前端 | 後端 | 審計備註 |
|------|------|---------|
| 通報次數 | slip_no | |
| 地點 | location, location_detail | |
| 勘查日期 | survey_date | ★ v10缺漏 |
| 預定開工/完工 | planned_start_date, planned_end_date | |
| 預定工期 | planned_duration | |
| 實際開工/完工 | actual_start_date, actual_end_date | ★ v10缺漏 |
| 逾期 | overdue_days, overdue_display | ★ v10缺漏 |
| 預估金額 | estimated_amount | |
| 結算金額 | settlement_amount | ★ v10缺漏 |
| 工項明細 | detail_line_ids | |
| 狀態 | state | draft/submitted/approved/in_progress/completed |

slip.line 欄位：task_id, item_no, description, unit, unit_price, planned_qty, actual_qty, completion_rate

### 6.7 檔案管理

model：supervision.document + supervision.document.category

| 前端 | 後端 |
|------|------|
| 名稱 | name |
| 分類 | document_category_id (階層，parent_id) |
| 編號 | document_no |
| 附件 | upload_attachment_ids |
| 狀態 | state (draft/uploaded/archived) |
| 到期日 | due_date |
| 是否逾期 | is_overdue (computed) |
| 上傳者 | uploader_id |
| 上傳日期 | upload_date |

---

## 7. vanilla JS 互動清單 (portal_v10.js)

```javascript
(function() {
    'use strict';
    if (!document.querySelector('.cy-v10-app')) return;

    // 自主檢查三按鈕 toggle + 計數更新
    // 施工項目下拉 ↔ 自行輸入切換
    // 安全衛生 yes/no 按鈕（Selection 型別）
    // 照片上傳即時預覽 + 刪除
    // 事件卡片 dismiss (classList.add hidden)
    // 篩選面板開合
    // 批次群組新增/刪除 (DOM 操作)
    // 可摺疊區塊
    // 問題標記 checkbox → 條件顯示 issue_description
    // 14天鎖定：鎖定的日誌 disable 所有 input
})();
```

提交：<form method="POST"> + hidden input 存 JS 計算的值

---

## 8. CSS 色彩系統

```css
:root {
  --wb-bg0: #f5f6fa;
  --wb-bg2: #ffffff;
  --wb-bg3: #f0f1f5;
  --wb-bdr: #e0e3eb;
  --wb-t1: #1a1d26;
  --wb-t2: #5a6070;
  --wb-t3: #8b90a0;
  --wb-amber: #e6a020;
  --wb-red: #e8364f;
  --wb-green: #22b357;
  --wb-blue: #3b8de0;
  --wb-nav-h: 76px;
}
[data-theme="dark"] {
  --wb-bg0: #0a0c10;
  --wb-bg2: #1a1e28;
  --wb-bg3: #232836;
  --wb-bdr: #333a4d;
  --wb-t1: #f0f2f8;
  --wb-t2: #a0a8bc;
  --wb-t3: #6b7280;
  --wb-amber: #f5b740;
  --wb-red: #ff4d6a;
  --wb-green: #3de87a;
  --wb-blue: #5eaaff;
}
```

字體：正文 16px+，觸控 44px+，提交按鈕 20px。

---

## 9. __manifest__.py 更新

```python
'version': '18.0.2.0.0',
'depends': [
    'portal',
    'construction_supervision_base',
    'construction_quality',
    'construction_photo',
    'construction_daily_log',
    'construction_notification_slip',
],
'data': [
    'security/security.xml',
    'security/ir.model.access.csv',
    'views/portal_templates.xml',
    'views/portal_inspection_templates.xml',
    'views/portal_defect_templates.xml',
    'views/portal_photo_templates.xml',
    'views/portal_daily_log_templates.xml',
    'views/portal_slip_templates.xml',
    'views/portal_document_templates.xml',
    'views/portal_settings_templates.xml',
],
'assets': {
    'web.assets_frontend': [
        'construction_portal/static/src/css/portal_mobile.css',
        'construction_portal/static/src/js/portal_v10.js',
    ],
},
```## 7. 重要欄位修正（v10 prototype vs 後端 — 已全部修正）

Prototype 中以下欄位已修正為與後端一致：

### 7.1 照片施工階段
- 修正前：foundation/structure/finishing/mep/landscape
- 修正後：before/施工前, during/施工中, after/施工後, defect/缺失, acceptance/驗收
- 正確做法：fields_get(['construction_phase'])

### 7.2 缺失嚴重度
- 後端 supervision.defect 沒有 severity 欄位
- Prototype 已移除 severity

### 7.3 通報單狀態
- 修正前：draft/submitted/approved/in_progress/completed (5個)
- 修正後：draft/not_started/in_progress/closed (4個)
- workStatus 欄位不存在，已移除

### 7.4 預約式缺失狀態
- 一般式 supervision.defect.state: open/investigating/action_taken/verified/closed
- 預約式 reservation.defect.improvement.state: conform/corrected/uncorrected/overdue/other
- 預約式多 is_fined + fine_amount 欄位

### 7.5 工程相關單位
- 業主 → authority_id (M2O res.partner)，取 .name
- 監造 → company_id (M2O res.company)，取 .name
- 承包 → contractor_company_ids (M2M res.company)，可能多家
- 工地主任 → site_manager_id (M2O res.users)
- 監造工程師 → supervision_engineer_id (M2O res.users)
- 後端沒有獨立的「設計單位」或「專案經理」或「安衛人員」欄位

### 7.6 工程資訊欄位名稱
- startDate → contractStartDate (contract_start_date)
- endDate → contractEndDate (contract_end_date)
- duration → contractDuration (contract_duration, Integer, computed)
- elapsed → actualDuration (actual_duration, Integer, computed)
- remaining → 後端無此欄位，controller 算 totalApprovedDuration - actualDuration
- progressPct → 後端無此欄位，controller 從 progress.schedule 拉或算 actualDuration/totalApprovedDuration
- contractType → projectType Selection (general/reservation)
- status → state Selection (draft/construction/completion/acceptance/closed/suspended/terminated)

### 7.7 通報單工項明細欄位
- prototype qty/done → 後端 planned_qty/actual_qty
- 進度 = actual_qty / planned_qty
- 多 unit_price, planned_amount, actual_amount, completion_rate

### 7.8 安全衛生欄位
- 後端有 5 個欄位（不是 4 個）：
  1. safety_pre_work_education — 實施勤前教育 (yes/no)
  2. safety_labor_insurance_check — 確認新進勞工保險及訓練紀錄 (yes/no)
  3. safety_ppe_check — 檢查勞工個人防護具 (yes/no)
  4. has_technician_requirement — 施工項目是否需設置技術士 (yes/no)
  5. safety_other_matters — 安全衛生其他事項 (Text)

### 7.9 新增專案
- code 是 ir.sequence 自動產生的，前端不需要手動輸入

### 7.10 日誌相關
- 預約式日誌可選 notification_slip_id 連結到特定通報單
- work_item_id 是 required，且有 domain 過濾只顯示最細項工項
- 日誌 state: draft/filled/auto_locked/locked

### 7.11 預約式自主檢查
- state 只有 3 個值（draft/inspected/confirmed），沒有 closed
- 一般式有 4 個值（draft/inspected/confirmed/closed）
# Claude Code 指令模板

> 直接貼進 Claude Code 或放進 CLAUDE.md

---

## 第一次啟動指令

```
# ChienYi Portal v10 遷移

## 基礎模組（修改現有的）
路徑：D:\work\odoo18-docker\addons\construction_portal
版本：18.0.1.0.0（ChienYi-18.0 repo 乾淨版）
結構：1 支 controller (portal.py, 426行, 13路由), 4 template, 1 CSS, 5 model
繼承：CustomerPortal

## 必讀文件
1. PORTAL_DESIGN_SPEC.md — 設計規格 + 後端欄位審計結果（第3節很重要）
2. chienyi-portal-v10.jsx — React prototype（設計參考，不是要直接轉碼）
3. construction_portal/controllers/portal.py — 現有 controller
4. construction_portal/views/*.xml — 現有 4 個 template

## 技術方案：方法 A
- QWeb server render + vanilla JS
- 不用 OWL、不用 jQuery
- 新增 static/src/js/portal_v10.js

## 嚴禁引用（v1.0.0 不存在）
- portal_workbench.py / WorkbenchPortal
- views/workbench/*.xml
- portal_pc.py / portal_admin.py
- cy_base_layout.xml / portal_mobile_app_shell
- _get_accessible_projects() / _is_mobile()
- --cy-* CSS 變數

## 遷移原則
1. Selection 從 fields_get 拉，不寫死
2. 色彩用 --wb-* CSS variables
3. 路由在 /my/construction/* 下
4. controller 在 portal.py 裡加（不新建 controller 檔案）
5. QWeb 改完要 -u construction_portal reload
6. Odoo 18：<list> 不是 <tree>，用 column_invisible

## 目前要做的事
[寫你當下的具體任務]
```

---

## 各階段指令

### 階段 1：首頁 + HUD + 導航

```
讀 PORTAL_DESIGN_SPEC.md 第2節（起點）和第6.1節（首頁）：
1. 重寫 views/portal_templates.xml — v10 設計的首頁
   - 固定 HUD（DAY 用 (today - project.contract_start_date).days）
   - 5-tab 底部導航（<a href>，active 用 page_name 判斷）
   - Breadcrumbs 等寬分段式
2. 重寫 static/src/css/portal_mobile.css — --wb-* 色彩系統
3. 改 portal.py 的 portal_my_construction_projects 方法帶入：
   - 當前工程 project.read()
   - 逾期缺失 count
   - 待檢查 count
   - 本週排程 construction.weekly.schedule
   - 通報單列表（預約式 t-if）

沿用 ConstructionPortal class 和 _get_construction_projects_domain()。
```

### 階段 2：施工日誌

```
讀 PORTAL_DESIGN_SPEC.md 第6.2節（含審計修正）：
1. 在 portal.py 加 4 條日誌路由
2. 新增 views/portal_daily_log_templates.xml
3. 注意審計發現的缺漏：
   - 累計數量 cumulative_qty、完工率 completion_rate 要顯示（唯讀）
   - 超出契約 is_over_contract 要紅色警告
   - 14天鎖定 is_locked 超過的日誌 disable 所有 input
   - 單位 unit 是 related 欄位，自動帶入不需手動填
   - 安全衛生是 Selection yes/no 不是 Boolean
4. portal_v10.js 加：
   - 工項下拉/自行輸入切換
   - 安全衛生按鈕 toggle
   - 問題標記 checkbox → 條件顯示 issue_description

後端 model：daily.log.sheet + daily.log.line
天氣：daily.log.sheet.fields_get(['weather_am'])
工項：project.task.search_read([project_id=pid])
depends 加：construction_daily_log
```

### 階段 3：自主檢查

```
讀 PORTAL_DESIGN_SPEC.md 第6.3節：
1. 重寫 views/portal_inspection_templates.xml
2. 注意：一般式用 general.self.inspection，預約式用 reservation.self.inspection
3. 審計缺漏要加：
   - inspector_id 顯示（自動=當前用戶）
   - contractor_company_id 顯示
   - overall_result 顯示
4. portal_v10.js 加：checklist 三按鈕 toggle + 計數

checklist items 從 self.inspection.type.default_item_ids 帶入。
預約式列表頂部加通報單篩選 chips。
```

### 階段 4：缺失改善

```
讀 PORTAL_DESIGN_SPEC.md 第6.4節：
1. 重寫 views/portal_defect_templates.xml
2. 一般式 supervision.defect / 預約式 reservation.defect.improvement
3. 審計缺漏要加：
   - 一般式：responsible_company_id, root_cause, days_open
   - 預約式：is_fined/fine_amount, defect_cause
   - 預約式照片用 photo_ids One2many + photo_stage 區分（不是 M2M）
4. severity 欄位後端沒有，Portal 先不顯示
```

### 階段 5：照片中心

```
讀 PORTAL_DESIGN_SPEC.md 第6.5節：
1. 重寫 views/portal_photo_templates.xml
2. 按日期分群、三個浮動元件
3. 篩選面板欄位全部從 fields_get 拉
4. 批次群組上傳用 portal_v10.js 處理 DOM

後端：supervision.photo.search_read
```

### 階段 6：通報單 + 檔案 + 設定

```
讀 PORTAL_DESIGN_SPEC.md 第6.6-6.7節：
1. 新增 views/portal_slip_templates.xml
   - 審計缺漏：actual dates, overdue_days, settlement_amount
   - 工項進度條用 slip.line.completion_rate
2. 新增 views/portal_document_templates.xml
   - 分類用 document_category_id（階層結構 parent_id）
3. 新增 views/portal_settings_templates.xml
4. 在 portal.py 加對應路由

depends 加：construction_notification_slip
```

---

## 除錯指令模式

```
# 改 template
自主檢查三按鈕不生效 → 檢查 portal_v10.js 的 querySelector('.insp-check-btn')

# 改 CSS
底部導航被 iPhone 劉海遮住 → .cy-bottom-nav 加 padding-bottom: max(8px, env(safe-area-inset-bottom))

# reload
docker compose exec odoo odoo -u construction_portal -d odoo18_dev --stop-after-init
docker compose restart odoo
```

---

## 重要提醒

1. 先讀 SPEC 第3節（欄位審計）再動手寫 template
2. severity/progressPct/designUnit 後端沒有，先不顯示
3. 安全衛生是 Selection 不是 Boolean
4. 日誌有14天鎖定機制要處理
5. 預約式缺失照片用 One2many + photo_stage，不是 M2M
6. 不要新建 controller 檔案，路由加在 portal.py 裡
7. 不要引用 v1.6.0 的任何東西
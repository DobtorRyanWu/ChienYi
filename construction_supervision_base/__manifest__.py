# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 核心基礎模組',
    # 4.6.0: 修 total_approved_duration 重複計算展延 —— 基數改用 original_duration
    #        （開工時凍結）而非 contract_duration（會隨 contract_end_date 移動、
    #        本身已含展延）。P11001 實測 178 → 164
    # 4.7.0: 併入 GitHub 上游修正 8f0bf84 —— _resolve_uom_id 自動建 uom.category/uom.uom
    #        改用 sudo（uom 是全域參照資料；原本要求 Administration/Settings 群組，
    #        非管理員如代操帳號建含新單位工項／套用引進新單位的契約變更時 AccessError）
    # 4.8.0: 四件事——(a) 契約工項 actual_amount 改為與 planned_amount 同一套三分支
    #        並向上滾動（實際完成數量本身由 construction_daily_log 計算）；
    #        (b) ir.attachment 加 supervision_project_id / document_category_id 兩欄
    #        並新增 supervision.attachment.mixin，各業務單據的附件自動歸類，
    #        新增「檔案管理 > 文件管理 > 全部工程附件」清單；
    #        (c) 文件分類改以實際案件歸檔資料夾為準（11-工程資料、12-文書資料、
    #        14-變更設計～18-府查核；照片另有「照片管理」專責故不設分類），
    #        舊 24 筆系統分類停用不刪；
    #        (d) supervision.document / category 的 name_get 改 _compute_display_name
    #        （Odoo 17 起 name_get 已移除，原本那兩段從未被呼叫過）
    # 4.8.1: 舊 24 筆文件分類補 post-migration 才真的停用得了
    #        （當初以 noupdate="1" 建立，旗標存在 ir_model_data 上，改 XML 無效）
    # 4.8.2: 拿掉「13-照片」文件分類（含 4 子分類）—— 照片由「照片管理」專責，
    #        不再給它第二套分類體系；supervision.photo 也不掛附件歸類 mixin
    'version': '18.0.5.4.0',  # 5.4.0: 營造廠商移到基本資訊區
    #        顯示欄位改為 項次/父工項/項目及說明/單位/契約數量/契約單價/備註——代操回報
    #        「各大項未區隔，項目會混淆」，選取對話框只列葉節點看不出屬於哪個大項。
    #        契約複價改預設隱藏、移除 sequence 拖曳把手（default_order 是 item_no_sort，
    #        拖曳本來就不會生效）。本 view 由 6 個「選擇施工項目」對話框共用，一起改。
    #        5.0.0: 代操作員(group_operator)登入落地頁設為「工程案件」——
    #        Odoo 只有 per-user 的 action_id(偏好設定>首頁動作)、沒有 per-group 設定，
    #        故在 create/群組異動時代設，只填空的不覆蓋使用者自訂；post-migrate 回填既有帳號。
    #        4.5.0: 工程案件新增經緯度範圍 constrains（原本完全沒有，實際存過非法緯度 121.51；且告示牌照片會繼承這組座標，錯值會擴散）；4.4.0: 新增 res.users.portal_role 自訂欄位管理前台角色(取代原生下拉,對Portal使用者可見可改;設定角色自動轉乾淨Portal,admin除外);角色群組移除 category_id；4.3.0: 前台四角色往下合併（boss/manager/field/observer 併入 subscriber/leader/user/viewer 並改名為 老闆/主管/現場人員/定期閱覽者、刪除新群組、到期邏輯解耦）post-migrate；4.1.1: 業主欄位 authority_id→authority_name 純文字化資料回填 post-migrate；4.1.0: project_task 必填欄位 NULL 回填 pre-migrate
    'category': 'Construction/Supervision',
    'summary': '工程監造與施工協作管理系統核心模組',
    'description': """
工程監造系統 - 核心基礎模組
============================

此模組提供工程監造系統的核心功能：

主要功能
--------
* 工程案件主檔管理 (supervision.project)
* 契約工項管理 (project.task 擴展)
* 工程文件管理與審核流程
* 多公司架構支援 (設計監造/施工廠商)
* 資料隔離與權限控制

技術特點
--------
* 繼承 Odoo 18 project 模組
* 支援一般式與預約式工程類型
* 完整的狀態機與工作流程
* 多層級權限控制
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'project',
        'hr_timesheet',
        'contacts',
        'mail',
        'resource',
        'uom',
        'product',
    ],
    'data': [
        # Security
        # 注意：必須先建立群組，才能載入 ir.model.access.csv
        'security/security.xml',
        'security/portal_groups.xml',  # 包含 group_operator 定義
        'security/new_portal_groups.xml',  # 前台四角色（老闆/主管/現場人員/定期閱覽者）+ 2 個組織類型
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        'data/document_category_data.xml',
        'data/ir_cron_data.xml',
        'data/portal_account_cron.xml',  # 臨時帳號到期自動停用
        # Wizard
        'wizard/tender_import_wizard_views.xml',
        'wizard/document_replace_attachment_wizard_views.xml',
        # Views
        'views/res_company_views.xml',
        'views/res_users_views.xml',  # 新架構：組織身分欄位
        'views/supervision_project_views.xml',
        'views/project_task_views.xml',
        'views/supervision_document_views.xml',
        'views/product_views.xml',
        'views/menu.xml',
        'views/supervision_document_category_views.xml',
        'views/supervision_attachment_views.xml',  # 需 menu.xml 的 menu_document_management
        'views/hide_official_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_supervision_base/static/src/css/backend.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 1,
    'post_migrate': 'construction_supervision_base.hooks.post_migrate',
}

# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 核心基礎模組',
    'version': '18.0.4.4.0',  # 4.4.0: 新增 res.users.portal_role 自訂欄位管理前台角色(取代原生下拉,對Portal使用者可見可改;設定角色自動轉乾淨Portal,admin除外);角色群組移除 category_id；4.3.0: 前台四角色往下合併（boss/manager/field/observer 併入 subscriber/leader/user/viewer 並改名為 老闆/主管/現場人員/定期閱覽者、刪除新群組、到期邏輯解耦）post-migrate；4.1.1: 業主欄位 authority_id→authority_name 純文字化資料回填 post-migrate；4.1.0: project_task 必填欄位 NULL 回填 pre-migrate
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

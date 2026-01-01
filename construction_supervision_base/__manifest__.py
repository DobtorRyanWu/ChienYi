# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 核心基礎模組',
    'version': '18.0.1.0.0',
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
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/res_company_views.xml',
        'views/supervision_project_views.xml',
        'views/project_task_views.xml',
        'views/supervision_document_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 1,
}

# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 稽核模組',
    'version': '18.0.1.0.0',
    'category': 'Construction/Audit',
    'summary': '操作軌跡記錄與稽核追蹤',
    'description': """
工程監造系統 - 稽核模組
============================

此模組提供系統操作軌跡記錄功能：

主要功能
--------
* 操作軌跡記錄 (audit.trail)
* 追蹤建立、修改、狀態變更、刪除等操作
* 記錄操作者、時間、來源記錄
* 記錄變更前後的值
* 完整的操作歷史查詢

技術特點
--------
* 自動記錄重要操作
* Mixin 模式供其他模型繼承
* 支援多模型審計追蹤
* 多公司資料隔離
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/audit_trail_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 50,
}

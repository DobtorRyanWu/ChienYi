# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 通報單管理',
    'version': '18.0.1.1.0',
    'category': 'Construction/Supervision',
    'summary': '預約式工程通報單管理模組',
    'description': """
工程監造系統 - 通報單管理
==========================

此模組提供預約式工程的通報單管理功能：

主要功能
--------
* 通報單管理 (reservation.notification.slip)
* 通報單明細 (reservation.notification.slip.line)

技術特點
--------
* 預算追蹤 (planned vs actual)
* 4 階段狀態流程（草稿→未開始→施工中→已結案）
* 整合工程範疇量預估
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_photo',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/notification_slip_views.xml',
        'wizard/add_slip_line_wizard_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 通報單管理',
    # 1.1.1: 修正驗收動作寫入不存在的狀態值 'completed'（會 ValueError）與
    #        slip_id domain 的 'approved'；狀態值域為 draft/not_started/in_progress/closed
    # 1.2.0: 新增通報單經緯度欄位（含範圍 constrains）。通報單照片沒有 GPS EXIF 時
    #        會沿用這組座標，現場人員不必逐張手填
    # 2.0.0: 照片收斂 —— related_photo_ids 改成真 One2many（同檢試驗）
    # 2.1.0: 後台「關聯照片」頁籤補上批次上傳入口（原本只有唯讀反查，完全無法上傳）
    # 2.2.0: 關聯照片改用共用看板
    # 2.3.0: 同上，關掉照片頁籤的「加入」按鈕
    'version': '18.0.2.3.0',
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
        'report/notification_slip_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

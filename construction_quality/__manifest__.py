# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 品質管理模組',
    'version': '18.0.2.1.1',
    'category': 'Construction/Quality',
    'summary': '工程監造品質管理、缺失追蹤與自主檢查',
    'description': """
工程監造系統 - 品質管理模組
============================

此模組提供工程品質管理功能：

主要功能
--------
* 缺失管理 (NCR) - supervision.defect
* 自主檢查類型管理 - self.inspection.type
* 一般式自主檢查 - general.self.inspection
* 預約式自主檢查 - reservation.self.inspection
* 預約式缺失改善 - reservation.defect.improvement

技術特點
--------
* NCR 完整狀態流程 (open -> investigating -> action_taken -> verified -> closed)
* 支援照片附件上傳
* 逾期追蹤與警示
* 多公司資料隔離
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_photo',
        'construction_notification_slip',  # reservation_defect/inspection 用 Many2one('reservation.notification.slip')
        'mail',
    ],
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',  # 缺失逾期通知（每日自動）
        # Views
        'views/defect_improvement_prefix_config_views.xml',
        'views/self_inspection_type_views.xml',
        'views/self_inspection_type_copy_wizard_views.xml',
        'views/general_self_inspection_views.xml',
        'views/reservation_self_inspection_views.xml',
        'views/reservation_defect_improvement_views.xml',
        'views/supervision_defect_views.xml',
        'views/menu.xml',
        'report/self_inspection_report.xml',
        'report/reservation_defect_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

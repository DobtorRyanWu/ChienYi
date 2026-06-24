# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 預約式工程專用模組',
    'version': '18.0.1.1.0',
    'category': 'Construction/Reservation',
    'summary': '預約式工程通報單整合自主檢查與缺失改善',
    'description': """
工程監造系統 - 預約式工程專用模組
==================================

此模組整合通報單與品質管理功能：

主要功能
--------
* 通報單擴展 - 整合自主檢查與缺失改善
* 預約式自主檢查增強 - 從通報單直接管理
* 預約式缺失改善增強 - 從通報單直接管理
* 統計分析與快速導覽

技術特點
--------
* 擴展 reservation.notification.slip 模型
* 整合 reservation.self.inspection
* 整合 reservation.defect.improvement
* 提供從自主檢查缺失項目自動建立缺失改善記錄
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_notification_slip',
        'construction_quality',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Wizards
        'views/create_reservation_defect_wizard_views.xml',
        # Views
        'views/notification_slip_views.xml',
        'views/reservation_self_inspection_views.xml',
        'views/reservation_defect_improvement_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 15,
}

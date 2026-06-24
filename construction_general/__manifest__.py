# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 一般式工程管理',
    'version': '18.0.2.0.0',
    'category': 'Construction/General',
    'summary': '一般式工程專用管理模組',
    'description': """
工程監造系統 - 一般式工程管理
============================

此模組提供一般式工程的專屬管理功能：

主要功能
--------
* 一般式自主檢查擴展 - 增加與缺失改善的整合
* 一般式缺失改善 - 獨立於通報單的缺失追蹤與改善
* 進度報告 - 定期記錄工程進度與施工狀況
* 即時損益 - 計算與追蹤工程即時損益

技術特點
--------
* 適用於 project_type = 'general' 的工程案件
* 完整的狀態流程與工作流
* 多公司資料隔離
* 與品質管理模組整合
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_quality',
        'construction_photo',
        'construction_payment',
        'mail',
    ],
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/general_defect_improvement_views.xml',
        'views/general_progress_report_views.xml',
        'views/general_realtime_profit_views.xml',
        'views/general_self_inspection_extend_views.xml',
        'views/create_defect_wizard_views.xml',
        'views/menu.xml',
        'report/print_reports.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_general/static/src/components/profit_loss_dashboard/profit_loss_dashboard.js',
            'construction_general/static/src/components/profit_loss_dashboard/profit_loss_dashboard.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 15,
}

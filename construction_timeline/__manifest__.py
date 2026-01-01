# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 時程控制模組',
    'version': '18.0.1.0.0',
    'category': 'Construction/Supervision',
    'summary': '工程時程 Timeline 視圖與計時器功能',
    'description': """
工程監造系統 - 時程控制模組
==============================

此模組提供工程時程控制與視覺化功能：

主要功能
--------
* Timeline 甘特圖視圖 - 視覺化工項時程
* 施工計時器 - 開始/結束施工計時
* 時程差異分析 - 預定 vs 實際時程對比
* 工時記錄整合 - 與 hr_timesheet 整合

技術特點
--------
* 參考 OCA project_timeline 設計
* 參考 hr_timesheet_time_control 計時器模式
* 支援 web_timeline widget
* 完整的時程追蹤與分析
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'hr_timesheet',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        'security/security.xml',
        # Views
        'views/project_task_timeline_views.xml',
        'views/timesheet_time_control_views.xml',
        'views/schedule_variance_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_timeline/static/src/css/timeline.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 15,
}

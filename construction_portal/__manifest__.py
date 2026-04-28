# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - Portal 入口',
    'version': '18.0.2.0.0',
    'category': 'Construction/Portal',
    'summary': '讓承包廠商聯絡人透過 Portal 查看工程、填寫日誌、檢查與缺失改善',
    'description': """
工程監造系統 - Portal v10
============================

此模組提供 Portal 用戶（承包廠商聯絡人）的前台操作功能。

v2.0.0 (Portal v10)
--------------------
* 全新 HUD 首頁設計（DAY 計數、事件通知、排程）
* --wb-* CSS 色彩系統
* 5-tab 底部導航
* vanilla JS 互動（portal_v10.js）
* 支援施工日誌、通報單模組整合

主要功能
--------
* 工程首頁（HUD + 事件通知 + 本週排程 + 每日任務）
* 施工日誌填寫與查詢
* 自主檢查表填寫
* 缺失改善提交
* 照片上傳管理
* 通報單查詢（預約式工程）
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'construction_supervision_base',
        'construction_quality',
        'construction_photo',
        'construction_daily_log',
        'construction_notification_slip',
        'web_leaflet_lib',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/portal_templates.xml',
        'views/portal_inspection_templates.xml',
        'views/portal_defect_templates.xml',
        'views/portal_photo_templates.xml',
        'views/portal_photo_map_templates.xml',
        'views/portal_daily_log_templates.xml',
        'views/portal_slip_templates.xml',
        'views/portal_document_templates.xml',
        'views/portal_settings_templates.xml',
        'views/portal_schedule_templates.xml',
        # 登入頁品牌化（EAGLE 風格）
        'views/login_templates.xml',
        # 停用 Odoo Website 預設 /contactus 頁面（客服走另一系統）
        'data/disable_contactus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'construction_portal/static/src/css/portal_login.css',
            'construction_portal/static/src/css/portal_mobile.css',
            'construction_portal/static/src/js/portal_v10.js',
            'construction_portal/static/src/js/portal_locator.js',
            # Leaflet（從 web_leaflet_lib 引入到 frontend）
            '/web_leaflet_lib/static/lib/leaflet/leaflet.css',
            '/web_leaflet_lib/static/lib/leaflet/leaflet.js',
            '/web_leaflet_lib/static/lib/leaflet_markercluster/MarkerCluster.css',
            '/web_leaflet_lib/static/lib/leaflet_markercluster/MarkerCluster.Default.css',
            '/web_leaflet_lib/static/lib/leaflet_markercluster/leaflet.markercluster.js',
            # Portal 照片地圖
            'construction_portal/static/src/css/portal_photos_map.css',
            'construction_portal/static/src/js/portal_photos_map.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 100,
}

# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - Portal 入口',
    'version': '18.0.1.0.0',
    'category': 'Construction/Portal',
    'summary': '讓承包廠商聯絡人透過 Portal 填寫自主檢查、缺失改善、上傳照片',
    'description': """
工程監造系統 - Portal 入口
============================

此模組提供 Portal 用戶（承包廠商聯絡人）的前台操作功能。

主要功能
--------
* 查看關聯的工程案件列表
* 填寫自主檢查表
* 查看/填寫缺失改善
* 上傳工程照片

使用方式
--------
1. 將廠商聯絡人設定為 Portal 用戶
2. 確認該聯絡人已關聯到承包廠商 (res.partner)
3. 承包廠商需已加入工程案件的「承包廠商」欄位
4. Portal 用戶即可在 /my/construction 查看相關工程

技術說明
--------
* 繼承 portal.mixin 提供 Portal 存取功能
* 自訂 Portal Controller 處理路由
* Portal 專用模板呈現資料
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'construction_supervision_base',
        'construction_quality',
        'construction_photo',
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
    ],
    'assets': {
        'web.assets_frontend': [
            'construction_portal/static/src/css/portal_mobile.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 100,
}

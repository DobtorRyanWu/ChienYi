# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 照片管理模組',
    'version': '18.0.1.2.0',
    'category': 'Construction/Supervision',
    'summary': '工程照片管理與 GPS 追蹤',
    'description': """
工程監造系統 - 照片管理模組
============================

此模組提供工程照片管理功能：

主要功能
--------
* 工程照片上傳與管理 (supervision.photo)
* 照片標籤分類系統 (supervision.photo.tag)
* GPS 位置記錄與追蹤
* 來源追蹤 (施工日誌、自主檢查、缺失改善等)
* 拍攝資訊記錄

技術特點
--------
* 使用 ir.attachment 存儲照片檔案
* 支援多標籤分類
* GPS 位置資訊記錄
* 完整來源追蹤機制
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views (photo_views first for action reference)
        'views/supervision_photo_views.xml',
        'views/supervision_photo_tag_views.xml',
        'views/supervision_photo_category_views.xml',
        'views/supervision_project_views.xml',
        'views/menu.xml',
        # Master data (loaded after views so menus can reference actions)
        'data/supervision_photo_category_data.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 25,
}

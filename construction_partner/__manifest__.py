# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 工程相關單位管理',
    # 附件自動歸類：掛 supervision.attachment.mixin，上傳的附件自動帶所屬工程與文件分類
    'version': '18.0.1.1.0',
    'category': 'Construction/Supervision',
    'summary': '工程相關單位分類標籤、證照資料與技術聯絡人管理',
    'description': """
工程監造系統 - 工程相關單位管理
================================

此模組提供工程相關單位的擴展管理功能：

主要功能
--------
* 工程單位分類標籤 (樹狀結構)
* 廠商證照資料管理與過期提醒
* 技術聯絡人管理
* res.partner 工程欄位擴展
* 營造廠商等級分類
* 工程表現評鑑資訊

分類體系
--------
* 業主 (政府機關/國營事業/民間企業)
* 施工廠商 (總承包商/專業分包商/供應商)
* 監造單位 (建築/結構/機電監造)
* 設計單位 (建築師/結構技師/機電技師事務所)
* 政府部門 (主管機關/消防/環保單位)
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'contacts',
        'construction_supervision_base',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/partner_category_data.xml',
        # Views
        'views/supervision_partner_category_views.xml',
        'views/partner_license_views.xml',
        'views/partner_technical_contact_views.xml',
        'views/res_partner_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 送審管制模組',
    # 附件自動歸類：掛 supervision.attachment.mixin，上傳的附件自動帶所屬工程與文件分類
    # 1.3.0: 計畫書管制表項次自動編號與唯一性檢查
    # 1.4.0: 新增 review_document_no（審查函號）——來源管制表的「審查日期」格子
    #        是「日期＋監造審查發文字號」兩行，舊版只接得住日期，
    #        文號只能擠進審查意見（把真正的審查意見擠掉）或丟掉。
    'version': '18.0.1.4.0',
    'category': 'Construction/Review',
    'summary': '工程監造材料送審管制與追蹤',
    'description': """
工程監造系統 - 送審管制模組
============================

此模組提供工程材料送審管制功能：

主要功能
--------
* 送審管制 - supervision.review.application
* 計畫書管制表 - supervision.plan.control
  (監造計畫、職安衛計畫、整體施工/品質計畫、營造綜合保險等的送審與核定追蹤；
  欄位結構同時可容納分項計畫與施工圖送審，目前只啟用計畫書)
* 材料型錄、樣品、測試報告送審追蹤
* 審查結果管理 (合格/條件式通過/不合格)
* 廠驗與取樣試驗管理
* 歸檔編號管理

技術特點
--------
* 完整狀態流程 (draft -> submitted -> reviewing -> approved/rejected)
* 送審日期追蹤 (預定/實際)
* 支援多種送審資料類型
* 附件管理
* 多公司資料隔離
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
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/review_application_views.xml',
        'views/plan_control_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 15,
}

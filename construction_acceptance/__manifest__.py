# -*- coding: utf-8 -*-
{
    'name': '工程驗收與結案管理',
    'version': '18.0.1.0.0',
    'category': 'Construction',
    'summary': '初驗、正驗、驗收缺失追蹤、結案處理',
    'description': """
工程驗收與結案管理模組
======================

此模組提供工程專案的驗收與結案功能：

主要功能
--------
* 初驗 (acceptance.preliminary)
    - 工程竣工後的初次驗收
    - 驗收人員、日期、結果記錄
    - 缺失發現與改善期限設定
    - 支援部分合格與不合格

* 正驗 (acceptance.final)
    - 初驗缺失改善後的正式驗收
    - 必須基於初驗結果
    - 最終驗收結果判定
    - 驗收合格證明產生

* 驗收缺失追蹤 (acceptance.defect)
    - 初驗/正驗發現的缺失追蹤
    - 改善期限與進度管理
    - 覆驗記錄
    - 逾期自動警示

* 結案處理 (project.closure)
    - 驗收合格後的結案程序
    - 保固期設定與管理
    - 結案文件檢核
    - 保留款退還追蹤

設計說明
--------
* 獨立的驗收缺失模型 (acceptance.defect)，與施工階段的缺失改善 (general/reservation.defect.improvement) 區分
* 完整的狀態流程與審核機制
* 支援多公司架構（設計監造/施工廠商分離）
    """,
    'author': 'Construction Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_payment',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/acceptance_preliminary_views.xml',
        'views/acceptance_final_views.xml',
        'views/acceptance_defect_views.xml',
        'views/project_closure_views.xml',
        'views/supervision_project_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

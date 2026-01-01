# -*- coding: utf-8 -*-
{
    'name': '工程成本分析',
    'version': '18.0.1.0.0',
    'category': 'Construction',
    'summary': '成本分析報表與損益追蹤',
    'description': """
工程成本分析模組
================

此模組提供工程專案的成本分析功能：

主要功能
--------
* 成本分析報表 (cost.analysis.report)
    - 分析契約金額 vs 實際執行金額
    - 計算各工項損益
    - 支援多維度分析 (按工項/按廠商/按月份)

* 成本分析摘要 (cost.analysis.summary)
    - 按專案彙總的成本分析
    - 契約金額、變更金額、現行契約金額
    - 執行率與估驗率追蹤
    - 預估損益分析

技術特點
--------
* 使用資料庫視圖 (_auto = False) 實作
* 即時計算，無需資料同步
* 支援 Pivot 與 Graph 視圖分析
    """,
    'author': 'Construction Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_payment',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Views
        'views/cost_analysis_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

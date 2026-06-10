# -*- coding: utf-8 -*-
{
    'name': '成本分析',
    'version': '18.0.2.0.0',
    'category': 'Construction',
    'summary': '成本分析與價格比對',
    'description': """
成本分析模組
========================

此模組提供工程專案的成本分析功能：

主要功能
--------
* 成本分析 (cost.analysis)
    - 從既有專案或 XML 標單匯入工項
    - 自動比對價格庫，計算差異百分比
    - 5 級差異警示（0-5%, 5-10%, 10-20%, 20-30%, >30%）
    - 計算總預算估價（基於系統建議單價）
    - 支援樹狀工項結構

技術特點
--------
* 多公司隔離：每個公司獨立的成本分析
* 價格庫整合：自動比對建議單價
* 父子工項支援：樹狀結構 (_parent_store)
* 即時計算：差異分析自動更新
    """,
    'author': 'Construction Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_price_library',
        'uom',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        'security/security.xml',
        # Views
        'views/cost_analysis_views.xml',
        'views/cost_analysis_wizard_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

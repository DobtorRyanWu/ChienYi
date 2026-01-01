# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 樣板設定',
    'version': '18.0.1.0.0',
    'category': 'Construction/Supervision',
    'summary': '文件樣板管理與設定',
    'description': """
工程監造系統 - 樣板設定模組
============================

此模組提供文件樣板管理功能：

主要功能
--------
* 文件樣板管理 (document.template)
* 支援多種樣板類型：施工日誌、自主檢查、缺失改善、進度表、估驗計價表等
* 系統預設樣板與專案自訂樣板
* 樣板上傳、下載、測試功能
* 欄位對照表設定 (JSON 格式)

技術特點
--------
* 多層級樣板優先順序：專案專屬 > 公司預設 > 系統預設
* 支援 Excel/Word 樣板格式
* 完整的權限控制
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/document_template_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 50,
}

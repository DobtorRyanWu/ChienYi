# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 檢試驗管理模組',
    'version': '18.0.1.0.0',
    'category': 'Construction/Test',
    'summary': '工程監造檢試驗項目管理與管制記錄',
    'description': """
工程監造系統 - 檢試驗管理模組
============================

此模組提供工程檢試驗管理功能：

主要功能
--------
* 檢試驗項目管理 (supervision.test.standard)
  - 試驗工項/材料設定
  - 依據方法與規範要求
  - 頻率與下限設定
  - 取樣規則與條件
  - 關聯契約工項

* 檢(試)驗管制記錄 (supervision.test.record)
  - 材料進場記錄
  - 取樣記錄與累計統計
  - 抽驗人員記錄
  - 試驗結果判定
  - 歸檔編號管理
  - 檢驗報告附件

技術特點
--------
* 自動計算累計進場數量與累計取樣數量
* 自動計算取樣率
* 支援多公司資料隔離
* 完整的狀態追蹤

舊系統對應
--------
* testStandard -> supervision.test.standard
* testRecord -> supervision.test.record
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
        'views/test_standard_views.xml',
        'views/test_record_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

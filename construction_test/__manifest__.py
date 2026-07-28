# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 檢試驗管理模組',
    'version': '18.0.1.2.0',
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
        'construction_daily_log',
        'construction_photo',
        'mail',
    ],
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',  # 定期任務
        'data/mail_activity_data.xml',  # 活動類型
        'data/formula_template_data.xml',  # 公式範本預建資料
        # Wizard
        'wizard/check_test_requirement_wizard_views.xml',
        'wizard/apply_formula_template_wizard_views.xml',
        # Views
        'views/test_formula_template_views.xml',  # 公式範本庫
        'views/test_standard_views.xml',  # 定義 action_test_standard
        'views/test_record_views.xml',    # 定義 action_test_record
        'views/test_warning_views.xml',   # 定義 action_test_warning（預警通知）
        'views/menu.xml',                 # 定義 menu_test_management_root，參照上述 actions
        'views/test_task_statistics_views.xml',  # 參照 menu_test_management_root
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

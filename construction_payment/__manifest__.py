# -*- coding: utf-8 -*-
{
    'name': '工程計價與請款管理',
    # 1.1.0: 併入 GitHub 上游修正 b9677e4 —— previous_approved_qty 納入 archived 估驗
    #        （archived 是「已核定後歸檔」，數量仍有效；原本只認 approved，
    #        前期估驗一歸檔，後期「前期已核定累計」就漏掉該期數量）
    # 附件自動歸類：掛 supervision.attachment.mixin，上傳的附件自動帶所屬工程與文件分類
    # 1.3.0: 移除 payment.estimate.slip_id —— 估驗計價與通報單在功能上無關
    #        （計價表是契約詳細價目表 × 期別的鏡像，通報單不出現在計價單上；
    #          一期橫跨多張通報單、一張通報單的量也會被切到多期，任何單值/多值
    #          關聯都表達不了）。匯入精靈的預約式分支一併移除，兩式行為一致。
    #        通報單的 valuation_count 改為「本工程已估驗次數」（工程層級）。
    #        ⚠ DB 的 payment_estimate.slip_id 欄位不會被 Odoo 自動刪除，
    #          升級後會留成孤兒欄位（全 NULL，無外鍵行為影響），可日後手動清理。
    'version': '18.0.1.3.0',
    'category': 'Construction',
    'summary': '估驗計價、工項驗收、請款管理',
    'description': """
工程計價與請款管理模組
======================

此模組提供工程專案的計價與請款功能：

主要功能
--------
* 估驗計價 (payment.estimate)
    - 分期估驗計畫與累計追蹤
    - 施工廠商提交，監造審查
    - 預算 vs 實際對比分析

* 工項驗收 (work.acceptance)
    - 監造驗收施工廠商完成的工項
    - 支援部分驗收與完工驗收
    - 驗收通過後可提交估驗計價

* 請款單 (payment.claim)
    - 向業主（政府機關）請款
    - 支援服務費（監造）和工程款（廠商）
    - 基於估驗計價或驗收單產生

設計說明
--------
* 不依賴 purchase 模組，獨立設計驗收與請款流程
* 支援多公司架構（設計監造/施工廠商分離）
* 完整狀態流程與審核機制
    """,
    'author': 'Construction Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_daily_log',
        'construction_contract_change',
        'construction_notification_slip',
        'construction_progress',
        'mail',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Wizard
        'wizard/progress_activate_wizard_views.xml',
        # Views
        'views/estimate_import_wizard_views.xml',
        'views/payment_estimate_views.xml',
        'views/work_acceptance_views.xml',
        'views/payment_claim_views.xml',
        'views/supervision_project_views.xml',
        'views/estimate_sync_wizard_views.xml',
        'views/menu.xml',
        'report/payment_estimate_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

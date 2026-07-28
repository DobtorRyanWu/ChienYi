# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 品質管理模組',
    # 3.0.1: 預約式檢查項目清單補回 check_item 欄（required 且無 default，
    #        不在清單中會導致後台「加入資料行」因 not-null 而無法儲存）
    # 3.0.0: 查驗階段改為每類型可設定的段落主檔 self.inspection.type.stage；
    #        三個 item 的 stage(Selection) 改名為 stage_id(Many2one)，舊欄位暫留待下版清除
    # 2.2.2: 逾期排程上收 mixin（一般式/預約式行為一致），補上預約式缺失的 ir.cron
    # 2.2.1: post-migration 清 NCR 的 DB 殘留（DROP 4 張表 + ir_model_data 孤兒）
    # 2.2.0: daily_defect_mixin 新增 source_description（來源登錄編號）；移除 NCR(supervision.defect)
    'version': '18.0.3.0.1',
    'category': 'Construction/Quality',
    'summary': '工程監造品質管理、缺失追蹤與自主檢查',
    'description': """
工程監造系統 - 品質管理模組
============================

此模組提供工程品質管理功能：

主要功能
--------
* 缺失改善 - general/reservation.defect.improvement（共用 construction.daily.defect.mixin）
* 自主檢查類型管理 - self.inspection.type
* 一般式自主檢查 - general.self.inspection
* 預約式自主檢查 - reservation.self.inspection
* 預約式缺失改善 - reservation.defect.improvement

技術特點
--------
* 缺失完整狀態流程 (draft -> notified -> improving -> improved -> verified -> closed)
* 支援照片附件上傳
* 逾期追蹤與警示
* 多公司資料隔離
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_photo',
        'construction_notification_slip',  # reservation_defect/inspection 用 Many2one('reservation.notification.slip')
        'mail',
    ],
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',  # 預約式缺失逾期狀態更新與通知
        # Views
        'views/defect_improvement_prefix_config_views.xml',
        'views/self_inspection_type_views.xml',
        'views/self_inspection_type_copy_wizard_views.xml',
        'views/general_self_inspection_views.xml',
        'views/reservation_self_inspection_views.xml',
        'views/reservation_defect_improvement_views.xml',
        'views/menu.xml',
        'report/self_inspection_report.xml',
        'report/reservation_defect_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

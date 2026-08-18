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
    # 3.1.0: 預約式缺失照片刪不掉修正（與 construction_general 同構的 5 處）
    # 3.2.0: 預約式缺失 unlink() 補「只有草稿可刪」狀態保護（一般式早有，預約式缺 →
    #        可整張刪掉已結案缺失，繞過前台「已驗證/結案不可刪單張照片」的限制）
    # 4.0.0: 照片收斂 —— 移除 reservation.defect.improvement.photo 照片行模型、
    #        兩個 legacy M2M 與兩個自主檢查的照片 M2M；全部改指 supervision.photo
    # 4.1.0: 自主檢查與預約式缺失的後台照片頁籤加上批次上傳精靈按鈕
    # 4.2.0: 預約式自主檢查／預約式缺失的照片，座標兜底改借所屬通報單的
    #        施工地點（比工程案件中心點精確）
    # 4.3.0: 照片頁籤改用共用看板；預約式缺失三階段改垂直排列（原本 group 預設兩欄造成「一左一右」）
    # 4.4.0: 照片頁籤關掉無效的「加入」按鈕（只能建空白記錄、傳不了檔）
    # 4.5.0: 自主檢查類型未儲存時選不到查驗段落 —— 段落加 item_ids 反向關聯，
    #        改從段落底下直接編輯檢查項目（純巢狀 o2m，不經伺服器 name_search）；
    #        item.create() 自動由 stage_id 補 type_id
    # 4.6.0: 兩式自主檢查移除 contractor_company_id（Many2one res.company）——
    #        一庫一公司下那個下拉永遠只有一個選項，反而誘導填表的人把協力廠商填進去。
    #        contractor_name 改為 compute + store + readonly=False，預設帶入工程案件的
    #        contractor_company_name、允許逐筆覆寫（depends 只掛 project_id，工程改名
    #        不回頭蓋掉已填值）。同時預約式缺失 source_type 補回 supervision（監造抽查），
    #        補齊後兩式只差預約式獨有的 slip
    # 4.7.0: 移除兩式自主檢查的 subcontractor_name（協力廠商）—— 無效欄位，
    #        兩式 DB 各 0 筆填值。不需資料 migration（沒有值要保留），欄位由
    #        Odoo 的 _process_end 自行 drop。列印報表的承攬廠商改為 colspan="3"
    # 4.8.0: 預約式自主檢查補上 overall_result（整體結果，與一般式同構）——
    #        原本只有一般式有，導致預約式專案的「自主檢查總表」試驗結果
    #        合格/不合格整欄空白（mappings/self_inspection.py 讀不到該欄）。
    #        list / form / search 一併對稱
    # 4.9.0: 兩式自主檢查的 inspection_timing 補上 random（隨機抽查）——
    #        紙本表單的「檢查時機」是「□檢驗停留點 □隨機抽查」一組，
    #        舊值域只有停留點、沒有隨機，導致廠商自主檢查表搬進來時
    #        勾「隨機抽查」的那幾張會被 ValueError 擋下（P11001 實例 6/27 張）。
    #        兩式同步新增，不需 migration（只是值域變大）。
    'version': '18.0.4.9.0',
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

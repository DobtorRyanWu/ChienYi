# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 通報單管理',
    # 1.1.1: 修正驗收動作寫入不存在的狀態值 'completed'（會 ValueError）與
    #        slip_id domain 的 'approved'；狀態值域為 draft/not_started/in_progress/closed
    # 1.2.0: 新增通報單經緯度欄位（含範圍 constrains）。通報單照片沒有 GPS EXIF 時
    #        會沿用這組座標，現場人員不必逐張手填
    # 2.0.0: 照片收斂 —— related_photo_ids 改成真 One2many（同檢試驗）
    # 2.1.0: 後台「關聯照片」頁籤補上批次上傳入口（原本只有唯讀反查，完全無法上傳）
    # 2.2.0: 關聯照片改用共用看板
    # 2.3.0: 同上，關掉照片頁籤的「加入」按鈕
    # 2.4.0: 補上三個「只印得出來、後台卻沒有輸入格」的欄位：
    #        location_detail（詳細位置說明）進基本資訊；item_no（項目編號，required 卻
    #        完全不在 UI 上）與 specification（規格說明，optional）進施工詳細表
    # 2.5.0: 施工地點座標改為在欄位前標出「緯度：」「經度：」（原本兩格並排、
    #        只靠 placeholder 分辨，UI 上看不出前後哪個是哪個）；
    #        valuation_count 改名「本工程已估驗次數」並改為工程層級
    #        （估驗計價與通報單無關聯，見 construction_payment 1.3.0）
    # 2.6.0: 修正清單依工程分組時，「通報單次數」欄位被當成金額加總
    #        （82 次通報單顯示成 3,367 次）。slip_no 是序號不是量，改 aggregator=False
    'version': '18.0.2.7.0',  # 2.7.0: 施工詳細表可選彙總項（選葉節點自動補齊祖先），金額改「有子列加總／無子列手填／葉節點數量×單價」三分支，結算金額只加總根列，新增明細預估合計與不符示警。
    'category': 'Construction/Supervision',
    'summary': '預約式工程通報單管理模組',
    'description': """
工程監造系統 - 通報單管理
==========================

此模組提供預約式工程的通報單管理功能：

主要功能
--------
* 通報單管理 (reservation.notification.slip)
* 通報單明細 (reservation.notification.slip.line)

技術特點
--------
* 預算追蹤 (planned vs actual)
* 4 階段狀態流程（草稿→未開始→施工中→已結案）
* 整合工程範疇量預估
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_photo',
        'mail',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/notification_slip_views.xml',
        'wizard/add_slip_line_wizard_views.xml',
        'views/menu.xml',
        'report/notification_slip_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

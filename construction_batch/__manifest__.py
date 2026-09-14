# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    'name': '工程監造系統 - 批次操作',
    # 2.7.3: 修「設了日期區間 + 有記錄日期空白時，按下載跳 UncaughtPromiseError」——
    #        _get_download_action() 缺 views，被塞進 display_notification 的 next 後
    #        不會經過 clean_action 補值，前端 action.views.map 直接掛掉
    'version': '18.0.2.8.0',  # 2.8.0: 下載中心新增「自主檢查表（單張）」——一張檢查紀錄一份 Word、多筆打包 zip。它與既有類型有兩點不同：(a) 模型是動態的（一般式/預約式由工程案件的 project_type 決定），所以新增 _record_model() 當單一入口，_get_record_domain/_get_records/_date_source 全部改用它；(b) 樣板來自檢查類型上傳的檔而非 document.template，所以不能沿用「一個專案查一次樣板」的快取，改為逐筆呼叫render_inspection_form()。另外它不提供手動選取（兩式是不同模型，一個 M2M 裝不下），field=None，相關三處都補了 None 判斷。 2.7.2: 預覽摘要拿掉多餘的日期欄位備註
    'category': 'Construction/Supervision',
    'summary': '報表 / 下載中心：各式正式表單的統一下載入口',
    'description': """
批次操作模組
============

「報表 / 下載」中心，把散落在各表單 header 的樣板匯出收攏成單一入口。

主要功能
--------
* 批次下載精靈 (batch.download.wizard)，支援 10 種下載類型：
    - 通報單（預約式工程施工回報單）
    - 施工日誌（監造日報表一/二、施工日誌一/二營造版）
    - 送審管制表
    - 計畫書管制表（計畫書送審管制總表，含工程保險）
    - 自主檢查（自主檢查總表）
    - 缺失改善（缺失管制表、矯正與預防處理紀錄）
    - 檢(試)驗管制紀錄（全案彙總表）
    - 估驗計價表（計價單、估驗詳細表、估驗照片）
    - 進度報告（general.progress.report）
    - 工程預定進度表（只帶工程名稱與工期，工項需自行填寫）

* 支援功能
    - 日期區間篩選（透過 context 傳給 construction_template 的對照表）
    - 輸出格式：正式表單（樣板套印）／清單彙總（Excel）
    - 多筆自動 ZIP 打包

設計說明
--------
* 正式表單一律呼叫 construction_template 的 get_template_for_report()
  與 template_render.render()，與各表單 header 匯出按鈕走同一條路，
  不自行產生版面
* 使用 TransientModel 精靈模式
    """,
    'author': 'Engineering Supervision System',
    'website': 'https://github.com/engineering-supervision',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_daily_log',
        'construction_payment',
        # 樣板套印引擎（正式表單的產出全靠它）
        'construction_template',
        # 下列模組提供各下載類型的資料來源模型。不宣告的話，使用者選到該類型
        # 才會在 runtime 炸 KeyError，而不是安裝時就擋下來。
        'construction_general',       # general.progress.report / 一般式缺失
        'construction_quality',       # 自主檢查、預約式缺失
        'construction_test',          # supervision.test.record
        'construction_review',        # supervision.review.application
        'construction_notification_slip',   # reservation.notification.slip
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Wizards
        # 預覽的 view 要先載入：batch_download_wizard 的 action_preview() 用 env.ref
        # 取它的 id，而精靈自己的 view 沒有這個相依關係
        'wizard/batch_download_preview_views.xml',
        'wizard/batch_download_wizard_views.xml',
        # Views
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 50,
}

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
    # 5.0.0: 🔴 兩式自主檢查的「檢查時機」由單選 Selection 改為複選，
    #        且選項不再寫死、改掛在檢查類型底下（self.inspection.type.timing）。
    #        起因：紙本表頭那一列實際上會同時勾多個（111年度西區水利 逸峰營造
    #        裂縫修補表：施工中＋施工完成），舊模型只能存一個，第二個靜靜掉。
    #        改成逐類型一組而非全域主檔，是因為各家表格的選項組與「用字」都不同：
    #        逸峰印「施工完成檢查」、川易（淡五號疏散門）印「施工後檢查」、
    #        監造抽查類則整組換成「查驗停留點／隨機抽查」。全域主檔要裝下這些，
    #        清單裡會同時躺著兩個近乎同義的選項，而且每張表單都看得到全部。
    #        檢查類型本身已有 project_id，故「不同工程選項不同」自然成立。
    #        新類型預設帶原本那 5 個（DEFAULT_TIMINGS），可自行增刪改字。
    #        跨工程穩定鍵是 code（hold_point/random/before/during/after），
    #        匯入與 migration 都認它，name 允許各類型自行改字。
    #        附 migrations/18.0.5.0.0（pre 抄舊欄、post 補預設並回填 M2M）。
    #        ⚠️ 舊欄位 default='during' 一併移除：沒填就是沒填，
    #        不要讓「沒填」被靜靜翻譯成「施工中檢查」。
    # 5.1.0: 🔴 檢查時機的匯入鍵改回「名稱」，`code` 降級為 `legacy_code`。
    #        5.0.0 把 code 做成「匯入用的穩定鍵」還顯示在畫面上，等於要求使用者
    #        替每個自訂時機想一個代碼並記住它，否則那個選項永遠匯不進來
    #        （留空的 code 沒有任何 _timing_codes 指得到）——做出一個
    #        「看得到、匯不進」的選項。
    #        同一支檔案裡的查驗段落 self.inspection.type.stage 根本不是這樣做的：
    #        legacy_code 明寫「資料遷移用，手動新增請留空」，匯入一律用段落名稱
    #        解析（3_匯入_引擎.py 的 stage_map()）。檢查時機沒有理由不同。
    #        改：欄位 code → legacy_code（string 舊代碼、copy=False、清單
    #        column_invisible，全部比照 stage）；匯入改以名稱解析、舊代碼作為
    #        相容備援；範本欄位 _timing_codes → _timing_names。
    #        附 migrations/18.0.5.1.0/pre-migrate.py（純欄位＋約束改名，不動資料）。
    # 6.0.0: 自主檢查新增「量測區塊」—— 紙本檢查項目表格**外面、下方**那一段
    #        （鋼筋組立抽查情形：1.丈量___位置，長___cm…□合格□不合格，預印 4 列）。
    #        掃 797 份自主檢查原生檔：27 種檢查表裡只有鋼筋有，但同一種鋼筋表
    #        三個案子三種寫法（檢附/請附/檢查照片、4 列 vs 3 列、逗號有無），
    #        所以標題／句型／列數三個都是資料，不寫死。
    #        三個新模型：self.inspection.type.measure（區塊定義，掛檢查類型、可多個）
    #        ＋ general/reservation.self.inspection.measure.line（量測列，
    #        共用 self.inspection.measure.line.mixin）。
    #        🔴 每一列存**句型快照**：日後改句型不會讓舊資料的欄位位移
    #        （values 是位置對應的，位移不會報錯）。
    #        🔴 result 必填、無預設值（不重演 check_result 預設 pass 的假性合格）。
    #        🔴 值的個數必須等於句型空格數，不符即擋（少一個就整句位移）。
    #        量測列的「不合格」計入 has_defect / defect_count / overall_result；
    #        缺失單精靈只能從檢查項目建，故補上「有缺失但無可選項目」的說明。
    #        空列＝沒有記錄：紙本預印 4 列實填 2 列就只存 2 列，列印也只印 2 列。
    # 6.0.2: 移除 slot_hint（①②③ 提示欄）—— 「填寫內容」空白時本來就顯示成
    #        「丈量＿＿位置，長＿＿cm」，有幾個 ＿＿ 就是要填幾格、位置也看得出來，
    #        那一欄是多餘的（使用者實測指出）。連同 SLOT_MARKS / slot_mark /
    #        numbered_template / slot_placeholder 四個 helper 一併清掉
    #        （最後一個從頭到尾沒被用過）。
    # 6.0.1: 使用者實測量測區塊打出三個缺陷：
    #        ① 量測區塊頁籤移到「預設檢查項目」之後。
    #        ② 🔴 後台清單新增一列直接撞「未設置必填欄位 template」——
    #           清單上只會選 block_id，沒有人填句型快照。照 1.7.0 的教訓做兩層：
    #           onchange 給畫面即時反應、create()／write() 才是權威。
    #           ⚠️ 修這個又打出第四個：write() 只換句型、沒同步對齊 values 的格數
    #           → 2 格的值配 3 格的新句型直接撞 _check_values_length。
    #           已改成換句型時值一併對齊（依位置保留、不足補空、超過截掉）。
    #        ③ 🔴 填寫時看不出要填什麼、幾格 → values_text 的反寫改成
    #           **不足補空、超過擋下**（只打 123 給 2 格的句型原本會報驗證錯誤）。
    #           ⚠️ 匯入那條路直接寫 values，不經過這個容錯，維持嚴格比對。
    'version': '18.0.6.0.2',
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

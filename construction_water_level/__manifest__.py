# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 水位監測',
    # 1.0.0: 水位監測站主檔 + 水位紀錄 + 後台圖表 + 地圖點選座標 widget
    #        + 對外上報端點（本系統第一支 auth='none' 路由，防護見 controllers/ingest.py）
    # 2.0.0: 新增「監測場域」層，同時服務社區蓄水池與工程案件河川；
    #        device.project_id 的 ondelete 從 cascade 改 restrict（cascade 會連坐刪掉水位紀錄）；
    #        Portal 老闆 rule 收斂成只看工程場域（原本 [(1,'=',1)] 會看到所有社區資料）
    # 2.1.0: 社區場域加前台成員制（member_user_ids）與四條社區 record rule，
    #        供 construction_portal 的社區水情頁使用
    # 2.2.0: 後台地圖（場域／蓄水池／監測站三個 leaflet_map view，標記依狀態上色）
    # 2.3.0: 改走 pull —— 新增可換來源的適配層（http_json／postgres／file_json）、
    #        欄位對應表、時間模式缺號偵測；push 端點保留，兩種並存
    # 2.4.0: 告警外送通道 —— _notify 除了站內 chatter，另把告警送出系統外
    #        （Webhook 先行，LINE／簡訊日後加一個 _send_ 方法即可）；
    #        含送達紀錄、每小時上限與失敗重送 cron
    # 2.5.0: 示範資料合成器 —— 新增第四種來源型態 demo_synth，拿已匯入的歷史真值
    #        當樣本合成擬真讀數（決定性、可重算），供真設備接上前的展示使用；
    #        場域／監測站／來源加 is_demo 標示；
    #        修正保存稽核寫死 1440 筆/日（改依各站 expected_interval_min 換算）；
    #        device 表單補上 source_id／remote_key／expected_interval_min
    #        （這三個欄位原本不在表單上，只能用 shell 設定）
    # 2.6.0: 監測站可向鄰站借水文形狀（demo_baseline_device_id）——自己沒有歷史的站
    #        （例如工地現場站）拿鄰近測站的真實歷史當基線，斷面高程差走既有的
    #        datum_elevation，合成器內部全程留在被借那台的值域；
    #        場域加代表站（primary_device_id），前台水情頁預設顯示它；
    #        基線日期規則收斂成 demo_synth.baseline_key() 一份（原本兩處各寫一份）
    # 2.7.0: 監測站加「地圖標籤」（map_label）——前台地圖的標記本來顯示 seq 這個整數，
    #        對看畫面的人沒意義；留空時沿用舊行為，所以是安全的擴充
    # 2.7.1: 狀態型告警（斷線／失電／線路切換）恢復後自動結案——原本只開不關，
    #        生產站曾出現「資料早就回來了，critical 斷線事件還掛著 21 小時」；
    #        水位越線刻意不自動關，那是災情事件要有人複核
    'version': '18.0.2.7.1',
    'category': 'Construction/Supervision',
    'summary': '水位監測站主檔、時序水位紀錄與設備上報端點',
    'description': """
工程監造系統 - 水位監測
========================

提供工程案件底下的水位監測站管理與時序水位紀錄。

主要功能
--------
* 水位監測站 (water.level.device)：掛工程案件、上下游序、經緯度、三級警戒水位
* 水位紀錄 (water.level.reading)：時序資料，(監測站, 時間) 唯一
* 設備上報端點 POST /water-level/ingest（契約見 docs/PAYLOAD_CONTRACT.md）
* 後台地圖點選座標 widget（latlng_map_picker）

技術特點
--------
* 警戒分級依經濟部水利署河川水位警戒：三級 → 二級 → 一級（數字越小越嚴重）
* 水位等級為 stored compute（純函數）；斷線判定即時計算不落地，避免狀態過期
* 上報寫入走 execute_values + ON CONFLICT DO NOTHING，重送不會產生重複資料
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'construction_supervision_base',
        'web_leaflet_lib',
        'web_view_leaflet_map',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        'security/water_level_security.xml',
        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        # Views
        'views/water_level_site_views.xml',
        'views/water_level_tank_views.xml',
        'views/water_level_views.xml',
        'views/water_level_map_views.xml',
        'views/water_level_source_views.xml',
        'views/water_level_event_views.xml',
        'views/water_level_gap_views.xml',
        'views/water_level_integrity_views.xml',
        'views/water_level_alert_channel_views.xml',
        'views/menu.xml',
        # Report
        'report/water_level_event_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_water_level/static/src/js/latlng_map_picker.js',
            'construction_water_level/static/src/xml/latlng_map_picker.xml',
            'construction_water_level/static/src/css/latlng_map_picker.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

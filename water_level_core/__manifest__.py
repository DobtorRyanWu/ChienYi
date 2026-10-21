# -*- coding: utf-8 -*-
{
    'name': '水位監測核心',
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
    #        水位越線刻意不自動關，那是災情事件要有人複核（3.2.0 起改為恢復後自動結束）
    # 3.0.0: 拆成三個模組——本模組（水位核心，不依賴任何工程模組）＋
    #        construction_water_level（工程案件場域）＋ community_water_level（社區蓄水池）。
    #        模型、資料表、欄位一律不動，只換「歸屬模組」：既有庫升級時由 hooks.py 的
    #        pre_init_hook 把 xmlid 從 construction_water_level 改掛到這裡，cron 的啟用
    #        狀態與事件序號因此原樣保留（見 hooks.py 檔頭）。
    #        前台水位圖表的 JS／CSS 從 construction_portal 搬進來，工程頁與社區頁共用。
    # 3.1.0: 告警分「千溢內部（所有方案）／客戶（旗艦）」兩種對象；新增 Discord 通道
    # 3.2.0: 水位越線事件在水位連續 3 筆回到正常後自動結束（社區與工程都套用，複核另按）；
    #        再越線一律開新事件，外送限速：同設備同類 60 分鐘內已外送過、等級沒升高就不外送（站內通知照發）；
    #        日摘要改用台灣日切分、每天重算最近 7 天，升級時整批重算（migrations/18.0.3.2.0）
    'version': '18.0.3.2.0',
    'category': 'Services/Water Level',
    'summary': '監測場域、監測站、時序水位紀錄、雜湊鏈稽核、告警與設備上報端點',
    'description': """
水位監測核心
============

不依賴任何工程模組的水位監測底座。工程案件與社區蓄水池由兩個擴充模組各自補上：

* construction_water_level：場域綁工程案件（project.project），前台走工程成員
* community_water_level：場域綁管委會（res.partner），蓄水池與儲水率，前台走場域成員
  （2026-10-21 起是獨立專案 water-odoo，不在本 repo；ChienYi 的庫只裝核心＋工程）

主要功能
--------
* 監測場域 (water.level.site)、監測站 (water.level.device)、三級警戒水位（高／低）
* 水位紀錄 (water.level.reading)：純追加、(監測站, 時間) 與 (監測站, 序號) 唯一
* 序號缺口、雜湊鏈驗證、保存期間稽核、日摘要、告警事件與外送
* 設備上報端點 POST /water-level/ingest（契約見 docs/PAYLOAD_CONTRACT.md）
* 資料來源適配層（pull）、示範資料合成器

權限
----
* 水位監測管理員（本模組）：完整權限
* 內部使用者：讀寫主檔、唯讀紀錄
* 前台（portal）：本模組**不給任何權限**，由擴充模組連同 record rule 一起給
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web_leaflet_lib',
        'web_view_leaflet_map',
    ],
    'data': [
        # Security
        'security/water_level_groups.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        # Views
        'views/water_level_site_views.xml',
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
            'water_level_core/static/src/js/latlng_map_picker.js',
            'water_level_core/static/src/xml/latlng_map_picker.xml',
            'water_level_core/static/src/css/latlng_map_picker.css',
        ],
        # 前台水位圖表（工程頁與社區頁共用）。Chart.js 不進 bundle，由頁面 JS 動態載入；
        # Leaflet 與 construction_portal 列同一組路徑，Odoo 組 bundle 時同路徑只收一次。
        'web.assets_frontend': [
            '/web_leaflet_lib/static/lib/leaflet/leaflet.css',
            '/web_leaflet_lib/static/lib/leaflet/leaflet.js',
            'water_level_core/static/src/css/water_level_frontend.css',
            'water_level_core/static/src/js/water_level_frontend.js',
        ],
    },
    'demo': [],
    # 既有庫（裝過 construction_water_level 2.x）升級時把歸屬改掛過來；空庫安裝時是 no-op
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 10,
}

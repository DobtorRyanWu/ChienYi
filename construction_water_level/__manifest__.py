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
    'version': '18.0.2.3.0',
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

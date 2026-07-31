# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 地理資訊整合',
    # 1.2.0: 移除「進階照片地圖」的入口（使用者決策）。該功能是日後某些功能的
    #        基石，但本體尚不完善，不應讓使用者在 ⚙️動作 下拉點得到。
    #        做法：把 views/photo_map_action.xml 移出 data（Odoo 升級時會自動
    #        清掉它建立的 client action 與 server action），並移出對應的 assets。
    #        **static/src 下的 js / xml / css 三個檔案刻意保留**，日後要重啟這個
    #        功能時只要把 data 與 assets 兩處加回來即可。
    # 1.1.0: （已被 1.2.0 取消）曾補上 photo_map_action 的 JS/XML 資產。
    'version': '18.0.1.2.0',
    'category': 'Construction/Supervision',
    'summary': '將工程照片整合至 GeoEngine 地圖視圖',
    'license': 'LGPL-3',
    'depends': [
        'construction_photo',
        'base_geoengine',
        'web_leaflet_lib',
    ],
    'data': [
        'views/supervision_photo_geo_views.xml',
        'views/photo_map_view.xml',
        # 'views/photo_map_action.xml',   ← 刻意停用（1.2.0）：這支會建立
        #   client action(tag='photo_map_action') 與綁在 supervision.photo 的
        #   server action。功能本體尚不完善，先不讓使用者看得到入口。
        #   檔案保留在 views/ 下，日後完善後把這行取消註解即可。
    ],
    'assets': {
        'web.assets_backend': [
            'construction_geoengine/static/src/css/photo_map_action.css',
            'construction_geoengine/static/src/js/photo_map_view.js',
            'construction_geoengine/static/src/xml/photo_map_view.xml',
            # 'construction_geoengine/static/src/js/photo_map_action.js',
            # 'construction_geoengine/static/src/xml/photo_map_action.xml',
            #   ↑ 與上面的 data 條目成套停用。photo_map_view（列表右上的
            #     第 5 個檢視鈕）是另一個功能，不受影響、維持啟用。
        ],
    },
    'post_init_hook': 'post_init_compute_geo_points',
    'installable': True,
    'auto_install': False,
    'application': False,
}

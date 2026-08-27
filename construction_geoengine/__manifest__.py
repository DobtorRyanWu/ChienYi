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
    # 1.2.1: 照片地圖的來源對照表（SOURCE_COLORS / SOURCE_LABELS）補上
    #        estimate（估驗計價）與 signboard（工程告示牌）、移除 acceptance，
    #        與 construction_photo 18.0.3.6.0 的 source_model Selection 同步。
    #        兩支 photo_map_*.js 都改（photo_map_action 雖停用仍保持一致）。
    # 1.3.0: 代操人員 2026-08-27 回報的三件事。
    #        (a) 地圖縮圖對非系統管理者全部破圖 —— 縮圖 URL 原本直接打
    #            /web/image/ir.attachment/<id>/datas，但 ir.attachment.check()
    #            對「res_id 為空」的附件只放行建立者與 base.group_system，
    #            其餘一律 AccessError，而 /web/image 會把它換成灰色佔位圖。
    #            改走 /web/image/supervision.photo/<id>/image 後檢查的是照片
    #            記錄本身的存取權（地圖本來就讀得到），問題消失。
    #            生產站實測：4,484 張照片有 4,373 張的附件 res_id=0。
    #        (b) 縮圖／清單／cluster popup 補上「所屬工程案件」（單點 marker
    #            popup 原本就有，其他三處沒有）。
    #        (c) 工程／標籤／分類三個 chip 的 popover 加關鍵字過濾（生產站
    #            187 個工程案件，平鋪清單捲不完）；材料分類 chip 從已停用的
    #            category Selection 改綁 category_id 主檔。
    'version': '18.0.1.3.0',
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

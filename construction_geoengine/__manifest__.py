# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 地理資訊整合',
    'version': '18.0.1.0.0',
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
        'views/photo_map_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_geoengine/static/src/css/photo_map_action.css',
            'construction_geoengine/static/src/js/photo_map_view.js',
            'construction_geoengine/static/src/xml/photo_map_view.xml',
        ],
    },
    'post_init_hook': 'post_init_compute_geo_points',
    'installable': True,
    'auto_install': False,
    'application': False,
}

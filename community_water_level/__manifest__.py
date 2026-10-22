# -*- coding: utf-8 -*-
{
    'name': '社區蓄水池水位',
    # 3.0.0: 從 construction_water_level 拆出來（版號接續，方便對照拆分前後）。
    #        蓄水池、容量曲線、場域的管委會與前台成員、社區前台水情頁（原在 construction_portal）。
    #        既有庫升級時由 hooks.py 把社區這一側的歸屬改掛過來，資料表不動。
    #        補權限洞：事件／事件影像／日摘要原本有 portal 讀取 ACL 卻沒有 record rule，
    #        改成跟著社區成員走（工程前台用不到這三個模型，jt 上那三條 ACL 會被移除）。
    'version': '18.0.4.0.0',
    'category': 'Services/Water Level',
    'summary': '社區蓄水池：儲水率換算、管委會前台水情頁',
    'description': """
社區蓄水池水位
==============

在水位監測核心（water_level_core）上補社區這一側，可以單獨上線（不需要工程監造系統）：

* 監測場域綁管委會／物業公司（res.partner），前台可見性走場域的前台成員
* 蓄水池與容量曲線：水位 → 體積 → 儲水率
* 前台 /community：管委會、物業、維護廠商用 portal 帳號看儲水率與水位歷程
* /my 首頁加「社區水情」入口
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'water_level_core',
        'portal',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/water_level_security.xml',
        'views/water_level_tank_views.xml',
        'views/water_level_views.xml',
        'views/portal_community_water_templates.xml',
        'views/portal_community_event_templates.xml',
        'views/portal_community_report_templates.xml',
        'report/community_period_report.xml',
        'data/ir_cron_line.xml',
        'views/water_level_line_views.xml',
        'views/portal_community_notification_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'community_water_level/static/src/css/community_water.css',
        ],
    },
    # 既有庫（裝過 construction_water_level 2.x）升級時把社區這一側的歸屬改掛過來；空庫安裝時是 no-op
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 20,
}

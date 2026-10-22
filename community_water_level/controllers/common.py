# -*- coding: utf-8 -*-
"""社區前台各頁共用：頁籤。

刻意寫成函式、不讓各頁的 controller 互相繼承：Odoo 的 controller 子類別會接手父類別的路由，
兩支都繼承同一個父類別時路由由誰處理就看載入順序。
"""

from odoo.addons.water_level_core.models.water_level_device import LEVEL_BASIC, LEVEL_FLAGSHIP

# (鍵, 標籤, 網址樣板, 需要的方案等級)。順序＝畫面上的順序；新功能上線時在這裡加一列
COMMUNITY_TABS = [
    ('water', '水情', '/community/%s/water', LEVEL_BASIC),
    ('events', '事件', '/community/%s/events', LEVEL_BASIC),
    ('reports', '報表', '/community/%s/reports', LEVEL_BASIC),
    ('notify', '通知', '/community/%s/notifications', LEVEL_FLAGSHIP),
]


def community_tabs(site, active):
    """這個社區看得到的頁籤。方案不含的頁籤不顯示——但路由端照樣要擋，這裡只是不給入口。"""
    return [{'key': key, 'label': label, 'url': url % site.id, 'active': key == active}
            for key, label, url, level in COMMUNITY_TABS
            if site._community_level_at_least(level)]

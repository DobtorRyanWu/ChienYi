# -*- coding: utf-8 -*-
"""地圖標記圖產生器。

`web_view_leaflet_map` 的 leaflet_map view 只吃「一個 Binary 影像欄位」當標記圖
（透過 /web/image?model=..&id=..&field=.. 取），沒有辦法用 CSS class 上色。
所以顏色要在後端畫成圖。

圖是用 Pillow 畫的小圓點，同一個顏色只畫一次就快取起來——標記只有幾種顏色，
每筆記錄各畫一張純粹是浪費 CPU。

顏色與前台 portal 的 --wb-wl-* 對齊，兩邊看到的紅黃綠是同一套語意。
"""

import base64
import io

# 與 construction_portal/static/src/css/portal_water_level.css 的 --wb-wl-* 對齊
COLOR_NORMAL = '#22b357'      # 正常
COLOR_WARN_3 = '#d68b1a'      # 三級警戒／高儲水率
COLOR_WARN_2 = '#e2660f'      # 二級警戒
COLOR_WARN_1 = '#e8364f'      # 一級警戒／嚴重缺水
COLOR_OFFLINE = '#8b90a0'     # 斷線
COLOR_NO_DATA = '#c8ccd4'     # 尚未裝表／沒有資料

# 產出的圖尺寸。view 的 marker_icon_size_x/y 要跟這個一致，不然 Leaflet 會拉伸。
MARKER_SIZE = 64
_MARKER_CACHE = {}


def marker_image(color):
    """回傳指定顏色的標記圖（base64 bytes，可直接放進 Binary 欄位）。"""
    if color in _MARKER_CACHE:
        return _MARKER_CACHE[color]

    from PIL import Image, ImageDraw

    size = MARKER_SIZE
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # 外圈白邊讓標記在任何底圖上都看得見（深色圖磚上純色圓點會糊掉）
    pad = 6
    draw.ellipse([pad, pad, size - pad, size - pad],
                 fill=color, outline='#ffffff', width=5)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue())
    _MARKER_CACHE[color] = encoded
    return encoded


def color_for_level_state(level_state, is_offline=False):
    """監測站：斷線蓋過一切（設備死掉比水位超標更常發生，也更容易被忽略）。"""
    if is_offline:
        return COLOR_OFFLINE
    return {
        'lv1': COLOR_WARN_1,
        'lv2': COLOR_WARN_2,
        'lv3': COLOR_WARN_3,
        'low1': COLOR_WARN_1,
        'low2': COLOR_WARN_2,
        'low3': COLOR_WARN_3,
    }.get(level_state, COLOR_NORMAL)

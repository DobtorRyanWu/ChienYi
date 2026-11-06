# -*- coding: utf-8 -*-
"""台灣日期 helper（公司儀表板合約 §1-6、§5.1）。

「今天」一律是台灣日期（Asia/Taipei），不隨使用者時區、也不是伺服器的 UTC 日期：
`fields.Date.today()`／`date.today()` 在容器裡是 UTC 日期，台灣 00:00–07:59 會落到前一天。
寫法照 community_water_level/utils.py 的 local_today()（另寫一份，不依賴社區模組）。
資料庫的 Datetime 一律是 naive UTC；轉換一律用 pytz 的 localize()——
`datetime(..., tzinfo=pytz 時區)` 會拿到 LMT +08:06。
"""

from datetime import datetime

import pytz

LOCAL_TZ_NAME = 'Asia/Taipei'
LOCAL_TZ = pytz.timezone(LOCAL_TZ_NAME)


def local_today():
    """台灣的今天（date）。"""
    return pytz.utc.localize(datetime.utcnow()).astimezone(LOCAL_TZ).date()


def to_local_date(utc_naive):
    """naive UTC 的 Datetime → 台灣日期（date）。空值回 None。"""
    if not utc_naive:
        return None
    return pytz.utc.localize(utc_naive).astimezone(LOCAL_TZ).date()

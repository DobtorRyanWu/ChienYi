# -*- coding: utf-8 -*-
"""社區前台共用的小工具：時間一律以台灣時區呈現。

為什麼不跟著帳號的時區：管委會的 portal 帳號常常沒設時區，`context_timestamp` 沒時區就印 UTC，
同一頁會出現兩種時間；水位讀值、事件、簽收都是「在台灣某個社區發生的事」，時間要釘在發生地，
不隨看的人改變（ChienYi construction_helpdesk 的 LOCAL_TZ 同一個理由）。
資料庫裡一律是 naive UTC；轉換一律用 pytz 的 localize()——`datetime(..., tzinfo=pytz 時區)` 會拿到 LMT +08:06。
"""

from datetime import datetime

import pytz

LOCAL_TZ_NAME = 'Asia/Taipei'
LOCAL_TZ = pytz.timezone(LOCAL_TZ_NAME)
STAMP_FORMAT = '%m/%d %H:%M'             # 畫面用（手機寬，不放年）
FULL_STAMP_FORMAT = '%Y-%m-%d %H:%M'     # 詳情頁、PDF
SECONDS_PER_HOUR = 3600


def to_local(utc_naive):
    """naive UTC → 台灣時間（aware）。None 原樣回傳。"""
    if not utc_naive:
        return None
    return pytz.utc.localize(utc_naive).astimezone(LOCAL_TZ)


def to_utc_naive(local_naive):
    """台灣時間（naive，例如期間的期初 00:00）→ naive UTC，給 ORM／SQL 查詢用。"""
    return LOCAL_TZ.localize(local_naive).astimezone(pytz.utc).replace(tzinfo=None)


def local_stamp(utc_naive, fmt=STAMP_FORMAT):
    local = to_local(utc_naive)
    return local.strftime(fmt) if local else ''


def local_today():
    """台灣的今天。不能用 fields.Date.today()（那是伺服器的 UTC 日期，台灣 00:00–07:59 會落到前一天）。"""
    return pytz.utc.localize(datetime.utcnow()).astimezone(LOCAL_TZ).date()

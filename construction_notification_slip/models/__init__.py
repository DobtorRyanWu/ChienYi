# -*- coding: utf-8 -*-

from . import supervision_photo   # 照片收斂：掛「通報單」來源欄位
from . import notification_slip
from . import notification_slip_line

# 註：models/notification_acceptance.py 與 notification_acceptance_line.py
# 刻意不在此匯入 —— 它們從未被載入過（實測 information_schema 查無任何
# notification_acceptance% 資料表），其宣告的 photo_ids 等欄位形同不存在。
# 這是既有狀態，本輪不改，另記待辦查明該功能是否還要。

# -*- coding: utf-8 -*-
from . import test_official_doc          # 公文：預設值、搜尋條件、逾期、所屬公司、讀取範圍、附件不能被塞 id
from . import test_portal_official_doc   # 手機公文頁：列表與搜尋、新增（含附件）、下載把關、標為已辦
from . import test_calendar_event        # 行事曆事項：預設結束時間、過期、所屬公司、誰看得到、公文帶出事項
from . import test_portal_calendar       # 手機行事曆頁：時區換算、新增與改時間的權限、完成
from . import test_calendar_upcoming     # 近期清單：台灣時間、N 天內的邊界、過期未完成要列、件數不受上限影響
from . import test_visit_account         # 參觀帳號：授權內看得到、授權外一律拿不到、過期、精靈、不影響既有角色

# -*- coding: utf-8 -*-

from . import res_users  # 前台通知中心：上次查看時間浮水印
from . import supervision_project
from . import general_self_inspection
from . import supervision_photo
from . import daily_log_sheet
from . import notification_slip
from . import mail_thread  # 前台留言改看讀取權（前台角色 ORM 寫入權已收回）
from . import project_deadline  # 期限待辦彙整：各模型「有期限、還沒辦完」的事項排成一張清單（淞源 C5／C8）
from . import res_company  # 期限提醒的兩個天數（公司設定；淞源 C8）
from . import deadline_reminder  # 期限提醒：每日排程、提醒紀錄（淞源 C8）

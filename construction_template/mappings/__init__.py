# -*- coding: utf-8 -*-
"""各樣板類型的儲存格對照表。

檔名必須等於 document.template 的 template_type，template_render.get_mapping()
以此動態載入；沒有對應檔案的類型會回報「還沒建立欄位對照表」而不是默默出空白檔。

兩種模式（由模組的 MODE 決定）：
  'cells'（預設）  座標對照，給沒有佔位符的舊樣板用（如監造版日報表）
  'placeholder'    ${token} / ${table:coll.field}，給 EAGLE 帶來的樣板用

已完成：daily_log_1（監造日報表第一聯，座標，單筆）
        daily_log_2（監造日報表第二聯，佔位符，單筆——2026-08-05 重做樣板）
        daily_log_c1 / daily_log_c2（施工日誌一二聯 營造版，佔位符，單筆）
        self_inspection（自主檢查總表，佔位符，**專案層級彙總**）
        defect_improvement / defect_control / review_control / test_control
        （皆 docx，專案層級彙總）
        notification_slip（預約式施工回報單，佔位符——2026-08-05 重做樣板，雙工作表）
        estimate_report（工程估驗計價單，佔位符——2026-08-05 重做樣板）
待建立：progress_report、progress_schedule、acceptance_report、material_test
"""

from . import daily_log_1
from . import daily_log_2
from . import daily_log_c1
from . import daily_log_c2
from . import self_inspection
from . import defect_improvement
from . import defect_control
from . import review_control
from . import test_control
from . import notification_slip
from . import estimate_report

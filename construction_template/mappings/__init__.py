# -*- coding: utf-8 -*-
"""各樣板類型的儲存格對照表。

檔名必須等於 document.template 的 template_type，template_render.get_mapping()
以此動態載入；沒有對應檔案的類型會回報「還沒建立欄位對照表」而不是默默出空白檔。

已完成：daily_log_1（監造日報表第一聯）
待建立：daily_log_2、self_inspection、defect_improvement、defect_control、
        review_control、test_control、progress_report、progress_schedule、
        estimate_report、acceptance_report、notification_slip、material_test
"""

from . import daily_log_1

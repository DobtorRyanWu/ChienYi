# -*- coding: utf-8 -*-
from . import test_daily_log_parser
from . import test_role_guards
from . import test_photo_access
from . import test_defect_source
from . import test_record_type_resolution
from . import test_defect_parsers
from . import test_water_level_window
from . import test_inspection_type_docx_upload
from . import test_daily_log_materials  # 前台工地材料：本日數量、權限、鎖定
from . import test_daily_log_daily_progress  # 前台日誌填本日實際進度（增量），不碰匯入的累計值
from . import test_inspection_result_layout  # 自主檢查依結果欄位畫按鈕、送勾選值（環境清潔、生態保育）
from . import test_manual_fixes_20261102  # 說明書修正回歸：P1 詳情頁照片、P2 檢試驗工項、本週目標、P17 同日重複日誌
from . import test_manual_fixes_batch2_20261102  # 第 2 批：P4 P8-P16 回歸

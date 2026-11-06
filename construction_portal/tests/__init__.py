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
from . import test_manual_fixes_batch3_20261103  # 第 3 批線 1：缺失日期、日誌存檔錯誤、error 參數、刪照片權限
from . import test_portal_orm_readonly  # 前台角色 ORM 寫入權收回：權限表、RPC 被擋、正當入口仍可用
from . import test_inspection_timing_multi  # 前台一次勾多個檢查時機都要存（11-06）
from . import test_contractor_scope_portal  # 公司儀表板合約 §3.6：營造方範圍與寫入矩陣（線 A2）
from . import test_portal_get_items_scope  # get-items 只回看得到的樣板（線 H，11-06 抗辯 F9）

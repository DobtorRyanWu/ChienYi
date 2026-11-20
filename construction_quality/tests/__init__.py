# -*- coding: utf-8 -*-

from . import test_result_layout   # 檢查類型的結果欄位：是／否／不適用（只紀錄）、是／不足／否
from . import test_display_and_chatter_20261102  # P3 預約式顯示名稱、B2 前綴設定顯示名稱、P19 chatter Markup／跳脫
from . import test_daily_summary  # 某工程某天已完成的自主檢查清單（施工日誌帶入用，淞源 C1）
from . import test_low_fixes_20261116  # 11-16 六件 low：逾期通知作者
from . import test_number_by_project_company  # 自主檢查／通報單單號依工程所屬公司取號（2026-11-16）
from . import test_number_backfill  # 「/」自主檢查依工程公司、依檢查日期補號（6.10.3，2026-11-16）
from . import test_inspection_library_hook  # 樣板庫載入：建得出來、重跑不重複（6.12.0）
from . import test_eagle_parity_20261120  # 回復原版：缺失與自主檢查舊系統沒有的限制（1118 會議，2026-11-20）

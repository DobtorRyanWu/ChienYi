# -*- coding: utf-8 -*-
from . import test_project_task_create
from . import test_item_no_sort  # A1/A9 項次排序鍵
from . import test_legacy_category_upgrade  # 舊分類 xmlid 不可讓升級收尾失敗
from . import test_manual_fixes_20261102  # B18 單位解析權限、T12 代操作員標單匯入（2026-11-02）
from . import test_system_partner_rename  # OdooBot 改名「系統」（2026-11-03）
from . import test_list_views_batch3  # 第 3 批清單/表單畫面（2026-11-03）
from . import test_relational_input_guard  # 呼叫端給的關聯 id 不能拿來以 sudo 讀資料（線 H，2026-11-06）
from . import test_item_no_backfill_migration  # 空 item_no 依專案補號、NOT NULL 設得上去（6.7.4，2026-11-16）
from . import test_sequence_by_project_company  # 單號依工程所屬公司取號（2026-11-16）
from . import test_eagle_parity_20261120  # 回復原版：開工不再要求初始化與契約開工日（1118 會議，2026-11-20）

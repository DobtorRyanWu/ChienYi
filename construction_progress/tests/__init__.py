# -*- coding: utf-8 -*-
from . import test_is_latest_version
from . import test_line_create_guard
from . import test_daily_log_sync   # 狀態改變、新增也要同步本日進度到進度表（2026-10-28）
from . import test_display_name_20261102  # B2 進度表明細麵包屑（2026-11-02）
from . import test_batch2_20261102  # 第2批：圖表、啟用精靈、新版本（2026-11-02）
from . import test_eagle_parity_20261120  # 回復原版：沒有進度表也能填日誌（1118 會議 A2，2026-11-20）
from . import test_boundary_correction_20261124  # 交界日只算一次、校正碰到交界日、啟用重算、校正後累計實際進度（2026-11-24）
from . import test_progress_unified_20261124  # 累計進度統一成一套算法：首頁、進度表、報告、曲線同一個數字（2026-11-24）
from . import test_change_day_20261124  # 1.15.0「變更日進度」：建立新版本先問變更日期、變更日獨立一列、兩格可以不填（2026-11-24）
from . import test_log_resync_all_versions_20261124  # 1.15.2 日誌改了、刪了，每一版進度表都跟著重算（2026-11-24）

# -*- coding: utf-8 -*-
from . import test_lock_and_cumulative
from . import test_lump_sum_over_contract  # A10 式工項累計不得超過契約量
from . import test_contract_material  # 案件契約材料清單：自動帶入與累計
from . import test_manual_fixes_20261102  # B3 排程 NewId、P19 排程提醒（2026-11-02）
from . import test_title_language  # 日誌標題不隨使用者語言（2026-11-03）

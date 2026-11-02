# -*- coding: utf-8 -*-
from . import test_progress_report_amounts
from . import test_daily_log_material_block  # 日報表第一聯查核材料：只印人工手填列
from . import test_daily_log_c1_checkboxes  # 營造版日誌第一聯：第四項、第五項(一)勾選跟資料走
from . import test_defect_improvement_tokens  # 附表12：缺失改善補監造廠商、檢查日期、位置、複查日期、複查結果勾選
from . import test_progress_cumulative  # 日誌預定／實際進度印累計值
from . import test_self_inspection_marks  # 自主檢查分欄勾記（新北固定清單檢查表）
from . import test_docx_sandbox  # docx 套印用沙箱化 Jinja2（樣板注入）
from . import test_ntpc_new_forms  # 新北附表11、估驗附件（進度報告表＋查對表）
from . import test_seed_guard  # 升級不覆蓋被人換過的系統預設樣板
from . import test_template_probe_item_no  # 硬編樣板第二欄是「項次」時，項目名稱取下一欄
from . import test_ntpc_contract_forms  # 契約附表 10 種（只帶表頭；附表6-2、附表7）
from . import test_seed_self_inspection_migration  # 3.8.1 升級補灌自主檢查表樣板

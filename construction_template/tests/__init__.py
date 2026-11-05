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
from . import test_authority_blank  # 機關沒填印空白（T5-1）
from . import test_material_test_letterhead  # 送審函抬頭不印死某一家的人與信箱（T5-2）
from . import test_template_metadata_clean  # 預設樣板 metadata／內網路徑清乾淨（T5-3）
from . import test_seed_3_8_2_migration  # 3.8.2 舊版換新版、客製不覆蓋（T5-4）
from . import test_template_attachment_private  # 預設樣板附件不公開（T7）
from . import test_docx_photo_layout  # 照片段落不固定行高、不超出格子（11-05）
from . import test_xlsx_template_fixes  # 日報表（一）施工項目列高、calcChain、3.9.0 換樣板（11-05）
from . import test_defect_outcome  # 缺失改善成果確認只勾一格（11-05）
from . import test_self_inspection_timing  # 複製的檢查類型也印得出檢查時機（11-05）
from . import test_estimate_report_categories  # 估驗計價單分類＝最上層大類、累計、合計僅合約項（11-05）

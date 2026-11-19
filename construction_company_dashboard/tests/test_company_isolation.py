# -*- coding: utf-8 -*-
"""S3-A（2026-11-11）：估驗、變更、進度、損益類 18 個模型的全域公司隔離。

規則放在模型所屬的模組（construction_payment／contract_change／progress／general／supervision_base 的
security/company_rules.xml）；測試放這裡，因為要用 RoleMatrixCase 的兩家監造公司夾具（本模組依賴那五個模組）。

夾具：沿用 RoleMatrixCase（監造公司 S＝這裡的 A；監造公司 S2＝這裡的 B，工程 PS2），補請款、計量驗收＋明細、
非契約工項＋明細、進度表明細、B 的估驗明細、工項分析的「公司空白」列。

受測者（安全斷言一律以帳號的允許公司 company_ids 為準；切換器只選 A 是介面慣例，只當行為測試——red-team F8）：
* 工程後台使用者（group_supervisor_admin）只屬 A：主要受測者，18 個模型裡 17 個有讀取 ACL；它原本帶各模型的「(1=1)」
  群組規則，正是洞最大的那種人。
* 工程後台使用者 A＋B 兩家都屬（allowed_company_ids 全選）：兩家都讀得到。
* 同一人、allowed_company_ids 只選 A：讀不到 B（行為測試）。
* 一般內部帳號只屬 A：只測它有讀取 ACL 的 8 個模型（payment.*、work.acceptance(.line)、project.task.version）。
* 工項分析（report.project.task.user）：工程後台使用者沒有讀取 ACL（核心只給專案 User／Manager），
  另用「工程後台使用者＋專案 Manager」只屬 A 的帳號（Manager 的群組規則是 1=1，隔離出新規則）。
前台帳號不當受測者：前台路由都 sudo，前台營造帳號會先被 rule_scope 擋（skeptic F3）。

期望值：每筆紀錄掛哪個工程記在 iso_meta，工程屬哪家公司由夾具的建法獨立寫出（_fixture_company，L3）；
不 import 實作的常數（規則 xmlid 表在這裡獨立寫一份，照 test_scope_rules.py 的寫法）——唯一的例外是寫後檢查的欄位表
COMPANY_RULE_FIELDS：它是被測物，鎖定測試拿它跟「從資料庫規則推出來的表」比（期望值來自規則本身，不來自實作）。
每一個「讀不到 B」都先證明它本來讀得到（M-B）：同一支測試裡把那條規則 active=False → 讀得到 B → 恢復 → 讀不到 B
——這同時是 18 條規則的 mutation（不另走 harness）。

寫入面（S3 fix1，實作 construction_supervision_base/models/company_rule_write_guard.py）：核心 write 只在寫入前用舊值
檢查規則，所以另驗「改掛到別家公司的工程／父單會被拒、資料沒變」「有工程的估驗／變更單（明細）不能變成沒有工程」，
以及正當流程（匯入工程案件、契約變更精靈、同公司內改掛、sudo）照常。
S3 fix2：寫後檢查的欄位表以 test_write_guard_table_matches_rules 鎖住（從資料庫規則推、兩個方向比；表上每一格都要有
REPARENT_CELLS 的一格行為測試）；related 欄位（company_id 等）非 sudo 不能直接寫，連同屬兩家公司的帳號也一樣。
1b（2026-11-12，第三輪 red-team R1）：已經有估驗等單據（寫後檢查表上的模型）的工程，非 sudo 改公司只有系統管理者能改
——同屬兩家公司的工程後台使用者改了，底下整串單據的公司跟著工程搬走（第 8 節）。
1b 放寬（2026-11-13 使用者決定）：開案時系統自己產生的不算單據——空的資料夾、工程成員名單；資料夾裡有檔案才算。

S4（2026-11-12）：照片、施工日誌（＋明細、人機料）、檢試驗、缺失、自主檢查、通報單、送審、工程文件、資料夾、工程成員、
工項共 29 個模型加進同一張表（EXPECT_COMPANY_MODELS），表驅動、逐條關規則、盤點、鎖定測試、寫入面的格都自動涵蓋。
夾具：一般式模型 A＝PA、B＝PS2；預約式（通報單系）A＝R、B＝另建的預約式工程 RB（通報單只能掛預約式工程）。
工項的 B 用「公司空白、工程在 B」的那一筆（dev 2924 筆就是這種；公司照常的 B 工項會先被核心規則 85 擋，M-B）。
檢試驗統計是 SQL 檢視、id 是 row_number()（不穩定），以「工項-檢驗項目」當鍵（KEYED_MODELS）。
「工程空白放行」：工項（私人任務）真的建一筆驗 A、B 都讀得到；檢試驗項目／頻率條件、資料夾、工程文件的工程欄位
資料庫 NOT NULL，空白的紀錄建不出來——那一格改成驗 NOT NULL（改成可空時會紅，提醒補真的格）。
本模組不依賴 construction_equipment（人機料）、construction_review（送審）：dev 都裝了，沒裝時夾具會直接失敗（不靜默略過）。

S5（2026-11-18）：自主檢查樣板（＋時機、段落、項目、量測）、缺失編號前綴設定、文件樣板、會議記錄、週施工排程（＋明細）、
初驗／正驗／驗收缺失／結案（＋明細、結案文件）、機具（＋維護請求）、計畫書送審管制共 20 個模型加進同一張表。
夾具都掛 PA／PS2。驗收四種主單的 B 把 stored related 的 company_id 清空：那個模組原有的群組規則（Internal User）公司空白放行，
公司照常的 B 會先被它擋（M-B；同工項 B 用公司空白那一筆）。
工程空白的三種語意另有專屬的格（不進 iso_meta）：全域樣板 A、B 都讀得到；文件樣板的系統預設 A、B 都讀得到、
公司層級只有自己公司讀得到；沒選工程的會議記錄只有記錄自己的公司讀得到。
規則欄位裡「改掛到 B」表達不了的三格（文件樣板的 company_id、is_default，會議記錄的 company_id）記在 SPECIAL_CELLS，
由 test_s5_special_cells_refused 各跑一格。
本模組不依賴 construction_acceptance、construction_meeting_record：同上，dev 都裝了，沒裝時夾具直接失敗。
"""
import os
import re
from contextlib import closing
from unittest.mock import patch

from odoo import fields
from odoo.addons.construction_supervision_base.models.company_rule_write_guard import (
    COMPANY_RULE_FIELDS, _project_link_fields, _project_paths)
from odoo.addons.construction_supervision_base.models import company_rule_write_guard, relational_input_guard
from odoo.addons.construction_supervision_base.models.relational_input_guard import guarded_fields_of
from odoo.exceptions import AccessError, UserError
from odoo.models import LOG_ACCESS_COLUMNS
from odoo.modules.module import get_module_path
from odoo.osv import expression
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .test_role_accounts import RoleMatrixCase
from .test_scope_rules import SUPERVISOR_ADMIN

MODULE = 'construction_company_dashboard'
# 模型 → 本規格新增的全域規則 xmlid（測試獨立寫一份；L2⑨：資料庫裡的集合要與它兩個方向都相等）
EXPECT_COMPANY_MODELS = {
    'payment.claim': 'construction_payment.rule_company_global_payment_claim',
    'payment.estimate': 'construction_payment.rule_company_global_payment_estimate',
    'payment.estimate.line': 'construction_payment.rule_company_global_payment_estimate_line',
    'payment.estimate.extra.item': 'construction_payment.rule_company_global_payment_estimate_extra_item',
    'payment.estimate.extra.line': 'construction_payment.rule_company_global_payment_estimate_extra_line',
    'work.acceptance': 'construction_payment.rule_company_global_work_acceptance',
    'work.acceptance.line': 'construction_payment.rule_company_global_work_acceptance_line',
    'contract.change.order': 'construction_contract_change.rule_company_global_contract_change_order',
    'contract.change.order.line': 'construction_contract_change.rule_company_global_contract_change_order_line',
    'progress.schedule': 'construction_progress.rule_company_global_progress_schedule',
    'progress.schedule.line': 'construction_progress.rule_company_global_progress_schedule_line',
    'general.progress.report': 'construction_general.rule_company_global_general_progress_report',
    'general.progress.report.line': 'construction_general.rule_company_global_general_progress_report_line',
    'general.realtime.profit': 'construction_general.rule_company_global_general_realtime_profit',
    'general.realtime.profit.cost': 'construction_general.rule_company_global_general_realtime_profit_cost',
    'profit.loss.entry': 'construction_general.rule_company_global_profit_loss_entry',
    'project.task.version': 'construction_supervision_base.rule_company_global_project_task_version',
    'report.project.task.user': 'construction_supervision_base.rule_company_global_report_project_task_user',
    # ── S4（2026-11-12）──
    'supervision.photo': 'construction_photo.rule_company_global_supervision_photo',
    'daily.log.sheet': 'construction_daily_log.rule_company_global_daily_log_sheet',
    'daily.log.line': 'construction_daily_log.rule_company_global_daily_log_line',
    'daily.log.material': 'construction_daily_log.rule_company_global_daily_log_material',
    'daily.log.specific.item': 'construction_daily_log.rule_company_global_daily_log_specific_item',
    'daily.log.weather': 'construction_daily_log.rule_company_global_daily_log_weather',
    'daily.log.man.machine': 'construction_equipment.rule_company_global_daily_log_man_machine',
    'daily.log.man.machine.detail': 'construction_equipment.rule_company_global_daily_log_man_machine_detail',
    'supervision.test.standard': 'construction_test.rule_company_global_supervision_test_standard',
    'supervision.test.task.statistics': 'construction_test.rule_company_global_supervision_test_task_statistics',
    'supervision.test.record': 'construction_test.rule_company_global_supervision_test_record',
    'supervision.test.warning': 'construction_test.rule_company_global_supervision_test_warning',
    'supervision.test.frequency.condition': 'construction_test.rule_company_global_supervision_test_frequency_condition',
    'general.defect.improvement': 'construction_general.rule_company_global_general_defect_improvement',
    'general.self.inspection': 'construction_quality.rule_company_global_general_self_inspection',
    'general.self.inspection.item': 'construction_quality.rule_company_global_general_self_inspection_item',
    'general.self.inspection.measure.line': 'construction_quality.rule_company_global_general_self_inspection_measure_line',
    'reservation.defect.improvement': 'construction_quality.rule_company_global_reservation_defect_improvement',
    'reservation.self.inspection': 'construction_quality.rule_company_global_reservation_self_inspection',
    'reservation.self.inspection.item': 'construction_quality.rule_company_global_reservation_self_inspection_item',
    'reservation.self.inspection.measure.line':
        'construction_quality.rule_company_global_reservation_self_inspection_measure_line',
    'reservation.notification.slip': 'construction_notification_slip.rule_company_global_reservation_notification_slip',
    'reservation.notification.slip.line':
        'construction_notification_slip.rule_company_global_reservation_notification_slip_line',
    'reservation.notification.slip.suspension':
        'construction_notification_slip.rule_company_global_reservation_notification_slip_suspension',
    'supervision.review.application': 'construction_review.rule_company_global_supervision_review_application',
    'supervision.folder': 'construction_supervision_base.rule_company_global_supervision_folder',
    'supervision.project.member': 'construction_supervision_base.rule_company_global_supervision_project_member',
    'supervision.document': 'construction_supervision_base.rule_company_global_supervision_document',
    'project.task': 'construction_supervision_base.rule_company_global_project_task',
    # ── S5（2026-11-18）──
    'self.inspection.type': 'construction_quality.rule_company_global_self_inspection_type',
    'self.inspection.type.timing': 'construction_quality.rule_company_global_self_inspection_type_timing',
    'self.inspection.type.stage': 'construction_quality.rule_company_global_self_inspection_type_stage',
    'self.inspection.type.item': 'construction_quality.rule_company_global_self_inspection_type_item',
    'self.inspection.type.measure': 'construction_quality.rule_company_global_self_inspection_type_measure',
    'defect.improvement.prefix.config': 'construction_quality.rule_company_global_defect_improvement_prefix_config',
    'document.template': 'construction_template.rule_company_global_document_template',
    'construction.meeting.record': 'construction_meeting_record.rule_company_global_construction_meeting_record',
    'construction.weekly.schedule': 'construction_daily_log.rule_company_global_construction_weekly_schedule',
    'construction.weekly.schedule.line': 'construction_daily_log.rule_company_global_construction_weekly_schedule_line',
    'acceptance.preliminary': 'construction_acceptance.rule_company_global_acceptance_preliminary',
    'acceptance.preliminary.line': 'construction_acceptance.rule_company_global_acceptance_preliminary_line',
    'acceptance.final': 'construction_acceptance.rule_company_global_acceptance_final',
    'acceptance.final.line': 'construction_acceptance.rule_company_global_acceptance_final_line',
    'acceptance.defect': 'construction_acceptance.rule_company_global_acceptance_defect',
    'project.closure': 'construction_acceptance.rule_company_global_project_closure',
    'project.closure.document': 'construction_acceptance.rule_company_global_project_closure_document',
    'supervision.equipment': 'construction_equipment.rule_company_global_supervision_equipment',
    'supervision.equipment.request': 'construction_equipment.rule_company_global_supervision_equipment_request',
    'supervision.plan.control': 'construction_review.rule_company_global_supervision_plan_control',
}
# 本規格新增規則的 xmlid 前綴與所在模組（盤點用）
RULE_XMLID_PREFIX = 'rule_company_global_'
RULE_MODULES = ('construction_payment', 'construction_contract_change', 'construction_progress',
                'construction_general', 'construction_supervision_base',
                # S4
                'construction_photo', 'construction_daily_log', 'construction_equipment', 'construction_test',
                'construction_quality', 'construction_notification_slip', 'construction_review',
                # S5（quality、daily_log、equipment、review 上面已有）
                'construction_template', 'construction_meeting_record', 'construction_acceptance')
# 一般內部帳號（只有 base.group_user）有讀取 ACL 的模型（dev ir_model_access 查得；其餘只給工程後台使用者等群組）
INTERNAL_USER_MODELS = frozenset({
    'payment.claim', 'payment.estimate', 'payment.estimate.line', 'payment.estimate.extra.item',
    'payment.estimate.extra.line', 'work.acceptance', 'work.acceptance.line', 'project.task.version',
    # S4：盤點「連一般內部帳號都讀得到」的三個
    'supervision.folder', 'supervision.project.member', 'project.task',
    # S5：base.group_user 有讀取 ACL 的（文件樣板、會議記錄、驗收與結案七個）
    'document.template', 'construction.meeting.record',
    'acceptance.preliminary', 'acceptance.preliminary.line', 'acceptance.final', 'acceptance.final.line',
    'acceptance.defect', 'project.closure', 'project.closure.document',
})
# 工程後台使用者沒有讀取 ACL 的模型（核心 project 只給 Project User／Manager）
PROJECT_USER_ONLY_MODELS = frozenset({'report.project.task.user'})
# SQL 檢視（_auto=False，寫不了）：不在寫後檢查的欄位表上
SQL_VIEW_MODELS = frozenset({'report.project.task.user', 'supervision.test.task.statistics'})
# S4：掛在預約式工程的模型（通報單只能掛預約式工程）：A＝R、B＝RB
RESERVATION_MODELS = frozenset({
    'reservation.notification.slip', 'reservation.notification.slip.line', 'reservation.notification.slip.suspension',
    'reservation.defect.improvement', 'reservation.self.inspection', 'reservation.self.inspection.item',
    'reservation.self.inspection.measure.line',
})
# S4：id 不穩定的 SQL 檢視，以這兩個欄位組成鍵（「工項 id-檢驗項目 id」）
KEYED_MODELS = {'supervision.test.task.statistics': ('task_id', 'standard_id')}
# S4：寫入格要用有寫權的人（工程後台使用者沒有專案 User 群組，寫不了有工程的工項）→ 工程後台使用者＋專案 Manager
PROJECT_WRITE_MODELS = frozenset({'project.task'})
# S4：規格說「工程空白放行」、但工程欄位資料庫 NOT NULL 的模型 → (資料表, 欄位)。頻率條件的工程走檢試驗項目
BLANK_SHARED_NOT_NULL = {
    'supervision.test.standard': ('supervision_test_standard', 'project_id'),
    'supervision.test.frequency.condition': ('supervision_test_standard', 'project_id'),
    'supervision.folder': ('supervision_folder', 'project_id'),
    'supervision.document': ('supervision_document', 'project_id'),
}
PROJECT_MANAGER = 'project.group_project_manager'
# 寫入面：A 的紀錄改掛到 B 的哪一種目標（模型名＝B 的那一種父單）。S3 fix1 的 8 格（skeptic F1 的 6 個欄位＋估驗／變更單的
# 工程）；S3 fix2 補成「規則用得到的每一個欄位一格」（第二輪 skeptic F1：表上一半的欄位沒有行為測試）——
# test_write_guard_table_matches_rules 驗這張表的 (模型, 欄位) ＝ 從資料庫規則推出來的，兩個方向都比
TARGET_PROJECT = 'project'
TARGET_TASK = 'task'
TARGET_COMPANY = 'company'
REPARENT_CELLS = (
    ('payment.claim', 'project_id', TARGET_PROJECT),
    ('work.acceptance', 'project_id', TARGET_PROJECT),
    ('work.acceptance.line', 'acceptance_id', 'work.acceptance'),
    ('payment.estimate.extra.item', 'project_id', TARGET_PROJECT),
    ('general.progress.report.line', 'report_id', 'general.progress.report'),
    ('project.task.version', 'task_id', TARGET_TASK),
    ('payment.estimate', 'project_id', TARGET_PROJECT),
    ('contract.change.order', 'project_id', TARGET_PROJECT),
    # S3 fix2
    ('payment.estimate.line', 'estimate_id', 'payment.estimate'),
    ('payment.estimate.extra.line', 'estimate_id', 'payment.estimate'),
    ('payment.estimate.extra.line', 'project_id', TARGET_PROJECT),
    ('contract.change.order', 'company_id', TARGET_COMPANY),
    ('contract.change.order.line', 'change_order_id', 'contract.change.order'),
    ('contract.change.order.line', 'company_id', TARGET_COMPANY),
    ('progress.schedule', 'project_id', TARGET_PROJECT),
    ('progress.schedule', 'company_id', TARGET_COMPANY),
    ('progress.schedule.line', 'schedule_id', 'progress.schedule'),
    ('progress.schedule.line', 'company_id', TARGET_COMPANY),
    ('general.progress.report', 'project_id', TARGET_PROJECT),
    ('general.progress.report', 'company_id', TARGET_COMPANY),
    ('general.realtime.profit', 'project_id', TARGET_PROJECT),
    ('general.realtime.profit', 'company_id', TARGET_COMPANY),
    ('general.realtime.profit.cost', 'profit_id', 'general.realtime.profit'),
    ('profit.loss.entry', 'project_id', TARGET_PROJECT),
    ('profit.loss.entry', 'company_id', TARGET_COMPANY),
    # S4（related 的 project_id＝父單或來源的工程，7 格：日誌、材料、特定項目、人機料明細、預約式缺失、預約式自主檢查、通報單工項；
    # 天氣的規則走父單、不用 related 的 project_id，見 construction_daily_log/security/company_rules.xml）
    ('supervision.photo', 'project_id', TARGET_PROJECT),
    ('daily.log.sheet', 'project_id', TARGET_PROJECT),
    ('daily.log.sheet', 'supervision_project_id', TARGET_PROJECT),
    ('daily.log.line', 'sheet_id', 'daily.log.sheet'),
    ('daily.log.material', 'project_id', TARGET_PROJECT),
    ('daily.log.material', 'daily_log_id', 'daily.log.sheet'),
    ('daily.log.specific.item', 'project_id', TARGET_PROJECT),
    ('daily.log.specific.item', 'daily_log_id', 'daily.log.sheet'),
    ('daily.log.weather', 'sheet_id', 'daily.log.sheet'),
    ('daily.log.man.machine', 'project_id', TARGET_PROJECT),
    ('daily.log.man.machine.detail', 'project_id', TARGET_PROJECT),
    ('daily.log.man.machine.detail', 'daily_log_id', 'daily.log.sheet'),
    ('supervision.test.standard', 'project_id', TARGET_PROJECT),
    ('supervision.test.record', 'project_id', TARGET_PROJECT),
    ('supervision.test.warning', 'project_id', TARGET_PROJECT),
    ('supervision.test.frequency.condition', 'standard_id', 'supervision.test.standard'),
    ('general.defect.improvement', 'project_id', TARGET_PROJECT),
    ('general.self.inspection', 'project_id', TARGET_PROJECT),
    ('general.self.inspection.item', 'inspection_id', 'general.self.inspection'),
    ('general.self.inspection.measure.line', 'inspection_id', 'general.self.inspection'),
    ('reservation.defect.improvement', 'project_id', TARGET_PROJECT),
    ('reservation.defect.improvement', 'slip_id', 'reservation.notification.slip'),
    ('reservation.self.inspection', 'project_id', TARGET_PROJECT),
    ('reservation.self.inspection', 'slip_id', 'reservation.notification.slip'),
    ('reservation.self.inspection.item', 'inspection_id', 'reservation.self.inspection'),
    ('reservation.self.inspection.measure.line', 'inspection_id', 'reservation.self.inspection'),
    ('reservation.notification.slip', 'project_id', TARGET_PROJECT),
    ('reservation.notification.slip.line', 'project_id', TARGET_PROJECT),
    ('reservation.notification.slip.line', 'slip_id', 'reservation.notification.slip'),
    ('reservation.notification.slip.suspension', 'slip_id', 'reservation.notification.slip'),
    ('supervision.folder', 'project_id', TARGET_PROJECT),
    ('supervision.project.member', 'project_id', TARGET_PROJECT),
    ('supervision.review.application', 'project_id', TARGET_PROJECT),
    ('supervision.document', 'project_id', TARGET_PROJECT),
    ('project.task', 'project_id', TARGET_PROJECT),
    # S5（related 的 project_id 2 格：週施工排程＝supervision_project_id、機具維護請求＝機具的工程）
    ('self.inspection.type', 'project_id', TARGET_PROJECT),
    ('self.inspection.type.timing', 'type_id', 'self.inspection.type'),
    ('self.inspection.type.stage', 'type_id', 'self.inspection.type'),
    ('self.inspection.type.item', 'type_id', 'self.inspection.type'),
    ('self.inspection.type.measure', 'type_id', 'self.inspection.type'),
    ('defect.improvement.prefix.config', 'project_id', TARGET_PROJECT),
    ('document.template', 'project_id', TARGET_PROJECT),
    ('construction.meeting.record', 'project_id', TARGET_PROJECT),
    ('construction.weekly.schedule', 'project_id', TARGET_PROJECT),
    ('construction.weekly.schedule', 'supervision_project_id', TARGET_PROJECT),
    ('construction.weekly.schedule.line', 'schedule_id', 'construction.weekly.schedule'),
    ('acceptance.preliminary', 'project_id', TARGET_PROJECT),
    ('acceptance.preliminary.line', 'acceptance_id', 'acceptance.preliminary'),
    ('acceptance.final', 'project_id', TARGET_PROJECT),
    ('acceptance.final.line', 'acceptance_id', 'acceptance.final'),
    ('acceptance.defect', 'project_id', TARGET_PROJECT),
    ('project.closure', 'project_id', TARGET_PROJECT),
    ('project.closure.document', 'closure_id', 'project.closure'),
    ('supervision.equipment', 'project_id', TARGET_PROJECT),
    ('supervision.equipment.request', 'project_id', TARGET_PROJECT),
    ('supervision.equipment.request', 'equipment_id', 'supervision.equipment'),
    ('supervision.plan.control', 'project_id', TARGET_PROJECT),
)
# S5：規則欄位裡「把 A 的紀錄改掛到 B 的工程／父單」表達不了的格——工程空白時才看的 company_id（獨立欄位）、
# 不是關聯欄位的 is_default。各由 test_s5_special_cells_refused 跑一格；鎖定測試把它們和 REPARENT_CELLS 合起來比
SPECIAL_CELLS = frozenset({
    ('document.template', 'company_id'),
    ('document.template', 'is_default'),
    ('construction.meeting.record', 'company_id'),
})
# related 欄位（company_id＝工程的公司、非契約工項明細的 project_id＝估驗的工程；S4 的 project_id＝父單／來源的工程）
# 非 sudo 不能直接寫：訊息片段（測試獨立寫出）與格數（上游說有幾格就要有幾格，M-C）：S3 8 格＋S4 7 格＋S5 2 格
RELATED_FIELD_HINT = '不能直接改'
RELATED_CELL_COUNT = 17
# 寫後檢查表上「拿掉也不會有行為測試變紅」的兩格（還有第二道防線，A2）
BACKSTOP_CELLS = frozenset({
    ('reservation.notification.slip.suspension', 'slip_id'),
    ('general.self.inspection.measure.line', 'inspection_id')})
# 正當流程：同公司內改掛工程照常的模型（S3 fix1 那 5 格）
SAME_COMPANY_REPARENT_MODELS = frozenset({
    'payment.claim', 'work.acceptance', 'payment.estimate.extra.item', 'payment.estimate', 'contract.change.order'})
# 規則對工程空白放行建立者的兩種單（清空工程要被擋）
BLANK_FALLBACK_MODELS = ('payment.estimate', 'contract.change.order')
# 「有工程的單不能變成沒有工程」的訊息片段（測試獨立寫出）。只比例外型別不夠：核心 AccessError 是 UserError 的子類別，
# 拿掉這道檢查時寫後檢查的 AccessError 照樣讓 assertRaises(UserError) 綠（S3 fix1 mutation W2 第一輪實測，L2⑮ 第二形狀）
LOST_PROJECT_HINT = '不能改成沒有工程'
LUMP_ADJUST_AMOUNT = 1000.0
# 已經有單據的工程改公司（2026-11-12「1b」）：只有系統管理者與代操作員能改（同日追加「代操跟管理者都要可以做」）。訊息片段測試獨立寫出（AccessError 是 UserError 的子類別，
# 只比例外型別會被別道檢查滿足，L2⑮）
SYSTEM_ADMIN = 'base.group_system'
OPERATOR = 'construction_supervision_base.group_operator'
COMPANY_MOVE_HINT = '只有系統管理者或代操作員能改'
# S4 fix1（S4 第一輪審查 red-team F1）：many2one 的顯示名稱核心以 sudo 讀——comodel 是公司隔離模型的 many2one
# 都要被 relational_input_guard 守（填不進讀不到的 id）。訊息片段測試獨立寫出（AccessError 很多道防線都會丟，M-B）
GUARD_MSG = '沒有讀取權限的紀錄'
DISPLAY_NAME_HINT = '顯示名稱'
ISOLATION_ROOT = 'project.project'
# (A 的紀錄的模型, 原本沒被守的 many2one, B 的目標種類)：工項、缺失、通報單、工程（兩格）——審查重現的那幾個欄位
DISPLAY_NAME_CELLS = (
    ('general.defect.improvement', 'task_id', TARGET_TASK),
    ('general.self.inspection.item', 'defect_improvement_id', 'general.defect.improvement'),
    ('daily.log.sheet', 'notification_slip_id', 'reservation.notification.slip'),
    ('supervision.photo', 'signboard_project_id', TARGET_PROJECT),
    ('daily.log.line', 'project_id', TARGET_PROJECT),
)
# S4 fix1（S4 第一輪審查 simplifier medium）：上 S4 前的檢查 SQL 在 repo 裡；(S4-1) 那段每個 S4 規則模型一列（SQL 檢視除外）
PRECHECK_SQL = ('runbook', 's4_precheck.sql')
PRECHECK_SECTION = 'S4-1'
S4_RULE_MODULES = ('construction_photo', 'construction_daily_log', 'construction_equipment', 'construction_test',
                   'construction_quality', 'construction_notification_slip', 'construction_review')
# S4 在 S3 那幾個模組裡加的規則（其餘 S4 規則在 S4_RULE_MODULES）
S4_RULES_IN_S3_MODULES = frozenset({
    'construction_general.rule_company_global_general_defect_improvement',
    'construction_supervision_base.rule_company_global_supervision_folder',
    'construction_supervision_base.rule_company_global_supervision_project_member',
    'construction_supervision_base.rule_company_global_supervision_document',
    'construction_supervision_base.rule_company_global_project_task',
})
S4_RULE_COUNT = 29
# S5（2026-11-18）：本輪的規則模型（測試獨立寫一份；有幾條規則和 S4 在同一個模組，所以用模型名分，不用模組分）
S5_RULE_MODELS = frozenset({
    'self.inspection.type', 'self.inspection.type.timing', 'self.inspection.type.stage', 'self.inspection.type.item',
    'self.inspection.type.measure', 'defect.improvement.prefix.config', 'document.template',
    'construction.meeting.record', 'construction.weekly.schedule', 'construction.weekly.schedule.line',
    'acceptance.preliminary', 'acceptance.preliminary.line', 'acceptance.final', 'acceptance.final.line',
    'acceptance.defect', 'project.closure', 'project.closure.document',
    'supervision.equipment', 'supervision.equipment.request', 'supervision.plan.control',
})
S5_RULE_COUNT = 20
S5_PRECHECK_SQL = ('runbook', 's5_precheck.sql')
S5_PRECHECK_SECTION = 'S5-1'
# S5：驗收模組原有的群組規則（Internal User）看 stored related 的 company_id、公司空白放行的四種主單
ACCEPTANCE_COMPANY_RULE_MODELS = ('acceptance.preliminary', 'acceptance.final', 'acceptance.defect', 'project.closure')
# S5：夾具用的文件樣板類型——同一家公司同一類型只能有一份非預設樣板（唯一鍵 template_type＋is_default＋company_id），各用一種
S5_TEMPLATE_TYPE_PROJECT = 'daily_log_1'
# 公司層級的兩份（A、B）要用不同類型：特殊格會把 A 的那份改成 B 公司，同類型的話先撞唯一鍵、測不到防線（M-B）
S5_TEMPLATE_TYPE_COMPANY_A = 'daily_log_2'
S5_TEMPLATE_TYPE_COMPANY_B = 'defect_improvement'
S5_TEMPLATE_TYPE_DEFAULT = 'self_inspection'
S5_MEASURE_TEMPLATE = '丈量___位置'
# 夾具數量
CLAIM_AMOUNT = 1000.0
ACCEPT_QTY = 1.0
SCHEDULE_DAYS = 6


@tagged('post_install', '-at_install', MODULE)
class TestCompanyIsolation(RoleMatrixCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        today = fields.Date.today()
        cls.co_iso_a, cls.co_iso_b = cls.co_s, cls.co_s2
        cls.p_iso_a, cls.p_iso_b = cls.p_a, cls.p_s2
        # 受測者
        sa = ['base.group_user', SUPERVISOR_ADMIN]
        cls.sa_a = cls._user('s3_sa_a', sa, company=cls.co_s, companies=cls.co_s)
        cls.sa_a2 = cls._user('s3_sa_a2', sa, company=cls.co_s, companies=cls.co_s)
        cls.sa_ab = cls._user('s3_sa_ab', sa, company=cls.co_s, companies=cls.co_s | cls.co_s2)
        cls.int_a = cls._user('s3_int_a', ['base.group_user'], company=cls.co_s, companies=cls.co_s)
        cls.rpt_a = cls._user('s3_rpt_a', sa + [PROJECT_MANAGER], company=cls.co_s, companies=cls.co_s)

        # 紀錄 → 工程（模型 → {id: 工程}）：從 RoleMatrixCase 的 meta 取 18 個模型裡有的，再補沒有的
        cls.iso_meta = {model: {} for model in EXPECT_COMPANY_MODELS}
        for model in EXPECT_COMPANY_MODELS:
            for rid, (project, _contractor) in cls.meta.get(model, {}).items():
                if project:
                    cls.iso_meta[model][rid] = project

        def note(records, project):
            for record in records:
                cls.iso_meta[record._name][record.id] = project

        for project, company in ((cls.p_iso_a, cls.co_iso_a), (cls.p_iso_b, cls.co_iso_b)):
            task = cls.tasks[project]
            estimate = cls.estimates.filtered(lambda e, p=project: e.project_id == p)[:1]
            assert estimate, f'夾具：{project.code} 應有估驗'
            note(env['payment.claim'].create({
                'project_id': project.id, 'company_id': company.id, 'claim_amount': CLAIM_AMOUNT}), project)
            acceptance = env['work.acceptance'].create({'project_id': project.id, 'contractor_company_id': cls.co_a.id})
            note(acceptance, project)
            note(env['work.acceptance.line'].create({
                'acceptance_id': acceptance.id, 'task_id': task.id,
                'completed_qty': ACCEPT_QTY, 'accepted_qty': ACCEPT_QTY}), project)
            item = env['payment.estimate.extra.item'].create({
                'project_id': project.id, 'code': f'S3X-{project.code}', 'name': 'S3 非契約工項'})
            note(item, project)
            note(env['payment.estimate.extra.line'].create({
                'estimate_id': estimate.id, 'extra_item_id': item.id, 'name': 'S3 非契約工項明細'}), project)
            schedule = project.with_context(active_test=False).schedule_ids[:1]
            assert schedule, f'夾具：{project.code} 應有進度表'
            note(env['progress.schedule.line'].with_context(allow_line_on_active_schedule=True).create({
                'schedule_id': schedule.id, 'sequence': 1, 'date_start': today,
                'date_end': fields.Date.add(today, days=SCHEDULE_DAYS), 'planned_progress': 0.0}), project)
            if not env['payment.estimate.line'].search_count([('estimate_id', '=', estimate.id)]):
                note(cls._make_line('payment.estimate.line', estimate), project)
            note(env['project.task.version'].search([('task_id', '=', task.id)]), project)
        # 工項分析（SQL 檢視，id＝工項 id）：A 用 PA 的工項（公司照常）；B 另建一個 PS2 的工項、用 SQL 把公司清空
        # ——dev 那 2924 列就是這個樣子（核心規則 91 放行公司空白），公司照常的 B 列會先被 91 擋（M-B）
        cls.task_b_blank = env['project.task'].create({'name': 'S3 公司空白工項', 'project_id': cls.p_iso_b.id})
        env.cr.execute('UPDATE project_task SET company_id = NULL WHERE id = %s', [cls.task_b_blank.id])
        cls.task_b_blank.invalidate_recordset(['company_id'])
        cls.iso_meta['report.project.task.user'] = {
            cls.tasks[cls.p_iso_a].id: cls.p_iso_a, cls.task_b_blank.id: cls.p_iso_b}
        cls._s4_fixtures()
        cls._s5_fixtures()
        env.flush_all()
        env.registry.clear_cache()

    @classmethod
    def _s4_fixtures(cls):
        """S4 的 29 個模型：A、B 各至少一筆（一般式掛 PA／PS2，預約式掛 R／RB），記進 iso_meta。"""
        env = cls.env
        today = fields.Date.today()
        # 預約式的 B 工程（通報單只能掛預約式工程）；_fixture_company 另外認得它
        cls.p_iso_rb = env['project.project'].create({
            'name': 'S4-RB 公司隔離測試工程', 'code': 'S4-RB', 'project_type': 'reservation', 'state': 'construction',
            'company_id': cls.co_iso_b.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.p_iso_rb.id, 'supervision_prefix': 'S4RBS', 'contractor_prefix': 'S4RBC'})
        cls.tasks[cls.p_iso_rb] = env['project.task'].create({
            'name': 'S4-RB 工項', 'project_id': cls.p_iso_rb.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': 100.0})
        cls.s4_reservation = {cls.co_iso_a: cls.r_shared, cls.co_iso_b: cls.p_iso_rb}
        ptype = env['personnel.type'].create({'name': 'S4 技工', 'record_type': 'personnel'})
        block = env['self.inspection.type.measure'].create({
            'type_id': cls.itype.id, 'name': 'S4 量測', 'template': '丈量___位置'})
        category = env['supervision.document.category'].create({'name': 'S4 文件分類'})
        # 工程成員：A、B 用不同的帳號（同一帳號改掛到 B 會先撞唯一鍵，測不到防線）
        members = {company: cls._user(f's4_member_{tag}', ['base.group_user'], company=company, companies=company)
                   for company, tag in ((cls.co_iso_a, 'a'), (cls.co_iso_b, 'b'))}
        cls.iso_meta.update({model: {} for model in EXPECT_COMPANY_MODELS if model not in cls.iso_meta})

        def note(records, project):
            for record in records:
                cls.iso_meta[record._name][record.id] = project

        for project, company in ((cls.p_iso_a, cls.co_iso_a), (cls.p_iso_b, cls.co_iso_b)):
            task = cls.tasks[project]
            note(cls._make_doc('supervision.photo', project, cls.co_a), project)
            sheet = cls._make_doc('daily.log.sheet', project, cls.co_a)
            note(sheet, project)
            note(cls._make_line('daily.log.line', sheet), project)
            note(env['daily.log.material'].create({'daily_log_id': sheet.id, 'name': 'S4 材料'}), project)
            note(env['daily.log.specific.item'].create({'daily_log_id': sheet.id, 'name': 'S4 特定項'}), project)
            # daily.log.weather 的 ORM 建立會壞（既有 bug：_check_date_in_sheet_range 讀不存在的 sheet_id.date_start，
            # 見 construction_portal/tests/test_contractor_scope_portal.py），用 SQL 放資料——跟那邊一樣**不填** related 的
            # project_id：規則要沿父單才看得到它（第一版規則用 project_id，portal 那 4 格就紅在這裡）
            env.cr.execute('INSERT INTO daily_log_weather (sheet_id, date) VALUES (%s, %s) RETURNING id',
                           [sheet.id, sheet.log_date])
            note(env['daily.log.weather'].browse(env.cr.fetchone()[0]), project)
            note(env['daily.log.man.machine'].create({'project_id': project.id, 'personnel_type_id': ptype.id}), project)
            note(env['daily.log.man.machine.detail'].create({
                'daily_log_id': sheet.id, 'personnel_type_id': ptype.id, 'hours': 8.0}), project)
            standard = env['supervision.test.standard'].create({
                'name': f'S4 抗壓 {project.code}', 'material': '預拌混凝土', 'project_id': project.id,
                'task_ids': [(4, task.id)]})
            note(standard, project)
            cls.iso_meta['supervision.test.task.statistics'][f'{task.id}-{standard.id}'] = project
            note(env['supervision.test.record'].create({'project_id': project.id, 'standard_id': standard.id}), project)
            note(env['supervision.test.warning'].create({
                'project_id': project.id, 'task_id': task.id, 'standard_id': standard.id}), project)
            note(env['supervision.test.frequency.condition'].create({
                'standard_id': standard.id, 'condition_type': 'every_batch'}), project)
            note(cls._make_doc('general.defect.improvement', project, cls.co_a), project)
            inspection = cls._make_doc('general.self.inspection', project, cls.co_a)
            note(inspection, project)
            note(env['general.self.inspection.item'].create({'inspection_id': inspection.id, 'check_item': 'S4 項目'}),
                 project)
            note(env['general.self.inspection.measure.line'].create({
                'inspection_id': inspection.id, 'block_id': block.id, 'template': block.template, 'result': 'pass'}),
                 project)
            note(env['supervision.folder'].create({'name': 'S4 資料夾', 'project_id': project.id}), project)
            note(env['supervision.project.member'].create({'project_id': project.id, 'user_id': members[company].id}),
                 project)
            note(env['supervision.review.application'].create({'name': 'S4 送審', 'project_id': project.id}), project)
            note(env['supervision.document'].create({
                'name': 'S4 文件', 'project_id': project.id, 'document_category_id': category.id}), project)
        # 工項：A＝PA 的工項（公司照常）；B＝PS2 上公司空白的那一筆（核心規則 85 放行公司空白，正是要補的洞；
        # 公司照常的 B 工項會先被 85 擋，M-B）
        # RoleMatrixCase.meta 已把各工程的工項記進來（setUpClass 開頭帶進 iso_meta），其中 PS2 的工項公司是 S2——
        # 它被核心 85 擋、不是被本規則擋，留著會讓「關掉規則 → 讀得到 B」恆紅（green 第一次實跑就紅在這裡），拿掉
        cls.iso_meta['project.task'].pop(cls.tasks[cls.p_iso_b].id, None)
        note(cls.tasks[cls.p_iso_a], cls.p_iso_a)
        note(cls.task_b_blank, cls.p_iso_b)
        # 預約式：A＝R、B＝RB
        for company, project in cls.s4_reservation.items():
            slip = cls._slip(project)
            note(slip, project)
            note(env['reservation.notification.slip.line'].create({
                'slip_id': slip.id, 'task_id': cls.tasks[project].id, 'item_no': '1', 'unit': '式'}), project)
            note(env['reservation.notification.slip.suspension'].create({
                # 要填復工日：通報單不是停工狀態時不准有未復工的停工紀錄（_check_suspension_consistency）
                'slip_id': slip.id, 'suspend_date': today, 'resume_date': today, 'reason': 'S4 停工'}), project)
            note(cls._make_doc('reservation.defect.improvement', project, cls.co_a), project)
            inspection = cls._make_doc('reservation.self.inspection', project, cls.co_a)
            note(inspection, project)
            note(env['reservation.self.inspection.item'].create({
                'inspection_id': inspection.id, 'check_item': 'S4 項目'}), project)
            note(env['reservation.self.inspection.measure.line'].create({
                'inspection_id': inspection.id, 'block_id': block.id, 'template': block.template, 'result': 'pass'}),
                 project)
        # 工程空白的工項（私人任務）：只給被指派的人（核心規則 125）；指派給只屬 A 與只屬 B 的工程後台使用者，
        # 公司清空（核心規則 85 放行公司空白）——這樣擋不擋它只看本規格的規則
        cls.sa_b = cls._user('s4_sa_b', ['base.group_user', SUPERVISOR_ADMIN], company=cls.co_iso_b, companies=cls.co_iso_b)
        cls.private_task = env['project.task'].create({
            'name': 'S4 私人任務', 'user_ids': [(6, 0, (cls.sa_a | cls.sa_b).ids)], 'company_id': False})

    @classmethod
    def _s5_fixtures(cls):
        """S5 的 20 個模型：A、B 各至少一筆（掛 PA／PS2），記進 iso_meta；另建工程空白的幾筆（不進 iso_meta，各有專屬的格）。"""
        env = cls.env
        today = fields.Date.today()
        cls.iso_meta.update({model: {} for model in EXPECT_COMPANY_MODELS if model not in cls.iso_meta})

        def note(records, project):
            for record in records:
                cls.iso_meta[record._name][record.id] = project

        category = env['supervision.equipment.category'].create({'name': 'S5 機具分類'})
        for project, company in ((cls.p_iso_a, cls.co_iso_a), (cls.p_iso_b, cls.co_iso_b)):
            tag = project.code
            itype = env['self.inspection.type'].create({'name': f'S5 專屬樣板 {tag}', 'project_id': project.id})
            note(itype, project)
            note(env['self.inspection.type.timing'].create({'type_id': itype.id, 'name': 'S5 時機'}), project)
            note(env['self.inspection.type.stage'].create({'type_id': itype.id, 'name': 'S5 段落'}), project)
            note(env['self.inspection.type.item'].create({'type_id': itype.id, 'name': 'S5 項目'}), project)
            note(env['self.inspection.type.measure'].create({
                'type_id': itype.id, 'name': 'S5 量測', 'template': S5_MEASURE_TEMPLATE}), project)
            prefix = env['defect.improvement.prefix.config'].search([('project_id', '=', project.id)])
            assert len(prefix) == 1, f'夾具：{tag} 應有一組缺失編號前綴（_project／_role_project 建的）'
            note(prefix, project)
            note(env['document.template'].create({
                'name': f'S5 專案樣板 {tag}', 'template_type': S5_TEMPLATE_TYPE_PROJECT,
                'project_id': project.id, 'company_id': company.id}), project)
            note(env['construction.meeting.record'].create({
                'name': f'S5 會議 {tag}', 'project_id': project.id, 'company_id': company.id}), project)
            schedule = env['construction.weekly.schedule'].create({
                'supervision_project_id': project.id, 'week_start': today})
            note(schedule, project)
            note(env['construction.weekly.schedule.line'].create({
                'schedule_id': schedule.id, 'task_id': cls.tasks[project].id}), project)
            preliminary = env['acceptance.preliminary'].create({'name': f'S5-PRE-{tag}', 'project_id': project.id})
            note(preliminary, project)
            note(env['acceptance.preliminary.line'].create({
                'acceptance_id': preliminary.id, 'name': 'S5 初驗項目'}), project)
            final = env['acceptance.final'].create({
                'name': f'S5-FIN-{tag}', 'project_id': project.id, 'preliminary_acceptance_id': preliminary.id})
            note(final, project)
            note(env['acceptance.final.line'].create({'acceptance_id': final.id, 'name': 'S5 正驗項目'}), project)
            note(env['acceptance.defect'].create({
                'name': f'S5-DEF-{tag}', 'project_id': project.id, 'source': 'preliminary',
                'preliminary_acceptance_id': preliminary.id, 'description': 'S5 驗收缺失', 'deadline': today}), project)
            closure = env['project.closure'].create({
                'name': f'S5-CLO-{tag}', 'project_id': project.id, 'final_acceptance_id': final.id})
            note(closure, project)
            note(env['project.closure.document'].create({'closure_id': closure.id, 'name': 'S5 結案文件'}), project)
            equipment = env['supervision.equipment'].create({
                'name': f'S5 機具 {tag}', 'category_id': category.id, 'project_id': project.id})
            note(equipment, project)
            note(env['supervision.equipment.request'].create({
                'name': f'S5 維護請求 {tag}', 'equipment_id': equipment.id}), project)
            note(env['supervision.plan.control'].create({'name': f'S5 計畫書 {tag}', 'project_id': project.id}), project)
        # 驗收四種主單的 B：把 stored related 的 company_id 清空——驗收模組原有的群組規則（Internal User）公司空白放行，
        # 公司照常的 B 會先被那條擋、不是被本規則擋（M-B；dev 現況 0 筆，這是「related 失真」時本規則才擋得住的那種）
        env.flush_all()
        for model in ACCEPTANCE_COMPANY_RULE_MODELS:
            ids = [rid for rid, project in cls.iso_meta[model].items() if project == cls.p_iso_b]
            assert ids, f'夾具：{model} 在 B 要有紀錄'
            env.cr.execute(f'UPDATE {env[model]._table} SET company_id = NULL WHERE id IN %s', [tuple(ids)])
            env[model].browse(ids).invalidate_recordset(['company_id'])
        # 工程空白的幾筆（不進 iso_meta）：全域樣板＋項目；每家公司一份系統預設、一份公司層級的文件樣板；每家公司一場沒選工程的會議
        cls.s5_global_type = env['self.inspection.type'].create({'name': 'S5 全域樣板'})
        cls.s5_global_item = env['self.inspection.type.item'].create({
            'type_id': cls.s5_global_type.id, 'name': 'S5 全域樣板項目'})
        cls.s5_default_template, cls.s5_company_template, cls.s5_company_meeting = {}, {}, {}
        for company, company_type in ((cls.co_iso_a, S5_TEMPLATE_TYPE_COMPANY_A),
                                      (cls.co_iso_b, S5_TEMPLATE_TYPE_COMPANY_B)):
            cls.s5_default_template[company] = env['document.template'].create({
                'name': f'S5 系統預設 {company.name}', 'template_type': S5_TEMPLATE_TYPE_DEFAULT,
                'is_default': True, 'company_id': company.id})
            cls.s5_company_template[company] = env['document.template'].create({
                'name': f'S5 公司層級 {company.name}', 'template_type': company_type,
                'company_id': company.id})
            cls.s5_company_meeting[company] = env['construction.meeting.record'].create({
                'name': f'S5 公司內部會議 {company.name}', 'company_id': company.id})

    # ── 期望值（夾具獨立寫出）──────────────────────────────────────────
    def _fixture_company(self, project):
        """夾具的工程屬哪家公司：DashScopeCase._project 與 RoleMatrixCase 都建在 S，只有 PS2 建在 S2；
        S4 另建的預約式工程 RB 也建在 S2。"""
        if project == self.p_iso_rb:
            return self.co_s2
        self.assertIn(project, self.all_projects, f'不認得的夾具工程 {project.code}')
        return self.co_s2 if project == self.p_s2 else self.co_s

    def _ids_of(self, model, company):
        return {rid for rid, project in self.iso_meta[model].items() if self._fixture_company(project) == company}

    def _seen(self, user, model, companies=None):
        companies = companies or user.sudo().company_ids
        env = self.env(user=user, context={'active_test': False, 'allowed_company_ids': companies.ids})
        if model in KEYED_MODELS:
            # SQL 檢視、id 不穩定：以夾具工項限縮，回傳「工項-檢驗項目」鍵
            first, second = KEYED_MODELS[model]
            task_ids = sorted({int(key.split('-')[0]) for key in self.iso_meta[model]})
            rows = env[model].search_read([(first, 'in', task_ids)], [first, second])
            return {f'{row[first][0]}-{row[second][0]}' for row in rows} & set(self.iso_meta[model])
        return set(env[model].search([('id', 'in', list(self.iso_meta[model]))]).ids)

    def _subjects(self):
        """(標籤, 帳號, 選取的公司, 模型) × 期望看得到的公司。"""
        both = self.co_iso_a | self.co_iso_b
        sa_models = sorted(set(EXPECT_COMPANY_MODELS) - PROJECT_USER_ONLY_MODELS)
        return [
            ('工程後台使用者只屬 A', self.sa_a, self.co_iso_a, sa_models, self.co_iso_a),
            ('工程後台使用者 A＋B 全選', self.sa_ab, both, sa_models, both),
            ('工程後台使用者 A＋B 只選 A（行為測試）', self.sa_ab, self.co_iso_a, sa_models, self.co_iso_a),
            ('一般內部帳號只屬 A', self.int_a, self.co_iso_a, sorted(INTERNAL_USER_MODELS), self.co_iso_a),
            ('工程後台使用者＋專案 Manager 只屬 A', self.rpt_a, self.co_iso_a, sorted(EXPECT_COMPANY_MODELS), self.co_iso_a),
        ]

    # ── 1. 表驅動：看得到的 id 兩個方向都比 ─────────────────────────────
    def test_isolation_table(self):
        checked = 0
        for label, user, selected, models, visible_companies in self._subjects():
            for model in models:
                with self.subTest(subject=label, model=model):
                    own, other = self._ids_of(model, self.co_iso_a), self._ids_of(model, self.co_iso_b)
                    self.assertTrue(own and other, f'{model}：夾具兩家公司都要有紀錄（否則恆真）')
                    expected = set().union(*(self._ids_of(model, c) for c in visible_companies))
                    seen = self._seen(user, model, selected)
                    self.assertTrue(own <= seen, f'{label} × {model}：自己公司的紀錄要讀得到（排除 ACL 先擋），少了 {sorted(own - seen)}')
                    self.assertEqual(seen, expected, f'{label} × {model}：多 {sorted(seen - expected)}、少 {sorted(expected - seen)}')
                    checked += 1
        self.assertGreaterEqual(checked, len(EXPECT_COMPANY_MODELS), '表驅動檢查的組數過少')

    # ── 2. 每條規則：關掉 → 讀得到 B；打開 → 讀不到 B（M-B；18 條規則的 mutation）─────────
    def test_each_rule_is_what_hides_other_company(self):
        Rule = self.env['ir.rule'].sudo()
        for model, xmlid in EXPECT_COMPANY_MODELS.items():
            user = self.rpt_a if model in PROJECT_USER_ONLY_MODELS else self.sa_a
            with self.subTest(model=model):
                rule = self.env.ref(xmlid, raise_if_not_found=False)
                self.assertTrue(rule, f'{model}：找不到規則 {xmlid}')
                own, other = self._ids_of(model, self.co_iso_a), self._ids_of(model, self.co_iso_b)
                self.assertTrue(own and other, model)
                seen = self._seen(user, model)
                self.assertTrue(own <= seen, f'{model}：規則開著時自己公司的要讀得到')
                self.assertFalse(seen & other, f'{model}：規則開著時讀不到 B')
                Rule.browse(rule.id).write({'active': False})
                self.env.registry.clear_cache()
                try:
                    seen_off = self._seen(user, model)
                    self.assertTrue(other <= seen_off, f'{model}：關掉這條規則後 B 應讀得到（證明擋 B 的是這條，不是別道防線）')
                finally:
                    Rule.browse(rule.id).write({'active': True})
                    self.env.registry.clear_cache()
                self.assertFalse(self._seen(user, model) & other, f'{model}：規則恢復後又讀不到 B')

    # ── 3. 盤點：資料庫裡本規格新增的全域規則 ＝ 表（兩個方向都比，L2⑨）──────────
    def test_rule_inventory_matches_table(self):
        data = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'ir.rule'), ('module', 'in', list(RULE_MODULES)),
            ('name', '=like', RULE_XMLID_PREFIX + '%')])
        self.assertTrue(data, '一條都找不到（前綴或模組寫錯時這裡要紅，不是恆真）')
        found = {f'{d.module}.{d.name}' for d in data}
        self.assertEqual(found, set(EXPECT_COMPANY_MODELS.values()),
                         f'多 {sorted(found - set(EXPECT_COMPANY_MODELS.values()))}、'
                         f'少 {sorted(set(EXPECT_COMPANY_MODELS.values()) - found)}')
        rules = self.env['ir.rule'].sudo().with_context(active_test=False).browse(data.mapped('res_id'))
        self.assertEqual(sorted(rules.mapped('model_id.model')), sorted(EXPECT_COMPANY_MODELS),
                         '規則掛的模型集合要等於表（每個模型恰好一條）')
        for xmlid_model, xmlid in EXPECT_COMPANY_MODELS.items():
            rule = self.env.ref(xmlid)
            with self.subTest(model=xmlid_model):
                self.assertEqual(rule.model_id.model, xmlid_model)
                self.assertTrue(rule.active and rule['global'] and not rule.groups, f'{xmlid}：要啟用、全域、不掛群組')
                self.assertTrue(rule.perm_read and rule.perm_write and rule.perm_create and rule.perm_unlink,
                                f'{xmlid}：讀寫建刪都要套')
                self.assertIn('company_ids', rule.domain_force, xmlid)

    # ── 3b. 寫後檢查的欄位表＝從資料庫規則推出來的表（兩個方向都比；S3 fix2，第二輪 simplifier medium／skeptic F1）──
    def _rule_fields(self):
        """{模型: 規則用得到、寫得進去的欄位}，從資料庫裡的規則推：domain 每個 leaf 路徑的第一段，扣掉 LOG_ACCESS_COLUMNS
        （核心 write 會把它們拿掉，寫不進去），stored related 欄位再展開到它的來源欄位（related 的 readonly 只是畫面屬性，
        ORM write 寫得進去；改來源也會讓它跟著變）。SQL 檢視（_auto=False）寫不了，跳過。"""
        context = dict(self.env['ir.rule']._eval_context(), company_ids=[])
        derived = {}
        for model, xmlid in EXPECT_COMPANY_MODELS.items():
            Model = self.env[model]
            if not Model._auto:
                continue
            todo = [leaf[0].split('.', 1)[0]
                    for leaf in safe_eval(self.env.ref(xmlid).domain_force, context) if expression.is_leaf(leaf)]
            names = derived.setdefault(model, set())
            while todo:
                name = todo.pop()
                if name in LOG_ACCESS_COLUMNS or name in names:
                    continue
                names.add(name)
                field = Model._fields[name]
                if field.related and field.store:
                    todo.append(field.related.split('.', 1)[0])
        return derived

    def test_write_guard_table_matches_rules(self):
        """COMPANY_RULE_FIELDS 是規則 domain 的第二份：少一列（或一個欄位）寫入洞就悄悄打開，多一列只是多查。
        這裡把它鎖在資料庫的規則上；另外要求每一個 (模型, 欄位) 都有一格行為測試（REPARENT_CELLS）。"""
        derived = self._rule_fields()
        self.assertEqual(set(derived), set(EXPECT_COMPANY_MODELS) - SQL_VIEW_MODELS,
                         '推得出欄位的模型要是 18 個減 SQL 檢視（_auto 判斷壞掉時這裡要紅，不是兩邊都空而恆真）')
        table = {model: set(names) for model, names in COMPANY_RULE_FIELDS.items()}
        self.assertEqual(set(table), set(derived),
                         f'表上多 {sorted(set(table) - set(derived))}、少 {sorted(set(derived) - set(table))}')
        for model in sorted(derived):
            with self.subTest(model=model):
                self.assertTrue(derived[model], f'{model}：規則推不出任何欄位')
                self.assertEqual(table[model], derived[model],
                                 f'{model}：表上多 {sorted(table[model] - derived[model])}、少 {sorted(derived[model] - table[model])}')
        pairs = {(model, name) for model, names in derived.items() for name in names}
        cells = {(model, field) for model, field, _kind in REPARENT_CELLS}
        self.assertEqual(len(cells), len(REPARENT_CELLS), 'REPARENT_CELLS 有重複的格')
        self.assertFalse(cells & SPECIAL_CELLS, 'SPECIAL_CELLS 的格不該同時在 REPARENT_CELLS')
        cells |= SPECIAL_CELLS
        self.assertEqual(cells, pairs, f'行為測試多 {sorted(cells - pairs)}、少 {sorted(pairs - cells)}')

    # ── 4. 工程空白的草稿（#2 估驗、#8 變更單、#9 變更明細）：本人存得進、讀得回；別人讀不到 ──
    def _make_blank_drafts(self, user):
        """以 user 本人身分（非 sudo）走畫面上的正當入口：先存工程空白的估驗、變更單，再在空工程變更單上加一筆明細。"""
        env = self.env(user=user, context={'allowed_company_ids': user.company_ids.ids})
        estimate = env['payment.estimate'].create({'estimate_date': fields.Date.today()})
        order = env['contract.change.order'].create({})
        line = env['contract.change.order.line'].create({'change_order_id': order.id, 'item_name': 'S3 空工程明細'})
        env.flush_all()
        return estimate, order, line

    def test_blank_project_draft_creator_can_save_and_read(self):
        estimate, order, line = self._make_blank_drafts(self.sa_a)
        self.assertFalse(estimate.sudo().project_id or order.sudo().project_id, '夾具：工程要是空白')
        for record in (estimate, order, line):
            with self.subTest(model=record._name):
                env = self.env(user=self.sa_a, context={'allowed_company_ids': self.sa_a.company_ids.ids})
                self.assertEqual(env[record._name].search([('id', '=', record.id)]).ids, record.ids,
                                 f'{record._name}：建立者要搜得到自己剛存的草稿')
                env[record._name].browse(record.id).read(['display_name'])
                env[record._name].browse(record.id).check_access('write')

    def test_blank_project_draft_hidden_from_others(self):
        estimate, order, line = self._make_blank_drafts(self.sa_a)
        for other in (self.sa_a2, self.sa_ab):
            env = self.env(user=other, context={'allowed_company_ids': other.company_ids.ids})
            for record in (estimate, order, line):
                with self.subTest(user=other.login, model=record._name):
                    self.assertFalse(env[record._name].search([('id', '=', record.id)]),
                                     f'{record._name}：別人（同公司的工程後台使用者也一樣）搜不到工程空白的草稿')
                    with self.assertRaises(AccessError):
                        env[record._name].browse(record.id).read(['display_name'])

    # ── 5. 寫入面（S3 fix1）：改掛到別家公司 → 被拒、資料沒變 ─────────────────
    def _env_of(self, user):
        return self.env(user=user, context={'allowed_company_ids': user.company_ids.ids})

    def _iso_project(self, model, project):
        """預約式模型（S4）沒有掛在 PA／PS2：A 換成 R、B 換成 RB（同一家公司的預約式工程）。"""
        if model in RESERVATION_MODELS and project in (self.p_iso_a, self.p_iso_b):
            return self.s4_reservation[self._fixture_company(project)]
        return project

    def _iso_one(self, model, project):
        """夾具裡掛在 project 的一筆（id 最小的，固定）。"""
        project = self._iso_project(model, project)
        ids = [rid for rid, owner in self.iso_meta[model].items() if owner == project]
        self.assertTrue(ids, f'夾具：{model} 在 {project.code} 沒有紀錄')
        return self.env[model].browse(min(ids))

    def _target(self, kind, project, model=None):
        if kind == TARGET_PROJECT:
            return self._iso_project(model, project)
        if kind == TARGET_TASK:
            return self.tasks[project]
        if kind == TARGET_COMPANY:
            return self._fixture_company(project)
        return self._iso_one(kind, project)

    def _is_related(self, model, field):
        """欄位是不是 stored related（看模型的欄位定義，不看寫入面實作）。"""
        return bool(self.env[model]._fields[field].related)

    def _assert_unchanged(self, record, field, before):
        record.invalidate_recordset()
        self.assertEqual(record.sudo()[field], before, f'{record._name}.{field}：被拒之後資料不可以變')

    def test_reparent_to_other_company_refused(self):
        """只屬 A 的工程後台使用者把 A 的紀錄改掛到 B（每一個規則欄位一格）→ 被拒、資料沒變。

        每一格在自己的、一定回滾的 savepoint 裡跑：沒擋住時那一格寫進去的改動不會連累下一格。
        期望：related 欄位（8 格）→ UserError「不能直接改」（寫入前就拒）；其餘 17 格 → AccessError。
        擋下的不一定是寫後檢查：25 格裡只有 5 格（請款、計量驗收、非契約工項的工程，進度報告明細的報告，工項版本的工項）
        只靠它——拿掉寫後檢查（mutation W1）時正是這 5 格紅。另外 11 格的欄位由 relational_input_guard 守
        （呼叫端給的 id 自己要讀得到，B 的工程／父單讀不到），related 的 8 格由「不能直接改」擋；
        work.acceptance.line 那一格另有附帶的擋：work_acceptance.py 的 write 覆寫寫完後以本人身分算超約
        （_is_over_contract 讀新父單）→ 讀不到 B 的驗收就 AccessError——那是附帶效果、不是設計好的防線。
        拿掉表上任一列時，那一列至少有一格會紅（只有 relational_input_guard 守的欄位除外，那幾格靠鎖定測試）。
        **S4 fix1 起上面的分工改變**：comodel 是公司隔離模型的 many2one 都由 relational_input_guard 守，本測試的格（目標都讀不到）
        一律先被它擋；拿掉寫後檢查（W1）這裡不再有格紅，寫後檢查改由 test_post_write_check_isolated_cell 隔離。
        S4：工項那一格由「工程後台使用者＋專案 Manager」寫（工程後台使用者沒有專案群組、寫不了有工程的工項，
        寫前檢查就不過——測不到防線，M-B）。S4 各格由誰擋下見 S4_report.md 的 mutation 節。
        """
        for model, field, kind in REPARENT_CELLS:
            env = self._env_of(self.rpt_a if model in PROJECT_WRITE_MODELS else self.sa_a)
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                before = record.sudo()[field]
                target = self._target(kind, self.p_iso_b, model)
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                if model == 'project.task.version':
                    # 版本號要避開目標工項已有的（唯一鍵 task_id＋version）：沒擋住時寫入要真的成功，紅的才是這道檢查
                    record.sudo().write({'version': max(target.sudo().version_ids.mapped('version') or [0]) + 1})
                # 寫前檢查過得了：被拒不是因為本來就不能寫這筆（M-B）
                env[model].browse(record.id).check_access('write')
                if self._is_related(model, field):
                    with self.assertRaises(UserError, msg=f'{model}.{field} 直接改成 B 要被拒') as ctx:
                        env[model].browse(record.id).write({field: target.id})
                        env.flush_all()
                    self.assertIn(RELATED_FIELD_HINT, str(ctx.exception), '擋下它的要是「related 不能直接改」')
                else:
                    with self.assertRaises(AccessError, msg=f'{model}.{field} 改掛到 B 要被拒'):
                        env[model].browse(record.id).write({field: target.id})
                        env.flush_all()
                self._assert_unchanged(record, field, before)

    def test_related_field_not_writable_even_for_two_company_user(self):
        """同屬 A＋B 的帳號把 A 工程單據的 related 欄位直接改成 B → UserError、資料沒變（第二輪 skeptic F2）。

        寫後檢查擋不到這種人：B 也在他的允許公司裡。沒擋時值就和工程脫鉤——只屬 A 的同事看不到、只屬 B 的人看得到。
        """
        env = self.env(user=self.sa_ab, context={'allowed_company_ids': (self.co_iso_a | self.co_iso_b).ids})
        checked = 0
        for model, field, kind in REPARENT_CELLS:
            if not self._is_related(model, field):
                continue
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                before = record.sudo()[field]
                target = self._target(kind, self.p_iso_b, model)
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                env[model].browse(record.id).check_access('write')
                with self.assertRaises(UserError, msg=f'{model}.{field}：兩家都屬的帳號直接改成 B 也要被拒') as ctx:
                    env[model].browse(record.id).write({field: target.id})
                    env.flush_all()
                self.assertIn(RELATED_FIELD_HINT, str(ctx.exception), '擋下它的要是「related 不能直接改」')
                self._assert_unchanged(record, field, before)
                checked += 1
        self.assertEqual(checked, RELATED_CELL_COUNT, 'related 欄位的格數不對（欄位定義或表改了要回頭看）')

    # ── 6. 有工程的單不能變成沒有工程（估驗、變更單、變更明細的工程空白退路）──────
    def test_blank_project_cannot_be_reached_by_clearing_others(self):
        """同公司有寫入權的人清空別人的估驗／變更單的工程 → 被拒（red-team F1：改了就只剩建立者看得到）。"""
        env = self._env_of(self.sa_a)
        for model in BLANK_FALLBACK_MODELS:
            with self.subTest(model=model):
                record = self._iso_one(model, self.p_iso_a)
                self.assertNotEqual(record.sudo().create_uid, self.sa_a, '夾具：要是別人建的')
                env[model].browse(record.id).check_access('write')
                with self.assertRaises(UserError) as ctx:
                    env[model].browse(record.id).write({'project_id': False})
                self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
                self._assert_unchanged(record, 'project_id', self.p_iso_a)

    def test_blank_project_cannot_be_reached_by_clearing_own(self):
        """建立者清空自己的估驗／變更單的工程 → 也被拒（清了同事就看不到）。"""
        env = self._env_of(self.sa_a)
        today = fields.Date.today()
        own = {
            'payment.estimate': env['payment.estimate'].create({'estimate_date': today, 'project_id': self.p_iso_a.id}),
            'contract.change.order': env['contract.change.order'].create({'project_id': self.p_iso_a.id}),
        }
        for model, record in own.items():
            with self.subTest(model=model):
                self.assertEqual(record.sudo().create_uid, self.sa_a, '夾具：要是本人建的')
                with self.assertRaises(UserError) as ctx:
                    record.write({'project_id': False})
                self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
                self._assert_unchanged(record, 'project_id', self.p_iso_a)

    def test_line_cannot_move_to_own_blank_order(self):
        """有工程的變更明細改掛到自己建的空工程變更單 → 被拒（明細規則的建立者退路會放行它，但同事就看不到了）。"""
        env = self._env_of(self.sa_a)
        line = self._iso_one('contract.change.order.line', self.p_iso_a)
        before = line.sudo().change_order_id
        blank = env['contract.change.order'].create({})
        self.assertFalse(blank.project_id, '夾具：空工程變更單')
        env['contract.change.order.line'].browse(line.id).check_access('write')
        with self.assertRaises(UserError) as ctx:
            env['contract.change.order.line'].browse(line.id).write({'change_order_id': blank.id})
        self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
        self._assert_unchanged(line, 'change_order_id', before)

    # ── 7. 正當流程照常（W-3 grep 找到的兩個精靈、同公司內改掛、sudo）──────────
    def test_legit_import_wizard_sets_project_on_blank_estimate(self):
        """「匯入工程案件」：本人先存工程空白的估驗，精靈替它設工程並帶入明細。"""
        env = self._env_of(self.sa_a)
        today = fields.Date.today()
        estimate = env['payment.estimate'].create({'estimate_date': today})
        wizard = env['estimate.import.wizard'].create({
            'estimate_id': estimate.id, 'project_id': self.p_iso_a.id, 'estimate_date': today})
        wizard._load_tasks_from_project()
        self.assertTrue(wizard.line_ids, '夾具：工程要有契約工項可匯入')
        wizard.action_import()
        estimate.invalidate_recordset()
        self.assertEqual(estimate.project_id, self.p_iso_a)
        self.assertTrue(estimate.line_ids, '明細要帶進來')
        env['payment.estimate'].browse(estimate.id).check_access('write')

    def test_legit_change_wizard_sets_project_on_blank_order(self):
        """契約變更精靈：本人先存工程空白的變更單，精靈替它設工程（只調發包工程費、不動工項）。"""
        env = self._env_of(self.sa_a)
        order = env['contract.change.order'].create({})
        wizard = env['contract.change.wizard'].create({
            'change_order_id': order.id, 'project_id': self.p_iso_a.id, 'lump_adjust_amount': LUMP_ADJUST_AMOUNT})
        wizard.action_confirm()
        order.invalidate_recordset()
        self.assertEqual(order.project_id, self.p_iso_a)

    def test_legit_reparent_within_company_and_sudo(self):
        """同公司內改掛照常；sudo（系統內部流程）改掛到別家、清空工程也照常。"""
        env = self._env_of(self.sa_a)
        same_company = self.p_b
        self.assertEqual(self._fixture_company(same_company), self.co_iso_a, '夾具：同公司的另一個工程')
        for model, field, kind in REPARENT_CELLS:
            # S3 fix1 的 5 格（fix2 補的格不在這裡：related 欄位本來就不能直接寫，其餘另有唯一鍵等與本題無關的條件）
            if kind != TARGET_PROJECT or model not in SAME_COMPANY_REPARENT_MODELS:
                continue
            with self.subTest(model=model, mode='同公司'):
                record = self._iso_one(model, self.p_iso_a)
                env[model].browse(record.id).write({field: same_company.id})
                record.invalidate_recordset()
                self.assertEqual(record.sudo()[field], same_company)
        line = self._iso_one('work.acceptance.line', self.p_iso_a)
        other_acceptance = self.env['work.acceptance'].create({
            'name': 'S3 同公司另一張驗收', 'project_id': self.p_iso_a.id, 'contractor_company_id': self.co_a.id})
        with self.subTest(model='work.acceptance.line', mode='同公司'):
            env['work.acceptance.line'].browse(line.id).write({'acceptance_id': other_acceptance.id})
            line.invalidate_recordset()
            self.assertEqual(line.sudo().acceptance_id, other_acceptance)
        with self.subTest(mode='sudo'):
            claim = self._iso_one('payment.claim', self.p_iso_b)
            claim.sudo().write({'project_id': self.p_iso_a.id})
            estimate = self._iso_one('payment.estimate', self.p_iso_b)
            estimate.sudo().write({'project_id': False})
            self.env.invalidate_all()
            self.assertEqual(claim.sudo().project_id, self.p_iso_a)
            self.assertFalse(estimate.sudo().project_id)

    # ── 7b. S4：「工程空白放行」的格、同公司內改掛照常 ─────────────────────────────
    def _private_task_readers(self):
        found = set()
        for user in (self.sa_a, self.sa_b):
            if self._env_of(user)['project.task'].search([('id', '=', self.private_task.id)]):
                found.add(user)
        return found

    def test_s4_blank_project_shared(self):
        """工項：工程空白的私人任務（公司也空白），被指派的只屬 A、只屬 B 兩人都讀得到；
        把本規則改成不放行工程空白 → 兩人都讀不到（證明放行的是規則的那一段，rig 有效，M-B）。
        檢試驗項目／頻率條件、資料夾、工程文件：規格說工程空白放行（規則也寫了那一段），但工程欄位資料庫 NOT NULL，
        空白的紀錄建不出來——這裡驗 NOT NULL；哪天改成可空，這一格會紅，要回頭補「A、B 都讀得到」的真格。"""
        both = {self.sa_a, self.sa_b}
        self.assertEqual(self._private_task_readers(), both, '工程空白的私人任務：被指派的 A、B 都讀得到')
        rule = self.env.ref(EXPECT_COMPANY_MODELS['project.task']).sudo()
        original = rule.domain_force
        rule.write({'domain_force': "[('project_id.company_id', 'in', company_ids)]"})
        self.env.registry.clear_cache()
        try:
            self.assertEqual(self._private_task_readers(), set(), 'rig：規則不放行工程空白時兩人都讀不到')
        finally:
            rule.write({'domain_force': original})
            self.env.registry.clear_cache()
        self.assertEqual(self._private_task_readers(), both, '規則恢復後兩人又讀得到')
        for model, (table, column) in BLANK_SHARED_NOT_NULL.items():
            with self.subTest(model=model):
                self.assertIn("('project_id', '=', False)", self.env.ref(EXPECT_COMPANY_MODELS[model]).domain_force.replace(
                    'standard_id.project_id', 'project_id'), f'{model}：規則要有「工程空白放行」那一段（規格語意）')
                self.env.cr.execute(
                    'SELECT is_nullable FROM information_schema.columns '
                    'WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s', [table, column])
                self.assertEqual(self.env.cr.fetchall(), [('NO',)],
                                 f'{table}.{column} 改成可空了：補一格「工程空白的 {model} A、B 都讀得到」')

    def test_s4_legit_reparent_within_company(self):
        """S4 的寫入面不擋正當操作：同公司內改掛工程／父單照常（工程後台使用者；工項由工程後台使用者＋專案 Manager）。"""
        same_company = self.p_b
        self.assertEqual(self._fixture_company(same_company), self.co_iso_a, '夾具：同公司的另一個工程')
        # 缺失不在這裡：改掛工程時缺失編號依新工程重算，會撞夾具 PB 上既有的編號（唯一鍵；與 S4 無關的既有行為）
        cases = [(model, 'project_id', same_company, {}) for model in (
            'supervision.photo', 'supervision.review.application', 'supervision.project.member',
            'daily.log.man.machine', 'supervision.test.record', 'project.task')]
        other_sheet = self._make_doc('daily.log.sheet', self.p_iso_a, self.co_a)
        # 日誌明細的日期要等於日誌日期（_check_date_in_sheet_range）：一起改
        cases.append(('daily.log.line', 'sheet_id', other_sheet, {'date': other_sheet.log_date}))
        for model, field, target, extra in cases:
            user = self.rpt_a if model in PROJECT_WRITE_MODELS else self.sa_a
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                self._env_of(user)[model].browse(record.id).write(dict(extra, **{field: target.id}))
                self.env.flush_all()
                record.invalidate_recordset()
                self.assertEqual(record.sudo()[field], target, f'{model}.{field}：同公司內改掛要成功')

    # ── 7b'. S5：工程空白的三種語意、特殊的三格、正當操作 ─────────────────────────────
    def _sees(self, user, record):
        return bool(self._env_of(user)[record._name].search([('id', '=', record.id)]))

    def _with_rule_off(self, model):
        """把 model 的全域公司規則關掉的 context manager（結束時打開；M-B 用）。"""
        test = self
        rule = self.env.ref(EXPECT_COMPANY_MODELS[model]).sudo()

        class _Off:
            def __enter__(self):
                rule.write({'active': False})
                test.env.registry.clear_cache()

            def __exit__(self, *exc):
                rule.write({'active': True})
                test.env.registry.clear_cache()
        return _Off()

    def test_s5_blank_project_shared_or_company_owned(self):
        """工程空白的三種語意（決定見 README_ROLE_ACCOUNTS §3c）：
        * 全域樣板（＋項目）：只屬 A、只屬 B 的人都讀得到；把規則改成不放行工程空白 → 都讀不到（rig，M-B）。
        * 文件樣板：系統預設不管掛在哪家公司，A、B 都讀得到；公司層級只有自己公司讀得到。
        * 沒選工程的會議記錄：只有記錄自己的公司讀得到。
        每一格「讀不到」都先關掉規則證明本來讀得到（擋下它的是這條規則，不是別道防線）。"""
        users = {self.co_iso_a: self.sa_a, self.co_iso_b: self.sa_b}
        for record in (self.s5_global_type, self.s5_global_item):
            with self.subTest(model=record._name, case='全域樣板 A、B 都讀得到'):
                self.assertTrue(all(self._sees(user, record) for user in users.values()))
                rule = self.env.ref(EXPECT_COMPANY_MODELS[record._name]).sudo()
                original = rule.domain_force
                path = 'project_id' if record._name == 'self.inspection.type' else 'type_id.project_id'
                rule.write({'domain_force': f"[('{path}.company_id', 'in', company_ids)]"})
                self.env.registry.clear_cache()
                try:
                    self.assertFalse(any(self._sees(user, record) for user in users.values()),
                                     'rig：規則不放行工程空白時兩人都讀不到')
                finally:
                    rule.write({'domain_force': original})
                    self.env.registry.clear_cache()
                self.assertTrue(all(self._sees(user, record) for user in users.values()), '規則恢復後又讀得到')
        for company, user in users.items():
            other = self.co_iso_b if company == self.co_iso_a else self.co_iso_a
            with self.subTest(user=user.login, case='系統預設的文件樣板：兩家的都讀得到'):
                self.assertTrue(self._sees(user, self.s5_default_template[company]))
                self.assertTrue(self._sees(user, self.s5_default_template[other]))
            for label, records in (('公司層級的文件樣板', self.s5_company_template),
                                   ('沒選工程的會議記錄', self.s5_company_meeting)):
                with self.subTest(user=user.login, case=label):
                    self.assertTrue(self._sees(user, records[company]), f'{label}：自己公司的要讀得到')
                    self.assertFalse(self._sees(user, records[other]), f'{label}：別家公司的讀不到')
                    with self._with_rule_off(records[other]._name):
                        self.assertTrue(self._sees(user, records[other]),
                                        f'{label}：關掉規則後別家的讀得到（證明擋的是這條規則）')
                    self.assertFalse(self._sees(user, records[other]), f'{label}：規則恢復後又讀不到')

    def test_s5_special_cells_refused(self):
        """SPECIAL_CELLS 的三格，各在自己的 savepoint 裡跑（被拒、資料沒變）：
        * 文件樣板 company_id：A 的公司層級樣板改成 B 公司 → 改完 A 的人讀不到 → 被拒。
        * 會議記錄 company_id：A 的公司內部會議改成 B 公司 → 同上。
        * 文件樣板 is_default：把 B 公司的系統預設取消預設 → 變成 B 的公司層級、A 的人讀不到 → 被拒
          （沒擋的話任何公司的人都能讓別家的系統預設從所有人面前消失）。只有寫後檢查擋得到這一格（布林欄位沒有關聯 id 守衛）。"""
        env = self._env_of(self.sa_a)
        cases = (
            ('document.template', 'company_id', self.s5_company_template[self.co_iso_a], self.co_iso_b.id),
            ('construction.meeting.record', 'company_id', self.s5_company_meeting[self.co_iso_a], self.co_iso_b.id),
            ('document.template', 'is_default', self.s5_default_template[self.co_iso_b], False),
        )
        self.assertEqual({(model, field) for model, field, _record, _value in cases}, set(SPECIAL_CELLS),
                         '每一格 SPECIAL_CELLS 都要有一個案例（上游說有幾格就要有幾格）')
        for model, field, record, value in cases:
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                before = record.sudo()[field]
                env[model].browse(record.id).check_access('write')   # 寫前檢查過得了：被拒不是本來就不能寫（M-B）
                with self.assertRaises(AccessError, msg=f'{model}.{field} 要被拒'):
                    env[model].browse(record.id).write({field: value})
                    env.flush_all()
                self._assert_unchanged(record, field, before)
        # is_default 那一格只靠寫後檢查：拿掉表上文件樣板那一列，同一個寫入就寫得進去（證明擋下它的是那一列）
        record = self.s5_default_template[self.co_iso_b]
        with closing(self.env.cr.savepoint()), patch.dict(company_rule_write_guard.COMPANY_RULE_FIELDS):
            company_rule_write_guard.COMPANY_RULE_FIELDS.pop('document.template')
            env['document.template'].browse(record.id).write({'is_default': False})
            env.flush_all()
            record.invalidate_recordset()
            self.assertFalse(record.sudo().is_default, 'rig：沒有那一列時取消別家的系統預設寫得進去')

    def test_s5_legit_writes(self):
        """S5 的寫入面不擋正當操作（只屬 A 的工程後台使用者）：同公司內改掛、把自己公司的樣板設成系統預設、
        把自己的專屬樣板變成全域、建一場沒選工程的會議、會議補上自己公司的工程。"""
        env = self._env_of(self.sa_a)
        same_company = self.p_b
        self.assertEqual(self._fixture_company(same_company), self.co_iso_a, '夾具：同公司的另一個工程')
        other_schedule = self.env['construction.weekly.schedule'].create({
            'supervision_project_id': same_company.id, 'week_start': fields.Date.today()})
        other_equipment = self.env['supervision.equipment'].create({
            'name': 'S5 同公司另一台機具', 'project_id': same_company.id,
            'category_id': self._iso_one('supervision.equipment', self.p_iso_a).category_id.id})
        cases = [
            ('supervision.plan.control', 'project_id', same_company),
            ('supervision.equipment', 'project_id', same_company),
            ('construction.meeting.record', 'project_id', same_company),
            ('construction.weekly.schedule', 'supervision_project_id', same_company),
            ('construction.weekly.schedule.line', 'schedule_id', other_schedule),
            ('supervision.equipment.request', 'equipment_id', other_equipment),
        ]
        for model, field, target in cases:
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                env[model].browse(record.id).write({field: target.id})
                self.env.flush_all()
                record.invalidate_recordset()
                self.assertEqual(record.sudo()[field], target, f'{model}.{field}：同公司內改掛要成功')
        with self.subTest(case='自己公司的公司層級樣板設成系統預設'), closing(self.env.cr.savepoint()):
            template = self.s5_company_template[self.co_iso_a]
            env['document.template'].browse(template.id).write({'is_default': True})
            self.env.flush_all()
            template.invalidate_recordset()
            self.assertTrue(template.sudo().is_default)
        with self.subTest(case='自己的專屬樣板清空工程＝變成全域樣板'), closing(self.env.cr.savepoint()):
            itype = self._iso_one('self.inspection.type', self.p_iso_a)
            env['self.inspection.type'].browse(itype.id).write({'project_id': False})
            self.env.flush_all()
            itype.invalidate_recordset()
            self.assertFalse(itype.sudo().project_id)
            self.assertTrue(self._sees(self.sa_b, itype), '變成全域之後別家也讀得到')
        with self.subTest(case='建一場沒選工程的會議，再補上自己公司的工程'), closing(self.env.cr.savepoint()):
            meeting = env['construction.meeting.record'].create({'name': 'S5 本人建的會議'})
            self.env.flush_all()
            self.assertEqual(meeting.sudo().company_id, self.co_iso_a, '沒指定時帶本人目前的公司')
            self.assertTrue(self._sees(self.sa_a, meeting))
            self.assertFalse(self._sees(self.sa_b, meeting))
            meeting.write({'project_id': self.p_iso_a.id})
            self.env.flush_all()
            self.assertEqual(meeting.sudo().project_id, self.p_iso_a)

    # ── 7c. S4 fix1：many2one 的顯示名稱（red-team F1）、上 S4 前的檢查 SQL（simplifier medium）──────────
    def _m2o_target(self, kind):
        """B 的目標。工項用「公司空白、工程在 B」那一筆（核心 85 放行公司空白，擋它的只有本規格的規則）。"""
        if kind == TARGET_TASK:
            return self.task_b_blank
        return self._target(kind, self.p_iso_b)

    def test_s4fix1_display_name_cells_refused(self):
        """只屬 A 的工程後台使用者把 B 的工項／缺失／通報單／工程 id 寫進自己紀錄上的 many2one → relational_input_guard
        擋下（AccessError、訊息指名欄位並寫「顯示名稱」）、資料沒變；新紀錄 onchange 帶同一個 id 也擋。
        修之前寫得進去，read／web_read 以 sudo 帶出 B 的顯示名稱（審查重現 s4r1_rt_leak.py：300 筆被藏的工項名稱逐 id 枚舉）。"""
        env = self._env_of(self.sa_a)
        for model, field, kind in DISPLAY_NAME_CELLS:
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                target = self._m2o_target(kind)
                before = record.sudo()[field]
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                with self.assertRaises(AccessError, msg='前提：B 的目標本人直接讀不到'):
                    env[target._name].browse(target.id).read(['display_name'])
                env[model].browse(record.id).check_access('write')   # 寫前檢查過得了：被拒不是本來就不能寫（M-B）
                with self.assertRaises(AccessError, msg=f'{model}.{field} 填 B 的 id 要被拒') as ctx:
                    env[model].browse(record.id).write({field: target.id})
                    env.flush_all()
                message = str(ctx.exception)
                self.assertIn(GUARD_MSG, message, f'擋下它的要是關聯 id 守衛：{message}')
                self.assertIn(f'（{field}）', message, f'訊息要指名欄位：{message}')
                self.assertIn(DISPLAY_NAME_HINT, message, f'訊息要寫「顯示名稱」：{message}')
                self._assert_unchanged(record, field, before)
        model, field, kind = DISPLAY_NAME_CELLS[0]
        with self.assertRaises(AccessError) as ctx:
            env[model].onchange({field: self._m2o_target(kind).id}, [field], {field: {'fields': {'display_name': {}}}})
        self.assertIn(f'（{field}）', str(ctx.exception), 'onchange（新紀錄）也要被同一道守衛擋')

    def test_s4fix1_display_name_legit_writes(self):
        """正當流程照常：同公司的 id 寫得進去；寫回原本就掛著、本人讀不到的現值不擋（既有語意：只查改變了的值）。"""
        env = self._env_of(self.sa_a)
        defect = self._iso_one('general.defect.improvement', self.p_iso_a)
        item = self._iso_one('general.self.inspection.item', self.p_iso_a)
        photo = self._iso_one('supervision.photo', self.p_iso_a)
        cases = ((defect, 'task_id', self.tasks[self.p_iso_a]), (item, 'defect_improvement_id', defect),
                 (photo, 'signboard_project_id', self.p_b))
        for record, field, target in cases:
            with self.subTest(model=record._name, field=field), closing(self.env.cr.savepoint()):
                owner = target if target._name == ISOLATION_ROOT else target.project_id
                self.assertEqual(self._fixture_company(owner), self.co_iso_a, '夾具：目標是同公司的')
                env[record._name].browse(record.id).write({field: target.id})
                env.flush_all()
                record.invalidate_recordset()
                self.assertEqual(record.sudo()[field], target, f'{record._name}.{field}：同公司的要寫得進去')
        with self.subTest(mode='寫回讀不到的現值'), closing(self.env.cr.savepoint()):
            defect.sudo().write({'task_id': self.task_b_blank.id})   # 既有資料（例：搬家前就掛著）
            env['general.defect.improvement'].browse(defect.id).write(
                {'task_id': self.task_b_blank.id, 'defect_description': 'S4 fix1 寫回現值'})
            env.flush_all()
            defect.invalidate_recordset()
            self.assertEqual(defect.sudo().defect_description, 'S4 fix1 寫回現值', '現值沒變的 many2one 不查，其他欄位照常寫進去')

    def test_s4fix1_isolated_many2one_all_guarded(self):
        """鎖定：走訪 registry，每個 comodel 是公司隔離模型的 stored many2one 都在 guarded_fields_of() 裡。
        隔離模型集合在這裡獨立寫（規則表減 SQL 檢視，加上工程），並與實作的 isolated_models() 比。"""
        isolated = (set(EXPECT_COMPANY_MODELS) - SQL_VIEW_MODELS) | {ISOLATION_ROOT}
        self.assertEqual(set(relational_input_guard.isolated_models()), isolated, '實作的隔離模型集合＝規則表（不含 SQL 檢視）＋工程')
        checked, missing = set(), []
        for name in sorted(self.env.registry):
            Model = self.env[name]
            if Model._abstract:
                continue
            guarded = guarded_fields_of(Model)
            for fname, field in Model._fields.items():
                if field.type == 'many2one' and field.store and field.comodel_name in isolated:
                    checked.add((name, fname))
                    if fname not in guarded:
                        missing.append(f'{name}.{fname} → {field.comodel_name}')
        self.assertFalse(missing, f'沒被守的隔離模型 many2one：{missing}')
        cells = {(model, field) for model, field, _kind in DISPLAY_NAME_CELLS}
        self.assertTrue(cells <= checked, f'審查重現的欄位都要被走訪到（上游說有幾格就要有幾格，M-C）：少 {sorted(cells - checked)}')

    def test_post_write_check_isolated_cell(self):
        """寫後檢查（company_rule_write_guard 第 1 點）還隔離得到的一格：S4 fix1 起 comodel 是隔離模型的 many2one 全部由
        relational_input_guard 守，改掛到「讀不到的」目標都先被它擋（test_reparent_* 那 61 格拿掉寫後檢查也照樣綠，
        mutation W1 實跑 SURVIVED）。剩下的是「目標讀得到、改完紀錄卻讀不到」：估驗明細改掛到自己建的工程空白估驗——
        空白估驗靠建立者退路讀得到，估驗明細的規則沒有退路，改完誰都讀不到（沒擋就是一筆明細從畫面上消失）。"""
        env = self._env_of(self.sa_a)
        line = self._iso_one('payment.estimate.line', self.p_iso_a)
        before = line.sudo().estimate_id
        blank = env['payment.estimate'].create({'estimate_date': fields.Date.today()})
        self.assertTrue(env['payment.estimate'].search([('id', '=', blank.id)]),
                        '前提：自己建的空工程估驗讀得到（relational_input_guard 不會擋）')
        env['payment.estimate.line'].browse(line.id).check_access('write')
        with self.assertRaises(AccessError) as ctx:
            env['payment.estimate.line'].browse(line.id).write({'estimate_id': blank.id})
            env.flush_all()
        self.assertNotIn(GUARD_MSG, str(ctx.exception), '擋下它的要是寫後檢查，不是關聯 id 守衛（M-B）')
        self._assert_unchanged(line, 'estimate_id', before)

    # ── S4 收尾（2026-11-13）：工項清空工程、寫後檢查的備援格、連結線上文件 ──────────────
    def test_task_clear_project_only_assignee(self):
        """工項清空工程（變成私人任務）：寫後檢查以寫入者身分檢查，私人任務的核心規則只給被指派的人——
        被指派的人清得掉、沒被指派的人被拒（AccessError）。行為由寫後檢查＋核心 rating_mixin 兩道一起擋（A1）。
        寫入者與 test_reparent_* 一樣用 PROJECT_WRITE_MODELS 的帳號（工程後台使用者寫不了有工程的工項，測不到防線）。"""
        writer = self.rpt_a
        env = self._env_of(writer)
        task = self._iso_one('project.task', self.p_iso_a)
        before = task.sudo().project_id
        self.assertTrue(before, '夾具：工項要有工程')
        task.sudo().write({'user_ids': [(3, writer.id)]})
        self.assertNotIn(writer, task.sudo().user_ids, '前提：寫入者沒被指派')
        env['project.task'].browse(task.id).check_access('write')
        with self.assertRaises(AccessError):
            env['project.task'].browse(task.id).write({'project_id': False})
            env.flush_all()
        self._assert_unchanged(task, 'project_id', before)
        # 規格原本預期「拿掉表上工項那一列，同一個寫入會成功」，實測不是：核心 project 的 rating_mixin.write 在改完 project_id 後
        # 以寫入者身分讀 record.project_id，私人任務讀不到 → 核心自己就 AccessError（odoo/addons/rating/models/rating_mixin.py）。
        # 所以工項這一格和 A2 那兩格一樣有第二道防線；這裡把「拿掉那一列仍被擋」鎖住（不是只靠表上的一列）
        with closing(self.env.cr.savepoint()), patch.dict(company_rule_write_guard.COMPANY_RULE_FIELDS):
            company_rule_write_guard.COMPANY_RULE_FIELDS.pop('project.task')
            with self.assertRaises(AccessError, msg='拿掉表上的工項那一列，核心的 rating_mixin 仍會擋下'):
                env['project.task'].browse(task.id).write({'project_id': False})
                env.flush_all()
        # 被指派的人清得掉
        task.invalidate_recordset()
        task.sudo().write({'user_ids': [(4, writer.id)]})
        env['project.task'].browse(task.id).write({'project_id': False})
        env.flush_all()
        task.invalidate_recordset()
        self.assertFalse(task.sudo().project_id, '被指派的人清空工程要成功')

    def test_backstop_cells_blocked_without_post_write_row(self):
        """寫後檢查表上兩格（停工的 slip_id、量測的 inspection_id）拿掉那一列，改掛到 B 的父單照樣被別的機制擋住——
        把「還有第二道防線」寫成測試（A2）。"""
        cells = tuple(cell for cell in REPARENT_CELLS if (cell[0], cell[1]) in BACKSTOP_CELLS)
        self.assertEqual(len(cells), len(BACKSTOP_CELLS), '夾具：兩格都要在 REPARENT_CELLS 裡')
        env = self._env_of(self.sa_a)
        ran = 0
        for model, field, kind in cells:
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()), \
                    patch.dict(company_rule_write_guard.COMPANY_RULE_FIELDS):
                company_rule_write_guard.COMPANY_RULE_FIELDS.pop(model)
                record = self._iso_one(model, self.p_iso_a)
                before = record.sudo()[field]
                target = self._target(kind, self.p_iso_b, model)
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                env[model].browse(record.id).check_access('write')
                with self.assertRaises(AccessError, msg=f'{model}.{field}：拿掉表上那一列仍要被擋'):
                    env[model].browse(record.id).write({field: target.id})
                    env.flush_all()
                self._assert_unchanged(record, field, before)
                ran += 1
        self.assertEqual(ran, len(BACKSTOP_CELLS), '兩格都要真的跑到')

    def test_linked_doc_other_company_refused(self):
        """「連結線上文件」(linked_doc_id → doc.document) 不能填別家公司的文件（B1；red-team F1 剩下的一格）。"""
        if 'doc.document' not in self.env:
            self.fail('doc.document 不在 registry：要先安裝 dobtor_doc_editor')
        Doc = self.env['doc.document'].sudo()
        doc_b = Doc.create({'name': 'S4 收尾 B 文件', 'company_id': self.co_iso_b.id})
        doc_a = Doc.create({'name': 'S4 收尾 A 文件', 'company_id': self.co_iso_a.id})
        env = self._env_of(self.sa_a)
        self.assertFalse(env['doc.document'].search([('id', '=', doc_b.id)]), '前提：sa_a 搜不到 B 公司的文件')
        self.assertTrue(env['doc.document'].search([('id', '=', doc_a.id)]), '前提：sa_a 搜得到 A 公司的文件')
        defect = self._iso_one('general.defect.improvement', self.p_iso_a)
        before = defect.sudo().linked_doc_id
        with self.assertRaises(AccessError) as ctx:
            env['general.defect.improvement'].browse(defect.id).write({'linked_doc_id': doc_b.id})
            env.flush_all()
        self.assertIn(GUARD_MSG, str(ctx.exception), '擋下它的要是關聯 id 守衛')
        self._assert_unchanged(defect, 'linked_doc_id', before)
        env['general.defect.improvement'].browse(defect.id).write({'linked_doc_id': doc_a.id})
        env.flush_all()
        self.assertEqual(defect.sudo().linked_doc_id, doc_a, '自己公司的文件要填得進去')

    def _assert_precheck_covers(self, sql_file, section_name, expected):
        """runbook 的檢查 SQL 某一段在測試庫實跑：每個資料表恰好一列（第一欄＝資料表、第二欄＝筆數）。
        漏改（新增規則模型沒補、表改名）時這裡紅；SQL 寫壞時 execute 就紅。"""
        path = os.path.join(get_module_path(MODULE), *sql_file)
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        section = re.escape(section_name)
        match = re.search(rf'-- \[{section}\]\n(.*?)-- \[/{section}\]', text, re.S)
        self.assertTrue(match, f'{path} 找不到 [{section_name}] 那一段')
        self.env.cr.execute(match.group(1))
        rows = self.env.cr.fetchall()
        labels = [row[0] for row in rows]
        self.assertEqual(len(labels), len(set(labels)), f'有重複的列：{labels}')
        self.assertEqual(set(labels), expected, f'SQL 多 {sorted(set(labels) - expected)}、少 {sorted(expected - set(labels))}')
        self.assertTrue(all(isinstance(row[1], int) for row in rows), '第二欄要是筆數')

    def test_s4_precheck_sql_covers_every_rule_model(self):
        """runbook/s4_precheck.sql 的 (S4-1)：每個 S4 規則模型（SQL 檢視除外）一列。"""
        s4_models = {model for model, xmlid in EXPECT_COMPANY_MODELS.items()
                     if model not in S5_RULE_MODELS
                     and (xmlid.split('.', 1)[0] in S4_RULE_MODULES or xmlid in S4_RULES_IN_S3_MODULES)}
        self.assertEqual(len(s4_models), S4_RULE_COUNT, '本輪規則模型數（上游說幾個就要幾個）')
        expected = {self.env[model]._table for model in s4_models if self.env[model]._auto}
        self.assertEqual(len(expected), S4_RULE_COUNT - 1, '扣掉一個 SQL 檢視（檢試驗統計）')
        self._assert_precheck_covers(PRECHECK_SQL, PRECHECK_SECTION, expected)

    def test_s5_precheck_sql_covers_every_rule_model(self):
        """runbook/s5_precheck.sql 的 (S5-1)：每個 S5 規則模型一列。S5 的模型集合在這裡獨立寫（S5_RULE_MODELS），
        並與規則表對：表上 S3、S4 以外的模型＝S5 的模型（新增一輪時沒分清楚會紅在這裡）。"""
        self.assertEqual(len(S5_RULE_MODELS), S5_RULE_COUNT, '本輪規則模型數（上游說幾個就要幾個）')
        self.assertTrue(S5_RULE_MODELS <= set(EXPECT_COMPANY_MODELS), 'S5 的模型都要在規則表上')
        self.assertEqual(len(EXPECT_COMPANY_MODELS), 18 + S4_RULE_COUNT + S5_RULE_COUNT, '規則表＝S3 18＋S4＋S5')
        expected = {self.env[model]._table for model in S5_RULE_MODELS}
        self.assertEqual(len(expected), S5_RULE_COUNT)
        self._assert_precheck_covers(S5_PRECHECK_SQL, S5_PRECHECK_SECTION, expected)

    # ── 8. 已經有單據的工程改公司：只有系統管理者（2026-11-12「1b」，第三輪 red-team R1）──────────
    def _env_two(self, user=None):
        """同屬 A＋B、兩家都選的帳號（預設：工程後台使用者 sa_ab）。"""
        user = user or self.sa_ab
        return self.env(user=user, context={'allowed_company_ids': (self.co_iso_a | self.co_iso_b).ids})

    def _fresh_project(self, code, company=None):
        """沒有任何單據的新工程（預設 A 公司；不走 _project／_role_project：那兩個會建進度表與工項，進度表、工項版本都算單據）。
        S4 起資料夾也在寫後檢查表上（算單據），而開案預設會自動建標準資料夾——這裡以 skip_standard_folders 不建
        （「只有自動資料夾」的工程另有一格 test_company_move_allowed_when_project_has_only_empty_folders_or_members）。

        不帶分析帳戶（allow_timesheets=False）：核心改工程公司時會一起改分析帳戶的公司（project _inverse_company_id），
        工程後台使用者沒有分析帳戶寫權 → 核心先 AccessError，測不到這道檢查（M-B）。R1 的洞就在沒有分析帳戶（或帳戶沒公司）
        的工程上（dev 11-12 實查 253 個工程裡 23 個）。"""
        vals = {
            'name': f'{code} 改公司測試工程', 'code': code, 'project_type': 'general', 'state': 'construction',
            'company_id': (company or self.co_iso_a).id, 'contractor_company_ids': [(6, 0, self.co_a.ids)]}
        if 'allow_timesheets' in self.env['project.project']._fields:
            vals['allow_timesheets'] = False
        project = self.env['project.project'].with_context(skip_standard_folders=True).create(vals)
        self.assertFalse(project.account_id, '夾具：不要有分析帳戶')
        self.assertFalse(self.env['supervision.folder'].sudo().search_count([('project_id', '=', project.id)]),
                         '夾具：不要有資料夾')
        return project

    def _fresh_project_with_estimate(self, code, company=None):
        project = self._fresh_project(code, company)
        estimate = self.env['payment.estimate'].create({'project_id': project.id, 'estimate_date': fields.Date.today()})
        return project, estimate

    def _sys_admin_ab(self):
        """系統管理者：與 sa_ab 只差 base.group_system（隔離出「系統管理者放行」這一條）。"""
        return self._user('s3_sys_ab', ['base.group_user', SUPERVISOR_ADMIN, SYSTEM_ADMIN],
                          company=self.co_iso_a, companies=self.co_iso_a | self.co_iso_b)

    def _operator_ab(self):
        """代操作員：與 sa_ab 只差代操作員群組（隔離出「代操作員放行」這一條）。"""
        return self._user('s3_op_ab', ['base.group_user', SUPERVISOR_ADMIN, OPERATOR],
                          company=self.co_iso_a, companies=self.co_iso_a | self.co_iso_b)

    def _assert_move_refused(self, env, projects, company):
        for project in projects:
            env['project.project'].browse(project.id).check_access('write')  # 寫前檢查過得了：被拒不是本來就不能寫（M-B）
        with self.assertRaises(UserError) as ctx:
            env['project.project'].browse(projects.ids).write({'company_id': company.id})
            env.flush_all()
        self.assertIn(COMPANY_MOVE_HINT, str(ctx.exception), '擋下它的要是「有單據的工程只有系統管理者或代操作員能改公司」')
        return str(ctx.exception)

    def test_company_move_refused_when_project_has_estimate(self):
        """同屬 A＋B 的工程後台使用者改「有估驗的工程」的公司 → 被拒；工程、估驗（經工程）的公司都沒變，只屬 A 的同事照樣
        看得到（沒擋時：估驗跟著工程搬到 B、只屬 A 的同事從此看不到——第三輪 red-team R1 的重現）。
        另一格：只有進度表的工程——進度表的 company_id 是 stored related，沒擋時它跟著改成 B。"""
        env = self._env_two()
        project, estimate = self._fresh_project_with_estimate('S3M-EST')
        self._assert_move_refused(env, project, self.co_iso_b)
        self.env.invalidate_all()
        self.assertEqual(project.sudo().company_id, self.co_iso_a, '工程的公司不可以變')
        self.assertEqual(estimate.sudo().project_id.company_id, self.co_iso_a, '估驗（經工程）的公司不可以變')
        self.assertEqual(self._env_of(self.sa_a)['payment.estimate'].search([('id', '=', estimate.id)]).ids, estimate.ids,
                         '只屬 A 的同事要照樣搜得到這張估驗')
        project2 = self._fresh_project('S3M-SCH')
        schedule = self.env['progress.schedule'].create({'project_id': project2.id, 'change_date': fields.Date.today()})
        self.assertEqual(schedule.company_id, self.co_iso_a, '夾具：進度表的公司跟著工程')
        self._assert_move_refused(env, project2, self.co_iso_b)
        self.env.invalidate_all()
        self.assertEqual((project2.sudo().company_id, schedule.sudo().company_id), (self.co_iso_a, self.co_iso_a),
                         '工程與進度表 stored 的公司都不可以變')

    def test_company_move_allowed_when_project_has_no_documents(self):
        """同一個人改「沒有任何單據的工程」的公司 → 成功（這道檢查只管有單據的）。"""
        project = self._fresh_project('S3M-NONE')
        self._env_two()['project.project'].browse(project.id).write({'company_id': self.co_iso_b.id})
        project.invalidate_recordset()
        self.assertEqual(project.sudo().company_id, self.co_iso_b)

    def _project_with_auto_folders(self, code):
        """照一般方式開的工程（不帶 skip_standard_folders）：開案自動建整套標準資料夾（都是空的），除此之外沒有別的單據。"""
        vals = {'name': f'{code} 改公司測試工程', 'code': code, 'project_type': 'general', 'state': 'construction',
                'company_id': self.co_iso_a.id, 'contractor_company_ids': [(6, 0, self.co_a.ids)]}
        if 'allow_timesheets' in self.env['project.project']._fields:
            vals['allow_timesheets'] = False
        project = self.env['project.project'].create(vals)
        self.assertTrue(self.env['supervision.folder'].sudo().search_count([('project_id', '=', project.id)]),
                        '夾具：開案要自動建標準資料夾')
        for model, path in _project_paths(self.env).items():
            if model != 'supervision.folder':
                self.assertFalse(self.env[model].sudo().with_context(active_test=False).search_count(
                    [(path, '=', project.id)]), f'夾具：除了資料夾不要有別的單據（{model}）')
        return project

    def _assert_move_allowed(self, project):
        self._env_two()['project.project'].browse(project.id).write({'company_id': self.co_iso_b.id})
        self.env.invalidate_all()
        self.assertEqual(project.sudo().company_id, self.co_iso_b)

    def test_company_move_allowed_when_project_has_only_empty_folders_or_members(self):
        """1b 放寬（2026-11-13 使用者決定）：開案時系統自己產生的東西不算單據——空的標準資料夾、工程成員名單
        （前台開案會把建立者加成成員）。同屬 A＋B 的工程後台使用者改這種工程的公司 → 成功。
        三格各隔離一個條件：只有空資料夾、只有成員名單、兩者都有（前台開案的實際樣子）。"""
        member_vals = {'user_id': self.sa_ab.id}
        with self.subTest(case='只有空的標準資料夾'):
            self._assert_move_allowed(self._project_with_auto_folders('S4M-FOLDER'))
        with self.subTest(case='只有工程成員名單'):
            project = self._fresh_project('S4M-MEMBER')
            self.env['supervision.project.member'].sudo().create(dict(member_vals, project_id=project.id))
            self._assert_move_allowed(project)
        with self.subTest(case='空資料夾＋成員名單'):
            project = self._project_with_auto_folders('S4M-BOTH')
            self.env['supervision.project.member'].sudo().create(dict(member_vals, project_id=project.id))
            self._assert_move_allowed(project)

    def test_company_move_refused_when_folder_has_file_or_s4_document(self):
        """放寬只到「空的」為止：資料夾裡有任何一個檔就算單據 → 被拒；S4 加進表的真單據（這裡用送審）也照舊被拒。
        工程都照一般方式開（有整套空資料夾），所以擋下來的原因就是那個檔／那張單，不是資料夾本身。"""
        with self.subTest(case='資料夾裡有檔案'):
            project = self._project_with_auto_folders('S4M-FILE')
            folder = self.env['supervision.folder'].sudo().search([('project_id', '=', project.id)], limit=1)
            self.env['ir.attachment'].sudo().create({'name': 's4m_file.txt', 'raw': b's4m', 'folder_id': folder.id})
            self._assert_move_refused(self._env_two(), project, self.co_iso_b)
            self.env.invalidate_all()
            self.assertEqual(project.sudo().company_id, self.co_iso_a)
        with self.subTest(case='有一張送審'):
            project = self._project_with_auto_folders('S4M-REVIEW')
            self.env['supervision.review.application'].sudo().create({'name': 'S4M 送審', 'project_id': project.id})
            self._assert_move_refused(self._env_two(), project, self.co_iso_b)
            self.env.invalidate_all()
            self.assertEqual(project.sudo().company_id, self.co_iso_a)

    def test_company_move_refused_when_project_has_off_table_data(self):
        """S4 收尾審查 F1（2026-11-13 使用者決定「任何資料都算」）：寫後檢查表以外、直接掛在工程底下的資料也算單據。
        里程碑（核心）、契約材料都不在表上，可見範圍卻跟著工程公司走——沒擋時只屬 A 的同事搬完就看不到。"""
        cases = (('project.milestone', 'S4M-MILE', {'name': 'S4M 里程碑'}),
                 ('construction.contract.material', 'S4M-MATL', {'name': 'S4M 契約材料'}))
        for model, code, vals in cases:
            with self.subTest(model=model):
                self.assertNotIn(model, COMPANY_RULE_FIELDS, '前提：這個模型不在寫後檢查表上')
                project = self._project_with_auto_folders(code)
                self.env[model].sudo().create(dict(vals, project_id=project.id))
                self._assert_move_refused(self._env_two(), project, self.co_iso_b)
                self.env.invalidate_all()
                self.assertEqual(project.sudo().company_id, self.co_iso_a)

    def test_company_move_counts_every_model_linked_to_project(self):
        """「任何資料都算」不另寫清單：表外的模型由 _project_link_fields() 從 registry 掃。這裡用另一個來源（ir.model.fields）
        獨立算一次「有 stored many2one 指向工程的實體模型」：表上的＋掃到的要剛好蓋住它（少一個＝那種資料不算、工程搬得走）。"""
        self.env.cr.execute(
            "SELECT DISTINCT f.model FROM ir_model_fields f JOIN ir_model m ON m.id = f.model_id "
            "WHERE f.ttype = 'many2one' AND f.relation = 'project.project' AND f.store AND NOT m.transient")
        expected = {model for (model,) in self.env.cr.fetchall()
                    if model in self.env and self.env[model]._auto and not self.env[model]._abstract
                    and model != 'project.project'}
        self.assertTrue(expected, '上游要有東西（空集合會恆真）')
        links = _project_link_fields(self.env)
        self.assertFalse(set(links) & set(COMPANY_RULE_FIELDS), '表上的模型已由 _project_paths 涵蓋，不重複掃')
        self.assertEqual(set(links) | (set(COMPANY_RULE_FIELDS) & expected), expected)
        for model in ('project.milestone', 'construction.contract.material'):
            self.assertIn(model, links, f'{model} 要掃得到')

    def test_company_move_allowed_for_system_admin_and_sudo(self):
        """系統管理者、代操作員、sudo 改有單據的工程的公司 → 成功，單據跟著工程走。"""
        for mode, code in (('系統管理者', 'S3M-OK-SYS'), ('代操作員', 'S3M-OK-OP'), ('sudo', 'S3M-OK-SU')):
            with self.subTest(mode=mode):
                project, estimate = self._fresh_project_with_estimate(code)
                if mode == 'sudo':
                    records = self._env_two()['project.project'].browse(project.id).sudo()
                elif mode == '代操作員':
                    records = self._env_two(self._operator_ab())['project.project'].browse(project.id)
                else:
                    records = self._env_two(self._sys_admin_ab())['project.project'].browse(project.id)
                records.write({'company_id': self.co_iso_b.id})
                self.env.invalidate_all()
                self.assertEqual(project.sudo().company_id, self.co_iso_b)
                self.assertEqual(estimate.sudo().project_id.company_id, self.co_iso_b, '估驗跟著工程走')

    def test_company_move_same_value_not_checked(self):
        """改成同一家公司（值沒變）→ 不擋，連有單據的工程也一樣。"""
        project, _estimate = self._fresh_project_with_estimate('S3M-SAME')
        self._env_two()['project.project'].browse(project.id).write({'company_id': self.co_iso_a.id})
        project.invalidate_recordset()
        self.assertEqual(project.sudo().company_id, self.co_iso_a)

    def test_company_move_batch_checks_each_project(self):
        """批次 write 逐個工程查：
        * [沒單據的 A 工程, 有估驗、本來就在 B 的工程] → 改成 B：後者值沒變不查 → 成功；
        * [沒單據的 A 工程, 有估驗的 A 工程] → 改成 B：被拒、訊息只點名有單據的那個、兩個都沒變（寫入前就拒）。"""
        env = self._env_two()
        empty = self._fresh_project('S3M-B0')
        in_b, _estimate_b = self._fresh_project_with_estimate('S3M-BB', self.co_iso_b)
        env['project.project'].browse((empty | in_b).ids).write({'company_id': self.co_iso_b.id})
        self.env.invalidate_all()
        self.assertEqual((empty.sudo().company_id, in_b.sudo().company_id), (self.co_iso_b, self.co_iso_b))
        empty2 = self._fresh_project('S3M-B1')
        with_doc, _estimate = self._fresh_project_with_estimate('S3M-B2')
        message = self._assert_move_refused(env, empty2 | with_doc, self.co_iso_b)
        self.assertIn('S3M-B2', message, '訊息要點名有單據的工程')
        self.assertNotIn('S3M-B1', message, '沒單據的工程不該被點名')
        self.env.invalidate_all()
        self.assertEqual((empty2.sudo().company_id, with_doc.sudo().company_id), (self.co_iso_a, self.co_iso_a),
                         '被拒時批次裡的工程都不可以變')

    def test_company_move_archived_task_version_counts(self):
        """封存的契約工項（S4 起工項本身也在表上）與它底下的工項版本都算單據 → 被拒。"""
        project = self._fresh_project('S3M-ARC')
        task = self.env['project.task'].create({
            'name': 'S3M 封存工項', 'project_id': project.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': 100.0})
        self.assertTrue(self.env['project.task.version'].search_count([('task_id', '=', task.id)]),
                        '夾具：有數量的工項會自動建 v1 版本')
        task.write({'active': False})
        self._assert_move_refused(self._env_two(), project, self.co_iso_b)

    def test_company_move_paths_reach_fixture_records(self):
        """「單據」＝寫後檢查表上的模型（不另寫清單）；每個模型連到工程的路徑由表推出來。
        這裡驗：一個模型一條路徑（上游說幾個就要幾個，M-C），而且每條路徑以 sudo 搜，搜到的正好包含夾具記在 iso_meta
        掛在 A 工程的那幾筆、不含掛在 B 工程的（期望值來自夾具，不來自實作，L3）。"""
        paths = _project_paths(self.env)
        self.assertEqual(set(paths), set(COMPANY_RULE_FIELDS),
                         '表上每個模型都要推得出路徑（本模組依賴那五個模組；S4 的人機料、送審模組 dev 有裝）')
        for model, path in sorted(paths.items()):
            with self.subTest(model=model, path=path):
                project_a = self._iso_project(model, self.p_iso_a)
                project_b = self._iso_project(model, self.p_iso_b)
                own = {rid for rid, project in self.iso_meta[model].items() if project == project_a}
                other = {rid for rid, project in self.iso_meta[model].items() if project == project_b}
                self.assertTrue(own and other, f'{model}：夾具兩個工程都要有紀錄（否則恆真）')
                found = set(self.env[model].sudo().with_context(active_test=False).search([(path, '=', project_a.id)]).ids)
                self.assertTrue(own <= found, f'{model}：{path} 少了 {sorted(own - found)}')
                self.assertFalse(other & found, f'{model}：{path} 搜到 B 工程的 {sorted(other & found)}')

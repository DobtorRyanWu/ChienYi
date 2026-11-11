# -*- coding: utf-8 -*-
"""營造方與控台讀取帳號的讀取範圍與拒寫（合約 §0b-1、§3.2–§3.4）。

單一程式點：覆寫 ir.rule._compute_domain，白名單、預設拒絕。

* 其他使用者（監造方、一般前台、管理者、超級使用者）：**直接回傳核心的值**，與原本完全相同。
* 營造方（res.users._dash_is_contractor_side()）：
  - 讀：營造廠層級 AND 營造條件；工程層級 AND 工程條件；自主檢查樣板 AND 樣板條件；個資收窄 AND 收窄條件；
        框架照舊原樣；其他 → 拒（[('id', '=', 0)]）。範圍不合格（範圍公司空白或不是營造廠、
        營造廠主管未啟用兩步驟驗證）→ 框架以外只剩本人的使用者與聯絡人（合約 §0b-16），其餘全拒。
  - 寫、建、刪：只放「框架的使用者自有狀態模型」，其他全拒。
  - 受邀協作（dobtor 線上文件，合約 §0b-29）：範圍合格時讀得到協作者含自己的那幾份（前台帳號也寫得到）；建、刪照拒；
    dobtor 範本照核心值讀（受邀文件開檔要用）。
* 控台讀取（group_console_reader）：讀只放框架照舊＋本人的使用者與聯絡人（合約 §0b-28）；寫建刪同上。同時是營造方時以控台讀取為準（較嚴）。
* 後台角色帳號（S1，2026-11-10；res.users._is_role_account()）：營造方角色帳號帶營造方標記，kind 照舊是 'contractor'；
  其餘角色帳號（監造方，以及組合不合法的）kind＝'supervision_role'。**有任何角色群組就絕不會是 None**——
  組合不合法、範圍不合格、沒開 TOTP 只會讓 _dash_scope_ok() 為 False（框架以外只剩本人）。
  讀取：工程條件 _dash_project_condition（營造方＝營造廠含範圍公司；監造方＝工程公司在監造公司內；主管再 AND
  參與成員、工程本身另排除未開始／終止；老闆不加狀態條件）；另外多看四類（ROLE_PROJECT_LEVEL、ROLE_ESTIMATE_CHILD、
  ROLE_COST_ANALYSIS）；多營造廠共用的工程，即時損益、損益支出、成本分析不給營造方看。寫建刪照舊全拒。
* 判定一律用 env.user（sudo 也不跳過；sudo 本來就不走規則，核心各檢查點在 env.su 時不呼叫本方法的結果）。
* 暫存模型（wizard）：只讀得到自己建的；建、寫、刪只放帳號自助白名單 SELF_SERVICE_TRANSIENT（合約 §0b-24）。
  11-06 抗辯實打：精靈的 related／compute 欄位以 sudo 計算（核心預設），呼叫端把範圍外 id 填進精靈就讀得到
  別家的契約金額、估驗單價；精靈的動作方法也常以 sudo 寫業務資料（資料夾上傳精靈改掛附件）——
  「wizard 不存業務資料、動作寫業務模型仍會被擋」的前提不成立，所以把建立精靈的能力拿掉。抽象模型照舊（沒有資料表）。
* 框架照舊類裡再收窄四件事（合約 §0b-24、§0b-25；兩種受限帳號都適用，見 _dash_framework_extra）：
  公開頻道（channel_type='channel'）與其成員讀不到也改不了、內部備註讀不到、共用篩選只能建寫刪自己的。

「核心的值」：_inherits 父模型（例 project.project → mail.alias）的規則也用核心值，
不套本覆寫——否則父模型落在「其他」類被拒，會連帶把子模型整個拒掉。
做法是帶一個 context 旗標呼叫 super，並把旗標加進快取鍵（_compute_domain_keys）。
旗標的值是本模組自己的物件、以 is 比對：RPC／前台送來的 context 只能是 JSON／XML-RPC 值，
永遠等不到這個物件——若用真假值判定，任何人在 context 帶上這個鍵就跳過整個範圍規則
（2026-11-06 實測：營造廠主管帶 {dash_scope_core_parent: True} 讀到全庫估驗 113 筆，正常 58 筆）。
"""
from odoo import api, fields, models, tools
from odoo.exceptions import AccessError
from odoo.osv import expression
from odoo.tools import config

from odoo.addons.construction_supervision_base.models.res_users import ROLE_LEVEL_BOSS, ROLE_LEVEL_MANAGER

# 本規則拒絕時回傳的條件（合約 §3.2 字面）
DENY_DOMAIN = (('id', '=', 0),)

# 呼叫核心時的 context 旗標：遞迴進 _inherits 父模型時直接用核心值。
# 只認 CORE_PARENT_TOKEN 這個物件本身（見檔頭）；外部送來的任何值都不算。
CORE_PARENT_CTX = 'dash_scope_core_parent'


class _CoreParentToken:
    """本模組內部呼叫核心規則的憑證（不可序列化成 RPC 值，外部偽造不了）。"""
    __slots__ = ()

    def __repr__(self):
        return '<dash_scope_core_parent token>'


CORE_PARENT_TOKEN = _CoreParentToken()

# 營造廠層級：模型 → 所屬工程欄位（本模型上的路徑）。
# 條件＝contractor_company_id 是我的範圍公司 且 所屬工程的營造廠含我的範圍公司（合約 §3.2）。
# 欄位逐一讀模型確認：日誌的 project_id 是 related（supervision_project_id），預約式缺失／自主檢查的
# project_id 是 stored related（slip_id.project_id），其餘是一般 Many2one。
CONTRACTOR_LEVEL = {
    'daily.log.sheet': 'supervision_project_id',
    'supervision.photo': 'project_id',
    'general.defect.improvement': 'project_id',
    'reservation.defect.improvement': 'project_id',
    'supervision.test.record': 'project_id',
    'general.self.inspection': 'project_id',
    'reservation.self.inspection': 'project_id',
    'payment.estimate': 'project_id',
}

# 營造廠層級的明細：不加欄位、走父單路徑（合約 §3.2、§3.5）。模型 → (父單欄位, 父單模型)
# 子表看得到 ⇔ 父單看得到，不會比父單寬。前台營造帳號有這些子表的讀取 ACL、會以本人身分
# 讀到（例：自主檢查列表的檢查項目數、日誌表單的材料累計），不列進來會被當「其他」靜默讀成空的
# （線 A2，合約 §3.6；父單欄位逐一讀模型確認）。
CONTRACTOR_LEVEL_LINES = {
    'daily.log.line': ('sheet_id', 'daily.log.sheet'),
    'payment.estimate.line': ('estimate_id', 'payment.estimate'),
    'daily.log.material': ('daily_log_id', 'daily.log.sheet'),
    'daily.log.weather': ('sheet_id', 'daily.log.sheet'),
    'daily.log.specific.item': ('daily_log_id', 'daily.log.sheet'),
    'daily.log.man.machine.detail': ('daily_log_id', 'daily.log.sheet'),
    'general.self.inspection.item': ('inspection_id', 'general.self.inspection'),
    'general.self.inspection.measure.line': ('inspection_id', 'general.self.inspection'),
    'reservation.self.inspection.item': ('inspection_id', 'reservation.self.inspection'),
    'reservation.self.inspection.measure.line': ('inspection_id', 'reservation.self.inspection'),
    'payment.estimate.extra.line': ('estimate_id', 'payment.estimate'),
}

# 工程層級：模型 → 所屬工程欄位路徑（None＝本身就是工程）。
# 條件＝所屬工程的營造廠含我的範圍公司（合約 §3.2；§13-2 契約工項、通報單歸這類）。
PROJECT_LEVEL = {
    'project.project': None,
    'project.task': 'project_id',
    'progress.schedule': 'project_id',
    'progress.schedule.line': 'schedule_id.project_id',
    'construction.weekly.schedule': 'supervision_project_id',
    'construction.weekly.schedule.line': 'schedule_id.supervision_project_id',
    'supervision.test.task.statistics': 'project_id',
    'reservation.notification.slip': 'project_id',
    'reservation.notification.slip.line': 'slip_id.project_id',
    'reservation.notification.slip.suspension': 'slip_id.project_id',
    # 合約 §0b-6：都掛在工程底下，營造廠是契約當事人、前台本來就給成員看
    'supervision.folder': 'project_id',
    'supervision.test.standard': 'project_id',
    'contract.change.order': 'project_id',
    # 合約 §0b-10：前台工程文件（附件掛在文件上，來源單據讀不到就下載不到）
    'supervision.document': 'project_id',
    # 合約 §0b-20：檢試驗預警（單一工程頁「檢試驗」區塊以本人身分數未處理預警；歸「其他」時整塊無權限）
    'supervision.test.warning': 'project_id',
}

# 自主檢查樣板（線 G；真瀏覽器實證：營造方前台老闆開有草稿自主檢查的工程首頁，模板以本人身分讀
# `inspection_type_id.name` → 403）。樣板不是營造廠的資料，看得到的是：全域樣板（project_id 空白）、
# 可見工程的樣板（樣板所屬工程的營造廠含範圍公司）、可見工程的自主檢查用到的樣板（檢查的 inspection_type_id
# 沒限制工程，樣板也可能被改到別的工程，只看樣板的 project_id 會漏）。別的工程專屬的樣板看不到。
# 樣板的明細（項目、段落、檢查時機、量測區塊）跟著樣板。模型 → 到樣板的路徑前綴（欄位逐一讀模型確認：
# construction_quality/models/self_inspection_type.py、self_inspection_measure.py 的 type_id）。
INSPECTION_TEMPLATE_LEVEL = {
    'self.inspection.type': '',
    'self.inspection.type.item': 'type_id.',
    'self.inspection.type.stage': 'type_id.',
    'self.inspection.type.timing': 'type_id.',
    'self.inspection.type.measure': 'type_id.',
}

# 個資收窄（依公司）：只看 company_id 是我的範圍公司的。
# hr.employee：沒有 HR 群組的帳號讀它時，核心改查 hr.employee.public（hr_employee.py _search），
# 兩者要同一個條件，否則 search_count 會從 public 漏出來。
NARROW_BY_COMPANY = frozenset({
    'hr.employee.public',
    'hr.employee',
    'hr.department',
    'resource.resource',
})
# 個資收窄（聯絡人、使用者）：自己＋自己範圍公司（合約 §13-3；細節見 _dash_scope_read_domain）
NARROW_USERS = 'res.users'
NARROW_PARTNERS = 'res.partner'
# 範圍不合格（範圍公司空白或不是營造廠、營造廠主管未啟用兩步驟驗證）時仍讀得到的「本人」資料（合約 §0b-16）：
# 只有自己的使用者與聯絡人。登入（核心第一次登入以本人身分讀 tz：odoo/addons/base/models/res_users.py
# _login 的 `not user.tz or not user.login_date`）、頭像選單、偏好設定、啟用兩步驟驗證都以本人身分讀它們；
# 拒掉就連登入都 403，「請啟用兩步驟驗證」的提示永遠看不到（線 C、D 真瀏覽器實測）。
SELF_ONLY_WHEN_BLOCKED = frozenset({NARROW_USERS, NARROW_PARTNERS})

# 受邀協作（合約 §0b-29，使用者 11-06 決定「營造方可讀寫受邀文件」）：dobtor 線上文件的原設計是
# 營造廠／業主代表以協作者身分跨公司讀寫「受邀的文件」（dobtor_doc_editor/security/doc_security.xml
# rule_doc_document_portal 與其 lock-in 測試）。營造方（範圍合格）只讀、寫得到協作者含自己的文件，
# 建、刪照拒；條件與核心值取且（核心另有群組規則與 ACL：營造廠主管沒有 dobtor 群組，ACL 就擋掉）。
# 範圍不合格的營造方與控台讀取帳號照拒（合約 §1-7）。誰能被加為協作者由監造方決定：
# collaborator_ids 是前台帳號寫不動的欄位（dobtor_doc_editor PORTAL_PROTECTED_FIELDS）。
# **寫只給前台帳號（share）**：dobtor 擋「前台寫不動的欄位」只看 share（doc_document.py write），
# 主要公司是營造廠的內部帳號（§0b-5）若帶 dobtor 編輯者群組，寫得動協作者、別名運算式、綁定對象——
# 11-06 第二輪抗辯 skeptic B F2／red-team B 實測。使用者決定的是「前台營造廠帳號可被邀請讀寫」，內部營造方只讀。
# 模型 → 協作者欄位
INVITED_COLLAB = {
    'doc.document': 'collaborator_ids',
}
# 受邀文件開得起來要讀的範本資料（編輯器開檔 /dobtor_doc/load 讀 template_id.field_aliases、name；
# /dobtor_doc/template_fields/* 讀欄位、簽核人、選項）。dobtor 對範本沒有任何規則、前台群組只有讀取 ACL，
# 18.0 的前台協作者本來就讀得到全部範本（空白表單設計，不是工程資料）；範圍合格的營造方照核心值讀，寫照拒。
# 11-06 第二輪抗辯 skeptic B F1：沒有這一條，營造方打不開任何帶範本的受邀文件（自動建立的文件全都帶範本）。
INVITED_COLLAB_SUPPORT_READ = frozenset({
    'doc.template',
    'doc.template.field',
    'doc.template.field.option',
    'doc.template.signer',
})

# 框架照舊：web 介面要用的，讀取不加條件（照核心原本的規則與各模型自己的存取檢查）。
# 只列「後台／前台介面會以使用者身分讀」且「本身有自己的範圍規則或不含業務資料」的模型。
FRAMEWORK_READ = frozenset({
    # 介面骨架與設定
    'ir.ui.menu', 'ir.ui.view', 'ir.model', 'ir.actions.report', 'report.paperformat',
    'ir.filters', 'ir.embedded.actions',
    # 附件、訊息：核心依來源單據的存取權判定（ir_attachment.py check、mail_message.py _search）
    'ir.attachment', 'mail.message', 'mail.notification',
    'discuss.channel', 'discuss.channel.member',
    'bus.bus', 'bus.presence',
    # 參照資料
    'res.lang', 'res.currency', 'res.currency.rate', 'res.country', 'res.country.state',
    'res.company', 'uom.uom', 'uom.category',
    # 使用者自己的設定與裝置、金鑰、兩步驟驗證（核心規則限本人）
    'res.users.settings', 'res.users.settings.volumes',
    'res.users.apikeys', 'res.device', 'res.device.log', 'auth_totp.device',
})

# 框架的使用者自有狀態模型：核心以使用者身分寫這些（上線狀態、對話、已讀、篩選），
# 寫建刪照核心原本的規則（合約 §3.3；odoo/addons/bus/models/ir_websocket.py:124-130、
# bus_presence.py:93-104）。其餘一律拒寫。
USER_OWNED_STATE = frozenset({
    'bus.presence',
    'discuss.channel',
    'discuss.channel.member',
    'mail.message',
    'mail.notification',
    'res.users.settings',
    'res.users.settings.volumes',
    'ir.filters',
})

# 受限帳號仍可建立／修改的暫存模型：帳號自助（合約 §0b-24；登入、偏好設定、啟用兩步驟驗證要用）。
# 其餘精靈一律拒建拒寫。前台的照片下載精靈（supervision.photo.download.wizard／.preview，前台閱覽者群組有 ACL）
# 不放：construction_portal/controllers 沒有任何路由建它們（只在後台表單使用），前台帳號又進不了後台。
SELF_SERVICE_TRANSIENT = frozenset({
    'auth_totp.wizard',                 # 我的偏好 →「啟用兩步驟驗證」（auth_totp action_totp_enable_wizard）
    'res.users.identitycheck',          # 改敏感設定前的密碼確認（核心 @check_identity：啟用 TOTP、新增金鑰）
    'res.users.apikeys.description',    # 我的偏好 →「新增 API 金鑰」（控台讀取帳號要在這裡建金鑰）
    'change.password.own',              # 我的偏好 →「變更密碼」
})

# 框架照舊類的收窄（模型 → 讀取條件／寫建刪條件；條件與核心值取且）。
# 公開頻道：千溢／監造方內部在用（#general 等），使用者 11-06 決定營造方與控台讀取帳號看不到、也改不了（§0b-25）；
#   私訊（chat）與群組對話（group）照舊。成員紀錄跟著頻道走（否則讀得到公開頻道的成員名單）。
# 內部備註（記錄備註）：Odoo 18 的「記錄備註」是 message_type='comment'＋內部子類型（mail.mt_note，internal=True），
#   回覆內部備註的郵件帶 is_internal（mail/models/mail_thread.py:1822-1826）。追蹤紀錄與系統通知
#   （_message_log／message_notify：message_type 'notification'／'user_notification'，也帶 is_internal）照舊看得到。
# 共用篩選：核心規則准內部帳號建寫刪「全體」篩選（user_id 空白，ir_filters_employee_rule），會套到監造方的清單上；
#   受限帳號只准動自己的。
# 內部備註的附件（fix1-B，審查 red-team F2 high）：核心只依「附件掛的單據」判斷讀取權，內部備註讀不到、它的附件卻讀得到
#   （search、read raw/datas、/web/content、chatter 附件欄都是）。受限的內部帳號只看得到：二進位欄位附件（res_field）、
#   沒有任何訊息引用的附件（單據本身的附件），或至少被一則「不是內部備註」的訊息引用（同一份 NOT_INTERNAL_NOTE 判準）。
#   前台帳號（share）不套：核心對非內部帳號的附件讀取本來就另外擋（ir_attachment check）。
CHANNEL_TYPE_PUBLIC = 'channel'
INTERNAL_NOTE_KEPT_TYPES = ('notification', 'user_notification')
NOT_PUBLIC_CHANNEL = (('channel_type', '!=', CHANNEL_TYPE_PUBLIC),)
NOT_PUBLIC_CHANNEL_MEMBER = (('channel_id.channel_type', '!=', CHANNEL_TYPE_PUBLIC),)
# 不是內部備註：追蹤／系統通知類型，或（不帶 is_internal 且子類型不是內部的）
NOT_INTERNAL_NOTE = (
    '|', ('message_type', 'in', INTERNAL_NOTE_KEPT_TYPES),
    '&', ('is_internal', '=', False), '|', ('subtype_id', '=', False), ('subtype_id.internal', '=', False),
)

# ── 後台角色帳號（S1）才讀得到的四類（前台營造帳號、營造廠主管、控台讀取照舊落在「其他」＝拒）──────────
# 工程層級：模型 → 到工程的欄位路徑（欄位逐一讀模型確認：construction_contract_change/models/contract_change_order_line.py
# change_order_id；construction_general/models/general_progress_report.py report_id、general_realtime_profit.py profit_id）
ROLE_PROJECT_LEVEL = {
    'contract.change.order.line': 'change_order_id.project_id',
    'general.progress.report': 'project_id',
    'general.progress.report.line': 'report_id.project_id',
    'general.realtime.profit': 'project_id',
    'general.realtime.profit.cost': 'profit_id.project_id',
}
# 營造方只看「只有一家營造廠（就是自己）」的工程的那幾個（預設決定：多營造廠共用的工程，損益與成本不給營造方看）
ROLE_SINGLE_CONTRACTOR_ONLY = frozenset({'general.realtime.profit', 'general.realtime.profit.cost'})
# 估驗的子資料：模型 → (到估驗的欄位, 到工程的欄位)。營造方再經由估驗的營造廠歸屬篩選（＋只有一家營造廠）
ROLE_ESTIMATE_CHILD = {
    'profit.loss.entry': ('estimate_id', 'project_id'),
}
# 成本分析（construction_cost_analysis，選裝）：模型 → (到來源工程的欄位路徑, 到公司的欄位路徑)。
# 營造方：要有來源工程、在範圍內、只有一家營造廠；監造老闆另外看得到沒有工程的（限監造公司）；監造主管只看範圍內的
ROLE_COST_ANALYSIS = {
    'cost.analysis': ('source_project_id', 'company_id'),
    'cost.analysis.line': ('planning_id.source_project_id', 'planning_id.company_id'),
}

# _dash_scope_kind() 的值
KIND_CONSOLE = 'console'
KIND_CONTRACTOR = 'contractor'
KIND_SUPERVISION_ROLE = 'supervision_role'
# 主管看不到的工程狀態（與前台成員規則相同：construction_supervision_base portal 規則 state not in draft/terminated）
MANAGER_EXCLUDED_PROJECT_STATES = ('draft', 'terminated')

# 附件 → 引用它的訊息（restricted_mail.py 在 ir.attachment 上加的反向欄位，同一張 message_attachment_rel）
ATTACHMENT_MESSAGES_FIELD = 'dash_message_ids'
NOT_ONLY_ON_INTERNAL_NOTES = (
    '|', '|',
    ('res_field', '!=', False),
    (ATTACHMENT_MESSAGES_FIELD, '=', False),
    (ATTACHMENT_MESSAGES_FIELD, 'any', list(NOT_INTERNAL_NOTE)),
)

# 拒絕時附在 AccessError 訊息後的說明（使用者看得到為什麼被擋）
DENY_NOTE_CONTRACTOR = '公司儀表板範圍規則：營造方帳號只讀得到自己範圍公司的資料，且不能寫、建、刪業務資料。'
DENY_NOTE_CONSOLE = '公司儀表板範圍規則：控台讀取帳號只能呼叫控台取資料方法，不能直接讀寫業務資料。'
DENY_NOTE_ROLE = '公司儀表板範圍規則：後台角色帳號只讀得到自己工程的資料，不能寫、建、刪。'


class IrRule(models.Model):
    _inherit = 'ir.rule'

    def _compute_domain_keys(self):
        # 旗標進快取鍵：帶旗標（核心值）與不帶旗標（本覆寫的值）分開快取
        return super()._compute_domain_keys() + [CORE_PARENT_CTX]

    def _compute_domain_context_values(self):
        # 快取鍵只放「是不是本模組的憑證」：呼叫端送來的任意值（dict 不可雜湊、各種真值）不進快取鍵，
        # 否則 dict 會讓快取查詢報錯、各種值各佔一格快取
        for key, value in zip(self._compute_domain_keys(), super()._compute_domain_context_values()):
            yield (value is CORE_PARENT_TOKEN) if key == CORE_PARENT_CTX else value

    @api.model
    def _dash_scope_kind(self):
        """'console'／'contractor'／'supervision_role'／None（不受本規則影響）。判定用 env.user，不因 env.su 跳過。"""
        return self._dash_kind_of(self.env.user)

    @api.model
    def _dash_kind_of(self, user):
        """某帳號的 kind：不是受限帳號（res.users._dash_is_restricted()，全系統唯一一份）回 None；
        受限帳號依序是控台讀取、營造方（含營造方角色帳號）、其餘＝監造方角色帳號（含組合不合法的，絕不回 None）。"""
        if not user or not user._dash_is_restricted():
            return None
        if user._dash_is_console_reader():
            return KIND_CONSOLE
        if user._dash_is_contractor_side():
            return KIND_CONTRACTOR
        return KIND_SUPERVISION_ROLE

    @api.model
    @tools.conditional(
        'xml' not in config['dev_mode'],
        tools.ormcache('self.env.uid', 'self.env.su', 'model_name', 'mode',
                       'tuple(self._compute_domain_context_values())'),
    )
    def _compute_domain(self, model_name, mode="read"):
        if self.env.context.get(CORE_PARENT_CTX) is CORE_PARENT_TOKEN:
            return super()._compute_domain(model_name, mode)
        kind = self._dash_scope_kind()
        if not kind:
            # 監造方與其他使用者：與原本完全相同
            return super()._compute_domain(model_name, mode)
        model = self.env[model_name]
        if model._abstract:
            return super()._compute_domain(model_name, mode)
        if model._transient:
            # 精靈：只看得到、改得到自己建的（Odoo 18 核心不限建立者：別人建的精靈以 id 就讀得到，related 欄位
            # 又是 sudo 算的）；建寫刪只放帳號自助白名單（見 SELF_SERVICE_TRANSIENT）
            if mode != 'read' and model_name not in SELF_SERVICE_TRANSIENT:
                return list(DENY_DOMAIN)
            return self._dash_and(super()._compute_domain(model_name, mode), [('create_uid', '=', self.env.user.id)])

        core = super(IrRule, self.with_context(**{CORE_PARENT_CTX: CORE_PARENT_TOKEN}))._compute_domain(model_name, mode)
        user = self.env.user
        if mode != 'read':
            if (mode == 'write' and kind == KIND_CONTRACTOR and model_name in INVITED_COLLAB
                    and user.share and user._dash_scope_ok()):
                # 受邀協作：前台帳號只寫得到受邀的那幾份（建、刪照拒；內部營造方只讀，見 INVITED_COLLAB）
                return self._dash_and(core, self._dash_invited_domain(model_name, user))
            if model_name not in USER_OWNED_STATE:
                return list(DENY_DOMAIN)
            return self._dash_and(core, self._dash_framework_extra(model_name, mode, user))
        if model_name in FRAMEWORK_READ:
            return self._dash_and(core, self._dash_framework_extra(model_name, mode, user))
        if kind == KIND_CONSOLE or not user._dash_scope_ok():
            # 控台讀取帳號、範圍不合格的營造方：框架以外只剩本人的使用者與聯絡人（合約 §0b-16；
            # 控台讀取帳號同理——登入、啟用兩步驟驗證、建 API key 都以本人身分讀自己，11-06 整合測試實測）
            if model_name not in SELF_ONLY_WHEN_BLOCKED:
                return list(DENY_DOMAIN)
            extra = self._dash_self_domain(model_name, user)
            return expression.AND([core, extra]) if core else extra
        extra = self._dash_scope_read_domain(model_name, user, kind=kind)
        if extra is None:
            return list(DENY_DOMAIN)
        return expression.AND([core, extra]) if core else extra

    @api.model
    def _dash_and(self, core, extra):
        """核心值 AND 本模組條件；沒有額外條件回核心值本身（[] 也照回，＝核心不限制）。"""
        if not extra:
            return core
        return expression.AND([core, extra]) if core else list(extra)

    @api.model
    def _dash_framework_extra(self, model_name, mode, user):
        """框架照舊／使用者自有狀態模型對受限帳號的收窄條件（見 NOT_PUBLIC_CHANNEL 等常數）；沒有回 None。"""
        if model_name == 'discuss.channel':
            return list(NOT_PUBLIC_CHANNEL)
        if model_name == 'discuss.channel.member':
            return list(NOT_PUBLIC_CHANNEL_MEMBER)
        if model_name == 'mail.message' and mode == 'read':
            return list(NOT_INTERNAL_NOTE)
        if model_name == 'ir.attachment' and mode == 'read' and user._dash_is_restricted_internal():
            return list(NOT_ONLY_ON_INTERNAL_NOTES)
        if model_name == 'ir.filters' and mode != 'read':
            return [('user_id', '=', user.id)]
        return None

    @api.model
    def _dash_scope_read_domain(self, model_name, user, kind=None):
        """受限帳號（範圍已確認合格）對白名單模型的讀取條件；不在白名單回 None（＝拒）。

        kind 沒給時依 user 算。監造方角色帳號走 _dash_supervision_role_read_domain；營造方（含營造方角色帳號）在這裡：
        不是角色帳號的（前台營造帳號、營造廠主管）產生的條件與 S1 之前逐字相同（_dash_project_condition 對它們不加任何東西）。
        """
        kind = kind or self._dash_kind_of(user)
        if kind == KIND_SUPERVISION_ROLE:
            return self._dash_supervision_role_read_domain(model_name, user)
        scope = user.sudo().dash_scope_company_id
        scope_id = scope.id
        role = user._is_role_account()
        if model_name in CONTRACTOR_LEVEL:
            return self._dash_contractor_condition('', CONTRACTOR_LEVEL[model_name], scope_id, user, kind)
        if model_name in CONTRACTOR_LEVEL_LINES:
            parent_field, parent_model = CONTRACTOR_LEVEL_LINES[model_name]
            return self._dash_contractor_condition(
                parent_field + '.', CONTRACTOR_LEVEL[parent_model], scope_id, user, kind)
        if model_name in PROJECT_LEVEL:
            return self._dash_project_condition(self._dash_prefix(PROJECT_LEVEL[model_name]), user, kind)
        if model_name in INSPECTION_TEMPLATE_LEVEL:
            if role:
                # 營造方角色帳號：與監造方同一份（工程條件含主管的成員＋狀態；fix2-R，審查 red-team r2 G3-1）
                return self._dash_role_template_condition(INSPECTION_TEMPLATE_LEVEL[model_name], user, kind)
            return self._dash_inspection_template_condition(INSPECTION_TEMPLATE_LEVEL[model_name], scope_id)
        if model_name in INVITED_COLLAB or model_name in INVITED_COLLAB_SUPPORT_READ:
            if role:
                return None     # 角色帳號暫時沒有線上文件協作（S1 預設決定，之後再補）
            if model_name in INVITED_COLLAB:
                return self._dash_invited_domain(model_name, user)
            return []   # 照核心值（見 INVITED_COLLAB_SUPPORT_READ）
        if role:
            role_domain = self._dash_role_category_domain(model_name, user, kind)
            if role_domain is not None:
                return role_domain
        if model_name in NARROW_BY_COMPANY:
            return [('company_id', '=', scope_id)]
        if model_name == NARROW_USERS:
            # 自己＋同一範圍公司的帳號（看範圍公司欄位，不看使用者自己改得到的 company_id）
            return ['|', ('id', '=', user.id), ('dash_scope_company_id', '=', scope_id)]
        if model_name == NARROW_PARTNERS:
            # 自己的聯絡人＋範圍公司本身與其下聯絡人＋屬於範圍公司的聯絡人＋同範圍帳號的聯絡人
            # （必須涵蓋上面 res.users 條件裡帳號的聯絡人：res.users 以 _inherits 掛在 res.partner 上）
            return [
                '|', '|', '|',
                ('id', '=', user.partner_id.id),
                ('commercial_partner_id', '=', scope.partner_id.id),
                ('company_id', '=', scope_id),
                ('user_ids.dash_scope_company_id', '=', scope_id),
            ]
        return None

    @api.model
    def _dash_supervision_role_read_domain(self, model_name, user):
        """監造方角色帳號（範圍已確認合格）的讀取條件；不在白名單回 None（＝拒）。

        監造公司＝user._role_supervision_company_ids()（允許公司裡不是營造廠的）。看得到所有營造廠的紀錄
        （與前台監造老闆相同）。人員與聯絡人明確限監造公司——**不可**沿用營造方「範圍公司」的公式：範圍公司空白時
        那個公式會變成「公司空白的聯絡人全看得到」（dev 87 筆聯絡人有 83 筆公司空白；抗辯 skeptic high）。
        """
        kind = KIND_SUPERVISION_ROLE
        companies = user._role_supervision_company_ids()
        if model_name in CONTRACTOR_LEVEL:
            return self._dash_project_condition(self._dash_prefix(CONTRACTOR_LEVEL[model_name]), user, kind)
        if model_name in CONTRACTOR_LEVEL_LINES:
            parent_field, parent_model = CONTRACTOR_LEVEL_LINES[model_name]
            return self._dash_project_condition(
                self._dash_prefix(f'{parent_field}.{CONTRACTOR_LEVEL[parent_model]}'), user, kind)
        if model_name in PROJECT_LEVEL:
            return self._dash_project_condition(self._dash_prefix(PROJECT_LEVEL[model_name]), user, kind)
        if model_name in INSPECTION_TEMPLATE_LEVEL:
            return self._dash_role_template_condition(INSPECTION_TEMPLATE_LEVEL[model_name], user, kind)
        role_domain = self._dash_role_category_domain(model_name, user, kind)
        if role_domain is not None:
            return role_domain
        if model_name in NARROW_BY_COMPANY:
            return [('company_id', 'in', companies)]
        if model_name == NARROW_USERS:
            return ['|', ('id', '=', user.id), ('company_ids', 'in', companies)]
        if model_name == NARROW_PARTNERS:
            # 自己的聯絡人＋屬於監造公司的聯絡人＋監造公司本身的聯絡人＋上面 res.users 條件裡帳號的聯絡人
            # （res.users 以 _inherits 掛在 res.partner 上，兩邊要對得起來）
            company_partners = self.env['res.company'].sudo().browse(companies).partner_id.ids
            return [
                '|', '|', '|',
                ('id', '=', user.partner_id.id),
                ('company_id', 'in', companies),
                ('id', 'in', company_partners),
                ('user_ids.company_ids', 'in', companies),
            ]
        # 受邀協作（dobtor）與其範本：角色帳號拒（S1 預設決定）；其他一律拒
        return None

    @api.model
    def _dash_role_template_condition(self, prefix, user, kind):
        """角色帳號（兩方）的自主檢查樣板與明細：全域樣板＋範圍內工程的樣板＋範圍內工程的自主檢查用到的樣板
        （比照營造方的四路 OR；one2many 那兩路用 any，主管的「成員」「狀態」與「公司／營造廠」才會落在同一張檢查的工程上）。"""
        return expression.OR([
            [(f'{prefix}project_id', '=', False)],
            self._dash_project_condition(f'{prefix}project_id.', user, kind),
            [(f'{prefix}dash_general_inspection_ids', 'any',
              self._dash_project_condition('project_id.', user, kind))],
            [(f'{prefix}dash_reservation_inspection_ids', 'any',
              self._dash_project_condition('project_id.', user, kind))],
        ])

    @api.model
    def _dash_role_category_domain(self, model_name, user, kind):
        """角色帳號才有的四類（ROLE_PROJECT_LEVEL／ROLE_ESTIMATE_CHILD／ROLE_COST_ANALYSIS）；不屬於這四類回 None。"""
        contractor = kind == KIND_CONTRACTOR
        scope_id = user.sudo().dash_scope_company_id.id
        if model_name in ROLE_PROJECT_LEVEL:
            prefix = self._dash_prefix(ROLE_PROJECT_LEVEL[model_name])
            domain = self._dash_project_condition(prefix, user, kind)
            if contractor and model_name in ROLE_SINGLE_CONTRACTOR_ONLY:
                domain = domain + self._dash_single_contractor_condition(prefix, scope_id)
            return domain
        if model_name in ROLE_ESTIMATE_CHILD:
            estimate_field, project_field = ROLE_ESTIMATE_CHILD[model_name]
            prefix = f'{project_field}.'
            domain = self._dash_project_condition(prefix, user, kind)
            if contractor:
                domain = ([(f'{estimate_field}.contractor_company_id', '=', scope_id)] + domain
                          + self._dash_single_contractor_condition(prefix, scope_id))
            return domain
        if model_name in ROLE_COST_ANALYSIS:
            project_path, company_path = ROLE_COST_ANALYSIS[model_name]
            prefix = f'{project_path}.'
            in_scope = self._dash_project_condition(prefix, user, kind)
            if contractor:
                return ([(project_path, '!=', False)] + in_scope
                        + self._dash_single_contractor_condition(prefix, scope_id))
            if user._role_level_raw() == ROLE_LEVEL_BOSS:
                # 沒有工程的成本分析只給監造老闆，而且限監造公司的（核心另有公司規則，這裡再明寫一次）
                return expression.OR([
                    [(project_path, '=', False), (company_path, 'in', user._role_supervision_company_ids())],
                    in_scope,
                ])
            return in_scope
        return None

    @api.model
    def _dash_prefix(self, path):
        """欄位路徑 → 條件前綴（'' 表示 project.project 本身，否則加一個點）。"""
        return f'{path}.' if path else ''

    @api.model
    def _dash_project_condition(self, prefix, user, kind):
        """工程條件（prefix＝到工程的路徑加點；'' 表示 project.project 本身）。

        * 營造方：工程的營造廠含範圍公司；監造方角色帳號：工程的公司在監造公司內。
        * 主管（角色帳號層級 manager）：再 AND 參與成員、而且工程不是未開始／終止——工程本身與子資料都套
          （fix1-C；S1 原本只套在工程本身，後台會比手機寬）。老闆不加狀態條件（手機新增的未開始工程要看得到）。
        * 不是角色帳號的營造方（前台營造帳號、營造廠主管）：只有第一條，與 S1 之前的條件逐字相同。
        """
        if kind == KIND_CONTRACTOR:
            domain = [(f'{prefix}contractor_company_ids', 'in', [user.sudo().dash_scope_company_id.id])]
        else:
            domain = [(f'{prefix}company_id', 'in', user._role_supervision_company_ids())]
        if user._role_level_raw() == ROLE_LEVEL_MANAGER:
            domain.append((f'{prefix}member_user_ids', 'in', [user.id]))
            # 未開始、終止的工程：工程本身與底下所有資料一律看不到（與手機前台主管一致；fix1-C 審查 skeptic F2）
            domain.append((f'{prefix}state', 'not in', list(MANAGER_EXCLUDED_PROJECT_STATES)))
        return domain

    @api.model
    def _dash_single_contractor_condition(self, prefix, scope_id):
        """工程的營造廠只有範圍公司一家（多營造廠共用的工程，損益與成本不給營造方看）。

        與工程條件的「營造廠含範圍公司」一起用＝恰好一家；營造廠清單裡有任何別家（含公司類型不是營造廠的髒資料、
        封存的公司）都算多家（拒絕方向）。用 not any 表達，不必另加 stored 欄位。
        子條件明寫 active 才不會被 active_test 自動濾掉封存的公司（核心 _search 只在條件沒提到 active 時才補）。
        """
        return [(f'{prefix}contractor_company_ids', 'not any',
                 [('id', '!=', scope_id), ('active', 'in', [True, False])])]

    @api.model
    def _dash_invited_domain(self, model_name, user):
        """受邀協作（合約 §0b-29）：協作者含自己的那幾筆。"""
        return [(INVITED_COLLAB[model_name], 'in', [user.id])]

    @api.model
    def _dash_self_domain(self, model_name, user):
        """範圍不合格的營造方只讀得到本人（合約 §0b-16）：自己的使用者、自己的聯絡人。"""
        if model_name == NARROW_USERS:
            return [('id', '=', user.id)]
        return [('id', '=', user.partner_id.id)]

    @api.model
    def _dash_inspection_template_condition(self, prefix, scope_id):
        """自主檢查樣板（及其明細）：全域、可見工程的、或可見工程的自主檢查用到的（見 INSPECTION_TEMPLATE_LEVEL）。"""
        visible = [scope_id]
        return [
            '|', '|', '|',
            (f'{prefix}project_id', '=', False),
            (f'{prefix}project_id.contractor_company_ids', 'in', visible),
            (f'{prefix}dash_general_inspection_ids.project_id.contractor_company_ids', 'in', visible),
            (f'{prefix}dash_reservation_inspection_ids.project_id.contractor_company_ids', 'in', visible),
        ]

    @api.model
    def _dash_contractor_condition(self, prefix, project_field, scope_id, user, kind):
        """營造廠層級條件：歸屬是我的範圍公司 且 所屬工程的營造廠仍含我的範圍公司（撤權即失效）。
        營造方主管角色帳號另外 AND 參與成員（_dash_project_condition）；其他營造方與 S1 之前逐字相同。"""
        return ([(f'{prefix}contractor_company_id', '=', scope_id)]
                + self._dash_project_condition(f'{prefix}{project_field}.', user, kind))

    def _make_access_error(self, operation, records):
        # 被本規則擋下時，訊息後面補一句原因（核心訊息找不到對應的規則記錄，看不出為什麼）
        error = super()._make_access_error(operation, records)
        kind = self._dash_scope_kind()
        if not kind:
            return error
        if kind == KIND_CONSOLE:
            note = DENY_NOTE_CONSOLE
        elif self.env.user._is_role_account():
            note = DENY_NOTE_ROLE
        else:
            note = DENY_NOTE_CONTRACTOR
        dash_error = AccessError(f'{error.args[0]}\n\n{note}')
        if getattr(error, 'context', None):
            dash_error.context = error.context
        return dash_error


class SelfInspectionType(models.Model):
    """樣板被哪些自主檢查用到：只給上面的範圍規則用（「可見工程的自主檢查用到的樣板」），畫面不顯示。"""
    _inherit = 'self.inspection.type'

    dash_general_inspection_ids = fields.One2many(
        'general.self.inspection', 'inspection_type_id', string='使用此樣板的一般式自主檢查')
    dash_reservation_inspection_ids = fields.One2many(
        'reservation.self.inspection', 'inspection_type_id', string='使用此樣板的預約式自主檢查')

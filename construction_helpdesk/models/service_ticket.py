# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

AGENT_GROUP = 'construction_helpdesk.group_helpdesk_agent'

# 回報人填的內容：離開「新建」後任何人都不能改（包含客服），只能用留言補充。
# 權威在 write()，view 的 readonly 只是 UX。
REPORTER_FIELDS = (
    'subject', 'description', 'channel', 'report_datetime',
    'customer_company', 'contact_name', 'project_name', 'project_code',
)

CHANNEL_SELECTION = [
    ('phone', '電話'),
    ('line', 'LINE'),
    ('email', 'Email'),
    ('in_person', '當面'),
    ('internal', '內部回報'),
    ('portal', '前台'),
]

# 兩個等待狀態只給「已掛上問題單」的服務單用（分級標準 v0.3 第九節）：
#   待客戶補件：修好之前，請客戶補資料 → 問題單自動勾「曾等客戶」，不適用逾期結案
#   待客戶驗證：修好之後，請客戶確認 → 前台有「問題已解決／仍有問題」按鈕，滿 N 天可逾期結案
# 沒掛問題單的服務單（例如操作疑問）等客戶時維持「處理中」。
STATE_SELECTION = [
    ('new', '新建'),
    ('processing', '處理中'),
    ('waiting_info', '待客戶補件'),
    ('waiting_verify', '待客戶驗證'),
    ('done', '已結案'),
    ('cancel', '取消'),
]
TICKET_ACTIVE_STATES = ('new', 'processing', 'waiting_info', 'waiting_verify')

CONFIRM_METHOD_SELECTION = [
    ('portal', '客戶在前台按「問題已解決」'),
    ('phone', '電話'),
    ('line', 'LINE'),
    ('email', 'Email'),
    ('in_person', '當面'),
]

# 只能由流程寫入的欄位（write() 擋手動修改）
VERIFY_FIELDS = (
    'waiting_verify_datetime', 'customer_confirmed', 'confirm_method', 'confirm_datetime',
    'confirm_contact', 'confirm_user_id', 'confirm_note', 'confirm_attachment_ids', 'overdue_closed',
)

SATISFACTION_SELECTION = [
    ('1', '1 非常不滿意'),
    ('2', '2 不滿意'),
    ('3', '3 普通'),
    ('4', '4 滿意'),
    ('5', '5 非常滿意'),
]


class ConstructionServiceTicket(models.Model):
    # 【分庫】日後分庫時服務單集中在「客服資料庫」，各客戶庫的前台透過 API 送單；
    # 屆時要加「來源客戶庫」「來源使用者」欄位。見 docs/分庫架構_集中客服資料庫.md
    _name = 'construction.service.ticket'
    _description = '服務單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'report_datetime desc, id desc'
    # 對話紀錄模式：看得到就能留言、附檔（附件上傳檢查的也是這個屬性）。
    # 欄位鎖定後，建單人仍要能補充資訊。
    _mail_post_access = 'read'

    name = fields.Char(string='單號', required=True, readonly=True, copy=False, default='新增')
    subject = fields.Char(string='主旨', required=True)
    description = fields.Html(string='詳細說明')
    category_id = fields.Many2one(
        'construction.service.category', string='類別', tracking=True, ondelete='restrict')
    ask_functional_module = fields.Boolean(related='category_id.ask_functional_module')
    is_helpdesk_agent = fields.Boolean(
        string='目前使用者是客服', compute='_compute_is_helpdesk_agent',
        help='畫面用：類別與發生功能是客服的處理欄位，送出後只有客服能改。')
    is_system_problem = fields.Boolean(
        related='category_id.is_system_problem', string='系統問題類')
    channel = fields.Selection(CHANNEL_SELECTION, string='回報管道', required=True)
    report_datetime = fields.Datetime(
        string='回報時間', required=True, default=fields.Datetime.now,
        help='客戶「告知我們」的時間，不是建單時間。'
             '例：客戶週六傳 LINE、週一才建單 → 填週六。送出後不可修改。')
    # 刻意用文字、不做 Many2one：本系統沒有管理「公司」主檔（res.partner 不是拿來記客戶公司的），
    # 做成關聯欄位只會逼客服去建一堆無人維護的聯絡人資料。
    customer_company = fields.Char(string='客戶公司', help='反映問題的客戶是哪一家公司（例：○○營造）。')
    contact_name = fields.Char(
        string='聯絡人', help='這件事要找誰聯絡：姓名，以及電話或 LINE。'
                           '前台送出的單自動帶入送出者姓名。')
    # 刻意用文字、不做 Many2one：日後分庫時工程案件在客戶庫，關聯連不過去
    project_name = fields.Char(string='工程案件')
    project_code = fields.Char(string='工程代號')
    functional_module_id = fields.Many2one(
        'construction.functional.module', string='發生功能', tracking=True, ondelete='restrict',
        help='客戶在使用哪一個功能時遇到問題（選填）。')
    state = fields.Selection(
        STATE_SELECTION, string='狀態', required=True, default='new', tracking=True, copy=False)
    close_datetime = fields.Datetime(string='結案時間', readonly=True, copy=False)

    # ---- 以下僅客服可見（欄位層級限制，自訂分組／匯出也拿不到）----
    problem_id = fields.Many2one(
        'construction.problem', string='關聯問題單', tracking=True, groups=AGENT_GROUP,
        ondelete='set null', copy=False)
    agent_user_id = fields.Many2one(
        'res.users', string='負責客服', tracking=True, groups=AGENT_GROUP,
        domain=lambda self: [('groups_id', 'in', self.env.ref(AGENT_GROUP).id)])
    notify_datetime = fields.Datetime(string='通知時間', groups=AGENT_GROUP, copy=False)
    notify_result = fields.Text(string='通知結果', groups=AGENT_GROUP, copy=False)
    satisfaction = fields.Selection(
        SATISFACTION_SELECTION, string='滿意度', groups=AGENT_GROUP, copy=False)
    customer_feedback = fields.Text(string='客戶意見', groups=AGENT_GROUP, copy=False)

    # ---- 客戶驗證（只由流程寫入：前台按鈕、登記客戶確認對話框、逾期排程）----
    waiting_verify_datetime = fields.Datetime(
        string='進入待客戶驗證時間', readonly=True, copy=False, groups=AGENT_GROUP,
        help='「客戶未回覆可結案天數」從這個時間起算。')
    customer_confirmed = fields.Boolean(
        string='客戶已確認解決', readonly=True, copy=False, groups=AGENT_GROUP, tracking=True)
    confirm_method = fields.Selection(
        CONFIRM_METHOD_SELECTION, string='確認方式', readonly=True, copy=False, groups=AGENT_GROUP)
    confirm_datetime = fields.Datetime(string='確認時間', readonly=True, copy=False, groups=AGENT_GROUP)
    confirm_contact = fields.Char(
        string='確認的人', readonly=True, copy=False, groups=AGENT_GROUP,
        help='客戶那邊是誰確認的（前台按鈕＝按的人）。')
    confirm_user_id = fields.Many2one(
        'res.users', string='登記人', readonly=True, copy=False, groups=AGENT_GROUP)
    confirm_note = fields.Text(string='確認說明', readonly=True, copy=False, groups=AGENT_GROUP)
    confirm_attachment_ids = fields.Many2many(
        'ir.attachment', 'construction_service_ticket_confirm_att_rel', 'ticket_id', 'attachment_id',
        string='確認佐證', readonly=True, copy=False, groups=AGENT_GROUP)
    overdue_closed = fields.Boolean(
        string='逾期未回覆結案', readonly=True, copy=False, groups=AGENT_GROUP, tracking=True,
        help='在「待客戶驗證」滿設定天數客戶都沒回覆而結案。客戶之後回覆會自動重開。')

    @api.depends_context('uid')
    def _compute_is_helpdesk_agent(self):
        is_agent = self.env.user.has_group(AGENT_GROUP)
        for ticket in self:
            ticket.is_helpdesk_agent = is_agent

    @api.onchange('category_id')
    def _onchange_category_clear_module(self):
        # 與前台一致：只有「操作疑問、系統問題」這類才問發生功能；改成別的類別就清掉
        if self.category_id and not self.category_id.ask_functional_module:
            self.functional_module_id = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # 非客服（代操作員、系統管理者）自己建單 → 預設「內部回報」。
        # 客服代客戶登記時不給預設值，逼他選實際管道。
        if 'channel' in fields_list and not res.get('channel') \
                and not self.env.user.has_group(AGENT_GROUP):
            res['channel'] = 'internal'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # 取號用 sudo：前台帳號沒有 ir.sequence 的讀取權（內部使用者才有）
            if vals.get('name', '新增') == '新增':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'construction.service.ticket') or '新增'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('helpdesk_system_write'):
            sys_touched = [f for f in VERIFY_FIELDS if f in vals]
            if sys_touched:
                raise UserError(_('%s 由系統依流程填寫（客戶在前台按的按鈕、逾期排程），不能手動修改。',
                                  '、'.join(self._fields[f].string for f in sys_touched)))
        if not self.env.su:
            locked = self.filtered(lambda t: t.state != 'new')
            touched = [f for f in REPORTER_FIELDS if f in vals]
            if locked and touched:
                labels = '、'.join(self._fields[f].string for f in touched)
                raise UserError(_(
                    '服務單 %(names)s 已送出（不是「新建」狀態），回報內容不可修改：%(fields)s。\n'
                    '要補充或更正，請在下方留言。',
                    names='、'.join(locked.mapped('name')), fields=labels))
            if 'state' in vals and not self.env.user.has_group(AGENT_GROUP):
                raise UserError(_('只有客服可以變更服務單狀態。'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # 狀態切換（按鈕只給客服；權威在 write() 的狀態檢查）
    # ------------------------------------------------------------------
    def _check_state_from(self, allowed):
        for ticket in self:
            if ticket.state not in allowed:
                raise UserError(_('服務單 %s 目前狀態不能執行這個動作。', ticket.name))

    def action_start(self):
        self._check_state_from(('new',))
        vals = {'state': 'processing'}
        self.write(vals)
        for ticket in self.filtered(lambda t: not t.agent_user_id):
            ticket.agent_user_id = self.env.user
        return True

    def _check_linked(self):
        for ticket in self:
            if not ticket.sudo().problem_id:
                raise UserError(_(
                    '服務單 %s 還沒有關聯問題單。「待客戶補件」「待客戶驗證」只用在已轉成問題單的服務單；'
                    '要請客戶補資料，請先轉問題單。', ticket.name))

    def action_wait_info(self):
        """修好之前請客戶補資料。問題單自動勾「曾等客戶」。"""
        self._check_state_from(('processing',))
        self._check_linked()
        self.write({'state': 'waiting_info'})
        self.sudo().problem_id._mark_waited_customer()
        return True

    def action_wait_verify(self):
        """修好（已部署）之後請客戶確認。從這一刻開始算「客戶未回覆可結案天數」。"""
        self._check_state_from(('processing',))
        self._check_linked()
        for ticket in self:
            problem = ticket.sudo().problem_id
            if problem.state not in ('pending_verify', 'done'):
                raise UserError(_(
                    '服務單 %(t)s 的問題單 %(p)s 還沒部署（目前「%(s)s」）。'
                    '要等問題單到「待驗證」之後才能請客戶驗證。',
                    t=ticket.name, p=problem.name,
                    s=dict(problem._fields['state'].selection).get(problem.state)))
        self.write({'state': 'waiting_verify'})
        self.with_context(helpdesk_system_write=True).write({
            'waiting_verify_datetime': fields.Datetime.now(),
            'customer_confirmed': False,
            'overdue_closed': False,
        })
        return True

    def action_back_to_processing(self):
        self._check_state_from(('waiting_info', 'waiting_verify'))
        self.write({'state': 'processing'})
        return True

    def action_done(self):
        """客服直接結案。掛著未結案問題單的服務單不能走這裡——要客戶確認或等逾期。"""
        self._check_state_from(('processing',))
        for ticket in self:
            problem = ticket.sudo().problem_id
            if problem and problem.state not in ('done', 'wont_fix'):
                raise UserError(_(
                    '服務單 %(t)s 關聯的問題單 %(p)s 還沒結案。'
                    '這類服務單要在「待客戶驗證」由客戶在前台按「問題已解決」，或等客戶逾期未回覆。',
                    t=ticket.name, p=problem.name))
        self.write({'state': 'done', 'close_datetime': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self._check_state_from(TICKET_ACTIVE_STATES)
        self.write({'state': 'cancel', 'close_datetime': fields.Datetime.now()})
        return True

    # 【停用】登記客戶確認（客服代登記電話、LINE 等方式的確認）。2026-09-29 使用者判斷目前沒有電話、LINE 客服，
    # 客戶一律在前台按「問題已解決」。要恢復時照 wizards/ticket_confirm_wizard.py 開頭的步驟取消註解。
    # def action_open_confirm_wizard(self):
    #     self.ensure_one()
    #     self._check_state_from(('waiting_verify',))
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': _('登記客戶確認'),
    #         'res_model': 'construction.service.ticket.confirm.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {'default_ticket_id': self.id},
    #     }

    # ------------------------------------------------------------------
    # 客戶驗證的結果（只由流程呼叫，以 sudo 執行：前台帳號沒有服務單的寫入權）
    # ------------------------------------------------------------------
    def _register_confirmation(self, method, contact, note, user, attachments=None):
        """客戶確認問題已解決 → 結案。"""
        self.ensure_one()
        if self.state != 'waiting_verify':
            raise UserError(_('服務單 %s 不在「待客戶驗證」，不能登記確認。', self.name))
        # 佐證依方式而定：LINE、Email 留得下截圖；電話、當面不可能有圖，改要求寫下對方怎麼說
        if method in ('line', 'email') and not attachments:
            raise UserError(_('LINE、Email 確認的，必須附上截圖作為佐證。'))
        if method in ('phone', 'in_person') and not (note or '').strip():
            raise UserError(_('電話、當面確認的，必須寫下時間與對方怎麼說。'))
        ticket = self.sudo()
        if attachments:
            # 對話框上傳的附件改掛到服務單，客服在服務單上看得到
            attachments.sudo().write({'res_model': self._name, 'res_id': self.id})
        now = fields.Datetime.now()
        ticket.with_context(helpdesk_system_write=True).write({
            'state': 'done',
            'close_datetime': now,
            'customer_confirmed': True,
            'confirm_method': method,
            'confirm_datetime': now,
            'confirm_contact': contact,
            'confirm_user_id': user.id,
            'confirm_note': note,
            'confirm_attachment_ids': [(6, 0, attachments.ids if attachments else [])],
        })
        label = dict(CONFIRM_METHOD_SELECTION)[method]
        ticket.message_post(
            body=_('客戶確認問題已解決（%(m)s，%(c)s）。', m=label, c=contact or user.name),
            subtype_xmlid='mail.mt_note', attachment_ids=attachments.ids if attachments else [])
        if ticket.problem_id:
            ticket.problem_id.message_post(
                body=_('服務單 %(t)s：客戶確認問題已解決（%(m)s）。', t=self.name, m=label),
                subtype_xmlid='mail.mt_note')
        return True

    def _register_not_resolved(self, user):
        """客戶在前台按「仍有問題」→ 回到處理中。"""
        self.ensure_one()
        if self.state != 'waiting_verify':
            raise UserError(_('服務單 %s 不在「待客戶驗證」。', self.name))
        ticket = self.sudo()
        ticket.with_context(helpdesk_system_write=True).write({'state': 'processing'})
        ticket.message_post(body=_('客戶回報「仍有問題」（%s），服務單回到處理中。', user.name),
                            subtype_xmlid='mail.mt_note')
        if ticket.problem_id:
            ticket.problem_id.message_post(
                body=_('服務單 %s：客戶回報「仍有問題」。請判斷是沒修乾淨（重開本單）還是另一個問題（改連新的問題單）。',
                       self.name),
                subtype_xmlid='mail.mt_note')
        return True

    def _close_no_reply(self):
        """客戶在「待客戶驗證」滿 N 天沒回覆 → 結案並標記。前台看得到這則說明。"""
        now = fields.Datetime.now()
        for ticket in self.sudo():
            ticket = ticket.with_context(helpdesk_system_write=True)
            ticket.write({'state': 'done', 'close_datetime': now, 'overdue_closed': True})
            # 用一般留言（不是內部備註）：客戶在前台要看得到。
            # context 帶 helpdesk_system_write：這則是系統發的，不能觸發下面 message_post 的「客戶回覆即重開」
            ticket.message_post(
                body=_('您一直沒有回覆，本單已視為問題解決並結案。'
                       '如果問題仍在，直接回覆本單即會重新開啟，不需要重新回報。'),
                message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    @api.model
    def _cron_close_overdue_verify(self):
        """每天執行：P3／P4 的服務單在「待客戶驗證」滿設定天數就自動結案。

        P1／P2 不自動結案：要由客服在問題單附齊三件修復對照後結案（屆時一併處理這些服務單）。
        """
        Sla = self.env['construction.problem.sla']
        now = fields.Datetime.now()
        tickets = self.sudo().search([('state', '=', 'waiting_verify')])
        todo = tickets.filtered(
            lambda t: t.problem_id.final_priority in ('p3', 'p4') and t.waiting_verify_datetime
            and t.waiting_verify_datetime <= now - timedelta(
                days=Sla.get_customer_wait_days(t.problem_id.final_priority)))
        todo._close_no_reply()
        for problem in todo.mapped('problem_id'):
            problem.message_post(
                body=_('關聯服務單逾期未回覆，已自動結案：%s',
                       '、'.join(todo.filtered(lambda t: t.problem_id == problem).mapped('name'))),
                subtype_xmlid='mail.mt_note')
        return len(todo)

    def message_post(self, **kwargs):
        """客戶回覆「逾期未回覆結案」的服務單 → 自動重開（自動結案通知裡的承諾）。"""
        message = super().message_post(**kwargs)
        if kwargs.get('message_type', 'notification') == 'comment' \
                and not self.env.user.has_group(AGENT_GROUP) \
                and not self.env.context.get('helpdesk_system_write'):
            for ticket in self.sudo().filtered(lambda t: t.state == 'done' and t.overdue_closed):
                ticket.with_context(helpdesk_system_write=True).write({
                    'state': 'processing', 'close_datetime': False, 'overdue_closed': False})
                ticket.message_post(body=_('客戶在逾期結案後回覆，服務單已自動重新開啟。'),
                                    subtype_xmlid='mail.mt_note')
                if ticket.problem_id:
                    ticket.problem_id.message_post(
                        body=Markup(_('服務單 %s 的客戶在逾期結案後回覆，服務單已重開，請確認問題是否仍在。'))
                        % ticket.name,
                        subtype_xmlid='mail.mt_note')
        return message

    def action_open_link_problem(self):
        self.ensure_one()
        if not self.is_system_problem:
            raise UserError(_('只有類別為「系統問題」的服務單可以轉問題單。請先把類別改成系統問題。'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('轉問題單'),
            'res_model': 'construction.problem.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

    def action_reopen(self):
        self._check_state_from(('done', 'cancel'))
        self.write({'state': 'processing', 'close_datetime': False})
        # 重開＝這次的確認／逾期結案不算數了（舊值留在修改紀錄裡）
        self.with_context(helpdesk_system_write=True).write({
            'customer_confirmed': False, 'overdue_closed': False})
        return True

    # ------------------------------------------------------------------
    # 留言送出後不能改、不能刪（所有人，含客服與 Odoo 管理員）
    # Odoo 18 預設允許作者本人或管理員編輯／刪除留言
    # （mail/controllers/thread.py `_is_message_editable`），刪除也是走這個方法（body 清空）。
    # 直接對 mail.message 的 RPC 寫入／刪除另在 models/mail_message.py 擋。
    # ------------------------------------------------------------------
    def _message_update_content(self, message, body, attachment_ids=None, partner_ids=None,
                                strict=True, **kwargs):
        raise UserError(_('服務單上的留言送出後不能修改或刪除。要更正請再留一則新的留言。'))

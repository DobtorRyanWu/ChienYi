# -*- coding: utf-8 -*-
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

STATE_SELECTION = [
    ('new', '新建'),
    ('processing', '處理中'),
    ('waiting_customer', '待客戶確認'),
    ('done', '已結案'),
    ('cancel', '取消'),
]

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

    def action_wait_customer(self):
        self._check_state_from(('processing',))
        self.write({'state': 'waiting_customer'})
        return True

    def action_back_to_processing(self):
        self._check_state_from(('waiting_customer',))
        self.write({'state': 'processing'})
        return True

    def action_done(self):
        self._check_state_from(('processing', 'waiting_customer'))
        self.write({'state': 'done', 'close_datetime': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self._check_state_from(('new', 'processing', 'waiting_customer'))
        self.write({'state': 'cancel', 'close_datetime': fields.Datetime.now()})
        return True

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

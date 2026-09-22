# -*- coding: utf-8 -*-
"""系統問題單。分級邏輯依《系統問題分級與處理時限標準》v0.2。"""
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .problem_sla import PRIORITY_SELECTION

# 起算日要把 Datetime（UTC）換成台灣日期。stored compute 不能跟著執行者的時區走，
# 否則不同人觸發重算會得到不同日期，所以固定用本系統所在時區。
LOCAL_TZ = pytz.timezone('Asia/Taipei')

WEEKDAYS = '一二三四五六日'

# 選項文字附上簡短判定條件，讓客服在下拉時就有依據（完整標準見表單上的判定標準參考表）
SEVERITY_SELECTION = [
    ('s1', 'S1 致命（資料錯誤／寫錯工程、無法登入或全面停擺、資安疑慮）'),
    ('s2', 'S2 嚴重（核心功能不能用，且沒有替代做法）'),
    ('s3', 'S3 中等（功能異常但有替代做法，或只影響部分人）'),
    ('s4', 'S4 輕微（不影響功能與資料正確性：錯字、跑版）'),
]
URGENCY_SELECTION = [
    ('u1', 'U1 立即（現場作業中斷，或 3 個工作天內有送件／請款／驗收）'),
    ('u2', 'U2 一般（可暫時替代，外部期限在 2 週內）'),
    ('u3', 'U3 可延後（不影響目前作業，沒有明確期限）'),
]

# P1～P4 代表的層級（分級標準第六節）。修復期限另從「處理時限設定」即時讀取，這裡只放不會變的部分
PRIORITY_MEANING = {
    'p1': ('最緊急', '緊急修補，修好即部署', '須先做暫行措施（停用功能／請客戶暫緩／人工提供正確數字）'),
    'p2': ('緊急', '緊急版本', ''),
    'p3': ('一般', '下一次例行版本', ''),
    'p4': ('低', '例行版本（排入規劃）', ''),
}
STATE_SELECTION = [
    ('pending_grade', '待分級'),
    ('processing', '處理中'),
    ('pending_deploy', '待部署'),
    ('pending_verify', '待驗證'),
    ('done', '已結案'),
    ('wont_fix', '不處理'),
]
CLOSED_STATES = ('done', 'wont_fix')

# P 表（S × U）。分級標準第四節。刻意寫死：P 表比時限更少變動，要改就改程式、bump 版號。
# 問題單上的 P 是 stored，改這張表不會回頭改既有問題單。
P_MATRIX = {
    ('s1', 'u1'): 'p1', ('s1', 'u2'): 'p1', ('s1', 'u3'): 'p2',
    ('s2', 'u1'): 'p1', ('s2', 'u2'): 'p2', ('s2', 'u3'): 'p3',
    ('s3', 'u1'): 'p2', ('s3', 'u2'): 'p3', ('s3', 'u3'): 'p4',
    ('s4', 'u1'): 'p3', ('s4', 'u2'): 'p4', ('s4', 'u3'): 'p4',
}

# 分級欄位：分級之後只能透過「變更等級」對話框修改（確保每次改判都有原因）
GRADE_FIELDS = (
    'severity', 'urgency', 'special_external_doc', 'special_security', 'special_repeat',
    'manual_priority', 'downgrade_reason',
)

DATA_FIX_STATE_SELECTION = [
    ('todo', '待盤點'),
    ('in_progress', '修正中'),
    ('done', '已完成'),
]


def p_rank(priority):
    """'p1' → 1。數字越小越優先。"""
    return int(priority[1]) if priority else None


def upgraded_priority(matrix_p, external_doc, security, repeat):
    """套用特例（分級標準第五節）。"""
    if security:
        return 'p1'                       # 資安直接 P1，不受「最多升一級」限制
    if not matrix_p:
        return False
    if external_doc or repeat:
        return 'p%d' % max(1, p_rank(matrix_p) - 1)   # 不論幾個成立，最多升一級
    return matrix_p


class ConstructionProblem(models.Model):
    _name = 'construction.problem'
    _description = '系統問題單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'title']

    # ------------------------------------------------------------------
    # 基本
    # ------------------------------------------------------------------
    name = fields.Char(string='單號', required=True, readonly=True, copy=False, default='新增')
    title = fields.Char(string='標題', required=True, tracking=True)
    description = fields.Html(
        string='問題說明',
        help='這個問題的具體情況（在哪個畫面、做了什麼、看到什麼）。從服務單轉出時自動帶入服務單的詳細說明。'
             '判斷其他客戶的回報是不是同一個問題，主要就是比對這裡與發生功能。')
    description_summary = fields.Char(
        string='問題說明摘要', compute='_compute_description_summary',
        help='問題說明的前 120 字（純文字），給轉問題單時比對候選用。')
    functional_module_id = fields.Many2one(
        'construction.functional.module', string='發生功能', tracking=True, ondelete='restrict')
    engineer_id = fields.Many2one(
        'res.users', string='負責工程師', tracking=True,
        domain=lambda self: [('groups_id', 'in', self.env.ref(
            'construction_helpdesk.group_helpdesk_agent').id)])
    state = fields.Selection(
        STATE_SELECTION, string='狀態', required=True, default='pending_grade', tracking=True,
        copy=False,
        # Selection 欄位要用 True（Odoo 自帶的展開）；'_read_group_expand_full' 只適用 Many2one，
        # 用在 Selection 會在看板分組時丟 AttributeError: 'list' object has no attribute 'search'
        group_expand=True)
    occurred_version = fields.Char(string='發生時的系統版本')

    # ------------------------------------------------------------------
    # 分級（S、U 刻意沒有預設值：沒判就是沒判）
    # ------------------------------------------------------------------
    severity = fields.Selection(SEVERITY_SELECTION, string='嚴重程度 S', tracking=True)
    urgency = fields.Selection(URGENCY_SELECTION, string='急迫性 U', tracking=True)
    matrix_priority = fields.Selection(
        PRIORITY_SELECTION, string='查表 P', compute='_compute_priorities', store=True)
    special_external_doc = fields.Boolean(
        string='錯誤已流入對外文件', tracking=True,
        help='升一級，且必須主動通知客戶可能受影響的範圍。')
    special_security = fields.Boolean(string='資安事件', tracking=True, help='直接 P1，並另循資安通報程序。')
    special_repeat = fields.Boolean(string='二次回報（前次未修好）', tracking=True, help='升一級。')
    upgraded_priority = fields.Selection(
        PRIORITY_SELECTION, string='套用特例後 P', compute='_compute_priorities', store=True)
    manual_priority = fields.Selection(
        PRIORITY_SELECTION, string='人工調整 P', tracking=True,
        help='留空＝採用「套用特例後 P」。調得比它低（降級）時，調整原因必填。')
    downgrade_reason = fields.Text(
        string='調整原因', tracking=True,
        help='人工調整 P 時說明原因。往下調（降級）時必填；往上調可選填。')
    final_priority = fields.Selection(
        PRIORITY_SELECTION, string='最終 P', compute='_compute_priorities', store=True, tracking=True)
    graded_datetime = fields.Datetime(string='分級時間', readonly=True, copy=False)
    grade_guide_html = fields.Html(
        string='判定標準', compute='_compute_grade_guide_html', sanitize=False,
        help='S／U／P 判定標準參考表。P 的修復期限即時讀「處理時限設定」，改了天數這裡跟著變。')
    is_graded = fields.Boolean(string='已分級', compute='_compute_is_graded', store=True)
    ever_upgraded = fields.Boolean(
        string='曾升級改判', readonly=True, copy=False, tracking=True,
        help='分級後又往上改判過。試行期每月檢視一次，看初判準不準。')

    # ------------------------------------------------------------------
    # 關聯
    # ------------------------------------------------------------------
    ticket_ids = fields.One2many('construction.service.ticket', 'problem_id', string='關聯服務單')
    ticket_count = fields.Integer(string='服務單數', compute='_compute_reported_customers', store=True)
    reported_customer_count = fields.Integer(
        string='回報客戶數', compute='_compute_reported_customers', store=True,
        help='關聯服務單的相異客戶公司數（依名稱文字比對；沒填的不算）。純資訊，不影響等級。')

    # ------------------------------------------------------------------
    # 時限（全部以日期計算，不用工作行事曆）
    # 預定修復日 ＝ 計算基準日 ＋ 預期工作天數 ＋ 非工作日天數
    # ------------------------------------------------------------------
    start_date = fields.Date(
        string='起算日', compute='_compute_start_date', store=True,
        help='客戶告知我們的日期：關聯服務單中最早的回報時間。沒有關聯服務單時＝問題單建立日。')
    base_date = fields.Date(
        string='計算基準日', tracking=True, copy=False,
        help='初次分級時＝起算日；改判時＝改判日。')
    base_date_label = fields.Char(string='計算基準日（星期）', compute='_compute_base_date_label')
    expected_work_days = fields.Integer(
        string='預期工作天數', tracking=True, copy=False,
        help='分級／改判時依最終 P 從處理時限設定帶入，可調整。0＝不設天數（P3、P4）。')
    non_working_days = fields.Integer(
        string='非工作日天數', tracking=True, copy=False,
        help='手動輸入：從計算基準日的「隔天」數到預定修復日為止的週末與國定假日。'
             '基準日當天不算。例：週六回報、P1（2 天）→ 日✗ 一① 二② → 填 1，預定修復日＝週二。')
    planned_fix_date = fields.Date(
        string='預定修復日', compute='_compute_planned_fix_date', store=True, tracking=True)
    non_working_to_confirm = fields.Boolean(
        string='非工作日待確認', readonly=True, copy=False,
        help='分級或等級變更後設起來。重新輸入非工作日天數、或按「確認非工作日天數」後清除。')
    fix_done_date = fields.Date(string='修復完成日', tracking=True, copy=False)
    total_days = fields.Integer(
        string='總處理天數', compute='_compute_total_days', store=True, aggregator='avg',
        help='修復完成日 − 起算日（日曆天）。這才是「客戶等了多久」；對外報告服務水準用這個，不用逾時率。')
    is_overdue = fields.Boolean(
        string='逾時', compute='_compute_is_overdue', search='_search_is_overdue',
        help='只代表沒達到內部工作目標（預定修復日），不代表客戶等太久。')

    # ------------------------------------------------------------------
    # 回應／暫行措施：只記錄，不判逾時
    # ------------------------------------------------------------------
    response_datetime = fields.Datetime(string='回應完成時間', tracking=True, copy=False)
    temporary_measure = fields.Text(string='暫行措施內容', copy=False)
    temporary_datetime = fields.Datetime(string='暫行措施執行時間', tracking=True, copy=False)
    temporary_user_id = fields.Many2one('res.users', string='暫行措施執行人', copy=False)

    # ------------------------------------------------------------------
    # 資料修正（S1 資料錯誤的第二個交付物，最容易漏掉）
    # ------------------------------------------------------------------
    data_fix_needed = fields.Boolean(string='需要修正既有資料', tracking=True)
    data_fix_scope = fields.Text(string='受影響範圍')
    data_fix_method = fields.Text(string='盤點方式')
    data_fix_state = fields.Selection(DATA_FIX_STATE_SELECTION, string='修正狀態', tracking=True)
    data_fix_done_date = fields.Date(string='修正完成日', tracking=True)

    # ------------------------------------------------------------------
    # 已知錯誤
    # ------------------------------------------------------------------
    is_known_error = fields.Boolean(string='已知錯誤', tracking=True)
    known_error_reply = fields.Text(string='客服回覆參考')

    # ==================================================================
    # compute
    # ==================================================================
    @api.depends('severity', 'urgency', 'special_external_doc', 'special_security',
                 'special_repeat', 'manual_priority')
    def _compute_priorities(self):
        for rec in self:
            matrix_p = P_MATRIX.get((rec.severity, rec.urgency), False)
            up_p = upgraded_priority(matrix_p, rec.special_external_doc,
                                     rec.special_security, rec.special_repeat)
            rec.matrix_priority = matrix_p
            rec.upgraded_priority = up_p
            # 人工調整只在已有判定結果時生效（S、U 沒判完就沒有 P）
            rec.final_priority = (rec.manual_priority or up_p) if up_p else False

    @api.depends('description')
    def _compute_description_summary(self):
        from odoo.tools import html2plaintext
        for rec in self:
            text = ' '.join(html2plaintext(rec.description or '').split())
            rec.description_summary = text[:120] + ('…' if len(text) > 120 else '')

    @api.depends('name', 'title')
    def _compute_display_name(self):
        # 下拉選單與清單顯示「單號 標題」：只看單號，客服不可能知道是哪個問題
        for rec in self:
            rec.display_name = ('%s %s' % (rec.name or '', rec.title or '')).strip()

    def _compute_grade_guide_html(self):
        html = self._grade_guide_html()
        for rec in self:
            rec.grade_guide_html = html

    @api.model
    def _grade_guide_html(self):
        """分級標準 v0.2 的 S 表、U 表、P 表與 P 的意義（修復期限讀處理時限設定）。"""
        from markupsafe import Markup, escape
        slas = {s.priority: s for s in self.env['construction.problem.sla'].sudo().search([])}
        th = 'style="padding:4px 8px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;white-space:nowrap"'
        td = 'style="padding:4px 8px;border:1px solid #d0d7de;vertical-align:top"'

        def table(head, rows):
            out = '<table style="border-collapse:collapse;margin:4px 0 12px 0;font-size:0.9em">'
            out += '<tr>' + ''.join('<th %s>%s</th>' % (th, escape(h)) for h in head) + '</tr>'
            for r in rows:
                out += '<tr>' + ''.join('<td %s>%s</td>' % (td, escape(c)) for c in r) + '</tr>'
            return out + '</table>'

        s_rows = [
            ('S1 致命', '資料錯誤、遺失、或寫到別的工程；系統無法登入或全面停擺；有資安疑慮。'
                       '畫面沒報錯但金額／數量算錯，也是 S1'),
            ('S2 嚴重', '核心功能無法完成作業，且沒有替代做法（核心功能：登入、施工日誌、通報單、'
                       '契約工項、估驗計價、自主檢查、檔案上傳下載）'),
            ('S3 中等', '功能異常或結果不正確，但有替代做法，或只影響部分使用者'),
            ('S4 輕微', '不影響功能與資料正確性：錯字、跑版、操作不便'),
        ]
        u_rows = [
            ('U1 立即', '現場作業當下中斷無法繼續；或 3 個工作天內有外部期限（送件、請款、驗收）'),
            ('U2 一般', '影響效率或正確性，但可用替代方式撐過；外部期限在 2 週內'),
            ('U3 可延後', '不影響目前作業，且沒有明確期限'),
        ]
        p_matrix = [(s, *[P_MATRIX[(s.lower(), u)].upper() for u in ('u1', 'u2', 'u3')])
                    for s in ('S1', 'S2', 'S3', 'S4')]
        p_rows = []
        for p in ('p1', 'p2', 'p3', 'p4'):
            level, deploy, extra = PRIORITY_MEANING[p]
            sla = slas.get(p)
            p_rows.append((p.upper() + ' ' + level,
                           sla.fix_limit_note if sla else '',
                           (sla.response_target or '') if sla else '',
                           deploy + ('；' + extra if extra else '')))
        body = (
            '<div style="font-size:0.9em;color:#57606a;margin-bottom:6px">'
            '判定順序：先判 S（由上往下，第一個符合的就是）→ 再判 U → 查 P 表 → 套用特例。'
            '<b>判斷不確定時取較高等級。</b></div>'
            '<b>S 嚴重程度</b>' + table(('等級', '判斷條件'), s_rows) +
            '<b>U 急迫性</b>' + table(('等級', '判斷條件'), u_rows) +
            '<b>P 表（S × U）</b>' + table(('', 'U1 立即', 'U2 一般', 'U3 可延後'), p_matrix) +
            '<b>P 代表的層級</b>（人工調整 P 時的依據）' +
            table(('等級', '修復期限', '回應目標', '部署方式'), p_rows) +
            '<div style="font-size:0.9em;color:#57606a">特例：錯誤已流入對外文件、二次回報 → 升一級（兩個都成立也只升一級）；'
            '資安事件 → 直接 P1。</div>'
        )
        return Markup(body)

    @api.depends('graded_datetime')
    def _compute_is_graded(self):
        for rec in self:
            rec.is_graded = bool(rec.graded_datetime)

    @api.depends('ticket_ids', 'ticket_ids.customer_company')
    def _compute_reported_customers(self):
        for rec in self:
            tickets = rec.ticket_ids
            rec.ticket_count = len(tickets)
            # 客戶公司是文字欄位：去頭尾空白後比對，空白的不算
            rec.reported_customer_count = len({
                (t.customer_company or '').strip() for t in tickets
                if (t.customer_company or '').strip()})

    @api.depends('ticket_ids.report_datetime', 'create_date')
    def _compute_start_date(self):
        for rec in self:
            stamps = [t.report_datetime for t in rec.ticket_ids if t.report_datetime]
            first = min(stamps) if stamps else rec.create_date
            rec.start_date = (pytz.utc.localize(first).astimezone(LOCAL_TZ).date()
                              if first else False)

    @api.depends('base_date')
    def _compute_base_date_label(self):
        for rec in self:
            rec.base_date_label = ('%s（%s）' % (rec.base_date, WEEKDAYS[rec.base_date.weekday()])
                                   if rec.base_date else False)

    @api.depends('base_date', 'expected_work_days', 'non_working_days')
    def _compute_planned_fix_date(self):
        for rec in self:
            if rec.base_date and rec.expected_work_days > 0:
                rec.planned_fix_date = rec.base_date + timedelta(
                    days=rec.expected_work_days + max(rec.non_working_days, 0))
            else:
                rec.planned_fix_date = False

    @api.depends('start_date', 'fix_done_date')
    def _compute_total_days(self):
        for rec in self:
            rec.total_days = ((rec.fix_done_date - rec.start_date).days
                              if rec.start_date and rec.fix_done_date else 0)

    # 非 stored（「今天」每天在變），但要宣告 depends，否則同一交易內改了日期不會重算
    @api.depends('planned_fix_date', 'fix_done_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            planned = rec.planned_fix_date
            if not planned:
                rec.is_overdue = False
            elif rec.fix_done_date:
                rec.is_overdue = rec.fix_done_date > planned
            else:
                rec.is_overdue = today > planned

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('「逾時」只支援等於／不等於 是或否。'))
        today = fields.Date.context_today(self)
        self.env['construction.problem'].flush_model(['planned_fix_date', 'fix_done_date'])
        # 兩個日期欄位互相比較，domain 表達不了，用 SQL 找出逾時的 id
        self.env.cr.execute("""
            SELECT id FROM construction_problem
             WHERE planned_fix_date IS NOT NULL
               AND ((fix_done_date IS NULL AND planned_fix_date < %s)
                 OR (fix_done_date IS NOT NULL AND fix_done_date > planned_fix_date))
        """, (today,))
        ids = [r[0] for r in self.env.cr.fetchall()]
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', ids)]

    # ==================================================================
    # constraints
    # ==================================================================
    @api.constrains('manual_priority', 'upgraded_priority', 'downgrade_reason')
    def _check_downgrade_reason(self):
        for rec in self:
            if rec.manual_priority and rec.upgraded_priority \
                    and p_rank(rec.manual_priority) > p_rank(rec.upgraded_priority) \
                    and not (rec.downgrade_reason or '').strip():
                raise ValidationError(_(
                    '%(name)s：人工調整為 %(m)s，低於套用特例後的 %(u)s（降級），必須填寫調整原因。',
                    name=rec.name, m=rec.manual_priority.upper(), u=rec.upgraded_priority.upper()))

    @api.constrains('expected_work_days', 'non_working_days')
    def _check_days(self):
        for rec in self:
            if rec.expected_work_days < 0 or rec.non_working_days < 0:
                raise ValidationError(_('天數不可為負數。'))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '新增') == '新增':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('construction.problem') or '新增'
        records = super().create(vals_list)
        records._apply_first_grading()
        return records

    def write(self, vals):
        if not self.env.context.get('helpdesk_regrade'):
            touched = [f for f in GRADE_FIELDS if f in vals]
            graded = self.filtered('graded_datetime')
            if touched and graded:
                raise UserError(_(
                    '%s 已分級，等級相關欄位請用「變更等級」修改（需填改判原因）。',
                    '、'.join(graded.mapped('name'))))
        if 'non_working_days' in vals and 'non_working_to_confirm' not in vals:
            # 客服重新輸入了非工作日天數 → 視為已確認
            vals = dict(vals, non_working_to_confirm=False)
        res = super().write(vals)
        if not self.env.context.get('helpdesk_regrade'):
            self._apply_first_grading()
        return res

    def _apply_first_grading(self):
        """初次分級：最終 P 第一次出現時，記下分級時間並依 P 算時限（快照）。"""
        Sla = self.env['construction.problem.sla']
        for rec in self.filtered(lambda r: r.final_priority and not r.graded_datetime):
            vals = {
                'graded_datetime': fields.Datetime.now(),
                'base_date': rec.start_date,
                'expected_work_days': Sla.get_default_fix_days(rec.final_priority),
            }
            if vals['expected_work_days']:
                vals['non_working_to_confirm'] = True
            if rec.state == 'pending_grade':
                vals['state'] = 'processing'
            rec.with_context(helpdesk_regrade=True).write(vals)

    # ==================================================================
    # 動作
    # ==================================================================
    def action_confirm_non_working_days(self):
        self.write({'non_working_to_confirm': False})
        return True

    def action_open_regrade(self):
        self.ensure_one()
        if not self.graded_datetime:
            raise UserError(_('尚未分級。請先在表單上判定 S 與 U。'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('變更等級'),
            'res_model': 'construction.problem.regrade.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_problem_id': self.id},
        }

    def _check_state_from(self, allowed):
        for rec in self:
            if rec.state not in allowed:
                raise UserError(_('%s 目前狀態不能執行這個動作。', rec.name))

    def action_to_deploy(self):
        self._check_state_from(('processing',))
        self.write({'state': 'pending_deploy'})
        return True

    def action_to_verify(self):
        self._check_state_from(('pending_deploy',))
        self.write({'state': 'pending_verify'})
        return True

    def action_back_to_processing(self):
        self._check_state_from(('pending_deploy', 'pending_verify'))
        self.write({'state': 'processing'})
        return True

    def action_done(self):
        self._check_state_from(('processing', 'pending_deploy', 'pending_verify'))
        for rec in self:
            if rec.data_fix_needed and rec.data_fix_state != 'done':
                raise UserError(_(
                    '%s 標記需要修正既有資料，但修正狀態還不是「已完成」，不能結案。\n'
                    '程式修好之後，資料庫裡既有的錯誤數值不會自動更正。', rec.name))
            vals = {'state': 'done'}
            if not rec.fix_done_date:
                vals['fix_done_date'] = fields.Date.context_today(rec)
            rec.write(vals)
        # 刻意不動關聯服務單的狀態（可能還沒部署）
        return True

    def action_wont_fix(self):
        self._check_state_from(('pending_grade', 'processing', 'pending_deploy', 'pending_verify'))
        self.write({'state': 'wont_fix'})
        return True

    def action_reopen(self):
        self._check_state_from(CLOSED_STATES)
        for rec in self:
            # 重開＝其實沒修好，清掉修復完成日（舊值留在修改紀錄裡）
            rec.write({'state': 'processing' if rec.graded_datetime else 'pending_grade',
                       'fix_done_date': False})
        return True

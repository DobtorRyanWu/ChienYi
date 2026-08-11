# -*- coding: utf-8 -*-

import re

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

# 項次開頭的數字（'12' → 12、'☆' → 無）
LEADING_NUMBER = re.compile(r'\s*(\d+)')

DEFAULT_CONTROL_TYPE = 'plan'


class SupervisionPlanControl(models.Model):
    """計畫書送審管制

    參考來源：既有案件「管制表」的 `1.計畫` 工作表（計畫書送審管制總表(含工程保險)）。
    管的是全案性的計畫書——監造計畫、職業安全衛生管理計畫、整體施工計畫、
    整體品質計畫、營造綜合保險等，與 supervision.review.application（材料設備送審）
    是兩回事：這裡沒有型錄／樣品／取樣試驗，改成四組「日期＋發文文號」的往返流程。

    同一份參考檔的 `2.分項計畫`、`3.施工圖送審` 兩張表欄位標題完全相同，只是裝的
    資料不同，所以三種共用這張表，用 control_type 區分。項次也是各類別各自從 1 編。
    匯出時三種共用同一份空白樣板，只換表名（見 construction_template 的
    mappings/plan_control.py）。
    """
    _name = 'supervision.plan.control'
    _description = '計畫書送審管制'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
    _order = 'control_type, item_sequence, sequence, id'
    _rec_name = 'display_name'

    # === 分類 ===
    control_type = fields.Selection([
        ('plan', '計畫書'),
        ('sub_plan', '分項計畫'),
        ('drawing', '施工圖'),
    ], string='管制表類別',
       default=DEFAULT_CONTROL_TYPE,
       required=True,
       index=True,
       tracking=True)

    # === 基本資料 ===
    # 排序用，不放進畫面（使用者不需要看到）。全部同值時等於依建立順序排，
    # 也就是使用者逐列輸入的順序；item_no 是 Char（含 ☆）不能拿來排。
    sequence = fields.Integer(string='排序', default=10)

    # 原表的「項次」不全是數字：監造單位自提的監造計畫、監造用人計畫填的是 ☆，
    # 承包商提送的才從 1 開始編。所以是 Char 不是 Integer。
    # 留空建立時會自動接續同一工程、同一類別的下一號，之後可自行改（含改成 ☆）。
    item_no = fields.Char(
        string='項次',
        help='留空會自動接續本工程的下一號；可自行修改。'
             '監造單位自提項目依原表慣例填 ☆')

    # 排序用的數值化項次：'12' → 12、'☆' 或空白 → 0（排在最前面，
    # 與原表把監造自提的 ☆ 兩列放在項次 1 之前一致）。
    # 清單與匯出都靠它排序，所以必須 store（_order 只能用實體欄位）。
    item_sequence = fields.Integer(
        string='項次序',
        compute='_compute_item_sequence',
        store=True,
        index=True)

    @api.depends('item_no')
    def _compute_item_sequence(self):
        for record in self:
            match = LEADING_NUMBER.match(record.item_no or '')
            record.item_sequence = int(match.group(1)) if match else 0

    name = fields.Char(
        string='送審項目',
        required=True,
        tracking=True)

    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True)

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        domain="[('state', 'not in', ['closed', 'terminated'])]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # === 提送要求 ===
    required_timing = fields.Text(
        string='應提送時程',
        help='契約規定的提送時機，例：訂約後15日內、工程開工前')

    deadline_date = fields.Date(
        string='限定提送日期',
        tracking=True)

    # === 四組「日期＋發文文號」 ===
    # 原表把日期與文號擠在同一個儲存格用換行分開，那是排版。這裡拆成 Date + Char，
    # 日期才能排序、算逾期天數、供匯出的日期區間篩選；匯出時再組回兩行。
    first_submit_date = fields.Date(string='第一次送審日期', tracking=True)
    first_submit_doc_no = fields.Char(string='第一次送審文號')

    second_submit_date = fields.Date(string='第二次送審日期', tracking=True)
    second_submit_doc_no = fields.Char(string='第二次送審文號')

    supervisor_review_date = fields.Date(string='監造審查日期', tracking=True)
    supervisor_review_doc_no = fields.Char(string='監造審查文號')

    authority_approve_date = fields.Date(string='機關核定日期', tracking=True)
    authority_approve_doc_no = fields.Char(string='機關核定文號')

    note = fields.Text(string='備註')

    # === 處理狀態（由日期推導，不做手動按鈕） ===
    progress_status = fields.Selection([
        ('not_submitted', '未送審'),
        ('submitted', '已送審'),
        ('reviewed', '監造已審'),
        ('approved', '機關已核定'),
    ], string='處理狀態',
       compute='_compute_progress_status',
       store=True,
       index=True,
       default='not_submitted')

    @api.depends('first_submit_date', 'supervisor_review_date',
                 'authority_approve_date')
    def _compute_progress_status(self):
        """由後往前判定：核定 > 監造審查 > 送審"""
        for record in self:
            if record.authority_approve_date:
                record.progress_status = 'approved'
            elif record.supervisor_review_date:
                record.progress_status = 'reviewed'
            elif record.first_submit_date:
                record.progress_status = 'submitted'
            else:
                record.progress_status = 'not_submitted'

    delay_days = fields.Integer(
        string='送審延遲天數',
        compute='_compute_delay_days',
        store=True,
        help='第一次送審日期與限定提送日期的差異天數，正數表示延遲')

    @api.depends('deadline_date', 'first_submit_date')
    def _compute_delay_days(self):
        for record in self:
            if record.deadline_date and record.first_submit_date:
                record.delay_days = (
                    record.first_submit_date - record.deadline_date).days
            else:
                record.delay_days = 0

    # 逾期會隨「今天」變動，store 起來就會過期（除非再養一支 cron），
    # 所以不 store，改提供 search 讓篩選器與 group by 仍然可用。
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_is_overdue',
        search='_search_is_overdue',
        help='已過限定提送日期但尚未送審')

    @api.depends('deadline_date', 'first_submit_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.is_overdue = bool(
                record.deadline_date
                and not record.first_submit_date
                and record.deadline_date < today)

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError('「已逾期」只支援等於／不等於的搜尋條件')
        today = fields.Date.context_today(self)
        # operator 與 value 一起決定要找逾期的還是沒逾期的
        want_overdue = (operator == '=') == bool(value)
        if want_overdue:
            return [('deadline_date', '!=', False),
                    ('deadline_date', '<', today),
                    ('first_submit_date', '=', False)]
        # 沒逾期＝沒設限期 或 還沒到期 或 已經送審了
        return ['|', '|',
                ('deadline_date', '=', False),
                ('deadline_date', '>=', today),
                ('first_submit_date', '!=', False)]

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'plan_control_attachment_rel',
        'plan_control_id',
        'attachment_id',
        string='送審文件')

    def _attachment_default_category(self):
        """送審文件 → 12-文書資料 / 08-送審管制 / 01-計畫書

        與材料設備送審（supervision.review.application → 02-材料）分開歸檔，
        對齊實際的資料夾結構，兩邊的文件不會混在同一個分類裡。
        """
        return self.env.ref(
            'construction_supervision_base.cat_12_08_01',
            raise_if_not_found=False) or super()._attachment_default_category()

    attachment_count = fields.Integer(
        string='附件數',
        compute='_compute_attachment_count')

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.attachment_ids)

    # === 計算欄位 ===
    @api.depends('item_no', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.item_no:
                record.display_name = f'[{record.item_no}] {record.name or ""}'
            else:
                record.display_name = record.name or ''

    # === 約束 ===
    @api.constrains('item_no', 'project_id', 'control_type')
    def _check_item_no_unique(self):
        """同一工程、同一類別的項次不可重複。

        非數字的項次不擋——原表的監造計畫、監造用人計畫兩列都是 ☆，
        本來就會重複。
        """
        for record in self:
            if record.item_sequence <= 0:
                continue
            item_no = (record.item_no or '').strip()
            duplicate = self.search([
                ('id', '!=', record.id),
                ('project_id', '=', record.project_id.id),
                ('control_type', '=', record.control_type),
                ('item_no', '=', item_no),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    '本工程的「%s」已經有項次 %s（%s），項次不可重複。'
                    % (dict(self._fields['control_type'].selection).get(
                           record.control_type, record.control_type),
                       item_no, duplicate.name))

    # === 檢視動作 ===
    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '送審文件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model
    def _next_item_no(self, project_id, control_type):
        """同一工程、同一類別的下一個項次號"""
        if not project_id:
            return 1
        existing = self.search([
            ('project_id', '=', project_id),
            ('control_type', '=', control_type),
        ])
        return max(existing.mapped('item_sequence') or [0]) + 1

    @api.model_create_multi
    def create(self, vals_list):
        """項次留空時自動接號；同一批建立多筆也要依序遞增"""
        counters = {}
        for vals in vals_list:
            if str(vals.get('item_no') or '').strip():
                continue
            key = (vals.get('project_id'),
                   vals.get('control_type') or DEFAULT_CONTROL_TYPE)
            if key not in counters:
                counters[key] = self._next_item_no(*key)
            vals['item_no'] = str(counters[key])
            counters[key] += 1
        return super().create(vals_list)

    def copy(self, default=None):
        """複製用於「修正N版」：項目與時程留著，往返日期文號全部清掉。

        項次也一併清掉重新取號——原表的「整體施工計畫(修正1版)」拿的是新的項次，
        不是沿用原來那一號。
        """
        default = dict(default or {})
        default.setdefault('item_no', False)
        default.update({
            'first_submit_date': False,
            'first_submit_doc_no': False,
            'second_submit_date': False,
            'second_submit_doc_no': False,
            'supervisor_review_date': False,
            'supervisor_review_doc_no': False,
            'authority_approve_date': False,
            'authority_approve_doc_no': False,
        })
        return super().copy(default)

    # === 名稱搜尋 ===
    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                '|',
                ('item_no', operator, name),
                ('name', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)

# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ReservationNotificationSlip(models.Model):
    """
    通報單 (預約式專用)

    狀態流程: draft → not_started → in_progress → closed
    """
    _name = 'reservation.notification.slip'
    _description = '通報單 (預約式專用)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'slip_no desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='通報單名稱',
        compute='_compute_name', store=True, readonly=False)

    slip_number = fields.Char(
        string='通報單編號', required=True, copy=False, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('reservation.notification.slip') or '/')

    project_id = fields.Many2one(
        'project.project', string='所屬工程', required=True,
        domain=[('project_type', '=', 'reservation')],
        tracking=True,
        help='僅可選擇預約式工程')

    slip_no = fields.Integer(
        string='通報單次', required=True, default=1,
        help='本工程的第幾次通報單')

    # === 編製資訊 ===
    compiler_id = fields.Many2one(
        'res.users', string='編製人員',
        default=lambda self: self.env.uid,
        tracking=True)

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='project_id.company_id', store=True)

    location = fields.Char(
        string='工程地點', required=True,
        help='本次通報單的施工地點')

    location_detail = fields.Text(
        string='詳細位置說明')

    # 通報單的施工地點座標。用途有二：
    # (1) 本通報單的照片若沒有 GPS EXIF，會沿用這組座標（見
    #     construction_portal/controllers/portal_photo.py 的通報單照片上傳），
    #     現場人員因此不必為每張照片手填座標；
    # (2) 通報單本身即代表工區內的一個特定地點，比工程案件的中心點精確。
    # 未填時是 0.0（等同未填），constrains 會放行 —— 與 supervision.photo /
    # project.project 的處理一致。
    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))

    @api.constrains('latitude', 'longitude')
    def _check_slip_coordinates(self):
        """座標範圍檢查（0 視為未填直接放行）。

        沒有這道關卡的話，填錯的座標（例如經緯度顛倒，緯度填成 121.5）會被
        照片繼承機制原樣複製到每一張通報單照片上，地圖整批跑到錯誤位置。
        """
        for rec in self:
            if rec.latitude and not -90 <= rec.latitude <= 90:
                raise ValidationError('緯度必須在 -90 到 90 之間！')
            if rec.longitude and not -180 <= rec.longitude <= 180:
                raise ValidationError('經度必須在 -180 到 180 之間！')

    # === 日期與工期 ===
    survey_date = fields.Date(
        string='工程會勘日期',
        help='現場會勘日期')

    planned_start_date = fields.Date(
        string='預定開工日期', tracking=True)

    planned_end_date = fields.Date(
        string='預定完工日期',
        compute='_compute_planned_end_date', store=True, readonly=False)

    planned_duration = fields.Integer(
        string='預定工期(日曆天)',
        help='預定施工天數')

    actual_start_date = fields.Date(
        string='實際開工日期', tracking=True)

    actual_end_date = fields.Date(
        string='實際竣工日期', tracking=True)

    actual_duration = fields.Integer(
        string='實際使用工期',
        compute='_compute_actual_duration', store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue_days', store=True)

    overdue_display = fields.Char(
        string='逾期狀態',
        compute='_compute_overdue_display')

    # === 預算與結算 ===
    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='project_id.currency_id', store=True)

    estimated_amount = fields.Monetary(
        string='預估金額 (預算)',
        currency_field='currency_id',
        tracking=True,
        help='本通報單的預算金額，參考工程範疇量預估')

    settlement_amount = fields.Monetary(
        string='結算金額 (實際)',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='本通報單的實際結算金額，由明細彙總')

    budget_variance = fields.Monetary(
        string='預算差異',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='settlement_amount - estimated_amount')

    budget_variance_rate = fields.Float(
        string='差異率 (%)',
        compute='_compute_settlement_amount', store=True,
        digits=(5, 2),
        help='(settlement_amount / estimated_amount - 1) x 100')

    # === 設計與施工概述 ===
    design_summary = fields.Text(
        string='設計概述',
        help='本通報單施工內容概述')

    completion_summary = fields.Text(
        string='完工概述',
        help='竣工時的施工成果說明')

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('not_started', '未開始'),
        ('in_progress', '施工中'),
        ('closed', '已結案'),
    ], string='施作狀態', default='draft', tracking=True, index=True,
       help='通報單生命週期: draft → not_started → in_progress → closed')

    # === 估驗計價次數（佔位欄位，由 construction_payment 覆寫為 compute） ===
    # 2026-08-18 改為工程層級：估驗計價以「工程 × 期別」為單位辦理，不歸屬於個別通報單。
    valuation_count = fields.Integer(
        string='本工程已估驗次數', default=0, readonly=True,
        help='本張通報單所屬工程已辦理的估驗計價期數。'
             '本單自身的金額請看「結算金額」。')

    # === 明細關聯 ===
    detail_line_ids = fields.One2many(
        'reservation.notification.slip.line', 'slip_id',
        string='詳細表項目')

    line_count = fields.Integer(
        string='項目數量',
        compute='_compute_line_count')

    # === 備註 ===
    notes = fields.Html(string='備註說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('slip_number_unique', 'UNIQUE(slip_number)', '通報單編號必須唯一！'),
        ('project_slip_no_unique', 'UNIQUE(project_id, slip_no)',
         '同一工程的通報單次不可重複！'),
        ('planned_dates_check',
         'CHECK(planned_end_date IS NULL OR planned_start_date IS NULL OR planned_end_date >= planned_start_date)',
         '預定完工日必須晚於或等於開工日！'),
    ]

    # === 計算方法 ===
    @api.depends('slip_no', 'location')
    def _compute_name(self):
        for rec in self:
            location_str = rec.location or ''
            rec.name = f'第{rec.slip_no}次通報單 - {location_str}'

    @api.depends('planned_start_date', 'planned_duration')
    def _compute_planned_end_date(self):
        for rec in self:
            if rec.planned_start_date and rec.planned_duration:
                rec.planned_end_date = rec.planned_start_date + timedelta(days=rec.planned_duration - 1)
            elif not rec.planned_end_date:
                rec.planned_end_date = False

    @api.depends('actual_start_date', 'actual_end_date')
    def _compute_actual_duration(self):
        for rec in self:
            if rec.actual_start_date and rec.actual_end_date:
                delta = rec.actual_end_date - rec.actual_start_date
                rec.actual_duration = delta.days + 1
            else:
                rec.actual_duration = 0

    @api.depends('planned_end_date', 'actual_end_date')
    def _compute_overdue_days(self):
        for rec in self:
            if rec.planned_end_date and rec.actual_end_date:
                delta = rec.actual_end_date - rec.planned_end_date
                rec.overdue_days = max(0, delta.days)
            else:
                rec.overdue_days = 0

    @api.depends('overdue_days', 'planned_end_date', 'actual_end_date')
    def _compute_overdue_display(self):
        for rec in self:
            if rec.overdue_days > 0:
                rec.overdue_display = f'逾期 {rec.overdue_days} 天'
            else:
                rec.overdue_display = '未逾期'

    @api.depends('detail_line_ids.actual_amount')
    def _compute_settlement_amount(self):
        for slip in self:
            slip.settlement_amount = sum(slip.detail_line_ids.mapped('actual_amount'))
            slip.budget_variance = slip.settlement_amount - slip.estimated_amount
            if slip.estimated_amount:
                slip.budget_variance_rate = ((slip.settlement_amount / slip.estimated_amount) - 1) * 100
            else:
                slip.budget_variance_rate = 0.0

    @api.depends('detail_line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.detail_line_ids)

    # === onchange 方法 ===
    @api.onchange('project_id')
    def _onchange_project_id(self):
        """計算下一個通報單次數"""
        if self.project_id:
            existing = self.search([
                ('project_id', '=', self.project_id.id)
            ], order='slip_no desc', limit=1)
            self.slip_no = (existing.slip_no + 1) if existing else 1

    @api.onchange('planned_duration')
    def _onchange_planned_duration(self):
        """更新預定完工日"""
        if self.planned_start_date and self.planned_duration:
            self.planned_end_date = self.planned_start_date + timedelta(days=self.planned_duration - 1)

    # === 約束驗證 ===
    @api.constrains('actual_start_date', 'actual_end_date')
    def _check_actual_dates(self):
        for rec in self:
            if rec.actual_start_date and rec.actual_end_date:
                if rec.actual_end_date < rec.actual_start_date:
                    raise ValidationError('實際竣工日必須晚於或等於實際開工日')

    @api.constrains('project_id')
    def _check_project_type(self):
        for rec in self:
            if rec.project_id and rec.project_id.project_type != 'reservation':
                raise ValidationError('通報單僅適用於預約式工程')

    # === 狀態動作方法 ===
    def action_confirm(self):
        """確認通報單: draft → not_started"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態可以確認')
            if not rec.detail_line_ids:
                raise ValidationError('請先填寫詳細表項目')
            rec.write({'state': 'not_started'})
            site_manager = rec.project_id.site_manager_id
            if site_manager:
                partner = site_manager.partner_id
                rec.message_subscribe(partner_ids=partner.ids)
                rec.message_post(
                    body=(
                        f'通報單 <b>{rec.slip_number}</b> 已確認，'
                        f'預定開工：{rec.planned_start_date or "未設定"}，'
                        f'地點：{rec.location}。'
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_start(self):
        """開始施工: not_started → in_progress"""
        for rec in self:
            if rec.state != 'not_started':
                raise UserError('只有未開始狀態可以開始施工')
            vals = {'state': 'in_progress'}
            if not rec.actual_start_date:
                vals['actual_start_date'] = fields.Date.today()
            rec.write(vals)

    def action_close(self):
        """結案: in_progress → closed"""
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError('只有施工中狀態可以結案')
            # 驗證：施工詳細表的實際數量與金額不能全為 0
            total_actual_qty = sum(rec.detail_line_ids.mapped('actual_qty'))
            total_actual_amount = sum(rec.detail_line_ids.mapped('actual_amount'))
            if total_actual_qty == 0 and total_actual_amount == 0:
                raise UserError(
                    '施工詳細表中尚未填寫任何實際完成數量或實際金額，無法結案。\n'
                    '請至「施工詳細表」頁籤填寫實際完成資料。'
                )
            vals = {'state': 'closed'}
            if not rec.actual_end_date:
                vals['actual_end_date'] = fields.Date.today()
            rec.write(vals)

    def action_return_to_draft(self):
        """退回草稿: not_started/in_progress → draft"""
        for rec in self:
            if rec.state not in ('not_started', 'in_progress'):
                raise UserError('只有未開始或施工中狀態可以退回草稿')
            rec.write({'state': 'draft'})

    # === Wizard 動作 ===
    def action_open_add_lines_wizard(self):
        """開啟加入工項 Wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '加入工項',
            'res_model': 'add.slip.line.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_slip_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('slip_number', '/') == '/':
                vals['slip_number'] = self.env['ir.sequence'].next_by_code(
                    'reservation.notification.slip') or '/'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態的通報單可以刪除')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'slip_number': self.env['ir.sequence'].next_by_code('reservation.notification.slip') or '/',
            'state': 'draft',
            'actual_start_date': False,
            'actual_end_date': False,
        })
        # 計算新的 slip_no
        if self.project_id:
            existing = self.search([
                ('project_id', '=', self.project_id.id)
            ], order='slip_no desc', limit=1)
            default['slip_no'] = (existing.slip_no + 1) if existing else 1
        return super().copy(default)

    def name_get(self):
        result = []
        for rec in self:
            name = f'[{rec.slip_number}] {rec.name}'
            result.append((rec.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', '|',
                      ('slip_number', operator, name),
                      ('name', operator, name),
                      ('location', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # === 關聯照片（反向 from supervision.photo.source_id） ===
    # 照片資料表收斂前這裡是 computed Many2many（靠 source_model/source_id 字串
    # 反查），唯讀 → 後台有頁籤卻**沒有任何上傳入口**（與檢試驗同樣的問題）。
    # 改成真 One2many 之後後台可直接掛上傳。
    related_photo_ids = fields.One2many(
        'supervision.photo',
        'slip_id',
        string='關聯照片',
        help='此通報單的照片')

    related_photo_count = fields.Integer(
        string='照片數',
        compute='_compute_related_photo_count')

    @api.depends('related_photo_ids')
    def _compute_related_photo_count(self):
        for rec in self:
            rec.related_photo_count = len(rec.related_photo_ids)

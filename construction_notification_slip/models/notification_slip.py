# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


#: 退單後仍可寫入的欄位（解除退單會動到的欄位）。其餘一律擋下，見 write()。
CANCEL_WRITABLE_FIELDS = {
    'state', 'state_before_cancel', 'cancel_reason', 'cancel_date',
    'cancel_note', 'merged_into_slip_id',
}
#: chatter / 前台分享 token 等系統自動寫入的欄位前綴，不屬於「通報單內容」
CANCEL_WRITABLE_PREFIXES = ('message_', 'activity_', 'access_')


class ReservationNotificationSlip(models.Model):
    """
    通報單 (預約式專用)

    狀態流程: draft → not_started → in_progress → closed
              in_progress ⇄ suspended（停工／復工），suspended → closed
              draft／not_started／in_progress／suspended → cancelled（退單）
              cancelled → 退單前的狀態（解除退單）

    退單（cancelled）：通報單作廢但編號保留、全表唯讀、不可刪除。
    同一個通報單次可以在退單後重新開立（真實案例：西區 111-16 第 7 通
    「工項價格有問題，退單。」之後以同一個「排序 7」重開），所以唯一鍵
    只約束「未退單」的通報單，見 _sql_constraints 與 init()。
    停工（suspended）：停工天數＝Σ（復工日 − 停工日），從逾期天數扣除
    （北搶 111-19 第 12、36 通的預定竣工日與逾期天數逐日吻合此算法）。
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

    # aggregator=False：這是「第幾次」的序號，不是可加總的量。
    # 沒有這行的話，Odoo 對 Integer 預設 aggregator='sum'，清單依工程分組時
    # 群組列會把 1+2+...+82 加起來顯示成 3,367 次（實際只開立 82 次）。
    slip_no = fields.Integer(
        string='通報單次', required=True, default=1,
        aggregator=False,
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

    # 停工天數由停工紀錄自動算；工期檢討核定的免計／展延天數另外手填。
    # 兩者都把「該完工的日子」往後推，逾期天數以調整後的日期判斷。
    suspension_ids = fields.One2many(
        'reservation.notification.slip.suspension', 'slip_id',
        string='停工紀錄')

    suspended_days = fields.Integer(
        string='停工天數',
        compute='_compute_suspended_days', store=True,
        help='已復工的停工期間合計（每段＝復工日 − 停工日），從逾期天數扣除。'
             '仍在停工中的那一段要等復工後才計入。')

    schedule_review_days = fields.Integer(
        string='工期檢討增加天數',
        tracking=True,
        help='工期檢討核定的免計工期與展延天數合計（與停工無關的部分）。'
             '例：「提送工期檢討 免計20日」填 20；「免計2天展延4天」填 6。')

    adjusted_planned_end_date = fields.Date(
        string='調整後預定完工日',
        compute='_compute_adjusted_planned_end_date', store=True,
        help='預定完工日 ＋ 停工天數 ＋ 工期檢討增加天數。逾期天數以這一天判斷。')

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue_days', store=True,
        help='實際竣工日 − 調整後預定完工日（不為負）')

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
        help='本通報單的實際結算金額，由明細的「根列」彙總'
             '（詳細表是契約工項樹的子樹，小計列不重複計入）')

    planned_total_amount = fields.Monetary(
        string='明細預估合計',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='詳細表根列的預估金額加總，與「結算金額」對稱。'
             '拿來跟手填的「預估金額 (預算)」對照，明細沒填完就看得出來。')

    estimated_variance = fields.Monetary(
        string='預估落差',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='明細預估合計 − 預估金額(預算)')

    has_estimated_mismatch = fields.Boolean(
        string='預估金額與明細不符',
        compute='_compute_settlement_amount', store=True)

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
        ('suspended', '停工'),
        ('closed', '已結案'),
        ('cancelled', '退單'),
    ], string='施作狀態', default='draft', tracking=True, index=True,
       help='通報單生命週期: draft → not_started → in_progress → closed；'
            '施工中可停工／復工；結案以外的狀態都可退單（＝作廢，編號保留）')

    # === 退單 ===
    state_before_cancel = fields.Selection([
        ('draft', '草稿'),
        ('not_started', '未開始'),
        ('in_progress', '施工中'),
        ('suspended', '停工'),
    ], string='退單前狀態', copy=False, readonly=True,
       help='解除退單時回到這個狀態')

    cancel_reason = fields.Selection([
        ('return', '退單'),
        ('merge', '合併'),
        ('other', '其他'),
    ], string='退單原因', copy=False, tracking=True)

    cancel_date = fields.Date(string='退單日期', copy=False, tracking=True)

    cancel_note = fields.Text(string='退單說明', copy=False)

    merged_into_slip_id = fields.Many2one(
        'reservation.notification.slip', string='併入的通報單',
        copy=False, tracking=True, index=True, ondelete='restrict',
        domain="[('project_id', '=', project_id), ('id', '!=', id), ('state', '!=', 'cancelled')]",
        help='退單原因為「合併」時，本單的工作併入哪一張通報單')

    merged_slip_ids = fields.One2many(
        'reservation.notification.slip', 'merged_into_slip_id',
        string='併入本單的通報單')

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
    # 同一工程的通報單次只約束「未退單」的通報單：退單後可以用同一個次數重開。
    # SQL 的 UNIQUE 約束不能帶 WHERE，所以定義留空（＝由自訂索引實作，見 init()），
    # Odoo 仍會用這裡的訊息把違反時的 IntegrityError 轉成看得懂的錯誤。
    # 舊的 project_slip_no_unique 由 migrations/18.0.3.0.0/pre-migrate.py 移除。
    _sql_constraints = [
        ('slip_number_unique', 'UNIQUE(slip_number)', '通報單編號必須唯一！'),
        ('project_slip_no_active_unique', '',
         '同一工程的通報單次不可重複（已退單的通報單不算）！'),
        ('planned_dates_check',
         'CHECK(planned_end_date IS NULL OR planned_start_date IS NULL OR planned_end_date >= planned_start_date)',
         '預定完工日必須晚於或等於開工日！'),
    ]

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                reservation_notification_slip_project_slip_no_active_unique
            ON reservation_notification_slip (project_id, slip_no)
            WHERE state <> 'cancelled'
        """)

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

    @api.depends('suspension_ids.days')
    def _compute_suspended_days(self):
        for rec in self:
            rec.suspended_days = sum(rec.suspension_ids.mapped('days'))

    @api.depends('planned_end_date', 'suspended_days', 'schedule_review_days')
    def _compute_adjusted_planned_end_date(self):
        for rec in self:
            if rec.planned_end_date:
                rec.adjusted_planned_end_date = rec.planned_end_date + timedelta(
                    days=(rec.suspended_days or 0) + (rec.schedule_review_days or 0))
            else:
                rec.adjusted_planned_end_date = False

    @api.depends('adjusted_planned_end_date', 'actual_end_date')
    def _compute_overdue_days(self):
        """逾期天數＝實際竣工日 − 調整後預定完工日（停工與工期檢討天數已順延）。

        實例（北搶 111-19 第 36 通）：預定竣工 8/29，8/19 停工、9/11 復工（23 天）
        → 調整後 9/21；實際竣工 9/27 → 逾期 6 天，與監造管理表相符。
        """
        for rec in self:
            if rec.adjusted_planned_end_date and rec.actual_end_date:
                delta = rec.actual_end_date - rec.adjusted_planned_end_date
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

    @api.depends('detail_line_ids.actual_amount',
                 'detail_line_ids.planned_amount',
                 'detail_line_ids.parent_line_id',
                 'estimated_amount')
    def _compute_settlement_amount(self):
        """結算/預估合計只加總「根列」（本單內沒有父列的列）。

        詳細表是契約工項樹的一個完整子樹，「壹 發包工程費」「一 工程費」這種
        小計列的金額本來就等於底下各列的和；全部加起來會重複計算。
        以第1次通報單為例：21 列全加是 719,990，正確答案是根列「壹」的 274,673。
        """
        for slip in self:
            roots = slip.detail_line_ids.filtered(lambda l: not l.parent_line_id)
            slip.settlement_amount = sum(roots.mapped('actual_amount'))
            slip.planned_total_amount = sum(roots.mapped('planned_amount'))

            slip.estimated_variance = (
                slip.planned_total_amount - slip.estimated_amount)
            # 1 元以內視為相符（金額多為兩位小數的加總）
            slip.has_estimated_mismatch = bool(
                slip.estimated_amount and abs(slip.estimated_variance) > 1)

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

    @api.constrains('state', 'cancel_reason', 'merged_into_slip_id', 'cancel_note')
    def _check_cancel_fields(self):
        """退單欄位只在退單狀態有意義；合併一定要指出併入哪一張。"""
        for rec in self:
            if rec.state == 'cancelled':
                if not rec.cancel_reason:
                    raise ValidationError('退單必須填寫退單原因')
                if rec.cancel_reason == 'merge' and not rec.merged_into_slip_id:
                    raise ValidationError('退單原因為「合併」時，必須選擇併入的通報單')
                if rec.cancel_reason == 'other' and not (rec.cancel_note or '').strip():
                    raise ValidationError('退單原因為「其他」時，必須填寫退單說明')
            elif rec.cancel_reason or rec.merged_into_slip_id:
                raise ValidationError('只有退單狀態的通報單可以有退單原因／併入的通報單')
            target = rec.merged_into_slip_id
            if target:
                if target == rec:
                    raise ValidationError('不能把通報單併入它自己')
                if target.project_id != rec.project_id:
                    raise ValidationError('只能併入同一工程的通報單')

    @api.constrains('state', 'state_before_cancel', 'suspension_ids')
    def _check_suspension_state(self):
        for rec in self:
            rec._check_suspension_consistency()

    def _check_suspension_consistency(self):
        """「有沒有未復工的停工紀錄」必須與狀態一致。

        停工 ⇔ 恰好一筆未復工的紀錄；從停工退單時那一筆保持未復工
        （解除退單會回到停工，資料才接得上）。停工紀錄本身被修改時
        （復工日清空等）也會呼叫這裡，見 suspension 模型的約束。
        """
        self.ensure_one()
        open_lines = self.suspension_ids.filtered(lambda s: not s.resume_date)
        if len(open_lines) > 1:
            raise ValidationError(
                f'{self.name}：同時有 {len(open_lines)} 筆未填復工日的停工紀錄，最多只能有一筆')
        was_suspended = (self.state == 'cancelled'
                         and self.state_before_cancel == 'suspended')
        if self.state == 'suspended' and not open_lines:
            raise ValidationError(f'{self.name}：停工狀態必須有一筆未填復工日的停工紀錄')
        if open_lines and self.state != 'suspended' and not was_suspended:
            raise ValidationError(
                f'{self.name}：有未填復工日的停工紀錄（停工日 {open_lines.suspend_date}），'
                '但通報單不是停工狀態。請填上復工日。')

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
        """結案: in_progress / suspended → closed

        從停工直接結案（停工後只結算已完成部分、不再復工）時，
        那一筆未復工的停工紀錄以實際竣工日收尾。
        """
        for rec in self:
            if rec.state not in ('in_progress', 'suspended'):
                raise UserError('只有施工中或停工狀態可以結案')
            # 驗證：施工詳細表的實際數量與金額不能全為 0
            total_actual_qty = sum(rec.detail_line_ids.mapped('actual_qty'))
            total_actual_amount = sum(rec.detail_line_ids.mapped('actual_amount'))
            if total_actual_qty == 0 and total_actual_amount == 0:
                raise UserError(
                    '施工詳細表中尚未填寫任何實際完成數量或實際金額，無法結案。\n'
                    '請至「施工詳細表」頁籤填寫實際完成資料。'
                )
            vals = {'state': 'closed'}
            end_date = rec.actual_end_date or fields.Date.context_today(rec)
            if not rec.actual_end_date:
                vals['actual_end_date'] = end_date
            open_line = rec.suspension_ids.filtered(lambda s: not s.resume_date)
            if open_line:
                if end_date < open_line.suspend_date:
                    raise UserError(
                        f'實際竣工日 {end_date} 早於停工日 {open_line.suspend_date}，'
                        '請先更正實際竣工日或停工紀錄')
                vals['suspension_ids'] = [Command.update(open_line.id, {
                    'resume_date': end_date,
                    'note': '停工後直接結案，以實際竣工日收尾',
                })]
            rec.write(vals)

    def action_return_to_draft(self):
        """退回草稿: not_started/in_progress → draft（停工中請先復工）"""
        for rec in self:
            if rec.state not in ('not_started', 'in_progress'):
                raise UserError('只有未開始或施工中狀態可以退回草稿')
            rec.write({'state': 'draft'})

    # --- 停工／復工 ---
    # 按鈕開精靈；真正的動作是下面帶參數的方法，精靈與匯入工具（RPC）共用同一份邏輯。
    def _open_state_wizard(self, mode, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'reservation.notification.slip.state.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_slip_id': self.id, 'default_mode': mode},
        }

    def action_open_suspend_wizard(self):
        return self._open_state_wizard('suspend', '停工')

    def action_open_resume_wizard(self):
        return self._open_state_wizard('resume', '復工')

    def action_open_cancel_wizard(self):
        return self._open_state_wizard('cancel', '退單')

    def action_suspend(self, suspend_date=None, reason=None):
        """停工: in_progress → suspended，新增一筆未復工的停工紀錄。"""
        reason = (reason or '').strip()
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError('只有施工中的通報單可以停工')
            if not reason:
                raise UserError('請填寫停工原因')
            day = fields.Date.to_date(suspend_date) or fields.Date.context_today(rec)
            rec.write({
                'state': 'suspended',
                'suspension_ids': [Command.create({
                    'suspend_date': day, 'reason': reason})],
            })
        return True

    def action_resume(self, resume_date=None):
        """復工: suspended → in_progress，補上停工紀錄的復工日。"""
        for rec in self:
            if rec.state != 'suspended':
                raise UserError('只有停工狀態的通報單可以復工')
            open_line = rec.suspension_ids.filtered(lambda s: not s.resume_date)
            if not open_line:
                raise UserError('找不到未復工的停工紀錄')
            day = fields.Date.to_date(resume_date) or fields.Date.context_today(rec)
            # 狀態與復工日要在同一次 write 裡改：分兩次寫，中間那一刻
            # 「停工狀態卻沒有未復工紀錄」會被一致性約束擋下。
            rec.write({
                'state': 'in_progress',
                'suspension_ids': [Command.update(open_line.id, {'resume_date': day})],
            })
        return True

    # --- 退單／解除退單 ---
    def _cancel_blockers(self):
        """回傳擋下退單的原因（空字串＝可以退單）。"""
        self.ensure_one()
        if self.state == 'closed':
            return '已結案的通報單不可退單'
        if self.state == 'cancelled':
            return '本通報單已是退單狀態'
        done = self.detail_line_ids.filtered(lambda l: l.actual_qty or l.actual_amount)
        if done:
            items = '、'.join(done[:5].mapped(lambda l: l.display_item_no or l.item_no or ''))
            return (f'本單已有實作數量（{items}{" 等" if len(done) > 5 else ""}，共 {len(done)} 列），'
                    '不能退單。\n請改走「結案」結算已完成的部分；'
                    '若是要併到別一通，請先把實作數量移到那一通。')
        return ''

    def action_cancel_slip(self, cancel_reason=None, cancel_date=None,
                           cancel_note=None, merged_into_slip_id=None):
        """退單（作廢）: draft/not_started/in_progress/suspended → cancelled。

        編號保留、全表唯讀、不可刪除；可用「解除退單」回到原狀態。
        從停工退單時，未復工的停工紀錄保持原樣，解除退單後仍是停工。
        """
        reasons = dict(self._fields['cancel_reason'].selection)
        if cancel_reason not in reasons:
            raise UserError('請選擇退單原因（退單／合併／其他）')
        if isinstance(merged_into_slip_id, models.BaseModel):
            merged_into_slip_id = merged_into_slip_id.id
        target = self.browse(merged_into_slip_id or [])
        note = (cancel_note or '').strip()
        for rec in self:
            blocker = rec._cancel_blockers()
            if blocker:
                raise UserError(blocker)
            if cancel_reason == 'merge':
                if not target:
                    raise UserError('退單原因為「合併」時，必須選擇併入的通報單')
                if target.state == 'cancelled':
                    raise UserError(f'{target.name} 已退單，不能併入已退單的通報單')
            vals = {
                'state': 'cancelled',
                'state_before_cancel': rec.state,
                'cancel_reason': cancel_reason,
                'cancel_date': fields.Date.to_date(cancel_date) or fields.Date.context_today(rec),
                'cancel_note': note or False,
                'merged_into_slip_id': target.id if cancel_reason == 'merge' else False,
            }
            rec.write(vals)
            summary = f'通報單已退單（{reasons[cancel_reason]}）'
            if cancel_reason == 'merge':
                summary += f'，併入 {target.name}'
                target.message_post(body=f'{rec.name} 已退單併入本單', subtype_xmlid='mail.mt_note')
            rec.message_post(body=summary + (f'：{note}' if note else ''),
                             subtype_xmlid='mail.mt_note')
        return True

    def action_uncancel(self):
        """解除退單: cancelled → 退單前的狀態。"""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError('只有退單狀態的通報單可以解除退單')
            dup = self.search([
                ('id', '!=', rec.id),
                ('project_id', '=', rec.project_id.id),
                ('slip_no', '=', rec.slip_no),
                ('state', '!=', 'cancelled'),
            ], limit=1)
            if dup:
                raise UserError(
                    f'本工程已重新開立第 {rec.slip_no} 次通報單（{dup.slip_number}），'
                    '同一個通報單次不能同時有兩張未退單的通報單，因此無法解除退單。')
            back = rec.state_before_cancel or 'draft'
            rec.write({
                'state': back,
                'state_before_cancel': False,
                'cancel_reason': False,
                'cancel_date': False,
                'cancel_note': False,
                'merged_into_slip_id': False,
            })
            label = dict(self._fields['state'].selection)[back]
            rec.message_post(body=f'已解除退單，回到「{label}」', subtype_xmlid='mail.mt_note')
        return True

    @api.onchange('detail_line_ids')
    def _onchange_detail_line_ids(self):
        """新增／刪除明細列時，讓上層小計在畫面上「立刻」反應，不必先存檔。

        parent_line_id / planned_amount / actual_amount 都是 compute + store，
        依賴鏈跨越同一個 one2many 裡「別的列」——網頁端不會自己重算。
        使用者刪掉「6 側溝清疏」之後，父列「一」還停在舊金額，
        很容易被誤以為沒反應而重複刪除、重新加入。這裡在 onchange 內用記憶體
        資料重算一次，讓畫面與存檔後的結果一致。

        ⚠️ 手填列（無子列的彙總項／稅什費類）**不可以**在這裡無條件歸零 ——
        使用者在別列打字也會觸發本 onchange，那樣會把手填金額一直清掉。
        只有「原本在資料庫裡有子列、現在記憶體裡沒有了」才歸零，
        對應 unlink() 存檔後的實際行為。
        """
        lines = self.detail_line_ids
        if not lines:
            return

        # 1) 用記憶體中的列重建父子關係（task 階層 → 本單內的列）
        by_task = {}
        for line in lines:
            if line.task_id and line.task_id.id not in by_task:
                by_task[line.task_id.id] = line
        children = {}
        for line in lines:
            parent_task = line.task_id.parent_id
            parent = by_task.get(parent_task.id) if parent_task else False
            line.parent_line_id = parent or False
            if parent:
                children.setdefault(parent, self.env[line._name])
                children[parent] |= line

        # 2) 由深往淺重算（子列先算完，父列才加得到）
        for line in sorted(lines, key=lambda l: l.task_id.item_level or 0, reverse=True):
            kids = children.get(line, False)
            # is_manual_amount 控制畫面上金額欄能不能打字。它是非儲存 compute，
            # 在 onchange 的記憶體情境下不保證即時重算，這裡一併明確指定，
            # 讓「可不可以填」與上面算出來的金額永遠一致。
            # （即使這裡判斷錯，存檔時 write() 仍會以真實資料為準把值導回 compute，
            #   資料不會壞，只是欄位一時可編輯而已。）
            line.is_manual_amount = bool(
                not kids and (line.is_summary_line or line.task_id.tax_misc_rate
                              or not line.unit_price))
            if kids:
                line.planned_amount = sum(kids.mapped('planned_amount'))
                line.actual_amount = sum(kids.mapped('actual_amount'))
            elif (line.is_summary_line or line.task_id.tax_misc_rate
                    or not line.unit_price):
                # 手填列：只有「剛剛失去所有子列」才歸零，其餘一律不動
                origin = line._origin
                if origin and origin.child_line_ids:
                    line.planned_amount = 0.0
                    line.actual_amount = 0.0
            else:
                line.planned_amount = line.planned_qty * line.unit_price
                line.actual_amount = line.actual_qty * line.unit_price

    # === 詳細表樹補齊（供匯入 RPC 呼叫）===
    def _complete_ancestor_lines(self):
        """補齊詳細表缺少的祖先彙總項列，回傳新增的列數。

        詳細表必須是契約工項樹的一個完整子樹，結算金額才能「只加總根列」而不
        重複計入小計。後台「加入工項」精靈在建立當下就補好了；匯入是用
        detail_line_ids 一次塞進來的，需要事後補一次。
        兩邊共用 slip.line._create_lines_for_tasks，不另寫一份補樹邏輯。
        """
        Line = self.env['reservation.notification.slip.line']
        added = 0
        for slip in self:
            tasks = slip.detail_line_ids.mapped('task_id')
            if tasks:
                added += len(Line._create_lines_for_tasks(slip, tasks))
        return added

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
        # 部分唯一索引看的是資料庫裡的 state：同一交易內剛退單（還在快取、
        # 尚未寫進資料庫）的舊單，INSERT 重開的同次通報單時會被誤判為重複。
        self.flush_model(['state', 'project_id', 'slip_no'])
        return super().create(vals_list)

    def write(self, vals):
        """退單後唯讀：只放行「解除退單」會動到的欄位與 chatter 等系統欄位。

        只靠畫面上的 readonly 擋不住 RPC／匯入／其他模組的程式寫入，
        所以權威放在這裡（明細列與停工紀錄另有同樣的守門）。
        """
        if any(rec.state == 'cancelled' for rec in self):
            blocked = [k for k in vals
                       if k not in CANCEL_WRITABLE_FIELDS
                       and not k.startswith(CANCEL_WRITABLE_PREFIXES)]
            if blocked:
                names = '、'.join(self._fields[k].string for k in blocked if k in self._fields)
                raise UserError(f'已退單的通報單不可修改（{names}）。如需修改請先「解除退單」。')
        return super().write(vals)

    def _check_not_cancelled_for_children(self, what):
        """明細列／停工紀錄等子表的寫入守門（退單後唯讀的另一半）。"""
        cancelled = self.filtered(lambda r: r.state == 'cancelled')
        if cancelled:
            raise UserError(
                f'{cancelled[0].name} 已退單，不可修改{what}。如需修改請先「解除退單」。')

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態的通報單可以刪除'
                                + ('（已退單的通報單保留編號，不可刪除）'
                                   if rec.state == 'cancelled' else ''))
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'slip_number': self.env['ir.sequence'].next_by_code('reservation.notification.slip') or '/',
            'state': 'draft',
            'actual_start_date': False,
            'actual_end_date': False,
            'schedule_review_days': 0,
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

    @api.depends('name', 'state')
    def _compute_display_name(self):
        """退單的通報單在任何下拉／關聯欄位上都標「（已退單）」。

        舊的自主檢查、缺失改善、日誌若掛在已退單的通報單上，一眼看得出來。
        （Odoo 18 已不呼叫上面的 name_get，顯示名稱走這裡。）
        """
        super()._compute_display_name()
        for rec in self:
            if rec.state == 'cancelled':
                rec.display_name = f'{rec.display_name}（已退單）'

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

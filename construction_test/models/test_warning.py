# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class TestWarning(models.Model):
    """
    檢試驗預警通知

    當施工日誌的累計完成數量達到檢驗頻率條件的 95% 時，
    系統自動建立預警記錄，提醒使用者即將需要進行檢驗。

    設計供前台 (Portal) 開發人員串接：
    - get_pending_warnings(): 取得未處理預警
    - get_warning_summary(): 取得預警摘要統計
    - action_mark_done(): 標記已處理
    - action_dismiss(): 標記已忽略
    """
    _name = 'supervision.test.warning'
    _description = '檢試驗預警通知'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # === 預警類型 ===
    warning_type = fields.Selection([
        ('frequency', '頻率預警'),
        ('completion', '完工提醒'),
    ], string='預警類型', default='frequency', required=True, index=True,
       help='頻率預警：累計數量接近檢驗門檻；完工提醒：累計數量達契約數量95%')

    # === 基本關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True)

    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        ondelete='cascade',
        index=True,
        help='頻率預警必填，完工提醒可為空')

    task_id = fields.Many2one(
        'project.task',
        string='契約工項',
        required=True,
        ondelete='cascade',
        index=True)

    condition_id = fields.Many2one(
        'supervision.test.frequency.condition',
        string='觸發條件',
        ondelete='set null',
        help='觸發此預警的頻率條件')

    # === 觸發來源 ===
    trigger_log_line_id = fields.Many2one(
        'daily.log.line',
        string='觸發日誌明細',
        readonly=True,
        ondelete='set null',
        help='觸發此預警的施工日誌明細')

    # === 數量資訊 ===
    current_cumulative_qty = fields.Float(
        string='當前累計數量',
        digits=(16, 4),
        readonly=True,
        help='預警當下的累計完成數量')

    next_threshold_qty = fields.Float(
        string='下一個檢驗門檻',
        digits=(16, 4),
        readonly=True,
        help='下一個需要檢驗的數量門檻')

    achievement_rate = fields.Float(
        string='達成率 (%)',
        digits=(5, 2),
        compute='_compute_achievement_rate',
        store=True,
        help='當前累計數量 / 下一個檢驗門檻 × 100')

    # === 條件摘要（related，方便顯示）===
    condition_summary = fields.Char(
        string='條件摘要',
        related='condition_id.condition_summary',
        readonly=True)

    standard_material = fields.Char(
        string='試驗工項',
        related='standard_id.material',
        readonly=True)

    task_name = fields.Char(
        string='工項名稱',
        related='task_id.name',
        readonly=True)

    # === 日期 ===
    warning_date = fields.Date(
        string='預警日期',
        required=True,
        default=fields.Date.context_today,
        readonly=True,
        index=True)

    # === 狀態管理 ===
    state = fields.Selection([
        ('pending', '未處理'),
        ('done', '已處理'),
        ('dismissed', '已忽略'),
    ], string='狀態',
       default='pending',
       required=True,
       tracking=True,
       index=True)

    # === 處理資訊 ===
    handled_by_id = fields.Many2one(
        'res.users',
        string='處理人',
        readonly=True,
        tracking=True)

    handled_date = fields.Datetime(
        string='處理時間',
        readonly=True)

    note = fields.Text(
        string='處理備註',
        help='處理時可填寫說明')

    # === 公司隔離 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # =========================================================================
    # 計算方法
    # =========================================================================

    @api.depends('current_cumulative_qty', 'next_threshold_qty')
    def _compute_achievement_rate(self):
        """計算達成率"""
        for rec in self:
            if rec.next_threshold_qty:
                rec.achievement_rate = (
                    rec.current_cumulative_qty / rec.next_threshold_qty
                ) * 100
            else:
                rec.achievement_rate = 0.0

    @api.depends('standard_id', 'task_id', 'state')
    def _compute_display_name(self):
        """自訂顯示名稱"""
        for rec in self:
            parts = []
            if rec.standard_material:
                parts.append(rec.standard_material)
            if rec.task_name:
                parts.append(rec.task_name)
            state_label = dict(rec._fields['state'].selection).get(rec.state, '')
            if state_label:
                parts.append(f'[{state_label}]')
            rec.display_name = ' - '.join(parts) if parts else f'預警 #{rec.id}'

    # =========================================================================
    # 動作方法（供前台串接）
    # =========================================================================

    def action_mark_done(self):
        """標記為已處理"""
        self.write({
            'state': 'done',
            'handled_by_id': self.env.user.id,
            'handled_date': fields.Datetime.now(),
        })

    def action_dismiss(self):
        """標記為已忽略"""
        self.write({
            'state': 'dismissed',
            'handled_by_id': self.env.user.id,
            'handled_date': fields.Datetime.now(),
        })

    def action_reset_pending(self):
        """重設為未處理"""
        self.write({
            'state': 'pending',
            'handled_by_id': False,
            'handled_date': False,
        })

    # =========================================================================
    # 查詢方法（供前台 Controller 使用）
    # =========================================================================

    @api.model
    def get_pending_warnings(self, project_id):
        """
        取得指定工程的未處理預警清單

        :param project_id: int, supervision.project ID
        :return: dict with count and warning list
        """
        warnings = self.search([
            ('project_id', '=', project_id),
            ('state', '=', 'pending'),
        ])
        return {
            'count': len(warnings),
            'warnings': [{
                'id': w.id,
                'standard_name': w.standard_id.name,
                'standard_material': w.standard_material,
                'task_name': w.task_name,
                'current_qty': w.current_cumulative_qty,
                'threshold_qty': w.next_threshold_qty,
                'achievement_rate': w.achievement_rate,
                'condition_summary': w.condition_summary,
                'warning_date': w.warning_date.isoformat() if w.warning_date else None,
            } for w in warnings],
        }

    @api.model
    def get_warning_summary(self, project_id):
        """
        取得指定工程的預警摘要統計

        :param project_id: int, supervision.project ID
        :return: dict with counts by state
        """
        result = {'pending': 0, 'done': 0, 'dismissed': 0, 'total': 0}
        warnings = self.read_group(
            domain=[('project_id', '=', project_id)],
            fields=['state'],
            groupby=['state'],
        )
        for w in warnings:
            state = w['state']
            count = w['state_count']
            result[state] = count
            result['total'] += count
        return result

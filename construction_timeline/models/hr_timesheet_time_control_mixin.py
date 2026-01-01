# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrTimesheetTimeControlMixin(models.AbstractModel):
    """
    時間控制 Mixin - 參考 OCA hr_timesheet_time_control

    此 Mixin 提供開始/結束計時功能，可被任何需要時間追蹤的模型繼承使用。
    主要功能：
    - 顯示計時控制按鈕 (開始/停止)
    - 與 account.analytic.line 整合記錄工時
    - 支援多筆正在執行的工時記錄

    使用方式：
    1. 模型繼承此 Mixin: _inherit = ['hr.timesheet.time.control.mixin']
    2. 實作 _relation_with_timesheet_line() 方法回傳關聯欄位名稱
    """
    _name = 'hr.timesheet.time.control.mixin'
    _description = '時間控制 Mixin'

    # === 計算欄位：顯示哪個控制按鈕 ===
    show_time_control = fields.Selection(
        selection=[
            ('start', '開始'),
            ('stop', '停止'),
        ],
        string='時間控制',
        compute='_compute_show_time_control',
        help='決定顯示「開始」或「停止」按鈕')

    running_timesheet_ids = fields.One2many(
        'account.analytic.line',
        compute='_compute_running_timesheet_ids',
        string='執行中工時')

    running_timesheet_count = fields.Integer(
        string='執行中工時數',
        compute='_compute_running_timesheet_ids')

    @api.model
    def _relation_with_timesheet_line(self):
        """
        回傳此模型與 account.analytic.line 的關聯欄位名稱。
        子類別必須覆寫此方法。

        例如 project.task 應回傳 'task_id'
        """
        return False

    def _get_running_timesheet_domain(self):
        """取得執行中工時記錄的 domain"""
        self.ensure_one()
        relation_field = self._relation_with_timesheet_line()
        if not relation_field:
            return []
        return [
            (relation_field, '=', self.id),
            ('is_timer_running', '=', True),
        ]

    def _compute_running_timesheet_ids(self):
        """計算執行中的工時記錄"""
        relation_field = self._relation_with_timesheet_line()
        if not relation_field:
            for record in self:
                record.running_timesheet_ids = False
                record.running_timesheet_count = 0
            return

        for record in self:
            domain = record._get_running_timesheet_domain()
            running = self.env['account.analytic.line'].search(domain)
            record.running_timesheet_ids = running
            record.running_timesheet_count = len(running)

    @api.depends('running_timesheet_ids')
    def _compute_show_time_control(self):
        """決定顯示開始或停止按鈕"""
        for record in self:
            if record.running_timesheet_count > 0:
                record.show_time_control = 'stop'
            else:
                record.show_time_control = 'start'

    def _get_timesheet_defaults(self):
        """取得建立工時記錄的預設值，子類別可覆寫"""
        self.ensure_one()
        return {
            'name': '/',
            'date': fields.Date.context_today(self),
            'date_time': fields.Datetime.now(),
            'unit_amount': 0,
            'is_timer_running': True,
        }

    def button_start_work(self):
        """
        開始施工計時

        建立一筆新的 account.analytic.line 記錄，
        設定 date_time 為現在時間，unit_amount = 0，
        is_timer_running = True。
        """
        self.ensure_one()
        relation_field = self._relation_with_timesheet_line()
        if not relation_field:
            return False

        # 取得預設值
        vals = self._get_timesheet_defaults()
        vals[relation_field] = self.id

        # 建立工時記錄
        timesheet = self.env['account.analytic.line'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'name': '施工計時已開始',
            'res_model': 'account.analytic.line',
            'res_id': timesheet.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def button_end_work(self):
        """
        結束施工計時

        找到所有執行中的工時記錄，計算時間差並更新 unit_amount，
        設定 is_timer_running = False。
        """
        self.ensure_one()
        running_lines = self.running_timesheet_ids
        if running_lines:
            return running_lines.button_end_work()
        return False

    def action_view_running_timesheet(self):
        """查看執行中的工時記錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '執行中工時',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form',
            'domain': self._get_running_timesheet_domain(),
            'context': {'default_' + self._relation_with_timesheet_line(): self.id},
        }

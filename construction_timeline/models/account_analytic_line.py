# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountAnalyticLine(models.Model):
    """
    工時記錄擴展 - 支援計時器功能

    擴展 account.analytic.line 以支援：
    - 計時器開始/結束功能
    - 自動計算工作時數
    - 與施工日誌整合
    """
    _inherit = 'account.analytic.line'

    # === 計時器欄位 ===
    date_time = fields.Datetime(
        string='開始時間',
        help='計時器開始的精確時間')

    date_time_end = fields.Datetime(
        string='結束時間',
        help='計時器結束的精確時間')

    is_timer_running = fields.Boolean(
        string='計時器執行中',
        default=False,
        help='標記此工時記錄的計時器是否正在執行')

    timer_duration = fields.Float(
        string='計時時長(小時)',
        compute='_compute_timer_duration',
        help='計時器累計時長')

    # === 工程相關欄位 ===
    work_description = fields.Text(
        string='工作內容說明',
        help='詳細描述本次施工內容')

    weather_condition = fields.Selection([
        ('sunny', '晴'),
        ('cloudy', '陰'),
        ('rainy', '雨'),
        ('typhoon', '颱風'),
    ], string='天氣狀況')

    @api.depends('date_time', 'date_time_end', 'is_timer_running')
    def _compute_timer_duration(self):
        """計算計時器時長"""
        now = fields.Datetime.now()
        for line in self:
            if line.date_time:
                end_time = line.date_time_end or (now if line.is_timer_running else line.date_time)
                delta = end_time - line.date_time
                line.timer_duration = delta.total_seconds() / 3600
            else:
                line.timer_duration = 0.0

    def button_start_work(self):
        """開始計時"""
        for line in self:
            if line.is_timer_running:
                raise UserError('此工時記錄已經在計時中')
            line.write({
                'date_time': fields.Datetime.now(),
                'is_timer_running': True,
            })
        return True

    def button_end_work(self):
        """結束計時並計算時數"""
        now = fields.Datetime.now()
        for line in self:
            if not line.is_timer_running:
                continue
            if not line.date_time:
                raise UserError('找不到開始時間，無法計算工時')

            # 計算時數
            delta = now - line.date_time
            hours = delta.total_seconds() / 3600

            line.write({
                'date_time_end': now,
                'unit_amount': hours,
                'is_timer_running': False,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '計時已結束',
                'message': f'已記錄工時 {hours:.2f} 小時',
                'type': 'success',
                'sticky': False,
            }
        }

    def button_pause_work(self):
        """暫停計時（不結束，保留狀態）"""
        for line in self:
            if not line.is_timer_running:
                continue
            # 計算到目前為止的時數並累加
            if line.date_time:
                now = fields.Datetime.now()
                delta = now - line.date_time
                additional_hours = delta.total_seconds() / 3600
                line.write({
                    'unit_amount': line.unit_amount + additional_hours,
                    'is_timer_running': False,
                })
        return True

    def button_resume_work(self):
        """繼續計時"""
        for line in self:
            if line.is_timer_running:
                raise UserError('此工時記錄已經在計時中')
            line.write({
                'date_time': fields.Datetime.now(),
                'is_timer_running': True,
            })
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """建立時自動設定開始時間"""
        for vals in vals_list:
            if vals.get('is_timer_running') and not vals.get('date_time'):
                vals['date_time'] = fields.Datetime.now()
        return super().create(vals_list)

    def action_open_timer_wizard(self):
        """開啟計時器精靈"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '編輯工時記錄',
            'res_model': 'account.analytic.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

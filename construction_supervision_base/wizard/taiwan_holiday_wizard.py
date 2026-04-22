# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date


# 台灣固定國定假日（不含農曆節日與清明節）
TAIWAN_FIXED_HOLIDAYS = [
    (1, 1, '元旦'),
    (2, 28, '和平紀念日'),
    (4, 4, '兒童節'),
    (5, 1, '勞動節'),
    (10, 10, '國慶日'),
]


class TaiwanHolidayWizard(models.TransientModel):
    """台灣假日建立精靈"""
    _name = 'taiwan.holiday.wizard'
    _description = '台灣假日建立精靈'

    year = fields.Integer(
        string='年度',
        default=lambda self: fields.Date.today().year,
        required=True,
    )
    calendar_id = fields.Many2one(
        'resource.calendar',
        string='工作行事曆',
        required=True,
        default=lambda self: self.env.company.resource_calendar_id,
        help='要建立假日的目標行事曆',
    )
    created_count = fields.Integer(string='已建立', readonly=True)
    skipped_count = fields.Integer(string='已跳過（重複）', readonly=True)
    state = fields.Selection([
        ('draft', '設定'),
        ('done', '完成'),
    ], default='draft')

    def action_generate_holidays(self):
        """產生固定國定假日"""
        self.ensure_one()
        Leave = self.env['resource.calendar.leaves']
        created = 0
        skipped = 0

        for month, day, name in TAIWAN_FIXED_HOLIDAYS:
            holiday_date = date(self.year, month, day)
            # 檢查是否已存在相同日期的假日
            existing = Leave.search_count([
                ('calendar_id', '=', self.calendar_id.id),
                ('resource_id', '=', False),
                ('date_from', '>=', f'{holiday_date} 00:00:00'),
                ('date_from', '<=', f'{holiday_date} 23:59:59'),
            ])
            if existing:
                skipped += 1
                continue

            Leave.create({
                'name': name,
                'calendar_id': self.calendar_id.id,
                'resource_id': False,  # 公共假日
                'date_from': f'{holiday_date} 00:00:00',
                'date_to': f'{holiday_date} 23:59:59',
            })
            created += 1

        self.write({
            'created_count': created,
            'skipped_count': skipped,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

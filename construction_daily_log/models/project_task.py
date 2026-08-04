# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api

# 「已確認」的施工日誌狀態。與 construction_general 的
# general_progress_report._sync_progress_lines 用同一組，勿另立一套；
# 'draft'（編輯中）不計入，避免尚在編修的日誌影響契約工項完成率。
CONFIRMED_SHEET_STATES = ('filled', 'auto_locked', 'locked')


class ProjectTask(models.Model):
    """契約工項：把「實際完成數量」接上施工日誌。

    construction_supervision_base 只把 actual_qty 宣告成唯讀欄位（因為它不認識
    daily.log.line），實際的計算掛在這裡。未安裝本模組時該欄位恆為 0。
    """
    _inherit = 'project.task'

    daily_log_line_ids = fields.One2many(
        'daily.log.line', 'work_item_id',
        string='施工日誌明細',
        help='所有登記本工項的施工日誌明細列')

    # 覆寫 base 的宣告：改為由施工日誌自動計算。
    # 不沿用 daily.log.line.cumulative_qty —— 那是掛在「每一列」上的逐列快照
    # （截至該列日期為止），且其 _compute_cumulative_qty 不篩 sheet_state，
    # 草稿日誌一填數量就會被算進去。這裡要的是「整個工項、只計已確認日誌」的
    # 總量，故直接加總 daily_qty。
    actual_qty = fields.Float(
        string='實際完成數量', digits=(16, 4),
        compute='_compute_actual_qty_from_daily_log',
        store=True, readonly=True,
        help='由施工日誌自動計算：本工項所有已確認日誌'
             '（已填寫／自動鎖定／已鎖定）的「本日完成數量」加總。\n'
             '彙總項不加總數量（各子工項單位不同），其金額由子工項向上滾動。')

    @api.depends('daily_log_line_ids.daily_qty',
                 'daily_log_line_ids.sheet_state',
                 'child_ids')
    def _compute_actual_qty_from_daily_log(self):
        for task in self:
            if task.child_ids:
                # 彙總項：子工項單位不一致，數量無法加總；金額走 actual_amount 滾動
                task.actual_qty = 0.0
                continue
            task.actual_qty = sum(
                line.daily_qty or 0.0
                for line in task.daily_log_line_ids
                if line.sheet_state in CONFIRMED_SHEET_STATES
            )

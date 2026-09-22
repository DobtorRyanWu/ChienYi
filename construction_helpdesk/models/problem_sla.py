# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PRIORITY_SELECTION = [
    ('p1', 'P1'),
    ('p2', 'P2'),
    ('p3', 'P3'),
    ('p4', 'P4'),
]


class ConstructionProblemSla(models.Model):
    """處理時限設定（P1～P4 固定四筆，只能改、不能新增刪除）。

    刻意不放在「設定」頁面：設定頁沒有修改紀錄，無法追究誰改的。
    這裡所有欄位開 tracking，chatter 自動記下誰、何時、從多少改成多少。

    問題單在分級當下把「預設修復工作天數」抄一份到自己身上（快照），
    所以這裡改了不會影響既有問題單。
    """
    _name = 'construction.problem.sla'
    _description = '處理時限設定'
    _inherit = ['mail.thread']
    _order = 'priority'
    _rec_name = 'priority'

    priority = fields.Selection(
        PRIORITY_SELECTION, string='優先級', required=True, readonly=True)
    default_fix_days = fields.Integer(
        string='預設修復工作天數', tracking=True,
        help='0 表示不設天數（P3「下一次例行版本」、P4「排入規劃」），'
             '此等級的問題單不會有預定修復日，也不判逾時。')
    no_days_note = fields.Char(
        string='不設天數時的說明', tracking=True,
        help='預設修復工作天數為 0 時顯示的文字，例如「下一次例行版本」「排入規劃」。'
             '有設天數時不使用（說明會自動顯示「N 個工作天」）。')
    fix_limit_note = fields.Char(
        string='修復時限說明', compute='_compute_fix_limit_note',
        help='依預設修復工作天數自動產生；天數為 0 時顯示「不設天數時的說明」。')
    response_target = fields.Char(
        string='回應目標', tracking=True,
        help='參考文字。系統只記錄回應完成時間，不判逾時。')
    temporary_target = fields.Char(
        string='暫行措施目標', tracking=True,
        help='參考文字（僅 P1）。系統只記錄完成時間，不判逾時。')

    _sql_constraints = [
        ('priority_unique', 'UNIQUE(priority)', '每個優先級只能有一筆時限設定。'),
    ]

    @api.depends('default_fix_days', 'no_days_note')
    def _compute_fix_limit_note(self):
        # 自動產生，避免「天數改成 3、說明還寫 2 個工作天」這種前後不一致
        for rec in self:
            rec.fix_limit_note = ('%s 個工作天' % rec.default_fix_days
                                  if rec.default_fix_days > 0 else (rec.no_days_note or '不設天數'))

    @api.constrains('default_fix_days')
    def _check_default_fix_days(self):
        for rec in self:
            if rec.default_fix_days < 0:
                raise ValidationError(_('預設修復工作天數不可為負數。'))

    @api.model
    def get_default_fix_days(self, priority):
        """依優先級取預設修復工作天數；0 或查無資料時回傳 0（＝不設天數）。"""
        sla = self.sudo().search([('priority', '=', priority)], limit=1)
        return sla.default_fix_days if sla else 0

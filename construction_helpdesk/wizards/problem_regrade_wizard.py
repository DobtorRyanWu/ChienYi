# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.problem import (
    P_MATRIX, SEVERITY_SELECTION, URGENCY_SELECTION, p_rank, upgraded_priority)
from ..models.problem_sla import PRIORITY_SELECTION


class ConstructionProblemRegradeWizard(models.TransientModel):
    """變更等級（分級之後的所有改判都走這裡，以確保每次都有原因）。

    最終 P 改變時：計算基準日＝今天、預期工作天數＝新 P 預設、掛「非工作日待確認」。
    起算日不動；「總處理天數」仍從客戶回報那天算，真相不會遺失。
    """
    _name = 'construction.problem.regrade.wizard'
    _description = '變更等級'

    problem_id = fields.Many2one('construction.problem', string='問題單', required=True, readonly=True)
    old_final_priority = fields.Selection(related='problem_id.final_priority', string='目前最終 P')
    severity = fields.Selection(SEVERITY_SELECTION, string='嚴重程度 S', required=True)
    urgency = fields.Selection(URGENCY_SELECTION, string='急迫性 U', required=True)
    special_external_doc = fields.Boolean(string='錯誤已流入對外文件')
    special_security = fields.Boolean(string='資安事件')
    special_repeat = fields.Boolean(string='二次回報（前次未修好）')
    manual_priority = fields.Selection(PRIORITY_SELECTION, string='人工調整 P')
    downgrade_reason = fields.Text(string='調整原因', help='人工調整 P 時說明原因；往下調（降級）時必填。')
    grade_guide_html = fields.Html(string='判定標準', compute='_compute_grade_guide_html', sanitize=False)
    new_upgraded_priority = fields.Selection(
        PRIORITY_SELECTION, string='套用特例後 P', compute='_compute_new_priority')
    new_final_priority = fields.Selection(
        PRIORITY_SELECTION, string='變更後最終 P', compute='_compute_new_priority')
    regrade_reason = fields.Text(string='改判原因', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        problem = self.env['construction.problem'].browse(
            res.get('problem_id') or self.env.context.get('default_problem_id'))
        if problem:
            for fname in ('severity', 'urgency', 'special_external_doc', 'special_security',
                          'special_repeat', 'manual_priority', 'downgrade_reason'):
                if fname in fields_list:
                    res[fname] = problem[fname]
        return res

    def _compute_grade_guide_html(self):
        html = self.env['construction.problem']._grade_guide_html()
        for wiz in self:
            wiz.grade_guide_html = html

    @api.depends('severity', 'urgency', 'special_external_doc', 'special_security',
                 'special_repeat', 'manual_priority')
    def _compute_new_priority(self):
        for wiz in self:
            up_p = upgraded_priority(P_MATRIX.get((wiz.severity, wiz.urgency), False),
                                     wiz.special_external_doc, wiz.special_security,
                                     wiz.special_repeat)
            wiz.new_upgraded_priority = up_p
            wiz.new_final_priority = (wiz.manual_priority or up_p) if up_p else False

    def action_confirm(self):
        self.ensure_one()
        problem = self.problem_id
        if not (self.regrade_reason or '').strip():
            raise UserError(_('請填寫改判原因。'))
        old_p = problem.final_priority
        grade_vals = {
            'severity': self.severity,
            'urgency': self.urgency,
            'special_external_doc': self.special_external_doc,
            'special_security': self.special_security,
            'special_repeat': self.special_repeat,
            'manual_priority': self.manual_priority,
            'downgrade_reason': self.downgrade_reason,
        }
        problem.with_context(helpdesk_regrade=True).write(grade_vals)  # 降級理由的約束在這裡檢查
        new_p = problem.final_priority

        lines = [_('<b>變更等級</b>：%(o)s → %(n)s', o=(old_p or '—').upper(), n=(new_p or '—').upper())]
        if new_p != old_p:
            Sla = self.env['construction.problem.sla']
            days = Sla.get_default_fix_days(new_p)
            date_vals = {
                'base_date': fields.Date.context_today(self),
                'expected_work_days': days,
                'non_working_to_confirm': bool(days),
            }
            if old_p and new_p and p_rank(new_p) < p_rank(old_p):
                date_vals['ever_upgraded'] = True
            problem.with_context(helpdesk_regrade=True).write(date_vals)
            lines.append(_('計算基準日改為今天，預期工作天數帶入 %(p)s 預設 %(d)s 天，請重新確認非工作日天數。',
                           p=new_p.upper(), d=days))
        else:
            lines.append(_('最終 P 未改變，預定修復日不變。'))
        body = Markup('<br/>').join([Markup(l) for l in lines] + [
            Markup('<b>改判原因</b>：%s') % escape(self.regrade_reason)])
        problem.message_post(body=body, subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}

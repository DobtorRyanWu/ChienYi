# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.problem import CLOSED_STATES


class ConstructionProblemLinkWizard(models.TransientModel):
    """轉問題單：連到既有的問題單（多位客戶回報同一問題），或新建一張。

    「是不是同一個問題」只能由客服人工判斷（各人描述不同，關鍵字比對不可靠；
    ITIL／Jira／ServiceNow 也都是人工連結）。系統的責任是讓客服看得出候選單在講什麼、
    找得到（不被發生功能選錯漏掉）、連錯了能改。
    """
    _name = 'construction.problem.link.wizard'
    _description = '轉問題單'

    ticket_id = fields.Many2one('construction.service.ticket', string='服務單', required=True, readonly=True)
    functional_module_id = fields.Many2one(related='ticket_id.functional_module_id', string='發生功能')
    ticket_description = fields.Html(related='ticket_id.description', string='這張服務單的詳細說明')
    current_problem_id = fields.Many2one(
        related='ticket_id.problem_id', string='目前關聯的問題單')
    mode = fields.Selection(
        [('link', '連到既有問題單'), ('new', '新建問題單')],
        string='方式', required=True, default='new')
    show_all = fields.Boolean(
        string='列出所有未結案問題單',
        help='預設只列同一發生功能的未結案問題單。客戶選錯或沒選發生功能時，同一個問題可能在別的功能底下，勾這個看全部。')
    candidate_ids = fields.Many2many(
        'construction.problem', string='候選問題單', compute='_compute_candidate_ids')
    candidate_count = fields.Integer(string='候選數', compute='_compute_candidate_ids')
    problem_id = fields.Many2one(
        'construction.problem', string='連到哪一張', domain="[('id', 'in', candidate_ids)]")
    title = fields.Char(string='標題')

    @api.depends('ticket_id', 'ticket_id.functional_module_id', 'show_all')
    def _compute_candidate_ids(self):
        Problem = self.env['construction.problem']
        for wiz in self:
            domain = [('state', 'not in', CLOSED_STATES)]
            # 同一發生功能、尚未結案；服務單沒填發生功能或勾了「全部」時列出全部未結案的
            if wiz.ticket_id.functional_module_id and not wiz.show_all:
                domain.append(('functional_module_id', '=', wiz.ticket_id.functional_module_id.id))
            if wiz.ticket_id.problem_id:
                domain.append(('id', '!=', wiz.ticket_id.problem_id.id))
            wiz.candidate_ids = Problem.search(domain)
            wiz.candidate_count = len(wiz.candidate_ids)

    @api.onchange('ticket_id')
    def _onchange_ticket_id(self):
        if self.ticket_id and not self.title:
            self.title = self.ticket_id.subject
        if self.candidate_ids and self.mode == 'new':
            # 有同發生功能的未結案問題單時，預設先讓客服看「連到既有」
            self.mode = 'link'

    def action_confirm(self):
        self.ensure_one()
        ticket = self.ticket_id
        if not ticket.is_system_problem:
            raise UserError(_('只有類別為「系統問題」的服務單可以轉問題單。'))
        if ticket.state in ('done', 'cancel'):
            raise UserError(_('已結案或已取消的服務單不能再轉問題單。'))
        if self.mode == 'link':
            if not self.problem_id:
                raise UserError(_('請選擇要連到哪一張問題單。'))
            problem = self.problem_id
        else:
            if not (self.title or '').strip():
                raise UserError(_('請填寫問題單標題。'))
            problem = self.env['construction.problem'].create({
                'title': self.title,
                'functional_module_id': ticket.functional_module_id.id,
                'description': ticket.description,
            })
        old = ticket.problem_id
        vals = {'problem_id': problem.id}
        if ticket.state == 'new':
            vals['state'] = 'processing'
            if not ticket.agent_user_id:
                vals['agent_user_id'] = self.env.user.id
        ticket.write(vals)
        problem.message_post(
            body=_('關聯服務單 %(t)s（%(s)s）', t=ticket.name, s=ticket.subject),
            subtype_xmlid='mail.mt_note')
        if old and old != problem:
            # 連錯了改連：舊的那張也留紀錄，事後查得到
            old.message_post(
                body=Markup(_('服務單 %(t)s 已改連到 %(p)s')) % {'t': ticket.name, 'p': problem.display_name},
                subtype_xmlid='mail.mt_note')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construction.problem',
            'res_id': problem.id,
            'view_mode': 'form',
            'target': 'current',
        }

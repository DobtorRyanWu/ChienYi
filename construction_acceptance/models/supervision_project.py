# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SupervisionProject(models.Model):
    """
    擴展工程案件主檔

    新增驗收與結案相關欄位
    """
    _inherit = 'supervision.project'

    # === 驗收關聯 ===
    preliminary_acceptance_ids = fields.One2many(
        'acceptance.preliminary',
        'project_id',
        string='初驗紀錄')

    preliminary_acceptance_count = fields.Integer(
        string='初驗次數',
        compute='_compute_acceptance_statistics')

    final_acceptance_ids = fields.One2many(
        'acceptance.final',
        'project_id',
        string='正驗紀錄')

    final_acceptance_count = fields.Integer(
        string='正驗次數',
        compute='_compute_acceptance_statistics')

    # === 驗收缺失關聯 ===
    acceptance_defect_ids = fields.One2many(
        'acceptance.defect',
        'project_id',
        string='驗收缺失')

    acceptance_defect_count = fields.Integer(
        string='驗收缺失數',
        compute='_compute_acceptance_statistics')

    unresolved_defect_count = fields.Integer(
        string='未解決缺失',
        compute='_compute_acceptance_statistics')

    # === 結案關聯 ===
    closure_id = fields.Many2one(
        'project.closure',
        string='結案記錄',
        compute='_compute_closure',
        store=True)

    is_closed = fields.Boolean(
        string='已結案',
        compute='_compute_closure',
        store=True)

    # === 保固資訊 ===
    warranty_end_date = fields.Date(
        string='保固截止日',
        compute='_compute_warranty_info',
        store=True)

    warranty_status = fields.Selection([
        ('none', '無保固'),
        ('active', '保固中'),
        ('expired', '已到期'),
    ], string='保固狀態',
       compute='_compute_warranty_info',
       store=True)

    @api.depends('preliminary_acceptance_ids', 'final_acceptance_ids',
                 'acceptance_defect_ids', 'acceptance_defect_ids.state')
    def _compute_acceptance_statistics(self):
        for project in self:
            project.preliminary_acceptance_count = len(project.preliminary_acceptance_ids)
            project.final_acceptance_count = len(project.final_acceptance_ids)
            project.acceptance_defect_count = len(project.acceptance_defect_ids)
            project.unresolved_defect_count = len(
                project.acceptance_defect_ids.filtered(
                    lambda d: d.state not in ('resolved', 'closed')
                )
            )

    @api.depends('final_acceptance_ids.closure_id', 'state')
    def _compute_closure(self):
        for project in self:
            closures = self.env['project.closure'].search([
                ('project_id', '=', project.id),
                ('state', '=', 'closed'),
            ], limit=1)
            project.closure_id = closures[0] if closures else False
            project.is_closed = project.state == 'closed'

    @api.depends('closure_id.warranty_end_date')
    def _compute_warranty_info(self):
        today = fields.Date.today()
        for project in self:
            if project.closure_id and project.closure_id.warranty_end_date:
                project.warranty_end_date = project.closure_id.warranty_end_date
                if today <= project.warranty_end_date:
                    project.warranty_status = 'active'
                else:
                    project.warranty_status = 'expired'
            else:
                project.warranty_end_date = False
                project.warranty_status = 'none'

    # === 查看動作 ===
    def action_view_preliminary_acceptances(self):
        """查看初驗紀錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '初驗紀錄',
            'res_model': 'acceptance.preliminary',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }

    def action_view_final_acceptances(self):
        """查看正驗紀錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '正驗紀錄',
            'res_model': 'acceptance.final',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }

    def action_view_acceptance_defects(self):
        """查看驗收缺失"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '驗收缺失',
            'res_model': 'acceptance.defect',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }

    def action_view_closure(self):
        """查看結案記錄"""
        self.ensure_one()
        if self.closure_id:
            return {
                'type': 'ir.actions.act_window',
                'name': '結案處理',
                'res_model': 'project.closure',
                'view_mode': 'form',
                'res_id': self.closure_id.id,
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': '結案處理',
                'res_model': 'project.closure',
                'view_mode': 'list,form',
                'domain': [('project_id', '=', self.id)],
                'context': {
                    'default_project_id': self.id,
                },
            }

    # === 建立初驗 ===
    def action_create_preliminary_acceptance(self):
        """建立初驗"""
        self.ensure_one()
        if self.state not in ('completion', 'acceptance'):
            raise UserError('只有已竣工或驗收中的工程可以建立初驗')

        return {
            'type': 'ir.actions.act_window',
            'name': '建立初驗',
            'res_model': 'acceptance.preliminary',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
            },
            'target': 'current',
        }

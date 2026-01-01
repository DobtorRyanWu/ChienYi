# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError


class GeneralSelfInspectionExtend(models.Model):
    """
    一般式自主檢查擴展

    設計說明：
    - 繼承 construction_quality 的 general.self.inspection
    - 增加與一般式缺失改善的整合功能
    - 提供缺失快速開立功能
    """
    _inherit = 'general.self.inspection'

    # === 缺失改善關聯 ===
    defect_improvement_ids = fields.One2many(
        'general.defect.improvement',
        'self_inspection_id',
        string='關聯缺失改善')

    defect_improvement_count = fields.Integer(
        string='缺失改善數',
        compute='_compute_defect_improvement_count')

    @api.depends('defect_improvement_ids')
    def _compute_defect_improvement_count(self):
        for record in self:
            record.defect_improvement_count = len(record.defect_improvement_ids)

    # === 動作方法 ===
    def action_view_defect_improvements(self):
        """查看關聯缺失改善"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '關聯缺失改善',
            'res_model': 'general.defect.improvement',
            'view_mode': 'list,form',
            'domain': [('self_inspection_id', '=', self.id)],
            'context': {
                'default_self_inspection_id': self.id,
                'default_project_id': self.project_id.id,
                'default_source_type': 'self_inspection',
            },
        }

    def action_create_defect_improvement(self):
        """從檢查缺失項目建立缺失改善單"""
        self.ensure_one()
        if not self.has_defect:
            raise UserError('此檢查無缺失項目')

        # 找出尚未建立缺失改善的缺失項目
        defect_items = self.checklist_ids.filtered(
            lambda x: x.check_result == 'defect' and not x.defect_improvement_id)

        if not defect_items:
            raise UserError('所有缺失項目皆已建立缺失改善單')

        created_improvements = self.env['general.defect.improvement']

        for item in defect_items:
            improvement = self.env['general.defect.improvement'].create({
                'project_id': self.project_id.id,
                'task_id': self.task_id.id if self.task_id else False,
                'source_type': 'self_inspection',
                'self_inspection_id': self.id,
                'self_inspection_item_id': item.id,
                'check_type': 'quality',
                'defect_category': 'quality',
                'defect_location': self.inspection_location,
                'defect_description': f"[{item.check_item}] {item.actual_result or ''}",
                'discovery_user_id': self.inspector_id.id if self.inspector_id else self.env.uid,
                'found_date': self.inspection_date,
                'responsible_company_id': self.contractor_company_id.id if self.contractor_company_id else False,
            })
            item.defect_improvement_id = improvement.id
            created_improvements |= improvement

        # 返回建立的缺失改善單
        if len(created_improvements) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': '缺失改善',
                'res_model': 'general.defect.improvement',
                'view_mode': 'form',
                'res_id': created_improvements.id,
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': '已建立的缺失改善',
                'res_model': 'general.defect.improvement',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_improvements.ids)],
            }


class GeneralSelfInspectionItemExtend(models.Model):
    """
    一般式自主檢查項目擴展

    設計說明：
    - 增加與一般式缺失改善的關聯
    """
    _inherit = 'general.self.inspection.item'

    # === 缺失改善關聯 ===
    defect_improvement_id = fields.Many2one(
        'general.defect.improvement',
        string='關聯缺失改善',
        help='若有缺失，可關聯一般式缺失改善單')

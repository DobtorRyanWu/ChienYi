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

    # === 缺失關聯（M4-b：收斂到 supervision.defect）===
    defect_improvement_ids = fields.One2many(
        'supervision.defect',
        'self_inspection_id',
        string='關聯缺失')

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
            'name': '關聯缺失',
            'res_model': 'supervision.defect',
            'view_mode': 'list,form',
            'domain': [('self_inspection_id', '=', self.id)],
            'context': {
                'default_self_inspection_id': self.id,
                'default_project_id': self.project_id.id,
                'default_source': 'self_inspection',
            },
        }

    def action_create_defect_improvement(self):
        """開啟建立缺失改善 Wizard，讓使用者選擇記錄類型"""
        self.ensure_one()
        if not self.has_defect:
            raise UserError('此檢查無缺失項目')

        defect_items = self.checklist_ids.filtered(
            lambda x: x.check_result == 'defect' and not x.supervision_defect_id)

        if not defect_items:
            raise UserError('所有缺失項目皆已建立缺失')

        # 用 context 開啟（讓 wizard 的 default_get 自動帶入未建立的缺失項目）
        return {
            'type': 'ir.actions.act_window',
            'name': '建立缺失改善',
            'res_model': 'create.defect.improvement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_inspection_id': self.id},
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

    def action_view_improvement(self):
        """查看本項目關聯的缺失（M4-b：supervision.defect）"""
        self.ensure_one()
        if not self.supervision_defect_id:
            raise UserError('尚未建立缺失')
        return {
            'type': 'ir.actions.act_window',
            'name': '缺失',
            'res_model': 'supervision.defect',
            'view_mode': 'form',
            'res_id': self.supervision_defect_id.id,
        }

    def action_create_improvement(self):
        """逐行建立缺失：開啟 wizard（選監造/營造），僅針對本項目"""
        self.ensure_one()
        if self.check_result != 'defect':
            raise UserError('只有缺失項目可以建立缺失')
        if self.supervision_defect_id:
            raise UserError('已建立缺失')
        return {
            'type': 'ir.actions.act_window',
            'name': '建立缺失改善',
            'res_model': 'create.defect.improvement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_inspection_id': self.inspection_id.id,
                'default_item_ids': [(6, 0, [self.id])],
            },
        }

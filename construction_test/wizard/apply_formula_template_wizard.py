# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class ApplyFormulaTemplateWizard(models.TransientModel):
    """套用公式範本精靈"""
    _name = 'apply.formula.template.wizard'
    _description = '套用公式範本精靈'

    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        required=True,
        readonly=True)

    template_id = fields.Many2one(
        'supervision.test.formula.template',
        string='公式範本',
        required=True,
        domain="['|', ('is_global', '=', True), ('company_id', '=', company_id)]")

    company_id = fields.Many2one(
        'res.company',
        related='standard_id.company_id')

    # 預覽欄位
    preview_description = fields.Text(
        string='公式說明',
        related='template_id.description',
        readonly=True)

    preview_formula = fields.Text(
        string='計算公式',
        related='template_id.custom_formula',
        readonly=True)

    preview_warning_formula = fields.Text(
        string='預警公式',
        related='template_id.custom_warning_formula',
        readonly=True)

    def action_apply(self):
        """套用範本到檢試驗項目"""
        self.ensure_one()

        if not self.template_id:
            raise UserError('請選擇公式範本')

        standard = self.standard_id
        template = self.template_id

        # 1. 複製公式到 standard
        standard.write({
            'use_custom_formula': True,
            'custom_formula': template.custom_formula,
            'custom_warning_formula': template.custom_warning_formula or False,
            'custom_formula_description': template.description or False,
        })

        # 2. 刪除 standard 現有的自訂變數
        standard.custom_formula_variable_ids.unlink()

        # 3. 從範本複製變數到 standard
        for var in template.variable_ids:
            self.env['supervision.test.formula.variable'].create({
                'standard_id': standard.id,
                'sequence': var.sequence,
                'name': var.name,
                'value': var.value,
                'description': var.description,
            })

        # 4. 記錄使用次數
        template.record_usage()

        return {'type': 'ir.actions.act_window_close'}

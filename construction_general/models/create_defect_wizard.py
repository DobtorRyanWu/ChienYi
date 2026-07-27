# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError


class CreateDefectImprovementWizard(models.TransientModel):
    """
    建立缺失改善 Wizard

    設計說明：
    - 讓使用者在建立缺失改善前選擇記錄類型（監造 / 營造）
    - 由自主檢查的「建立缺失改善」按鈕觸發
    """
    _name = 'create.defect.improvement.wizard'
    _description = '建立缺失改善 - 選擇記錄類型'

    inspection_id = fields.Many2one(
        'general.self.inspection',
        string='自主檢查',
        required=True,
        ondelete='cascade')

    record_type = fields.Selection([
        ('supervision', '監造'),
        ('contractor', '營造'),
    ], string='記錄類型', required=True, default='supervision')

    item_ids = fields.Many2many(
        'general.self.inspection.item',
        relation='create_gen_defect_wiz_item_rel',
        column1='wizard_id', column2='item_id',
        string='缺失項目',
        help='要建立缺失改善的檢查項目；逐行建立時為單一項，整張批次時為全部未建立缺失項')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # 若未由 context 指定 item_ids（逐行建立），則自動帶入整張檢查的未建立缺失項
        if 'item_ids' in fields_list and not res.get('item_ids'):
            inspection_id = res.get('inspection_id') or self.env.context.get('default_inspection_id')
            if inspection_id:
                inspection = self.env['general.self.inspection'].browse(inspection_id)
                defect_items = inspection.checklist_ids.filtered(
                    lambda x: x.check_result == 'defect' and not x.supervision_defect_id)
                res['item_ids'] = [(6, 0, defect_items.ids)]
        return res

    def action_confirm(self):
        """確認並建立缺失改善單"""
        self.ensure_one()
        inspection = self.inspection_id

        # 只處理本 wizard 指定、仍為缺失且尚未建立改善的項目
        defect_items = self.item_ids.filtered(
            lambda x: x.check_result == 'defect' and not x.supervision_defect_id)

        if not defect_items:
            raise UserError('所有缺失項目皆已建立缺失改善單')

        # M4-b：改建 supervision.defect（一般式缺失唯一模型）。用 supervision 真欄位，
        # 不依賴 portal 相容層。
        Defect = self.env['supervision.defect']
        created = Defect
        for item in defect_items:
            defect = Defect.create({
                'project_id': inspection.project_id.id,
                'task_id': inspection.task_id.id if inspection.task_id else False,
                'source': 'self_inspection',
                'self_inspection_id': inspection.id,
                'self_inspection_item_id': item.id,
                'record_type': self.record_type,
                'defect_type': 'quality',
                'location': inspection.inspection_location,
                'description': f"[{item.check_item}] {item.actual_result or ''}",
                'discovery_user_id': inspection.inspector_id.id if inspection.inspector_id else self.env.uid,
                'found_date': inspection.inspection_date,
                'responsible_company_id': inspection.contractor_company_id.id if inspection.contractor_company_id else False,
            })
            item.supervision_defect_id = defect.id
            created |= defect

        # 返回建立的缺失
        if len(created) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': '缺失',
                'res_model': 'supervision.defect',
                'view_mode': 'form',
                'res_id': created.id,
            }
        return {
            'type': 'ir.actions.act_window',
            'name': '已建立的缺失',
            'res_model': 'supervision.defect',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }

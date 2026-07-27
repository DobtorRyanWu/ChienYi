# -*- coding: utf-8 -*-
"""M4-b：一般式缺失收斂到 supervision.defect。

自主檢查的「建立缺失改善」精靈原本建 general.defect.improvement（已淘汰、資料已清空）。
本檔讓 supervision.defect 帶回「來源自主檢查」欄位、並讓自主檢查項可反向連到
supervision.defect，供精靈改建 supervision.defect（見 create_defect_wizard）。

放在 construction_general（depends construction_quality）→ 可同時參照 supervision.defect
與自身的 general.self.inspection，無循環相依。
"""
from odoo import models, fields


class SupervisionDefectInspectionSource(models.Model):
    _inherit = 'supervision.defect'

    # 自主檢查來源追溯（原僅 general.defect.improvement 有）
    self_inspection_id = fields.Many2one(
        'general.self.inspection', string='來源自主檢查',
        ondelete='set null', index=True)
    self_inspection_item_id = fields.Many2one(
        'general.self.inspection.item', string='來源檢查項', ondelete='set null')
    record_type = fields.Selection(
        [('supervision', '監造'), ('contractor', '營造')],
        string='記錄類型', default='supervision')


class GeneralSelfInspectionItemDefectLink(models.Model):
    _inherit = 'general.self.inspection.item'

    supervision_defect_id = fields.Many2one(
        'supervision.defect', string='關聯缺失',
        help='M4-b：自主檢查建立的缺失已收斂到 supervision.defect')

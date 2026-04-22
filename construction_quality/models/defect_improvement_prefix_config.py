# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DefectImprovementPrefixConfig(models.Model):
    """缺失改善編號前綴配置"""
    _name = 'defect.improvement.prefix.config'
    _description = '缺失改善編號前綴設定'
    _order = 'project_id'

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='工程案件',
        required=True,
        ondelete='cascade',
        index=True,
        help='此前綴配置所屬的工程案件')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    project_name = fields.Char(
        string='工程名稱',
        related='project_id.name',
        readonly=True)

    # === 編號前綴設定 ===
    supervision_prefix = fields.Char(
        string='監造編號前綴',
        required=True,
        help='監造單位使用的缺失改善編號前綴')

    contractor_prefix = fields.Char(
        string='營造編號前綴',
        required=True,
        help='營造廠商使用的缺失改善編號前綴')

    # === 備註 ===
    note = fields.Text(
        string='備註說明',
        help='此配置的額外說明')

    # === 約束與驗證 ===
    _sql_constraints = [
        ('unique_project_id',
         'UNIQUE(project_id)',
         '每個工程只能有一組編號前綴配置！'),
    ]

    @api.constrains('supervision_prefix', 'contractor_prefix')
    def _check_prefixes(self):
        """驗證前綴欄位"""
        for record in self:
            if record.supervision_prefix and len(record.supervision_prefix) > 10:
                raise ValidationError('監造編號前綴不得超過10個字元')
            if record.contractor_prefix and len(record.contractor_prefix) > 10:
                raise ValidationError('營造編號前綴不得超過10個字元')
            # 確保前綴不包含特殊字元
            import re
            if record.supervision_prefix and not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+$', record.supervision_prefix):
                raise ValidationError('監造編號前綴只能包含中文、英文字母和數字')
            if record.contractor_prefix and not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+$', record.contractor_prefix):
                raise ValidationError('營造編號前綴只能包含中文、英文字母和數字')

    def name_get(self):
        """自訂顯示名稱"""
        result = []
        for record in self:
            name = f"{record.project_name} (監造:{record.supervision_prefix} / 營造:{record.contractor_prefix})"
            result.append((record.id, name))
        return result

# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class ResUsers(models.Model):
    """擴展 res.users 模型，新增組織身分欄位"""
    _inherit = 'res.users'

    is_supervision_org = fields.Boolean(
        string='監造組織',
        help='勾選此項表示用戶屬於監造方組織',
    )

    is_contractor_org = fields.Boolean(
        string='營造組織',
        help='勾選此項表示用戶屬於營造方組織',
    )

    @api.onchange('is_supervision_org')
    def _onchange_is_supervision_org(self):
        """監造組織欄位變更時，自動同步群組關係（保留現有群組）"""
        group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
        if not group_supervision:
            return

        # 取得當前已有的群組 ID 清單
        current_group_ids = [g.id for g in self.groups_id]

        if self.is_supervision_org:
            # 如果沒有該群組，才加入
            if group_supervision.id not in current_group_ids:
                current_group_ids.append(group_supervision.id)
        else:
            # 移出該群組
            if group_supervision.id in current_group_ids:
                current_group_ids.remove(group_supervision.id)

        # 使用 (6, 0, ids) 替換，確保保留所有其他群組
        self.groups_id = [(6, 0, current_group_ids)]

    @api.onchange('is_contractor_org')
    def _onchange_is_contractor_org(self):
        """營造組織欄位變更時，自動同步群組關係（保留現有群組）"""
        group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
        if not group_contractor:
            return

        # 取得當前已有的群組 ID 清單
        current_group_ids = [g.id for g in self.groups_id]

        if self.is_contractor_org:
            # 如果沒有該群組，才加入
            if group_contractor.id not in current_group_ids:
                current_group_ids.append(group_contractor.id)
        else:
            # 移出該群組
            if group_contractor.id in current_group_ids:
                current_group_ids.remove(group_contractor.id)

        # 使用 (6, 0, ids) 替換，確保保留所有其他群組
        self.groups_id = [(6, 0, current_group_ids)]

    @api.model
    def create(self, vals):
        """建立用戶時同步群組"""
        user = super().create(vals)

        # 同步監造組織群組
        if vals.get('is_supervision_org'):
            group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
            if group_supervision:
                user.groups_id = [(4, group_supervision.id)]

        # 同步營造組織群組
        if vals.get('is_contractor_org'):
            group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
            if group_contractor:
                user.groups_id = [(4, group_contractor.id)]

        return user

    def write(self, vals):
        """更新用戶時同步群組"""
        res = super().write(vals)

        # 同步監造組織群組
        if 'is_supervision_org' in vals:
            group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
            if group_supervision:
                if vals['is_supervision_org']:
                    self.groups_id = [(4, group_supervision.id)]
                else:
                    self.groups_id = [(3, group_supervision.id)]

        # 同步營造組織群組
        if 'is_contractor_org' in vals:
            group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
            if group_contractor:
                if vals['is_contractor_org']:
                    self.groups_id = [(4, group_contractor.id)]
                else:
                    self.groups_id = [(3, group_contractor.id)]

        return res

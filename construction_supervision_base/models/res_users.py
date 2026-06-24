# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models, fields, api

# 定期閱覽者（臨時帳號）預設有效天數：
# 指派 group_portal_observer 但未填到期日時，自動帶今日 + 此天數
DEFAULT_OBSERVER_VALIDITY_DAYS = 90


class ResUsers(models.Model):
    """擴展 res.users 模型，新增組織身分欄位與臨時帳號到期欄位"""
    _inherit = 'res.users'

    is_supervision_org = fields.Boolean(
        string='監造組織',
        help='勾選此項表示用戶屬於監造方組織',
    )

    is_contractor_org = fields.Boolean(
        string='營造組織',
        help='勾選此項表示用戶屬於營造方組織',
    )

    portal_valid_until = fields.Date(
        string='帳號有效期至',
        help='僅對「定期閱覽者」臨時帳號有效。逾此日期後，由每日排程自動停用登入。'
             '留空表示不自動到期。',
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

        # 定期閱覽者：未填到期日時自動帶預設天數
        user._apply_observer_default_validity()

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

        # 群組異動時，若新加入定期閱覽者群組且未填到期日，帶入預設天數
        if 'groups_id' in vals:
            self._apply_observer_default_validity()

        return res

    def _apply_observer_default_validity(self):
        """定期閱覽者帳號未填到期日時，自動帶今日 + DEFAULT_OBSERVER_VALIDITY_DAYS"""
        observer_group = self.env.ref(
            'construction_supervision_base.group_portal_observer',
            raise_if_not_found=False)
        if not observer_group:
            return
        default_date = fields.Date.today() + timedelta(days=DEFAULT_OBSERVER_VALIDITY_DAYS)
        for user in self:
            if observer_group in user.groups_id and not user.portal_valid_until:
                user.portal_valid_until = default_date

    @api.model
    def _cron_deactivate_expired_portal_users(self):
        """每日排程：停用逾期的定期閱覽者（臨時帳號）

        條件（全部成立才停用）：
        - 有設定 portal_valid_until 且已逾期（< 今日）
        - 帳號目前仍啟用 active=True
        - 屬於 group_portal_observer 群組
        """
        observer_group = self.env.ref(
            'construction_supervision_base.group_portal_observer',
            raise_if_not_found=False)
        if not observer_group:
            return
        today = fields.Date.today()
        expired = self.search([
            ('portal_valid_until', '!=', False),
            ('portal_valid_until', '<', today),
            ('active', '=', True),
            ('groups_id', 'in', observer_group.id),
        ])
        if expired:
            expired.write({'active': False})

# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models, fields, api

# 定期閱覽者（臨時帳號）預設有效天數：
# 頂層角色為「定期閱覽者」(group_portal_viewer 但無 group_portal_user)
# 且未填到期日時，自動帶今日 + 此天數
DEFAULT_OBSERVER_VALIDITY_DAYS = 90

# 代操作員的登入落地頁：工程管理 > 工程總覽 > 工程案件
OPERATOR_GROUP_XMLID = 'construction_supervision_base.group_operator'
OPERATOR_HOME_ACTION_XMLID = 'construction_supervision_base.action_supervision_project'


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

    # 前台角色 key → 對應群組 xml_id（單選；四群組成繼承鏈，皆隱含 base.group_portal）
    _ROLE_KEY_TO_XMLID = {
        'observer': 'construction_supervision_base.group_portal_viewer',
        'field': 'construction_supervision_base.group_portal_user',
        'manager': 'construction_supervision_base.group_portal_leader',
        'boss': 'construction_supervision_base.group_portal_subscriber',
    }
    # 高→低（取最高角色用；老闆 ⊃ 主管 ⊃ 現場人員 ⊃ 定期閱覽者）
    _ROLE_KEYS_HIGH_TO_LOW = ('boss', 'manager', 'field', 'observer')

    portal_role = fields.Selection(
        selection=[
            ('observer', '定期閱覽者（臨時帳號）'),
            ('field', '現場人員'),
            ('manager', '主管'),
            ('boss', '老闆'),
        ],
        string='前台角色',
        compute='_compute_portal_role',
        inverse='_inverse_portal_role',
        store=True,
        help='外部前台使用者的角色。設定後此帳號會成為 Portal（入口網站）使用者。\n'
             '老闆 ⊃ 主管 ⊃ 現場人員 ⊃ 定期閱覽者（高階含低階全部權限）。\n'
             '系統管理者帳號不受此欄位轉換。',
    )

    @api.depends('groups_id')
    def _compute_portal_role(self):
        """由目前群組反推前台角色（取最高階）。"""
        refs = {k: self.env.ref(x, raise_if_not_found=False)
                for k, x in self._ROLE_KEY_TO_XMLID.items()}
        for user in self:
            role = False
            for key in self._ROLE_KEYS_HIGH_TO_LOW:
                g = refs.get(key)
                if g and g in user.groups_id:
                    role = key
                    break
            user.portal_role = role

    def _inverse_portal_role(self):
        """寫回：設定所選角色群組（移除其他角色群組）；指派角色且非系統管理者時，
        一併移除內部使用者身分、補上 base.group_portal，成為乾淨的 Portal 帳號。"""
        refs = {k: self.env.ref(x, raise_if_not_found=False)
                for k, x in self._ROLE_KEY_TO_XMLID.items()}
        all_roles = [g for g in refs.values() if g]
        g_user = self.env.ref('base.group_user', raise_if_not_found=False)
        g_portal = self.env.ref('base.group_portal', raise_if_not_found=False)
        g_system = self.env.ref('base.group_system', raise_if_not_found=False)
        for user in self:
            target = refs.get(user.portal_role) if user.portal_role else None
            cmds = [(3, g.id) for g in all_roles]          # 先移除全部角色群組
            if target:
                cmds.append((4, target.id))                # 補上所選角色
            # 指派角色且非 admin → 轉為乾淨 Portal（移除內部身分群組、補 portal）
            if target and g_user and g_portal and not (g_system and g_system in user.groups_id):
                internal = user.groups_id.filtered(
                    lambda g: g_user in (g | g.trans_implied_ids))
                cmds += [(3, g.id) for g in internal]
                cmds.append((4, g_portal.id))
            if cmds:
                user.groups_id = cmds

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

        # 前台帳號未設監造/營造身分 → 預設「營造(承包商)」，避免建缺失單無法判定類型
        user._apply_default_contractor_org()

        # 會填施工日誌/進度表的帳號自動建立對應 hr.employee，免手動再去「員工」設定
        user._ensure_construction_employee()

        # 內部（監造）帳號改站內通知（inbox），免依賴 email 也能收通知
        user._apply_internal_inbox_notification()

        # 代操作員登入直接落在工程案件，免每次自己點進去
        user._apply_operator_home_action()

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
            # 同時處理「這次才被加進代操作員群組」的帳號
            self._apply_operator_home_action()

        return res

    def _apply_observer_default_validity(self):
        """定期閱覽者帳號未填到期日時，自動帶今日 + DEFAULT_OBSERVER_VALIDITY_DAYS

        合併後「定期閱覽者」= group_portal_viewer（鏈底，被所有前台角色 imply），
        故「頂層角色就是定期閱覽者」= 有 viewer 但沒有 user
        （現場人員/主管/老闆的 groups_id 都實體含 user）。
        """
        viewer_group = self.env.ref(
            'construction_supervision_base.group_portal_viewer',
            raise_if_not_found=False)
        user_group = self.env.ref(
            'construction_supervision_base.group_portal_user',
            raise_if_not_found=False)
        if not viewer_group or not user_group:
            return
        default_date = fields.Date.today() + timedelta(days=DEFAULT_OBSERVER_VALIDITY_DAYS)
        for user in self:
            if (viewer_group in user.groups_id
                    and user_group not in user.groups_id
                    and not user.portal_valid_until):
                user.portal_valid_until = default_date

    def _apply_operator_home_action(self):
        """代操作員登入後直接落在「工程管理 > 工程總覽 > 工程案件」。

        Odoo 只有 per-user 的 `action_id`（偏好設定 > 首頁動作），沒有 per-group
        的落地頁設定，所以在授予 group_operator 時代設。

        只在 `action_id` 為空時寫入——使用者自己改過首頁動作之後，往後的群組異動
        與模組升級都不會覆蓋掉他的選擇。要恢復預設把該欄清空再存檔即可。
        """
        operator_group = self.env.ref(OPERATOR_GROUP_XMLID, raise_if_not_found=False)
        action = self.env.ref(OPERATOR_HOME_ACTION_XMLID, raise_if_not_found=False)
        if not operator_group or not action:
            return
        for user in self:
            if operator_group in user.groups_id and not user.action_id:
                user.action_id = action.id

    def _apply_default_contractor_org(self):
        """前台(portal)帳號未設監造/營造身分時，預設為營造(承包商)。

        建缺失單時 general/reservation.defect.improvement._resolve_record_type
        需靠 is_supervision_org / is_contractor_org 判定類型；前台帳號兩者皆空會被擋。
        DB-per-承包商 架構下前台帳號多為承包商，故預設營造；監造方用 portal 的特例後台改。
        只在兩者皆空時預設，不覆蓋已設值。
        """
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        if not portal_group:
            return
        for user in self:
            if (portal_group in user.groups_id
                    and not user.is_supervision_org
                    and not user.is_contractor_org):
                user.is_contractor_org = True

    def _ensure_construction_employee(self):
        """為會填施工日誌/進度表的帳號自動建立對應 hr.employee(若無)。

        施工日誌/進度表的「填表人」= hr.employee(required)。原本建帳號後還要手動去
        「員工」再建一筆並綁使用者，此處自動建立以省去兩頁操作。
        略過：系統/public/範本帳號、純定期閱覽者(view-only 不填表)。
        """
        Employee = self.env['hr.employee'].sudo()
        viewer_group = self.env.ref(
            'construction_supervision_base.group_portal_viewer', raise_if_not_found=False)
        user_group = self.env.ref(
            'construction_supervision_base.group_portal_user', raise_if_not_found=False)
        for user in self:
            if user.login in ('__system__', 'public', 'default', 'portaltemplate'):
                continue
            if Employee.search([('user_id', '=', user.id)], limit=1):
                continue
            # 純定期閱覽者(有 viewer、無 user，且為前台帳號)不需填表 → 略過
            if (viewer_group and user_group and user.share
                    and viewer_group in user.groups_id
                    and user_group not in user.groups_id):
                continue
            Employee.create({
                'name': user.name or user.login,
                'user_id': user.id,
                'company_id': user.company_id.id,
            })

    def _apply_internal_inbox_notification(self):
        """內部（非 portal）帳號預設站內通知（inbox），免依賴 email 也能收通知。

        portal（share）帳號受 Odoo SQL constraint「notification_type='email' OR NOT share」
        強制 email，故只對內部帳號設 inbox（設 inbox 會透過 inverse 自動加入
        mail.group_mail_notification_type_inbox 群組，compute 依此穩定判定）。
        """
        for user in self:
            if not user.share and user.notification_type != 'inbox':
                user.notification_type = 'inbox'

    def action_reset_password(self):
        """允許無 email 的帳號直接建立/使用（登入帳號可任意、不必是 email）。

        原生 auth_signup._action_reset_password 對無 email 使用者 raise
        「Cannot send email: user ... has no email address」，導致以非 email 登入帳號
        建帳號（會觸發邀請/重設密碼信）時流程中斷。此處僅對「有 email」的使用者走原生
        寄信流程；無 email 者靜默略過（不寄、不報錯），帳號維持無 email。
        """
        valid = self.filtered(lambda u: (u.email or '').strip())
        if not valid:
            return True
        return super(ResUsers, valid).action_reset_password()

    @api.model
    def _cron_deactivate_expired_portal_users(self):
        """每日排程：停用逾期的定期閱覽者（臨時帳號）

        條件（全部成立才停用）：
        - 有設定 portal_valid_until 且已逾期（< 今日）
        - 帳號目前仍啟用 active=True
        - 頂層角色是「定期閱覽者」= 有 viewer 但沒有 user
          （現場人員/主管/老闆都帶 user，即使有到期日也不自動停用）
        """
        viewer_group = self.env.ref(
            'construction_supervision_base.group_portal_viewer',
            raise_if_not_found=False)
        user_group = self.env.ref(
            'construction_supervision_base.group_portal_user',
            raise_if_not_found=False)
        if not viewer_group or not user_group:
            return
        today = fields.Date.today()
        expired = self.search([
            ('portal_valid_until', '!=', False),
            ('portal_valid_until', '<', today),
            ('active', '=', True),
            ('groups_id', 'in', viewer_group.id),
            ('groups_id', 'not in', user_group.id),
        ])
        if expired:
            expired.write({'active': False})

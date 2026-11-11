# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError, ValidationError

# 定期閱覽者（臨時帳號）預設有效天數：
# 頂層角色為「定期閱覽者」(group_portal_viewer 但無 group_portal_user)
# 且未填到期日時，自動帶今日 + 此天數
DEFAULT_OBSERVER_VALIDITY_DAYS = 90

# 代操作員的登入落地頁：工程管理 > 工程總覽 > 工程案件
OPERATOR_GROUP_XMLID = 'construction_supervision_base.group_operator'
OPERATOR_HOME_ACTION_XMLID = 'construction_supervision_base.action_supervision_project'
# 工程管理者 = 代操作員 ＋ base.group_system（工程師）
MANAGER_GROUP_XMLID = 'construction_supervision_base.group_engineering_manager'

# ── 公司儀表板：身分判定（合約 docs/architecture/dashboard/實作合約_v2.md §2）──
# 兩個群組定義在新模組 construction_company_dashboard；未安裝時 env.ref 回 None → 判定為否
DASH_CONTRACTOR_MANAGER_XMLID = 'construction_company_dashboard.group_contractor_manager'
DASH_CONSOLE_READER_XMLID = 'construction_company_dashboard.group_console_reader'
CONTRACTOR_ORG_GROUP_XMLID = 'construction_supervision_base.group_contractor_org'
# res.company.company_type 的營造廠值（與 res_company.py 的 Selection 一致）
COMPANY_TYPE_CONTRACTOR = 'contractor'
# 本庫主公司：本產品裡一定是監造公司或千溢，永遠不當營造廠（見 _dash_company_is_contractor）
MAIN_COMPANY_XMLID = 'base.main_company'

# ── 後台角色帳號（老闆／主管的內部唯讀帳號；S1，2026-11-10）──
# 群組定義在 construction_company_dashboard（模組沒裝 → env.ref 回 None → 判定一律為否）。
# 組合：層級（老闆 ROLE_BOSS 隱含主管 ROLE_MANAGER）＋方別標記恰好一個——
# 營造方標記＝DASH_CONTRACTOR_MANAGER_XMLID（沿用「營造廠主管」群組），監造方標記＝ROLE_SUPERVISION_XMLID。
# 判定只看原始群組成員資格（不看 TOTP、不看範圍）：有任何角色群組就是角色帳號＝受限帳號，
# 組合不合法、範圍不合格、沒開 TOTP 只會讓 _dash_scope_ok() 為 False（什麼都看不到），絕不會變回不受限的內部帳號。
ROLE_BOSS_XMLID = 'construction_company_dashboard.group_role_boss'
ROLE_MANAGER_XMLID = 'construction_company_dashboard.group_role_manager'
ROLE_SUPERVISION_XMLID = 'construction_company_dashboard.group_role_supervision'
# 層級的值：後台角色帳號（_role_level_raw）與前台角色（_portal_role_level、portal_role 欄位）共用同一組（S2 fix1-Q）
ROLE_LEVEL_BOSS = 'boss'
ROLE_LEVEL_MANAGER = 'manager'
PORTAL_LEVEL_FIELD = 'field'
PORTAL_LEVEL_OBSERVER = 'observer'
ROLE_SIDE_CONTRACTOR = 'contractor'
ROLE_SIDE_SUPERVISION = 'supervision'

# ── 手機（前台）能力的唯一來源（S2，2026-11-11）──────────────────────────
# 前台角色 → 群組的**唯一一張表**（高→低；S2 fix1-Q：portal_role 欄位的 _ROLE_KEY_TO_XMLID／_ROLE_KEYS_HIGH_TO_LOW
# 與手機能力的 _portal_role_level 都由它推出，增減角色只改這裡）。四群組成繼承鏈：老闆 ⊃ 主管 ⊃ 現場人員 ⊃ 定期閱覽者，
# 都隱含 base.group_portal。前台 controller（construction_portal/controllers/portal_utils.py GROUP_*）是同一組 xmlid。
PORTAL_ROLE_GROUPS = (
    (ROLE_LEVEL_BOSS, 'construction_supervision_base.group_portal_subscriber'),
    (ROLE_LEVEL_MANAGER, 'construction_supervision_base.group_portal_leader'),
    (PORTAL_LEVEL_FIELD, 'construction_supervision_base.group_portal_user'),
    (PORTAL_LEVEL_OBSERVER, 'construction_supervision_base.group_portal_viewer'),
)
PORTAL_ROLE_GROUP_BY_LEVEL = dict(PORTAL_ROLE_GROUPS)
# 管理層級（建工程、審核）與寫入層級（建立、修改單據；閱覽者不行）
PORTAL_MANAGE_LEVELS = frozenset({ROLE_LEVEL_BOSS, ROLE_LEVEL_MANAGER})
PORTAL_WRITE_LEVELS = frozenset({ROLE_LEVEL_BOSS, ROLE_LEVEL_MANAGER, PORTAL_LEVEL_FIELD})
SYSTEM_GROUP_XMLID = 'base.group_system'
# 組織群組（隱含 base.group_portal：只能給前台帳號，F5）
SUPERVISION_ORG_GROUP_XMLID = 'construction_supervision_base.group_supervision_org'


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

    # 營造方的「我的公司」（合約 §2、§1-7）：只看這個欄位，不看使用者自己改得到的 company_id。
    # groups='base.group_system'：只有系統管理者讀寫得到（工程管理者隱含此群組）；不在可自改欄位內。
    dash_scope_company_id = fields.Many2one(
        'res.company',
        string='範圍公司',
        index=True,
        groups='base.group_system',
        domain="[('company_type', '=', 'contractor')]",
        help='營造方帳號（營造廠主管、前台營造組織）在公司儀表板與讀取範圍裡的「我的公司」，必須是營造廠。\n'
             '營造方帳號（營造標記之一，或主要公司是營造廠）範圍公司空白時，這個帳號什麼都看不到（預設拒絕）。\n'
             '建立帳號時主要公司是營造廠會自動帶入；之後只有系統管理者能改。',
    )

    portal_valid_until = fields.Date(
        string='帳號有效期至',
        help='僅對「定期閱覽者」臨時帳號有效。逾此日期後，由每日排程自動停用登入。'
             '留空表示不自動到期。',
    )

    # 前台角色 key → 對應群組 xml_id、高→低順序：都由模組層的 PORTAL_ROLE_GROUPS 推出（S2 fix1-Q：只留一張表）
    _ROLE_KEY_TO_XMLID = PORTAL_ROLE_GROUP_BY_LEVEL
    _ROLE_KEYS_HIGH_TO_LOW = tuple(key for key, _xmlid in PORTAL_ROLE_GROUPS)

    is_engineering_manager = fields.Boolean(
        string='是工程管理者',
        compute='_compute_is_engineering_manager',
        help='控制使用者表單上「降級為代操作員」按鈕是否顯示。',
    )

    @api.depends('groups_id')
    def _compute_is_engineering_manager(self):
        manager = self.env.ref(MANAGER_GROUP_XMLID, raise_if_not_found=False)
        for user in self:
            user.is_engineering_manager = bool(manager and manager in user.groups_id)

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
        """監造組織欄位變更時，自動同步群組關係（保留現有群組）。只對前台帳號（F5，見 _org_group_sync_targets）。"""
        group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
        if not group_supervision or not self.share:
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
        """營造組織欄位變更時，自動同步群組關係（保留現有群組）。只對前台帳號（F5，見 _org_group_sync_targets）。"""
        group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
        if not group_contractor or not self.share:
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
        # 範圍公司要在 super().create() 之前帶入：約束在 create 內就會檢查
        vals = self._dash_prefill_scope_company(vals)
        user = super().create(vals)
        sync_targets = user._org_group_sync_targets()

        # 同步監造組織群組（F5：只對前台帳號）
        if vals.get('is_supervision_org') and sync_targets:
            group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
            if group_supervision:
                sync_targets.groups_id = [(4, group_supervision.id)]

        # 同步營造組織群組（F5：只對前台帳號）
        if vals.get('is_contractor_org') and sync_targets:
            group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
            if group_contractor:
                sync_targets.groups_id = [(4, group_contractor.id)]

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
        # F5：組織群組只同步給前台帳號（寫入之後的 share；轉換動作一次把群組換成內部帳號時就不會再加回去）
        sync_targets = self._org_group_sync_targets() if {'is_supervision_org', 'is_contractor_org'} & vals.keys() else self.browse()

        # 同步監造組織群組
        if 'is_supervision_org' in vals and sync_targets:
            group_supervision = self.env.ref('construction_supervision_base.group_supervision_org', raise_if_not_found=False)
            if group_supervision:
                if vals['is_supervision_org']:
                    sync_targets.groups_id = [(4, group_supervision.id)]
                else:
                    sync_targets.groups_id = [(3, group_supervision.id)]

        # 同步營造組織群組
        if 'is_contractor_org' in vals and sync_targets:
            group_contractor = self.env.ref('construction_supervision_base.group_contractor_org', raise_if_not_found=False)
            if group_contractor:
                if vals['is_contractor_org']:
                    sync_targets.groups_id = [(4, group_contractor.id)]
                else:
                    sync_targets.groups_id = [(3, group_contractor.id)]

        # 群組異動時，若新加入定期閱覽者群組且未填到期日，帶入預設天數
        if 'groups_id' in vals:
            self._apply_observer_default_validity()
            # 同時處理「這次才被加進代操作員群組」的帳號
            self._apply_operator_home_action()

        return res

    def _org_group_sync_targets(self):
        """組織旗標（is_supervision_org／is_contractor_org）要同步成組織群組的帳號：只有前台帳號（share）。

        F5（S2）：組織群組隱含 base.group_portal，內部帳號（含後台角色帳號）被加進去就變成 portal 與 internal 並存、
        被核心拒絕；角色帳號的方別只看方別群組（_role_side），旗標對內部帳號只是營造方標記（_dash_is_contractor_side）。
        """
        return self.filtered(lambda user: user.sudo().share)

    # ── 公司儀表板：身分判定與範圍公司（合約 §2）────────────────────────
    @api.model
    def _dash_prefill_scope_company(self, vals):
        """建立帳號時：沒指定範圍公司、而主要公司是營造廠 → 範圍公司帶主要公司。

        主要公司沒填時用 res.users.company_id 的預設值（env.company）。
        帶不到（主要公司是監造公司）就留空：營造方而範圍公司空白＝什麼都看不到（預設拒絕，合約 §0b-4）。
        預帶的意義：company_id 使用者自己改得到，範圍公司才是耐久的營造方標記（合約 §0b-5）。
        """
        if vals.get('dash_scope_company_id'):
            return vals
        company_id = vals.get('company_id') or self.env.company.id
        company = self.env['res.company'].sudo().browse(company_id).exists()
        if company and self._dash_company_is_contractor(company):
            vals = dict(vals, dash_scope_company_id=company.id)
        return vals

    @api.model
    def _dash_company_is_contractor(self, company):
        """公司算不算營造廠：公司類型是施工廠商，而且不是本庫主公司（base.main_company）。

        company_type 的預設值是「施工廠商」（res_company.py，18.0 既有），新庫的 1 號公司一開始就是施工廠商；
        不排除主公司的話，裝上儀表板後所有主要公司是 1 號公司的帳號（含管理員）都被判成營造方、什麼都看不到
        （線 F2 乾淨庫全模組測試實測：候選 126 支紅、基準 0 支）。本產品一庫屬於一家（或幾家）監造公司，
        主公司是該監造公司或千溢，不會是營造廠。
        """
        company = company.sudo()
        if not company or company.company_type != COMPANY_TYPE_CONTRACTOR:
            return False
        main = self.env.ref(MAIN_COMPANY_XMLID, raise_if_not_found=False)
        return company != main

    def _dash_in_group(self, xmlid):
        """是否帶某群組（含隱含群組）。

        不用 has_group：它讀 ormcache（_get_group_ids），在 write 的約束裡會讀到寫入前的群組；
        groups_id 本身已含隱含群組（核心 UsersImplied）。群組不存在（模組未裝）→ False。
        """
        self.ensure_one()
        group = self.env.ref(xmlid, raise_if_not_found=False)
        return bool(group) and group in self.sudo().groups_id

    def _dash_is_contractor_side(self):
        """營造方使用者（合約 §2、§0b-5）：帶營造廠主管群組、或勾營造組織、或屬營造組織群組、
        或範圍公司是營造廠、或主要公司是營造廠。

        判定只看帳號本身（呼叫端用 env.user，不因 env.su 跳過）；任何一個營造標記成立就是營造方。
        主要公司（company_id）使用者自己改得到，所以不能只靠它：建帳號預帶與 migration 會把它寫進
        範圍公司，之後改主要公司仍是營造方。
        """
        self.ensure_one()
        user = self.sudo()
        return bool(
            user._dash_in_group(DASH_CONTRACTOR_MANAGER_XMLID)
            or user.is_contractor_org
            or user._dash_in_group(CONTRACTOR_ORG_GROUP_XMLID)
            or self._dash_company_is_contractor(user.dash_scope_company_id)
            or self._dash_company_is_contractor(user.company_id)
        )

    def _dash_scope_ok(self):
        """範圍合格。False → 讀取規則預設拒絕（框架以外只剩本人，合約 §1-7、§0b-16）。

        * 角色帳號：要有層級，且依方別——營造方＝範圍公司是營造廠；監造方＝不是營造方、而且允許公司裡
          至少有一家不是營造廠；方別不是恰好一個（沒有方別或兩個都有）＝不合格。
        * 其他帳號（營造方、前台營造帳號）：範圍公司有值且是營造廠（原本的判定，不變）。
        """
        self.ensure_one()
        if self._is_role_account():
            if not self._role_level_raw():
                return False
            side = self._role_side()
            if side == ROLE_SIDE_CONTRACTOR:
                return self._dash_company_is_contractor(self.sudo().dash_scope_company_id)
            if side == ROLE_SIDE_SUPERVISION:
                return not self._dash_is_contractor_side() and bool(self._role_supervision_company_ids())
            return False
        return self._dash_company_is_contractor(self.sudo().dash_scope_company_id)

    def _dash_is_console_reader(self):
        """控台讀取帳號（合約 §3.1、§8.1）。"""
        self.ensure_one()
        return self._dash_in_group(DASH_CONSOLE_READER_XMLID)

    # ── 後台角色帳號（見檔頭 ROLE_* 常數）──────────────────────────────
    def _role_level_raw(self):
        """層級：'boss'／'manager'／None。只看群組；前台帳號（share）一律 None。"""
        self.ensure_one()
        if self.sudo().share:
            return None
        if self._dash_in_group(ROLE_BOSS_XMLID):
            return ROLE_LEVEL_BOSS
        if self._dash_in_group(ROLE_MANAGER_XMLID):
            return ROLE_LEVEL_MANAGER
        return None

    def _role_side(self):
        """方別：營造方標記與監造方標記剛好一個時回 'contractor'／'supervision'，否則 None。"""
        self.ensure_one()
        contractor = self._dash_in_group(DASH_CONTRACTOR_MANAGER_XMLID)
        supervision = self._dash_in_group(ROLE_SUPERVISION_XMLID)
        if contractor and not supervision:
            return ROLE_SIDE_CONTRACTOR
        if supervision and not contractor:
            return ROLE_SIDE_SUPERVISION
        return None

    def _is_role_account(self):
        """角色帳號：內部帳號，且帶老闆、主管或監造方標記任一群組。

        只看原始群組成員資格，不看 TOTP、不看範圍、不看組合合不合法（fail-closed 的前提，見檔頭）。
        只帶營造方標記、沒有層級的是原本的「營造廠主管」，不算角色帳號。
        """
        self.ensure_one()
        if self.sudo().share:
            return False
        return bool(
            self._dash_in_group(ROLE_BOSS_XMLID)
            or self._dash_in_group(ROLE_MANAGER_XMLID)
            or self._dash_in_group(ROLE_SUPERVISION_XMLID)
        )

    def _role_supervision_company_ids(self):
        """監造方角色帳號的監造公司：允許公司（company_ids）裡不是營造廠的那些（id 排序）。"""
        self.ensure_one()
        return sorted(
            company.id for company in self.sudo().company_ids
            if not self._dash_company_is_contractor(company)
        )

    def _dash_is_restricted(self):
        """受限帳號：營造方（含前台營造帳號）、控台讀取帳號、後台角色帳號。**全系統只有這一份**（fix1-G）。

        rule_scope 的 kind 不為 None、方法閘門、伺服器動作閘門、公開頻道、內部備註與其附件、通知、
        前台「以本人身分再過一次 ir.rule」、後台人員判定（_is_backend_staff）都由它推出；
        之後再加一種受限帳號，只改這裡。判定只看帳號本身（呼叫端用 env.user，不因 env.su 跳過）。
        """
        self.ensure_one()
        return bool(self._dash_is_console_reader() or self._dash_is_contractor_side() or self._is_role_account())

    def _dash_is_restricted_internal(self):
        """受限的內部帳號（營造廠主管、控台讀取、後台角色帳號）：內部帳號而且受限。**全系統只有這一份**（fix2-M）。

        留言／附件／通知／訊息寫入的守衛（construction_company_dashboard restricted_mail.py）、內部備註附件規則（rule_scope）
        都看它；前台帳號（share）照核心原本的規則。空的 recordset（沒有使用者）回 False。
        """
        if not self:
            return False
        self.ensure_one()
        return not self.sudo().share and self._dash_is_restricted()

    def _dash_is_blocked_internal(self):
        """範圍不合格的受限內部帳號（營造廠主管、後台角色帳號；沒開 TOTP、範圍公司或組合不合格）。**全系統只有這一份**（S2-D）。

        讀取規則讓它們讀不到業務單據上的訊息、收件人計算也拿掉它們（construction_company_dashboard rule_scope.py、
        restricted_mail.py 檔頭八），兩邊看同一個判斷才不會「讀不到卻被通知」而讓別人發訊息時失敗。
        控台讀取帳號不在內（它本來就只讀控台取資料方法，行為照舊）。
        """
        if not self:
            return False
        self.ensure_one()
        return bool(self._dash_is_restricted_internal() and not self._dash_is_console_reader()
                    and not self._dash_scope_ok())

    def _is_backend_staff(self):
        """監造方後台人員：內部帳號、而且不是受限帳號（不是營造方、控台讀取、角色帳號）。

        危險能力（樣板管理、樣板 docx 上傳、已提報缺失的定義欄位、營造廠歸屬重填、監造工程師下拉）一律看這個。
        """
        self.ensure_one()
        return bool(self._is_internal() and not self._dash_is_restricted())

    def _construction_org_side(self):
        """組織方別 'supervision'／'contractor'／None（S1 只定義；S2 才接上缺失類型）。

        角色帳號看方別群組（不看帳號上的組織旗標：前台帳號建立時會被自動勾營造組織）；
        其他帳號照組織旗標，兩個都勾或都沒勾回 None。
        """
        self.ensure_one()
        if self._is_role_account():
            return self._role_side()
        user = self.sudo()
        if user.is_supervision_org and not user.is_contractor_org:
            return ROLE_SIDE_SUPERVISION
        if user.is_contractor_org and not user.is_supervision_org:
            return ROLE_SIDE_CONTRACTOR
        return None

    def _is_supervision_side(self):
        """監造方使用者（合約 §2）：等於 _is_backend_staff()（名稱保留給既有呼叫端）。

        既有帳號沒有角色群組，結果與原本「內部帳號、不是營造方、也不是控台讀取」相同；
        角色帳號（含監造方角色帳號）不算——它們在後台唯讀、手機在 S1 也唯讀。
        """
        return self._is_backend_staff()

    # ── 手機（前台）能力：全系統各只有一份（S2，2026-11-11）──────────────────
    # 前台 controller 的守衛（construction_portal/controllers/portal.py：_can_manage、_is_field_only、_require_write、
    # _require_photo_deleter、_require_not_contractor、日誌解鎖）與模板裡的按鈕顯示條件都呼叫這裡，畫面與路由不會分岔。
    # 角色帳號沒有前台角色群組，能力由後台層級（_role_level_raw）推出；範圍不合格（含沒開 TOTP、組合不合法）＝沒有任何手機能力。
    def _portal_role_level(self):
        """手機能力的層級：'boss'／'manager'／'field'／'observer'／None（值與 portal_role 欄位同一組，PORTAL_ROLE_GROUPS）。

        * 前台帳號（share）：照前台角色群組取最高的一級。
        * 後台角色帳號：照後台層級（老闆、主管），而且範圍要合格（_dash_scope_ok：方別、範圍公司、TOTP）——
          沒開 TOTP 的角色帳號讀不到任何資料，也不能在手機寫入（例：建工程不必先讀任何紀錄）。
        * 其他內部帳號（監造方後台人員、代操作員、系統管理者）：None，它們另有自己的放行條件（_is_supervision_side 等），照舊。
        """
        self.ensure_one()
        if self.sudo().share:
            for level, xmlid in PORTAL_ROLE_GROUPS:
                if self._dash_in_group(xmlid):
                    return level
            return None
        if self._is_role_account():
            return self._role_level_raw() if self._dash_scope_ok() else None
        return None

    def _portal_can_manage(self):
        """手機的管理權（建工程、審核、工期展延…）：老闆、主管、系統管理者、代操作員。"""
        self.ensure_one()
        return bool(self._portal_role_level() in PORTAL_MANAGE_LEVELS
                    or self._dash_in_group(SYSTEM_GROUP_XMLID)
                    or self._dash_in_group(OPERATOR_GROUP_XMLID))

    def _portal_is_field_only(self):
        """現場人員（而且不是老闆、主管、系統管理者）：寫入只能限自己建立的單據。"""
        self.ensure_one()
        level = self._portal_role_level()
        if level in PORTAL_MANAGE_LEVELS or self._dash_in_group(SYSTEM_GROUP_XMLID):
            return False
        return level == PORTAL_LEVEL_FIELD

    def _portal_can_write(self):
        """手機能不能建立、修改單據（前台 _require_write 的放行條件）：閱覽者與受限的唯讀帳號不行。

        監造方後台人員（_is_supervision_side）一律可以；前台角色要現場人員以上；管理權（含代操作員）可以。
        """
        self.ensure_one()
        return bool(self._is_supervision_side() or self._portal_can_manage()
                    or self._portal_role_level() in PORTAL_WRITE_LEVELS)

    def _portal_owns_or_may_edit(self, record):
        """「現場人員只能改自己建立的單據」**全系統只有這一份**（S2 fix1-R）：不是現場人員、或沒有紀錄（新建，例：匯入時當天還沒有日誌）、
        或紀錄是本人建立的 → True。前台路由 _require_owner_or_manager 與模板（經 _portal_can_edit_record）都呼叫它。
        create_uid 是上傳／建立的人（前台以 sudo 建立，sudo 不換人）。"""
        self.ensure_one()
        return not self._portal_is_field_only() or not record or record.sudo().create_uid == self

    def _portal_can_edit_record(self, record):
        """能不能改這一張單據＝能寫入（_portal_can_write），而且通過「現場人員只能改自己建的」（_portal_owns_or_may_edit）：
        前台 _require_write＋_require_owner_or_manager 兩道的組合；模板的按鈕呼叫它。"""
        self.ensure_one()
        return self._portal_can_write() and self._portal_owns_or_may_edit(record)

    def _portal_can_delete_others_photos(self):
        """刪別人上傳的照片：管理權或監造方後台人員（其餘只能刪自己上傳的）。"""
        self.ensure_one()
        return bool(self._portal_can_manage() or self._is_supervision_side())

    def _dash_is_contractor_or_console(self):
        """營造方或控台讀取帳號（小集合）：「這件事限監造單位」的判斷（審核、結案、解鎖、工程主檔、自動補建樣板／工項）。

        監造方角色帳號不算營造方。和受限帳號（_dash_is_restricted，大集合：要以本人身分再過一次讀取規則）不同。
        """
        self.ensure_one()
        return bool(self._dash_is_contractor_side() or self._dash_is_console_reader())

    def _portal_review_visible(self):
        """審核類動作（限監造單位的那些：審核、結案、日誌解鎖、工程主檔、工期展延）看得到、做得到：
        有管理權，而且不是營造方／控台讀取。

        **審核類的判斷全系統只有這一份**：按鈕的顯示條件、路由守衛（前台 _require_review）、
        日誌的 can_unlock（construction_daily_log；解鎖按鈕與解鎖路由都看那個欄位）都呼叫它。
        """
        self.ensure_one()
        return self._portal_can_manage() and not self._dash_is_contractor_or_console()

    def _portal_other_data_visible(self):
        """「其他」類前台頁（水位監測、意見回饋）：監造方看得到（含範圍合格的監造方角色帳號；水位唯讀，意見回饋見 S2 fix2-W），
        營造方、控台讀取看不到。

        舊的前台監造老闆／主管（share）本來就看得到（S1 前的條件是「不是營造方」）；角色帳號照「同方別」。
        """
        self.ensure_one()
        if self._is_role_account():
            return self._role_side() == ROLE_SIDE_SUPERVISION and bool(self._portal_role_level())
        return not self._dash_is_restricted()

    def _portal_uses_phone_home(self):
        """登入後、/my 首頁走手機（/construction）的帳號：前台帳號與後台角色帳號（S2 計畫的預設決定：先到手機）。

        監造方後台人員等其他內部帳號照 Odoo 原本（後台）。
        """
        self.ensure_one()
        return bool(self.sudo().share or self._is_role_account())

    @api.constrains('dash_scope_company_id')
    def _check_dash_scope_company(self):
        """範圍公司可以空白，有值時必須是營造廠（合約 §0b-4）。

        營造方而範圍公司空白不擋：讀取規則預設拒絕（什麼都看不到），已是 fail-closed；
        若改成必填，監造方就建不了任何前台帳號（既有程式會把沒勾監造組織的前台帳號預設成營造組織）。
        """
        for user in self:
            scope = user.sudo().dash_scope_company_id
            if scope and not self._dash_company_is_contractor(scope):
                raise ValidationError(
                    '帳號「%s」的範圍公司「%s」不是營造廠（公司類型必須是施工廠商，且不能是本庫主公司）。'
                    % (user.display_name, scope.display_name))

    @api.model
    def _get_invalidation_fields(self):
        """範圍公司與營造組織旗標改變時清規則快取（ir.rule._compute_domain 以 uid 快取）。"""
        return super()._get_invalidation_fields() | {'dash_scope_company_id', 'is_contractor_org'}

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
        # 工程管理者也包含代操作員，但工程師登入後維持原本的畫面（使用者裁示）
        manager_group = self.env.ref(MANAGER_GROUP_XMLID, raise_if_not_found=False)
        for user in self:
            if manager_group and manager_group in user.groups_id:
                continue
            if operator_group in user.groups_id and not user.action_id:
                user.action_id = action.id

    def action_downgrade_to_operator(self):
        """工程管理者 → 代操作員。

        只在下拉把「工程管理者」改成「代操作員」拿不乾淨：Odoo 移除群組時
        不會連帶移除它帶進來的群組，於是「設定」(base.group_system) 與它再帶進來
        的群組（客服、Bypass HTML Field Sanitize、Mail Template Editor…）全部殘留，
        而且那些群組多半在 debug 才看得到的區塊，一般畫面上移不掉。

        移除範圍 ＝ 工程管理者 ＋ 設定 ＋ 設定帶進來的全部群組，
        但保留「代操作員會帶的」以及「此帳號其他群組會帶的」。
        ⚠️ Odoo 分不出某群組是「單獨勾的」還是「被帶進來的」：若此帳號另外被單獨
        指派了客服等群組，而它剛好也是設定會帶的，會一併移除，需要時再手動加回。
        """
        if not self.env.user.has_group('base.group_system'):
            raise AccessError('只有具備「設定」權限的帳號可以執行降級。')
        manager = self.env.ref(MANAGER_GROUP_XMLID)
        operator = self.env.ref(OPERATOR_GROUP_XMLID)
        system = self.env.ref('base.group_system')
        for user in self:
            if user.id == SUPERUSER_ID or user == self.env.user:
                raise UserError('不能降級自己（或系統內建的超級使用者），以免失去管理權而無法復原。')
            if manager not in user.groups_id:
                raise UserError('「%s」目前不是工程管理者，不需要降級。' % user.name)
            granted = manager | system | system.trans_implied_ids
            others = user.groups_id - granted
            keep = operator | operator.trans_implied_ids | others | others.trans_implied_ids
            to_remove = (user.groups_id & granted) - keep
            user.write({'groups_id': [(3, g.id) for g in to_remove] + [(4, operator.id)]})
        return True

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

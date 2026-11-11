# -*- coding: utf-8 -*-
"""營造廠主管、控台讀取、後台角色帳號的帳號設定（合約 §2、§3.1、§13-6；角色帳號 S1，2026-11-10）。

* 群組允許清單約束（res.users 與 res.groups 兩邊）：帶「營造廠主管」「控台讀取」或後台角色群組的帳號，
  群組只能是這些群組＋它們隱含的群組閉包＋通知類群組；帶營造廠主管就必須範圍公司合格；
  後台角色帳號另有組合限制（_dash_check_role_setup）。
* 伺服器動作「設為營造廠主管」（工程管理者限定）：一次寫好群組、主要公司、允許公司。
* 允許公司的計算（動作與自動同步共用）：營造公司（範圍公司）＋所承攬工程的所有監造公司；
  主公司＝承攬工程最多的監造公司。
* 兩步驟驗證（auth_totp）：要不要強制看 DASH_REQUIRE_TOTP（S2 fix2-Z，使用者 11-11 暫定：先不強制），唯一判斷點
  _dash_totp_missing；範圍不合格見 _dash_scope_ok。啟用／改密碼／改語言時區走核心 self-writeable 的 sudo，不受拒寫規則影響
  （見 tests/test_account_setup.py）。
* XML-RPC／JSON-RPC 外部 API 只收 API key（S2 fix3-9，使用者 11-11）：受限內部帳號（營造廠主管、後台角色帳號、控台讀取）
  走 /xmlrpc、/jsonrpc 不收密碼（_rpc_api_keys_only）；瀏覽器、手機登入照常只要密碼。這不是「密碼不能跑程式」：
  程式可用密碼走互動式登入（/web/session/authenticate）取得 session 再打 /web/dataset/call_kw（S2 第三輪 red-team F1；
  不開兩步驟驗證時的本質限制，見 README_ROLE_ACCOUNTS.md 已知限制）。
"""
import logging
from collections import Counter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.construction_supervision_base.models.res_users import (
    COMPANY_TYPE_CONTRACTOR,
    CONTRACTOR_ORG_GROUP_XMLID,
    DASH_CONSOLE_READER_XMLID,
    DASH_CONTRACTOR_MANAGER_XMLID,
    MANAGER_GROUP_XMLID,
    PORTAL_ROLE_GROUP_BY_LEVEL,
    ROLE_BOSS_XMLID,
    ROLE_LEVEL_BOSS,
    ROLE_LEVEL_MANAGER,
    ROLE_MANAGER_XMLID,
    ROLE_SIDE_CONTRACTOR,
    ROLE_SIDE_SUPERVISION,
    ROLE_SUPERVISION_XMLID,
    SUPERVISION_ORG_GROUP_XMLID,
)

from .rule_scope import ROLE_FEEDBACK_OWN, ROLE_FEEDBACK_REFERENCE

COMPANY_TYPE_SUPERVISION = 'supervision'
# 通知類與介面類群組，不算越權：內部帳號預設站內通知（construction_supervision_base 建帳號時自動補）、
# 多家允許公司時核心自動補的「Multi Companies」（只決定公司切換器顯示，不授予資料存取）
NOTIFICATION_GROUP_XMLIDS = (
    'mail.group_mail_notification_type_inbox',
    'base.group_multi_company',
)
# 選單實際名稱：有裝人資模組叫「我的個人資料」，沒裝叫「個人設定」；分頁叫「帳戶安全性」（fix1-I，真瀏覽器確認）
TOTP_SETUP_HINT = '請到右上角頭像 →「我的個人資料」（或「個人設定」）→「帳戶安全性」啟用兩步驟驗證（身分驗證 App），啟用後重新整理頁面即可看到資料。'
DENY_NOTE_TOTP = '公司儀表板範圍規則：這個後台唯讀帳號（營造廠主管／後台角色帳號）尚未啟用兩步驟驗證，' + TOTP_SETUP_HINT
# 群組允許清單的載體：帶任一個就只能帶「載體＋隱含閉包＋通知類群組」（營造廠主管、控台讀取、後台角色帳號三種）
CARRIER_GROUP_XMLIDS = (
    DASH_CONTRACTOR_MANAGER_XMLID, DASH_CONSOLE_READER_XMLID,
    ROLE_BOSS_XMLID, ROLE_MANAGER_XMLID, ROLE_SUPERVISION_XMLID,
)
# 範本使用者（base.default_user）加群組時，核心把新群組推給全部內部帳號（odoo/addons/base/models/res_users.py
# write：`internal_users.write({'groups_id': [Command.link(...)]})`，dev 開了 base_setup.default_user_rights）。
# 營造廠主管、控台讀取帳號不接收：推給它們會被群組允許清單約束擋下，讓「安裝一個替範本加群組的模組」整個失敗
# （hr_attendance 把考勤管理員加進範本，線 F1 在 dev 複本實測），放行又等於讓唯讀帳號多出管理權。
# base.group_user 新隱含的群組走另一條路（隱含閉包），約束本來就放行，不受這裡影響。
# 旗標只認本模組自己的物件（以 is 比對）：外部 RPC 帶同名鍵不算，避免被拿來讓寫入靜默略過受限帳號（L4④）。
TEMPLATE_PROPAGATION_CTX = 'dash_template_group_propagation'


class _TemplatePropagationToken:
    """本模組內部標記「這次 write 是核心從範本推送群組」的憑證（外部偽造不了）。"""
    __slots__ = ()

    def __repr__(self):
        return '<dash_template_group_propagation token>'


TEMPLATE_PROPAGATION_TOKEN = _TemplatePropagationToken()
# 營造廠主管與後台角色帳號要不要強制兩步驟驗證（S2 fix2-Z）。**使用者 11-11 暫定：先不強制，之後可能恢復**——
# 恢復只要改成 True：沒開 TOTP＝範圍不合格（什麼都看不到、手機沒能力、不收業務通知）的判斷都還在，只經 _dash_totp_missing。
# 控台讀取帳號本來就不看它。測試裡要驗「強制時」的行為就把這個常數 patch 成 True（tests/test_scope_rules.require_totp）。
DASH_REQUIRE_TOTP = False
# 寫了這些欄位，帳號可能從此變成受限帳號（群組、營造組織旗標、範圍公司、主要公司：_dash_is_contractor_side 的標記）
RESTRICTION_MARKER_FIELDS = frozenset({'groups_id', 'is_contractor_org', 'dash_scope_company_id', 'company_id'})
_logger = logging.getLogger(__name__)

# ── 前台角色帳號 ↔ 後台角色帳號的轉換（S2，2026-11-11）──────────────────────────
INTERNAL_USER_GROUP_XMLID = 'base.group_user'
PORTAL_USER_GROUP_XMLID = 'base.group_portal'
INBOX_GROUP_XMLID = 'mail.group_mail_notification_type_inbox'
# 層級 → 後台角色群組（老闆 ⊃ 主管兩邊都是繼承鏈，寫最高那一個，隱含的由核心補）。前台角色群組照
# construction_supervision_base 的 PORTAL_ROLE_GROUP_BY_LEVEL（前台與後台用同一組層級值；S2 fix1-Q）
LEVEL_TO_ROLE_GROUP = {ROLE_LEVEL_BOSS: ROLE_BOSS_XMLID, ROLE_LEVEL_MANAGER: ROLE_MANAGER_XMLID}
# 轉換會改到、改回要逐欄寫回的 res.users 欄位（S2 fix1-P）；轉換時原值存進 dash_role_origin
ROLE_ORIGIN_FIELDS = ('groups_id', 'is_supervision_org', 'is_contractor_org', 'dash_scope_company_id',
                      'company_id', 'company_ids')
# 方別：後台方別標記 ↔ 前台組織群組
SIDE_TO_ROLE_MARKER = {ROLE_SIDE_CONTRACTOR: DASH_CONTRACTOR_MANAGER_XMLID, ROLE_SIDE_SUPERVISION: ROLE_SUPERVISION_XMLID}
SIDE_TO_ORG_GROUP = {ROLE_SIDE_CONTRACTOR: CONTRACTOR_ORG_GROUP_XMLID, ROLE_SIDE_SUPERVISION: SUPERVISION_ORG_GROUP_XMLID}


# 意見回饋（construction_helpdesk，dev 才有裝；S2 fix2-W）：後台角色帳號的讀取權。不寫在 csv：本模組不依賴 construction_helpdesk，
# 沒裝的庫引用不到它的模型。由升級本模組時的函式（data/feedback_acl.xml）建，模型不存在就略過；之後才裝 helpdesk 的庫
# 要再 -u 本模組（README_ROLE_ACCOUNTS.md §4）。讀得到哪幾筆由 rule_scope 決定（ROLE_FEEDBACK_OWN：只有自己建的；營造方角色帳號全拒）。
# 模型名只有 rule_scope 那一份（S2 fix3-8，審查 simplifier W-1）
FEEDBACK_ACL_MODELS = (ROLE_FEEDBACK_OWN, *sorted(ROLE_FEEDBACK_REFERENCE))
FEEDBACK_ACL_NAME = '後台角色帳號 讀 意見回饋（S2 fix2-W）'


def _groups_by_xmlid(env, xmlids):
    groups = env['res.groups']
    for xmlid in xmlids:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            groups |= group
    return groups


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ── 判定 ──────────────────────────────────────────────────────────
    def _dash_is_contractor_manager(self):
        """帶營造廠主管群組（群組未安裝 → False）。"""
        self.ensure_one()
        return self._dash_in_group(DASH_CONTRACTOR_MANAGER_XMLID)

    def _dash_totp_missing(self):
        """營造廠主管或後台角色帳號（含監造方角色帳號）而沒有啟用 TOTP（合約 §13-6；S1 預設決定監造方也強制）。
        其他帳號不要求。**唯一判斷點**：範圍合格（_dash_scope_ok）、session 的 dash_totp_missing、手機首頁的提示、
        儀表板的提示都看它。DASH_REQUIRE_TOTP 為 False（S2 fix2-Z，使用者 11-11 暫定）時一律回 False＝不要求。"""
        self.ensure_one()
        if not DASH_REQUIRE_TOTP:
            return False
        return ((self._dash_is_contractor_manager() or self._is_role_account())
                and not self.sudo().totp_enabled)

    def _dash_scope_ok(self):
        """範圍合格：base 的判斷（範圍公司、方別、層級；construction_supervision_base res.users._dash_scope_ok），
        強制兩步驟驗證時（DASH_REQUIRE_TOTP）另要已啟用——經 _dash_totp_missing，常數為 False 時不看。

        False → 讀取規則預設拒絕（框架以外只剩本人的使用者與聯絡人，合約 §0b-16）。判定只看帳號本身，不因 env.su 跳過。
        """
        return super()._dash_scope_ok() and not self._dash_totp_missing()

    def _rpc_api_keys_only(self):
        """S2 fix3-9（使用者 11-11「關」；審查 s2review2-redteam F1）：受限內部帳號（營造廠主管、後台角色帳號、控台讀取）的
        XML-RPC／JSON-RPC 外部 API（/xmlrpc/2、/jsonrpc：核心的非互動式登入）只收 API key、不收密碼——與核心 auth_totp 對「開了 TOTP 的帳號」
        同一個機制（auth_totp/models/res_users.py 覆寫的就是這一支；判斷在 base/models/res_users.py _check_credentials 的
        非互動式分支）。瀏覽器／手機登入（/web/login、/web/session/authenticate，互動式）不看這裡，照常只要密碼，
        **不要求任何人開兩步驟驗證**（使用者 11-11：「大家用兩步驟驗證太麻煩」）。所以程式仍可用密碼模仿網頁登入取得 session、
        再打 /web/dataset/call_kw（S2 第三輪 red-team F1）——不開兩步驟驗證時的本質限制，完整防護只有恢復 DASH_REQUIRE_TOTP。控台讀取帳號本來就用 API key
        （tools/console_agent/pull_overview.py；dev 的 console_reader 有一把 scope=rpc 的 key）。self＝要登入的那個帳號。"""
        return self._dash_is_restricted_internal() or super()._rpc_api_keys_only()

    # ── 群組允許清單 ──────────────────────────────────────────────────
    def _dash_allowed_groups(self):
        """本帳號允許帶的群組；不受限（沒帶任何載體群組，見 CARRIER_GROUP_XMLIDS）→ None。"""
        self.ensure_one()
        carriers = _groups_by_xmlid(self.env, CARRIER_GROUP_XMLIDS) & self.sudo().groups_id
        if not carriers:
            return None
        allowed = carriers | carriers.trans_implied_ids
        return allowed | _groups_by_xmlid(self.env, NOTIFICATION_GROUP_XMLIDS)

    def _dash_check_account_setup(self):
        """群組允許清單＋營造廠主管的範圍公司（合約 §3.1）；不合格丟 ValidationError。"""
        for user in self.sudo():
            allowed = user._dash_allowed_groups()
            if allowed is None:
                continue
            extra = user.groups_id - allowed
            if extra:
                raise ValidationError(_(
                    '帳號「%(user)s」帶有營造廠主管、控台讀取或後台角色帳號群組，不可再帶其他群組：%(groups)s。\n'
                    '這幾種帳號只能是唯讀範圍（營造廠主管請用使用者表單「設為營造廠主管」重設群組）。',
                    user=user.display_name,
                    groups='、'.join(extra.mapped('full_name'))))
            if user._is_role_account():
                user._dash_check_role_setup()
            if user._dash_is_contractor_manager():
                # 範圍公司有值但不是營造廠，由 construction_supervision_base 的 _check_dash_scope_company 擋
                if not user.dash_scope_company_id:
                    raise ValidationError(_(
                        '營造廠主管帳號「%s」必須設定範圍公司（營造廠）。', user.display_name))

    def _dash_check_role_setup(self):
        """後台角色帳號的組合（S1）：方別標記恰好一個、監造方要有層級、監造方不是營造方且至少一家非營造廠的允許公司。

        這只是「從 ORM 設定時就擋下來」；就算用 SQL 繞過，判定也是 fail-closed（_dash_scope_ok() 為 False，見
        construction_supervision_base/models/res_users.py 檔頭的 ROLE_* 說明）。
        """
        self.ensure_one()
        name = self.display_name
        if self._dash_is_console_reader():
            raise ValidationError(_('帳號「%s」不可同時是控台讀取帳號與後台角色帳號。', name))
        contractor = self._dash_in_group(DASH_CONTRACTOR_MANAGER_XMLID)
        supervision = self._dash_in_group(ROLE_SUPERVISION_XMLID)
        if contractor == supervision:
            raise ValidationError(_(
                '後台角色帳號「%s」必須恰好帶一個方別標記：「營造方（後台唯讀）」或「監造單位（角色帳號）」。', name))
        if supervision:
            if not self._role_level_raw():
                raise ValidationError(_(
                    '監造方角色帳號「%s」必須帶層級：「後台老闆」或「後台主管」。', name))
            if self._dash_is_contractor_side():
                raise ValidationError(_(
                    '監造方角色帳號「%s」不可是營造方（營造組織標記、範圍公司、主要公司都不可以是營造廠）。', name))
            if not self._role_supervision_company_ids():
                raise ValidationError(_(
                    '監造方角色帳號「%s」的允許公司至少要有一家不是營造廠（監造公司）。', name))

    # 範圍公司、組織旗標、主要公司、允許公司改變時也要重查（監造方角色帳號的營造標記與監造公司看這些欄位）
    @api.constrains('groups_id', 'dash_scope_company_id', 'is_contractor_org', 'company_id', 'company_ids')
    def _check_dash_account_setup(self):
        self._dash_check_account_setup()

    def _dash_restricted_users(self):
        """self 之中帶載體群組（營造廠主管、控台讀取、後台角色帳號）的帳號（群組允許清單約束管的那些）。"""
        carriers = _groups_by_xmlid(self.env, CARRIER_GROUP_XMLIDS)
        return self.filtered(lambda user: user.sudo().groups_id & carriers) if carriers else self.browse()

    def write(self, vals):
        res = self._dash_write(vals)
        if RESTRICTION_MARKER_FIELDS & vals.keys():
            # 帳號變成受限帳號（例：既有員工改設為營造廠主管）：移出公開頻道（restricted_channels.py）
            self._dash_leave_public_channels()
        return res

    def _dash_write(self, vals):
        if self.env.context.get(TEMPLATE_PROPAGATION_CTX) is TEMPLATE_PROPAGATION_TOKEN and set(vals) == {'groups_id'}:
            # 核心把範本的新群組推給既有內部帳號：跳過受限帳號（見 TEMPLATE_PROPAGATION_CTX）
            skipped = self._dash_restricted_users()
            if skipped:
                _logger.warning('範本使用者新增的群組不推給營造廠主管／控台讀取帳號（%s）：%s',
                                ', '.join(skipped.mapped('login')), vals['groups_id'])
                rest = self - skipped
                return super(ResUsers, rest).write(vals) if rest else True
            return super().write(vals)
        template = self.env.ref('base.default_user', raise_if_not_found=False)
        if 'groups_id' in vals and template and template in self:
            return super(ResUsers, self.with_context(**{TEMPLATE_PROPAGATION_CTX: TEMPLATE_PROPAGATION_TOKEN})).write(vals)
        return super().write(vals)

    # ── 允許公司與主公司 ───────────────────────────────────────────────
    @api.model
    def _dash_manager_companies(self, scope):
        """某營造廠的主管帳號該有的 (允許公司, 承攬工程最多的監造公司)。

        承攬工程含封存、終止的（儀表板的未結事項要算，合約 §5.1）；監造公司只算公司類型是監造的
        （工程 company_id 填成營造廠的髒資料不該因此開放別家營造廠的資料給主管）。
        """
        projects = self.env['project.project'].sudo().with_context(active_test=False).search(
            [('contractor_company_ids', 'in', scope.ids)])
        counts = Counter(
            project.company_id.id for project in projects
            if project.company_id.company_type == COMPANY_TYPE_SUPERVISION)
        Company = self.env['res.company'].sudo()
        companies = Company.browse(sorted(counts))
        main = Company.browse(min(counts, key=lambda cid: (-counts[cid], cid))) if counts else scope
        return scope | companies, main

    def _dash_apply_manager_companies(self, force_main):
        """把允許公司寫成「範圍公司＋所有相關監造公司」。

        force_main=True：主公司一律重設成承攬工程最多的監造公司（伺服器動作）；
        False：目前的主公司仍在允許公司內且是監造公司就保留（自動同步，不推翻使用者在偏好裡選的）。
        """
        for user in self.sudo():
            scope = user.dash_scope_company_id
            allowed, main = self._dash_manager_companies(scope)
            current = user.company_id
            keep = (not force_main and current in allowed
                    and current.company_type == COMPANY_TYPE_SUPERVISION)
            user.write({
                'company_ids': [(6, 0, allowed.ids)],
                'company_id': (current if keep else main).id,
            })

    @api.model
    def _dash_sync_managers_of(self, contractors):
        """營造廠 contractors 的營造廠主管，允許公司自動重算（sudo；工程變動時呼叫）。"""
        group = self.env.ref(DASH_CONTRACTOR_MANAGER_XMLID, raise_if_not_found=False)
        if not group or not contractors:
            return
        managers = self.sudo().with_context(active_test=False).search([
            ('groups_id', 'in', group.id),
            ('dash_scope_company_id', 'in', contractors.ids),
        ])
        managers._dash_apply_manager_companies(force_main=False)

    # ── 伺服器動作「設為營造廠主管」──────────────────────────────────────
    def action_set_contractor_manager(self):
        """依合約 §2 一次寫好：群組只剩營造廠主管、主公司、允許公司（範圍公司要先填）。"""
        if not (self.env.su or self.env.user.has_group(MANAGER_GROUP_XMLID)):
            raise AccessError(_('只有工程管理者可以把帳號設為營造廠主管。'))
        manager_group = self.env.ref(DASH_CONTRACTOR_MANAGER_XMLID)
        notification = _groups_by_xmlid(self.env, NOTIFICATION_GROUP_XMLIDS)
        for user in self.sudo():
            if user.id == self.env.user.id or user._is_superuser():
                raise UserError(_('不能把自己或系統內建帳號設為營造廠主管（群組會被整個重設，會失去管理權）。'))
            scope = user.dash_scope_company_id
            if not scope:
                raise UserError(_('帳號「%s」尚未填「範圍公司」，請先在使用者表單填營造廠再執行。', user.display_name))
            if scope.company_type != COMPANY_TYPE_CONTRACTOR:
                raise UserError(_(
                    '帳號「%(user)s」的範圍公司「%(company)s」不是營造廠（公司類型必須是施工廠商）。',
                    user=user.display_name, company=scope.display_name))
            # 群組先重設（約束在這一步就會檢查：只剩營造廠主管＋隱含群組＋通知群組）；
            # Multi Companies 由核心依允許公司數自動補，不在這裡指定
            user.write({'groups_id': [(6, 0, (manager_group | notification.filtered(
                lambda g: g.get_external_id()[g.id] != 'base.group_multi_company')).ids)]})
            user._dash_apply_manager_companies(force_main=True)
        names = '、'.join(self.mapped('display_name'))
        # 強制兩步驟驗證時才提醒（只經 _dash_totp_missing 看 DASH_REQUIRE_TOTP；S2 fix3 Z-1）
        if any(user._dash_totp_missing() for user in self):
            return self._dash_notify(_('已設為營造廠主管：%s。提醒對方登入後先啟用兩步驟驗證。', names))
        return self._dash_notify(_('已設為營造廠主管：%s。', names))


    # ── 伺服器動作「轉成後台角色帳號」「改回前台角色帳號」（S2）──────────────────
    # 同一個 user id（工程成員、歷史單據、建立者都掛在這個 id 上），群組一次寫成目標集合（(6, 0, ids)）。
    # 兩步驟驗證（TOTP）兩個方向都**保留**：密鑰綁的是這個人的驗證 App，轉換不換人；前台帳號也能用 TOTP
    # （auth_totp_portal），保留只是讓改回後仍要驗證碼，不會讓誰多看到東西。範圍不合格見 _dash_scope_ok。
    dash_role_origin = fields.Json(
        string='轉換前的帳號設定（改回前台帳號用）', groups='base.group_system', copy=False, readonly=True,
        help='「轉成後台角色帳號」時記下轉換會改到的欄位原值（群組、組織旗標、範圍公司、主要公司、允許公司）；'
             '「改回前台角色帳號」照它逐欄寫回，之後清空。')

    def _dash_require_engineering_manager(self, action_label):
        if not (self.env.su or self.env.user.has_group(MANAGER_GROUP_XMLID)):
            raise AccessError(_('只有工程管理者可以執行「%s」。', action_label))

    def _dash_role_conversion_side(self):
        """前台帳號轉成角色帳號時的方別：'supervision'／'contractor'；判不出來丟 UserError（說明原因）。

        * 監造方：勾監造組織（或在監造組織群組），而且範圍公司、主要公司都不是營造廠——帳號上的營造組織旗標是
          建帳號時被自動勾的（_apply_default_contractor_org），轉換時清掉。
        * 營造方：沒有監造組織標記，範圍公司（或主要公司）是營造廠。
        * 其他（兩邊都有營造廠公司、或什麼標記都沒有）：拒絕。
        """
        self.ensure_one()
        user = self.sudo()
        supervision_mark = user.is_supervision_org or user._dash_in_group(SUPERVISION_ORG_GROUP_XMLID)
        scope = user._dash_role_conversion_scope()
        if supervision_mark and not scope:
            return ROLE_SIDE_SUPERVISION
        if scope and not supervision_mark:
            return ROLE_SIDE_CONTRACTOR
        if supervision_mark:
            raise UserError(_(
                '帳號「%s」勾了監造組織，但範圍公司或主要公司是營造廠，無法判定是監造方還是營造方，請先修正帳號再轉換。',
                user.display_name))
        raise UserError(_(
            '帳號「%s」無法判定方別：沒有勾監造組織，範圍公司與主要公司也都不是營造廠。', user.display_name))

    def _dash_role_conversion_scope(self):
        """營造方的範圍公司：範圍公司是營造廠就用它，否則主要公司是營造廠就用主要公司；都不是回空的。"""
        self.ensure_one()
        user = self.sudo()
        for company in (user.dash_scope_company_id, user.company_id):
            if self._dash_company_is_contractor(company):
                return company
        return self.env['res.company']

    def action_convert_to_role_account(self):
        """前台老闆／主管 → 後台角色帳號（手機能力照舊＋電腦後台唯讀；S2 規格 C）。

        拒絕：不是前台帳號（已經是內部帳號）、層級只有現場人員或定期閱覽者、方別判不出來、自己或系統帳號。
        監造方：允許公司要有非營造廠的公司（後台範圍＝那些監造公司）。轉完以 _dash_check_account_setup 再驗一次。
        """
        self._dash_require_engineering_manager(_('轉成後台角色帳號'))
        for user in self.sudo():
            if user.id == self.env.user.id or user._is_superuser():
                raise UserError(_('不能轉換自己或系統內建帳號。'))
            if not user.share:
                raise UserError(_('帳號「%s」已經是內部帳號，不能再轉換（只轉前台帳號）。', user.display_name))
            level = user._portal_role_level()
            if level not in LEVEL_TO_ROLE_GROUP:
                raise UserError(_(
                    '帳號「%s」的前台角色不是老闆或主管（現場人員、定期閱覽者沒有對應的後台角色帳號），不能轉換。',
                    user.display_name))
            side = user._dash_role_conversion_side()
            vals = {
                'groups_id': [(6, 0, _groups_by_xmlid(self.env, (
                    INTERNAL_USER_GROUP_XMLID, SIDE_TO_ROLE_MARKER[side],
                    LEVEL_TO_ROLE_GROUP[level], INBOX_GROUP_XMLID)).ids)],
                'dash_role_origin': user._dash_role_origin_values(),
            }
            if side == ROLE_SIDE_SUPERVISION:
                # 監造方：營造組織旗標是營造方標記（_dash_is_contractor_side），一定要清掉
                vals['is_contractor_org'] = False
                if not user._role_supervision_company_ids():
                    raise UserError(_(
                        '帳號「%s」的允許公司沒有任何一家監造公司（全是營造廠），轉成監造方角色帳號後什麼都看不到。',
                        user.display_name))
            else:
                vals['dash_scope_company_id'] = user._dash_role_conversion_scope().id
            user.write(vals)
            if side == ROLE_SIDE_CONTRACTOR:
                # 允許公司照營造廠主管的同步規則：營造廠＋所承攬工程的監造公司（S1）
                user._dash_apply_manager_companies(force_main=True)
            user._dash_check_account_setup()
            if not user._is_role_account() or user._role_side() != side:
                raise UserError(_('帳號「%s」轉換後不是預期的角色帳號，已取消。', user.display_name))
        names = '、'.join(self.mapped('display_name'))
        if any(user._dash_totp_missing() for user in self):   # 常數只經 _dash_totp_missing 看（S2 fix3 Z-1）
            return self._dash_notify(_('已轉成後台角色帳號：%s。對方登入後要先在手機首頁的提示啟用兩步驟驗證，才看得到資料。', names))
        return self._dash_notify(_('已轉成後台角色帳號：%s。', names))

    def _dash_role_origin_values(self):
        """轉換前的原值（ROLE_ORIGIN_FIELDS），存進 dash_role_origin；改回時照它逐欄寫回（S2 fix1-P）。"""
        self.ensure_one()
        user = self.sudo()
        origin = {}
        for name in ROLE_ORIGIN_FIELDS:
            value = user[name]
            if isinstance(value, models.BaseModel):
                value = value.ids if user._fields[name].type == 'many2many' else (value.id or False)
            origin[name] = value
        return origin

    def _dash_revert_vals_from_origin(self, origin):
        """完整的轉換紀錄 → 改回要寫的值（逐欄原值）；紀錄裡的群組不像前台帳號、或主要公司已不在就 UserError。"""
        self.ensure_one()
        Groups, Company = self.env['res.groups'].sudo(), self.env['res.company'].sudo()
        groups = Groups.browse(origin['groups_id']).exists()
        if self.env.ref(PORTAL_USER_GROUP_XMLID) not in groups or self.env.ref(INTERNAL_USER_GROUP_XMLID) in groups:
            raise UserError(_('帳號「%s」的轉換紀錄不是前台帳號的群組，不能照紀錄改回，請洽系統管理者。', self.display_name))
        companies = Company.browse(origin['company_ids']).exists()
        main = Company.browse(origin['company_id'] or []).exists()
        if not main or main not in companies:
            raise UserError(_('帳號「%s」轉換前的主要公司已不存在，不能照紀錄改回，請洽系統管理者。', self.display_name))
        return {
            'groups_id': [(6, 0, groups.ids)],
            'is_supervision_org': bool(origin['is_supervision_org']),
            'is_contractor_org': bool(origin['is_contractor_org']),
            'dash_scope_company_id': Company.browse(origin['dash_scope_company_id'] or []).exists().id or False,
            'company_ids': [(6, 0, companies.ids)],
            'company_id': main.id,
        }

    def _dash_revert_vals_derived(self):
        """沒有完整轉換紀錄（直接建成的角色帳號）→ 照層級／方別推；範圍公司、主要公司、允許公司不動。
        S2 fix3-7（審查 simplifier P-1）：拿掉「只記了公司」的舊格式相容路徑（只在 S2 未 commit 時期產生、只有 dev 的測試帳號）。"""
        self.ensure_one()
        level, side = self._role_level_raw(), self._role_side()
        if level not in LEVEL_TO_ROLE_GROUP or not side:
            raise UserError(_(
                '帳號「%s」的角色帳號設定不完整（層級或方別不是恰好一個），請先修正再改回。', self.display_name))
        return {
            'groups_id': [(6, 0, _groups_by_xmlid(self.env, (
                PORTAL_USER_GROUP_XMLID, PORTAL_ROLE_GROUP_BY_LEVEL[level], SIDE_TO_ORG_GROUP[side])).ids)],
            'is_supervision_org': side == ROLE_SIDE_SUPERVISION,
            'is_contractor_org': side == ROLE_SIDE_CONTRACTOR,
        }

    def action_revert_to_portal_role(self):
        """後台角色帳號 → 前台角色帳號（同一個 user id；S2 規格 C 改回；fix1-P 起逐欄可逆）。

        有完整轉換紀錄（dash_role_origin 含 ROLE_ORIGIN_FIELDS 每一欄）：群組、兩個組織旗標、範圍公司、主要公司、
        允許公司照紀錄寫回，改回後與轉換前逐欄相同（含「兩個組織旗標都勾」「營造方範圍公司空白」這種轉換會改到
        旗標或範圍公司的帳號）。沒有完整紀錄（直接建成的角色帳號）：見 _dash_revert_vals_derived。
        share 變回 True、通知方式由核心回到 email；TOTP 不動（理由見本節開頭）。
        """
        self._dash_require_engineering_manager(_('改回前台角色帳號'))
        for user in self.sudo():
            if user.id == self.env.user.id or user._is_superuser():
                raise UserError(_('不能轉換自己或系統內建帳號。'))
            if not user._is_role_account():
                raise UserError(_('帳號「%s」不是後台角色帳號，沒有東西可以改回。', user.display_name))
            origin = user.dash_role_origin or {}
            if set(ROLE_ORIGIN_FIELDS) <= set(origin):
                vals = user._dash_revert_vals_from_origin(origin)
            else:
                vals = user._dash_revert_vals_derived()
            vals['dash_role_origin'] = False
            user.write(vals)
            if not user.share:
                raise UserError(_('帳號「%s」改回後不是前台帳號，已取消。', user.display_name))
        return self._dash_notify(_('已改回前台角色帳號：%s。', '、'.join(self.mapped('display_name'))))

    @api.model
    def _dash_sync_feedback_acl(self):
        """建意見回饋的讀取權（FEEDBACK_ACL_MODELS；只讀、給後台角色帳號的層級群組，老闆隱含主管）。可重跑；回傳新建筆數。"""
        group = self.env.ref(ROLE_MANAGER_XMLID)
        Access = self.env['ir.model.access'].sudo()
        created = 0
        for model_name in FEEDBACK_ACL_MODELS:
            model = self.env['ir.model'].sudo()._get(model_name)
            if not model or Access.search_count([('model_id', '=', model.id), ('group_id', '=', group.id),
                                                 ('name', '=', FEEDBACK_ACL_NAME)]):
                continue
            Access.create({'name': FEEDBACK_ACL_NAME, 'model_id': model.id, 'group_id': group.id,
                           'perm_read': True, 'perm_write': False, 'perm_create': False, 'perm_unlink': False})
            created += 1
        return created

    @api.model
    def _dash_notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': message, 'sticky': False},
        }


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.constrains('users')
    def _check_dash_account_setup(self):
        """從群組表單加人也要擋（res.users 那一側的約束不會因此觸發）。"""
        carriers = _groups_by_xmlid(self.env, CARRIER_GROUP_XMLIDS)
        if not carriers:
            return
        # 帶這兩個群組的帳號很少，直接全檢查（不載入 base.group_user 之類大群組的全部使用者）
        users = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('groups_id', 'in', carriers.ids)])
        users._dash_check_account_setup()


class IrRule(models.Model):
    _inherit = 'ir.rule'

    def _make_access_error(self, operation, records):
        # 營造廠主管／角色帳號沒設兩步驟驗證而被擋下時，訊息直接說明怎麼處理
        error = super()._make_access_error(operation, records)
        user = self.env.user
        if user and user._dash_totp_missing():
            new_error = AccessError(f'{error.args[0]}\n\n{DENY_NOTE_TOTP}')
            if getattr(error, 'context', None):
                new_error.context = error.context
            return new_error
        return error

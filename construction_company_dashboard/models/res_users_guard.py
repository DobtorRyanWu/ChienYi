# -*- coding: utf-8 -*-
"""營造廠主管、控台讀取、後台角色帳號的帳號設定（合約 §2、§3.1、§13-6；角色帳號 S1，2026-11-10）。

* 群組允許清單約束（res.users 與 res.groups 兩邊）：帶「營造廠主管」「控台讀取」或後台角色群組的帳號，
  群組只能是這些群組＋它們隱含的群組閉包＋通知類群組；帶營造廠主管就必須範圍公司合格；
  後台角色帳號另有組合限制（_dash_check_role_setup）。
* 伺服器動作「設為營造廠主管」（工程管理者限定）：一次寫好群組、主要公司、允許公司。
* 允許公司的計算（動作與自動同步共用）：營造公司（範圍公司）＋所承攬工程的所有監造公司；
  主公司＝承攬工程最多的監造公司。
* 兩步驟驗證（auth_totp）：Odoo 18 原生只有 auth_totp_mail_enforce（寄信驗證碼、全站或全員工的設定，
  不分群組、不擋資料），不符合「只對營造廠主管強制、沒設就什麼都看不到」，所以自己做：
  營造廠主管沒有啟用 TOTP 時 _dash_scope_ok() 為 False → rule_scope 對他預設拒絕（框架以外只剩本人的使用者與聯絡人，合約 §0b-16）。
  啟用／改密碼／改語言時區走核心 self-writeable 的 sudo，不受拒寫規則影響（見 tests/test_account_setup.py）。
"""
import logging
from collections import Counter

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.construction_supervision_base.models.res_users import (
    COMPANY_TYPE_CONTRACTOR,
    DASH_CONSOLE_READER_XMLID,
    DASH_CONTRACTOR_MANAGER_XMLID,
    MANAGER_GROUP_XMLID,
    ROLE_BOSS_XMLID,
    ROLE_MANAGER_XMLID,
    ROLE_SUPERVISION_XMLID,
)

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
# 寫了這些欄位，帳號可能從此變成受限帳號（群組、營造組織旗標、範圍公司、主要公司：_dash_is_contractor_side 的標記）
RESTRICTION_MARKER_FIELDS = frozenset({'groups_id', 'is_contractor_org', 'dash_scope_company_id', 'company_id'})
_logger = logging.getLogger(__name__)


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
        其他帳號不要求。"""
        self.ensure_one()
        return ((self._dash_is_contractor_manager() or self._is_role_account())
                and not self.sudo().totp_enabled)

    def _dash_scope_ok(self):
        """範圍公司合格，且（營造廠主管）已啟用兩步驟驗證。

        False → 讀取規則預設拒絕（框架以外只剩本人的使用者與聯絡人，合約 §0b-16）。判定只看帳號本身，不因 env.su 跳過。
        """
        return super()._dash_scope_ok() and not self._dash_totp_missing()

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
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('已設為營造廠主管：%s。提醒對方登入後先啟用兩步驟驗證。',
                             '、'.join(self.mapped('display_name'))),
                'sticky': False,
            },
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

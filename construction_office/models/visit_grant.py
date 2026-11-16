# -*- coding: utf-8 -*-
"""參觀帳號（淞源 2026-11-10 會議 C11）。

淞源：業主或監造臨時要看一下，給一個有期限的帳號；只開照片、和指定給他看的公文，其他都不要讓他看到。
老闆：可以，預設給七天。

做法（預設拒絕）：
* 群組 construction_office.group_visitor 只隱含 base.group_portal，沒有任何業務模型的 ACL。
* 看得到什麼只由本表決定：帳號 × 工程 ×（可不可以看照片、可以看哪幾份公文）。
  專用頁面在 /construction/visit 底下（controllers/portal_visit.py），逐筆對照本表後才以 sudo 取資料。
* 其他網址一律擋（models/ir_http.py）；XML-RPC／JSON-RPC 不收密碼（_rpc_api_keys_only）。
* 有效期沿用帳號的「帳號有效期至」（res.users.portal_valid_until）：過期當下就進不來（每個請求都查），
  每日排程再把帳號停用。沒有設有效期的參觀帳號視為已過期（不會有「永久的參觀帳號」）。
* 參觀帳號不能同時帶前台其他角色或後台帳號的群組（那些群組有業務模型的 ACL，會破壞「只看指定的」）。
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.construction_supervision_base.models.res_users import PORTAL_ROLE_GROUPS
from odoo.addons.construction_supervision_base.utils.local_date import local_today

VISITOR_GROUP = 'construction_office.group_visitor'
DEFAULT_VISIT_DAYS = 7          # 老闆在會中說的預設天數
MAX_VISIT_DAYS = 30             # 參觀帳號最長給幾天（再長就該開正式的閱覽帳號）
INTERNAL_GROUP = 'base.group_user'
PHOTO_MODEL = 'supervision.photo'
DOC_MODEL = 'construction.official.doc'


class ConstructionVisitGrant(models.Model):
    _name = 'construction.visit.grant'
    _description = '參觀帳號授權'
    _order = 'user_id, project_id'
    _rec_name = 'project_id'

    user_id = fields.Many2one(
        'res.users', string='參觀帳號', required=True, index=True, ondelete='cascade',
        context={'active_test': False})
    project_id = fields.Many2one(
        'project.project', string='工程', required=True, index=True, ondelete='cascade')
    allow_photos = fields.Boolean(string='可看照片', default=True, help='這個工程的全部照片')
    official_doc_ids = fields.Many2many(
        DOC_MODEL, 'construction_visit_grant_doc_rel', 'grant_id', 'doc_id', string='可看的公文',
        domain="[('project_id', '=', project_id)]",
        help='只有列在這裡的公文看得到（含附件）；只能挑這個工程的公文')
    valid_until = fields.Date(string='帳號有效期至', related='user_id.portal_valid_until', readonly=True)

    _sql_constraints = [
        ('uniq_user_project', 'unique(user_id, project_id)', '同一個參觀帳號在同一個工程只能有一筆授權'),
    ]

    @api.constrains('user_id')
    def _check_user_is_visitor(self):
        for grant in self:
            if not grant.user_id._is_visit_account():
                raise ValidationError('「%s」不是參觀帳號，不能設定參觀授權。' % grant.user_id.sudo().name)

    def _visit_docs(self):
        """這些授權現在看得到的公文：列在授權上、沒封存，而且「目前」還掛在授權的那個工程上。
        公文事後改掛別的工程（下面的約束只在改授權時檢查），原工程的授權就不再給看（淞源權限審查 low #3）。"""
        docs = self.env[DOC_MODEL].sudo()
        for grant in self:
            docs |= grant.official_doc_ids.filtered(lambda doc: doc.active and doc.project_id == grant.project_id)
        return docs

    @api.constrains('official_doc_ids', 'project_id')
    def _check_docs_belong_to_project(self):
        for grant in self:
            others = grant.sudo().official_doc_ids.filtered(lambda doc: doc.project_id != grant.project_id)
            if others:
                raise ValidationError('可看的公文只能挑「%s」這個工程的：%s'
                                      % (grant.sudo().project_id.name, '、'.join(others.mapped('subject')[:5])))


class ResUsers(models.Model):
    _inherit = 'res.users'

    visit_grant_ids = fields.One2many(
        'construction.visit.grant', 'user_id', string='參觀授權', groups='base.group_user')

    # ── 判斷 ──────────────────────────────────────────────────────────────
    def _is_visit_account(self):
        """參觀帳號（只看原始群組成員資格）。"""
        self.ensure_one()
        return self._dash_in_group(VISITOR_GROUP)

    def _visit_expired(self):
        """參觀帳號過期了沒：有效期那一天還能用，隔天起過期；沒設有效期＝過期。「今天」是台灣日期。"""
        self.ensure_one()
        valid_until = self.sudo().portal_valid_until
        return not valid_until or valid_until < local_today()

    def _visit_grants(self):
        """這個參觀帳號目前有效的授權（sudo 的紀錄；不是參觀帳號、已過期、已停用都回空的）。"""
        self.ensure_one()
        Grant = self.env['construction.visit.grant'].sudo()
        if not self.sudo().active or not self._is_visit_account() or self._visit_expired():
            return Grant.browse()
        return Grant.search([('user_id', '=', self.id), ('project_id.active', '=', True)])

    # ── 約束與預設 ────────────────────────────────────────────────────────
    @api.constrains('groups_id')
    def _check_visit_account_is_pure(self):
        """參觀帳號不能混其他角色：那些群組帶業務模型的 ACL。"""
        mixed = [INTERNAL_GROUP] + [xmlid for _level, xmlid in PORTAL_ROLE_GROUPS]
        for user in self:
            if user._is_visit_account() and any(user._dash_in_group(xmlid) for xmlid in mixed):
                raise ValidationError(
                    '「%s」是參觀帳號，不能同時是前台其他角色（閱覽者、現場人員、主管、老闆）或後台帳號。'
                    '要給更多權限請另開正式帳號。' % user.sudo().name)

    def _apply_visit_default_validity(self):
        """參觀帳號沒填有效期時帶今天＋DEFAULT_VISIT_DAYS。"""
        default_date = local_today() + timedelta(days=DEFAULT_VISIT_DAYS)
        for user in self:
            if user._is_visit_account() and not user.sudo().portal_valid_until:
                user.sudo().portal_valid_until = default_date

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._apply_visit_default_validity()
        return users

    def write(self, vals):
        result = super().write(vals)
        if 'groups_id' in vals or any(key.startswith(('in_group_', 'sel_groups_')) for key in vals):
            self._apply_visit_default_validity()
        return result

    def _ensure_construction_employee(self):
        """參觀帳號不填任何表：不要替它建員工資料。"""
        return super(ResUsers, self.filtered(lambda user: not user._is_visit_account()))._ensure_construction_employee()

    # ── 到期、RPC ─────────────────────────────────────────────────────────
    @api.model
    def _cron_deactivate_expired_portal_users(self):
        """每日排程：除了原本的定期閱覽者，也停用過期（或沒設有效期）的參觀帳號。"""
        result = super()._cron_deactivate_expired_portal_users()
        group = self.env.ref(VISITOR_GROUP, raise_if_not_found=False)
        if group:
            expired = self.search([
                ('groups_id', 'in', group.id), ('active', '=', True),
                '|', ('portal_valid_until', '=', False), ('portal_valid_until', '<', local_today())])
            if expired:
                expired.write({'active': False})
        return result

    def _rpc_api_keys_only(self):
        """參觀帳號的 XML-RPC／JSON-RPC 不收密碼（它本來就不該用程式介面；網頁那一側另有網址白名單）。"""
        self.ensure_one()
        return self._is_visit_account() or super()._rpc_api_keys_only()

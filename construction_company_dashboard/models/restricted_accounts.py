# -*- coding: utf-8 -*-
"""受限帳號唯一清單（S3-C，2026-11-11；S3 fix1 簡化＋fail-closed）：解除安裝硬擋（hooks.uninstall_hook）、
換版工具 qd.py 的降版硬擋（已改成呼叫本函式，odoo18-docker 34d6265）、runbook 共用。

res.users.dash_restricted_account_logins()：
* 公開方法（RPC 可呼叫）、@api.model、唯讀；系統管理者或 sudo（hook）才能叫，其他一律 AccessError。
* 回傳 {'internal': [login, …], 'portal': [login, …]}：res.users._dash_is_restricted()（全系統唯一一份判斷，
  含前台營造帳號）為真的帳號，含已封存（active_test=False），依 login 排序；share（前台）分到 portal，其餘 internal；
  超級使用者排除。
* fail-closed：判斷函式靠 5 個受限群組（res_users_guard.CARRIER_GROUP_XMLIDS）認人，任一個 xmlid 找不到
  （半套解除安裝、手動刪）就認不全 → UserError，不回一份殘缺的清單讓人以為可以解除安裝／降版。
"""
from odoo import SUPERUSER_ID, _, api, models
from odoo.exceptions import AccessError, UserError

from .res_users_guard import CARRIER_GROUP_XMLIDS

BUCKET_INTERNAL = 'internal'
BUCKET_PORTAL = 'portal'


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def dash_restricted_account_logins(self):
        """受限帳號的 login 清單 {'internal': [...], 'portal': [...]}（含已封存、依 login 排序；見檔頭）。"""
        if not (self.env.su or self.env.user._is_system()):
            raise AccessError(_('只有系統管理者可以列出受限帳號清單（dash_restricted_account_logins）。'))
        missing = [xmlid for xmlid in CARRIER_GROUP_XMLIDS if not self.env.ref(xmlid, raise_if_not_found=False)]
        if missing:
            raise UserError(_('受限群組定義不完整，無法確認受限帳號：找不到 %(xmlids)s。先把群組資料修好再列清單'
                              '（README_ROLE_ACCOUNTS.md）。', xmlids='、'.join(missing)))
        users = self.sudo().with_context(active_test=False).search([('id', '!=', SUPERUSER_ID)])
        restricted = users.filtered(lambda user: user._dash_is_restricted())
        return {
            BUCKET_INTERNAL: sorted(restricted.filtered(lambda user: not user.share).mapped('login')),
            BUCKET_PORTAL: sorted(restricted.filtered('share').mapped('login')),
        }

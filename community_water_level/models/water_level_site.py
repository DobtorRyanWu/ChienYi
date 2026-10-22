# -*- coding: utf-8 -*-
"""監測場域：社區這一側。

社區場域指向 res.partner（管委會／物業公司／學校機關），一個社區一場域、底下可多個蓄水池。
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.water_level_core.models.water_level_device import LEVEL_BASIC, SERVICE_LEVEL_RANK
from odoo.addons.water_level_core.models.water_level_site import SITE_TYPE_COMMUNITY

_logger = logging.getLogger(__name__)


class WaterLevelSite(models.Model):
    _inherit = 'water.level.site'

    owner_partner_id = fields.Many2one(
        'res.partner', string='場域擁有者',
        ondelete='restrict', index=True, tracking=True,
        help='場域類型為「社區」時必填：管理委員會、物業管理公司或學校機關。')

    # 前台可見性走成員制，與 project.project.member_user_ids 同一個概念、同一種 rule 形狀。
    # 刻意不用 owner_partner_id 比對：整個 addons 目錄從來沒有拿 partner 做過權限判斷，
    # 為了社區另開一套只有這裡有的機制，日後沒人記得它的存在。
    # 管委會本來就不只一個人（主委、總幹事、物業經理各一個帳號），成員制天生吃這種情況。
    member_user_ids = fields.Many2many(
        'res.users', 'water_level_site_member_rel', 'site_id', 'user_id',
        string='前台成員',
        help='可以在前台看到這個場域的使用者。工程場域不必填——它的可見性走工程案件的成員。')

    tank_ids = fields.One2many(
        'water.level.tank', 'site_id', string='蓄水池')

    # 方案等級設在社區、設備跟著社區（2026-10-21 使用者定案：一個社區一份合約）。
    # core 的方案檢查點（影像 402、即時告警、雜湊鏈 cron）讀的是設備等級，所以改這裡要同步到每一台設備，
    # 設備端再由約束守住「不能和場域不一樣」——兩邊不一致時前台說有、core 說沒有。
    service_level = fields.Selection(
        selection='_selection_service_level', string='方案等級',
        default=LEVEL_BASIC, required=True, tracking=True,
        help='社區場域用：管委會簽的方案。旗下每一台監測站都跟著這個等級，不必逐台設定。')

    @api.model
    def _selection_service_level(self):
        # 標籤沿用 core 設備欄位那一份，不另寫一套（DM 改名時只改一處）
        return self.env['water.level.device']._fields['service_level'].selection

    @api.constrains('site_type', 'owner_partner_id')
    def _check_community_owner(self):
        """社區場域一定要有擁有者（管委會／物業）；其他類型（工程）不准填。"""
        for site in self:
            if site.site_type == SITE_TYPE_COMMUNITY and not site.owner_partner_id:
                raise ValidationError(_('社區類型的場域必須指定場域擁有者（管委會／物業公司）。'))
            if site.site_type != SITE_TYPE_COMMUNITY and site.owner_partner_id:
                raise ValidationError(_('工程案件類型的場域不應該填場域擁有者。'))

    def write(self, vals):
        res = super().write(vals)
        if {'service_level', 'site_type'} & set(vals):
            self._community_sync_device_levels()
        return res

    def _community_sync_device_levels(self):
        """把社區場域的等級寫到旗下每一台設備——含停用的（重新啟用時才不會和場域不一樣）。"""
        devices = self.env['water.level.device'].sudo().with_context(active_test=False)
        for site in self.filtered(lambda s: s.site_type == SITE_TYPE_COMMUNITY):
            stale = devices.search([('site_id', '=', site.id), ('service_level', '!=', site.service_level)])
            if stale:
                stale.write({'service_level': site.service_level})

    def _community_level_at_least(self, level):
        """這個社區的方案含不含 `level` 以上的功能。路由與模板共用這一支，門檻只寫在呼叫端。"""
        self.ensure_one()
        return SERVICE_LEVEL_RANK.get(self.service_level, 0) >= SERVICE_LEVEL_RANK[level]

    @api.model
    def _community_migrate_service_levels(self):
        """既有庫升級（18.0.4.0.0）：每個社區場域取旗下（含停用）設備的最高等級，沒有設備＝基本。

        取最高是使用者定的「不讓客戶掉功能」。寫回場域會經 write 同步到每一台設備。
        回傳 {場域 id: (遷移前場域等級, 遷移後)}，post-migrate 印進 log 留底。
        """
        devices = self.env['water.level.device'].sudo().with_context(active_test=False)
        result = {}
        for site in self.sudo().with_context(active_test=False).search([('site_type', '=', SITE_TYPE_COMMUNITY)]):
            levels = devices.search([('site_id', '=', site.id)]).mapped('service_level')
            target = max(levels, key=SERVICE_LEVEL_RANK.get, default=LEVEL_BASIC)
            result[site.id] = (site.service_level, target)
            # 值沒變也照寫：write 一律經過上面的覆寫同步設備，場域原本就等於 target 時設備仍可能不一致
            site.write({'service_level': target})
        return result

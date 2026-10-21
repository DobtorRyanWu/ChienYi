# -*- coding: utf-8 -*-
"""監測站：工程案件這一側（project_id 與後台依工程分群的排序）。"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WaterLevelDevice(models.Model):
    _inherit = 'water.level.device'
    # 後台清單依工程案件分群看；核心預設是 site_id, seq, id
    _order = 'project_id, seq, id'

    # ⚠️ ondelete 從 cascade 改成 restrict：cascade 會讓「刪工程案件」在資料庫層
    #    連坐刪光該案所有水位紀錄，而且完全不報錯，直接繞過 unlink() 的保護。
    #    這套系統對客戶承諾「依法保存三年」，這條路徑必須堵死。
    # ⚠️ 這是實體欄位不是 related：改成 related store 會讓 reading.project_id
    #    （也是 stored related）跟著級聯重算上千萬列，而且 ingest 的原生 SQL
    #    要明寫這個欄位（見 _ingest_extra_columns）。值由 site 帶入，一致性靠下面的 constrains 保證。
    project_id = fields.Many2one(
        'project.project', string='工程案件',
        ondelete='restrict', index=True, tracking=True,
        help='由監測場域帶入。社區場域的設備此欄為空。')

    @api.constrains('site_id', 'project_id')
    def _check_site_project_consistency(self):
        """設備的 project_id 必須與場域一致；社區場域的設備不得有 project_id。"""
        for device in self:
            expected = device.site_id.project_id
            if device.project_id != expected:
                raise ValidationError(_(
                    '設備「%(name)s」的工程案件與場域「%(site)s」不一致。'
                    '這個欄位由場域帶入，不要手動改。',
                    name=device.name, site=device.site_id.name))

    @api.onchange('site_id')
    def _onchange_site_id_project(self):
        self.project_id = self.site_id.project_id

    @api.model_create_multi
    def create(self, vals_list):
        """沒帶 project_id 就從場域補上，帶錯的由 constrains 擋下。"""
        sites = self.env['water.level.site'].browse([
            vals.get('site_id') for vals in vals_list if vals.get('site_id')])
        by_id = {site.id: site for site in sites}
        for vals in vals_list:
            site = by_id.get(vals.get('site_id'))
            if site and 'project_id' not in vals:
                vals['project_id'] = site.project_id.id or False
        return super().create(vals_list)

    def _ingest_extra_columns(self):
        """reading.project_id 是 stored related，ingest 走原生 SQL 不會自動填，要明寫。

        社區設備沒有工程案件。Odoo 的空 M2O 回傳 False，直接塞進 integer 欄位
        會變成 boolean 型別不符——要轉成 None 讓它進 NULL。
        """
        extra = super()._ingest_extra_columns()
        extra['project_id'] = self.project_id.id or None
        return extra

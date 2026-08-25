# -*- coding: utf-8 -*-
"""監測場域。

v2 新增的一層，用來吸收「社區蓄水池」與「工程案件河川／排水」的差異，
讓下游（設備、讀值、圖表、稽核）不必到處寫 if 社區 else 工程。

兩種場域的歸屬對象不同：
* 工程：指向 project.project（工程案件），一案一場域。
* 社區：指向 res.partner（管委會／物業公司／學校機關），一個社區一場域、底下可多個蓄水池。

刪除策略一律 restrict。這是承諾「依法保存兩年」的系統，任何「刪 A 連坐刪掉水位紀錄」
的路徑都必須堵死——包含資料庫層的 ON DELETE CASCADE，它會繞過 model 層的 unlink 保護。
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# DM 承諾的保存期間（天）
DEFAULT_RETENTION_DAYS = 730

LATITUDE_LIMIT = 90.0
LONGITUDE_LIMIT = 180.0

SITE_TYPE_PROJECT = 'project'
SITE_TYPE_COMMUNITY = 'community'


class WaterLevelSite(models.Model):
    _name = 'water.level.site'
    _description = '監測場域'
    _inherit = ['mail.thread']
    _order = 'site_type, name'

    name = fields.Char(string='場域名稱', required=True, tracking=True)
    code = fields.Char(string='場域代號', copy=False)
    active = fields.Boolean(string='啟用', default=True)

    site_type = fields.Selection(
        [(SITE_TYPE_PROJECT, '工程案件'),
         (SITE_TYPE_COMMUNITY, '社區')],
        string='場域類型', required=True, default=SITE_TYPE_PROJECT, tracking=True)

    project_id = fields.Many2one(
        'project.project', string='工程案件',
        ondelete='restrict', index=True, tracking=True,
        help='場域類型為「工程案件」時必填。建立後不可更改。')
    owner_partner_id = fields.Many2one(
        'res.partner', string='場域擁有者',
        ondelete='restrict', index=True, tracking=True,
        help='場域類型為「社區」時必填：管理委員會、物業管理公司或學校機關。')

    retention_days = fields.Integer(
        string='保存天數', default=DEFAULT_RETENTION_DAYS,
        help='對客戶承諾的資料保存期間。到期只會通知，不會自動刪除。')

    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))
    address = fields.Char(string='地址')

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
    device_ids = fields.One2many(
        'water.level.device', 'site_id', string='監測設備')
    device_count = fields.Integer(
        string='設備數', compute='_compute_device_count')

    # ==================== Compute ====================

    def _compute_device_count(self):
        self.device_count = 0
        saved = self.filtered(lambda s: isinstance(s.id, int))
        if not saved:
            return
        groups = self.env['water.level.device']._read_group(
            [('site_id', 'in', saved.ids)],
            groupby=['site_id'],
            aggregates=['__count'],
        )
        counts = {site.id: count for site, count in groups}
        for site in saved:
            site.device_count = counts.get(site.id, 0)

    # ==================== Constrains ====================

    @api.constrains('site_type', 'project_id', 'owner_partner_id')
    def _check_owner(self):
        """場域類型與歸屬對象必須對得起來，不能兩邊都填或兩邊都空。"""
        for site in self:
            if site.site_type == SITE_TYPE_PROJECT:
                if not site.project_id:
                    raise ValidationError(_('工程案件類型的場域必須指定工程案件。'))
                if site.owner_partner_id:
                    raise ValidationError(_('工程案件類型的場域不應該填場域擁有者。'))
            else:
                if not site.owner_partner_id:
                    raise ValidationError(_('社區類型的場域必須指定場域擁有者（管委會／物業公司）。'))
                if site.project_id:
                    raise ValidationError(_('社區類型的場域不應該綁工程案件。'))

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        """比照既有慣例：0 視為未填，放行。"""
        for site in self:
            if site.latitude and not -LATITUDE_LIMIT <= site.latitude <= LATITUDE_LIMIT:
                raise ValidationError(_('緯度必須介於 -90 到 90 之間。'))
            if site.longitude and not -LONGITUDE_LIMIT <= site.longitude <= LONGITUDE_LIMIT:
                raise ValidationError(_('經度必須介於 -180 到 180 之間。'))

    def write(self, vals):
        """project_id 建立後禁改。

        設備上的 project_id 是實體欄位（不是 related），靠 constrains 與場域保持一致；
        場域換工程等於底下所有設備與讀值的歸屬瞬間改變，那是遷移不是編輯。
        """
        if 'project_id' in vals:
            for site in self:
                if site.project_id and site.project_id.id != vals['project_id']:
                    raise ValidationError(_(
                        '場域「%s」已綁定工程案件，不可更改。'
                        '要改歸屬請走資料遷移，不要直接編輯。', site.name))
        return super().write(vals)

    def init(self):
        """一個工程案件只能有一個場域。

        用部分唯一索引而非 _sql_constraints：社區場域的 project_id 是 NULL，
        普通 unique 對多個 NULL 不會擋，但也不該讓 NULL 參與這個約束。
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS water_level_site_project_uniq
            ON water_level_site (project_id)
            WHERE site_type = 'project' AND project_id IS NOT NULL
        """)

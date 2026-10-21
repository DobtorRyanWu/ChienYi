# -*- coding: utf-8 -*-
"""監測場域：工程案件這一側。

工程場域指向 project.project，一案一場域。刪除策略 restrict——這是承諾「依法保存三年」
的系統，「刪工程案件連坐刪掉水位紀錄」的路徑必須堵死（含資料庫層的 ON DELETE CASCADE，
它會繞過 model 層的 unlink 保護）。
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.water_level_core.models.water_level_site import SITE_TYPE_PROJECT


class WaterLevelSite(models.Model):
    _inherit = 'water.level.site'

    project_id = fields.Many2one(
        'project.project', string='工程案件',
        ondelete='restrict', index=True, tracking=True,
        help='場域類型為「工程案件」時必填。建立後不可更改。')

    @api.constrains('site_type', 'project_id')
    def _check_project_owner(self):
        """工程場域一定要綁工程案件；其他類型（社區）不准綁。"""
        for site in self:
            if site.site_type == SITE_TYPE_PROJECT and not site.project_id:
                raise ValidationError(_('工程案件類型的場域必須指定工程案件。'))
            if site.site_type != SITE_TYPE_PROJECT and site.project_id:
                raise ValidationError(_('社區類型的場域不應該綁工程案件。'))

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
        super().init()
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS water_level_site_project_uniq
            ON water_level_site (project_id)
            WHERE site_type = 'project' AND project_id IS NOT NULL
        """)

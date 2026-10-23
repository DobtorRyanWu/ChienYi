# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionContractMaterial(models.Model):
    """案件契約材料清單。

    來源是 PCCES 契約檔的「契約資源統計表」。每案一份清單；其中 is_key=True 的
    「重要材料」會在建立施工日誌時自動帶入第三節「工地材料管理概況」，
    現場只需要填本日數量，累計由 daily.log.material 顯式重算。
    """
    _name = 'construction.contract.material'
    _description = '契約材料清單'
    _order = 'project_id, sequence, id'

    project_id = fields.Many2one(
        'project.project', string='工程案件',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('排序', default=10)
    code = fields.Char('資源代碼')
    name = fields.Char('材料名稱', required=True)
    unit = fields.Char('單位')
    contract_qty = fields.Float('契約數量', digits=(16, 4))
    unit_price = fields.Float('單價', digits=(16, 4))
    amount = fields.Float('複價', digits=(16, 2))
    is_key = fields.Boolean(
        '重要材料', default=False,
        help='勾選後，新建的施工日誌會自動帶入這一項（現場只填本日數量）。')
    active = fields.Boolean('啟用', default=True)
    note = fields.Char('備註')
    company_id = fields.Many2one(
        related='project_id.company_id', store=True, string='公司')

    _sql_constraints = [
        ('project_code_uniq', 'unique(project_id, code)',
         '同一案件內的資源代碼不可重複！'),
    ]

    @api.constrains('project_id')
    def _check_project_vs_linked_rows(self):
        # 已有日誌連結的清單項不可改所屬工程：舊案日誌的列會被算進新案的累計（不同公司時還會跨公司）
        rows = self.env['daily.log.material'].sudo().search([('catalog_item_id', 'in', self.ids)])
        wrong = rows.filtered(lambda r: r.catalog_item_id.project_id != r.daily_log_id.supervision_project_id)
        if wrong:
            raise ValidationError('「%s」已有其他工程的日誌在用，不能改所屬工程。'
                                  % '、'.join(wrong.catalog_item_id.mapped('name')))

    def action_apply_to_open_logs(self):
        """把所選清單項所屬案件的「重要材料」補到每張未鎖定的日誌。

        已鎖定（超過 14 天且未解鎖）的日誌略過；已有同一清單項的日誌不重複帶入。
        """
        sheets = self.env['daily.log.sheet'].search([('supervision_project_id', 'in', self.project_id.ids)])
        # _load_key_materials 用 sudo 建列：先確認呼叫者對這些日誌有寫入權
        sheets.check_access('write')
        locked = sheets.filtered(lambda s: s._is_edit_locked())
        added = (sheets - locked)._load_key_materials()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '套用完成',
                'message': '補上重要材料 %d 列；已鎖定而略過的日誌 %d 張。' % (added, len(locked)),
                'type': 'success',
                'sticky': False,
            },
        }

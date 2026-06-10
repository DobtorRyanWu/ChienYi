# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_standard_work_item = fields.Boolean(
        string='標準工項',
        default=False,
        index=True,
        help='標記此產品為標準工項，顯示於標準工項管理畫面')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    supervision_task_ids = fields.One2many(
        'project.task', 'product_id',
        string='使用此標準工項的契約工項')

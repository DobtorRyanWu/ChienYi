# -*- coding: utf-8 -*-
"""舊版文件分類的 xmlid 不在 XML 裡，noupdate 必須是 True。

是 False 的話，核心 _process_end 每次 -u 都會 unlink 它們，撞上系統分類的刪除守衛，
整次升級在最後一步失敗。
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestLegacyCategoryUpgrade(TransactionCase):

    def test_legacy_xmlids_are_noupdate(self):
        Category = self.env['supervision.document.category']
        rows = self.env['ir.model.data'].search([
            ('module', '=', 'construction_supervision_base'),
            ('model', '=', 'supervision.document.category'),
            ('name', 'in', list(Category._LEGACY_CATEGORY_XMLIDS)),
        ])
        self.assertFalse(rows.filtered(lambda r: not r.noupdate).mapped('name'))

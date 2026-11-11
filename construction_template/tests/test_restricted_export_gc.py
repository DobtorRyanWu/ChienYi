# -*- coding: utf-8 -*-
"""S2 fix2-V（使用者 11-11）：唯讀帳號的匯出檔（EXPORT_ATTACHMENT_MARKER、沒掛單據）超過保留時間就由每日 autovacuum 清掉。

四種附件：舊的有標記孤兒（要刪）、新的有標記孤兒、舊的沒標記孤兒、舊的有標記但掛單據（後台人員的匯出）——只有第一種被刪。
建立時間用 SQL 改成過去（ORM 不讓寫 create_date）。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.models.template_export_mixin import EXPORT_ATTACHMENT_MARKER

# 改成「過去」的時間：比保留時間（1 天）多一天，避免邊界
OLD_AGE = timedelta(days=2)


@tagged('post_install', '-at_install', 'construction_template')
class TestRestrictedExportGc(TransactionCase):

    def _attachment(self, name, marker=True, res_model=False, age=None):
        vals = {'name': name, 'raw': b'S2V', 'description': EXPORT_ATTACHMENT_MARKER if marker else 'S2V 一般附件'}
        if res_model:
            vals.update(res_model='res.partner', res_id=self.env.user.partner_id.id)
        attachment = self.env['ir.attachment'].sudo().create(vals)
        if age:
            self.env.cr.execute('UPDATE ir_attachment SET create_date = %s WHERE id = %s',
                                [fields.Datetime.now() - age, attachment.id])
        return attachment

    def test_only_old_marked_orphans_are_removed(self):
        old_orphan = self._attachment('s2v-old-orphan.xlsx', age=OLD_AGE)
        new_orphan = self._attachment('s2v-new-orphan.xlsx')
        old_unmarked = self._attachment('s2v-old-unmarked.xlsx', marker=False, age=OLD_AGE)
        old_attached = self._attachment('s2v-old-attached.xlsx', res_model=True, age=OLD_AGE)
        self.env.invalidate_all()
        removed = self.env['ir.attachment']._gc_restricted_template_exports()
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(old_orphan.exists(), '超過保留時間、有標記、沒掛單據：刪')
        self.assertTrue(new_orphan.exists(), '1 天內的匯出檔：留著')
        self.assertTrue(old_unmarked.exists(), '沒有標記的附件：不碰')
        self.assertTrue(old_attached.exists(), '掛在單據上的附件（含後台人員的匯出）：不碰')


@tagged('post_install', '-at_install', 'construction_template')
class TestBackofficeExportReplace(TransactionCase):
    """S2 fix2-Y（使用者 11-11「改成只刪上一次匯出留下的副本」）：後台人員的匯出檔也帶 EXPORT_ATTACHMENT_MARKER，
    重匯只刪同一筆單據上、同名、有標記的；使用者上傳的同名附件永遠不碰。"""

    def test_reexport_keeps_uploaded_same_name(self):
        self.assertFalse(self.env.user._dash_is_restricted_internal(), '前提：後台人員那條路')
        project = self.env['project.project'].create({'name': 'S2Y 匯出測試', 'code': 'S2Y-1'})
        name = 's2y-匯出.xlsx'
        uploaded = self.env['ir.attachment'].create({
            'name': name, 'raw': b'S2Y uploaded', 'res_model': project._name, 'res_id': project.id})
        first = project._create_export_attachment(name, b'S2Y export 1')
        second = project._create_export_attachment(name, b'S2Y export 2')
        self.assertTrue(uploaded.exists(), '使用者上傳的同名附件還在')
        self.assertFalse(first.exists(), '上一次匯出留下的副本被取代')
        exports = self.env['ir.attachment'].search([('res_model', '=', project._name), ('res_id', '=', project.id),
                                                     ('description', '=', EXPORT_ATTACHMENT_MARKER)])
        self.assertEqual(exports, second, '匯出副本只剩一份且有標記')
        self.assertEqual(second.raw, b'S2Y export 2')

# -*- coding: utf-8 -*-
"""seed_default_templates 的覆蓋守衛（3.6.0）。

升級時 migration 會換系統預設樣板的檔。2.5.0 以前是整批重灌——系統裡有人換過的預設樣板
會被 repo 版默默蓋掉、舊附件刪掉，沒有備份。現在只在既有附件是「已知出貨版」時才換。
"""

import base64

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.hooks import seed_default_templates

TTYPE = 'daily_log_c1'


@tagged('post_install', '-at_install', 'construction_template')
class TestSeedGuard(TransactionCase):

    def _default(self):
        return self.env['document.template'].search([
            ('template_type', '=', TTYPE), ('is_default', '=', True)])

    def test_customized_default_is_not_overwritten(self):
        tmpl = self._default()
        self.assertEqual(len(tmpl), 1, '測資前提：dev 有一筆系統預設 c1')
        tmpl.attachment_id.write({'datas': base64.b64encode(b'customized by someone')})
        att, checksum = tmpl.attachment_id, tmpl.attachment_id.checksum
        seed_default_templates(self.env, types=(TTYPE,), replaceable={TTYPE: {'0' * 40}})
        self.assertEqual(tmpl.attachment_id, att)
        self.assertEqual(tmpl.attachment_id.checksum, checksum)

    def test_shipped_default_is_replaced(self):
        tmpl = self._default()
        old_att = tmpl.attachment_id
        seed_default_templates(self.env, types=(TTYPE,),
                               replaceable={TTYPE: {old_att.checksum}})
        self.assertNotEqual(tmpl.attachment_id, old_att)
        self.assertFalse(old_att.exists())

    def test_archived_duplicate_is_left_alone(self):
        tmpl = self._default()
        tmpl.write({'active': False})
        att = tmpl.attachment_id
        seed_default_templates(self.env, types=(TTYPE,), replaceable={TTYPE: {att.checksum}})
        self.assertEqual(tmpl.attachment_id, att)
        self.assertEqual(self.env['document.template'].with_context(active_test=False).search_count(
            [('template_type', '=', TTYPE), ('is_default', '=', True)]), 1)

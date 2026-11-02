# -*- coding: utf-8 -*-
"""3.8.2 migration：舊版出貨的預設樣板換成去識別化的新版，被人換過的不動（T5-4）。"""
import base64
import hashlib
import importlib.util
import os

from odoo.tests.common import TransactionCase, tagged

from .common import blank_template

MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '18.0.3.8.2', 'post-migrate.py')


def _load():
    spec = importlib.util.spec_from_file_location('mig_3_8_2', MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha1_of_blank(ttype, ext):
    with open(blank_template('%s.%s' % (ttype, ext)), 'rb') as fp:
        return hashlib.sha1(fp.read()).hexdigest()


@tagged('post_install', '-at_install', 'construction_template')
class TestSeed382Migration(TransactionCase):

    def _default(self, ttype):
        return self.env['document.template'].search([
            ('template_type', '=', ttype), ('is_default', '=', True)], limit=1)

    def test_replaceable_lists_old_versions_and_excludes_new(self):
        mod = _load()
        self.assertIn('material_test', mod.REPLACEABLE)
        for ttype, checksums in mod.REPLACEABLE.items():
            ext = 'docx' if ttype in mod.DOCX_TYPES else 'xlsx'
            self.assertTrue(checksums, ttype)
            self.assertNotIn(_sha1_of_blank(ttype, ext), checksums,
                             '%s：新版不該列在可被覆蓋的舊版裡' % ttype)

    def test_shipped_old_version_is_replaced_and_customized_is_not(self):
        mod = _load()
        old_t, custom_t = 'material_test', 'invoice_detail'
        old_tmpl, custom_tmpl = self._default(old_t), self._default(custom_t)
        # 舊版：塞一份內容不同的檔，並把它的 checksum 登記成「出貨過的舊版」
        fake_old = b'fake shipped version'
        old_tmpl.attachment_id.write({'datas': base64.b64encode(fake_old)})
        mod.REPLACEABLE[old_t].add(hashlib.sha1(fake_old).hexdigest())
        # 被人換過：內容不在清單裡
        custom_tmpl.attachment_id.write({'datas': base64.b64encode(b'customized by someone')})
        custom_att = custom_tmpl.attachment_id
        custom_sum = custom_att.checksum
        self.env.flush_all()
        mod.migrate(self.env.cr, '18.0.3.8.1')
        self.env.invalidate_all()
        self.assertEqual(old_tmpl.attachment_id.checksum, _sha1_of_blank(old_t, 'docx'))
        self.assertEqual(custom_tmpl.attachment_id, custom_att)
        self.assertEqual(custom_tmpl.attachment_id.checksum, custom_sum)
        for tmpl in (old_tmpl, custom_tmpl):
            self.assertFalse(tmpl.attachment_id.public)
            self.assertEqual(tmpl.attachment_id.res_id, tmpl.id)

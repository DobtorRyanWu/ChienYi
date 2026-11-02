# -*- coding: utf-8 -*-
"""3.8.1 migration：升級上來的庫補灌「自主檢查表（單張）」系統預設樣板。

直接呼叫 migration 的 migrate()，證明升級路徑真的補得回來（不是只測 seed 函式）。
"""
import importlib.util
import os

from odoo.tests.common import TransactionCase, tagged

TTYPE = 'self_inspection_form'
MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '18.0.3.8.1', 'post-migrate.py')


def _run_migration(env):
    spec = importlib.util.spec_from_file_location('mig_3_8_1', MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.migrate(env.cr, '18.0.3.8.0')


@tagged('post_install', '-at_install', 'construction_template')
class TestSeedSelfInspectionMigration(TransactionCase):

    def _defaults(self):
        return self.env['document.template'].with_context(active_test=False).search([
            ('template_type', '=', TTYPE), ('is_default', '=', True)])

    def test_missing_default_is_recreated(self):
        self._defaults().unlink()
        self.assertEqual(len(self._defaults()), 0)
        _run_migration(self.env)
        created = self._defaults()
        self.assertEqual(len(created), 1)
        self.assertTrue(created.attachment_id.raw)

    def test_existing_default_is_not_overwritten_or_duplicated(self):
        if not self._defaults():
            _run_migration(self.env)
        tmpl = self._defaults()
        self.assertEqual(len(tmpl), 1)
        att, checksum = tmpl.attachment_id, tmpl.attachment_id.checksum
        _run_migration(self.env)
        self.assertEqual(self._defaults(), tmpl)
        self.assertEqual(tmpl.attachment_id, att)
        self.assertEqual(tmpl.attachment_id.checksum, checksum)

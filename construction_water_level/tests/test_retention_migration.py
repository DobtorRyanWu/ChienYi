# -*- coding: utf-8 -*-
"""18.0.2.8.0 migration：保存期間由兩年改三年，只改「還停在舊預設 730」的場域。

客戶合約另外議定的天數不能被蓋掉。（新建場域預設 1095 的那一半在 water_level_core 測。）
這支 migration 屬於 construction_water_level 的升級歷史（2.x 時整套水位都在這個模組），
所以 2026-10 拆模組時跟著留在這裡。
"""

import importlib.util
import os

from odoo.tests import common, tagged

THREE_YEARS_DAYS = 1095
OLD_DEFAULT_DAYS = 730
CUSTOM_DAYS = 400


def _load_migration():
    """migration 目錄名含句點，不能用一般 import。"""
    path = os.path.join(os.path.dirname(__file__), '..', 'migrations',
                        '18.0.2.8.0', 'post-migration.py')
    spec = importlib.util.spec_from_file_location('wl_mig_2_8_0', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestWaterLevelRetentionMigration(common.TransactionCase):

    def _site(self, name, **vals):
        project = self.env['project.project'].create({'name': name})
        return self.env['water.level.site'].create(dict({
            'name': name, 'site_type': 'project', 'project_id': project.id,
        }, **vals))

    def test_migration_only_moves_old_default(self):
        old = self._site('測試工程（舊預設）', retention_days=OLD_DEFAULT_DAYS)
        custom = self._site('測試工程（合約另議）', retention_days=CUSTOM_DAYS)
        self.env.flush_all()

        _load_migration().migrate(self.env.cr, '18.0.2.7.1')
        self.env.invalidate_all()

        self.assertEqual(old.retention_days, THREE_YEARS_DAYS)
        self.assertEqual(custom.retention_days, CUSTOM_DAYS, '合約另議的天數不得被 migration 蓋掉')

# -*- coding: utf-8 -*-
"""保存期間：三年（1095 天）。

**這個測試在防什麼**

新北市政府水利局 115.10.02 函（新北水河計字第1151900632號）要求透水保水義務人的
監測資料等佐證「保存期限至少 3 年」。DM 原本寫「依法保存兩年」，系統預設 730 天——
對新北客戶不成立。2026-10-07 決定 DM 與系統一起改成三年。

兩件事要釘住：
1. 新建場域的預設保存天數是 1095。
2. 18.0.2.8.0 migration 只改「還停在舊預設 730」的場域；客戶合約另外議定的天數不能被蓋掉。
"""

import importlib.util
import os

from odoo.tests import common, tagged

from odoo.addons.construction_water_level.models.water_level_site import (
    DEFAULT_RETENTION_DAYS,
)

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
class TestWaterLevelRetention(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env['res.partner'].create({'name': '測試管委會（保存期）'})

    def _site(self, name, **vals):
        return self.env['water.level.site'].create(dict({
            'name': name, 'site_type': 'community', 'owner_partner_id': self.owner.id,
        }, **vals))

    def test_default_is_three_years(self):
        self.assertEqual(DEFAULT_RETENTION_DAYS, THREE_YEARS_DAYS)
        self.assertEqual(self._site('測試社區（預設）').retention_days, THREE_YEARS_DAYS)

    def test_migration_only_moves_old_default(self):
        old = self._site('測試社區（舊預設）', retention_days=OLD_DEFAULT_DAYS)
        custom = self._site('測試社區（合約另議）', retention_days=CUSTOM_DAYS)
        self.env.flush_all()

        _load_migration().migrate(self.env.cr, '18.0.2.7.1')
        self.env.invalidate_all()

        self.assertEqual(old.retention_days, THREE_YEARS_DAYS)
        self.assertEqual(custom.retention_days, CUSTOM_DAYS, '合約另議的天數不得被 migration 蓋掉')

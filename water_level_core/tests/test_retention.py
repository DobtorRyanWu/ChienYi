# -*- coding: utf-8 -*-
"""保存期間：三年（1095 天）。

**這個測試在防什麼**

新北市政府水利局 115.10.02 函（新北水河計字第1151900632號）要求透水保水義務人的
監測資料等佐證「保存期限至少 3 年」。DM 原本寫「依法保存兩年」，系統預設 730 天——
對新北客戶不成立。2026-10-07 決定 DM 與系統一起改成三年。

這裡釘住「新建場域的預設保存天數是 1095」。另一半（18.0.2.8.0 migration 只改還停在
舊預設 730 的場域）跟著 migration 留在 construction_water_level/tests/test_retention_migration.py。
"""

from odoo.tests import common, tagged

from odoo.addons.water_level_core.models.water_level_site import (
    DEFAULT_RETENTION_DAYS,
)

from .common import site_vals

THREE_YEARS_DAYS = 1095


@tagged('post_install', '-at_install')
class TestWaterLevelRetention(common.TransactionCase):

    def test_default_is_three_years(self):
        self.assertEqual(DEFAULT_RETENTION_DAYS, THREE_YEARS_DAYS)
        site = self.env['water.level.site'].create(site_vals(self.env, '測試社區（預設）'))
        self.assertEqual(site.retention_days, THREE_YEARS_DAYS)

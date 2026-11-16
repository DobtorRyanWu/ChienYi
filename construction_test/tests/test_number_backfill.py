# -*- coding: utf-8 -*-
"""18.0.2.8.2 migration：單號是「/」的試驗紀錄依工程公司補號，日期依序取 取樣日 → 進場日 → 建立日。

jt 2026-11-16：任泰沒有試驗紀錄序列，149 張是「/」。
"""
import importlib.util
import os

from odoo import fields
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

MIGRATION_VERSION = '18.0.2.8.2'
INSTALLED_VERSION = '18.0.2.8.1'
PADDING = 4
SLASH = '/'


def _load_migration():
    path = os.path.join(get_module_path('construction_test'),
                        'migrations', MIGRATION_VERSION, 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('test_record_number_backfill', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'construction_test')
class TestNumberBackfill(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({'name': '試驗補號測試 B 監造'})
        cls.env['ir.sequence'].create({
            'name': '試驗補號測試', 'code': 'supervision.test.record',
            'prefix': 'TR-B-%(year)s%(month)s-', 'padding': PADDING, 'implementation': 'no_gap',
            'company_id': cls.company_b.id})
        cls.project_b = cls.env['project.project'].create({
            'name': '試驗補號測試工程', 'code': 'TR-BF-B', 'company_id': cls.company_b.id})
        cls.standard = cls.env['supervision.test.standard'].create({
            'name': '混凝土抗壓強度', 'material': '預拌混凝土', 'project_id': cls.project_b.id})

    def _record(self, **dates):
        return self.env['supervision.test.record'].create(dict(
            project_id=self.project_b.id, standard_id=self.standard.id, **dates))

    def test_backfill_date_fallback(self):
        by_sample = self._record(sample_date='2022-03-05', in_site_date='2022-01-20')
        by_in_site = self._record(in_site_date='2022-02-10')
        by_create = self._record()
        records = by_sample | by_in_site | by_create
        self.env.flush_all()
        self.env.cr.execute('UPDATE supervision_test_record SET name = %s WHERE id IN %s',
                            (SLASH, tuple(records.ids)))
        records.invalidate_recordset(['name'])

        _load_migration().migrate(self.env.cr, INSTALLED_VERSION)
        self.env.invalidate_all()

        self.assertTrue(by_sample.name.startswith('TR-B-202203-'), by_sample.name)
        self.assertTrue(by_in_site.name.startswith('TR-B-202202-'), by_in_site.name)
        create_month = fields.Date.to_date(by_create.create_date).strftime('%Y%m')
        self.assertTrue(by_create.name.startswith('TR-B-%s-' % create_month), by_create.name)
        # 依日期排序給流水號：2022-02（進場日）< 2022-03（取樣日）< 建立日
        serial = lambda r: int(r.name.rsplit('-', 1)[1])  # noqa: E731
        self.assertLess(serial(by_in_site), serial(by_sample))
        self.assertLess(serial(by_sample), serial(by_create))

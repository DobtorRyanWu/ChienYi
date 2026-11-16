# -*- coding: utf-8 -*-
"""18.0.6.10.3 migration：單號是「/」的自主檢查依工程公司、依檢查日期補號。

jt 2026-11-16：任泰沒有自主檢查序列，一般式 2,313 張、預約式 309 張是「/」。
使用者選「依單據日期」：前綴年月用檢查日期，依日期、同日再依 id 給流水號。
"""
import importlib.util
import os

from odoo import fields
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

MIGRATION_VERSION = '18.0.6.10.3'
INSTALLED_VERSION = '18.0.6.10.2'
PADDING = 4
SLASH = '/'


def _load_migration():
    path = os.path.join(get_module_path('construction_quality'),
                        'migrations', MIGRATION_VERSION, 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('quality_number_backfill', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'construction_quality')
class TestNumberBackfill(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({'name': '補號測試 B 監造'})
        Seq = cls.env['ir.sequence']
        # no_gap：號碼存在資料表、跟著測試 rollback，期望值才固定
        for code, prefix in (('general.self.inspection', 'GSI-B-%(year)s%(month)s-'),
                             ('reservation.self.inspection', 'RSI-B-%(year)s%(month)s-')):
            Seq.create({'name': '補號測試 %s' % code, 'code': code, 'prefix': prefix,
                        'padding': PADDING, 'implementation': 'no_gap',
                        'company_id': cls.company_b.id})
        Project = cls.env['project.project']
        cls.project_b = Project.create({'name': '補號測試（一般式）', 'code': 'BF-B',
                                        'project_type': 'general', 'company_id': cls.company_b.id})
        cls.res_project_b = Project.create({'name': '補號測試（預約式）', 'code': 'BF-B-R',
                                            'project_type': 'reservation',
                                            'company_id': cls.company_b.id})
        cls.itype = cls.env['self.inspection.type'].create({'name': '補號測試類型'})

    def _general(self, date):
        return self.env['general.self.inspection'].create({
            'project_id': self.project_b.id, 'inspection_type_id': self.itype.id,
            'sub_project_name': '補號測試', 'inspection_date': date})

    def _set_slash(self, records, field):
        self.env.flush_all()
        self.env.cr.execute('UPDATE %s SET %s = %%s WHERE id IN %%s' % (records._table, field),
                            (SLASH, tuple(records.ids)))
        records.invalidate_recordset([field])

    @staticmethod
    def _serial(number):
        return int(number.rsplit('-', 1)[1])

    def test_general_backfill_by_inspection_date(self):
        june_first = self._general('2022-06-13')
        may = self._general('2022-05-01')
        june_second = self._general('2022-06-13')
        keep = self._general('2022-07-01')
        keep_name = keep.name
        self._set_slash(june_first | may | june_second, 'name')

        _load_migration().migrate(self.env.cr, INSTALLED_VERSION)
        self.env.invalidate_all()

        # 前綴年月用檢查日期
        self.assertTrue(may.name.startswith('GSI-B-202205-'), may.name)
        self.assertTrue(june_first.name.startswith('GSI-B-202206-'), june_first.name)
        self.assertTrue(june_second.name.startswith('GSI-B-202206-'), june_second.name)
        # 依日期、同日再依 id 給流水號
        self.assertLess(self._serial(may.name), self._serial(june_first.name))
        self.assertLess(self._serial(june_first.name), self._serial(june_second.name))
        # 本來就有號的不動
        self.assertEqual(keep.name, keep_name)
        self.assertFalse(self.env['general.self.inspection'].search_count(
            [('name', '=', SLASH), ('project_id', '=', self.project_b.id)]))

    def test_reservation_backfill_uses_slip_project_company(self):
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.res_project_b.id, 'location': '補號測試地點'})
        slip.sudo().write({'state': 'in_progress'})
        insp = self.env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': self.itype.id,
            'sub_project_name': '補號測試', 'inspection_date': '2023-03-09'})
        self._set_slash(insp, 'inspection_no')

        _load_migration().migrate(self.env.cr, INSTALLED_VERSION)
        self.env.invalidate_all()

        self.assertTrue(insp.inspection_no.startswith('RSI-B-202303-'), insp.inspection_no)

    def test_fresh_install_is_skipped(self):
        insp = self._general(fields.Date.today())
        self._set_slash(insp, 'name')
        _load_migration().migrate(self.env.cr, None)
        self.env.invalidate_all()
        self.assertEqual(insp.name, SLASH)

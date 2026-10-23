# -*- coding: utf-8 -*-
"""案件契約材料清單 ＋ 施工日誌工地材料管理：自動帶入、自動累計。

重點約束：沒有連結契約材料的舊列（例如任泰那 430 筆人工手填累計）行為與數值完全不變。
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestContractMaterial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Sheet = cls.env['daily.log.sheet']
        cls.Catalog = cls.env['construction.contract.material']
        cls.company = cls.env.company
        cls.project = cls._make_project('CM-A')
        cls.other_project = cls._make_project('CM-B')
        cls.employee = cls.env['hr.employee'].create({
            'name': '契約材料測試員工', 'company_id': cls.company.id})
        cls.today = fields.Date.today()

    @classmethod
    def _make_project(cls, code):
        project = cls.env['project.project'].create({
            'name': '契約材料測試工程 %s' % code,
            'code': code,
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.company.id,
        })
        schedule = cls.env['progress.schedule'].create({
            'project_id': project.id,
            'change_date': fields.Date.today(),
        })
        schedule.write({'state': 'active'})
        return project

    def _item(self, code, name, is_key=True, project=None, **kw):
        vals = {
            'project_id': (project or self.project).id,
            'code': code, 'name': name, 'unit': 'M3',
            'contract_qty': 100.0, 'is_key': is_key,
        }
        vals.update(kw)
        return self.Catalog.create(vals)

    def _sheet(self, days_ago, **extra):
        vals = {
            'supervision_project_id': self.project.id,
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'log_date': self.today - timedelta(days=days_ago),
        }
        vals.update(extra)
        return self.Sheet.create(vals)

    def _row(self, sheet, item):
        row = sheet.material_ids.filtered(lambda m: m.catalog_item_id == item)
        self.assertEqual(len(row), 1, '日誌 %s 應恰好有一列 %s' % (sheet.log_date, item.name))
        return row

    # a ------------------------------------------------------------------
    def test_a_create_sheet_autofills_only_key_items(self):
        key = self._item('M001', '預拌混凝土', unit='M3', contract_qty=250.0)
        self._item('M002', '非重要材料', is_key=False)
        self._item('M003', '已封存重要材料', active=False)
        sheet = self._sheet(1)
        self.assertEqual(len(sheet.material_ids), 1)
        row = sheet.material_ids
        self.assertEqual(row.catalog_item_id, key)
        self.assertEqual((row.name, row.unit, row.contract_qty),
                         ('預拌混凝土', 'M3', 250.0))
        self.assertEqual((row.daily_qty, row.cumulative_qty), (0.0, 0.0))

    # b ------------------------------------------------------------------
    def test_b_cumulative_follows_dates_and_edits(self):
        item = self._item('M001', '鋼筋')
        s1, s2, s3 = self._sheet(3), self._sheet(2), self._sheet(1)
        for sheet, qty in ((s1, 10.0), (s2, 20.0), (s3, 30.0)):
            self._row(sheet, item).write({'daily_qty': qty})
        self.assertEqual([self._row(s, item).cumulative_qty for s in (s1, s2, s3)],
                         [10.0, 30.0, 60.0])
        self._row(s1, item).write({'daily_qty': 15.0})
        self.assertEqual([self._row(s, item).cumulative_qty for s in (s1, s2, s3)],
                         [15.0, 35.0, 65.0])

    # c ------------------------------------------------------------------
    def test_c_backfill_delete_and_date_change_recompute(self):
        item = self._item('M001', '鋼筋')
        s2, s3 = self._sheet(2), self._sheet(1)
        self._row(s2, item).write({'daily_qty': 20.0})
        self._row(s3, item).write({'daily_qty': 30.0})
        self.assertEqual(self._row(s3, item).cumulative_qty, 50.0)

        # 補建更早的一天
        s1 = self._sheet(3)
        self._row(s1, item).write({'daily_qty': 10.0})
        self.assertEqual(self._row(s1, item).cumulative_qty, 10.0)
        self.assertEqual(self._row(s2, item).cumulative_qty, 30.0)
        self.assertEqual(self._row(s3, item).cumulative_qty, 60.0)

        # 刪除一整張日誌（材料列是 DB cascade 刪除）
        s2.unlink()
        self.assertEqual(self._row(s3, item).cumulative_qty, 40.0)

        # 改日誌日期：把 s3 搬到 s1 前面
        s3.write({'log_date': self.today - timedelta(days=5)})
        self.assertEqual(self._row(s3, item).cumulative_qty, 30.0)
        self.assertEqual(self._row(s1, item).cumulative_qty, 40.0)

    # d ------------------------------------------------------------------
    def test_d_unlinked_rows_are_never_touched(self):
        item = self._item('M001', '鋼筋')
        s1, s2 = self._sheet(2), self._sheet(1)
        manual = self.env['daily.log.material'].create({
            'daily_log_id': s2.id, 'name': '人工手填材料',
            'daily_qty': 5.0, 'cumulative_qty': 999.0,
        })
        self.assertEqual(manual.cumulative_qty, 999.0)
        self._row(s1, item).write({'daily_qty': 10.0})
        self._row(s2, item).write({'daily_qty': 20.0})
        s1.write({'log_date': self.today - timedelta(days=4)})
        self.assertEqual(manual.cumulative_qty, 999.0)
        manual.write({'daily_qty': 7.0})
        self.assertEqual(manual.cumulative_qty, 999.0)
        # 連結列的累計被手改 → 被覆蓋回正確值
        row = self._row(s2, item)
        row.write({'cumulative_qty': 12345.0})
        self.assertEqual(row.cumulative_qty, 30.0)

    # e ------------------------------------------------------------------
    def test_e_locked_sheet_is_skipped_or_blocked(self):
        old = self._sheet(20)
        recent = self._sheet(3)
        item = self._item('M001', '鋼筋')  # 清單是在兩張日誌都建立之後才有的
        self.assertFalse(old.material_ids)
        self.assertFalse(recent.material_ids)
        with self.assertRaises(UserError):
            old.action_load_key_materials()
        self.assertFalse(old.material_ids)
        item.action_apply_to_open_logs()
        self.assertFalse(old.material_ids, '鎖定的日誌不可被補入')
        self.assertEqual(recent.material_ids.catalog_item_id, item)
        # 再套用一次不會重複帶入
        item.action_apply_to_open_logs()
        self.assertEqual(len(recent.material_ids), 1)

    # f ------------------------------------------------------------------
    def test_f_manual_rows_do_not_suppress_autofill(self):
        # vals 自帶的材料列（後台先手填一列、xlsm 匯入）照留，重要材料仍要補上，不能整張略過
        item = self._item('M001', '鋼筋')
        sheet = self._sheet(1, material_ids=[Command.create({'name': '匯入的材料'})])
        self.assertEqual(sorted(sheet.material_ids.mapped('name')), sorted(['匯入的材料', '鋼筋']))
        self.assertEqual(sheet.material_ids.catalog_item_id, item)

    # g ------------------------------------------------------------------
    def test_g_project_without_catalog_gets_no_rows(self):
        sheet = self._sheet(1)
        self.assertFalse(sheet.material_ids)

    # h ------------------------------------------------------------------
    def test_h_catalog_item_of_other_project_rejected(self):
        foreign = self._item('M001', '別案材料', project=self.other_project)
        sheet = self._sheet(1)
        with self.assertRaises(ValidationError):
            self.env['daily.log.material'].create({
                'daily_log_id': sheet.id, 'name': foreign.name,
                'catalog_item_id': foreign.id,
            })

    @mute_logger('odoo.sql_db')
    def test_unique_code_per_project(self):
        self._item('M001', '鋼筋')
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self._item('M001', '重複代碼')

    # 第一輪抗辯後補的守衛 ---------------------------------------------------
    def test_i_project_change_with_linked_rows_rejected(self):
        # 日誌改了所屬工程，連結列還指著舊案清單 → 累計會算錯案，必須擋
        self._item('M001', '預拌混凝土')
        sheet = self._sheet(1)
        self.assertEqual(len(sheet.material_ids), 1)
        with self.assertRaises(ValidationError):
            sheet.write({'supervision_project_id': self.other_project.id})

    def test_j_linked_qty_must_be_finite_and_bounded(self):
        item = self._item('M001', '鋼筋')
        row = self._row(self._sheet(1), item)
        for bad in (float('nan'), 1e303, -1.0):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                row.write({'daily_qty': bad})
        # 未連結的人工手填列維持原本行為（不受新守衛影響）
        manual = self.env['daily.log.material'].create({
            'daily_log_id': self._sheet(2).id, 'name': '人工手填', 'daily_qty': 1e303})
        self.assertEqual(manual.daily_qty, 1e303)

    def _admin_user(self, login):
        return self.env['res.users'].create({
            'name': login, 'login': login,
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('construction_supervision_base.group_supervisor_admin').id])],
        })

    def _created_earlier(self, sheet):
        # 測試全在同一個交易裡；守衛把「本交易剛建立的日誌」視為未鎖定（後台補登），
        # 要模擬「以前就建好的日誌」得把 create_date 往前移
        self.env.cr.execute(
            "UPDATE daily_log_sheet SET create_date = create_date - interval '30 days' WHERE id = %s", [sheet.id])
        sheet.invalidate_recordset(['create_date'])
        return sheet

    def test_k_direct_write_on_locked_linked_row_blocked(self):
        # 材料列可以被直接寫（例如 JSON-RPC），不經日誌的鎖定檢查；連結列一改就會改寫後面所有日誌的累計
        item = self._item('M001', '鋼筋')
        old, recent = self._created_earlier(self._sheet(20)), self._sheet(3)
        user = self._admin_user('contract_material_admin')
        Material = self.env['daily.log.material'].with_user(user)
        manual_old = self.env['daily.log.material'].create({'daily_log_id': old.id, 'name': '人工列'})
        attacks = {
            '改本日數量': lambda: self._row(old, item).with_user(user).write({'daily_qty': 3.0}),
            '刪除': lambda: self._row(old, item).with_user(user).unlink(),
            '在已鎖定日誌新增連結列': lambda: Material.create({
                'daily_log_id': old.id, 'name': '鋼筋', 'catalog_item_id': item.id, 'daily_qty': 5.0}),
            '把人工列改成連結列': lambda: manual_old.with_user(user).write({'catalog_item_id': item.id}),
            '把連結列搬進已鎖定日誌': lambda: self._row(recent, item).with_user(user).write(
                {'daily_log_id': old.id}),
        }
        for name, attack in attacks.items():
            with self.assertRaises(UserError, msg=name):
                attack()
        self.assertEqual(self._row(old, item).daily_qty, 0.0)
        self._row(recent, item).with_user(user).write({'daily_qty': 4.0})   # 未鎖定照常可改
        self.assertEqual(self._row(recent, item).cumulative_qty, 4.0)

    def test_k2_backend_backfill_with_linked_row_allowed(self):
        # 後台補登 20 天前的日誌、連同連結材料列一起建立：本交易剛建立的日誌不算鎖定
        item = self._item('M001', '鋼筋')
        user = self._admin_user('contract_material_backfill')
        sheet = self.Sheet.with_user(user).create({
            'supervision_project_id': self.project.id, 'company_id': self.company.id,
            'employee_id': self.employee.id, 'log_date': self.today - timedelta(days=20),
            'material_ids': [Command.create({'name': '鋼筋', 'catalog_item_id': item.id, 'daily_qty': 6.0})],
        })
        self.assertEqual(self._row(sheet, item).cumulative_qty, 6.0)

    def test_l_catalog_is_company_scoped(self):
        # 清單含契約單價：只看得到目前選取公司的工程的清單
        company_b = self.env['res.company'].create({'name': '契約材料隔離測試 B 公司'})
        project_b = self.env['project.project'].create({
            'name': '契約材料隔離測試工程 B', 'company_id': company_b.id})
        mine = self._item('M001', '預拌混凝土')
        theirs = self._item('M001', '預拌混凝土', project=project_b)
        user = self.env['res.users'].create({
            'name': '契約材料隔離測試代操', 'login': 'contract_material_operator',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('construction_supervision_base.group_operator').id])],
        })
        got = self.Catalog.with_user(user).search([('id', 'in', (mine | theirs).ids)])
        self.assertEqual(got, mine)

    def test_m_backend_new_linked_row_saves(self):
        # 後台新增一列、選契約材料：名稱等欄位在連結列是唯讀，要由 onchange 帶入並 force_save，否則存不了
        item = self._item('M009', '銲接鋼線網', is_key=False, unit='M2', contract_qty=30.0)
        sheet = self._sheet(1)
        with Form(sheet) as form:
            with form.material_ids.new() as row:
                row.catalog_item_id = item
                row.daily_qty = 2.0
        line = sheet.material_ids.filtered(lambda m: m.catalog_item_id == item)
        self.assertEqual((line.name, line.unit, line.contract_qty, line.cumulative_qty),
                         ('銲接鋼線網', 'M2', 30.0, 2.0))

    def test_n_catalog_project_change_blocked_when_in_use(self):
        item = self._item('M001', '預拌混凝土')
        self._sheet(1)
        with self.assertRaises(ValidationError):
            item.write({'project_id': self.other_project.id})
        unused = self._item('M002', '未使用的材料')
        unused.write({'project_id': self.other_project.id})   # 還沒被用到的照常可改

    def test_o_xlsm_import_flag_skips_autofill(self):
        self._item('M001', '鋼筋')
        sheet = self.Sheet.with_context(skip_key_material_autofill=True).create({
            'supervision_project_id': self.project.id, 'company_id': self.company.id,
            'employee_id': self.employee.id, 'log_date': self.today - timedelta(days=1),
            'material_ids': [Command.create({'name': '鋼筋（匯入）', 'daily_qty': 7.0})],
        })
        self.assertEqual(sheet.material_ids.mapped('name'), ['鋼筋（匯入）'])


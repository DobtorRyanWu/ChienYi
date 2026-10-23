# -*- coding: utf-8 -*-
"""前台施工日誌「工地材料（約定重要材料）」：本日數量填寫與權限。

設計重點（見 construction_daily_log 2.10.0）：
- 前台 update 路由是 sudo 寫入；材料列的 (1, id, vals) 指令在 Odoo 18 不檢查父記錄，
  所以必須只接受「這張日誌自己、已連結契約材料」的列 id，否則偽造 id 會寫到別張日誌。
- 材料指令併進同一次 log.write()，14 天鎖定才擋得到。
- 閱覽者原本可以 POST update（既有漏洞），現在要被 _require_write 擋下。
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

VIEWER = 'construction_supervision_base.group_portal_viewer'
LEADER = 'construction_supervision_base.group_portal_leader'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalDailyLogMaterials(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '前台材料測試工程', 'code': 'PM-MAT',
            'state': 'construction', 'company_id': cls.company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        cls.leader = cls._mk_user('pm_leader', LEADER)
        cls.viewer = cls._mk_user('pm_viewer', VIEWER)
        for user in (cls.leader, cls.viewer):
            cls.env['supervision.project.member'].create({
                'project_id': cls.project.id, 'user_id': user.id})
        # 建立 res.users 時 hr 會自動建員工（hr_employee_user_uniq）→ 取用現成的
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.leader.id)], limit=1)
        if not cls.employee:
            cls.employee = cls.env['hr.employee'].create({
                'name': '前台材料測試員工', 'company_id': cls.company.id,
                'user_id': cls.leader.id})
        cls.item = cls.env['construction.contract.material'].create({
            'project_id': cls.project.id, 'code': 'M001', 'name': '預拌混凝土',
            'unit': 'M3', 'contract_qty': 500.0, 'is_key': True,
        })

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })

    def _sheet(self, days_ago):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'log_date': fields.Date.today() - timedelta(days=days_ago),
        })

    def _row(self, sheet):
        return sheet.material_ids.filtered(lambda m: m.catalog_item_id == self.item)

    def _update(self, user, sheet, **post):
        with MockRequest(self.env(user=user)) as req:
            req.httprequest.files.getlist.return_value = []
            return self.ctrl.portal_construction_daily_log_update(
                self.project.id, sheet.id, **post)

    def _location(self, response):
        return response.headers.get('Location', '')

    # i ------------------------------------------------------------------
    def test_i_leader_update_writes_qty_and_cumulative(self):
        first, second = self._sheet(2), self._sheet(1)
        self._row(first).write({'daily_qty': 10.0})
        res = self._update(self.leader, second,
                           **{'material_qty_%s' % self._row(second).id: '12.5'})
        self.assertIn('message=updated', self._location(res))
        self.assertEqual(self._row(second).daily_qty, 12.5)
        self.assertEqual(self._row(second).cumulative_qty, 22.5)

    # j ------------------------------------------------------------------
    def test_j_foreign_row_id_is_ignored(self):
        mine, other = self._sheet(1), self._sheet(2)
        other_row = self._row(other)
        self._update(self.leader, mine, **{
            'material_qty_%s' % other_row.id: '99',
            'material_qty_%s' % self._row(mine).id: '3',
        })
        self.assertEqual(other_row.daily_qty, 0.0, '別張日誌的材料列不可被改')
        self.assertEqual(self._row(mine).daily_qty, 3.0)

    def test_j2_unlinked_row_id_is_ignored(self):
        sheet = self._sheet(1)
        manual = self.env['daily.log.material'].create({
            'daily_log_id': sheet.id, 'name': '人工列', 'cumulative_qty': 7.0})
        self._update(self.leader, sheet, **{'material_qty_%s' % manual.id: '50'})
        self.assertEqual((manual.daily_qty, manual.cumulative_qty), (0.0, 7.0))

    # k ------------------------------------------------------------------
    def test_k_viewer_blocked_on_update(self):
        sheet = self._sheet(1)
        with self.assertRaises(AccessError):
            self._update(self.viewer, sheet, work_summary='竄改',
                         **{'material_qty_%s' % self._row(sheet).id: '8'})
        self.assertEqual(self._row(sheet).daily_qty, 0.0)
        self.assertFalse(sheet.work_summary)

    # l ------------------------------------------------------------------
    def test_l_locked_sheet_redirects_and_keeps_data(self):
        sheet = self._sheet(20)
        res = self._update(self.leader, sheet,
                           **{'material_qty_%s' % self._row(sheet).id: '8'})
        self.assertIn('error=locked', self._location(res))
        self.assertEqual(self._row(sheet).daily_qty, 0.0)

    # 無效數量 ------------------------------------------------------------
    def test_invalid_qty_redirects_and_writes_nothing(self):
        sheet = self._sheet(1)
        rid = self._row(sheet).id
        for bad in ('-3', 'abc', 'nan', 'inf', '1e303'):
            res = self._update(self.leader, sheet, work_summary='不該寫入',
                               **{'material_qty_%s' % rid: bad})
            # 導回編輯頁（表單上有提示），整筆未儲存
            self.assertIn('/edit?error=invalid_qty', self._location(res), bad)
            self.assertEqual(self._row(sheet).daily_qty, 0.0, bad)
            self.assertFalse(sheet.work_summary, bad)

    # m ------------------------------------------------------------------
    def test_m_create_with_key_material_qty(self):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            res = self.ctrl.portal_construction_daily_log_create(
                project_id=str(self.project.id),
                log_date=str(fields.Date.today() - timedelta(days=1)),
                **{'key_material_qty_%s' % self.item.id: '7.5'})
        self.assertIn('message=created', self._location(res))
        log = self.env['daily.log.sheet'].search(
            [('supervision_project_id', '=', self.project.id)], limit=1)
        self.assertEqual(self._row(log).daily_qty, 7.5)
        self.assertEqual(self._row(log).cumulative_qty, 7.5)

    def test_non_ascii_digit_key_is_ignored_not_500(self):
        # 「²」對 str.isdigit() 是 True，但 int() 會丟例外；這種欄位名要被略過，不能變成 500
        sheet = self._sheet(1)
        res = self._update(self.leader, sheet, work_summary='照常儲存',
                           **{'material_qty_²': '5', 'material_qty_' + '9' * 5000: '5'})
        self.assertNotIn('error=', self._location(res))
        self.assertEqual(sheet.work_summary, '照常儲存')
        self.assertEqual(self._row(sheet).daily_qty, 0.0)


    def test_portal_roles_cannot_read_contract_catalog(self):
        # 清單含契約單價；前台路由一律 sudo 讀，前台角色本身不給讀權（共用庫裡會讀到別家的單價）
        Catalog = self.env['construction.contract.material']
        for user in (self.leader, self.viewer):
            self.assertFalse(Catalog.with_user(user).has_access('read'), user.login)

    def test_clearing_qty_sets_zero(self):
        # 表單把 0 顯示成空白；原本填 5、使用者清空送出，要真的歸零（不能留著 5 又顯示「已更新」）
        sheet = self._sheet(1)
        row = self._row(sheet)
        row.write({'daily_qty': 5.0})
        self._update(self.leader, sheet, **{'material_qty_%s' % row.id: ''})
        self.assertEqual(row.daily_qty, 0.0)
        self.assertEqual(row.cumulative_qty, 0.0)

    def test_file_field_with_qty_name_is_invalid_not_500(self):
        # multipart 的檔案欄位會被併進 POST 參數；FileStorage 沒有 .strip()
        from io import BytesIO
        from werkzeug.datastructures import FileStorage
        sheet = self._sheet(1)
        res = self._update(self.leader, sheet, **{
            'material_qty_%s' % self._row(sheet).id: FileStorage(BytesIO(b'5'), filename='x.txt')})
        self.assertIn('error=invalid_qty', self._location(res))

    def test_viewer_cannot_load_key_materials(self):
        # action_load_key_materials 以 sudo 建列：閱覽者（只有讀權）經 RPC 呼叫要被擋
        sheet = self._sheet(1)
        extra = self.env['construction.contract.material'].create({
            'project_id': self.project.id, 'code': 'M099', 'name': '後來才勾的重要材料', 'is_key': True})
        with self.assertRaises(AccessError):
            sheet.with_user(self.viewer).action_load_key_materials()
        self.assertNotIn(extra, sheet.material_ids.catalog_item_id)

    def test_edit_form_lists_only_linked_rows(self):
        # 沒有契約材料清單的案件（例如任泰），編輯頁不多出「工地材料」這一節
        sheet = self._sheet(1)
        self.env['daily.log.material'].create({'daily_log_id': sheet.id, 'name': '人工手填'})
        with MockRequest(self.env(user=self.leader)):
            rows = self.ctrl._daily_log_form_materials(self.project, sheet)
        self.assertEqual([r.name for r in rows], ['預拌混凝土'])


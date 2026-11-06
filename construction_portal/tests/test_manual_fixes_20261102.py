# -*- coding: utf-8 -*-
"""說明書撰寫時發現的前台問題回歸（2026-11-02）。

全部用「現場人員」群組的真實使用者（非 sudo）驅動真實路由方法／真實模板渲染：
- P1  日誌詳情頁照片：前台帳號沒有 ir.attachment 讀權，詳情頁取附件原本 403。
- P2  檢試驗頁綁工項：前台帳號沒有 project.task 讀權，模板讀 task_id.name 原本 403。
- P2' 本週目標：首頁與日誌清單頁讀排程明細，要真的有值。
- P17 同一天已有日誌再新增：導回新增頁帶提示，不留下半成品、不跳錯誤頁。
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

FIELD = 'construction_supervision_base.group_portal_user'   # 現場人員
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalManualFixes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.company = cls.env.company
        # 夾具：前台現場人員是營造方帳號（範圍公司＝工程的承攬廠商）
        cls.contractor = make_contractor(cls.env, '說明書修正測試營造')
        cls.project = cls.env['project.project'].create({
            'name': '說明書修正測試工程', 'code': 'MF-1102',
            'state': 'construction', 'company_id': cls.company.id,
            **contractor_project_vals(cls.contractor),
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        cls.worker = cls.env['res.users'].create({
            'name': 'mf_worker', 'login': 'mf_worker',
            'groups_id': [(6, 0, [cls.env.ref(FIELD).id])],
            **contractor_user_vals(cls.contractor),
        })
        cls.env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.worker.id})
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.worker.id)], limit=1)
        if not cls.employee:
            cls.employee = cls.env['hr.employee'].create({
                'name': 'mf_worker_emp', 'company_id': cls.company.id,
                'user_id': cls.worker.id})
        cls.task = cls.env['project.task'].create({
            'name': 'MF 本週目標工項', 'project_id': cls.project.id})

    def _assert_task_unreadable(self):
        """前提：頁面不能靠前台帳號自己的工項讀取權（P1／P2 的 403 就是這樣來的）。

        2026-11-04 起成員讀得到本案工項（project_task_portal_member_rule），所以先把它換成
        「前台一律讀不到工項」，頁面照樣得靠 sudo 才渲染得出來，這組測試的鑑別力不變。"""
        self.env.ref('construction_portal.project_task_portal_member_rule').active = False
        self.env['ir.rule'].create({
            'name': '測試：前台一律讀不到工項',
            'model_id': self.env['ir.model']._get('project.task').id,
            'domain_force': "[(0, '=', 1)]",
            'groups': [(4, self.env.ref('base.group_portal').id)],
            'perm_read': True, 'perm_write': False, 'perm_create': False, 'perm_unlink': False,
        })
        self.env.invalidate_all()
        with self.assertRaises(AccessError, msg='前提：前台帳號沒有 project.task 讀權'):
            self.task.with_user(self.worker).name

    def _sheet(self, days_ago=0):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'log_date': fields.Date.today() - timedelta(days=days_ago),
        })

    def _drive(self, user, method, *args, params=None, **kw):
        """用真實使用者（非 sudo）跑路由方法，並把它交給 request.render 的模板與變數
        真的渲染成 HTML（MockRequest 的 render 只回假字串，模板裡的權限錯誤要這樣才看得到）。
        回傳 (values, html)；路由回的是 redirect 時 values 為 None、html 為 Location。"""
        # 建立資料時超級使用者已把值讀進共用快取，不清掉的話前台帳號讀快取會繞過權限檢查而測不出 403
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.params = params or {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    # P1 ----------------------------------------------------------------
    def test_p1_log_detail_with_photo_renders_for_field_worker(self):
        sheet = self._sheet()
        att = self.env['ir.attachment'].create({
            'name': 'mf.png', 'datas': PNG_B64, 'mimetype': 'image/png',
            # 與 _portal_save_photos 一致：res_model 是 supervision.photo、沒有 res_id
            'public': False, 'res_model': 'supervision.photo'})
        with self.assertRaises(AccessError, msg='前提：前台帳號本來就讀不到這張附件'):
            att.with_user(self.worker).read(['name'])
        self.env['supervision.photo'].create({
            'project_id': self.project.id, 'attachment_id': att.id,
            'daily_log_id': sheet.id})
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_daily_log_detail,
            self.project.id, sheet.id)
        self.assertIsNotNone(vals, '應渲染詳情頁而不是被導走：%s' % html)
        self.assertEqual(vals['photos'].ids, [att.id])
        self.assertIn('/construction/img/%s' % att.id, html)

    # P2 ----------------------------------------------------------------
    def test_p2_test_detail_with_task_renders_for_field_worker(self):
        self._assert_task_unreadable()
        Test = self.env['supervision.test.record']
        standard = self.env['supervision.test.standard'].create({
            'name': 'MF 試驗工項', 'material': 'MF 材料', 'project_id': self.project.id})
        rec = Test.create({
            'project_id': self.project.id, 'standard_id': standard.id,
            'task_id': self.task.id})
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_test_detail,
            self.project.id, rec.id)
        self.assertIsNotNone(vals, '應渲染詳情頁而不是被導走：%s' % html)
        self.assertIn('MF 本週目標工項', html)

    # P2' ---------------------------------------------------------------
    def _make_schedule(self):
        self._assert_task_unreadable()
        today = fields.Date.today()
        week_start = today - timedelta(days=today.weekday())
        sched = self.env['construction.weekly.schedule'].create({
            'supervision_project_id': self.project.id,
            'week_start': week_start,
            'week_end': week_start + timedelta(days=6),
        })
        self.env['construction.weekly.schedule.line'].create({
            'schedule_id': sched.id, 'task_id': self.task.id})
        return sched

    def test_p2b_week_target_has_value_on_daily_log_list(self):
        self._make_schedule()
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_daily_logs, self.project.id)
        self.assertIsNotNone(vals, html)
        self.assertIn('MF 本週目標工項', vals['week_target'])
        self.assertIn('MF 本週目標工項', html)

    def test_p2c_week_target_has_value_on_project_home(self):
        self._make_schedule()
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_project_detail, self.project.id)
        self.assertIsNotNone(vals, html)
        self.assertIn('MF 本週目標工項', vals['week_target'])

    # P17 ---------------------------------------------------------------
    def test_p17_duplicate_day_redirects_back_with_error(self):
        self._sheet()
        before = self.env['daily.log.sheet'].search_count(
            [('supervision_project_id', '=', self.project.id)])
        vals, location = self._drive(
            self.worker, self.ctrl.portal_construction_daily_log_create,
            project_id=str(self.project.id),
            log_date=fields.Date.today().isoformat())
        self.assertIsNone(vals)
        self.assertIn('/daily-log/new?error=duplicate_log', location)
        # 新增頁真的把提示畫出來
        vals, html = self._drive(
            self.worker, self.ctrl.portal_construction_daily_log_new,
            self.project.id, params={'error': 'duplicate_log'}, error='duplicate_log')
        self.assertIsNotNone(vals, html)
        self.assertIn('同一天已經有施工日誌', html)
        after = self.env['daily.log.sheet'].search_count(
            [('supervision_project_id', '=', self.project.id)])
        self.assertEqual(before, after, '重複的那筆不可留下')

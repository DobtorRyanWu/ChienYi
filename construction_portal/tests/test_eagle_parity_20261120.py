# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：會議起因的情境走一次真實的前台路由。

情境：開口合約（預約式）沒有預定進度表、也沒做初始化設定。
修改前：開不了工（六項初始化未完成）；就算開了工，前台新增日誌也會被「尚未建立進度表」擋下；
        超過 14 天的日誌前台不能改（error=locked）。
修改後：直接開工 → 前台新增日誌成功 → 20 天前的日誌前台照樣能改。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（PJ-04、DL-01、DL-05）。
"""
from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

LEADER = 'construction_supervision_base.group_portal_leader'


@tagged('post_install', '-at_install', 'construction_portal')
class TestEagleParityPortalScenario(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(cls.env, '回復原版前台營造')
        cls.project = cls.env['project.project'].create({
            'name': '回復原版開口合約', 'code': 'EP-PORTAL', 'project_type': 'reservation',
            'company_id': cls.env.company.id, **contractor_project_vals(cls.contractor)})
        cls.env['project.task'].create({'name': '回復原版開口工項', 'project_id': cls.project.id})
        cls.leader = cls.env['res.users'].create({
            'name': 'ep_portal_leader', 'login': 'ep_portal_leader',
            'groups_id': [(6, 0, [cls.env.ref(LEADER).id])], **contractor_user_vals(cls.contractor)})
        cls.env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': cls.leader.id})
        if not cls.env['hr.employee'].search([('user_id', '=', cls.leader.id)], limit=1):
            cls.env['hr.employee'].create({
                'name': '回復原版前台員工', 'company_id': cls.env.company.id, 'user_id': cls.leader.id})

    def _post(self, method, *args, **post):
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            return method(*args, **post).headers.get('Location', '')

    def _logs(self):
        return self.env['daily.log.sheet'].search([('supervision_project_id', '=', self.project.id)])

    def test_open_contract_without_schedule_end_to_end(self):
        project = self.project
        self.assertEqual(project.state, 'draft')
        self.assertFalse(project.all_init_done, '前提：初始化設定都沒做')
        self.assertFalse(self.env['progress.schedule'].search_count([('project_id', '=', project.id)]),
                         '前提：沒有進度表')
        project.action_approve()                                      # 直接開工
        self.assertEqual(project.state, 'construction')

        day = fields.Date.today() - timedelta(days=1)
        loc = self._post(self.ctrl.portal_construction_daily_log_create,
                         project_id=str(project.id), log_date=str(day))
        self.assertIn('message=created', loc)                         # 前台新增日誌
        log = self._logs()
        self.assertEqual((len(log), log.log_date), (1, day))

    def test_old_log_editable_from_portal(self):
        self.project.action_approve()
        employee = self.env['hr.employee'].search([('user_id', '=', self.leader.id)], limit=1)
        old = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': employee.id, 'log_date': fields.Date.today() - timedelta(days=20),
            'contractor_company_id': self.contractor.id})
        self.env.cr.execute(          # 模擬以前就建好的日誌
            "UPDATE daily_log_sheet SET create_date = create_date - interval '30 days' WHERE id = %s", [old.id])
        loc = self._post(self.ctrl.portal_construction_daily_log_update, self.project.id, old.id,
                         work_summary='20 天前的日誌從前台補記')
        self.assertNotIn('error=', loc)
        self.env.invalidate_all()
        self.assertEqual(old.work_summary, '20 天前的日誌從前台補記')

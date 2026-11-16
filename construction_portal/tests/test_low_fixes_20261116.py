# -*- coding: utf-8 -*-
"""11-16 六件 low 的回歸：本檔為 construction_portal 部分（工期展延送出失敗不留半套資料）。"""
from unittest.mock import patch

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import SUPERVISION_USER_VALS

LEADER = 'construction_supervision_base.group_portal_leader'
PROGRESS_SCHEDULE = 'odoo.addons.construction_progress.models.progress_schedule.ProgressSchedule'
EXTENSION_DAYS = 9


@tagged('post_install', '-at_install', 'construction_portal')
class TestScheduleExtendSavepoint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.leader = env['res.users'].create({
            'name': '展延測試主管', 'login': 'ext_leader_1116',
            'groups_id': [(6, 0, [env.ref('base.group_portal').id, env.ref(LEADER).id])],
            **SUPERVISION_USER_VALS})   # 工期展延限監造方
        cls.project = env['project.project'].create({
            'name': '展延 savepoint 工程', 'code': 'EXT-SP', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id,
            'contract_start_date': fields.Date.to_date('2026-01-05'),
            'contract_end_date': fields.Date.to_date('2026-03-30')})
        env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.leader.id})
        cls.schedule = env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()})

    def _submit(self, days):
        with MockRequest(self.env(user=self.leader)):
            return self.ctrl.portal_schedule_extend_submit(
                self.project.id, self.schedule.id, current_extension=str(days))

    def test_failed_extend_leaves_no_half_written_extension(self):
        """修前：先 write current_extension 再展延，展延失敗時天數已寫入（交易照 commit）。"""
        self.assertEqual(self.schedule.current_extension, 0, '前提')
        with patch(PROGRESS_SCHEDULE + '.action_extend_lines',
                   side_effect=ValidationError('模擬展延失敗')):
            res = self._submit(EXTENSION_DAYS)
        self.assertIn('error=action_failed', res.headers.get('Location', ''))
        self.schedule.invalidate_recordset()
        self.assertEqual(self.schedule.current_extension, 0, '失敗要整個退回，不能留下展延天數')

    def test_successful_extend_still_saves(self):
        """正常案例：成功時天數照寫入。"""
        res = self._submit(EXTENSION_DAYS)
        self.assertIn('success=1', res.headers.get('Location', ''))
        self.assertEqual(self.schedule.current_extension, EXTENSION_DAYS)

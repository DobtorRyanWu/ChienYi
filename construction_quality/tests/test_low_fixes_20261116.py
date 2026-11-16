# -*- coding: utf-8 -*-
"""11-16 六件 low 的回歸：缺失逾期通知的作者不是「系統」。"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

OVERDUE_DAYS = 3
FOUND_DAYS_AGO = 10


@tagged('post_install', '-at_install', 'construction_quality')
class TestOverdueNotificationAuthor(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.project = env['project.project'].create({
            'name': '逾期通知作者工程', 'code': 'QA-AUTH',
            'project_type': 'general', 'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'AUTHQA', 'contractor_prefix': 'AUTHQR'})
        cls.discoverer = env['res.users'].create({'name': 'qa_auth_discoverer', 'login': 'qa_auth_discoverer'})
        cls.responsible = env['res.users'].create({'name': 'qa_auth_responsible', 'login': 'qa_auth_responsible'})

    def _overdue_defect(self, **extra):
        today = fields.Date.today()
        vals = {
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '逾期通知作者', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': 'notified',
            'found_date': today - timedelta(days=FOUND_DAYS_AGO),
            'deadline': today - timedelta(days=OVERDUE_DAYS),
            'responsible_user_id': self.responsible.id,
        }
        vals.update(extra)
        defect = self.env['general.defect.improvement'].create(vals)
        defect.invalidate_recordset()
        return defect

    def _overdue_message(self, defect):
        self.env['general.defect.improvement']._cron_send_overdue_notification()
        return self.env['mail.message'].search([
            ('model', '=', defect._name), ('res_id', '=', defect.id),
            ('message_type', '=', 'notification'), ('body', 'ilike', '已逾期')], limit=1)

    def test_overdue_notification_author_is_discoverer(self):
        """修前：cron 以系統帳號跑，作者記成「系統」（OdooBot）。"""
        defect = self._overdue_defect(discovery_user_id=self.discoverer.id)
        msg = self._overdue_message(defect)
        self.assertTrue(msg, '前提：逾期通知有發出')
        self.assertEqual(msg.author_id, self.discoverer.partner_id)
        self.assertNotEqual(msg.author_id, self.env.ref('base.partner_root'))
        self.assertIn(self.responsible.partner_id, msg.partner_ids, '收件人仍是負責人')

    def test_overdue_notification_author_falls_back_to_creator(self):
        """沒有發現人時退而用建立者，不退回「系統」。"""
        defect = self._overdue_defect(discovery_user_id=False)
        msg = self._overdue_message(defect)
        self.assertTrue(msg)
        self.assertEqual(msg.author_id, defect.create_uid.partner_id)

# -*- coding: utf-8 -*-
"""說明書撰寫時發現的問題回歸（2026-11-02）。

- P3  預約式缺失的顯示名稱要是缺失編號，不是 `reservation.defect.improvement,4`。
- B2  編號前綴設定的顯示名稱（麵包屑）要是「工程 (監造:… / 營造:…)」，
      Odoo 18 讀 display_name，不再呼叫 name_get。
- P19 缺失通知的 chatter 訊息：標籤要是真的標籤（不顯示原始 <b>），
      使用者輸入（缺失說明、執行改善單位）含 <script> 要被跳脫。
"""

from datetime import timedelta

from markupsafe import Markup

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'construction_quality')
class TestDisplayAndChatter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '顯示名稱測試', 'code': 'QA-DISP',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})
        cls.config = cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'DSPQA', 'contractor_prefix': 'DSPQR'})
        cls.user = cls.env['res.users'].create({
            'name': 'qa_disp_user', 'login': 'qa_disp_user'})

    def _defect(self, **extra):
        vals = {
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '牆面裂縫', 'defect_location': 'B1',
            'source_type': 'daily_check',
            'deadline': fields.Date.today() + timedelta(days=7),
            'responsible_user_id': self.user.id,
        }
        vals.update(extra)
        return self.env['general.defect.improvement'].create(vals)

    def _last_body(self, rec):
        return self.env['mail.message'].search(
            [('model', '=', rec._name), ('res_id', '=', rec.id),
             ('message_type', '=', 'notification')], order='id desc', limit=1).body

    # B2 ----------------------------------------------------------------
    def test_b2_prefix_config_display_name(self):
        self.assertEqual(
            self.config.display_name,
            '顯示名稱測試 (監造:DSPQA / 營造:DSPQR)')
        self.assertNotIn('defect.improvement.prefix.config', self.config.display_name)

    # P3 ----------------------------------------------------------------
    def test_p3_reservation_defect_display_name_is_defect_no(self):
        res_project = self.env['project.project'].create({
            'name': '預約式顯示名稱', 'code': 'QA-DISP-R',
            'project_type': 'reservation', 'company_id': self.env.company.id})
        self.env['defect.improvement.prefix.config'].create({
            'project_id': res_project.id,
            'supervision_prefix': 'DSPRS', 'contractor_prefix': 'DSPRC'})
        slip = self.env['reservation.notification.slip'].create({
            'project_id': res_project.id, 'location': '顯示名稱測試地點'})
        slip.sudo().write({'state': 'in_progress'})
        defect = self.env['reservation.defect.improvement'].create({
            'slip_id': slip.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '預約式缺失', 'defect_location': 'B1',
            'notification_date': fields.Date.today()})
        self.assertTrue(defect.defect_no)
        self.assertEqual(defect.display_name, defect.defect_no)

    # P19 ---------------------------------------------------------------
    def test_p19_notify_body_is_markup_and_escapes_input(self):
        defect = self._defect(
            defect_description=XSS, improvement_unit=XSS)
        defect.action_notify()
        body = self._last_body(defect)
        self.assertIsInstance(body, Markup)
        self.assertIn('<b>%s</b>' % defect.defect_no, body, '標籤要是真的標籤')
        self.assertNotIn('&lt;b&gt;', body, '標籤不可被當文字跳脫')
        self.assertNotIn('<script>', body, '使用者輸入的 <script> 必須被跳脫')
        self.assertIn('&lt;script&gt;', body)

    def test_p19_improved_body_is_markup(self):
        defect = self._defect(discovery_user_id=self.user.id)
        defect.write({'state': 'improving', 'improvement_action': '已處理'})
        defect.action_complete_improvement()
        body = self._last_body(defect)
        self.assertIn('<b>%s</b>' % defect.defect_no, body)
        self.assertNotIn('&lt;b&gt;', body)

    def test_p19_overdue_body_is_markup(self):
        defect = self._defect(
            found_date=fields.Date.today() - timedelta(days=10),
            deadline=fields.Date.today() - timedelta(days=3), state='notified')
        defect.invalidate_recordset()
        self.env['general.defect.improvement']._cron_send_overdue_notification()
        body = self._last_body(defect)
        self.assertIn('<b>%s</b>' % defect.defect_no, body)
        self.assertNotIn('&lt;b&gt;', body)

# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：缺失改善、自主檢查裡舊系統沒有的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的缺失沒有狀態流程：所有欄位隨時可改、刪除不看狀態（連確認視窗都沒有）、
日期欄位彼此不比對（後端 routes/errorRecord.js、前端 components/resource/m_errorRecord/）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（DF、QI 開頭的編號）。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


class EagleParityDefectCase(TransactionCase):
    """一般式與預約式缺失各一張的夾具。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.today()
        cls.project = env['project.project'].create({
            'name': '回復原版缺失（一般式）', 'code': 'EP-DF-G', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.res_project = env['project.project'].create({
            'name': '回復原版缺失（預約式）', 'code': 'EP-DF-R', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        Prefix = env['defect.improvement.prefix.config']
        Prefix.create({'project_id': cls.project.id, 'supervision_prefix': 'EPGS', 'contractor_prefix': 'EPGC'})
        Prefix.create({'project_id': cls.res_project.id, 'supervision_prefix': 'EPRS', 'contractor_prefix': 'EPRC'})
        cls.slip = env['reservation.notification.slip'].create({
            'project_id': cls.res_project.id, 'location': '回復原版測試地點'})
        cls.slip.sudo().write({'state': 'in_progress'})

    def _general(self, **extra):
        vals = {
            'project_id': self.project.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版一般式缺失', 'defect_location': 'B1',
            'source_type': 'daily_check', 'deadline': self.today + timedelta(days=7)}
        vals.update(extra)
        return self.env['general.defect.improvement'].create(vals)

    def _reservation(self, **extra):
        vals = {
            'slip_id': self.slip.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版預約式缺失', 'defect_location': 'B1',
            'notification_date': self.today}
        vals.update(extra)
        return self.env['reservation.defect.improvement'].create(vals)

    def _both(self):
        return (('一般式', self._general()), ('預約式', self._reservation()))


@tagged('post_install', '-at_install', 'construction_quality')
class TestEagleParityDefectDelete(EagleParityDefectCase):

    def test_non_draft_defect_can_be_deleted(self):
        """DF-06：不是草稿的缺失也能刪（照片跟著刪的邏輯不變）。"""
        for label, defect in self._both():
            for state in ('notified', 'verified', 'closed'):
                defect.sudo().write({'state': state})
            self.assertEqual(defect.state, 'closed', label)
            defect.unlink()
            self.assertFalse(defect.exists(), label)


@tagged('post_install', '-at_install', 'construction_quality')
class TestEagleParityDefectFlow(EagleParityDefectCase):

    def test_notify_without_deadline(self):
        """DF-01：沒有改善期限也能通知改善（舊系統期限不必填）。"""
        for label, defect in (('一般式', self._general(deadline=False)), ('預約式', self._reservation())):
            self.assertFalse(defect.deadline, label)
            defect.action_notify()
            self.assertEqual(defect.state, 'notified', label)

    def test_notify_message_without_deadline_has_no_false(self):
        """沒有期限時，通知訊息不能把期限印成 False。"""
        responsible = self.env['res.users'].create({'name': 'ep_responsible', 'login': 'ep_responsible'})
        defect = self._general(deadline=False, responsible_user_id=responsible.id)
        defect.action_notify()
        body = self.env['mail.message'].search(
            [('model', '=', defect._name), ('res_id', '=', defect.id), ('message_type', '=', 'notification')],
            order='id desc', limit=1).body
        self.assertTrue(body, '前提：有發出通知訊息')
        self.assertNotIn('False', body)

    def test_complete_improvement_without_corrective_action(self):
        """DF-03：沒有填矯正措施也能標記改善完成（舊系統矯正措施是選填）。"""
        for label, defect in self._both():
            defect.sudo().write({'state': 'improving'})
            self.assertFalse(defect.improvement_action, label)
            defect.action_complete_improvement()
            self.assertEqual(defect.state, 'improved', label)


@tagged('post_install', '-at_install', 'construction_quality')
class TestEagleParityInspect(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.itype = env['self.inspection.type'].create({'name': '回復原版檢查類型'})
        cls.project = env['project.project'].create({
            'name': '回復原版自主檢查（一般式）', 'code': 'EP-QI-G', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        res_project = env['project.project'].create({
            'name': '回復原版自主檢查（預約式）', 'code': 'EP-QI-R', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        cls.slip = env['reservation.notification.slip'].create({'project_id': res_project.id, 'location': '回復原版測試地點'})
        cls.slip.sudo().write({'state': 'in_progress'})

    def test_inspect_without_checklist_items(self):
        """QI-07：沒有檢查項目也能按「完成檢查」（舊系統儲存檢查單只檢查類型與名稱有填）。"""
        general = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'inspection_type_id': self.itype.id, 'sub_project_name': '回復原版分項'})
        reservation = self.env['reservation.self.inspection'].create({
            'slip_id': self.slip.id, 'inspection_type_id': self.itype.id, 'sub_project_name': '回復原版分項'})
        for label, insp in (('一般式', general), ('預約式', reservation)):
            self.assertFalse(insp.checklist_ids, '前提：%s 沒有檢查項目' % label)
            insp.action_inspect()
            self.assertEqual(insp.state, 'inspected', label)


@tagged('post_install', '-at_install', 'construction_quality')
class TestEagleParityDefectDates(EagleParityDefectCase):
    """DF-11：缺失的期限、通知日、發現日彼此不再比對先後（舊系統日期欄位各存各的）。"""

    def test_general_dates_in_any_order(self):
        defect = self._general(found_date=self.today, deadline=self.today - timedelta(days=3),
                               notification_date=self.today - timedelta(days=5))
        self.env.flush_all()
        self.assertLess(defect.deadline, defect.found_date)
        self.assertLess(defect.notification_date, defect.found_date)

    def test_reservation_deadline_before_notification(self):
        defect = self._reservation(deadline=self.today - timedelta(days=3))
        self.env.flush_all()
        self.assertLess(defect.deadline, defect.notification_date)

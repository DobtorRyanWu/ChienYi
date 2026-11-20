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

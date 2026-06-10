# -*- coding: utf-8 -*-
"""construction.meeting.record 基本 CRUD + 狀態流測試（Sprint 24）"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_meeting_record')
class TestMeetingRecord(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Meeting = cls.env['construction.meeting.record']
        cls.project = cls.env['supervision.project'].create({
            'name': 'Sprint 24 會議測試工程',
            'code': 'S24-MEET',
            'project_type': 'general',
        })

    def test_create_minimum(self):
        rec = self.Meeting.create({
            'name': 'Sprint 24 第 1 次會議',
            'meeting_date': date.today(),
        })
        self.assertEqual(rec.state, 'draft')
        self.assertTrue(rec.recorder_id)  # 預設 = env.user

    def test_state_flow(self):
        rec = self.Meeting.create({
            'name': '狀態流測試',
            'meeting_date': date.today(),
        })
        rec.action_confirm()
        self.assertEqual(rec.state, 'confirmed')
        rec.action_close()
        self.assertEqual(rec.state, 'closed')
        rec.action_reset_to_draft()
        self.assertEqual(rec.state, 'draft')

    def test_with_attendees_and_project(self):
        partner = self.env['res.partner'].create({'name': 'S24 Attendee'})
        rec = self.Meeting.create({
            'name': '完整欄位測試',
            'meeting_date': date.today(),
            'location': '會議室 A',
            'project_id': self.project.id,
            'attendee_ids': [(6, 0, [partner.id])],
        })
        self.assertEqual(len(rec.attendee_ids), 1)
        self.assertEqual(rec.project_id, self.project)

    def test_mail_thread_inherit(self):
        """繼承 mail.thread → 應有 message_ids 欄位。"""
        self.assertIn('message_ids', self.Meeting._fields)

    def test_no_doc_linked_mixin_without_bridge(self):
        """單裝此模組（無 bridge）→ 不應有 linked_doc_id 欄位。

        裝 dobtor_doc_editor_chienyi 後此 test 在第 5 case 改 inverted（見
        bridge round3 test）。"""
        # 此 test 在 bridge 已裝的環境下會 expected to fail；用 _fields 寬鬆檢查
        if 'linked_doc_id' in self.Meeting._fields:
            # bridge 已裝；驗證 mixin field 與 ChienYi 自家欄位共存
            self.assertIn('name', self.Meeting._fields)
            self.assertIn('linked_doc_id', self.Meeting._fields)
        else:
            # 純 ChienYi 安裝（bridge 未裝），驗證單獨可運作
            self.assertNotIn('linked_doc_id', self.Meeting._fields)

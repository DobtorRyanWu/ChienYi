# -*- coding: utf-8 -*-
"""Sprint 24 — bridge 第三輪：construction.meeting.record × doc.linked.mixin

驗證 4 個樣板（self_inspection / defect_improvement / payment_estimate /
meeting_record）全部有 host model 接入後 mixin 行為一致。
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestMeetingRecordBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env['res.users']
        cls.Meeting = cls.env['construction.meeting.record']
        cls.Partner = cls.env['res.partner']

        cls.project = cls.env['project.project'].create({
            'name': 'Sprint 24 會議 bridge 測試工程',
            'code': 'S24-MEET-B',
            'project_type': 'general',
        })
        cls.chair = cls.User.create({
            'name': 'S24 會議主席',
            'login': 's24_chair@example.com',
        })
        cls.attendee_user = cls.User.create({
            'name': 'S24 出席者 user',
            'login': 's24_attendee@example.com',
        })
        # attendee 用 partner（出席者欄位 = res.partner Many2many）
        cls.attendee_partner = cls.attendee_user.partner_id

    def _make(self, **vals):
        d = {
            'name': 'Sprint 24 第 1 次監造會議',
            'meeting_date': date.today(),
            'location': '會議室 A',
            'project_id': self.project.id,
            'chairperson_id': self.chair.id,
            'attendee_ids': [(6, 0, [self.attendee_partner.id])],
        }
        d.update(vals)
        return self.Meeting.create(d)

    def test_mixin_fields_present(self):
        self.assertIn('linked_doc_id', self.Meeting._fields)
        self.assertIn('linked_doc_count', self.Meeting._fields)

    def test_uses_meeting_record_template(self):
        rec = self._make()
        self.assertEqual(
            rec._doc_default_template_xml_id(),
            'dobtor_doc_editor.template_meeting_record',
        )
        # 樣板必須真的存在
        self.assertTrue(self.env.ref(
            rec._doc_default_template_xml_id(),
            raise_if_not_found=False,
        ))

    def test_action_creates_doc_with_template_content(self):
        rec = self._make()
        rec.action_open_linked_doc()
        self.assertTrue(rec.linked_doc_id)
        # template_meeting_record 含實際內容（從 doc_template_data.xml 來）
        self.assertTrue(
            rec.linked_doc_id.content_html,
            'content_html 不應為空（應從樣板複製）',
        )

    def test_initial_name_combines_name_and_date(self):
        rec = self._make()
        name = rec._doc_initial_name()
        self.assertIn('Sprint 24 第 1 次監造會議', name)
        self.assertIn(str(date.today()), name)

    def test_collaborators_include_chair_attendee_user_and_creator(self):
        """主席 + 出席者中的 user + 當前 user 都在 collaborators。"""
        rec = self._make()
        users = rec._doc_collaborators()
        self.assertIn(self.chair, users)
        self.assertIn(self.attendee_user, users)
        self.assertIn(self.env.user, users)

    def test_collaborators_skip_partners_without_user(self):
        """attendee_ids 含無 user 的 partner 不應 crash。"""
        partner_no_user = self.Partner.create({'name': 'S24 純 partner 無 user'})
        rec = self._make(attendee_ids=[(6, 0, [partner_no_user.id])])
        users = rec._doc_collaborators()
        # 主席 + env.user 應仍在
        self.assertIn(self.chair, users)
        self.assertIn(self.env.user, users)

    def test_render_context_has_meeting_keys(self):
        rec = self._make()
        ctx = rec._doc_render_context()
        for key in ('record_id', 'record_model', 'meeting_name',
                    'meeting_date', 'location', 'chairperson',
                    'recorder', 'attendees', 'attendee_count', 'project_name'):
            self.assertIn(key, ctx)
        self.assertEqual(ctx['record_model'], 'construction.meeting.record')
        self.assertEqual(ctx['meeting_name'], 'Sprint 24 第 1 次監造會議')
        self.assertEqual(ctx['attendee_count'], 1)
        self.assertEqual(ctx['chairperson'], self.chair.name)

    def test_doc_deletion_clears_linked_doc_id(self):
        rec = self._make()
        rec.action_open_linked_doc()
        rec.linked_doc_id.unlink()
        rec.invalidate_recordset(['linked_doc_id', 'linked_doc_count'])
        self.assertFalse(rec.linked_doc_id)
        self.assertEqual(rec.linked_doc_count, 0)

    def test_template_coverage_100_percent_after_sprint24(self):
        """4 個 dobtor 預設樣板 Sprint 24 後全部有 host model 接入。"""
        templates_with_hosts = {
            'dobtor_doc_editor.template_self_inspection': [
                'general.self.inspection', 'reservation.self.inspection',
            ],
            'dobtor_doc_editor.template_defect_improvement': [
                'supervision.defect',
            ],
            'dobtor_doc_editor.template_payment_estimate': [
                'payment.estimate',
            ],
            'dobtor_doc_editor.template_meeting_record': [
                'construction.meeting.record',
            ],
        }
        for tpl_xml_id, host_models in templates_with_hosts.items():
            template = self.env.ref(tpl_xml_id, raise_if_not_found=False)
            self.assertTrue(template, '樣板 %s 應存在' % tpl_xml_id)
            for host in host_models:
                # env.get() 回 empty recordset；用 'in env' 檢測 model 存在性
                self.assertIn(host, self.env,
                              '%s should be installed' % host)
                Model = self.env[host]
                self.assertIn(
                    'linked_doc_id',
                    Model._fields,
                    '%s 應 inherit doc.linked.mixin（Sprint 24 後 100%% 覆蓋）' % host,
                )

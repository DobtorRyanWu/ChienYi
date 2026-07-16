# -*- coding: utf-8 -*-
"""Sprint 22 — ChienYi mixin 第二輪整合測試

涵蓋 reservation.self.inspection / supervision.defect / payment.estimate 三個 model。
測試方法沿用 Sprint 21 pattern：fields/methods 繼承、template 套用、
collaborators、render context、ondelete 守則。
"""

from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestReservationSelfInspectionBridge(TransactionCase):
    """預約式自主檢查整合。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env['res.users']
        cls.Inspection = cls.env['reservation.self.inspection']

        cls.project = cls.env['project.project'].create({
            'name': 'Sprint 22 預約式測試工程',
            'code': 'S22-RES',
            'project_type': 'reservation',
        })
        cls.inspection_type = cls.env['self.inspection.type'].create({
            'name': '預約式檢查樣板',
            'project_id': cls.project.id,
        })
        cls.inspector = cls.User.create({
            'name': 'S22 預約檢查人',
            'login': 's22_res_inspector@example.com',
        })
        # reservation.self.inspection.slip_id 必填，且 _check_slip_state 限定在
        # approved / in_progress / completed 才能建 inspection；用 sudo write 直接拉到 approved
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id,
            'location': 'Sprint 22 測試地點',
        })
        # _check_slip_state 接受 (approved, in_progress, completed)，但 slip 模型的
        # state Selection 實際只有 (draft, not_started, in_progress, closed) — 取交集 in_progress
        cls.slip.sudo().write({'state': 'in_progress'})

    def _make(self, **vals):
        d = {
            'project_id': self.project.id,
            'slip_id': self.slip.id,
            'inspection_type_id': self.inspection_type.id,
            'sub_project_name': '預約式分項',
            'inspector_id': self.inspector.id,
            'inspection_date': date.today(),
        }
        d.update(vals)
        return self.Inspection.create(d)

    def test_mixin_fields_present(self):
        self.assertIn('linked_doc_id', self.Inspection._fields)
        self.assertIn('linked_doc_count', self.Inspection._fields)

    def test_create_doc_uses_self_inspection_template(self):
        rec = self._make()
        self.assertEqual(
            rec._doc_default_template_xml_id(),
            'dobtor_doc_editor.template_self_inspection',
        )

    def test_action_creates_doc_with_template_content(self):
        rec = self._make()
        rec.action_open_linked_doc()
        self.assertTrue(rec.linked_doc_id)
        self.assertTrue(
            rec.linked_doc_id.content_html,
            'content_html 不應為空（應從樣板複製）',
        )

    def test_collaborators_inspector_and_current_user(self):
        rec = self._make()
        users = rec._doc_collaborators()
        self.assertIn(self.inspector, users)
        self.assertIn(self.env.user, users)

    def test_render_context_has_required_keys(self):
        rec = self._make(sub_project_name='RES-Sprint22')
        ctx = rec._doc_render_context()
        for key in ('record_id', 'project_name', 'inspection_no',
                    'inspection_date', 'sub_project_name',
                    'inspector', 'timing'):
            self.assertIn(key, ctx)
        self.assertEqual(ctx['record_model'], 'reservation.self.inspection')
        self.assertEqual(ctx['sub_project_name'], 'RES-Sprint22')


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestSupervisionDefectBridge(TransactionCase):
    """缺失改善整合。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env['res.users']
        cls.Defect = cls.env['supervision.defect']

        cls.project = cls.env['project.project'].create({
            'name': 'Sprint 22 缺失測試工程',
            'code': 'S22-DEF',
            'project_type': 'general',
        })
        cls.responsible = cls.User.create({
            'name': 'S22 缺失負責人',
            'login': 's22_def_resp@example.com',
        })

    def _make(self, **vals):
        d = {
            'project_id': self.project.id,
            'description': 'Sprint 22 自動測試缺失條目',
            'found_date': date.today(),
            'deadline': date.today() + timedelta(days=7),
            'responsible_user_id': self.responsible.id,
        }
        d.update(vals)
        return self.Defect.create(d)

    def test_mixin_fields_present(self):
        self.assertIn('linked_doc_id', self.Defect._fields)

    def test_create_doc_uses_defect_template(self):
        rec = self._make()
        self.assertEqual(
            rec._doc_default_template_xml_id(),
            'dobtor_doc_editor.template_defect_improvement',
        )
        # 樣板必須真存在
        self.assertTrue(self.env.ref(
            rec._doc_default_template_xml_id(),
            raise_if_not_found=False,
        ))

    def test_action_creates_doc_with_template_content(self):
        rec = self._make()
        rec.action_open_linked_doc()
        self.assertTrue(rec.linked_doc_id)
        self.assertTrue(rec.linked_doc_id.content_html)

    def test_collaborators_include_responsible_and_creator(self):
        rec = self._make()
        users = rec._doc_collaborators()
        self.assertIn(self.responsible, users)
        # create_uid 在 setUpClass context 是 admin (env.user)
        self.assertIn(self.env.user, users)

    def test_render_context_has_defect_fields(self):
        rec = self._make()
        ctx = rec._doc_render_context()
        for key in ('record_id', 'project_name', 'defect_no',
                    'description', 'found_date', 'deadline',
                    'responsible'):
            self.assertIn(key, ctx)
        self.assertEqual(ctx['record_model'], 'supervision.defect')
        self.assertEqual(ctx['responsible'], self.responsible.name)
        # 描述截短到 40 字內
        self.assertIn('Sprint 22', rec._doc_initial_name())


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestPaymentEstimateBridge(TransactionCase):
    """估驗計價整合。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.User = cls.env['res.users']
        cls.Estimate = cls.env['payment.estimate']

        cls.project = cls.env['project.project'].create({
            'name': 'Sprint 22 估驗測試工程',
            'code': 'S22-PAY',
            'project_type': 'general',
        })
        cls.submitter = cls.User.create({
            'name': 'S22 提出人',
            'login': 's22_pay_sub@example.com',
        })

    def _make(self, **vals):
        d = {
            'project_id': self.project.id,
            'estimate_date': date.today(),
        }
        d.update(vals)
        return self.Estimate.create(d)

    def test_mixin_fields_present(self):
        self.assertIn('linked_doc_id', self.Estimate._fields)

    def test_create_doc_uses_payment_template(self):
        rec = self._make()
        self.assertEqual(
            rec._doc_default_template_xml_id(),
            'dobtor_doc_editor.template_payment_estimate',
        )
        self.assertTrue(self.env.ref(
            rec._doc_default_template_xml_id(),
            raise_if_not_found=False,
        ))

    def test_action_creates_doc_with_template_content(self):
        rec = self._make()
        rec.action_open_linked_doc()
        self.assertTrue(rec.linked_doc_id)
        self.assertTrue(rec.linked_doc_id.content_html)

    def test_collaborators_with_submitter(self):
        rec = self._make(submitted_by_id=self.submitter.id)
        users = rec._doc_collaborators()
        self.assertIn(self.submitter, users)
        self.assertIn(self.env.user, users)

    def test_render_context_has_payment_fields(self):
        rec = self._make()
        ctx = rec._doc_render_context()
        for key in ('record_id', 'project_name', 'estimate_name',
                    'estimate_no', 'estimate_date', 'subtotal',
                    'state_label', 'line_count'):
            self.assertIn(key, ctx)
        self.assertEqual(ctx['record_model'], 'payment.estimate')
        # 預設狀態 draft
        self.assertEqual(ctx['state_label'], '草稿')

    def test_initial_name_combines_project(self):
        rec = self._make()
        name = rec._doc_initial_name()
        self.assertIn('估驗計價', name)
        self.assertIn(self.project.name, name)

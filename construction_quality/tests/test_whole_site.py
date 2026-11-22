# -*- coding: utf-8 -*-
"""預約式自主檢查「全工區」（18.0.6.14.0，2026-11-22）。

使用者需求：預約式自主檢查原本一定要掛一張通報單；多一個「全工區」，
跟「掛哪一張通報單」二擇一：
- 勾全工區 → 不掛通報單
- 不勾全工區 → 照舊一定要選一張通報單
- 兩個都有、兩個都沒有 → 擋下
"""

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_quality')
class TestWholeSite(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': '全工區負責人', 'login': 'qa_whole_site_resp'})
        cls.project = cls.env['project.project'].create({
            'name': '全工區測試（預約式）', 'code': 'QA-WHOLE-R',
            'project_type': 'reservation', 'company_id': cls.env.company.id})
        cls.project.activity_inspection_user_id = cls.user
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': '全工區測試地點'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.itype = cls.env['self.inspection.type'].create({
            'name': '全工區測試類型', 'project_id': cls.project.id})
        cls.Insp = cls.env['reservation.self.inspection']

    def _vals(self, **kw):
        vals = {'inspection_type_id': self.itype.id,
                'inspection_date': fields.Date.today(),
                'sub_project_name': '全工區測試'}
        vals.update(kw)
        return vals

    # --- 欄位與畫面 ---
    def test_01_field_exists_and_slip_not_required(self):
        self.assertIn('is_whole_site', self.Insp._fields)
        self.assertEqual(self.Insp._fields['is_whole_site'].string, '全工區')
        self.assertFalse(self.Insp._fields['slip_id'].required,
                         '通報單改由「二擇一」約束管，欄位本身不再必填')

    def test_02_db_column_nullable(self):
        self.env.cr.execute("""
            SELECT is_nullable FROM information_schema.columns
             WHERE table_name = 'reservation_self_inspection' AND column_name = 'slip_id'""")
        self.assertEqual(self.env.cr.fetchone()[0], 'YES')

    def test_03_form_view_has_whole_site(self):
        arch = self.Insp.get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('name="is_whole_site"', arch)

    # --- 二擇一 ---
    def test_10_whole_site_without_slip_ok(self):
        insp = self.Insp.create(self._vals(project_id=self.project.id, is_whole_site=True))
        self.assertTrue(insp.is_whole_site)
        self.assertFalse(insp.slip_id)
        self.assertEqual(insp.project_id, self.project)
        # 取號照工程（以前看通報單的工程，沒有通報單會取成 /）
        self.assertTrue(insp.inspection_no and insp.inspection_no != '/', insp.inspection_no)

    def test_11_whole_site_responsible_from_project(self):
        expected = self.user
        insp = self.Insp.create(self._vals(project_id=self.project.id, is_whole_site=True))
        self.assertEqual(insp.responsible_user_id, expected)

    def test_12_slip_only_ok(self):
        insp = self.Insp.create(self._vals(slip_id=self.slip.id))
        self.assertFalse(insp.is_whole_site)
        self.assertEqual(insp.slip_id, self.slip)
        self.assertEqual(insp.project_id, self.project)

    def test_13_both_blocked(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Insp.create(self._vals(slip_id=self.slip.id, is_whole_site=True))

    def test_14_neither_blocked(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Insp.create(self._vals(project_id=self.project.id))

    def test_20_write_switch_to_whole_site(self):
        insp = self.Insp.create(self._vals(slip_id=self.slip.id))
        # 只勾全工區、沒拿掉通報單 → 兩個都有 → 擋
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                insp.write({'is_whole_site': True})
        insp.write({'is_whole_site': True, 'slip_id': False})
        self.assertTrue(insp.is_whole_site)
        self.assertFalse(insp.slip_id)
        self.assertEqual(insp.project_id, self.project, '拿掉通報單時工程不變')

    def test_21_write_switch_back_to_slip(self):
        insp = self.Insp.create(self._vals(project_id=self.project.id, is_whole_site=True))
        # 取消全工區卻沒選通報單 → 兩個都沒有 → 擋
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                insp.write({'is_whole_site': False})
        insp.write({'is_whole_site': False, 'slip_id': self.slip.id})
        self.assertEqual(insp.slip_id, self.slip)

    def test_22_onchange_whole_site_clears_slip(self):
        insp = self.Insp.new(self._vals(project_id=self.project.id, slip_id=self.slip.id))
        insp.is_whole_site = True
        insp._onchange_whole_site_clear_slip()
        self.assertFalse(insp.slip_id)

    # --- 表單帶入（照後台表單的必填／隱藏規則走，Form 模擬畫面操作）---
    def test_23_form_whole_site_fills_fields(self):
        f = Form(self.Insp)
        f.project_id = self.project
        f.inspection_type_id = self.itype
        f.sub_project_name = '全工區表單'
        f.is_whole_site = True
        self.assertFalse(f.slip_id, '勾全工區後通報單是空的')
        self.assertEqual(f.responsible_user_id, self.user, '勾全工區時馬上由工程帶入自主檢查負責人')
        insp = f.save()
        self.assertTrue(insp.is_whole_site)
        self.assertFalse(insp.slip_id)
        self.assertEqual(insp.project_id, self.project)
        self.assertEqual(insp.responsible_user_id, self.user)
        self.assertEqual(insp.sub_project_name, '全工區表單')
        self.assertTrue(insp.inspection_no and insp.inspection_no != '/')
        self.assertEqual(insp.company_id, self.project.company_id)

    def test_24_form_slip_then_whole_site(self):
        f = Form(self.Insp)
        f.project_id = self.project
        f.slip_id = self.slip
        f.inspection_type_id = self.itype
        f.sub_project_name = '先選通報單'
        f.is_whole_site = True
        self.assertFalse(f.slip_id, '先選通報單再勾全工區，通報單被清掉')
        insp = f.save()
        self.assertTrue(insp.is_whole_site)
        self.assertFalse(insp.slip_id)
        self.assertFalse(insp.slip_location, '全工區沒有通報單地點')

    def test_25_form_slip_required_without_whole_site(self):
        f = Form(self.Insp)
        f.project_id = self.project
        f.inspection_type_id = self.itype
        f.sub_project_name = '沒選'
        with self.assertRaises(AssertionError):   # 表單上通報單必填（required="not is_whole_site"）
            f.save()

    def test_26_form_slip_path_unchanged(self):
        f = Form(self.Insp)
        f.project_id = self.project
        f.slip_id = self.slip
        f.inspection_type_id = self.itype
        f.sub_project_name = '掛通報單'
        self.assertEqual(f.responsible_user_id, self.user)
        insp = f.save()
        self.assertEqual(insp.slip_id, self.slip)
        self.assertFalse(insp.is_whole_site)
        self.assertEqual(insp.slip_location, '全工區測試地點')

    def test_27_doc_context_slip_no(self):
        insp = self.Insp.create(self._vals(project_id=self.project.id, is_whole_site=True))
        if not hasattr(insp, '_doc_render_context'):
            self.skipTest('dobtor_doc_editor_chienyi 沒裝')
        ctx = insp._doc_render_context()
        self.assertEqual(ctx['slip_no'], '全工區')
        self.assertEqual(ctx['project_name'], self.project.name)

    # --- 顯示 ---
    def test_30_report_shows_whole_site(self):
        insp = self.Insp.create(self._vals(project_id=self.project.id, is_whole_site=True))
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'construction_quality.action_report_reservation_self_inspection', insp.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('全工區', html)
        self.assertNotIn('False', html.split('通報單')[1][:200] if '通報單' in html else '')


@tagged('post_install', '-at_install', 'construction_quality')
class TestWholeSiteDefect(TransactionCase):
    """預約式缺失改善也一樣：全工區跟所屬通報單二擇一（2026-11-22）"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '全工區缺失測試', 'code': 'QA-WHOLE-D',
            'project_type': 'reservation', 'company_id': cls.env.company.id})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'QWS', 'contractor_prefix': 'QWC'})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': '全工區缺失地點'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.Defect = cls.env['reservation.defect.improvement']

    def _vals(self, **kw):
        vals = {'defect_description': '全工區缺失', 'record_type': 'supervision',
                'check_type': 'construction', 'found_date': fields.Date.today()}
        vals.update(kw)
        return vals

    def test_01_field_and_views(self):
        self.assertIn('is_whole_site', self.Defect._fields)
        self.assertFalse(self.Defect._fields['slip_id'].required)
        arch = self.Defect.get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('name="is_whole_site"', arch)
        self.env.cr.execute("""
            SELECT is_nullable FROM information_schema.columns
             WHERE table_name = 'reservation_defect_improvement' AND column_name = 'slip_id'""")
        self.assertEqual(self.env.cr.fetchone()[0], 'YES')

    def test_10_whole_site_ok(self):
        d = self.Defect.create(self._vals(project_id=self.project.id, is_whole_site=True))
        self.assertFalse(d.slip_id)
        self.assertEqual(d.project_id, self.project)
        self.assertTrue(d.defect_no)

    def test_11_slip_only_ok(self):
        d = self.Defect.create(self._vals(slip_id=self.slip.id))
        self.assertEqual(d.project_id, self.project)
        self.assertFalse(d.is_whole_site)

    def test_12_both_blocked(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Defect.create(self._vals(slip_id=self.slip.id, is_whole_site=True))

    def test_13_neither_blocked(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Defect.create(self._vals(project_id=self.project.id))

    def test_14_write_switch(self):
        d = self.Defect.create(self._vals(slip_id=self.slip.id))
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                d.write({'is_whole_site': True})
        d.write({'is_whole_site': True, 'slip_id': False})
        self.assertEqual(d.project_id, self.project)
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                d.write({'is_whole_site': False})

    def test_15_onchange_clears_slip(self):
        d = self.Defect.new(self._vals(project_id=self.project.id, slip_id=self.slip.id))
        d.is_whole_site = True
        d._onchange_whole_site_clear_slip()
        self.assertFalse(d.slip_id)

    def test_21_default_group_order_project_then_slip(self):
        """後台預約式缺失清單預設分組：先工程、再通報單（2026-11-22 使用者回報順序錯）"""
        from odoo.tools.safe_eval import safe_eval
        for xid in ('construction_quality.action_reservation_defect_improvement',
                    'construction_quality.action_reservation_defect_improvement_supervision',
                    'construction_quality.action_reservation_defect_improvement_contractor'):
            ctx = safe_eval(self.env.ref(xid).context or '{}')
            self.assertLess(ctx.get('search_default_group_project'), ctx.get('search_default_group_slip'),
                            '%s：工程的分組順位要在通報單前面' % xid)

    def test_20_search_filters(self):
        for model in ('reservation.defect.improvement', 'reservation.self.inspection'):
            arch = self.env[model].get_views([(False, 'search')])['views']['search']['arch']
            self.assertIn('name="whole_site"', arch, model)

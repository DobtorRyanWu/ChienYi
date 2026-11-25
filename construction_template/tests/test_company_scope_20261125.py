# -*- coding: utf-8 -*-
"""文件樣板的公司檢查與複製（W5 H1、H2，2026-11-25）。

H1：_check_company_allowed 原本只要 vals 帶 company_id 就檢查，不比新舊值——RPC 或匯入帶「沒改的」company_id
    （例：專案層級樣板的 company_id 與工程公司不同，可見範圍看工程的公司），會被誤擋。改成只檢查值真的有變的記錄。
H2（查證後不改）：複製專案層級樣板時，副本（沒有工程的公司層級樣板）歸「目前選的公司」。審查曾建議改成歸工程的公司，
    但唯一鍵 unique_default_type_company（同類型、同公司、非預設只能一份）讓副本一定撞到原樣板自己——
    dev 實測真的專案層級樣板兩種情況都 UniqueViolation。所以維持歸目前選的公司（3.16.1，S5 審查 F1），這裡鎖住。
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

ADMIN = 'construction_supervision_base.group_supervisor_admin'
TTYPE = 'invoice_detail'


@tagged('post_install', '-at_install', 'construction_template')
class TestTemplateCompanyScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_a = env['res.company'].create({'name': 'TPLW5 公司 A', 'company_type': 'supervision'})
        cls.co_b = env['res.company'].create({'name': 'TPLW5 公司 B', 'company_type': 'supervision'})
        cls.co_c = env['res.company'].create({'name': 'TPLW5 公司 C', 'company_type': 'supervision'})
        cls.user_a = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'tplw5_a', 'login': 'tplw5_a', 'company_id': cls.co_a.id,
            'company_ids': [(6, 0, cls.co_a.ids)],
            'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref(ADMIN).id])]})
        cls.user_ab = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'tplw5_ab', 'login': 'tplw5_ab', 'company_id': cls.co_a.id,
            'company_ids': [(6, 0, (cls.co_a | cls.co_b).ids)],
            'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref(ADMIN).id])]})
        Project = env['project.project']
        cls.proj_a = Project.create({'name': 'TPLW5 工程 A', 'code': 'TPLW5-A', 'project_type': 'general',
                                     'state': 'construction', 'company_id': cls.co_a.id})
        cls.proj_b = Project.create({'name': 'TPLW5 工程 B', 'code': 'TPLW5-B', 'project_type': 'general',
                                     'state': 'construction', 'company_id': cls.co_b.id})

    def _template(self, **vals):
        return self.env['document.template'].sudo().create(
            {'name': 'TPLW5 樣板', 'template_type': TTYPE, **vals})

    def _as(self, records, user):
        """以 user 身分、允許公司＝帳號自己的公司（和網頁用戶端選好公司的情況一樣）。"""
        return records.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    # ═══ H1 ═══════════════════════════════════════════════════════════
    def test_h1_unchanged_company_in_vals_is_not_checked(self):
        """專案層級樣板（工程在 A）的 company_id 是 B（不在 A 帳號的允許公司內）：帶著沒改的 company_id 改名稱，
        修前被 _check_company_allowed 誤擋（ValidationError），修後通過。"""
        template = self._template(project_id=self.proj_a.id, company_id=self.co_b.id)
        self._as(template, self.user_a).write({'company_id': self.co_b.id, 'name': 'TPLW5 改名'})
        self.assertEqual(template.name, 'TPLW5 改名')
        self.assertEqual(template.company_id, self.co_b)

    def test_h1_real_change_outside_allowed_companies_still_refused(self):
        """值真的有變、而且改到允許公司以外：照樣擋（F2 原本要擋的）。"""
        template = self._template(company_id=self.co_a.id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._as(template, self.user_a).write({'company_id': self.co_b.id})
        self.env.invalidate_all()
        self.assertEqual(template.company_id, self.co_a, '被拒之後資料沒變')

    def test_h1_batch_mixes_unchanged_and_changed(self):
        """同一批裡一筆沒改、一筆真的改到允許公司以外：整批照樣被擋，沒改的那筆不被誤擋。"""
        same = self._template(project_id=self.proj_a.id, company_id=self.co_b.id)
        moved = self._template(company_id=self.co_a.id)
        both = self._as(same | moved, self.user_a)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            both.write({'company_id': self.co_b.id})

    # ═══ H2（維持原行為）═════════════════════════════════════════════
    def test_h2_duplicate_project_template_goes_to_current_company(self):
        """工程 B 的專案層級樣板（樣板公司＝工程公司 B，實際資料都是這樣），目前選的公司是 A：
        複製要成功，副本是公司層級、歸目前選的公司 A。
        改成「歸工程的公司」的話副本會撞到原樣板自己的唯一鍵（同類型、同公司、非預設），複製直接失敗。"""
        template = self._template(project_id=self.proj_b.id, company_id=self.co_b.id)
        action = self._as(template, self.user_ab).action_duplicate()
        copy = self.env['document.template'].browse(action['res_id'])
        self.assertFalse(copy.project_id, '前提：副本沒有工程（公司層級）')
        self.assertEqual(copy.company_id, self.co_a)

    def test_h2_duplicate_without_project_belongs_to_current_company(self):
        """3.16.1（S5 審查 F1）要保留：沒有工程的樣板，副本歸複製的人目前的公司。"""
        template = self._template(company_id=self.co_b.id)
        action = self._as(template, self.user_ab).action_duplicate()
        copy = self.env['document.template'].browse(action['res_id'])
        self.assertEqual(copy.company_id, self.co_a)

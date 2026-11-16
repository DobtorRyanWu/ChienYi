# -*- coding: utf-8 -*-
"""自主檢查／通報單的單號依工程所屬公司取號（construction_supervision_base 的
ir.sequence._next_by_code_for_project）。

修前：create() 用 next_by_code()，依「目前選的公司」取號——替別家公司的工程開單會用到
目前公司的計數器；目前公司沒有序列時寫成「/」（任泰 jt 10-23 自主檢查 69/118 張）。
另外欄位預設值也呼叫 next_by_code()，後台一開表單就先吃掉一個號。
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged

PADDING = 4


@tagged('post_install', '-at_install', 'construction_quality')
class TestNumberByProjectCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env['res.company']
        cls.company_b = Company.create({'name': '單號測試 B 監造'})
        cls.company_c = Company.create({'name': '單號測試 C（沒有序列）'})
        # B 公司自己的序列，前綴跟主公司不同，才分得出用了誰的計數器
        Seq = cls.env['ir.sequence']
        for code, prefix in (('general.self.inspection', 'GSI-B-'),
                             ('reservation.self.inspection', 'RSI-B-'),
                             ('reservation.notification.slip', 'SLIP-B-')):
            Seq.create({'name': '單號測試 %s' % code, 'code': code, 'prefix': prefix,
                        'padding': PADDING, 'company_id': cls.company_b.id})
        Project = cls.env['project.project']
        cls.project_b = Project.create({'name': '單號測試（一般式）', 'code': 'NUM-B',
                                        'project_type': 'general', 'company_id': cls.company_b.id})
        cls.res_project_b = Project.create({'name': '單號測試（預約式）', 'code': 'NUM-B-R',
                                            'project_type': 'reservation',
                                            'company_id': cls.company_b.id})
        cls.itype = cls.env['self.inspection.type'].create({'name': '單號測試類型'})

    def _general(self, env=None):
        return (env or self.env)['general.self.inspection'].create({
            'project_id': self.project_b.id, 'inspection_type_id': self.itype.id,
            'sub_project_name': '單號測試', 'inspection_date': fields.Date.today()})

    def test_general_inspection_uses_project_company(self):
        """目前公司是主公司，替 B 的工程開一般式自主檢查 → B 的號。"""
        self.assertNotEqual(self.env.company, self.company_b)
        self.assertTrue(self._general().name.startswith('GSI-B-'))

    def test_current_company_without_sequence_gets_project_number(self):
        """目前公司 C 沒有自主檢查序列：修前是「/」，修後拿 B 的號。"""
        env_c = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_c.id]))
        self.assertFalse(env_c['ir.sequence'].next_by_code('general.self.inspection'),
                         '前提：C 沒有序列，原生取法會回 False')
        self.assertTrue(self._general(env_c).name.startswith('GSI-B-'))

    def test_form_default_does_not_take_a_number(self):
        """後台開新表單只顯示「/」，存檔時才取號（不再用目前公司先吃一個號）。"""
        self.assertEqual(self.env['general.self.inspection'].default_get(['name'])['name'], '/')
        self.assertEqual(
            self.env['reservation.self.inspection'].default_get(['inspection_no'])['inspection_no'], '/')

    def test_slip_and_reservation_inspection_follow_project_company(self):
        """通報單直接看工程；預約式自主檢查的工程是通報單的 related 欄位，也要拿 B 的號。"""
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.res_project_b.id, 'location': '單號測試地點'})
        self.assertTrue(slip.slip_number.startswith('SLIP-B-'))
        slip.sudo().write({'state': 'in_progress'})
        insp = self.env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': self.itype.id,
            'sub_project_name': '單號測試', 'inspection_date': fields.Date.today()})
        self.assertTrue(insp.inspection_no.startswith('RSI-B-'))

    def test_slip_copy_uses_project_company(self):
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.res_project_b.id, 'location': '單號測試地點（複製）'})
        self.assertTrue(slip.copy().slip_number.startswith('SLIP-B-'))

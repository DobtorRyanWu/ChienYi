# -*- coding: utf-8 -*-
"""ir.sequence._next_by_code_for_project：單號依工程所屬公司取號。

Odoo 的 next_by_code() 依「登入者目前選的公司」找序列；本系統的單據序列綁公司，
所以目前公司跟工程公司不同時會用到別家的計數器，目前公司沒有序列時會變成「/」
（任泰 jt 10-23：自主檢查 69/118、試驗紀錄 76/615 張是「/」）。
"""
from odoo.tests import TransactionCase, tagged

CODE = 'chienyi.test.doc.number'
HELPER_LOGGER = 'odoo.addons.construction_supervision_base.models.ir_sequence'
PADDING = 4
# no_gap：號碼存在資料表，跟著測試 rollback；standard 用 PostgreSQL sequence，取過的號不會退回，
# 前一支測試用掉的號會讓下一支的期望值錯開
IMPLEMENTATION = 'no_gap'


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestSequenceByProjectCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env['res.company']
        cls.company_a = cls.env.company  # 「目前選的公司」
        cls.company_b = Company.create({'name': '取號測試 B 監造'})
        cls.company_c = Company.create({'name': '取號測試 C 監造（沒有序列）'})
        Seq = cls.env['ir.sequence']
        cls.seq_a = Seq.create({'name': '取號測試 A', 'code': CODE, 'prefix': 'A-',
                                'padding': PADDING, 'implementation': IMPLEMENTATION,
                                'company_id': cls.company_a.id})
        cls.seq_b = Seq.create({'name': '取號測試 B', 'code': CODE, 'prefix': 'B-',
                                'padding': PADDING, 'implementation': IMPLEMENTATION,
                                'company_id': cls.company_b.id})
        Project = cls.env['project.project']
        cls.project_b = Project.create({'name': '取號測試工程 B', 'code': 'SEQ-B',
                                        'project_type': 'general', 'company_id': cls.company_b.id})
        cls.project_c = Project.create({'name': '取號測試工程 C', 'code': 'SEQ-C',
                                        'project_type': 'general', 'company_id': cls.company_c.id})

    def _next(self, project, code=CODE, env=None):
        return (env or self.env)['ir.sequence']._next_by_code_for_project(code, project)

    @staticmethod
    def _next_actual(seq):
        # number_next_actual 是計算欄位（讀資料庫序列），會快取；前後比較前要先清掉
        seq.invalidate_recordset(['number_next_actual'])
        return seq.number_next_actual

    def _company_seqs(self, company):
        return self.env['ir.sequence'].search([('code', '=', CODE), ('company_id', '=', company.id)])

    def test_core_lookup_follows_current_company(self):
        """修前的行為（Odoo 原生）：目前公司是 A，就拿 A 的號，不管單據是哪個工程的。"""
        self.assertTrue(self.env['ir.sequence'].with_company(self.company_a)
                        .next_by_code(CODE).startswith('A-'))

    def test_number_follows_project_company(self):
        """目前公司是 A，替 B 公司的工程開單 → 拿 B 的號，A 的計數器不動。"""
        a_next = self._next_actual(self.seq_a)
        self.assertEqual(self._next(self.project_b), 'B-0001')
        self.assertEqual(self._next(self.project_b), 'B-0002')
        self.assertEqual(self._next_actual(self.seq_a), a_next)

    def test_sequence_lookup_does_not_take_a_number(self):
        """_sequence_for_project 只查不取號（dev 示範工具的唯讀驗證用它）。"""
        b_next = self._next_actual(self.seq_b)
        found = self.env['ir.sequence'].with_company(self.company_a)._sequence_for_project(
            CODE, self.project_b)
        self.assertEqual(found, self.seq_b)
        self.assertEqual(self._next_actual(self.seq_b), b_next)

    def test_project_id_is_accepted(self):
        """呼叫端多半手上只有 vals['project_id']。"""
        self.assertEqual(self._next(self.project_b.id), 'B-0001')

    def test_current_company_without_sequence_does_not_get_slash(self):
        """目前公司 C 沒有這支序列：原生回 False（→「/」）；依工程公司取號則拿到 B 的號。"""
        env_c = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_c.id]))
        self.assertFalse(env_c['ir.sequence'].next_by_code(CODE))
        self.assertEqual(self._next(self.project_b, env=env_c), 'B-0001')

    def test_missing_company_sequence_is_copied(self):
        """工程的公司還沒有這支序列 → 照最早那支複製一支（前綴相同、從 1 起），來源的計數器不動。"""
        a_next = self._next_actual(self.seq_a)
        self.assertFalse(self._company_seqs(self.company_c))
        self.assertEqual(self._next(self.project_c), 'A-0001')
        copied = self._company_seqs(self.company_c)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied.prefix, 'A-')
        self.assertEqual(self._next(self.project_c), 'A-0002')
        self.assertEqual(len(self._company_seqs(self.company_c)), 1, '第二次取號不可再複製')
        self.assertEqual(self._next_actual(self.seq_a), a_next)

    def test_global_sequence_is_used_without_copy(self):
        """只有全域序列（不綁公司）時照用，不另外複製。"""
        code = CODE + '.global'
        self.env['ir.sequence'].create({'name': '取號測試全域', 'code': code, 'prefix': 'G-',
                                        'padding': PADDING, 'implementation': IMPLEMENTATION,
                                        'company_id': False})
        self.assertEqual(self._next(self.project_c, code=code), 'G-0001')
        self.assertEqual(self.env['ir.sequence'].search_count([('code', '=', code)]), 1)

    def test_no_project_uses_current_company(self):
        self.assertTrue(self._next(False).startswith('A-'))

    def test_no_project_and_current_company_without_sequence(self):
        """沒有工程、目前公司 C 也沒有序列：照最早那支替 C 複製一支，不再是「/」。"""
        env_c = self.env(context=dict(self.env.context, allowed_company_ids=[self.company_c.id]))
        self.assertEqual(self._next(False, env=env_c), 'A-0001')
        self.assertEqual(len(self._company_seqs(self.company_c)), 1)

    def test_unknown_code_logs_error_and_returns_false(self):
        """完全沒有這種序列：回 False，並記 ERROR（不再靜默變「/」）。"""
        with self.assertLogs(HELPER_LOGGER, level='ERROR'):
            self.assertFalse(self._next(self.project_b, code='chienyi.test.no.such.code'))

    def test_user_outside_project_company(self):
        """只開 A 公司的內部帳號替 B 的工程取號（例：前台 sudo 建單、受限帳號）也拿 B 的號。"""
        user = self.env['res.users'].create({
            'name': '取號測試只開 A', 'login': 'seq_test_only_a',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        env_user = self.env(user=user)
        self.assertEqual(self._next(self.project_b.id, env=env_user), 'B-0001')

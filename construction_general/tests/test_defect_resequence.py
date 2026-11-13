# -*- coding: utf-8 -*-
"""缺失改掛工程／改日期時自動重新取當日序號（2026-11-13 使用者決定）。

修前：當日序號只在建立與表單 onchange 時取號；程式、匯入、RPC 直接 write 改工程、發現日期、檢查類型或記錄類型時，
序號照舊帶過去——新分組裡已經有同序號的缺失就撞唯一鍵（unique_sequence_per_day／defect_no_unique），整筆不存。
修後：分組真的變了、而且呼叫端沒有明給序號，就照新建一筆的方式在新分組取下一個序號（construction_quality 的
construction.daily.defect.mixin.write）。
"""
from datetime import date

from odoo.tests.common import TransactionCase, tagged

FOUND_DATE = date(2026, 11, 13)
OTHER_DATE = date(2026, 11, 12)
EXPLICIT_SEQUENCE = 7


@tagged('post_install', '-at_install', 'construction_general')
class TestDefectResequence(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project'].with_context(skip_standard_folders=True)
        cls.project_a, cls.project_b = (
            Project.create({'name': f'{code} 重新取號測試工程', 'code': code, 'project_type': 'general',
                            'company_id': cls.env.company.id})
            for code in ('RSQA', 'RSQB'))
        for project, prefix in ((cls.project_a, 'RSQA'), (cls.project_b, 'RSQB')):
            cls.env['defect.improvement.prefix.config'].create({
                'project_id': project.id, 'supervision_prefix': prefix + 'S', 'contractor_prefix': prefix + 'C'})

    def _defect(self, project, found_date=FOUND_DATE):
        return self.env['general.defect.improvement'].create({
            'project_id': project.id, 'found_date': found_date, 'defect_description': '重新取號測試'})

    def _assert_numbers_unique(self, records):
        numbers = records.mapped('defect_no')
        self.assertEqual(len(numbers), len(set(numbers)), f'缺失編號不可以重複：{numbers}')

    def test_move_project_takes_next_free_sequence(self):
        """A 的第 1 號改掛到已經有 1、2 號的 B → 拿到 3 號，編號換成 B 的前綴。"""
        moved = self._defect(self.project_a)
        others = self._defect(self.project_b) | self._defect(self.project_b)
        self.assertEqual((moved.sequence_number, others.mapped('sequence_number')), (1, [1, 2]), '夾具：建立時的序號')
        moved.write({'project_id': self.project_b.id})
        self.env.flush_all()
        self.assertEqual(moved.sequence_number, 3)
        self.assertTrue(moved.defect_no.startswith('RSQBS-') and moved.defect_no.endswith('_3'), moved.defect_no)
        self._assert_numbers_unique(moved | others)

    def test_batch_move_gets_distinct_sequences(self):
        """一次把 A 的兩筆改掛到已經有 1 號的 B → 各拿一個序號（2、3），不互撞。"""
        batch = self._defect(self.project_a) | self._defect(self.project_a)
        existing = self._defect(self.project_b)
        batch.write({'project_id': self.project_b.id})
        self.env.flush_all()
        self.assertEqual(sorted(batch.mapped('sequence_number')), [2, 3])
        self._assert_numbers_unique(batch | existing)

    def test_change_found_date_resequences(self):
        """同一個工程：把另一天的第 1 號改到已經有 1 號的那一天 → 拿到 2 號。"""
        existing = self._defect(self.project_a)
        moved = self._defect(self.project_a, OTHER_DATE)
        self.assertEqual((existing.sequence_number, moved.sequence_number), (1, 1), '夾具：兩天各自的第 1 號')
        moved.write({'found_date': FOUND_DATE})
        self.env.flush_all()
        self.assertEqual(moved.sequence_number, 2)
        self._assert_numbers_unique(existing | moved)

    def test_same_group_write_keeps_sequence(self):
        """分組沒變（寫回同樣的工程與日期、或只改別的欄位）→ 序號不動，不無謂跳號。"""
        first = self._defect(self.project_a)
        second = self._defect(self.project_a)
        second.write({'project_id': self.project_a.id, 'found_date': FOUND_DATE})
        second.write({'defect_description': '只改說明'})
        self.env.flush_all()
        self.assertEqual((first.sequence_number, second.sequence_number), (1, 2))

    def test_explicit_sequence_is_respected(self):
        """呼叫端明給序號（表單 onchange 算好一起送出就是這樣）→ 照給的值，不另外取號。"""
        moved = self._defect(self.project_a)
        self._defect(self.project_b)
        moved.write({'project_id': self.project_b.id, 'sequence_number': EXPLICIT_SEQUENCE})
        self.env.flush_all()
        self.assertEqual(moved.sequence_number, EXPLICIT_SEQUENCE)

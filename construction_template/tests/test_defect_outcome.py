# -*- coding: utf-8 -*-
"""矯正與預防處理紀錄「缺失改善成果確認」：□符合要求 □逾時未矯正 □未矯正 只勾一格（2026-11-05）。

EAGLE 原系統是單一 result 欄位、四格互斥（main.js：`isQualified=result===qualified` …）。
原本的對照表三格各自判斷：
  ・未矯正＝「狀態不是已驗證／結案」→ 已改善（廠商做完、監造還沒驗證）被勾成未矯正
  ・符合要求＝recheck_result == 'pass'，但沒有任何按鈕會寫這欄 → dev 176 筆結案的三格全空
  ・逾期的同時勾「逾時未矯正」與「未矯正」
使用者 2026-11-05 裁示：EAGLE 式只勾一格；已改善（待監造驗證）三格都不勾；
新北附表12 的「□改善完成 □未完成改善」用同一套判斷。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import defect_improvement

MARK = defect_improvement.MARK
BOXES = ('isQualified', 'isTimeout', 'isUncorrected')


@tagged('post_install', '-at_install', 'construction_template')
class TestDefectOutcome(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'general.defect.improvement' not in cls.env:
            cls.skipTest(cls, 'construction_general 沒有安裝')
        cls.project = cls.env['project.project'].create({
            'name': '缺失成果確認測試', 'code': 'TPL-DIOUT',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'TOQA', 'contractor_prefix': 'TOQR',
        })
        cls.today = fields.Date.today()

    def _defect(self, overdue=False, **vals):
        base = {
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '模板縫隙過大', 'source_type': 'daily_check',
            'found_date': self.today - timedelta(days=30),
            'notification_date': self.today - timedelta(days=20),
            'deadline': self.today + timedelta(days=(-5 if overdue else 10)),
            'improvement_action': '重新封模',
        }
        base.update(vals)
        return self.env['general.defect.improvement'].create(base)

    def _marks(self, defect):
        ctx = defect_improvement.build_context(self.project)
        rec = [r for r in ctx['errorRecords'] if r['no'] == (defect.defect_no or defect.name)]
        self.assertEqual(len(rec), 1)
        rec = rec[0]
        checked = tuple(key for key in BOXES if rec[key] == MARK)
        return checked, (rec['doneBox'], rec['undoneBox'])

    def test_improved_waiting_for_verification_checks_nothing(self):
        defect = self._defect(state='improved')
        self.assertEqual(self._marks(defect), ((), ('□', '□')),
                         '已改善（監造還沒驗證）不能勾未矯正，也還不能勾符合要求')

    def test_closed_and_verified_are_qualified(self):
        for state in ('verified', 'closed'):
            defect = self._defect(state=state, defect_description='結案 %s' % state)
            self.assertEqual(self._marks(defect), (('isQualified',), ('■', '□')),
                             '%s 的缺失應勾「符合要求」' % state)

    def test_overdue_checks_only_timeout(self):
        defect = self._defect(state='notified', overdue=True)
        self.assertTrue(defect.is_overdue, '測資前提：已逾期')
        self.assertEqual(self._marks(defect), (('isTimeout',), ('□', '■')),
                         '逾期未改善只勾「逾時未矯正」，不能同時勾「未矯正」')

    def test_not_yet_improved_is_uncorrected(self):
        for state in ('notified', 'improving'):
            defect = self._defect(state=state, defect_description='未改善 %s' % state)
            self.assertEqual(self._marks(defect), (('isUncorrected',), ('□', '■')), state)

    def test_verify_fail_flow_is_uncorrected(self):
        defect = self._defect(state='improved')
        defect.action_verify_fail()
        self.assertEqual((defect.state, defect.verify_result), ('improving', 'fail'))
        self.assertEqual(self._marks(defect), (('isUncorrected',), ('□', '■')))

    def test_verify_pass_flow_is_qualified(self):
        defect = self._defect(state='improved')
        defect.action_verify_pass()
        self.assertEqual(self._marks(defect), (('isQualified',), ('■', '□')))

    def test_manual_recheck_result_still_wins(self):
        """一般式表單可手填複查結果；附表12 測試（10-24）定的語意保留"""
        cases = [('pass', (('isQualified',), ('■', '□'))),
                 ('fail', (('isUncorrected',), ('□', '■'))),
                 ('pending', ((), ('□', '□')))]
        for result, expected in cases:
            defect = self._defect(state='improved', recheck_result=result,
                                  defect_description='手填複查 %s' % result)
            self.assertEqual(self._marks(defect), expected, result)

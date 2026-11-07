# -*- coding: utf-8 -*-
"""矯正與預防處理紀錄「缺失改善成果確認」：□符合要求 □逾時未矯正 □未矯正 □其他 只勾一格（2026-11-05）。

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
BOXES = ('isQualified', 'isTimeout', 'isUncorrected', 'isOther')


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

    def test_reopened_defect_drops_stale_recheck(self):
        """手填過「複查結果：通過」，結案後又重新開啟：不能再印符合要求（2026-11-06）。

        預約式的 action_reopen 本來就清複查日期／結果／說明，一般式只清結案人與驗證結果，
        殘留的「通過」會讓重開（改善中）的缺失印成「符合要求」＋「改善完成」。
        """
        defect = self._defect(state='improved', recheck_result='pass')
        defect.action_verify_pass()
        defect.action_close()
        defect.action_reopen()
        self.assertEqual(defect.state, 'improving')
        self.assertEqual(self._marks(defect), (('isUncorrected',), ('□', '■')))

    def test_verify_fail_drops_stale_recheck_pass(self):
        """先手填「複查通過」，監造按「驗證不通過」退回改善：以驗證結果為準"""
        defect = self._defect(state='improved', recheck_result='pass')
        defect.action_verify_fail()
        self.assertEqual(self._marks(defect), (('isUncorrected',), ('□', '■')))

    def test_verify_fail_drops_stale_pending(self):
        """殘留「待複查」又被驗證退回：改善中的缺失要印未矯正，不是三格都不勾"""
        defect = self._defect(state='improved', recheck_result='pending')
        defect.action_verify_fail()
        self.assertEqual(self._marks(defect), (('isUncorrected',), ('□', '■')))

    def test_stored_outcome_wins_over_auto(self):
        """缺失上存了「成果確認」就照它勾（2026-11-06：回填 EAGLE 資料要照舊系統印）。

        EAGLE 由監造選一個結果存起來、印的時候照勾；例：存「未矯正」但期限已過，
        EAGLE 印 ■未矯正，自動判斷會印 ■逾時未矯正。
        """
        cases = [
            # (outcome_result, state, 逾期?, 預期勾的格子, 附表12 兩格)
            ('uncorrected', 'draft', True, ('isUncorrected',), ('□', '■')),     # 自動會是逾時未矯正
            ('timeout', 'notified', False, ('isTimeout',), ('□', '■')),         # 自動會是未矯正
            ('other', 'notified', True, ('isOther',), ('□', '□')),              # 自動永遠不勾「其他」
            # 已矯正：上面四格沒有它的格子（照 EAGLE 都不勾）；新北附表12 勾「改善完成」（使用者 2026-11-07 裁示）
            ('corrected', 'closed', False, (), ('■', '□')),
            ('corrected', 'improved', True, (), ('■', '□')),                    # 逾期也一樣：存的是監造判定
        ]
        for outcome, state, overdue, boxes, ntpc in cases:
            defect = self._defect(state=state, overdue=overdue, outcome_result=outcome,
                                  defect_description='成果確認 %s' % outcome)
            self.assertEqual(self._marks(defect), (boxes, ntpc), outcome)

    def test_state_change_clears_stored_outcome(self):
        """存的成果確認只代表「當時」的結果：之後狀態一變（重開、退回、在 Odoo 走完流程結案）就清掉，
        改回自動判斷（2026-11-06 red-team F1／F2：重開的缺失原本照舊印「符合要求」；
        回填成「未矯正」的缺失在 Odoo 結案後原本還印「未矯正」）。"""
        closed = self._defect(state='closed', outcome_result='qualified', defect_description='重開')
        closed.action_reopen()
        self.assertEqual(closed.state, 'improving')
        self.assertFalse(closed.outcome_result)
        self.assertEqual(self._marks(closed), (('isUncorrected',), ('□', '■')))
        old = self._defect(state='draft', overdue=True, outcome_result='uncorrected', defect_description='回填後結案')
        old.write({'state': 'closed'})
        self.assertFalse(old.outcome_result)
        self.assertEqual(self._marks(old), (('isQualified',), ('■', '□')))
        same = self._defect(state='draft', overdue=True, outcome_result='uncorrected', defect_description='狀態沒變')
        same.write({'state': 'draft', 'improvement_action': '補說明'})
        self.assertEqual(same.outcome_result, 'uncorrected', '狀態沒有真的改變就不清')

    def test_outcome_must_match_state(self):
        """「符合要求」只能配已驗證／結案；已驗證／結案不能配「未矯正／逾時未矯正」（red-team F3）"""
        from odoo.exceptions import ValidationError
        draft = self._defect(state='draft', defect_description='不一致')
        with self.assertRaises(ValidationError):
            draft.outcome_result = 'qualified'
            draft.flush_recordset()
        closed = self._defect(state='closed', defect_description='不一致2')
        with self.assertRaises(ValidationError):
            closed.outcome_result = 'uncorrected'
            closed.flush_recordset()

    def test_outcome_not_copied(self):
        defect = self._defect(state='draft', overdue=True, outcome_result='uncorrected', defect_description='複製')
        self.assertFalse(defect.copy({'defect_description': '複製出來的'}).outcome_result)

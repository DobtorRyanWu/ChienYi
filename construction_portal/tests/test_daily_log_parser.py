# -*- coding: utf-8 -*-
"""施工日誌解析器：安全衛生勾選項的解析測試

重點在「確認新進勞工是否提報勞工保險」這一題。紙本表單有三個框：
    □有  □無  ■無新進勞工
第三個框「無新進勞工」的語意是「當日無新進勞工，本項不適用」，
與「無」（有新進勞工但未提報勞保）意思相反，必須解析成獨立的值。
"""

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.utils.daily_log_xlsm_parser import (
    _parse_safety_checks as parse_safety_xlsm,
)
from odoo.addons.construction_portal.utils.daily_log_b_xlsx_parser import (
    _tick_with_no_new,
)


def _safety_text(labor_line):
    """組出 A 標 xlsm R33 那一整格的文字，只換勞保那一行"""
    return (
        '五、工地職業安全衛生事項\n'
        ' (一)施工前檢查事項：\n'
        '  1.實施勤前教育(含工地預防災變及危害告知):■有  □無\n'
        f'  {labor_line}\n'
        '  3.檢查勞工個人防護具：■有  □無\n'
        ' (二)其他事項：無\n'
    )


LABOR_PREFIX = '2.確認新進勞工是否提報勞工保險(或其他商業保險)資料及安全衛生教育訓練紀錄：'


@tagged('post_install', '-at_install')
class TestDailyLogSafetyChecks(TransactionCase):

    # === A 標 xlsm ===

    def test_xlsm_no_new_worker(self):
        """勾「無新進勞工」→ no_new_worker（不是 no）"""
        text = _safety_text(LABOR_PREFIX + '□有  □無  ■無新進勞工')
        _pre, ins, _ppe, _other = parse_safety_xlsm(text)
        self.assertEqual(ins, 'no_new_worker')

    def test_xlsm_no_new_worker_with_space(self):
        """■ 與字之間有空白也要認得（Excel 儲存格常見變體）"""
        text = _safety_text(LABOR_PREFIX + '□有  □無  ■ 無新進勞工')
        _pre, ins, _ppe, _other = parse_safety_xlsm(text)
        self.assertEqual(ins, 'no_new_worker')

    def test_xlsm_no(self):
        """勾「無」→ no（原有行為不可改壞）"""
        text = _safety_text(LABOR_PREFIX + '□有  ■無  □無新進勞工')
        _pre, ins, _ppe, _other = parse_safety_xlsm(text)
        self.assertEqual(ins, 'no')

    def test_xlsm_yes(self):
        """勾「有」→ yes"""
        text = _safety_text(LABOR_PREFIX + '■有  □無  □無新進勞工')
        _pre, ins, _ppe, _other = parse_safety_xlsm(text)
        self.assertEqual(ins, 'yes')

    def test_xlsm_unticked(self):
        """三框全空 → False（B 標實況，維持不填）"""
        text = _safety_text(LABOR_PREFIX + '□有  □無  □無新進勞工')
        _pre, ins, _ppe, _other = parse_safety_xlsm(text)
        self.assertFalse(ins)

    def test_xlsm_siblings_not_broken(self):
        """共用的 _tick() 沒被改壞：同一段文字的勤前教育／防護具仍正確"""
        text = _safety_text(LABOR_PREFIX + '□有  □無  ■無新進勞工')
        pre, _ins, ppe, _other = parse_safety_xlsm(text)
        self.assertEqual(pre, 'yes')
        self.assertEqual(ppe, 'yes')

    # === B 標 xlsx ===

    def test_b_xlsx_no_new_worker(self):
        self.assertEqual(
            _tick_with_no_new(LABOR_PREFIX + '□有  □無  ■無新進勞工'),
            'no_new_worker',
        )

    def test_b_xlsx_no(self):
        self.assertEqual(
            _tick_with_no_new(LABOR_PREFIX + '□有  ■無  □無新進勞工'),
            'no',
        )

    def test_b_xlsx_yes(self):
        self.assertEqual(
            _tick_with_no_new(LABOR_PREFIX + '■有  □無  □無新進勞工'),
            'yes',
        )

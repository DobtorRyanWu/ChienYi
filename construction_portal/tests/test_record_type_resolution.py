# -*- coding: utf-8 -*-
"""缺失匯入的 record_type（監造／營造）四層優先序測試。

權威依據：使用者匯入管道 `B標匯入_合併.xlsx`「缺失改善」工作表 R1 註記 ——
「record_type 由『原始編號(source_no)』前綴自動推導：QA→監造、QR→營造」。

四層優先序（權威 → 推論 → 人工）：
  1. 登錄編號前綴 QA/QR      B標 `QA-11309191`、P11001 `QA-001`
  2. 工作表名 QA/QR          P11001 `QA.QR-工程缺失改善追蹤一覽表.xlsx`
  3. 解析器自檔名推導        docx `derive_record_type()`
  4. 缺失類別代理推論        A標（88 筆登錄編號全是 Q01-，此為唯一訊號）
  5. 匯入頁下拉 fallback     全部判不出時
"""

from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal_utils import (
    resolve_record_type)


@tagged('post_install', '-at_install', 'construction_portal')
class TestRecordTypeResolution(TransactionCase):

    # ── 第 1 層：登錄編號前綴（權威，勝過其它所有訊號） ──────────

    def test_register_no_qa_wins(self):
        self.assertEqual(
            resolve_record_type({'register_no': 'QA-001'}), 'supervision')

    def test_register_no_qr_wins(self):
        self.assertEqual(
            resolve_record_type({'register_no': 'QR-006'}), 'contractor')

    def test_register_no_b_biao_format(self):
        """B 標格式 QA-11309191（QA/QR + 民國日期 + 序號）。"""
        self.assertEqual(
            resolve_record_type({'register_no': 'QA-11309191'}), 'supervision')

    def test_register_no_case_insensitive(self):
        self.assertEqual(
            resolve_record_type({'register_no': 'qr-002'}), 'contractor')

    def test_register_no_overrides_lower_layers(self):
        """登錄編號說 QR，即使類別是施工品質、下拉選監造，仍以登錄編號為準。"""
        self.assertEqual(
            resolve_record_type(
                {'register_no': 'QR-001', 'defect_category': 'workmanship'},
                sheet_name='QA', fallback='supervision'),
            'contractor')

    # ── 第 2 層：工作表名（權威） ────────────────────────────────

    def test_sheet_name_qa(self):
        self.assertEqual(
            resolve_record_type({}, sheet_name='QA'), 'supervision')

    def test_sheet_name_qr_with_whitespace(self):
        self.assertEqual(
            resolve_record_type({}, sheet_name='  qr  '), 'contractor')

    def test_sheet_name_overrides_category(self):
        self.assertEqual(
            resolve_record_type({'defect_category': 'workmanship'},
                                sheet_name='QR'),
            'contractor')

    def test_unrelated_sheet_name_falls_through(self):
        """A 標的工作表名是「不合格品改善追蹤一覽表」，不該被誤判。"""
        self.assertEqual(
            resolve_record_type({'defect_category': 'safety'},
                                sheet_name='不合格品改善追蹤一覽表'),
            'contractor')

    # ── 第 3 層：解析器自檔名推導 ────────────────────────────────

    def test_parser_supplied_record_type(self):
        self.assertEqual(
            resolve_record_type({'record_type': 'contractor'}), 'contractor')

    def test_parser_none_falls_through(self):
        """derive_record_type 推不出時回 None，應往下一層落。"""
        self.assertEqual(
            resolve_record_type({'record_type': None,
                                 'defect_category': 'safety'}),
            'contractor')

    def test_parser_garbage_value_ignored(self):
        self.assertEqual(
            resolve_record_type({'record_type': 'nonsense'},
                                fallback='contractor'),
            'contractor')

    # ── 第 4 層：缺失類別代理推論（A 標唯一可用訊號） ────────────

    def test_category_construction_side_is_supervision(self):
        for cat in ('material', 'workmanship', 'dimension', 'document'):
            self.assertEqual(
                resolve_record_type({'defect_category': cat}), 'supervision',
                f'{cat} 應歸監造')

    def test_category_safety_env_side_is_contractor(self):
        for cat in ('safety', 'environment'):
            self.assertEqual(
                resolve_record_type({'defect_category': cat}), 'contractor',
                f'{cat} 應歸營造')

    def test_a_biao_rule(self):
        """A 標實測：改正單位 施工→監造(49 筆)、職安/環境→營造(39 筆)。"""
        # parser 把 改正單位 轉成 defect_category
        self.assertEqual(
            resolve_record_type({'register_no': 'Q01-1130109',
                                 'defect_category': 'workmanship'}),
            'supervision')
        self.assertEqual(
            resolve_record_type({'register_no': 'Q01-1121007',
                                 'defect_category': 'safety'}),
            'contractor')
        self.assertEqual(
            resolve_record_type({'register_no': 'Q01-1130116',
                                 'defect_category': 'environment'}),
            'contractor')

    def test_category_other_falls_through(self):
        """'other' 不在對照表中，應落到 fallback。"""
        self.assertEqual(
            resolve_record_type({'defect_category': 'other'},
                                fallback='contractor'),
            'contractor')

    # ── 第 5 層：下拉 fallback ───────────────────────────────────

    def test_fallback_used_when_nothing_resolvable(self):
        self.assertEqual(
            resolve_record_type({}, fallback='contractor'), 'contractor')

    def test_default_fallback_is_supervision(self):
        self.assertEqual(resolve_record_type({}), 'supervision')

    def test_invalid_fallback_defaults_to_supervision(self):
        self.assertEqual(
            resolve_record_type({}, fallback='garbage'), 'supervision')

    def test_result_always_valid_selection_value(self):
        """回傳值一定是模型 record_type 的合法 Selection 值。"""
        valid = {v for v, _ in self.env['general.defect.improvement']
                 ._fields['record_type'].selection}
        for row in ({}, {'register_no': 'QA-1'}, {'defect_category': 'safety'},
                    {'record_type': 'contractor'}, {'register_no': ''}):
            self.assertIn(resolve_record_type(row), valid)

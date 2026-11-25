# -*- coding: utf-8 -*-
"""公文、行事曆事項的所屬公司寫後檢查（W5 A3，2026-11-25）。

和外部標案同一種洞：全域規則是「所屬公司在允許公司內」，有寫入權的後台帳號把 company_id 改成自己允許公司以外的，
核心只在寫入前用舊值檢查規則，改完照樣落到別家公司。construction_supervision_base 的寫後檢查表
（COMPANY_OWNED_RULE_FIELDS）要有這兩個模型。沒裝 construction_office 的庫整組略過。
"""
from odoo import fields
from odoo.addons.construction_supervision_base.models import company_rule_write_guard
from odoo.exceptions import AccessError
from odoo.models import LOG_ACCESS_COLUMNS
from odoo.osv import expression
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .test_dashboard_indicators import DashIndicatorCase
from .test_scope_rules import SUPERVISOR_ADMIN

DOC_MODEL = 'construction.official.doc'
EVENT_MODEL = 'construction.calendar.event'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestOfficeWriteGuard(DashIndicatorCase):

    def setUp(self):
        super().setUp()
        if DOC_MODEL not in self.env or EVENT_MODEL not in self.env:
            self.skipTest('沒裝 construction_office')

    def _records(self):
        doc = self.env[DOC_MODEL].create({'subject': 'OWG 公文', 'company_id': self.co_s.id})
        event = self.env[EVENT_MODEL].create({
            'name': 'OWG 事項', 'company_id': self.co_s.id, 'start': fields.Datetime.now(),
            'responsible_user_id': self.sup.id})
        return {DOC_MODEL: doc, EVENT_MODEL: event}

    def test_company_cannot_be_moved_outside_allowed_companies(self):
        """有寫入權的帳號不能把公文、行事曆事項的所屬公司改成允許公司以外的（修前寫得進去）；允許公司內換公司照常。"""
        for model, record in self._records().items():
            with self.subTest(model=model):
                with self.assertRaises(AccessError), self.cr.savepoint():
                    record.with_user(self.sup).write({'company_id': self.co_a.id})
                self.env.invalidate_all()
                self.assertEqual(record.company_id, self.co_s, '被拒之後資料沒變')
                both = self._user('owg_both_' + model.split('.')[-1], ['base.group_user', SUPERVISOR_ADMIN],
                                  self.co_s, self.co_s | self.co_b)
                record.with_user(both).write({'company_id': self.co_b.id})
                self.assertEqual(record.company_id, self.co_b)

    def test_write_guard_fields_match_rules(self):
        """寫後檢查要盯的欄位＝這兩個模型的全域規則用得到、寫得進去的欄位（從資料庫的規則推，不抄實作）。"""
        context = dict(self.env['ir.rule']._eval_context(), company_ids=[])
        for model in (DOC_MODEL, EVENT_MODEL):
            with self.subTest(model=model):
                rules = self.env['ir.rule'].sudo().search([('model_id.model', '=', model), ('global', '=', True)])
                self.assertTrue(rules, '前提：%s 有全域規則' % model)
                derived = {leaf[0].split('.', 1)[0] for rule in rules for leaf in safe_eval(rule.domain_force, context)
                           if expression.is_leaf(leaf)} - set(LOG_ACCESS_COLUMNS)
                watched = company_rule_write_guard.COMPANY_OWNED_RULE_FIELDS.get(model, frozenset())
                self.assertEqual(set(watched), derived)

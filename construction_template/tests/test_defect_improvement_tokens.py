# -*- coding: utf-8 -*-
"""缺失改善（defect_improvement）對照表：新北契約附表12「不合格品改正紀錄表」要的欄位。

附表12 比系統原本的「矯正與預防處理紀錄」多要：監造廠商、檢查日期、缺失位置、
缺失複查日期、複查結果「□改善完成 □未完成改善」。資料欄位都在缺失模型上
（found_date、defect_location、recheck_date、recheck_result），對照表沒給 token。
只加 key、不改舊 key——任泰在用的 EAGLE 樣板（+++INS+++）照舊。
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import defect_improvement


@tagged('post_install', '-at_install', 'construction_template')
class TestDefectImprovementTokens(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'general.defect.improvement' not in cls.env:
            cls.skipTest(cls, 'construction_general 沒有安裝')
        cls.project = cls.env['project.project'].create({
            'name': '附表12測試工程', 'code': 'TPL-NTPC12',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id,
            'management_company_name': '測試監造顧問',
        })
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'T12QA',
            'contractor_prefix': 'T12QR',
        })

    def _defect(self, **vals):
        base = {
            'project_id': self.project.id,
            'record_type': 'supervision',
            'check_type': 'construction',
            'defect_category': 'workmanship',
            'defect_description': '模板縫隙過大',
            'source_type': 'daily_check',
            'state': 'notified',
        }
        base.update(vals)
        return self.env['general.defect.improvement'].create(base)

    def _record_of(self, defect):
        ctx = defect_improvement.build_context(self.project)
        recs = [r for r in ctx['errorRecords'] if r['no'] == (defect.defect_no or defect.name)]
        self.assertEqual(len(recs), 1)
        return ctx, recs[0]

    def test_new_tokens(self):
        defect = self._defect(
            # 發現日要早於預設的通知日（今天）：模型有「通知改善日期不得早於發現日期」約束
            found_date=fields.Date.to_date('2026-10-01'),
            defect_location='北側護岸 0K+120',
            recheck_date=fields.Date.to_date('2026-10-08'),
            recheck_result='pass',
        )
        ctx, rec = self._record_of(defect)
        self.assertEqual(ctx['supervisorCompany'], '測試監造顧問')
        self.assertEqual(rec['foundAt'], '115.10.01')   # 與同表 deadLine 一樣用 roc_date
        self.assertEqual(rec['location'], '北側護岸 0K+120')
        self.assertEqual(rec['recheckAt'], '115.10.08')
        self.assertEqual((rec['doneBox'], rec['undoneBox']), ('■', '□'))

    def test_recheck_boxes(self):
        failed = self._defect(recheck_result='fail', defect_description='鋼筋保護層不足')
        pending = self._defect(recheck_result='pending', defect_description='排水不良')
        _ctx, rec = self._record_of(failed)
        self.assertEqual((rec['doneBox'], rec['undoneBox']), ('□', '■'))
        # 待複查：兩格都不能先勾
        _ctx, rec = self._record_of(pending)
        self.assertEqual((rec['doneBox'], rec['undoneBox']), ('□', '□'))
        self.assertEqual(rec['recheckAt'], '')

    def test_old_tokens_unchanged(self):
        defect = self._defect(recheck_result='pass')
        _ctx, rec = self._record_of(defect)
        for key in ('no', 'No', 'images', 'isConstruction', 'notifiedAt', 'deadLine',
                    'description', 'reason', 'improvements', 'finishedAt', 'isQualified',
                    'isTimeout', 'isUncorrected', 'result'):
            self.assertIn(key, rec)

# -*- coding: utf-8 -*-
"""進度報告（以估驗單為期間錨點）的完成百分率：分母要含沒有單價的工項。

完成百分率 ＝ 金額 ÷ 契約金額。契約金額原本一律是 Σ 核定數量 × 單價，
自主品管費、稅什費這類沒有單價的工項（整包項的金額在 xml_amount、
比例項是「比例 × 基數」）就不在分母裡 —— 但它們的本期／累計金額在分子裡，
百分率因此偏高。construction_payment 18.0.1.8.1 把累計金額改對之後，
開發庫 111-20-AEF-V 第 13 期累計百分率變成 99.52%（應為 89.66%）。

改法：有單價的工項照舊（估驗明細上的核定數量 × 單價），
沒有單價的工項用工項的契約金額 planned_amount。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import progress_report


@tagged('post_install', '-at_install', 'construction_template')
class TestProgressReportAmounts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '進度報告百分率測試工程',
            'code': 'TPL-PRPCT',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']
        cls.root = Task.create({
            'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹',
            'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0, 'sequence': 1,
        })
        cls.normal = Task.create({
            'name': '一般工項', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '一', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 100.0,
            'sequence': 10,
        })
        cls.lump = Task.create({
            'name': '自主品管費', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '二', 'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
            'xml_amount': 2000.0, 'is_lump_sum': True, 'sequence': 20,
        })
        # 比例項：基數＝同層前置工項（一般工項 10,000 ＋ 自主品管費 2,000）× 5% ＝ 600
        cls.rate = Task.create({
            'name': '稅什費', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '三', 'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
            'tax_misc_rate': 5.0, 'sequence': 30,
        })
        cls.d0 = fields.Date.today() - timedelta(days=60)

    def _estimate(self, days, rows):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': self.d0 + timedelta(days=days),
        })
        Line = self.env['payment.estimate.line']
        for seq, (task, qty, amount) in enumerate(
                [(self.root, 1.0, None)] + rows, start=1):
            vals = Line._prepare_line_vals(task, seq)
            vals.update({'estimate_id': est.id, 'estimate_qty': qty})
            if amount is not None:
                vals['estimate_amount'] = amount
            Line.create(vals)
        return est

    def _lines(self, est):
        return est.line_ids.sorted(lambda ln: (ln.sequence, ln.id))

    def test_contract_includes_items_without_unit_price(self):
        self.assertEqual(self.lump.planned_amount, 2000.0, '測資前提：整包項契約金額')
        self.assertEqual(self.rate.planned_amount, 600.0, '測資前提：比例項契約金額')
        est = self._estimate(0, [
            (self.normal, 10.0, None),          # 1,000
            (self.lump, 0.1, 200.0),            # 整包項手動金額
            (self.rate, 0.1, 60.0),             # 比例項手動金額
        ])
        contract, current, cumulative = progress_report._amounts(self._lines(est))
        self.assertAlmostEqual(
            contract, 10000.0 + 2000.0 + 600.0, places=2,
            msg='沒有單價的工項（整包項／比例項）沒算進契約金額（完成百分率的分母）')
        self.assertAlmostEqual(current, 1260.0, places=2)
        self.assertAlmostEqual(cumulative, 1260.0, places=2)

    def test_percent_uses_full_contract(self):
        e1 = self._estimate(0, [
            (self.normal, 10.0, None), (self.lump, 0.1, 200.0), (self.rate, 0.1, 60.0)])
        e2 = self._estimate(30, [
            (self.normal, 20.0, None), (self.lump, 0.2, 400.0), (self.rate, 0.2, 120.0)])
        e1.action_submit_estimate()
        e1.action_approve()
        self.env.invalidate_all()
        ctx = progress_report.build_context(e2)
        self.assertAlmostEqual(ctx['donePercent'], 2520.0 / 12600.0, places=6)
        self.assertAlmostEqual(
            ctx['totalPercent'], (1260.0 + 2520.0) / 12600.0, places=6,
            msg='累計完成百分率的分母少了沒有單價的工項 → 百分率偏高')

    # === 契約變更刪掉的工項（變更後核定數量 0） ===
    def _cancelled_setup(self):
        """一般工項＋一個被契約變更刪掉的工項（原契約 50、現在 0）"""
        cancelled = self.env['project.task'].create({
            'name': '被刪掉的工項', 'project_id': self.project.id, 'parent_id': self.root.id,
            'item_no': '四', 'unit': 'M', 'planned_qty': 0.0, 'unit_price': 100.0,
            'sequence': 40,
        })
        est = self._estimate(0, [(self.normal, 10.0, None)])
        Line = self.env['payment.estimate.line']
        vals = Line._prepare_line_vals(cancelled, 9)
        vals.update({'estimate_id': est.id, 'contract_qty': 50.0, 'approved_qty': 0.0})
        line = Line.create(vals)
        return est, line

    def test_cancelled_item_not_in_contract(self):
        est, _line = self._cancelled_setup()
        contract, _cur, _cum = progress_report._amounts(self._lines(est))
        self.assertAlmostEqual(
            contract, 10000.0, places=2,
            msg='契約變更刪掉的工項（變更後 0）被當成「沒填」，用原契約數量算進契約金額')

    def test_cancelled_item_prints_zero(self):
        from odoo.addons.construction_template.mappings import invoice_detail
        est, _line = self._cancelled_setup()
        row = [it for it in invoice_detail.build_context(est)['payItems']
               if it['fullItemNo'] == '四'][0]
        self.assertEqual(row['quantity'], '50', '（一）契約數量照印原契約數量')
        self.assertEqual(row['approvedQuantity'], '0',
                         '（二）變更後核定數量：刪掉的工項應印 0，不是原契約數量')
        row = [it for it in progress_report.build_context(est)['payItems']
               if it['fullItemNo'] == '四'][0]
        self.assertEqual(row['quantity'], '0', '進度報告契約數量：刪掉的工項應印 0')

    def test_unfilled_approved_qty_falls_back(self):
        """變更後核定數量沒填的舊資料（工項現在不是 0）照舊退回原契約數量"""
        from odoo.addons.construction_template.mappings import invoice_detail
        est = self._estimate(0, [(self.normal, 10.0, None)])
        line = est.line_ids.filtered(lambda ln: ln.task_id == self.normal)
        line.write({'approved_qty': 0.0, 'contract_qty': 100.0})
        contract, _cur, _cum = progress_report._amounts(self._lines(est))
        self.assertAlmostEqual(contract, 100.0 * 100.0, places=2)
        row = [it for it in invoice_detail.build_context(est)['payItems']
               if it['fullItemNo'] == '一'][0]
        self.assertEqual(row['approvedQuantity'], '100')

    def test_priced_items_unchanged(self):
        """全部都有單價的工程：契約金額照舊是 核定數量 × 單價（估驗明細上的快照）"""
        est = self._estimate(0, [(self.normal, 10.0, None)])
        line = est.line_ids.filtered(lambda ln: ln.task_id == self.normal)
        line.write({'approved_qty': 80.0})       # 快照與工項現值不同時，以快照為準
        contract, _cur, _cum = progress_report._amounts(self._lines(est))
        self.assertAlmostEqual(contract, 80.0 * 100.0, places=2)

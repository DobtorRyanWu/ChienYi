# -*- coding: utf-8 -*-
"""契約變更套用後的「同步估驗計價工項」：既有工項的單價也要更新成變更後的單價。

以前同步只補新增工項、更新「變更後核定數量」，**不更新單價** —— 契約變更改了
某項單價時，變更前就建好的草稿估驗單（例：進度表啟用時一次建好的各期）同步之後
仍用舊單價，本次估驗金額也照舊單價算（2026-10-19 pg18 實測：A 改成 12 元，
同步後估驗單仍是 10 元、本次金額 50 不是 60）。使用者裁示：同步時單價與數量都要更新
（改動前的期別照原始金額、改動後才用改動之金額 —— 基準日之前的估驗單不動）。

同步的範圍不變：只處理草稿／待核定、估驗日期 ≥ 基準日的估驗單；已核定／已歸檔不動。
手動金額照手動值（單價更新不會蓋掉使用者填的金額）。原始契約數量留原值。
"""

import datetime

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEstimateSyncWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '同步估驗工項測試工程', 'code': 'EST-SYNC',
            'state': 'construction', 'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']
        cls.root = Task.create({
            'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹',
            'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0, 'sequence': 1})
        cls.a = Task.create({
            'name': '工項A', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '一', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 10.0, 'sequence': 10})
        cls.d = Task.create({
            'name': '工項D（手動金額）', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '二', 'unit': 'M3', 'planned_qty': 50.0, 'unit_price': 100.0, 'sequence': 20})
        # 大的不變工項：讓本次變更金額比例小，不碰累計變更上限
        cls.b = Task.create({
            'name': '工項B', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '三', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 1000.0, 'sequence': 30})
        cls.change_date = datetime.date(2026, 1, 1)

    def _estimate(self, date, manual_d=None):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id, 'estimate_date': date})
        Line = self.env['payment.estimate.line']
        for seq, t in enumerate((self.root, self.a, self.d, self.b), start=1):
            vals = Line._prepare_line_vals(t, seq * 10)
            vals['estimate_id'] = est.id
            if t == self.a:
                vals['estimate_qty'] = 5.0
            if t == self.d and manual_d is not None:
                vals['estimate_qty'] = 1.0
                vals['estimate_amount'] = manual_d      # create() 會標成手動金額
            Line.create(vals)
        return est

    def _line(self, est, task):
        return est.line_ids.filtered(lambda l: l.task_id == task)

    def _apply_change(self):
        co = self.env['contract.change.order'].create({
            'name': 'EST-SYNC-CHG', 'project_id': self.project.id,
            'change_date': self.change_date})
        CL = self.env['contract.change.order.line']
        CL.create({'change_order_id': co.id, 'change_type': 'modify', 'task_id': self.a.id,
                   'item_name': self.a.name, 'unit': 'M3', 'original_qty': 100.0,
                   'original_unit_price': 10.0, 'new_qty': 120.0, 'new_unit_price': 12.0})
        CL.create({'change_order_id': co.id, 'change_type': 'modify', 'task_id': self.d.id,
                   'item_name': self.d.name, 'unit': 'M3', 'original_qty': 50.0,
                   'original_unit_price': 100.0, 'new_qty': 60.0, 'new_unit_price': 110.0})
        CL.create({'change_order_id': co.id, 'change_type': 'add', 'item_name': '工項C（變更新增）',
                   'item_no': '四', 'unit': 'M', 'new_qty': 50.0, 'new_unit_price': 20.0,
                   'parent_task_id': self.root.id})
        co.write({'state': 'approved'})        # 省略送審／核定流程
        co.action_apply()
        return co

    def _sync(self, co, from_date):
        act = co.action_open_sync_wizard()
        wiz = self.env['estimate.sync.wizard'].with_context(**act['context']).create({})
        wiz.sync_from_date = from_date
        wiz.action_sync()
        self.env.invalidate_all()
        return wiz

    def test_sync_updates_unit_price_and_qty(self):
        est = self._estimate(datetime.date(2026, 1, 31), manual_d=777.0)
        co = self._apply_change()
        self.assertEqual(self.a.unit_price, 12.0, '測資前提：契約變更已套用到工項')
        self._sync(co, self.change_date)

        la = self._line(est, self.a)
        self.assertEqual(la.approved_qty, 120.0)
        self.assertEqual(la.unit_price, 12.0, '同步後估驗單的單價沒有更新成變更後的單價')
        self.assertEqual(la.estimate_amount, 60.0, '本次估驗金額仍照舊單價算（應為 12 × 5）')
        self.assertEqual(la.contract_qty, 100.0, '原始契約數量要留原值')

        ld = self._line(est, self.d)
        self.assertEqual(ld.approved_qty, 60.0)
        self.assertEqual(ld.unit_price, 110.0)
        self.assertTrue(ld.is_amount_manual)
        self.assertEqual(ld.estimate_amount, 777.0, '手動金額被單價更新蓋掉')

        c = self.env['project.task'].search([
            ('project_id', '=', self.project.id), ('name', '=', '工項C（變更新增）')])
        lc = est.line_ids.filtered(lambda l: l.task_id == c)
        self.assertEqual(len(lc), 1, '變更新增的工項沒有補上')
        self.assertEqual(lc.unit_price, 20.0)
        self.assertEqual(lc.approved_qty, 50.0)

    def test_default_base_date_is_change_date(self):
        """同步視窗的預設基準日＝變更單的「變更日期」（＝工項版本的生效日期），不是套用日。

        施工日誌的「當時契約數量」也是以這個日期為界；補建歷史資料時套用日遠晚於
        變更日期，用套用日當預設會讓變更後的舊期別全部同步不到（使用者 2026-10-19 裁示）。
        """
        est = self._estimate(datetime.date(2026, 1, 31))
        co = self._apply_change()
        self.assertGreater(co.applied_date.date(), est.estimate_date, '測資前提：套用日晚於估驗日期')
        act = co.action_open_sync_wizard()
        wiz = self.env['estimate.sync.wizard'].with_context(**act['context']).create({})
        self.assertEqual(wiz.sync_from_date, self.change_date,
                         '預設基準日不是變更日期（舊版是套用日）')
        self.assertEqual(wiz.affected_estimate_count, 1,
                         '變更日期之後的草稿估驗單預設就該在同步範圍內')

    def test_sync_leaves_out_of_scope_estimates(self):
        """基準日之前的草稿、基準日之後但已核定的估驗單都不動"""
        before = self._estimate(datetime.date(2025, 12, 31))
        approved = self._estimate(datetime.date(2026, 1, 31))
        approved.action_submit_estimate()
        approved.action_approve()
        target = self._estimate(datetime.date(2026, 2, 28))
        co = self._apply_change()
        self._sync(co, self.change_date)

        for est, why in ((before, '基準日之前的草稿'), (approved, '已核定')):
            la = self._line(est, self.a)
            self.assertEqual(la.unit_price, 10.0, '%s 的估驗單被同步改了單價' % why)
            self.assertEqual(la.approved_qty, 100.0, '%s 的估驗單被同步改了數量' % why)
        self.assertEqual(self._line(target, self.a).unit_price, 12.0)

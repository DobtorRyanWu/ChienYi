# -*- coding: utf-8 -*-
"""報表 / 下載中心：選取欄位的清空與重設。

2026-10-13 生產站事故：2.8.0 在 RECORD_SOURCES 加入 field=None 的
「自主檢查表（單張）」後，三處「對每個類型的選取欄位做同一件事」的迴圈
仍直接迭代 RECORD_SOURCES，於是：
- _onchange_download_type 執行 self[None] = False → KeyError: None。
  這個 onchange 在**開啟精靈的第一次 onchange** 就會跑（web 的 onchange()
  首次呼叫會觸發所有有預設值的欄位），所以整個精靈打不開，不只換類型時。
- action_reset 寫入 {None: [Command.clear()]} → 「重新下載」按鈕崩潰。

測試一律走使用者會走的路徑（Form 驅動 web 的 onchange()、按鈕方法），
並斷言「已選的記錄真的被清掉」，避免把迴圈刪掉也能讓測試轉綠。
"""

from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBatchDownloadSelectionFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env['batch.download.wizard']
        cls.project = cls.env['project.project'].create({
            'name': '批次下載測試工程',
            'code': 'BATCH-DL',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.report = cls.env['general.progress.report'].create({
            'project_id': cls.project.id,
            'period_start': '2026-10-01',
            'period_end': '2026-10-07',
        })

    def test_open_and_switch_through_every_type(self):
        """開啟精靈並依序切換每一種下載類型都不可崩潰"""
        types = [value for value, _label
                 in self.Wizard._fields['download_type'].selection]
        # field=None 的類型必須在被測清單裡，否則這支測試量不到事故的成因
        self.assertIn('self_inspection_form', types)

        form = Form(self.Wizard)
        for download_type in types:
            form.download_type = download_type
            self.assertEqual(form.download_type, download_type)

    def test_switch_type_clears_selected_records(self):
        """換類型要清掉前一個類型已手動選取的記錄（onchange 的本意）"""
        form = Form(self.Wizard)
        form.download_type = 'progress_report'
        form.progress_report_ids.add(self.report)
        self.assertEqual(len(form.progress_report_ids), 1)

        form.download_type = 'self_inspection_form'
        self.assertEqual(len(form.progress_report_ids), 0)

    def test_reset_after_download(self):
        """「重新下載」要回到設定步驟並清掉已選記錄"""
        wizard = self.Wizard.create({
            'download_type': 'progress_report',
            'progress_report_ids': [(6, 0, self.report.ids)],
            'state': 'done',
        })
        self.assertEqual(wizard.progress_report_ids, self.report)

        wizard.action_reset()

        self.assertEqual(wizard.state, 'draft')
        self.assertFalse(wizard.progress_report_ids)

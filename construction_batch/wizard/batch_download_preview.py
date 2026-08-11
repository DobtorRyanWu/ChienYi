# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models

# 來源模型 → 本模型用哪個欄位裝它。欄位是 Many2many 而不是自己抄一份明細，
# 這樣畫面上出現的就是該模型**原本的 list view**（欄位、排序、可點進去看詳情）。
# 加新的下載類型時，這裡要一起補一個欄位。
SOURCE_FIELDS = {
    'daily.log.sheet': 'daily_log_ids',
    'payment.estimate': 'estimate_ids',
    'general.progress.report': 'progress_report_ids',
    'reservation.notification.slip': 'slip_ids',
    'supervision.review.application': 'review_ids',
    'supervision.plan.control': 'plan_control_ids',
    'supervision.test.record': 'test_ids',
    'general.self.inspection': 'general_inspection_ids',
    'reservation.self.inspection': 'reservation_inspection_ids',
    'general.defect.improvement': 'general_defect_ids',
    'reservation.defect.improvement': 'reservation_defect_ids',
}


class BatchDownloadPreview(models.TransientModel):
    """報表 / 下載中心的「預覽記錄」視窗。

    為什麼不直接對來源模型開一個 act_window 就好？
    因為 Odoo 的 action 對話框不會堆疊——`action_service.js` 的 `_updateUI` 在開新
    對話框前會先 `_removeDialog()`，預覽一開，下載精靈就被銷毀，關掉預覽後所有設定
    都要重選。開在自己的視窗才有地方放「返回設定」，靠 `wizard_id._reopen()`
    把同一筆精靈記錄叫回來。

    來源記錄用一組 Many2many 裝（每個來源模型一個欄位，見 SOURCE_FIELDS），
    畫面上顯示的就是各模型原本的 list view，可以點進去看單筆詳情。
    """
    _name = 'batch.download.preview'
    _description = '批次下載預覽'

    wizard_id = fields.Many2one(
        'batch.download.wizard',
        string='來源精靈',
        required=True,
        ondelete='cascade')

    source_model = fields.Char(string='來源模型', readonly=True)
    summary = fields.Char(string='摘要', readonly=True)
    note = fields.Char(string='說明', readonly=True)

    # === 各來源模型的記錄（一次只會用到其中一個，由 source_model 決定顯示哪個） ===
    daily_log_ids = fields.Many2many(
        'daily.log.sheet', 'batch_preview_daily_log_rel',
        'preview_id', 'record_id', string='施工日誌')
    estimate_ids = fields.Many2many(
        'payment.estimate', 'batch_preview_estimate_rel',
        'preview_id', 'record_id', string='估驗計價')
    progress_report_ids = fields.Many2many(
        'general.progress.report', 'batch_preview_progress_report_rel',
        'preview_id', 'record_id', string='進度報告')
    slip_ids = fields.Many2many(
        'reservation.notification.slip', 'batch_preview_slip_rel',
        'preview_id', 'record_id', string='通報單')
    review_ids = fields.Many2many(
        'supervision.review.application', 'batch_preview_review_rel',
        'preview_id', 'record_id', string='送審管制')
    plan_control_ids = fields.Many2many(
        'supervision.plan.control', 'batch_preview_plan_control_rel',
        'preview_id', 'record_id', string='計畫書管制表')
    test_ids = fields.Many2many(
        'supervision.test.record', 'batch_preview_test_rel',
        'preview_id', 'record_id', string='檢(試)驗管制')
    general_inspection_ids = fields.Many2many(
        'general.self.inspection', 'batch_preview_general_inspection_rel',
        'preview_id', 'record_id', string='自主檢查')
    reservation_inspection_ids = fields.Many2many(
        'reservation.self.inspection', 'batch_preview_reservation_inspection_rel',
        'preview_id', 'record_id', string='自主檢查（預約式）')
    general_defect_ids = fields.Many2many(
        'general.defect.improvement', 'batch_preview_general_defect_rel',
        'preview_id', 'record_id', string='缺失改善')
    reservation_defect_ids = fields.Many2many(
        'reservation.defect.improvement', 'batch_preview_reservation_defect_rel',
        'preview_id', 'record_id', string='缺失改善（預約式）')

    def action_back(self):
        """回到下載精靈（同一筆記錄，設定全部留著）"""
        self.ensure_one()
        return self.wizard_id._reopen()

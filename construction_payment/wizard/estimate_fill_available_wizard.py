# -*- coding: utf-8 -*-

import html

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# 數量欄位精度，對齊 payment.estimate.line.estimate_qty / available_qty 的 digits=(16, 4)
QTY_PRECISION_DIGITS = 4


class EstimateFillAvailableWizard(models.TransientModel):
    """帶入可估驗數量

    把系統依施工日誌算出的「本次可估驗數量」(available_qty) 預覽後寫入可編輯的
    「本次估驗數量」(estimate_qty)，免去承辦逐列重打——這是對外文宣
    「完成數量只在施工日誌填一次，累計與估驗數量由系統帶出」能不能成立的最後一哩路。

    設計要點（比照 estimate.manual.amount.wizard 的結構）：
    - 彙總項（一式，available_qty 恆為 1）不列入候選：寫入是 no-op，
      且會與「補列彙總項」互打，直接排除、不出現在清單裡。
    - 已填（estimate_qty != 0）、金額手動輸入（is_amount_manual）、可估量 ≤ 0
      三類仍列出，但預設不勾選（使用者仍可手動勾選覆寫）；
      只有「空白且可估量 > 0」預設勾選。
    - 🔴 只寫 estimate_qty 這一個鍵，絕對不要寫 estimate_amount：
      payment.estimate.line.write() 會把顯式寫入 estimate_amount（且未同時給
      manual_estimate_amount）的動作強制標記 is_amount_manual=True（見該檔案的
      write() 覆寫），一次帶入就會把整批列鎖成手動金額。estimate_amount 是
      store=True 的 compute，depends 含 estimate_qty，寫完 qty 會自動跟上。
    """
    _name = 'estimate.fill.available.wizard'
    _description = '帶入可估驗數量'

    estimate_id = fields.Many2one(
        'payment.estimate',
        '估驗單',
        required=True,
        ondelete='cascade'
    )
    line_ids = fields.One2many(
        'estimate.fill.available.wizard.line',
        'wizard_id',
        '候選工項'
    )
    selected_count = fields.Integer(
        '已勾選數',
        compute='_compute_selected_count'
    )
    has_missing_date = fields.Boolean(
        '缺估驗日期',
        compute='_compute_has_missing_date',
        help='估驗日期為空時，本次可估驗數量全部算成 0'
    )

    @api.depends('line_ids.to_apply')
    def _compute_selected_count(self):
        for wiz in self:
            wiz.selected_count = len(wiz.line_ids.filtered('to_apply'))

    @api.depends('estimate_id.estimate_date')
    def _compute_has_missing_date(self):
        for wiz in self:
            wiz.has_missing_date = bool(wiz.estimate_id) and not wiz.estimate_id.estimate_date

    @staticmethod
    def _default_checked(estimate_line):
        """預設是否勾選：只有「空白且可估量 > 0」才預設勾選

        三類預設不勾（已填／金額手動／可估量 ≤ 0）仍列出供使用者手動覆寫，
        優先序（與略過原因分類一致）：已填未勾 > 金額手動 > 可估量 ≤ 0。
        """
        already_filled = float_compare(
            estimate_line.estimate_qty, 0.0, precision_digits=QTY_PRECISION_DIGITS) != 0
        if already_filled or estimate_line.is_amount_manual:
            return False
        return float_compare(
            estimate_line.available_qty, 0.0, precision_digits=QTY_PRECISION_DIGITS) > 0

    @api.model
    def default_get(self, fields_list):
        """由估驗單帶出所有非彙總工項（彙總項硬跳過，不出現在候選清單）"""
        res = super().default_get(fields_list)
        estimate_id = res.get('estimate_id') or self.env.context.get('active_id')
        if not estimate_id:
            return res
        estimate = self.env['payment.estimate'].browse(estimate_id)
        res['estimate_id'] = estimate.id
        candidate_lines = estimate.line_ids.filtered(
            lambda l: not l.is_summary_item
        ).sorted(key=lambda l: (l.sequence or 0, l.id))
        res['line_ids'] = [
            (0, 0, {
                'estimate_line_id': line.id,
                'sequence': line.sequence,
                'to_apply': self._default_checked(line),
            })
            for line in candidate_lines
        ]
        return res

    def action_select_all(self):
        """全選"""
        self.ensure_one()
        self.line_ids.to_apply = True
        return self._reopen()

    def action_unselect_all(self):
        """全不選"""
        self.ensure_one()
        self.line_ids.to_apply = False
        return self._reopen()

    def action_select_blank_only(self):
        """只勾「空白且可估量 > 0」的列（還原成預設勾選狀態）"""
        self.ensure_one()
        for line in self.line_ids:
            line.to_apply = self._default_checked(line.estimate_line_id)
        return self._reopen()

    def _reopen(self):
        """保持在同一張精靈（全選／全不選／只勾空白列 後重新顯示）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '帶入可估驗數量',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_fill_available_qty(self):
        """把勾選工項的「本次可估驗數量」寫入「本次估驗數量」

        逐筆 write（而非整批同值 write）：每列的新值各不相同，且需要各自的
        原值/新值供 chatter 明細，候選列數以單張估驗單的工項數為界，非全庫掃描。
        """
        self.ensure_one()
        estimate = self.estimate_id
        if estimate.state not in ('draft', 'pending_approval'):
            raise UserError('已核定或已歸檔的估驗單不能修改數量。')

        selected = self.line_ids.filtered('to_apply')
        if not selected:
            if not estimate.estimate_date:
                raise UserError(
                    '請至少勾選一個要帶入可估驗數量的工項。\n'
                    '本單尚未填「估驗日期」，本次可估驗數量全部算成 0，'
                    '請先在表頭填上估驗日期再重新開啟本精靈。'
                )
            raise UserError('請至少勾選一個要帶入可估驗數量的工項。')

        applied_details = []
        for wline in selected.sorted(key=lambda l: (l.sequence or 0, l.id)):
            est_line = wline.estimate_line_id
            old_qty = est_line.estimate_qty
            new_qty = est_line.available_qty
            if float_compare(old_qty, new_qty, precision_digits=QTY_PRECISION_DIGITS) == 0:
                continue
            # 🔴 只寫這一個鍵，estimate_amount 由 store compute 自動跟上
            est_line.write({'estimate_qty': new_qty})
            label = est_line.item_no or est_line.description or ('明細#%s' % est_line.id)
            applied_details.append(
                '%s：%.4f → %.4f' % (label, old_qty, new_qty)
            )

        # 略過原因分類（優先序：已填未勾 > 金額手動 > 可估量≤0 > 使用者未勾選其餘空白列）
        skip_filled = skip_manual = skip_zero = skip_other = 0
        for wline in self.line_ids.filtered(lambda l: not l.to_apply):
            est_line = wline.estimate_line_id
            if float_compare(
                    est_line.estimate_qty, 0.0, precision_digits=QTY_PRECISION_DIGITS) != 0:
                skip_filled += 1
            elif est_line.is_amount_manual:
                skip_manual += 1
            elif float_compare(
                    est_line.available_qty, 0.0, precision_digits=QTY_PRECISION_DIGITS) <= 0:
                skip_zero += 1
            else:
                skip_other += 1
        skip_summary = len(estimate.line_ids.filtered('is_summary_item'))

        applied_count = len(applied_details)
        reason_parts = []
        if skip_summary:
            reason_parts.append('彙總項 %s' % skip_summary)
        if skip_filled:
            reason_parts.append('已填未勾 %s' % skip_filled)
        if skip_manual:
            reason_parts.append('金額手動 %s' % skip_manual)
        if skip_zero:
            reason_parts.append('可估量≤0 %s' % skip_zero)
        if skip_other:
            reason_parts.append('使用者未勾選 %s' % skip_other)
        total_skipped = skip_summary + skip_filled + skip_manual + skip_zero + skip_other
        reason_text = '、'.join(reason_parts) if reason_parts else '無'

        # chatter：帶「原值 → 新值」明細，是唯一的還原依據
        body = (
            '帶入可估驗數量：<b>%s</b> 個工項已寫入本次估驗數量，'
            '略過 <b>%s</b> 個工項（%s）。'
        ) % (applied_count, total_skipped, html.escape(reason_text))
        if applied_details:
            body += '<br/>原值 → 新值明細：<ul>' + ''.join(
                '<li>%s</li>' % html.escape(d) for d in applied_details
            ) + '</ul>'
        else:
            body += '<br/>（本次勾選的工項數值與現況相同，未實際變動。）'
        if not estimate.estimate_date:
            body += '<br/>⚠ 本單尚未填「估驗日期」，本次可估驗數量全部算成 0，請先填估驗日期。'
        estimate.message_post(body=body)

        if applied_count:
            notif_message = '已帶入 %s 個工項的本次可估驗數量。' % applied_count
            notif_type = 'success'
        else:
            notif_message = '勾選的工項數值與現況相同，未實際變動。'
            notif_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '帶入可估驗數量',
                'message': notif_message,
                'type': notif_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class EstimateFillAvailableWizardLine(models.TransientModel):
    """帶入可估驗數量 — 候選工項"""
    _name = 'estimate.fill.available.wizard.line'
    _description = '帶入可估驗數量明細'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'estimate.fill.available.wizard',
        '精靈',
        required=True,
        ondelete='cascade'
    )
    # ⚠ 不可加 readonly=True：Odoo 17+ 前端不回送 readonly 欄位，
    #   精靈存檔時 estimate_line_id 會變 NULL 而撞 not-null（同
    #   estimate_manual_amount_wizard.py 的實測註解）。本欄在 view 內是
    #   column_invisible，使用者本來就改不到。
    estimate_line_id = fields.Many2one(
        'payment.estimate.line',
        '估驗明細',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer('序號')
    to_apply = fields.Boolean(
        '帶入',
        default=False,
        help='勾選＝把本次可估驗數量寫入本次估驗數量；不勾＝維持現值'
    )

    # === 顯示用（唯讀，即時反映估驗明細現況）===
    item_no = fields.Char('項目編號', related='estimate_line_id.item_no', readonly=True)
    description = fields.Char('項目及說明', related='estimate_line_id.description', readonly=True)
    unit = fields.Char('單位', related='estimate_line_id.unit', readonly=True)
    is_amount_manual = fields.Boolean(
        '金額手動輸入', related='estimate_line_id.is_amount_manual', readonly=True
    )
    current_qty = fields.Float(
        '現有本次估驗數量',
        digits=(16, 4),
        related='estimate_line_id.estimate_qty',
        readonly=True
    )
    available_qty = fields.Float(
        '本次可估驗數量',
        digits=(16, 4),
        related='estimate_line_id.available_qty',
        readonly=True
    )
    diff_qty = fields.Float(
        '差額',
        digits=(16, 4),
        compute='_compute_diff_qty',
        help='本次可估驗數量 − 現有本次估驗數量（帶入後數量的變動量）'
    )

    @api.depends('estimate_line_id.estimate_qty', 'estimate_line_id.available_qty')
    def _compute_diff_qty(self):
        for line in self:
            line.diff_qty = line.available_qty - line.current_qty

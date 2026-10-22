"""會費繳至的連續計算（計畫 §2.3）。

欄位定義在 `assoc_base`（沒裝繳費模組時「繳至」就等於期初值）；
這裡把它換成「常年會費期別一期一期接上去，中間斷一期就停」。

fail-closed：跳繳、漏產應繳列、應繳未繳，一律停在斷掉的前一期。
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

ANNUAL = 'annual'
SETTLED_STATES = ('paid', 'waived')


class AssocMemberFee(models.Model):
    _inherit = 'assoc.member'

    dues_ids = fields.One2many('assoc.dues', 'member_id', string='應繳紀錄')
    payment_ids = fields.One2many('assoc.payment', 'member_id', string='收款紀錄')
    unpaid_dues_count = fields.Integer(string='未繳筆數', compute='_compute_unpaid')

    @api.depends('fee_paid_opening', 'dues_ids.state', 'dues_ids.fee_type',
                 'dues_ids.date_from', 'dues_ids.date_to')
    def _compute_fee_coverage(self):
        """一期一期往後接；斷掉就停。**不看今天**（理由見 assoc_base 的基礎版）。"""
        for member in self:
            coverage = member.fee_paid_opening
            start = False
            # 排序要是決定性的：`sorted('date_from')` 是穩定排序，起日相同時
            # 順序由 recordset 既有順序（`_order` 含 period_id desc）決定，
            # 同一份業務事實會因建立順序不同而得到不同答案。
            # 重疊已由期別的 `_check_no_annual_overlap` 擋掉，這裡再加 id 保底。
            periods = member.dues_ids.filtered(lambda d: d.fee_type == ANNUAL).sorted(
                key=lambda d: (d.date_from, d.date_to, d.id))
            for dues in periods:
                if dues.state not in SETTLED_STATES:
                    break
                if coverage:
                    # 必須接得上：中間空一段就是斷掉（跳繳）
                    if dues.date_from > coverage + timedelta(days=1):
                        break
                else:
                    # 還沒有起點：第一期繳清才開始起算
                    start = dues.date_from
                # 只往後接，不會倒退：期初繳至可能比某一期的迄日還晚
                # （舊系統已預繳到後年），結清那一期不該把會籍往前縮。
                coverage = max(coverage, dues.date_to) if coverage else dues.date_to
            member.fee_paid_until = coverage
            member.coverage_from = start

    @api.depends('dues_ids.state')
    def _compute_unpaid(self):
        for member in self:
            member.unpaid_dues_count = len(
                member.dues_ids.filtered(lambda d: d.state == 'unpaid'))

    def action_collect_fee(self):
        """從會員表單開一張草稿收款，並把他所有未繳的應繳帶進去。

        不用 wizard（本專案慣例）：直接建草稿並開啟它，出納在上面確認金額與方式後過帳。
        """
        self.ensure_one()
        unpaid = self.dues_ids.filtered(lambda d: d.state == 'unpaid' and not d.payment_id)
        if not unpaid:
            raise UserError(_('這位會員沒有未繳的應繳。'))
        payment = self.env['assoc.payment'].create({
            'company_id': self.company_id.id,
            'member_id': self.id,
            'payer_name': self.name,
        })
        payment.action_bind_dues(unpaid.ids)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'assoc.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

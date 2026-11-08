# -*- coding: utf-8 -*-
"""payment.estimate × doc.linked.mixin（Sprint 22）

估驗計價整合：套 template_payment_estimate 樣板。
collaborators = submitted_by_id（提出人）+ approved_by_id（核定人）+ 當前 user。
建立文件／重新套用範本時，表頭與「本期完成工項」填成實際值（見 payment_estimate_doc_helper）。
"""

from odoo import models, _
from odoo.tools.float_utils import float_is_zero

from . import payment_estimate_doc_helper as helper

# 「前期已核定」的狀態：與 payment.estimate.line._compute_previous_approved_qty、
# construction_template/mappings/estimate_report.py::APPROVED_STATES 相同
APPROVED_STATES = ('approved', 'archived')
# 本期數量／金額小於這個位數就當作 0（本期沒估、不列進工項表）
ZERO_DIGITS = 6


class PaymentEstimate(models.Model):
    _name = 'payment.estimate'
    _inherit = ['payment.estimate', 'doc.linked.mixin']

    def _doc_default_template_xml_id(self):
        self.ensure_one()
        return 'dobtor_doc_editor.template_payment_estimate'

    def _doc_initial_name(self):
        self.ensure_one()
        # name 預設是「第N次估驗計價」
        base = self.name or (
            _('第%s次估驗計價') % (self.estimate_no or 1)
        )
        if self.project_id:
            return '%s - %s' % (base, self.project_id.name)
        return base

    def _doc_prepare_content_html(self, html):
        """把範本的 {{ 變數 }} 與工項表填成這張估驗的實際值（建立與「重新套用範本」都走這裡）。

        金額定義與「工程估驗計價單」匯出的「合計（僅合約項）」相同
        （construction_template/mappings/estimate_report.py::build_context）：
          本期 ＝ contract_subtotal（Monetary，已依幣別精度捨入；工項表小計合計＝它）
          累計 ＝ 本張葉節點明細金額 ＋ 排在前面、已核定／已歸檔各期葉節點的實際金額，
                 **加總後才**四捨五入（不是各期 contract_subtotal 相加：那是逐期捨入後再加，
                 會差 1～2 元，與匯出對不起來）
        沒有估驗日期時前期一律不算（模型的前期累計也是這樣，estimate_warnings 會提醒）。
        """
        html = super()._doc_prepare_content_html(html)
        if not html:
            return html
        self.ensure_one()
        project = self.project_id
        earlier = self.browse()
        if self.estimate_date:
            earlier = self._estimates_before().filtered(lambda e: e.state in APPROVED_STATES)
        current = self.contract_subtotal or 0.0
        leaves = self.line_ids.filtered(lambda ln: not ln.is_summary_item)
        cumulative = sum(leaves.mapped('estimate_amount')) + sum(
            ln._get_effective_amount()
            for est in earlier
            for ln in est.line_ids.filtered(lambda ln: not ln.is_summary_item))
        html = helper.fill_vars(html, {
            'project_name': project.name or '',
            'estimate_date': helper.roc_date(self.estimate_date),
            'contractor': self._doc_contractor_name(),
            'estimate_no': str(self.estimate_no or ''),
            'current_amount': helper.money(helper.round_half_up(current)),
            'cumulative_amount': helper.money(helper.round_half_up(cumulative)),
        })
        lines = leaves.filtered(
            lambda ln: not (
                float_is_zero(ln.estimate_qty, precision_digits=ZERO_DIGITS)
                and float_is_zero(ln.estimate_amount, precision_digits=ZERO_DIGITS))
        ).sorted(lambda ln: (ln.sequence, ln.id))
        # 小計做尾差調整：整欄加起來等於表頭的本期估驗金額（逐列四捨五入會差 1～2 元）
        amounts = helper.balanced(lines.mapped('estimate_amount'), current)
        rows = [
            (ln.item_no or '', ln.description or '', ln.unit or '',
             helper.number(ln.estimate_qty, helper.QTY_DIGITS),
             helper.number(ln.unit_price, helper.PRICE_DIGITS),
             helper.money(amount))
            for ln, amount in zip(lines, amounts)
        ]
        return helper.inject_rows(html, rows)

    def _doc_contractor_name(self):
        """工程案件的承包廠商名稱：contractor_company_name（純文字）→ 承包廠商聯絡人。

        與 construction_template/utils/formatters.py::contractor_name 同一個取值序。
        contractor_partner_ids 定義在 construction_portal（本模組不依賴它），所以先查欄位在不在。
        """
        self.ensure_one()
        project = self.project_id
        if not project:
            return ''
        if project.contractor_company_name:
            return project.contractor_company_name
        if 'contractor_partner_ids' in project._fields:
            return '、'.join(project.contractor_partner_ids.mapped('name'))
        return ''

    def _doc_collaborators(self):
        """提出人 + 核定人 + 當前 user（不含 line 內的 task assignees，避免噪音）。"""
        self.ensure_one()
        users = self.env['res.users']
        if self.submitted_by_id:
            users |= self.submitted_by_id
        if self.approved_by_id:
            users |= self.approved_by_id
        users |= self.env.user
        return users

    def _doc_render_context(self):
        self.ensure_one()
        state_label = ''
        if self.state and 'state' in self._fields:
            state_label = dict(
                self._fields['state'].selection
            ).get(self.state, '')
        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'project_name': self.project_id.name if self.project_id else '',
            'estimate_name': self.name or '',
            'estimate_no': self.estimate_no or 0,
            'estimate_date': self.estimate_date.strftime('%Y-%m-%d')
                if self.estimate_date else '',
            'submitted_date': (self.submitted_date.strftime('%Y-%m-%d %H:%M')
                               if self.submitted_date else ''),
            'submitted_by': (self.submitted_by_id.name
                             if self.submitted_by_id else ''),
            'approved_date': (self.approved_date.strftime('%Y-%m-%d %H:%M')
                              if self.approved_date else ''),
            'approved_by': (self.approved_by_id.name
                            if self.approved_by_id else ''),
            'subtotal': self.subtotal or 0.0,
            'state_label': state_label,
            'line_count': len(self.line_ids),
        }

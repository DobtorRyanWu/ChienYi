# -*- coding: utf-8 -*-
"""xlsx.linked.mixin（§4.5.2）

讓任何 ChienYi 業務模型「關聯」可編輯試算表（spreadsheet.spreadsheet），提供：
- 試算表自動建立（pull-on-demand：點按鈕才建，避免一堆空表）
- 通用回掛（res_model/res_id，不需各 model 在 spreadsheet 上開 FK）
- 初始資料 hook（由業務 model 覆寫，產出 o-spreadsheet WorkbookData）

對標 dobtor_doc_editor 的 doc.linked.mixin。

使用方式：
    class PaymentEstimate(models.Model):
        _name = 'payment.estimate'
        _inherit = ['xlsx.linked.mixin']

        def _xlsx_default_name(self):
            return _('估驗試算表 - %s') % self.display_name

        def _xlsx_build_data(self):
            return self._build_estimate_workbook_data()  # o-spreadsheet WorkbookData dict

設計原則：
    - mixin 不知道 ChienYi 業務細節：所有業務邏輯走 hook method 由繼承 model 覆寫
    - 通用 res_model/res_id：spreadsheet 端零侵入（不需逐 model 開 FK）
"""
from odoo import api, fields, models, _


class XlsxLinkedMixin(models.AbstractModel):
    _name = "xlsx.linked.mixin"
    _description = "可關聯可編輯試算表的 mixin"

    linked_spreadsheet_count = fields.Integer(
        string="關聯試算表數",
        compute="_compute_linked_spreadsheet_count",
    )

    def _compute_linked_spreadsheet_count(self):
        Spreadsheet = self.env["spreadsheet.spreadsheet"]
        # 一次 read_group 避免逐筆 search_count
        if not self.ids:
            for rec in self:
                rec.linked_spreadsheet_count = 0
            return
        groups = Spreadsheet.read_group(
            [("res_model", "=", self._name), ("res_id", "in", self.ids)],
            ["res_id"],
            ["res_id"],
        )
        counts = {g["res_id"]: g["res_id_count"] for g in groups}
        for rec in self:
            rec.linked_spreadsheet_count = counts.get(rec.id, 0)

    # ─── Hook methods（由繼承 model 覆寫）──────────────────────────

    def _xlsx_default_name(self):
        """新建試算表的名稱（預設用記錄顯示名）。"""
        self.ensure_one()
        return self.display_name or _("試算表")

    def _xlsx_build_data(self):
        """回傳初始 o-spreadsheet WorkbookData（dict）；預設 None = 空白試算表。

        業務 model 覆寫此 method 產出工項/估驗等初始內容。
        """
        return None

    def _xlsx_extra_create_vals(self):
        """新建 spreadsheet 的額外欄位（如 fidelity_grade）。"""
        return {}

    # ─── Actions ──────────────────────────────────────────────────

    def _linked_spreadsheets(self):
        self.ensure_one()
        return self.env["spreadsheet.spreadsheet"].search(
            [("res_model", "=", self._name), ("res_id", "=", self.id)],
            order="id desc",
        )

    def _create_linked_spreadsheet(self):
        """建立一份回掛本記錄的試算表並回傳之。"""
        self.ensure_one()
        vals = {
            "name": self._xlsx_default_name(),
            "res_model": self._name,
            "res_id": self.id,
        }
        data = self._xlsx_build_data()
        if data is not None:
            vals["spreadsheet_raw"] = data
        vals.update(self._xlsx_extra_create_vals())
        return self.env["spreadsheet.spreadsheet"].create(vals)

    def _open_spreadsheet_action(self, spreadsheet):
        return {
            "type": "ir.actions.client",
            "tag": "action_spreadsheet_oca",
            "params": {"spreadsheet_id": spreadsheet.id, "model": "spreadsheet.spreadsheet"},
        }

    def action_open_linked_spreadsheet(self):
        """開啟關聯試算表（pull-on-demand：無則建一份；多份則開最新）。"""
        self.ensure_one()
        existing = self._linked_spreadsheets()
        spreadsheet = existing[:1] if existing else self._create_linked_spreadsheet()
        return self._open_spreadsheet_action(spreadsheet)

    def action_open_linked_spreadsheets(self):
        """列出本記錄關聯的所有試算表（多份時用）。"""
        self.ensure_one()
        existing = self._linked_spreadsheets()
        if len(existing) == 1:
            return self._open_spreadsheet_action(existing)
        return {
            "type": "ir.actions.act_window",
            "name": _("關聯試算表"),
            "res_model": "spreadsheet.spreadsheet",
            "view_mode": "list,form",
            "domain": [("res_model", "=", self._name), ("res_id", "=", self.id)],
            "context": {"create": False},
        }

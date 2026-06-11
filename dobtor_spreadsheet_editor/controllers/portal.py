# -*- coding: utf-8 -*-
"""Portal 試算表（§4.5.3）

讓 portal/internal user 在前台編輯被授權的試算表：
- /my/spreadsheets：清單（受 ir.rule 限制）
- /my/spreadsheet/<id>：嵌入 o-spreadsheet 編輯器（前端 mount Spreadsheet 元件）

存取控制：browse + check_access（read/write）；portal user 由 ir.rule 過濾。
編輯器資料/存檔走 JSON rpc（read_spreadsheet / save_spreadsheet），於元件內呼叫。
"""
from odoo import http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class SpreadsheetPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "spreadsheet_count" in counters:
            values["spreadsheet_count"] = (
                request.env["spreadsheet.spreadsheet"].search_count([])
                if request.env["spreadsheet.spreadsheet"].check_access_rights("read", raise_exception=False)
                else 0
            )
        return values

    @http.route(["/my/spreadsheets", "/my/spreadsheets/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_spreadsheets(self, page=1, sortby="date", **kw):
        Spreadsheet = request.env["spreadsheet.spreadsheet"]
        domain = []
        sortings = {
            "date": {"label": _("最新"), "order": "write_date desc"},
            "name": {"label": _("名稱"), "order": "name"},
        }
        order = sortings.get(sortby, sortings["date"])["order"]
        total = Spreadsheet.search_count(domain)
        pager = portal_pager(
            url="/my/spreadsheets",
            url_args={"sortby": sortby},
            total=total,
            page=page,
            step=self._items_per_page,
        )
        records = Spreadsheet.search(domain, order=order, limit=self._items_per_page, offset=pager["offset"])
        values = {
            "spreadsheets": records,
            "page_name": "spreadsheet",
            "pager": pager,
            "sortby": sortby,
            "sortings": sortings,
            "default_url": "/my/spreadsheets",
        }
        return request.render("dobtor_spreadsheet_editor.portal_my_spreadsheets", values)

    @http.route(["/my/spreadsheet/<int:spreadsheet_id>"], type="http", auth="user", website=True)
    def portal_spreadsheet(self, spreadsheet_id, **kw):
        try:
            spreadsheet = self._document_check_access(spreadsheet_id, "read")
        except (AccessError, MissingError):
            return request.redirect("/my")
        # 可編輯旗標（模型層 ACL）；存檔 rpc 另以 check_access_rule('write') 二次把關記錄規則
        editable = spreadsheet.check_access_rights("write", raise_exception=False)
        values = {
            "spreadsheet": spreadsheet,
            "spreadsheet_id": spreadsheet_id,
            "sse_editable": editable,
            "page_name": "spreadsheet",
        }
        return request.render("dobtor_spreadsheet_editor.portal_spreadsheet_page", values)

    def _document_check_access(self, spreadsheet_id, access):
        spreadsheet = request.env["spreadsheet.spreadsheet"].browse(spreadsheet_id)
        spreadsheet.check_access_rights(access)
        spreadsheet.check_access_rule(access)
        if not spreadsheet.exists():
            raise MissingError(_("試算表不存在"))
        return spreadsheet

    # ── 編輯器資料 / 存檔（JSON rpc）──
    @http.route(["/my/spreadsheet/<int:spreadsheet_id>/data"], type="json", auth="user")
    def portal_spreadsheet_data(self, spreadsheet_id, **kw):
        sp = self._document_check_access(spreadsheet_id, "read")
        return {
            "name": sp.name,
            "spreadsheet_raw": sp.spreadsheet_raw,
            "revisions": [],  # portal 單人編輯，不走協作 revision
        }

    @http.route(["/my/spreadsheet/<int:spreadsheet_id>/save"], type="json", auth="user")
    def portal_spreadsheet_save(self, spreadsheet_id, data=None, **kw):
        sp = self._document_check_access(spreadsheet_id, "write")
        if data is not None:
            sp.write({"spreadsheet_raw": data})
        return {"ok": True}

# -*- coding: utf-8 -*-
"""general.self.inspection × doc.linked.mixin 整合（Sprint 21）

把 doc.linked.mixin 加進一般式自主檢查的 _inherit 鏈，並依
docs/chienyi_integration_examples.md §3 的範例覆寫 hook methods。

整合邏輯：
    template = dobtor_doc_editor.template_self_inspection（已存在於 data/doc_template_data.xml）
    協作者   = inspector_id + supervisor_id + contractor_company_id 的 user_ids
    Jinja ctx = 工程名 / 檢查日期 / 類型 / 時機 / 檢查人 / 承包商
"""

from odoo import models, _

from .self_inspection_doc_helper import inject_checklist


class GeneralSelfInspection(models.Model):
    """擴充一般式自主檢查，加入 doc.linked.mixin 能力。

    Sprint 21 第一個實際植入 mixin 的 ChienYi 模組。
    """

    _name = 'general.self.inspection'
    _inherit = ['general.self.inspection', 'doc.linked.mixin']

    # ─── doc.linked.mixin hook 覆寫 ───────────────────────────────

    def _doc_default_template_xml_id(self):
        """套用 dobtor_doc_editor 預設的「自主檢查表」樣板。"""
        self.ensure_one()
        return 'dobtor_doc_editor.template_self_inspection'

    def _create_linked_doc(self):
        """建立文件後，把檢查清單換成此檢查類型的預設項目（self.inspection.type.item）。"""
        doc = super()._create_linked_doc()
        if doc and self.inspection_type_id:
            items = self.inspection_type_id.default_item_ids.sorted('sequence')
            new_html = inject_checklist(doc.content_html, items)
            if new_html != doc.content_html:
                doc.content_html = new_html
        return doc

    def _doc_initial_name(self):
        """文件命名：檢查編號 + 分項工程名稱（若有）。"""
        self.ensure_one()
        if self.sub_project_name:
            return '%s - %s' % (self.name or _('自主檢查'), self.sub_project_name)
        return self.name or _('自主檢查')

    def _doc_collaborators(self):
        """檢查人 + 監造員 + 承包商所屬 user 全部加為協作者。

        - inspector_id / supervisor_id 為 res.users
        - contractor_company_id 是 res.company；其關聯 user 走 user_ids
        """
        self.ensure_one()
        users = self.env['res.users']
        if self.inspector_id:
            users |= self.inspector_id
        if self.supervisor_id:
            users |= self.supervisor_id
        if self.contractor_company_id and 'user_ids' in self.contractor_company_id._fields:
            users |= self.contractor_company_id.user_ids
        # 至少包含當前 user（避免 collaborators 為空）
        users |= self.env.user
        return users

    def _doc_render_context(self):
        """提供 Jinja 樣板填充用的 context（key 與 template_self_inspection 對齊）。"""
        self.ensure_one()
        timing_label = ''
        if self.inspection_timing and 'inspection_timing' in self._fields:
            timing_label = dict(
                self._fields['inspection_timing'].selection
            ).get(self.inspection_timing, '')
        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'project_name': self.project_id.name if self.project_id else '',
            'inspection_no': self.name or '',
            'inspection_date': self.inspection_date.strftime('%Y-%m-%d')
                if self.inspection_date else '',
            'inspection_type': self.inspection_type_id.name
                if self.inspection_type_id else '',
            'sub_project_name': self.sub_project_name or '',
            'inspection_location': self.inspection_location or '',
            'timing': timing_label,
            'inspector': self.inspector_id.name if self.inspector_id else '',
            'supervisor': self.supervisor_id.name if self.supervisor_id else '',
            'contractor': self.contractor_company_id.name
                if self.contractor_company_id else '',
        }

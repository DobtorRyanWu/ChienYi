# -*- coding: utf-8 -*-
"""reservation.self.inspection × doc.linked.mixin（Sprint 22）

預約式自主檢查整合，沿用 Sprint 21 general.self.inspection 模式。
與一般式差異：
- 沒有 supervisor_id / contractor_company_id
- 多了 slip_id 通報單關聯
- name 欄位是 inspection_no（Char）
"""

from odoo import models, _

from .self_inspection_doc_helper import inject_checklist


class ReservationSelfInspection(models.Model):
    _name = 'reservation.self.inspection'
    _inherit = ['reservation.self.inspection', 'doc.linked.mixin']

    def _doc_default_template_xml_id(self):
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
        self.ensure_one()
        no = self.inspection_no or _('預約式自主檢查')
        if self.sub_project_name:
            return '%s - %s' % (no, self.sub_project_name)
        return no

    def _doc_collaborators(self):
        """檢查人 + 當前使用者；預約式無 supervisor/contractor。"""
        self.ensure_one()
        users = self.env['res.users']
        if self.inspector_id:
            users |= self.inspector_id
        users |= self.env.user
        return users

    def _doc_render_context(self):
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
            'slip_no': (self.slip_id.slip_number
                        if self.slip_id and 'slip_number' in self.slip_id._fields
                        else ''),
            'inspection_no': self.inspection_no or '',
            'inspection_date': self.inspection_date.strftime('%Y-%m-%d')
                if self.inspection_date else '',
            'inspection_type': self.inspection_type_id.name
                if self.inspection_type_id else '',
            'sub_project_name': self.sub_project_name or '',
            'inspection_location': self.inspection_location or '',
            'timing': timing_label,
            'inspector': self.inspector_id.name if self.inspector_id else '',
            'contractor': self.contractor_name or '',
            'subcontractor': self.subcontractor_name or '',
        }

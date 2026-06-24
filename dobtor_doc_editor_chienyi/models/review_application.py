# -*- coding: utf-8 -*-
"""supervision.review.application × doc.linked.mixin

材料／設備送審管制整合：套 template_review_control 樣板。
與自主檢查/缺失同模式（Sprint 21-22）。
"""

from odoo import models, _


class SupervisionReviewApplication(models.Model):
    _name = 'supervision.review.application'
    _inherit = ['supervision.review.application', 'doc.linked.mixin']

    def _doc_default_template_xml_id(self):
        self.ensure_one()
        return 'dobtor_doc_editor.template_review_control'

    def _doc_initial_name(self):
        self.ensure_one()
        code = self.sequence_code if self.sequence_code and self.sequence_code != '/' else ''
        material = self.name or _('送審管制')
        return '%s %s' % (code, material) if code else material

    def _doc_collaborators(self):
        """送審無專屬負責人欄位 → 建立者 + 當前 user。"""
        self.ensure_one()
        users = self.env['res.users']
        if self.create_uid:
            users |= self.create_uid
        users |= self.env.user
        return users

    def _doc_render_context(self):
        self.ensure_one()
        # 審查結果 Selection label
        result_label = ''
        if 'final_review_result' in self._fields and self.final_review_result:
            result_label = dict(
                self._fields['final_review_result'].selection
            ).get(self.final_review_result, '')
        # 送審內容（依 has_* 布林組合）
        items = []
        for fname, label in (('has_catalog', '型錄'),
                             ('has_demo', '樣品'),
                             ('has_related_test_report', '相關測試報告'),
                             ('has_subcontractor', '協力廠商資料')):
            if fname in self._fields and self[fname]:
                items.append(label)
        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'project_name': self.project_id.name if self.project_id else '',
            'review_no': self.sequence_code or '',
            'material_name': self.name or '',
            'item_no': self.no or '',
            'quantity': self.number or '',
            'expected_date': self.expected_review_date.strftime('%Y-%m-%d')
                if self.expected_review_date else '',
            'final_date': self.final_review_date.strftime('%Y-%m-%d')
                if self.final_review_date else '',
            'review_result': result_label,
            'review_items': '、'.join(items),
        }

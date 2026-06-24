# -*- coding: utf-8 -*-
"""payment.estimate × doc.linked.mixin（Sprint 22）

估驗計價整合：套 template_payment_estimate 樣板。
collaborators = submitted_by_id（提出人）+ approved_by_id（核定人）+ 當前 user。
"""

from odoo import models, _


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

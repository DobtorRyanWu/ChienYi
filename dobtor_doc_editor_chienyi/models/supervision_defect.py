# -*- coding: utf-8 -*-
"""supervision.defect × doc.linked.mixin（Sprint 22）

缺失改善整合：套 template_defect_improvement 樣板，
collaborators 包含 responsible_user_id（負責人）+ created_by + 當前 user。
"""

from odoo import models, _


class SupervisionDefect(models.Model):
    _name = 'supervision.defect'
    _inherit = ['supervision.defect', 'doc.linked.mixin']

    def _doc_default_template_xml_id(self):
        self.ensure_one()
        return 'dobtor_doc_editor.template_defect_improvement'

    def _doc_initial_name(self):
        self.ensure_one()
        if self.description:
            short = self.description[:40].strip()
            return '%s - %s' % (self.name or _('缺失'), short)
        return self.name or _('缺失改善通知')

    def _doc_collaborators(self):
        """負責人 + 建立者 + 當前 user。"""
        self.ensure_one()
        users = self.env['res.users']
        if self.responsible_user_id:
            users |= self.responsible_user_id
        if self.create_uid:
            users |= self.create_uid
        users |= self.env.user
        return users

    def _doc_render_context(self):
        self.ensure_one()
        defect_type_label = ''
        severity_label = ''
        if self.defect_type and 'defect_type' in self._fields:
            defect_type_label = dict(
                self._fields['defect_type'].selection
            ).get(self.defect_type, '')
        if 'severity' in self._fields and self.severity:
            severity_label = dict(
                self._fields['severity'].selection
            ).get(self.severity, '')
        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'project_name': self.project_id.name if self.project_id else '',
            'defect_no': self.name or '',
            'defect_type': defect_type_label,
            'severity': severity_label,
            'description': self.description or '',
            'found_date': self.found_date.strftime('%Y-%m-%d')
                if self.found_date else '',
            'deadline': self.deadline.strftime('%Y-%m-%d')
                if self.deadline else '',
            'responsible': (self.responsible_user_id.name
                            if self.responsible_user_id else ''),
            'source_description': self.source_description or '',
        }

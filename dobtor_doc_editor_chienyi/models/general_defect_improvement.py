# -*- coding: utf-8 -*-
"""general.defect.improvement × doc.linked.mixin

缺失改善整合：套 template_defect_improvement 樣板，
collaborators 包含 responsible_user_id（負責人）+ created_by + 當前 user。

原本掛在 supervision.defect（NCR）上；NCR 移除後改指一般式缺失改善。
除了模型換掉，也一併補齊樣板需要但舊版 context 沒給的三個 key
（notice_no / responsible_company / defect_categories）。

寫法比照同模組的 general_self_inspection.py（同一 mixin 的既有宿主）。
"""

from odoo import models, _


class GeneralDefectImprovement(models.Model):
    _name = 'general.defect.improvement'
    _inherit = ['general.defect.improvement', 'doc.linked.mixin']

    # ─── doc.linked.mixin hook 覆寫 ───────────────────────────────

    def _doc_default_template_xml_id(self):
        self.ensure_one()
        return 'dobtor_doc_editor.template_defect_improvement'

    def _doc_initial_name(self):
        self.ensure_one()
        if self.defect_description:
            short = self.defect_description[:40].strip()
            return '%s - %s' % (self.defect_no or _('缺失'), short)
        return self.defect_no or _('缺失改善通知')

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
        """提供 Jinja 樣板填充用的 context（key 與 template_defect_improvement 對齊）。"""
        self.ensure_one()

        def _label(fname, value):
            if not value:
                return ''
            return dict(self._fields[fname].selection).get(value, '')

        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'project_name': self.project_id.name if self.project_id else '',
            # 樣板的「通知編號」——general 的每日編號（如 0722B標QA-施1130919_1）
            'notice_no': self.defect_no or '',
            'defect_no': self.defect_no or '',
            # 樣板的「缺失類別（可複選）」——general 是單選，給其顯示名稱
            'defect_categories': _label('defect_category', self.defect_category),
            'severity': _label('severity', self.severity),
            'description': self.defect_description or '',
            'found_date': self.found_date.strftime('%Y-%m-%d')
                if self.found_date else '',
            'deadline': self.deadline.strftime('%Y-%m-%d')
                if self.deadline else '',
            # 樣板的「負責廠商」——執行改善的施工廠商
            'responsible_company': (self.responsible_company_id.name
                                    if self.responsible_company_id else ''),
            'responsible': (self.responsible_user_id.name
                            if self.responsible_user_id else ''),
            'source_description': self.source_description or '',
        }

# -*- coding: utf-8 -*-
"""construction.meeting.record × doc.linked.mixin（Sprint 24）

第 4 個 host model — 把唯一沒 host 的 dobtor 預設樣板 template_meeting_record
真實接起來，使 4 個樣板引用率達 100%。
"""

from odoo import models, _


class ConstructionMeetingRecord(models.Model):
    _name = 'construction.meeting.record'
    _inherit = ['construction.meeting.record', 'doc.linked.mixin']

    def _doc_default_template_xml_id(self):
        self.ensure_one()
        return 'dobtor_doc_editor.template_meeting_record'

    def _doc_initial_name(self):
        """文件命名：會議名稱 + 日期。"""
        self.ensure_one()
        if self.meeting_date and self.name:
            return '%s（%s）' % (self.name, self.meeting_date)
        return self.name or _('會議記錄')

    def _doc_collaborators(self):
        """主席 + 紀錄人 + 出席者中的 user + 當前 user。

        attendee_ids 是 res.partner 集合，要透過 user_ids 換成 res.users。
        """
        self.ensure_one()
        users = self.env['res.users']
        if self.chairperson_id:
            users |= self.chairperson_id
        if self.recorder_id:
            users |= self.recorder_id
        # res.partner.user_ids 反向走到 res.users
        if self.attendee_ids:
            users |= self.attendee_ids.mapped('user_ids')
        users |= self.env.user
        return users

    def _doc_render_context(self):
        self.ensure_one()
        return {
            'record_id': self.id,
            'record_model': self._name,
            'record_name': self.display_name or '',
            'meeting_name': self.name or '',
            'meeting_date': self.meeting_date.strftime('%Y-%m-%d')
                if self.meeting_date else '',
            'location': self.location or '',
            'chairperson': self.chairperson_id.name if self.chairperson_id else '',
            'recorder': self.recorder_id.name if self.recorder_id else '',
            'attendees': self.attendee_ids.mapped('name'),
            'attendee_count': len(self.attendee_ids),
            'project_name': self.project_id.name if self.project_id else '',
        }

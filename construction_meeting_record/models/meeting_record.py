# -*- coding: utf-8 -*-
"""監造會議記錄（Sprint 24）

ChienYi 系統的會議記錄核心 model，獨立於 dobtor_doc_editor。
裝 dobtor_doc_editor_chienyi bridge 後會自動取得 doc.linked.mixin 能力。
"""

from odoo import models, fields, api, _


class ConstructionMeetingRecord(models.Model):
    _name = 'construction.meeting.record'
    _description = '監造會議記錄'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'meeting_date desc, id desc'

    name = fields.Char(
        string='會議名稱',
        required=True,
        tracking=True,
    )
    meeting_date = fields.Date(
        string='會議日期',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    location = fields.Char(
        string='地點',
        tracking=True,
    )
    chairperson_id = fields.Many2one(
        'res.users',
        string='主席',
        tracking=True,
    )
    recorder_id = fields.Many2one(
        'res.users',
        string='紀錄人',
        default=lambda self: self.env.user,
        tracking=True,
    )
    attendee_ids = fields.Many2many(
        'res.partner',
        string='出席者',
    )
    project_id = fields.Many2one(
        'supervision.project',
        string='關聯工程',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        default=lambda self: self.env.company,
    )
    agenda = fields.Html(
        string='議程',
    )
    note = fields.Text(
        string='備註',
    )
    state = fields.Selection(
        [
            ('draft', '草稿'),
            ('confirmed', '已確認'),
            ('closed', '已結案'),
        ],
        string='狀態',
        default='draft',
        tracking=True,
    )

    @api.depends('meeting_date', 'name')
    def _compute_display_name(self):
        for rec in self:
            if rec.meeting_date and rec.name:
                rec.display_name = '%s（%s）' % (rec.name, rec.meeting_date)
            else:
                rec.display_name = rec.name or _('新會議記錄')

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'
        return True

    def action_close(self):
        for rec in self:
            rec.state = 'closed'
        return True

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
        return True

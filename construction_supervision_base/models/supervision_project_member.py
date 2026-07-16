# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class SupervisionProjectMember(models.Model):
    """工程案件參與成員

    逐帳號決定「哪個帳號可以看到哪個專案」。
    前台可見性 record rule 透過 supervision.project.member_user_ids
    （stored compute）讀取本表，老闆角色除外（走公司範圍）。
    """
    _name = 'supervision.project.member'
    _description = '工程案件參與成員'
    _order = 'project_id, id'

    project_id = fields.Many2one(
        'project.project', string='工程案件',
        required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one(
        'res.users', string='參與帳號',
        required=True, index=True,
        help='被指派可存取本專案的前台帳號')
    note = fields.Char(string='備註')

    _sql_constraints = [
        ('uniq_project_user', 'unique(project_id, user_id)',
         '同一帳號不可重複加入同一專案'),
    ]

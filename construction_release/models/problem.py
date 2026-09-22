# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ConstructionProblem(models.Model):
    _inherit = 'construction.problem'

    # 與更新紀錄的「關聯問題單」是同一張關聯表（反向）
    release_entry_ids = fields.Many2many(
        'construction.release.entry', 'construction_release_entry_problem_rel',
        'problem_id', 'entry_id', string='關聯更新紀錄', groups='base.group_system')
    # 由「問題單 ← 更新紀錄 → 系統版本」自動推得，不能手改；多筆取最新的版本
    fix_release_id = fields.Many2one(
        'construction.release', string='修復版本（系統版本）', compute='_compute_fix_release',
        store=True, compute_sudo=True, readonly=True, index=True)
    fix_release_display = fields.Char(
        string='修復版本', compute='_compute_fix_release_display', compute_sudo=True)

    @api.depends('release_entry_ids.release_id')
    def _compute_fix_release(self):
        for rec in self:
            releases = rec.release_entry_ids.mapped('release_id')
            # id 越大越新（草稿永遠是最新建立的那一版）
            rec.fix_release_id = releases.sorted('id')[-1:] if releases else False

    @api.depends('fix_release_id.state', 'fix_release_id.name', 'fix_release_id.planned_date',
                 'fix_release_id.publish_datetime', 'release_entry_ids')
    def _compute_fix_release_display(self):
        for rec in self:
            rel = rec.fix_release_id
            if not rel:
                rec.fix_release_display = (_('尚未排入版本') if rec.release_entry_ids
                                           else _('沒有關聯的更新紀錄'))
            elif rel.state == 'draft':
                rec.fix_release_display = (
                    _('下一版（草稿，預計 %s）', rel.planned_date.strftime('%m/%d'))
                    if rel.planned_date else _('下一版（草稿，未定預計發布日）'))
            elif rel.state == 'confirmed':
                rec.fix_release_display = _('%s（已確認，尚未發布）', rel.name)
            else:
                local = fields.Datetime.context_timestamp(rec, rel.publish_datetime)
                rec.fix_release_display = _('%(n)s（已發布 %(d)s）', n=rel.name, d=local.strftime('%m/%d'))

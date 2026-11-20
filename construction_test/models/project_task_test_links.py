# -*- coding: utf-8 -*-
"""2026-11-20：檢試驗項目「關聯契約工項」（supervision.test.standard.task_ids，多選）算引用。

- 刪契約工項：還有檢試驗項目連到它就擋，列出是哪幾筆（整個工程要刪時不算，見 unlinking_project_ids）。
- 標單匯入精靈覆蓋前的引用檢查：併進 _extra_task_reference_hits。
- 精靈上的「清除這些連結」：先列出會受影響的檢試驗項目與檢試驗紀錄，確認後才清，並在檢試驗項目的
  chatter 留紀錄。只在精靈上加兩個欄位，不新增資料表。
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

LIST_LIMIT = 10


def _standards_linked(env, tasks):
    """連到這些工項的檢試驗項目（含封存的；sudo 只用來找）"""
    if not tasks:
        return env['supervision.test.standard']
    return env['supervision.test.standard'].sudo().with_context(active_test=False).search(
        [('task_ids', 'in', tasks.ids)])


def _label(rec):
    # 檢試驗項目的 display_name 是材料名稱，列出時要看得出是哪一筆項目
    if rec._name == 'supervision.test.standard':
        return '%s（%s）' % (rec.name, rec.material) if rec.material and rec.material != rec.name else rec.name
    return rec.display_name


def _names(records, limit=LIST_LIMIT):
    names = [_label(r) for r in records[:limit]]
    if len(records) > limit:
        names.append('…等 %d 筆' % len(records))
    return '、'.join(names)


class ProjectTaskTestLinks(models.Model):
    _inherit = 'project.task'

    @api.model
    def _extra_task_reference_hits(self, tasks):
        hits = super()._extra_task_reference_hits(tasks)
        standards = _standards_linked(self.env, tasks)
        if standards:
            hits.append(('檢試驗項目的「關聯契約工項」（%s）' % _names(standards), len(standards)))
        return hits

    def unlink(self):
        standards = _standards_linked(self.env, self)
        skip = set(self.env.context.get('unlinking_project_ids') or [])
        standards = standards.filtered(lambda s: s.project_id.id not in skip)
        if standards:
            raise UserError(
                '下列檢試驗項目的「關聯契約工項」還連到要刪除的工項，不能刪：\n%s\n'
                '請先到這些檢試驗項目取消關聯（或在標單匯入精靈按「清除這些連結」）再刪。'
                % '\n'.join('- %s：%s' % (_label(s), _names(s.task_ids & self)) for s in standards))
        return super().unlink()


class TenderImportWizardTestLinks(models.TransientModel):
    _inherit = 'tender.import.wizard'

    test_link_detail = fields.Text(
        string='會受影響的檢試驗資料', readonly=True,
        help='按「清除這些連結」時列出；確認後才會真的清除')
    has_test_links = fields.Boolean(compute='_compute_has_test_links')

    @api.depends('project_id', 'state', 'existing_task_count')
    def _compute_has_test_links(self):
        for wiz in self:
            wiz.has_test_links = bool(wiz.existing_task_count and _standards_linked(
                self.env, wiz._existing_tasks()))

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'name': '匯入契約標單', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def action_preview_clear_test_links(self):
        """第一步：列出會受影響的檢試驗項目與檢試驗紀錄（還沒清）"""
        self.ensure_one()
        tasks = self._existing_tasks()
        standards = _standards_linked(self.env, tasks)
        if not standards:
            raise UserError('沒有檢試驗項目連到這個工程的契約工項。')
        records = self.env['supervision.test.record'].sudo().search(
            [('standard_id', 'in', standards.ids)])
        lines = ['確認後會把下列檢試驗項目的「關聯契約工項」中，屬於本工程的工項清掉：']
        for s in standards:
            lines.append('・%s：%s' % (_label(s), _names(s.task_ids & tasks)))
        lines.append('')
        lines.append('這些檢試驗項目底下的檢試驗紀錄 %d 筆（紀錄本身不刪；累計進場量、應檢次數會跟著變）%s'
                     % (len(records), ('：' + _names(records)) if records else ''))
        self.test_link_detail = '\n'.join(lines)
        return self._reopen()

    def action_clear_test_links(self):
        """第二步：確認後才清除，並在 chatter 留紀錄，再重新預覽"""
        self.ensure_one()
        if not self.test_link_detail:
            raise UserError('請先按「清除這些連結」看過會受影響的資料，再確認清除。')
        tasks = self._existing_tasks()
        for s in _standards_linked(self.env, tasks):
            removed = s.task_ids & tasks
            s.write({'task_ids': [(3, t.id) for t in removed]})
            s.message_post(body=_('重匯標單前清除「關聯契約工項」%(n)d 個：%(names)s',
                                  n=len(removed), names=_names(removed, limit=50)))
        self.test_link_detail = False
        return self.action_preview()

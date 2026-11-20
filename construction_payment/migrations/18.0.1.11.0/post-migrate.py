# -*- coding: utf-8 -*-
"""實際請款金額改用已核定／已歸檔估驗的本次估驗金額加總：重算全部契約工項。

actual_amount、completion_rate、qty_remaining、budget_status 是 stored compute，改公式之後 -u 不會
自己重算（只有欄位剛建立時才算），所以這裡排進重算佇列、flush 落庫。工程上的 actual_cost、
budget_usage_rate 由 actual_amount 推得，一起排。沒有核定估驗的工程，實際請款金額會變 0（使用者同意）。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    Task = env['project.task']
    cr.execute("SELECT COALESCE(SUM(actual_amount), 0) FROM project_task WHERE parent_id IS NULL")
    before = cr.fetchone()[0]
    tasks = Task.search([])
    for fname in ('actual_amount', 'completion_rate', 'qty_remaining', 'budget_status'):
        env.add_to_compute(Task._fields[fname], tasks)
    Project = env['project.project']
    projects = Project.search([])
    for fname in ('actual_cost', 'budget_usage_rate'):
        if fname in Project._fields and Project._fields[fname].store and Project._fields[fname].compute:
            env.add_to_compute(Project._fields[fname], projects)
    env.flush_all()
    cr.execute("SELECT COALESCE(SUM(actual_amount), 0) FROM project_task WHERE parent_id IS NULL")
    after = cr.fetchone()[0]
    _logger.info('實際請款金額改用估驗：重算工項 %d 筆、工程 %d 個；頂層工項實際請款金額合計 %s → %s',
                 len(tasks), len(projects), before, after)

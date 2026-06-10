# -*- coding: utf-8 -*-

from odoo import fields


def _mark_existing_standard_work_items(env):
    """將現有 product_id 有值的 project.task 所對應的 product 標記為標準工項"""
    env.cr.execute("""
        UPDATE product_template pt
        SET is_standard_work_item = true
        FROM product_product pp
        WHERE pt.id = pp.product_tmpl_id
          AND pp.id IN (
              SELECT DISTINCT product_id FROM project_task WHERE product_id IS NOT NULL
          )
          AND pt.is_standard_work_item = false
    """)


def post_migrate(env):
    """為所有尚未有版本記錄的既有工項建立 v1；標記現有標準工項 product"""
    _mark_existing_standard_work_items(env)

    tasks = env['project.task'].search([
        ('version_ids', '=', False),
        ('is_summary_item', '=', False),
        ('planned_qty', '>', 0),
    ])

    if not tasks:
        return

    version_vals = []
    for task in tasks:
        # 若曾經歷變更，original_planned_qty 才是真正的原始契約數量
        v1_qty = task.original_planned_qty if task.original_planned_qty else task.planned_qty
        version_vals.append({
            'task_id': task.id,
            'version': 1,
            'planned_qty': v1_qty,
            'unit_price': task.unit_price,
            'change_date': task.create_date.date() if task.create_date else fields.Date.today(),
            'change_reason': '原始契約（遷移）',
        })

    env['project.task.version'].create(version_vals)

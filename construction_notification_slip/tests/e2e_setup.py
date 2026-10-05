# -*- coding: utf-8 -*-
"""停工／退單的瀏覽器與 HTTP 端到端驗證 —— 準備（會 commit）。跑完一定要執行 e2e_cleanup.py。

建兩個臨時帳號（前台老闆、後台工程人員，密碼隨機產生、只寫在容器的 /tmp/e2e_slip.json）
與 DEMO-2026-003 底下五張測試通報單（slip_no 951～954，954 有兩張：退單＋重開）：
  951 停工中　952 合併目標　953 合併退單（併入 952）　954 退單 → 954 重開　955 施工中（給後台點按鈕）
"""
import json
import secrets
from datetime import timedelta

from odoo import Command, fields

project = env['project.project'].search([('code', '=', 'DEMO-2026-003')], limit=1)
task = env['project.task'].search([
    ('supervision_project_id', '=', project.id), ('is_summary_item', '=', False),
    ('unit_price', '>', 0)], limit=1)
today = fields.Date.context_today(env['reservation.notification.slip'])
Slip = env['reservation.notification.slip']


def mk(no, loc):
    return Slip.create({
        'project_id': project.id, 'slip_no': no, 'location': f'[E2E] {loc}',
        'planned_start_date': today - timedelta(days=10), 'planned_duration': 14,
        'detail_line_ids': [Command.create({
            'task_id': task.id, 'item_no': task.display_item_no or 'T1',
            'unit': task.unit or '式', 'unit_price': task.unit_price, 'planned_qty': 2})],
    })


s951 = mk(951, '停工中')
s951.action_confirm()
s951.write({'actual_start_date': today - timedelta(days=10)})
s951.action_start()
s951.action_suspend(today - timedelta(days=3), '機關通知暫停施工（E2E）')

s952 = mk(952, '合併目標')
s952.action_confirm()

s953 = mk(953, '合併退單')
s953.action_confirm()
s953.action_cancel_slip('merge', today, '併入第 952 次（E2E）', s952.id)

s954 = mk(954, '退單')
s954.action_cancel_slip('return', today, '工項價格有問題（E2E）')
s954b = mk(954, '同次重開')

s955 = mk(955, '施工中（後台點按鈕）')
s955.action_confirm()
s955.write({'actual_start_date': today - timedelta(days=5)})
s955.action_start()

pw_portal = secrets.token_urlsafe(12)
pw_back = secrets.token_urlsafe(12)
company = env['res.partner'].create({'name': 'ZZ E2E 退單停工', 'is_company': True})
portal_user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'ZZ E2E 前台老闆', 'login': 'zz_e2e_slip_portal', 'password': pw_portal,
    'parent_id': company.id,
    'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                          env.ref('construction_supervision_base.group_portal_subscriber').id])],
})
back_user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'ZZ E2E 後台', 'login': 'zz_e2e_slip_back', 'password': pw_back,
    'groups_id': [(6, 0, [env.ref('base.group_user').id,
                          env.ref('construction_supervision_base.group_supervisor_admin').id,
                          # 前台詳情頁的核定／結案按鈕只給老闆／主管／系統管理者看
                          env.ref('base.group_system').id])],
})
env.cr.commit()
json.dump({
    'project_id': project.id,
    'slips': {'951': s951.id, '952': s952.id, '953': s953.id, '954': s954.id,
              '954b': s954b.id, '955': s955.id},
    'portal': {'login': portal_user.login, 'pw': pw_portal, 'uid': portal_user.id},
    'back': {'login': back_user.login, 'pw': pw_back, 'uid': back_user.id},
    'company': company.id,
}, open('/tmp/e2e_slip.json', 'w'))
print('SETUP OK project=%s slips=%s' % (project.id, [s951.id, s952.id, s953.id, s954.id, s954b.id, s955.id]))

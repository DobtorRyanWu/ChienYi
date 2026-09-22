# -*- coding: utf-8 -*-
"""後台跳窗／橫幅的瀏覽器驗證前置（會 commit；跑完用 e2e_cleanup.py 清）。

建一個臨時內部帳號，再發布一個帶公告的版本（帳號要先建立，公告才會跳給它）。
"""
import json

from datetime import timedelta

from odoo import fields

LOGIN = 'zz_release_backend'
PW = 'zzReleaseBack!2026'

admin = env.ref('base.user_admin')
user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'ZZ 後台測試（版本公告）', 'login': LOGIN, 'password': PW,
    'groups_id': [(6, 0, [env.ref('base.group_user').id])],
})
env.cr.commit()  # 先讓帳號的建立時間落地，之後發布的公告才會跳給它

Rel = env['construction.release'].with_user(admin)
pay = env['ir.module.module'].search([('name', '=', 'construction_payment')])
rel = Rel.create({'planned_date': fields.Date.context_today(Rel)})
env['construction.release.entry'].with_user(admin).create({
    'entry_type': 'feature', 'title': 'ZZ 後台公告測試', 'reason': 'E2E 原因',
    'change': 'ZZ 後台跳窗測試：同日多期估驗的累計會正確加總',
    'method': 'E2E 做法', 'commits': '07258fb', 'announce': 'yes',
    'line_ids': [(0, 0, {'module_id': pay.id, 'version_before': '18.0.1.8.0',
                         'version_after': '18.0.1.8.1'})],
})
rel.action_pull_entries()
wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(
    rel.action_open_confirm_wizard()['res_id'])
wiz.action_confirm()
rel.action_generate_announcement()
now = fields.Datetime.now()
rel.write({'maint_start': now, 'maint_end': now + timedelta(hours=2)})
rel.action_maint_announce()
rel.action_check_deployment()
rel.action_publish()

json.dump({'login': LOGIN, 'pw': PW, 'release_id': rel.id, 'version': rel.name,
           'user_id': user.id}, open('/tmp/e2e_release.json', 'w'))
env.cr.commit()
print('BACKEND SETUP OK version=%s user=%s state=%s' % (rel.name, user.id, rel.state))

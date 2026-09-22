# -*- coding: utf-8 -*-
"""HTTP 端到端測試的前置（會 commit，測完務必跑 e2e_cleanup.py）。

造：臨時前台帳號 ＋ 一個已確認且發布維護預告的系統版本（尚未發布）。
"""
import json

from odoo import fields
from datetime import timedelta

LOGIN = 'zz_release_portal'
PW = 'zzReleaseE2E!2026'

admin = env.ref('base.user_admin')
Rel = env['construction.release'].with_user(admin)
Entry = env['construction.release.entry'].with_user(admin)
pay = env['ir.module.module'].search([('name', '=', 'construction_payment')])

user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'ZZ 前台測試（版本公告）',
    'login': LOGIN,
    'password': PW,
    'groups_id': [(6, 0, [env.ref('base.group_portal').id])],
})

rel = Rel.create({'planned_date': fields.Date.context_today(Rel)})
Entry.create({
    'entry_type': 'feature', 'title': 'ZZ E2E 公告測試', 'reason': 'E2E 原因',
    'change': 'ZZ 端到端測試用的公告內容：多期估驗累計會正確加總',
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

json.dump({'login': LOGIN, 'pw': PW, 'release_id': rel.id, 'version': rel.name,
           'user_id': user.id, 'entry_ids': rel.entry_ids.ids},
          open('/tmp/e2e_release.json', 'w'))
env.cr.commit()
print('SETUP OK release=%s version=%s user=%s' % (rel.id, rel.name, user.id))

# -*- coding: utf-8 -*-
"""HTTP 端到端測試 —— 準備（會 commit）：建臨時前台帳號。跑完一定要執行 e2e_portal_cleanup.py。"""
import json
import secrets

pw = secrets.token_urlsafe(16)
company = env['res.partner'].create({'name': 'ZZ E2E 營造', 'is_company': True})
user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'ZZ E2E 前台', 'login': 'zz_e2e_portal', 'password': pw, 'parent_id': company.id,
    'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                          env.ref('construction_supervision_base.group_portal_subscriber').id])],
})
# 別人（客服）建的單：驗證前台看不到
other = env['construction.service.ticket'].with_user(env.ref('base.user_admin')).create({
    'subject': 'ZZ E2E 客服代登記（前台不該看到）', 'channel': 'phone'})
project = env['project.project'].search([], limit=1)
env.cr.commit()
json.dump({'login': 'zz_e2e_portal', 'pw': pw, 'uid': user.id, 'company': company.id,
           'other_ticket': other.id, 'project_id': project.id, 'project_name': project.name,
           'project_code': project.code or '',
           'payment_module_id': env.ref('construction_helpdesk.module_payment').id},
          open('/tmp/e2e_helpdesk.json', 'w'))
print('SETUP OK uid=%s project=%s' % (user.id, project.id))

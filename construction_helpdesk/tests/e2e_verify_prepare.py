# -*- coding: utf-8 -*-
"""HTTP 端到端（2.0.0 客戶驗證）—— 準備（會 commit）。

在 e2e_portal_http.py 之後、e2e_portal_cleanup.py 之前執行：
把前台送出的兩張單轉成同一張問題單（P3）、部署、請客戶驗證，讓前台出現「問題已解決／仍有問題」按鈕。
"""
import json

cfg = json.load(open('/tmp/e2e_helpdesk.json'))
out = json.load(open('/tmp/e2e_helpdesk_out.json'))
agent = env.ref('base.user_admin')
T = env['construction.service.ticket'].with_user(agent)
t1, t2 = T.browse(out['tid']), T.browse(out['tid2'])
cat_sys = env.ref('construction_helpdesk.category_system_problem')
(t1 | t2).write({'category_id': cat_sys.id})
wiz = env['construction.problem.link.wizard'].with_user(agent).with_context(default_ticket_id=t1.id).create(
    {'mode': 'new', 'title': 'ZZ E2E 驗證用問題單'})
problem = env['construction.problem'].browse(wiz.action_confirm()['res_id'])
wiz2 = env['construction.problem.link.wizard'].with_user(agent).with_context(default_ticket_id=t2.id).create(
    {'mode': 'link', 'problem_id': problem.id})
wiz2.action_confirm()
problem.with_user(agent).write({'severity': 's3', 'urgency': 'u2'})    # P3
problem.with_user(agent).action_to_deploy()
problem.with_user(agent).action_to_verify()
(t1 | t2).action_wait_verify()
env.cr.commit()
out['problem_id'] = problem.id
json.dump(out, open('/tmp/e2e_helpdesk_out.json', 'w'))
print('VERIFY PREPARE OK problem=%s states=%s' % (problem.name, (t1.state, t2.state)))

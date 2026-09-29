# -*- coding: utf-8 -*-
"""瀏覽器驗收 F～J 用的測試資料（會 commit）。跑完一定要執行 ui_fj_cleanup.py。

標題一律以「ZZ UI」開頭。
"""
import json

agent = env.ref('base.user_admin')
T = env['construction.service.ticket'].with_user(agent)
P = env['construction.problem'].with_user(agent)
cat_sys = env.ref('construction_helpdesk.category_system_problem')
mod_pay = env.ref('construction_helpdesk.module_payment')
seq_t = env.ref('construction_helpdesk.seq_service_ticket')
seq_p = env.ref('construction_helpdesk.seq_problem')
before = {'seq_t': seq_t.number_next_actual, 'seq_p': seq_p.number_next_actual}


def ticket_problem(title, s, u, **extra):
    t = T.create({'subject': title, 'channel': 'internal', 'category_id': cat_sys.id,
                  'functional_module_id': mod_pay.id})
    wiz = env['construction.problem.link.wizard'].with_user(agent).with_context(
        default_ticket_id=t.id).create({'mode': 'new', 'title': title})
    p = env['construction.problem'].browse(wiz.action_confirm()['res_id'])
    vals = {'severity': s, 'urgency': u}
    vals.update(extra)
    p.with_user(agent).write(vals)
    return t, p


def deploy(p):
    p.with_user(agent).action_to_deploy()
    p.with_user(agent).action_to_verify()


# F：P1、已部署、服務單在待客戶驗證、客戶還沒回
tF, pF = ticket_problem('ZZ UI F 結案訊息', 's1', 'u1')
deploy(pF)
tF.action_wait_verify()
# G：P1（試不處理被擋）、P3（併入主單）、P3 主單
tG1, pG1 = ticket_problem('ZZ UI G1 P1 不處理', 's1', 'u1')
tG3, pG3 = ticket_problem('ZZ UI G3 重複的單', 's3', 'u2')
tGm, pGm = ticket_problem('ZZ UI G 主單', 's3', 'u2')
# H：資安
tH, pH = ticket_problem('ZZ UI H 資安', 's4', 'u3', special_security=True)
# I：P1 已部署（資料盤修）
tI, pI = ticket_problem('ZZ UI I 資料盤修', 's1', 'u2')
deploy(pI)

env.cr.commit()
ids = {'tickets': (tF | tG1 | tG3 | tGm | tH | tI).ids,
       'problems': (pF | pG1 | pG3 | pGm | pH | pI).ids,
       'F': pF.id, 'G1': pG1.id, 'G3': pG3.id, 'Gm': pGm.id, 'H': pH.id, 'I': pI.id, 'tF': tF.id}
ids.update(before)
json.dump(ids, open('/tmp/ui_fj.json', 'w'))
print('UI SETUP OK', {k: v for k, v in ids.items() if k not in ('tickets', 'problems')},
      [(p.name, p.title, p.final_priority, p.state) for p in env['construction.problem'].browse(ids['problems'])])

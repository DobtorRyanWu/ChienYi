# -*- coding: utf-8 -*-
"""HTTP 端到端測試 —— 驗 DB 結果並清理（會 commit）。一定要在 e2e_portal_setup.py 之後執行。"""
import json
import os

cfg = json.load(open('/tmp/e2e_helpdesk.json'))
out = json.load(open('/tmp/e2e_helpdesk_out.json')) if os.path.exists('/tmp/e2e_helpdesk_out.json') else {}
T = env['construction.service.ticket'].sudo()
results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


user = env['res.users'].sudo().browse(cfg['uid'])
t1 = T.browse(out.get('tid') or 0).exists()
t2 = T.browse(out.get('tid2') or 0).exists()
if t1:
    check('DB：管道＝前台、狀態＝新建、建單人＝前台帳號',
          t1.channel == 'portal' and t1.state == 'new' and t1.create_uid == user)
    check('DB：硬塞後台專用的「估驗計價」被丟掉（系統問題類）', not t1.functional_module_id,
          t1.functional_module_id.name)
    check('DB：工程名稱／代號自動帶入', t1.project_name == cfg['project_name']
          and (t1.project_code or '') == cfg['project_code'], (t1.project_name, t1.project_code))
    check('DB：客戶公司（文字）＝前台帳號所屬公司名稱、聯絡人＝本人姓名',
          t1.customer_company == 'ZZ E2E 營造' and t1.contact_name == user.name,
          (t1.customer_company, t1.contact_name))
    check('DB：附件以留言形式掛在單上', t1.message_ids.mapped('attachment_ids').mapped('name') == ['screen.png'],
          t1.message_ids.mapped('attachment_ids').mapped('name'))
    check('DB：前台帳號不是追蹤者（不寄 Email）', user.partner_id not in t1.message_partner_ids)
    check('DB：說明是純文字轉 HTML，<script> 已跳脫', '<script>' not in (t1.description or ''))
if t2:
    check('DB：操作疑問＋施工日誌 → 發生功能有保留', t2.functional_module_id.name == '施工日誌')

# ---------- 清理 ----------
tickets = (t1 | t2 | T.browse(cfg['other_ticket']).exists())
tickets.unlink()
# 系統既有行為：建立使用者（含前台帳號）時會自動建一筆員工資料，它會以 RESTRICT 擋住刪除使用者
if 'hr.employee' in env:
    env['hr.employee'].sudo().with_context(active_test=False).search([('user_id', '=', user.id)]).unlink()
user_partner = user.partner_id
user.unlink()
# 刪使用者不會連帶刪掉他自己的聯絡人，要另外刪
(user_partner | env['res.partner'].sudo().browse(cfg['company'])).exists().unlink()
remaining = T.with_context(active_test=False).search_count([])
seq = env.ref('construction_helpdesk.seq_service_ticket')
# 單號序號退回「現存最大單號＋1」：測試單用掉的號碼收回來，但不能跟使用者自己建的單撞號
existing = [int(n.split('-')[-1]) for n in T.with_context(active_test=False).search([]).mapped('name')
            if n.split('-')[-1].isdigit()]
seq.sudo().write({'number_next': (max(existing) + 1) if existing else 1})
env.cr.commit()
check('清理：測試單、帳號、公司皆已刪除', not tickets.exists() and not user.exists())
check('清理：測試單已刪、單號序號退回現存最大單號＋1',
      seq.number_next_actual == ((max(existing) + 1) if existing else 1),
      (remaining, seq.number_next_actual))
for f in ('/tmp/e2e_helpdesk.json', '/tmp/e2e_helpdesk_out.json'):
    if os.path.exists(f):
        os.remove(f)
ok = sum(1 for x in results if x[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== DB＋清理 %d/%d 通過 ====' % (ok, len(results)))

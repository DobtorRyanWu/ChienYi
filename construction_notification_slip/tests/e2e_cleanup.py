# -*- coding: utf-8 -*-
"""停工／退單端到端驗證 —— 清理（會 commit）。一定要在 e2e_setup.py 之後執行。

刪掉測試通報單（含明細、停工紀錄、chatter）、兩個臨時帳號（員工→使用者→partner 三步），
並把通報單編號序號退回「現存最大號」。
"""
import json

cfg = json.load(open('/tmp/e2e_slip.json'))
Slip = env['reservation.notification.slip'].sudo()
slips = Slip.search([('project_id', '=', cfg['project_id']), ('slip_no', 'in', [951, 952, 953, 954, 955])])
slips = slips.filtered(lambda s: (s.location or '').startswith('[E2E]'))
# 退單／施工中的通報單模型不准刪（編號保留）—— 測試資料用 SQL 退回草稿再刪。
# 分兩批：同一個次數有「退單＋重開」兩張時，同時改成草稿會撞部分唯一索引，
# 所以先刪未退單的，再刪退單的。
n = len(slips)
env.cr.execute("UPDATE reservation_notification_slip SET merged_into_slip_id=NULL "
               "WHERE id IN %s", (tuple(slips.ids or [0]),))
for batch in (slips.filtered(lambda s: s.state != 'cancelled'),
              slips.filtered(lambda s: s.state == 'cancelled')):
    if batch:
        env.cr.execute("UPDATE reservation_notification_slip SET state='draft', cancel_reason=NULL "
                       "WHERE id IN %s", (tuple(batch.ids),))
        env.invalidate_all()
        batch.unlink()

users = env['res.users'].sudo().with_context(active_test=False).browse(
    [cfg['portal']['uid'], cfg['back']['uid']]).exists()
partners = users.mapped('partner_id') | env['res.partner'].sudo().browse(cfg['company']).exists()
if 'hr.employee' in env:
    env['hr.employee'].sudo().with_context(active_test=False).search(
        [('user_id', 'in', users.ids)]).unlink()
users.unlink()
partners.exists().unlink()

seq = env.ref('construction_notification_slip.seq_reservation_notification_slip')
env.cr.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(slip_number, '^.*-', ''), '')::int), 0)
                    FROM reservation_notification_slip WHERE slip_number ~ '-[0-9]+$'""")
max_no = env.cr.fetchone()[0]
if seq.implementation == 'standard' and max_no:
    env.cr.execute("SELECT setval('ir_sequence_%03d', %%s, true)" % seq.id, (max_no,))
env.cr.commit()
left = Slip.search_count([('location', '=like', '[E2E]%')])
print('CLEANUP OK slips_deleted=%s users_deleted=%s left_e2e_slips=%s seq=%s'
      % (n, len(users), left, max_no))

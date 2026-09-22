# -*- coding: utf-8 -*-
"""端到端測試的清理（會 commit）：刪掉測試版本、更新紀錄、部署紀錄與臨時帳號。

⚠️ 三個坑：①已發布的版本不能刪、部署紀錄不能刪 → 這裡用 SQL；
          ②建使用者會自動建 hr.employee（RESTRICT 擋刪）；
          ③刪使用者不會刪它的 partner。
"""
import json
import os

cfg = json.load(open('/tmp/e2e_release.json'))
rid, uid = cfg['release_id'], cfg['user_id']
cr = env.cr

cr.execute("DELETE FROM mail_tracking_value WHERE mail_message_id IN "
           "(SELECT id FROM mail_message WHERE model IN "
           "('construction.release','construction.release.entry'))")
cr.execute("DELETE FROM mail_message WHERE model IN "
           "('construction.release','construction.release.entry')")
cr.execute("DELETE FROM mail_followers WHERE res_model IN "
           "('construction.release','construction.release.entry')")
cr.execute("DELETE FROM construction_release_entry_problem_rel")
cr.execute("DELETE FROM construction_release_entry")
cr.execute("DELETE FROM construction_deployment")
cr.execute("DELETE FROM construction_release_read_user_rel")
cr.execute("DELETE FROM construction_release")
cr.execute("UPDATE ir_sequence SET number_next = 1 WHERE code = 'construction.release.entry'")

user = env['res.users'].browse(uid).exists()
if user:
    partner = user.partner_id
    env['hr.employee'].sudo().with_context(active_test=False).search(
        [('user_id', '=', uid)]).unlink()
    user.unlink()
    if partner.exists():
        partner.unlink()

env.cr.commit()
if os.path.exists('/tmp/e2e_release.json'):
    os.remove('/tmp/e2e_release.json')
print('CLEANUP OK 版本 %d 更新紀錄 %d 部署 %d 帳號 %d' % (
    env['construction.release'].search_count([]),
    env['construction.release.entry'].search_count([]),
    env['construction.deployment'].search_count([]),
    env['res.users'].search_count([('login', '=', cfg['login'])])))

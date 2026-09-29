# -*- coding: utf-8 -*-
"""清掉 ui_fj_setup.py 建的測試資料（會 commit），單號序號退回建立前的值。"""
import json
import os

ids = json.load(open('/tmp/ui_fj.json'))
T = env['construction.service.ticket'].sudo()
P = env['construction.problem'].sudo()
problems = P.browse(ids['problems']).exists()
# 瀏覽器操作時上傳的附件也一起清掉
atts = env['ir.attachment'].sudo().search([
    '|', '&', ('res_model', '=', 'construction.problem'), ('res_id', 'in', ids['problems']),
    '&', ('res_model', '=', 'construction.service.ticket'), ('res_id', 'in', ids['tickets'])])
T.browse(ids['tickets']).exists().unlink()
problems.unlink()
atts.exists().unlink()
env.ref('construction_helpdesk.seq_service_ticket').sudo().write({'number_next': ids['seq_t']})
env.ref('construction_helpdesk.seq_problem').sudo().write({'number_next': ids['seq_p']})
env.cr.commit()
left = P.search_count([('title', 'like', 'ZZ UI')]) + T.search_count([('subject', 'like', 'ZZ UI')])
print('UI CLEANUP OK, 殘留 %s 筆, 序號 SRV→%s PRB→%s' % (left, ids['seq_t'], ids['seq_p']))
os.remove('/tmp/ui_fj.json')

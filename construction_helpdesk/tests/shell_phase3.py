# -*- coding: utf-8 -*-
"""第三、四階段驗收：系統問題單、分級、時限、兩個對話框、統計（odoo shell，全程 rollback）。

echo 'exec(open("/mnt/extra-addons/construction_helpdesk/tests/shell_phase3.py", encoding="utf-8").read())' \
  | odoo shell -d system_development ... --no-http
"""
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, exc, fn):
    # 包 savepoint：被擋下的寫入不能殘留在 ORM 快取裡（實際使用時整個請求會 rollback）
    try:
        with env.cr.savepoint():
            fn()
    except exc as e:
        results.append((True, name, type(e).__name__))
        return
    except Exception as e:
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


def tw(y, m, d, hh=10):
    """台灣時間 → Odoo 存的 UTC naive datetime。"""
    return datetime(y, m, d, hh) - timedelta(hours=8)


T = 'construction.service.ticket'
P = 'construction.problem'

env.cr.execute('SAVEPOINT helpdesk_p3')
try:
    u_agent = env.ref('base.user_admin')
    u_op = env['res.users'].browse(6)
    Ta = env[T].with_user(u_agent)
    # 測試用預設值（rollback，不影響使用者在後台改過的數字）
    env.ref('construction_helpdesk.sla_p1').write({'default_fix_days': 2})
    env.ref('construction_helpdesk.sla_p2').write({'default_fix_days': 5})
    Pa = env[P].with_user(u_agent)
    cat_sys = env.ref('construction_helpdesk.category_system_problem')
    cat_q = env.ref('construction_helpdesk.category_operation_question')
    mod_pay = env.ref('construction_helpdesk.module_payment')
    mod_log = env.ref('construction_helpdesk.module_daily_log')
    pa, pb = 'ZZ 甲營造', 'ZZ 乙營造'

    def link_new(ticket, title=None):
        wiz = env['construction.problem.link.wizard'].with_user(u_agent).with_context(
            default_ticket_id=ticket.id).create({'mode': 'new', 'title': title or ticket.subject})
        action = wiz.action_confirm()
        return env[P].browse(action['res_id'])

    # ================= 轉問題單 =================
    t1 = env[T].with_user(u_op).create({
        'subject': 'ZZ 估驗金額算錯', 'report_datetime': tw(2026, 9, 26),   # 週六
        'functional_module_id': mod_pay.id})
    t1.with_user(u_agent).write({'category_id': cat_sys.id, 'customer_company': False})
    raises('代操作員無法轉問題單', AccessError,
           lambda: env['construction.problem.link.wizard'].with_user(u_op).create({'ticket_id': t1.id}))
    t_q = Ta.create({'subject': 'ZZ 操作疑問', 'channel': 'phone', 'category_id': cat_q.id})
    raises('非系統問題類別不能轉問題單', UserError, lambda: t_q.action_open_link_problem())

    prb = link_new(t1)
    check('轉問題單：新建問題單、單號 PRB-', prb.name.startswith('PRB-'), prb.name)
    check('轉問題單：服務單改為處理中並關聯', t1.state == 'processing' and t1.problem_id == prb)
    check('新問題單：待分級、S／U／P 全空',
          prb.state == 'pending_grade' and not prb.severity and not prb.urgency and not prb.final_priority)
    check('起算日＝服務單回報日（台灣時間 2026-09-26）', prb.start_date == date(2026, 9, 26), prb.start_date)
    raises('代操作員讀不到問題單', AccessError, lambda: prb.with_user(u_op).read(['title']))
    raises('代操作員讀不到服務單的關聯問題單欄位', AccessError, lambda: t1.with_user(u_op).read(['problem_id']))

    # ================= 分級 =================
    prb.with_user(u_agent).write({'severity': 's1'})
    check('只判 S、沒判 U → 沒有 P、未分級', not prb.final_priority and not prb.graded_datetime)
    prb.with_user(u_agent).write({'urgency': 'u2'})
    check('S1×U2 → 查表 P1', prb.matrix_priority == 'p1' and prb.final_priority == 'p1')
    check('分級完成：記下分級時間、狀態 → 處理中', prb.graded_datetime and prb.state == 'processing')
    check('計算基準日＝起算日、預期工作天數＝P1 預設 2、掛非工作日待確認',
          prb.base_date == date(2026, 9, 26) and prb.expected_work_days == 2 and prb.non_working_to_confirm)
    check('基準日顯示星期', prb.base_date_label == '2026-09-26（六）', prb.base_date_label)
    prb.with_user(u_agent).write({'non_working_days': 1})
    check('週六回報、P1、非工作日 1 → 預定修復日＝週二 9/29', prb.planned_fix_date == date(2026, 9, 29), prb.planned_fix_date)
    check('輸入非工作日天數後，待確認自動清除', not prb.non_working_to_confirm)
    raises('分級後直接改 S 被擋（要走變更等級）', UserError, lambda: prb.with_user(u_agent).write({'severity': 's2'}))
    raises('分級後直接勾特例被擋', UserError, lambda: prb.with_user(u_agent).write({'special_repeat': True}))

    # 分級標準第七節另外兩個例子：週五、週一回報
    def graded_problem(report_dt, s, u, nonwork, partner=False, module=mod_pay, **extra):
        t = Ta.create({'subject': 'ZZ 例', 'channel': 'phone', 'category_id': cat_sys.id,
                       'report_datetime': report_dt, 'functional_module_id': module.id,
                       'customer_company': partner or False})
        p = link_new(t)
        vals = {'severity': s, 'urgency': u}
        vals.update(extra)
        p.with_user(u_agent).write(vals)
        if nonwork is not None:
            p.with_user(u_agent).write({'non_working_days': nonwork})
        return p, t

    p_fri, _t = graded_problem(tw(2026, 9, 25), 's1', 'u1', 2)
    check('週五回報、非工作日 2 → 週二 9/29', p_fri.planned_fix_date == date(2026, 9, 29), p_fri.planned_fix_date)
    p_mon, _t = graded_problem(tw(2026, 9, 28), 's1', 'u1', 0)
    p_mon.with_user(u_agent).action_confirm_non_working_days()
    check('週一回報、非工作日 0 → 週三 9/30；按確認清除待確認',
          p_mon.planned_fix_date == date(2026, 9, 30) and not p_mon.non_working_to_confirm)
    # 台灣時間凌晨（UTC 前一天）也要算成台灣的日期
    p_tz, _t = graded_problem(datetime(2026, 9, 27, 17, 30), 's3', 'u3', None)   # UTC 9/27 17:30 ＝ 台灣 9/28 01:30
    check('起算日依台灣時間換日（UTC 9/27 17:30 → 9/28）', p_tz.start_date == date(2026, 9, 28), p_tz.start_date)

    # ================= 特例 =================
    p_sp, _t = graded_problem(tw(2026, 9, 21), 's3', 'u2', None)
    check('S3×U2 → P3、沒有預定修復日、不判逾時',
          p_sp.final_priority == 'p3' and not p_sp.planned_fix_date and not p_sp.is_overdue
          and not p_sp.non_working_to_confirm)
    p_x, _t = graded_problem(tw(2026, 9, 21), 's3', 'u2', None, special_external_doc=True)
    check('特例：流入對外文件 → 升一級 P2', p_x.final_priority == 'p2', p_x.final_priority)
    p_xx, _t = graded_problem(tw(2026, 9, 21), 's3', 'u2', None, special_external_doc=True, special_repeat=True)
    check('兩個特例同時成立 → 最多升一級（仍是 P2）', p_xx.final_priority == 'p2', p_xx.final_priority)
    p_sec, _t = graded_problem(tw(2026, 9, 21), 's4', 'u3', None, special_security=True)
    check('資安 → 直接 P1（S4×U3 原本是 P4）', p_sec.final_priority == 'p1', p_sec.final_priority)

    # ================= 人工調整 =================
    t_dg = Ta.create({'subject': 'ZZ 降級', 'channel': 'phone', 'category_id': cat_sys.id,
                      'functional_module_id': mod_log.id})
    p_dg = link_new(t_dg)
    raises('降級（P1 → P3）沒填理由存不進去', ValidationError,
           lambda: p_dg.with_user(u_agent).write({'severity': 's1', 'urgency': 'u1', 'manual_priority': 'p3'}))
    p_dg.with_user(u_agent).write({'severity': 's1', 'urgency': 'u1', 'manual_priority': 'p3',
                                   'downgrade_reason': '已有替代做法'})
    check('降級有填理由 → 最終 P3', p_dg.final_priority == 'p3')
    t_ug = Ta.create({'subject': 'ZZ 人工升級', 'channel': 'phone', 'category_id': cat_sys.id,
                      'functional_module_id': mod_log.id})
    p_ug = link_new(t_ug)
    p_ug.with_user(u_agent).write({'severity': 's4', 'urgency': 'u3', 'manual_priority': 'p1'})
    check('人工往上調不需理由 → 最終 P1', p_ug.final_priority == 'p1')

    # ================= 時限快照 =================
    sla_p1 = env.ref('construction_helpdesk.sla_p1')
    sla_p1.with_user(u_agent).write({'default_fix_days': 3})
    prb.invalidate_recordset()
    check('改時限設定後，既有 P1 單的預期天數與預定修復日不變',
          prb.expected_work_days == 2 and prb.planned_fix_date == date(2026, 9, 29))
    sla_p1.with_user(u_agent).write({'default_fix_days': 2})

    # ================= 變更等級 =================
    Wiz = env['construction.problem.regrade.wizard'].with_user(u_agent)
    # 用客服的時區取「今天」（shell 的 superuser 沒有時區＝UTC，台灣凌晨時會差一天）
    today = fields.Date.context_today(env['res.users'].with_user(u_agent))

    def regrade(problem, reason='ZZ 改判原因', **vals):
        w = Wiz.with_context(default_problem_id=problem.id).create(dict({'regrade_reason': reason}, **vals))
        w.action_confirm()
        problem.invalidate_recordset()
        return w

    w0 = Wiz.with_context(default_problem_id=p_sp.id).create({'regrade_reason': 'x'})
    check('變更等級對話框帶入目前的 S／U', w0.severity == 's3' and w0.urgency == 'u2')
    w0.regrade_reason = '   '
    raises('改判原因空白被擋', UserError, lambda: w0.action_confirm())

    old_start = p_sp.start_date
    regrade(p_sp, reason='查下去才發現金額會算錯', severity='s1')
    check('P3 → P1 改判：基準日＝今天、天數＝P1 預設、待確認、曾升級改判',
          p_sp.final_priority == 'p1' and p_sp.base_date == today and p_sp.expected_work_days == 2
          and p_sp.non_working_to_confirm and p_sp.ever_upgraded,
          (p_sp.final_priority, p_sp.base_date, p_sp.expected_work_days))
    check('改判後起算日不變（總處理天數仍從客戶回報那天算）', p_sp.start_date == old_start)
    check('改判不會一改就逾時（預定修復日在今天之後）', p_sp.planned_fix_date > today and not p_sp.is_overdue)
    note = p_sp.message_ids.filtered(lambda m: '查下去才發現金額會算錯' in (m.body or ''))
    check('改判原因與 P3 → P1 寫進 chatter', note and 'P3' in note[0].body and 'P1' in note[0].body)

    base_before = p_sp.base_date
    p_sp.with_user(u_agent).with_context(helpdesk_regrade=True).write({'base_date': today - timedelta(days=5)})
    regrade(p_sp, reason='補勾二次回報，P 不變', special_repeat=True)
    check('改判但最終 P 不變 → 基準日不動', p_sp.final_priority == 'p1' and p_sp.base_date == today - timedelta(days=5))

    regrade(p_fri, reason='有替代做法，降級', urgency='u3')   # S1×U3 → P2
    check('降級改判（P1 → P2）：天數＝P2 預設 5、不算「曾升級」',
          p_fri.final_priority == 'p2' and p_fri.expected_work_days == 5 and not p_fri.ever_upgraded)
    raises('改判時降級（人工調低）沒填降級理由被擋', ValidationError,
           lambda: regrade(p_mon, manual_priority='p4'))

    # ================= 逾時 =================
    p_od, _t = graded_problem(tw(2026, 9, 1), 's1', 'u1', 0)    # 預定 9/3，今天已過
    check('未完成且已過預定修復日 → 逾時', p_od.is_overdue)
    overdue_ids = env[P].search([('is_overdue', '=', True)]).ids
    check('「逾時」可以篩選（_search）', p_od.id in overdue_ids and p_mon.id not in overdue_ids,
          (p_mon.planned_fix_date, p_mon.is_overdue))
    check('「逾時＝否」篩選不含逾時單', p_od.id not in env[P].search([('is_overdue', '=', False)]).ids)
    p_od.with_user(u_agent).write({'fix_done_date': date(2026, 9, 3)})
    check('完成日＝預定日 → 不逾時', not p_od.is_overdue)
    p_od.with_user(u_agent).write({'fix_done_date': date(2026, 9, 5)})
    check('完成日晚於預定日 → 逾時', p_od.is_overdue and p_od.id in env[P].search([('is_overdue', '=', True)]).ids)
    check('總處理天數＝完成日 − 起算日（9/5 − 9/1＝4）', p_od.total_days == 4, p_od.total_days)

    # ================= 多客戶回報同一問題 =================
    ta = Ta.create({'subject': 'ZZ 甲回報', 'channel': 'phone', 'category_id': cat_sys.id,
                    'functional_module_id': mod_log.id, 'customer_company': pa, 'report_datetime': tw(2026, 9, 22)})
    p_multi = link_new(ta)
    p_multi.with_user(u_agent).write({'severity': 's3', 'urgency': 'u1'})     # P2
    base_multi = p_multi.base_date
    tb = Ta.create({'subject': 'ZZ 乙回報同一問題', 'channel': 'line', 'category_id': cat_sys.id,
                    'functional_module_id': mod_log.id, 'customer_company': ' ' + pb + ' ', 'report_datetime': tw(2026, 9, 20)})
    wl = env['construction.problem.link.wizard'].with_user(u_agent).with_context(default_ticket_id=tb.id).create({})
    wl._onchange_ticket_id()
    check('轉問題單：同功能模組有未結案問題單時預設「連到既有」並列出它',
          wl.mode == 'link' and p_multi in wl.candidate_ids)
    check('候選清單不含其他功能模組的問題單', prb not in wl.candidate_ids)
    wl.write({'mode': 'link', 'problem_id': p_multi.id})
    wl.action_confirm()
    check('兩張服務單指向同一問題單；回報客戶數 2', p_multi.ticket_count == 2 and p_multi.reported_customer_count == 2)
    check('回報客戶數純資訊：等級不變（仍 P2）', p_multi.final_priority == 'p2')
    check('較早的回報連進來 → 起算日提前，但計算基準日不動',
          p_multi.start_date == date(2026, 9, 20) and p_multi.base_date == base_multi)
    tc = Ta.create({'subject': 'ZZ 內部回報', 'channel': 'internal', 'category_id': cat_sys.id,
                    'functional_module_id': mod_log.id})
    tc.write({'problem_id': p_multi.id})
    check('沒填客戶公司的服務單不算進回報客戶數', p_multi.ticket_count == 3 and p_multi.reported_customer_count == 2)

    # ================= 結案 =================
    prb.with_user(u_agent).write({'data_fix_needed': True, 'data_fix_state': 'in_progress'})
    raises('需要修正既有資料但未完成 → 不能結案', UserError, lambda: prb.with_user(u_agent).action_done())
    prb.with_user(u_agent).write({'data_fix_state': 'done'})
    prb.with_user(u_agent).action_to_deploy()
    prb.with_user(u_agent).action_to_verify()
    prb.with_user(u_agent).action_done()
    check('結案：記下修復完成日＝今天', prb.state == 'done' and prb.fix_done_date == today)
    check('問題單結案不動服務單（仍處理中）', t1.state == 'processing')
    prb.with_user(u_agent).action_reopen()
    check('重新開啟 → 處理中、清掉修復完成日', prb.state == 'processing' and not prb.fix_done_date)

    # ================= 1.6.0：判定標準、調整原因、候選問題單、改連 =================
    check('問題單顯示「單號 標題」（下拉與候選清單看得出是什麼問題）',
          prb.display_name == '%s %s' % (prb.name, prb.title), prb.display_name)
    guide = str(prb.grade_guide_html)
    check('判定標準參考表：含 S／U 條件、P 表、P1 修復期限讀自處理時限設定',
          'S1 致命' in guide and 'U1 立即' in guide and 'P 表' in guide
          and env.ref('construction_helpdesk.sla_p1').fix_limit_note in guide)
    env.ref('construction_helpdesk.sla_p2').write({'default_fix_days': 6})
    check('改處理時限設定 → 判定標準表跟著變（P2 6 個工作天）',
          '6 個工作天' in str(env['construction.problem']._grade_guide_html()))
    env.ref('construction_helpdesk.sla_p2').write({'default_fix_days': 5})
    check('S 選項附簡短條件', '資料錯誤' in dict(env[P]._fields['severity'].selection)['s1'])
    check('降級理由改名「調整原因」', env[P]._fields['downgrade_reason'].string == '調整原因')
    wv = env['construction.problem.regrade.wizard'].get_views([(False, 'form')])['views']['form']['arch']
    from lxml import etree
    _node = etree.fromstring(wv).xpath("//field[@name='regrade_reason']")
    check('變更等級：改判原因放在 group 內（才會顯示欄位名稱）、有判定標準',
          'grade_guide_html' in wv and _node and _node[0].getparent().tag == 'group')
    # 候選：同發生功能 vs 全部未結案
    t_c = Ta.create({'subject': 'ZZ 候選測試', 'channel': 'phone', 'category_id': cat_sys.id,
                     'functional_module_id': mod_log.id})
    wc = env['construction.problem.link.wizard'].with_user(u_agent).with_context(default_ticket_id=t_c.id).create({})
    same = wc.candidate_ids
    wc.show_all = True
    check('「列出所有未結案」會列出其他發生功能的問題單',
          prb in wc.candidate_ids and prb not in same and same <= wc.candidate_ids)
    # 改連：連錯了可以改，舊的那張留紀錄
    wc.write({'mode': 'link', 'problem_id': prb.id}); wc.action_confirm()
    first = t_c.problem_id
    w2 = env['construction.problem.link.wizard'].with_user(u_agent).with_context(default_ticket_id=t_c.id).create(
        {'mode': 'link', 'show_all': True})
    check('改連時候選清單不含目前已連的那張', first not in w2.candidate_ids)
    target = (w2.candidate_ids - first)[:1]
    w2.write({'problem_id': target.id}); w2.action_confirm()
    check('更改關聯問題單：服務單改指到新的那張', t_c.problem_id == target)
    check('舊問題單留下「已改連」紀錄',
          any('已改連' in (m.body or '') for m in first.message_ids))

    # ================= 1.6.1：以問題說明＋發生功能判斷是否同一問題 =================
    t_d = Ta.create({'subject': 'ZZ 說明帶入', 'channel': 'phone', 'category_id': cat_sys.id,
                     'functional_module_id': mod_log.id,
                     'description': '<p>在施工日誌按存檔後，跳出錯誤訊息並且資料沒有存進去。' + '很長' * 80 + '</p>'})
    p_d = link_new(t_d)
    check('新建問題單時自動帶入服務單的詳細說明', '按存檔後' in (p_d.description or ''))
    check('問題說明摘要：純文字、最多 120 字＋…',
          p_d.description_summary.startswith('在施工日誌按存檔後') and len(p_d.description_summary) == 121
          and p_d.description_summary.endswith('…'), len(p_d.description_summary))
    lv = env['construction.problem.link.wizard'].get_views([(False, 'form')])['views']['form']['arch']
    from lxml import etree
    cols = [f.get('name') for f in etree.fromstring(lv).xpath("//field[@name='candidate_ids']/list/field")]
    check('候選清單只列：單號、標題、發生功能、問題說明摘要', cols == ['name', 'title', 'functional_module_id', 'description_summary'], cols)
    check('轉問題單對話框顯示本服務單的詳細說明（對照用）', 'ticket_description' in lv)
    pv = env[P].get_views([(False, 'form')])['views']['form']['arch']
    pages = [pg.get('string') for pg in etree.fromstring(pv).xpath('//notebook/page')]
    check('問題單第一個頁籤是「問題說明」', pages and pages[0] == '問題說明', pages)

    # ================= 看板（依狀態分組）=================
    try:
        groups = env[P].with_user(u_agent).web_read_group([], ['state'], ['state'])
        states = [g['state'] for g in groups['groups']]
        check('看板依狀態分組：六個狀態欄都出現（含沒有單的空欄）',
              set(states) == {'pending_grade', 'processing', 'pending_deploy', 'pending_verify', 'done', 'wont_fix'},
              states)
    except Exception as e:
        check('看板依狀態分組', False, repr(e))

    # ================= 畫面與選單 =================
    for model, views in ((P, ('kanban', 'list', 'form', 'search', 'pivot', 'graph')),
                         ('construction.problem.link.wizard', ('form',)),
                         ('construction.problem.regrade.wizard', ('form',)),
                         (T, ('list', 'form', 'search', 'pivot', 'graph'))):
        try:
            env[model].with_user(u_agent).get_views([(False, v) for v in views])
            check('get_views %s（客服）' % model, True)
        except Exception as e:
            check('get_views %s（客服）' % model, False, repr(e))
    try:
        env[T].with_user(u_op).get_views([(False, 'form'), (False, 'list')])
        check('get_views 服務單（代操作員，含轉問題單按鈕被移除）', True)
    except Exception as e:
        check('get_views 服務單（代操作員）', False, repr(e))
    arch_op = env[T].with_user(u_op).get_views([(False, 'form')])['views']['form']['arch']
    check('代操作員的服務單表單沒有「轉問題單」與關聯問題單', 'action_open_link_problem' not in arch_op and 'problem_id' not in arch_op)
    pv = env.ref('construction_helpdesk.view_problem_pivot_monthly')
    try:
        env[P].with_user(u_agent).get_views([(pv.id, 'pivot')])
        env[P].with_user(u_agent).read_group([('state', '=', 'done')], ['total_days:avg'], ['fix_done_date:month'])
        check('每月處理量樞紐與平均總處理天數可查詢', True)
    except Exception as e:
        check('每月處理量樞紐', False, repr(e))
    vis_op = env['ir.ui.menu'].with_user(u_op)._visible_menu_ids()
    vis_ag = env['ir.ui.menu'].with_user(u_agent)._visible_menu_ids()
    stat_menus = ['menu_problem', 'menu_report_problem_overdue', 'menu_report_problem_to_confirm',
                  'menu_report_problem_upgraded', 'menu_report_problem_by_module',
                  'menu_report_ticket_by_partner', 'menu_report_problem_monthly']
    ids = [env.ref('construction_helpdesk.' + m).id for m in stat_menus]
    check('客服看得到問題單與 6 個統計選單', all(i in vis_ag for i in ids))
    check('代操作員看不到問題單與統計選單', not any(i in vis_op for i in ids),
          [m for m, i in zip(stat_menus, ids) if i in vis_op])
    for xmlid in ('action_report_problem_overdue', 'action_report_problem_to_confirm',
                  'action_report_problem_upgraded'):
        act = env.ref('construction_helpdesk.' + xmlid)
        check('統計 action 可載入：%s' % act.name, act.read(['name', 'context']))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT helpdesk_p3')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

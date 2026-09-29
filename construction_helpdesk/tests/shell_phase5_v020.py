# -*- coding: utf-8 -*-
"""18.0.2.0.0 驗收：分級標準 v0.3 的分級、等待客戶、結案條件、不處理原因、資安、資料盤修（odoo shell，全程 rollback）。

echo 'exec(open("/mnt/extra-addons/construction_helpdesk/tests/shell_phase5_v020.py", encoding="utf-8").read())' \
  | odoo shell -d system_development ... --no-http
"""
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, exc, fn, contains=None):
    try:
        with env.cr.savepoint():
            fn()
    except exc as e:
        ok = contains is None or contains in str(e)
        results.append((ok, name, type(e).__name__ if ok else 'message: %s' % e))
        return
    except Exception as e:
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


T = 'construction.service.ticket'
P = 'construction.problem'

env.cr.execute('SAVEPOINT helpdesk_p5')
try:
    u_agent = env.ref('base.user_admin')
    Ta = env[T].with_user(u_agent)
    Att = env['ir.attachment']
    Sla = env['construction.problem.sla']
    cat_sys = env.ref('construction_helpdesk.category_system_problem')
    cat_q = env.ref('construction_helpdesk.category_operation_question')
    mod_pay = env.ref('construction_helpdesk.module_payment')
    today = fields.Date.context_today(env['res.users'].with_user(u_agent))
    company = env['res.partner'].create({'name': 'ZZ v020 營造', 'is_company': True})
    pu = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ v020 前台', 'login': 'zz_v020_portal', 'parent_id': company.id,
        'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                              env.ref('construction_supervision_base.group_portal_user').id])]})

    def att(rec, name='a.txt'):
        return Att.create({'name': name, 'raw': b'x', 'res_model': rec._name, 'res_id': rec.id})

    def new_ticket(subject='ZZ v020', user=None, **extra):
        vals = {'subject': subject, 'channel': 'phone', 'category_id': cat_sys.id,
                'functional_module_id': mod_pay.id}
        vals.update(extra)
        if user:
            vals.update({'channel': 'portal'})
            return env[T].with_user(user).create(vals)
        return Ta.create(vals)

    def link_new(ticket):
        wiz = env['construction.problem.link.wizard'].with_user(u_agent).with_context(
            default_ticket_id=ticket.id).create({'mode': 'new', 'title': ticket.subject})
        return env[P].browse(wiz.action_confirm()['res_id'])

    def graded(s, u, ticket=None, **extra):
        t = ticket or new_ticket()
        p = link_new(t)
        vals = {'severity': s, 'urgency': u}
        vals.update(extra)
        p.with_user(u_agent).write(vals)
        return p, t

    def deploy(p):
        p.with_user(u_agent).action_to_deploy()
        p.with_user(u_agent).action_to_verify()

    def evidence(p, prod=True):
        vals = {'evidence_before_ids': [(6, 0, att(p).ids)], 'evidence_after_ids': [(6, 0, att(p).ids)]}
        if prod:
            vals['evidence_prod_ids'] = [(6, 0, att(p).ids)]
        p.with_user(u_agent).write(vals)

    def notice(p):
        p.with_user(u_agent).write({'customer_notice_datetime': fields.Datetime.now(),
                                    'customer_notice_content': 'ZZ 通知'})

    def backdate_verify(t, days):
        t.sudo().with_context(helpdesk_system_write=True).write(
            {'waiting_verify_datetime': fields.Datetime.now() - timedelta(days=days, minutes=1)})

    # ================= 處理時限設定 =================
    s = {p: env.ref('construction_helpdesk.sla_' + p) for p in ('p1', 'p2', 'p3', 'p4')}
    check('客戶未回覆可結案天數：P1～P4 皆 7', all(s[p].customer_wait_days == 7 for p in s),
          [s[p].customer_wait_days for p in s])
    check('資料盤修天數：P1、P2 為 7，P3、P4 為 0',
          s['p1'].data_fix_days == 7 and s['p2'].data_fix_days == 7 and not s['p3'].data_fix_days)
    check('P2 暫行措施目標「1 個工作天」', s['p2'].temporary_target == '1 個工作天', s['p2'].temporary_target)
    raises('客戶未回覆可結案天數不能是 0（等於客戶確認形同選配）', ValidationError,
           lambda: s['p3'].write({'customer_wait_days': 0}))

    # ================= 分級（v0.3）=================
    p_ext, _t = graded('s4', 'u3', special_external_doc=True)
    check('錯誤已流入對外文件 → 直接 P1（S4×U3）', p_ext.final_priority == 'p1', p_ext.final_priority)
    guide = str(env[P]._grade_guide_html())
    check('判定標準：S1 含「寫進資料庫」與安全告警', '寫進資料庫' in guide and '告警' in guide)
    check('判定標準：核心功能含進度表、契約變更、缺失改善、水位，不含驗收',
          all(k in guide for k in ('進度表', '契約變更', '缺失改善', '水位')) and '驗收' not in guide.split('U1 立即')[0])
    check('判定標準：P 表多一欄暫行措施、說明不設多客戶特例', '暫行措施' in guide and '多個客戶' in guide)
    check('分級時帶入資料盤修天數快照（P1＝7）', p_ext.data_fix_days == 7, p_ext.data_fix_days)

    # ================= 服務單兩個等待狀態 =================
    p_info, t_info = graded('s2', 'u2')          # P2
    raises('問題單未部署 → 不能請客戶驗證', UserError, lambda: t_info.with_user(u_agent).action_wait_verify())
    t_info.with_user(u_agent).action_wait_info()
    check('待客戶補件：服務單狀態、問題單自動勾曾等客戶',
          t_info.state == 'waiting_info' and p_info.ever_waited_customer)
    raises('曾等客戶不能手動取消', UserError,
           lambda: p_info.with_user(u_agent).write({'ever_waited_customer': False}))
    raises('結案方式不能手動填', UserError, lambda: p_info.with_user(u_agent).write({'close_type': 'confirmed'}))
    raises('服務單的客戶確認欄位不能手動改', UserError,
           lambda: t_info.with_user(u_agent).write({'customer_confirmed': True}))
    raises('待客戶補件的服務單不能直接結案', UserError, lambda: t_info.with_user(u_agent).action_done())
    t_info.with_user(u_agent).action_back_to_processing()
    check('回到處理中後，曾等客戶仍保留', t_info.state == 'processing' and p_info.ever_waited_customer)
    raises('掛著未結案問題單的服務單不能直接結案', UserError, lambda: t_info.with_user(u_agent).action_done())

    # ================= 前台：問題已解決／仍有問題 =================
    t_pt = new_ticket('ZZ v020 前台單', user=pu)
    t_pt.with_user(u_agent).write({'category_id': cat_sys.id})
    p_pt = link_new(t_pt)
    p_pt.with_user(u_agent).write({'severity': 's3', 'urgency': 'u2'})     # P3
    deploy(p_pt)
    check('按待驗證 → 修復完成日＝今天', p_pt.fix_done_date == today)
    t_pt.with_user(u_agent).action_wait_verify()
    check('待客戶驗證：記下進入時間', t_pt.state == 'waiting_verify' and t_pt.waiting_verify_datetime)
    raises('前台帳號不能直接改服務單狀態', (AccessError, UserError),
           lambda: t_pt.with_user(pu).write({'state': 'done'}))
    t_pt.with_user(pu)._register_not_resolved(pu)
    check('客戶按「仍有問題」→ 回到處理中、問題單留紀錄',
          t_pt.state == 'processing' and any('仍有問題' in (m.body or '') for m in p_pt.message_ids))
    t_pt.with_user(u_agent).action_wait_verify()
    t_pt.with_user(pu)._register_confirmation('portal', pu.name, False, pu)
    check('客戶按「問題已解決」→ 服務單結案、已確認、方式＝前台',
          t_pt.state == 'done' and t_pt.customer_confirmed and t_pt.confirm_method == 'portal'
          and t_pt.confirm_user_id == pu)
    p_pt.with_user(u_agent).action_done()
    check('P3 有一張客戶確認 → 問題單結案（客戶確認）', p_pt.state == 'done' and p_pt.close_type == 'confirmed')

    # ================= 登記客戶確認：2.0.1 起停用（對話框、按鈕都不載入），佐證規則仍在寫入層 =================
    check('登記客戶確認對話框已停用（模型不存在）', 'construction.service.ticket.confirm.wizard' not in env)
    arch_t = env[T].with_user(u_agent).get_views([(False, 'form')])['views']['form']['arch']
    from lxml import etree as _et
    # 用元素判斷：arch 會保留 XML 註解，註解裡的舊按鈕文字還在
    check('服務單表單沒有「登記客戶確認」按鈕',
          not _et.fromstring(arch_t).xpath("//button[@name='action_open_confirm_wizard']"))
    p_ph, t_ph = graded('s3', 'u2')
    deploy(p_ph)
    t_ph.with_user(u_agent).action_wait_verify()
    raises('（寫入層）LINE 確認沒附截圖 → 擋下', UserError,
           lambda: t_ph.with_user(u_agent)._register_confirmation('line', 'ZZ 李小姐', 'ZZ', u_agent))
    raises('（寫入層）電話確認沒寫對方怎麼說 → 擋下', UserError,
           lambda: t_ph.with_user(u_agent)._register_confirmation('phone', 'ZZ 李小姐', '  ', u_agent))
    t_ph.with_user(u_agent)._register_confirmation('phone', 'ZZ 李小姐', 'ZZ 9/29 10:00 來電說好了', u_agent)
    check('（寫入層）電話確認不需要附圖、有寫說明即可 → 服務單結案',
          t_ph.state == 'done' and t_ph.customer_confirmed and t_ph.confirm_method == 'phone')

    # ================= P3／P4：排程逾期自動結案、客戶回覆即重開 =================
    t_od = new_ticket('ZZ v020 前台逾期單', user=pu)   # 前台帳號建的：之後要以客戶身分回覆
    t_od.with_user(u_agent).write({'category_id': cat_sys.id})
    p_od, t_od = graded('s4', 'u2', ticket=t_od)       # P4
    deploy(p_od)
    t_od.with_user(u_agent).action_wait_verify()
    raises('P4 客戶還沒回、也還沒逾期 → 問題單不能結案', UserError, lambda: p_od.with_user(u_agent).action_done())
    backdate_verify(t_od, 6)
    env[T]._cron_close_overdue_verify()
    check('排程：未滿 7 天不結案', t_od.state == 'waiting_verify')
    backdate_verify(t_od, 7)
    n = env[T]._cron_close_overdue_verify()
    check('排程：滿 7 天 → 服務單逾期結案', t_od.state == 'done' and t_od.overdue_closed, n)
    check('逾期結案的說明是客戶看得到的留言（comment）',
          any('回覆本單' in (m.body or '') and m.message_type == 'comment' for m in t_od.message_ids))
    p_od.with_user(u_agent).action_done()
    check('P4 服務單逾期結案 → 問題單可結案（逾期未回覆結案）',
          p_od.state == 'done' and p_od.close_type == 'no_reply_overdue')
    t_od.with_user(u_agent).message_post(body='ZZ 客服補充', message_type='comment',
                                         subtype_xmlid='mail.mt_comment')
    check('客服留言不會重開逾期結案的單', t_od.state == 'done')
    t_od.with_user(pu).message_post(body='ZZ 問題還在', message_type='comment',
                                    subtype_xmlid='mail.mt_comment')
    check('客戶回覆逾期結案的單 → 自動重開（處理中、清掉逾期標記）',
          t_od.state == 'processing' and not t_od.overdue_closed)

    p_p1, t_p1 = graded('s1', 'u1')              # P1
    deploy(p_p1)
    t_p1.with_user(u_agent).action_wait_verify()
    backdate_verify(t_p1, 30)
    env[T]._cron_close_overdue_verify()
    check('排程不會自動結案 P1 的服務單', t_p1.state == 'waiting_verify')

    # ================= P1／P2：未回覆、附對照結案 =================
    raises('P1 沒通知客戶 → 不能結案', UserError, lambda: p_p1.with_user(u_agent).action_done(), '通知客戶')
    notice(p_p1)
    raises('P1 沒附修復前後對照 → 不能結案', UserError, lambda: p_p1.with_user(u_agent).action_done(), '修復前')
    evidence(p_p1, prod=False)
    raises('P1 客戶未回覆、缺正式站實測 → 不能結案', UserError,
           lambda: p_p1.with_user(u_agent).action_done(), '正式站實測')
    evidence(p_p1, prod=True)
    backdate_verify(t_p1, 6)
    due = (t_p1.waiting_verify_datetime + timedelta(days=7) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
    raises('P1 未滿 7 天 → 不能附對照結案，訊息寫出該服務單哪天滿 7 天（台灣時間）', UserError,
           lambda: p_p1.with_user(u_agent).action_done(), '%s（%s 滿 7 天）' % (t_p1.name, due))
    t2 = new_ticket('ZZ 同問題另一家')
    t2.with_user(u_agent).write({'problem_id': p_p1.id})
    t2.with_user(u_agent).action_start() if t2.state == 'new' else None
    backdate_verify(t_p1, 8)
    raises('還有關聯服務單不在待客戶驗證 → 不能附對照結案，訊息寫出它目前的狀態', UserError,
           lambda: p_p1.with_user(u_agent).action_done(), '%s（目前「處理中」，尚未請客戶驗證）' % t2.name)
    t2.with_user(u_agent).action_cancel()
    p_p1.with_user(u_agent).action_done()
    check('P1 全部服務單滿 7 天未回、三件對照齊 → 結案（未回覆、附對照）',
          p_p1.state == 'done' and p_p1.close_type == 'no_reply_evidence')
    check('一直沒回的服務單一併逾期結案', t_p1.state == 'done' and t_p1.overdue_closed)

    # ================= 沒有關聯服務單（內部發現）=================
    p_int = env[P].with_user(u_agent).create({'title': 'ZZ 內部發現'})
    p_int.with_user(u_agent).write({'severity': 's2', 'urgency': 'u2'})    # P2
    deploy(p_int)
    raises('沒有服務單的 P2 沒附對照 → 不能結案', UserError, lambda: p_int.with_user(u_agent).action_done())
    evidence(p_int)
    p_int.with_user(u_agent).action_done()
    check('沒有服務單的 P2 附齊對照 → 結案（無關聯服務單）', p_int.close_type == 'internal')
    p_int4 = env[P].with_user(u_agent).create({'title': 'ZZ 內部發現 P4'})
    p_int4.with_user(u_agent).write({'severity': 's4', 'urgency': 'u3'})
    p_int4.with_user(u_agent).action_done()
    check('沒有服務單的 P4 → 可直接結案', p_int4.state == 'done' and p_int4.close_type == 'internal')

    # ================= 不處理 =================
    Ww = env['construction.problem.wontfix.wizard'].with_user(u_agent)
    p_w1, _t = graded('s1', 'u1')
    for reason in ('cannot_reproduce', 'risk_accepted'):
        w = Ww.create({'problem_id': p_w1.id, 'reason': reason, 'note': 'ZZ'})
        raises('P1 不能以「%s」不處理' % reason, UserError, lambda w=w: w.action_confirm())
    w = Ww.create({'problem_id': p_w1.id, 'reason': 'not_system', 'note': '  '})
    raises('不處理說明空白 → 擋下', UserError, lambda: w.action_confirm())
    p_w3, _t = graded('s3', 'u3')
    Ww.create({'problem_id': p_w3.id, 'reason': 'risk_accepted', 'note': 'ZZ 成本太高'}).action_confirm()
    check('P4 接受風險 → 不處理、記下原因與說明',
          p_w3.state == 'wont_fix' and p_w3.wont_fix_reason == 'risk_accepted' and p_w3.wont_fix_note)
    p_dup, t_dup = graded('s3', 'u2')
    t_dup.with_user(u_agent).action_wait_info()
    p_main, t_main = graded('s3', 'u2')
    raises('重複沒選對象 → 擋下', UserError,
           lambda: Ww.create({'problem_id': p_dup.id, 'reason': 'duplicate', 'note': 'ZZ'}).action_confirm())
    Ww.create({'problem_id': p_dup.id, 'reason': 'duplicate', 'note': 'ZZ 同一件事',
               'duplicate_of_id': p_main.id}).action_confirm()
    check('重複：本單不處理並記下重複於哪張',
          p_dup.state == 'wont_fix' and p_dup.duplicate_of_id == p_main)
    check('重複：關聯服務單移到主單、曾等客戶一併帶過去',
          t_dup.problem_id == p_main and p_main.ever_waited_customer)
    raises('不處理的單不能變更等級（按鈕）', UserError, lambda: p_dup.with_user(u_agent).action_open_regrade())
    wrg = env['construction.problem.regrade.wizard'].with_user(u_agent).with_context(
        default_problem_id=p_dup.id).create({'regrade_reason': 'ZZ'})
    raises('不處理的單不能變更等級（對話框直接確定）', UserError, lambda: wrg.action_confirm())
    p_dup.with_user(u_agent).action_reopen()
    check('重新開啟清掉不處理原因', not p_dup.wont_fix_reason and not p_dup.duplicate_of_id)
    check('重新開啟後可以變更等級', p_dup.with_user(u_agent).action_open_regrade().get('res_model')
          == 'construction.problem.regrade.wizard')

    # ================= 資安事件 =================
    p_sec, t_sec = graded('s4', 'u3', special_security=True)
    check('資安 → 直接 P1', p_sec.final_priority == 'p1')
    notice(p_sec)
    evidence(p_sec)
    deploy(p_sec)
    t_sec.with_user(u_agent).action_wait_verify()
    t_sec.with_user(u_agent)._register_confirmation('portal', 'ZZ', False, u_agent)
    raises('資安檢核表未填 → 不能結案', UserError, lambda: p_sec.with_user(u_agent).action_done(), '資安事件檢核表')
    t0 = datetime(2026, 9, 26, 22, 0)
    p_sec.with_user(u_agent).write({
        'sec_discovered_datetime': t0, 'sec_contained_datetime': t0 + timedelta(minutes=50),
        'sec_contained_by': 'ZZ 黃工程師', 'sec_pii_leak': 'unknown',
        'sec_pii_judged_datetime': t0 + timedelta(hours=5), 'sec_scope_estimate': 'ZZ 帳號 3 筆',
        'sec_scope_datetime': t0 + timedelta(hours=20)})
    check('資安耗時以實際經過時間計（週五晚上 22:00 起算，不等週一）',
          p_sec.sec_contain_hours == 0.8 and p_sec.sec_pii_hours == 5.0 and p_sec.sec_scope_hours == 20.0,
          (p_sec.sec_contain_hours, p_sec.sec_pii_hours, p_sec.sec_scope_hours))
    raises('個資「無法判定」視同有 → 要填法定通知評估', UserError,
           lambda: p_sec.with_user(u_agent).action_done(), '法定通知評估')
    p_sec.with_user(u_agent).write({'sec_legal_assessment': 'ZZ 評估', 'sec_notify_decision': 'not_notify'})
    raises('決定不通知 → 要寫理由', UserError, lambda: p_sec.with_user(u_agent).action_done(), '不通知的理由')
    p_sec.with_user(u_agent).write({'sec_not_notify_reason': 'ZZ 理由'})
    p_sec.with_user(u_agent).action_done()
    check('資安檢核表填齊 → 可結案', p_sec.state == 'done')

    # ================= 資料盤修 =================
    # 客戶 20 天前回報：才能把修復完成日設在 10 天前（修復完成日不能早於起算日）
    p_df, t_df = graded('s1', 'u2', ticket=new_ticket(
        report_datetime=fields.Datetime.now() - timedelta(days=20)))                # P1
    p_df.with_user(u_agent).write({'data_fix_needed': True, 'data_fix_state': 'done'})
    check('尚未部署 → 沒有盤修預定日', not p_df.data_fix_planned_date)
    raises('修復完成日早於起算日 → 擋下（否則總處理天數變負數）', ValidationError,
           lambda: p_df.with_user(u_agent).write({'fix_done_date': p_df.start_date - timedelta(days=1)}))
    deploy(p_df)
    check('盤修預定日＝修復完成日＋7', p_df.data_fix_planned_date == today + timedelta(days=7), p_df.data_fix_planned_date)
    p_df.with_user(u_agent).write({'fix_done_date': today - timedelta(days=10)})
    check('超過盤修預定日且未完成 → 盤修逾時', p_df.data_fix_overdue)
    notice(p_df)
    evidence(p_df)
    t_df.with_user(u_agent).action_wait_verify()
    t_df.with_user(u_agent)._register_confirmation('portal', 'ZZ', False, u_agent)
    raises('盤修缺備份位置／範圍／對照／腳本 → 不能結案', UserError,
           lambda: p_df.with_user(u_agent).action_done(), '原始錯誤值備份位置')
    p_df.with_user(u_agent).write({
        'data_fix_backup_location': '/bk', 'data_fix_scope': 'ZZ', 'data_fix_done_date': today,
        'data_fix_compare_ids': [(6, 0, att(p_df).ids)], 'data_fix_script_ids': [(6, 0, att(p_df).ids)]})
    p_df.with_user(u_agent).action_done()
    check('盤修交付物齊 → 可結案', p_df.state == 'done')

    # ================= 改判帶入新等級的盤修天數 =================
    p_rg, _t = graded('s3', 'u3')                  # P4，盤修天數 0
    check('P4 盤修天數＝0', p_rg.data_fix_days == 0)
    w = env['construction.problem.regrade.wizard'].with_user(u_agent).with_context(
        default_problem_id=p_rg.id).create({'regrade_reason': 'ZZ 查下去是資料錯', 'severity': 's1'})
    w.action_confirm()
    check('改判成 S1×U3＝P2 → 盤修天數帶入 7', p_rg.final_priority == 'p2' and p_rg.data_fix_days == 7,
          (p_rg.final_priority, p_rg.data_fix_days))

    # ================= 畫面、選單、排程 =================
    from lxml import etree
    for model, views in ((P, ('kanban', 'list', 'form', 'search', 'pivot', 'graph')),
                         (T, ('list', 'form', 'search')),
                         ('construction.problem.wontfix.wizard', ('form',)),
                         ('construction.problem.sla', ('list', 'form'))):
        try:
            env[model].with_user(u_agent).get_views([(False, v) for v in views])
            check('get_views %s' % model, True)
        except Exception as e:
            check('get_views %s' % model, False, repr(e))
    pv = env[P].with_user(u_agent).get_views([(False, 'form')])['views']['form']['arch']
    pages = [pg.get('string') for pg in etree.fromstring(pv).xpath('//notebook/page')]
    check('問題單頁籤含「修復驗證與結案」「資安事件」', '修復驗證與結案' in pages and '資安事件' in pages, pages)
    for xmlid in ('view_problem_pivot_close_type',):
        v = env.ref('construction_helpdesk.' + xmlid)
        try:
            env[P].with_user(u_agent).get_views([(v.id, 'pivot')])
            env[P].with_user(u_agent).read_group([('state', 'in', ('done', 'wont_fix'))], ['__count'],
                                                 ['close_type', 'ever_waited_customer'], lazy=False)
            check('結案方式統計樞紐可查詢', True)
        except Exception as e:
            check('結案方式統計樞紐', False, repr(e))
    monthly = env.ref('construction_helpdesk.action_report_problem_monthly')
    check('每月處理量剔除曾等客戶', 'ever_waited_customer' in (monthly.domain or ''), monthly.domain)
    vis = env['ir.ui.menu'].with_user(u_agent)._visible_menu_ids()
    check('客服看得到「結案方式統計」選單',
          env.ref('construction_helpdesk.menu_report_problem_close_type').id in vis)
    cron = env.ref('construction_helpdesk.cron_close_overdue_verify')
    check('逾期結案排程存在、每天執行、啟用', cron.active and cron.interval_type == 'days' and cron.interval_number == 1)
    try:
        groups = env[T].with_user(u_agent).web_read_group([], ['state'], ['state'])
        check('服務單可依狀態分組（含兩個等待狀態）', True)
    except Exception as e:
        check('服務單依狀態分組', False, repr(e))
    sel = dict(env[T]._fields['state'].selection)
    check('服務單狀態：待客戶補件、待客戶驗證，沒有舊的待客戶確認',
          sel.get('waiting_info') == '待客戶補件' and sel.get('waiting_verify') == '待客戶驗證'
          and 'waiting_customer' not in sel)
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT helpdesk_p5')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

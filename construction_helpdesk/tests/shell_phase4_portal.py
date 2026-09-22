# -*- coding: utf-8 -*-
"""前台「意見回饋」模型層驗收（odoo shell，全程 rollback，不留資料）。

echo 'exec(open("/mnt/extra-addons/construction_helpdesk/tests/shell_phase4_portal.py", encoding="utf-8").read())' \
  | odoo shell -d system_development ... --no-http
"""
from odoo.exceptions import AccessError, UserError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, exc, fn):
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


T = 'construction.service.ticket'
AGENT = 'construction_helpdesk.group_helpdesk_agent'

env.cr.execute('SAVEPOINT helpdesk_p4')
try:
    u_agent = env.ref('base.user_admin')
    company = env['res.partner'].create({'name': 'ZZ 前台測試營造', 'is_company': True})

    def portal_user(login):
        return env['res.users'].with_context(no_reset_password=True).create({
            'name': 'ZZ ' + login, 'login': login, 'parent_id': company.id,
            'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                                  env.ref('construction_supervision_base.group_portal_user').id])],
        })

    pu = portal_user('zz_portal_a')
    pu2 = portal_user('zz_portal_b')
    check('前台帳號不是內部使用者、不是客服', pu.share and not pu.has_group(AGENT))

    # ---------- 資料遷移 ----------
    Mod = env['construction.functional.module']
    names = Mod.search([]).mapped('name')
    portal_labels = [m.get_portal_label() for m in Mod.search([('show_in_portal', '=', True)])]
    check('發生功能「名稱」以後台為主（登入／帳號、文件管理、不確定／其他）',
          {'登入／帳號', '文件管理', '不確定／其他'} <= set(names) and '檔案' not in names, names)
    check('前台看到的叫法（工程列表／工程資訊、照片中心、缺失改善、檔案管理、檢試驗管制、自主檢查樣板庫、工程進度）',
          {'工程列表／工程資訊', '照片中心', '缺失改善', '檔案管理', '檢試驗管制', '水位監測',
           '自主檢查樣板庫', '通知', '工程進度'} <= set(portal_labels), portal_labels)
    backend_only = Mod.search([('show_in_portal', '=', False)]).mapped('name')
    check('後台專用 8 項不在前台顯示（契約管理、估驗計價…）', len(backend_only) == 8
          and {'契約管理', '估驗計價', '成本分析', '報表下載'} <= set(backend_only), backend_only)
    Cat = env['construction.service.category']
    ask = Cat.search([('ask_functional_module', '=', True)]).mapped('name')
    check('只有操作疑問、系統問題會詢問發生功能', set(ask) == {'操作疑問', '系統問題'}, ask)
    check('第 7 類名稱為「帳務查核問題」', env.ref('construction_helpdesk.category_billing_audit').name == '帳務查核問題')

    # ---------- 前台可讀的主檔 ----------
    check('前台可讀類別（8 類）', Cat.with_user(pu).search_count([]) == 8)
    check('前台可讀發生功能（14 項）', Mod.with_user(pu).search_count([('show_in_portal', '=', True)]) == 14)
    raises('前台不能改類別', AccessError, lambda: Cat.with_user(pu).search([], limit=1).write({'name': 'x'}))

    # ---------- 前台建單（controller 同樣以本人身分、nosubscribe 建立）----------
    cat_sys = env.ref('construction_helpdesk.category_system_problem')
    mod_log = env.ref('construction_helpdesk.module_daily_log')
    vals = {
        'subject': 'ZZ 前台：施工日誌存檔錯誤', 'description': '<p>按存檔跳錯</p>',
        'category_id': cat_sys.id, 'functional_module_id': mod_log.id, 'channel': 'portal',
        'contact_name': pu.name, 'customer_company': company.name,
        'project_name': 'ZZ 工程', 'project_code': 'ZZ-001',
    }
    t = env[T].with_user(pu).with_context(mail_create_nosubscribe=True).create(vals)
    check('前台可建立服務單、狀態新建、管道前台', t.state == 'new' and t.channel == 'portal' and t.name.startswith('SRV-'))
    check('客戶公司（文字）＝前台帳號所屬公司名稱', t.customer_company == company.name)
    check('建單的前台帳號不是追蹤者（不寄 Email）', pu.partner_id not in t.message_partner_ids,
          t.message_partner_ids.mapped('name'))

    msg0 = t.with_user(pu).message_post(
        body='建單時附上的檔案', attachments=[('shot.png', b'fakepng')],
        message_type='comment', subtype_xmlid='mail.mt_comment')
    check('前台建單時可附檔（以留言形式）', msg0.attachment_ids and msg0.author_id == pu.partner_id)
    check('前台留言後仍不是追蹤者', pu.partner_id not in t.message_partner_ids)

    # ---------- 可見範圍與寫入 ----------
    t2 = env[T].with_user(pu2).with_context(mail_create_nosubscribe=True).create(dict(vals, subject='ZZ 另一人'))
    check('前台只看得到自己送的', env[T].with_user(pu).search([('id', 'in', (t | t2).ids)]) == t)
    raises('前台讀不到別人送的', AccessError, lambda: t2.with_user(pu).read(['subject']))
    raises('前台不能改自己的單（新建也不行）', AccessError, lambda: t.with_user(pu).write({'subject': 'x'}))
    raises('前台不能刪單', AccessError, lambda: t.with_user(pu).unlink())
    raises('前台讀不到關聯問題單欄位', AccessError, lambda: t.with_user(pu).read(['problem_id']))
    raises('前台讀不到負責客服', AccessError, lambda: t.with_user(pu).read(['agent_user_id']))
    raises('前台讀不到系統問題單', AccessError,
           lambda: env['construction.problem'].with_user(pu).search([]))
    raises('前台不能在別人的單留言', AccessError,
           lambda: t2.with_user(pu).message_post(body='x', message_type='comment'))

    # ---------- 對話：客服「傳送訊息」客戶看得到、「記錄備註」看不到 ----------
    t.with_user(u_agent).action_start()
    m_msg = t.with_user(u_agent).message_post(body='ZZ 客服回覆：已收到', message_type='comment',
                                                subtype_xmlid='mail.mt_comment')
    m_note = t.with_user(u_agent).message_post(body='ZZ 內部備註：疑似 S1', message_type='comment',
                                                 subtype_xmlid='mail.mt_note')
    seen = env['mail.message'].with_user(pu).search([('model', '=', T), ('res_id', '=', t.id)])
    check('客服「傳送訊息」客戶看得到', m_msg in seen)
    check('客服「記錄備註」客戶看不到', m_note not in seen)
    thread = env[T].with_user(pu)._get_thread_with_access(t.id, mode=env[T]._mail_post_access)
    check('前台 chatter 的存取檢查對建單人放行（處理中也可留言附檔）', thread == t)
    m_reply = t.with_user(pu).message_post(body='ZZ 客戶補充', message_type='comment',
                                           subtype_xmlid='mail.mt_comment')
    check('處理中客戶仍可留言', m_reply.author_id == pu.partner_id)
    raises('客戶不能修改自己的留言', UserError,
           lambda: t.with_user(pu)._message_update_content(m_reply, '<p>改</p>'))
    raises('客戶不能刪除自己的留言', UserError,
           lambda: t.with_user(pu)._message_update_content(m_reply, '', attachment_ids=[]))
    raises('客戶無法用 RPC 改留言', UserError, lambda: m_reply.with_user(pu).write({'body': 'x'}))

    # ---------- 客服端：前台送來的單照常處理 ----------
    seen_ag = env[T].with_user(u_agent).search([('id', 'in', (t | t2).ids)])
    check('客服看得到前台送來的單', seen_ag == (t | t2))
    raises('前台送來的單，客服也不能改回報內容', UserError,
           lambda: t.with_user(u_agent).write({'description': '<p>x</p>'}))
    t.with_user(u_agent).write({'category_id': env.ref('construction_helpdesk.category_operation_question').id})
    check('客服可以改客戶選錯的類別', t.category_id.name == '操作疑問')

    # ---------- 畫面 ----------
    for xmlid in ('construction_helpdesk.portal_feedback_list', 'construction_helpdesk.portal_feedback_new',
                  'construction_helpdesk.portal_feedback_detail', 'construction_helpdesk.portal_drawer_feedback'):
        check('QWeb 模板存在：%s' % xmlid.split('.')[1], env.ref(xmlid, raise_if_not_found=False))
    full = env.ref('construction_portal.portal_v10_drawer')._get_combined_arch()
    from lxml import etree
    xml = etree.tostring(full, encoding='unicode')
    check('抽屜已換成真入口（/construction/feedback），佔位 alert 已移除',
          '/construction/feedback' in xml and '意見回饋即將推出' not in xml)
    for model, views in ((T, ('list', 'form', 'search')), ('construction.functional.module', ('list', 'search')),
                         ('construction.service.category', ('list',))):
        try:
            env[model].with_user(u_agent).get_views([(False, v) for v in views])
            check('get_views %s' % model, True)
        except Exception as e:
            check('get_views %s' % model, False, repr(e))
    bundle = env['ir.qweb']._get_asset_bundle('web.assets_backend')
    check('後台 bundle 含「傳送訊息」防呆 JS',
          any('ticket_send_confirm.js' in (f.get('url') or f.get('filename') or '') for f in bundle.files))
    fbundle = env['ir.qweb']._get_asset_bundle('web.assets_frontend')
    fnames = [(f.get('url') or f.get('filename') or '') for f in fbundle.files]
    check('前台 bundle 含意見回饋 JS、不含防呆 JS',
          any('portal_feedback.js' in n for n in fnames) and not any('ticket_send_confirm.js' in n for n in fnames))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT helpdesk_p4')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

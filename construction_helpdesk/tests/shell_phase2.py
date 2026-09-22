# -*- coding: utf-8 -*-
"""第二階段驗收：服務單（odoo shell 執行，全程 rollback，不留資料）。

echo 'exec(open("/mnt/extra-addons/construction_helpdesk/tests/shell_phase2.py", encoding="utf-8").read())' \
  | odoo shell -d system_development ... --no-http
"""
import base64
from odoo.exceptions import AccessError, UserError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, exc, fn):
    try:
        fn()
    except exc as e:
        results.append((True, name, type(e).__name__))
        return
    except Exception as e:
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


AGENT = 'construction_helpdesk.group_helpdesk_agent'
ADMIN_GRP = 'construction_supervision_base.group_supervisor_admin'
T = 'construction.service.ticket'

env.cr.execute('SAVEPOINT helpdesk_p2')
try:
    u_agent = env.ref('base.user_admin')
    u_op = env['res.users'].browse(6)
    u_sa = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ 只有系統管理者', 'login': 'zz_helpdesk_sa_only',
        'groups_id': [(6, 0, [env.ref(ADMIN_GRP).id])],
    })
    cat_sys = env.ref('construction_helpdesk.category_system_problem')
    cat_other = env.ref('construction_helpdesk.category_operation_question')
    partner = env['res.partner'].create({'name': 'ZZ 測試營造', 'is_company': True})

    # ---------- 建單 ----------
    t_op = env[T].with_user(u_op).create({'subject': 'ZZ 代操作員建的單', 'description': '<p>原始內容</p>'})
    check('代操作員建單成功、單號 SRV-', t_op.name.startswith('SRV-'), t_op.name)
    check('代操作員建單回報管道預設「內部回報」', t_op.channel == 'internal')
    check('新單狀態＝新建', t_op.state == 'new')
    dflt = env[T].with_user(u_agent).default_get(['channel'])
    check('客服建單時回報管道沒有預設值', not dflt.get('channel'), dflt)
    t_sa = env[T].with_user(u_sa).create({'subject': 'ZZ 系統管理者建的單'})
    t_ag = env[T].with_user(u_agent).create({
        'subject': 'ZZ 客服代客戶登記', 'channel': 'line', 'customer_company': 'ZZ 測試營造',
        'contact_name': '王小明 0912-000-000',
        'category_id': cat_sys.id,
    })

    # ---------- 可見範圍 ----------
    ids_all = (t_op | t_sa | t_ag).ids
    seen_op = env[T].with_user(u_op).search([('id', 'in', ids_all)])
    seen_sa = env[T].with_user(u_sa).search([('id', 'in', ids_all)])
    seen_ag = env[T].with_user(u_agent).search([('id', 'in', ids_all)])
    check('代操作員只看得到自己的', seen_op == t_op, seen_op.mapped('name'))
    check('只有系統管理者的帳號只看得到自己的', seen_sa == t_sa, seen_sa.mapped('name'))
    check('客服看得到全部', seen_ag == (t_op | t_sa | t_ag))
    raises('代操作員讀不到別人的單', AccessError, lambda: t_sa.with_user(u_op).read(['subject']))

    # ---------- 新建階段 ----------
    t_op.with_user(u_op).write({'subject': 'ZZ 代操作員建的單（改）', 'category_id': cat_other.id})
    check('新建階段建單人可改回報內容與類別', t_op.subject.endswith('（改）') and t_op.category_id == cat_other)
    raises('代操作員不能刪單', AccessError, lambda: t_op.with_user(u_op).unlink())
    raises('代操作員不能改狀態', UserError, lambda: t_op.with_user(u_op).write({'state': 'processing'}))
    raises('代操作員不能按「開始處理」', UserError, lambda: t_op.with_user(u_op).action_start())

    # ---------- 客服開始處理 ----------
    t_op.with_user(u_agent).action_start()
    check('開始處理 → 處理中、負責客服自動帶入',
          t_op.state == 'processing' and t_op.agent_user_id == u_agent)

    # ---------- 送出後：回報內容任何人不可改 ----------
    # 先攔下的是 write() 的回報內容鎖定（UserError，訊息較清楚），不是 record rule；兩者都算擋下
    raises('處理中：建單人改主旨被擋', UserError,
           lambda: t_op.with_user(u_op).write({'subject': 'x'}))
    raises('處理中：建單人改類別也被擋', AccessError,
           lambda: t_op.with_user(u_op).write({'category_id': cat_sys.id}))
    raises('處理中：客服改主旨被擋', UserError, lambda: t_op.with_user(u_agent).write({'subject': 'x'}))
    raises('處理中：客服改內容被擋', UserError, lambda: t_op.with_user(u_agent).write({'description': '<p>x</p>'}))
    raises('處理中：客服改回報時間被擋', UserError,
           lambda: t_op.with_user(u_agent).write({'report_datetime': '2026-01-01 00:00:00'}))
    t_op.with_user(u_agent).write({'category_id': cat_sys.id, 'notify_result': '已電話告知'})
    check('處理中：客服可改類別與通知結果', t_op.category_id == cat_sys and t_op.notify_result == '已電話告知')

    # ---------- 送出後：建單人仍可留言、附檔 ----------
    thread = env[T].with_user(u_op)._get_thread_with_access(t_op.id, mode=env[T]._mail_post_access)
    check('附件上傳的存取檢查對建單人放行（mode=read）', thread == t_op)
    msg = t_op.with_user(u_op).message_post(
        body='補充：截圖如附件', message_type='comment', subtype_xmlid='mail.mt_comment',
        attachments=[('screen.txt', b'fake screenshot')])
    check('處理中：建單人可留言並附檔', msg and msg.attachment_ids and msg.author_id == u_op.partner_id,
          msg.attachment_ids.mapped('name'))
    raises('代操作員不能在別人的單留言', AccessError,
           lambda: t_sa.with_user(u_op).message_post(body='x', message_type='comment'))

    # ---------- 留言不能改、不能刪 ----------
    raises('作者本人編輯留言被擋', UserError,
           lambda: t_op.with_user(u_op)._message_update_content(msg, '<p>改過</p>'))
    raises('客服／管理員編輯留言被擋', UserError,
           lambda: t_op.with_user(u_agent)._message_update_content(msg.with_user(u_agent), '<p>改過</p>'))
    raises('作者本人從畫面刪除留言（body 清空）被擋', UserError,
           lambda: t_op.with_user(u_op)._message_update_content(msg, '', attachment_ids=[]))
    raises('RPC 直接改 mail.message 內容被擋（客服）', UserError,
           lambda: msg.with_user(u_agent).write({'body': '<p>改過</p>'}))
    raises('RPC 直接刪 mail.message 被擋（客服）', UserError, lambda: msg.with_user(u_agent).unlink())
    # Odoo 的 AccessError 是 UserError 的子類別，兩種都算擋下
    raises('RPC 直接刪 mail.message 被擋（作者）', UserError, lambda: msg.with_user(u_op).unlink())
    msg.with_user(u_op).toggle_message_starred()
    check('標星號（不改內容）照常可用', u_op.partner_id in msg.starred_partner_ids)
    check('留言內容仍是原文', 'fake' not in (msg.body or '') and '補充' in (msg.body or ''))

    # 其他模型不受影響：代操作員在工程案件上留言後可自行編輯
    proj = env['project.project'].search([], limit=1)
    pmsg = proj.with_user(u_op).message_post(body='ZZ 其他模型留言', message_type='comment',
                                             subtype_xmlid='mail.mt_note')
    proj.with_user(u_op)._message_update_content(pmsg, '<p>ZZ 其他模型留言（改）</p>')
    check('其他模型的留言照常可由作者編輯（未改成全域行為）', '（改）' in pmsg.body)

    # ---------- 欄位層級限制 ----------
    raises('代操作員讀不到「負責客服」', AccessError, lambda: t_op.with_user(u_op).read(['agent_user_id']))
    raises('代操作員讀不到「滿意度」', AccessError, lambda: t_op.with_user(u_op).read(['satisfaction']))
    raises('代操作員無法用「負責客服」自訂分組', AccessError,
           lambda: env[T].with_user(u_op).read_group([], ['subject'], ['agent_user_id']))
    fg = env[T].with_user(u_op).fields_get()
    check('代操作員的欄位清單（自訂篩選／匯出來源）沒有客服欄位',
          not ({'agent_user_id', 'notify_datetime', 'notify_result', 'satisfaction', 'customer_feedback'} & set(fg)))
    arch_op = env[T].with_user(u_op).get_views([(False, 'form')])['views']['form']['arch']
    check('代操作員的表單沒有狀態按鈕與客服頁籤',
          'action_start' not in arch_op and 'agent_user_id' not in arch_op and 'satisfaction' not in arch_op)
    arch_ag = env[T].with_user(u_agent).get_views([(False, 'form')])['views']['form']['arch']
    check('客服的表單有狀態按鈕與客服頁籤', 'action_start' in arch_ag and 'satisfaction' in arch_ag)
    check('表單：送出後建單人（非客服）不能改類別與發生功能',
          arch_ag.count("readonly=\"state != 'new' and not is_helpdesk_agent\"") == 2, arch_ag.count('is_helpdesk_agent'))
    check('目前使用者是否為客服：客服 True、代操作員 False',
          t_op.with_user(u_agent).is_helpdesk_agent and not t_op.with_user(u_op).is_helpdesk_agent)
    check('表單：類別必填、發生功能只在「詢問發生功能」的類別出現',
          'name="category_id"' in arch_ag and 'invisible="not ask_functional_module"' in arch_ag)
    check('表單：客戶公司、聯絡人是文字欄位', env[T]._fields['customer_company'].type == 'char'
          and env[T]._fields['contact_name'].type == 'char' and 'partner_id' not in env[T]._fields)
    from odoo.tests import Form
    f = Form(env[T].with_user(u_agent))
    f.subject = 'ZZ onchange'
    f.channel = 'phone'
    f.category_id = env.ref('construction_helpdesk.category_system_problem')
    f.functional_module_id = env.ref('construction_helpdesk.module_daily_log')
    f.category_id = env.ref('construction_helpdesk.category_billing_invoice')
    check('類別改成帳務類 → 發生功能自動清空', not f.functional_module_id)

    # ---------- 狀態流程 ----------
    t_op.with_user(u_agent).action_wait_customer()
    check('處理中 → 待客戶確認', t_op.state == 'waiting_customer')
    t_op.with_user(u_agent).action_done()
    check('結案並記下結案時間', t_op.state == 'done' and t_op.close_datetime)
    t_op.with_user(u_agent).action_reopen()
    check('重新處理 → 處理中、清掉結案時間', t_op.state == 'processing' and not t_op.close_datetime)
    raises('狀態不對時按鈕被擋', UserError, lambda: t_op.with_user(u_agent).action_start())

    # ---------- 客服刪整張單（連帶清訊息）----------
    mid = msg.id
    t_op.with_user(u_agent).unlink()
    check('客服可刪整張服務單，留言一併清除', not t_op.exists() and not env['mail.message'].browse(mid).exists())

    # ---------- 選單 ----------
    vis_op = env['ir.ui.menu'].with_user(u_op)._visible_menu_ids()
    check('代操作員看得到「服務單」選單', env.ref('construction_helpdesk.menu_service_ticket').id in vis_op)

    # ---------- get_views ----------
    for user, label in ((u_agent, '客服'), (u_op, '代操作員'), (u_sa, '只有系統管理者')):
        try:
            env[T].with_user(user).get_views([(False, v) for v in ('list', 'form', 'search', 'pivot', 'graph')])
            check('get_views 服務單（%s）' % label, True)
        except Exception as e:
            check('get_views 服務單（%s）' % label, False, repr(e))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT helpdesk_p2')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

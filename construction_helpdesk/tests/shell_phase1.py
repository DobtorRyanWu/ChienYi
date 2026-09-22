# -*- coding: utf-8 -*-
"""第一階段驗收（odoo shell 執行，全程 rollback，不留資料）。

docker exec pg18-odoo bash -lc 'odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=warn < /mnt/extra-addons/construction_helpdesk/tests/shell_phase1.py'
"""
from odoo.exceptions import AccessError, UserError, ValidationError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, exc, fn):
    try:
        fn()
    except exc as e:
        results.append((True, name, type(e).__name__))
        return
    except Exception as e:  # 型別不對也算失敗
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


AGENT = 'construction_helpdesk.group_helpdesk_agent'
ADMIN_GRP = 'construction_supervision_base.group_supervisor_admin'

env.cr.execute('SAVEPOINT helpdesk_p1')
try:
    agent_group = env.ref(AGENT)
    # ---------- 群組 ----------
    check('客服群組不在下拉分類（無 category）', not agent_group.category_id)
    check('「設定」implied 客服', agent_group in env.ref('base.group_system').implied_ids)
    u_admin = env.ref('base.user_admin')
    u_op = env['res.users'].browse(6)
    check('uid2（設定）擁有客服', u_admin.has_group(AGENT))
    check('uid6（代操作員）沒有客服', u_op.has_group('construction_supervision_base.group_operator') and not u_op.has_group(AGENT))

    # 臨時帳號：只有系統管理者、沒有設定
    u_sa = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ 只有系統管理者', 'login': 'zz_helpdesk_sa_only',
        'groups_id': [(6, 0, [env.ref(ADMIN_GRP).id])],
    })
    check('臨時帳號：有系統管理者、沒有設定、沒有客服',
          u_sa.has_group(ADMIN_GRP) and not u_sa.has_group('base.group_system') and not u_sa.has_group(AGENT))

    Cat = env['construction.service.category']
    Mod = env['construction.functional.module']
    Sla = env['construction.problem.sla']
    # 測試用預設值（rollback，不影響使用者在後台改過的數字）
    env.ref('construction_helpdesk.sla_p1').write({'default_fix_days': 2})
    env.ref('construction_helpdesk.sla_p2').write({'default_fix_days': 5})

    # ---------- 預設資料 ----------
    check('預設 8 個類別', Cat.search_count([]) == 8, Cat.search_count([]))
    sys_cat = env.ref('construction_helpdesk.category_system_problem')
    check('系統問題類恰好一個', Cat.with_context(active_test=False).search_count([('is_system_problem', '=', True)]) == 1)
    check('預設 22 個發生功能（14 前台＋8 後台專用）', Mod.search_count([]) == 22
          and Mod.search_count([('show_in_portal', '=', False)]) == 8, Mod.search_count([]))
    check('「進度管理」前台顯示為「工程進度」',
          env.ref('construction_helpdesk.module_progress').get_portal_label() == '工程進度')
    check('名稱以後台為主（照片管理＝前台照片中心、缺失管理＝缺失改善、文件管理＝檔案管理）',
          env.ref('construction_helpdesk.module_photo').name == '照片管理'
          and env.ref('construction_helpdesk.module_photo').get_portal_label() == '照片中心'
          and env.ref('construction_helpdesk.module_defect').get_portal_label() == '缺失改善'
          and env.ref('construction_helpdesk.module_file').get_portal_label() == '檔案管理')
    check('前台「工程列表」已併入「工程案件」（原筆封存）',
          not env.ref('construction_helpdesk.module_project_list').active
          and env.ref('construction_helpdesk.module_project_info').name == '工程案件')
    check('發生功能名稱依後台選單（契約管理、報表下載…）',
          {'契約管理', '送審管制', '計畫書管制', '人機管理', '成本分析', '即時損益', '報表下載'}
          <= set(Mod.search([('show_in_portal', '=', False)]).mapped('name')))
    slas = Sla.search([])
    check('時限設定 4 筆', len(slas) == 4)
    check('P1=2、P2=5、P3/P4=0',
          [s.default_fix_days for s in slas.sorted('priority')] == [2, 5, 0, 0],
          [s.default_fix_days for s in slas.sorted('priority')])
    check('get_default_fix_days(p1)=2', Sla.get_default_fix_days('p1') == 2)
    p1r, p3r = env.ref('construction_helpdesk.sla_p1'), env.ref('construction_helpdesk.sla_p3')
    check('修復時限說明依天數自動產生（P1＝2 個工作天、P3＝下一次例行版本）',
          p1r.fix_limit_note == '2 個工作天' and p3r.fix_limit_note == '下一次例行版本',
          (p1r.fix_limit_note, p3r.fix_limit_note))
    p1r.write({'default_fix_days': 3})
    check('天數改 3 → 說明自動變成 3 個工作天', p1r.fix_limit_note == '3 個工作天', p1r.fix_limit_note)
    p1r.write({'default_fix_days': 2})
    sla_arch = Sla.get_views([(False, 'list')])['views']['list']['arch']
    check('處理時限設定清單不是直接編輯（點一列開表單看修改紀錄）', 'editable' not in sla_arch)
    # 先把「測試用預設值」寫入的修改紀錄推出去，下面的 2→3 才看得清楚
    env.cr.precommit.run()

    # ---------- 系統問題類別保護 ----------
    raises('系統問題類不可刪除', UserError, lambda: sys_cat.unlink())
    raises('系統問題類不可封存', UserError, lambda: sys_cat.write({'active': False}))
    raises('系統問題類不可取消旗標', UserError, lambda: sys_cat.write({'is_system_problem': False}))
    raises('不可再建第二個系統問題類', ValidationError,
           lambda: Cat.create({'name': 'ZZ 第二個系統問題', 'is_system_problem': True}))
    other = env.ref('construction_helpdesk.category_other')
    other.write({'active': False})
    check('一般類別可以封存', not other.active)
    tmp = Cat.create({'name': 'ZZ 可刪類別'})
    tmp.unlink()
    check('一般類別可以刪除', not tmp.exists())

    # ---------- 權限：代操作員（uid6）----------
    raises('代操作員不可改類別', AccessError, lambda: Cat.with_user(u_op).browse(sys_cat.id).write({'name': 'x'}))
    check('代操作員可讀類別', Cat.with_user(u_op).search_count([]) >= 1)
    check('代操作員可讀功能模組', Mod.with_user(u_op).search_count([]) >= 1)
    raises('代操作員讀不到時限設定', AccessError, lambda: Sla.with_user(u_op).search([]).read(['default_fix_days']))
    raises('只有系統管理者的帳號讀不到時限設定', AccessError,
           lambda: Sla.with_user(u_sa).search([]).read(['default_fix_days']))

    # ---------- 權限：客服（uid2）----------
    p1 = env.ref('construction_helpdesk.sla_p1')
    # ⚠️ 修改紀錄的測試必須排在「刪除被擋」之前：mail.thread.unlink() 會先 _track_discard()
    #    再檢查權限，同一交易內之後對該筆的修改就不再被追蹤（實際使用時整個請求會 rollback，無此問題）
    Sla.with_user(u_admin).browse(p1.id).write({'default_fix_days': 3})
    # tracking 是在 commit 前（precommit）才寫成 chatter 訊息；測試不 commit，要手動觸發
    env.cr.precommit.run()
    env.flush_all()
    env.cr.execute("""
        SELECT tv.old_value_integer, tv.new_value_integer, m.author_id
          FROM mail_tracking_value tv
          JOIN mail_message m ON m.id = tv.mail_message_id
          JOIN ir_model_fields f ON f.id = tv.field_id
         WHERE m.model = 'construction.problem.sla' AND m.res_id = %s
           AND f.name = 'default_fix_days'
         ORDER BY tv.id DESC LIMIT 1
    """, (p1.id,))
    row = env.cr.fetchone()
    check('時限設定修改留下修改紀錄（chatter，2→3）', row and row[0] == 2 and row[1] == 3, row)
    check('修改紀錄記下是誰改的', row and row[2] == u_admin.partner_id.id, row)
    raises('天數不可為負', ValidationError, lambda: p1.write({'default_fix_days': -1}))
    raises('客服不可新增時限設定', AccessError,
           lambda: Sla.with_user(u_admin).create({'priority': 'p1'}))
    raises('客服不可刪除時限設定', AccessError, lambda: Sla.with_user(u_admin).browse(p1.id).unlink())

    # ---------- 選單可見性 ----------
    Menu = env['ir.ui.menu']
    cfg = env.ref('construction_helpdesk.menu_helpdesk_config')
    sla_menu = env.ref('construction_helpdesk.menu_problem_sla')
    vis_op = Menu.with_user(u_op)._visible_menu_ids()
    vis_ad = Menu.with_user(u_admin)._visible_menu_ids()
    check('代操作員看不到「設定」選單', cfg.id not in vis_op and sla_menu.id not in vis_op)
    check('客服看得到「處理時限設定」選單', sla_menu.id in vis_ad)

    # ---------- get_views ----------
    for model in ('construction.service.category', 'construction.functional.module',
                  'construction.problem.sla'):
        try:
            env[model].get_views([(False, 'list'), (False, 'form'), (False, 'search')])
            check('get_views %s' % model, True)
        except Exception as e:
            check('get_views %s' % model, False, repr(e))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT helpdesk_p1')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed or detail else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

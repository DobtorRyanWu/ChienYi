# -*- coding: utf-8 -*-
"""第二階段驗收：系統版本、版本清單、部署檢查、問題單修復版本（全程 rollback，不留資料）。

docker exec pg18-odoo bash -lc 'echo "exec(open(\"/mnt/extra-addons/construction_release/tests/shell_phase2.py\").read())" | odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=warn'
"""
from datetime import date, timedelta

from odoo import fields, release
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.construction_release.models.module_version import custom_module_names

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, fn, exc=Exception):
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc as e:
        results.append((True, name, '%s: %s' % (type(e).__name__, str(e).splitlines()[0][:80])))
        return
    except Exception as e:
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


env.cr.execute('SAVEPOINT release_p2')
try:
    # ------------------------------------------------------------------
    # 與資料庫裡既有的版本／紀錄隔離
    # ⚠️ 測試不能假設資料庫是空的：使用者自己在做手動測試時，庫裡就會有版本與更新紀錄，
    #    會讓「v1.0.0 已經用過了」「橫幅抓到別人那一筆」這種假失敗。
    #    這裡在 savepoint 內用 SQL 清空，結束時整個 rollback，使用者的資料不受影響。
    # ------------------------------------------------------------------
    for _t in ('construction_deployment_line', 'construction_deployment',
               'construction_release_manifest_line', 'construction_release_entry_line',
               'construction_release_entry_problem_rel', 'construction_release_entry',
               'construction_release_read_user_rel', 'construction_release'):
        env.cr.execute('DELETE FROM %s' % _t)
    env.invalidate_all()
    admin = env.ref('base.user_admin')
    u_op = env['res.users'].browse(6)
    Rel = env['construction.release'].with_user(admin)
    Entry = env['construction.release.entry'].with_user(admin)
    Module = env['ir.module.module']
    pay = Module.search([('name', '=', 'construction_payment')])
    qual = Module.search([('name', '=', 'construction_quality')])
    check('前提：庫內沒有任何系統版本', not Rel.search_count([]))

    seq = [0]

    def new_entry(module=pay, announce='yes', change='同日多期估驗的累計會正確加總', **kw):
        seq[0] += 1
        prev = env['construction.release.entry.line'].sudo()._previous_line(module.name)
        before = prev.version_after if prev else '18.0.1.0.0'
        b = [int(x) for x in before.split('.')]
        after = '18.0.%d.%d.%d' % (b[2], b[3], b[4] + 1)
        v = {'entry_type': 'fix', 'title': '測試紀錄 %d' % seq[0], 'reason': '原因', 'change': change,
             'method': '做法', 'commits': '07258fb', 'announce': announce,
             'line_ids': [(0, 0, {'module_id': module.id, 'version_before': before, 'version_after': after})]}
        v.update(kw)
        return Entry.create(v)

    # ---------- 沒有草稿時登記：維持未排入 ----------
    e0 = new_entry(title='無草稿時登記')
    check('沒有草稿 → 紀錄維持未排入', not e0.release_id)

    # ---------- 草稿 ----------
    r1 = Rel.create({})
    check('新版本預設為草稿、沒有版號', r1.state == 'draft' and not r1.name)
    check('顯示「下一版（未定預計發布日）」', r1.display_name == '下一版（未定預計發布日）', r1.display_name)
    r1.planned_date = date(2026, 10, 1)
    check('顯示「下一版（預計 10/01）」', r1.display_name == '下一版（預計 10/01）', r1.display_name)
    check('建立草稿不會自動吃掉既有紀錄（要按帶入）', not e0.release_id)
    raises('同時第二個草稿 → 擋', lambda: Rel.create({}), ValidationError)

    r1.action_pull_entries()
    check('「帶入未排入的紀錄」→ 放進草稿', e0.release_id == r1)
    e1 = new_entry()
    check('有草稿時登記 → 自動放進草稿', e1.release_id == r1)
    e_no = new_entry(announce='no', change='不公告的調整')
    raises('使用者直接改「所屬系統版本」→ 擋', lambda: e1.write({'release_id': False}), UserError)
    e0.action_remove_from_release()
    check('「移出」→ 回到未排入', not e0.release_id and e0 not in r1.entry_ids)
    check('草稿中紀錄可修改', e1.write({'title': '改標題'}) and e1.title == '改標題')

    # ---------- 問題單修復版本 ----------
    prb = env['construction.problem'].create({'title': 'ZZ 測試問題單'})
    check('沒有關聯的問題單 → 「沒有關聯的更新紀錄」', prb.fix_release_display == '沒有關聯的更新紀錄',
          prb.fix_release_display)
    e0.problem_ids = [(4, prb.id)]
    check('關聯到未排入的紀錄 → 「尚未排入版本」', prb.fix_release_display == '尚未排入版本' and not prb.fix_release_id,
          prb.fix_release_display)
    e1.problem_ids = [(4, prb.id)]
    check('關聯到草稿中的紀錄 → 修復版本＝草稿（stored）', prb.fix_release_id == r1)
    check('顯示「下一版（草稿，預計 10/01）」', prb.fix_release_display == '下一版（草稿，預計 10/01）',
          prb.fix_release_display)
    r1.planned_date = date(2026, 10, 3)
    check('延期只改版本一處 → 問題單跟著變', prb.fix_release_display == '下一版（草稿，預計 10/03）',
          prb.fix_release_display)
    r1.planned_date = date(2026, 10, 1)

    # ---------- 公告草稿 ----------
    r1.action_generate_announcement()
    check('公告只收「要公告」的紀錄、取「改變」欄',
          r1.announce_body == '・同日多期估驗的累計會正確加總' and '不公告' not in (r1.announce_body or ''),
          r1.announce_body)

    # ---------- 確認 ----------
    check('第一版：三種跳法都指向 v1.0.0', set(r1._candidate_names().values()) == {'v1.0.0'},
          r1._candidate_names())
    check('全是修正 → 建議小版本', r1._suggest_bump() == 'patch')
    act = r1.action_open_confirm_wizard()
    wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(act['res_id'])
    check('確認精靈預填建議版號 v1.0.0', wiz.version_name == 'v1.0.0' and wiz.bump == 'patch', wiz.version_name)
    check('精靈顯示目前最新版號（還沒發過）', wiz.last_version == '還沒發布過任何版本', wiz.last_version)
    wiz.version_name = 'v1.0'
    raises('版號格式不對（少一段）→ 擋', wiz.action_confirm, UserError)
    wiz.version_name = 'v1.0.0.1'
    raises('版號格式不對（四段）→ 擋', wiz.action_confirm, UserError)
    wiz.version_name = '1.0.0'
    wiz.action_confirm()
    check('沒打 v 也接受，存成 v1.0.0', r1.name == 'v1.0.0', r1.name)
    check('確認 → 已確認、確認人', r1.state == 'confirmed'
          and r1.confirm_user_id == admin and r1.confirm_datetime)
    names = custom_module_names()
    ml = r1.manifest_line_ids
    check('版本清單＝自有＋第三方全部模組（含未安裝）＋ Odoo 本體一行',
          len(ml) == len(names) + 1 and 'web_responsive' in ml.mapped('module_name'), (len(ml), len(names)))
    core = ml.filtered('is_core')
    check('Odoo 本體一行＝odoo.release.version', core.version == release.version, core.version)
    pl = ml.filtered(lambda l: l.module_name == 'construction_payment')
    check('清單版號取程式檔（installed_version）', pl.version == pay.installed_version, pl.version)
    check('清單不含 Odoo 內建模組', 'mail' not in ml.mapped('module_name'))

    # ---------- 確認即鎖 ----------
    check('紀錄顯示已鎖定', e1.is_locked)
    raises('鎖定：改紀錄 → 擋', lambda: e1.write({'title': '再改'}), UserError)
    raises('鎖定：改受影響模組 → 擋', lambda: e1.line_ids.write({'version_after': '18.0.9.9.9'}), UserError)
    raises('鎖定：新增受影響模組 → 擋', lambda: env['construction.release.entry.line'].with_user(admin).create({
        'entry_id': e1.id, 'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.5.0'}),
        UserError)
    raises('鎖定：刪紀錄 → 擋', e1.unlink, UserError)
    raises('鎖定：移出 → 擋', e1.action_remove_from_release, UserError)
    check('確認後的顯示「v1.0.0（已確認，尚未發布）」', prb.fix_release_display == 'v1.0.0（已確認，尚未發布）',
          prb.fix_release_display)
    e_later = new_entry(title='確認後才登記')
    check('確認後、沒有草稿時登記 → 未排入（不會掉進已確認的版本）', not e_later.release_id)
    raises('已確認的版本不能刪', r1.unlink, UserError)

    # ---------- 退回草稿 ----------
    r1.action_back_to_draft()
    check('退回草稿 → 清掉版號、版本清單，紀錄解鎖',
          r1.state == 'draft' and not r1.name and not r1.manifest_line_ids and not e1.is_locked)
    wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(
        r1.action_open_confirm_wizard()['res_id'])
    wiz.action_confirm()
    check('再確認一次 → 版號重新編（仍是 v1.0.0）', r1.name == 'v1.0.0', r1.name)

    # ---------- 維護預告 ----------
    raises('沒填時間就發布預告 → 擋', r1.action_maint_announce, UserError)
    now = fields.Datetime.now()
    raises('結束早於開始 → 擋', lambda: r1.write({'maint_start': now, 'maint_end': now - timedelta(hours=1)}),
           ValidationError)
    r1.write({'maint_start': now, 'maint_end': now + timedelta(hours=1)})
    check('預告內容有預設文字', '屬正常現象' in (r1.maint_message or ''))
    r1.action_maint_announce()
    check('發布維護預告 → 已發布預告', r1.maint_state == 'announced')
    raises('已發布預告時退回草稿 → 擋（先取消預告）', r1.action_back_to_draft, UserError)

    # ---------- 部署檢查 ----------
    raises('沒有部署紀錄就發布 → 擋', r1.action_publish, UserError)
    dep_ok = env['construction.deployment'].browse(r1.action_check_deployment()['res_id'])
    bad = dep_ok.line_ids.filtered(lambda l: l.result in ('mismatch', 'half', 'extra'))
    check('本庫目前狀態 → 相符', dep_ok.result == 'match' and not dep_ok.mismatch_count and not dep_ok.half_count,
          [(l.module_name, l.expected, l.actual, l.result) for l in bad][:5])
    check('部署紀錄記下資料庫名稱與檢查人', dep_ok.db_name == env.cr.dbname and dep_ok.user_id == admin)
    nl = dep_ok.line_ids.filtered(lambda l: l.module_name == 'web_responsive')
    check('未安裝的模組 → 本庫未安裝（不算問題）', nl.result == 'not_installed')

    # 故意製造：一個版號不符、一個升到一半、一個清單沒有
    with env.cr.savepoint() as sp:
        r1.sudo().manifest_line_ids.filtered(
            lambda l: l.module_name == 'construction_payment').version = '18.0.9.9.9'
        r1.sudo().manifest_line_ids.filtered(lambda l: l.module_name == 'construction_timeline').unlink()
        audit = Module.search([('name', '=', 'construction_audit')])
        audit.sudo().write({'state': 'to upgrade'})
        dep_bad = env['construction.deployment'].browse(r1.action_check_deployment()['res_id'])
        by = {l.module_name: l for l in dep_bad.line_ids}
        check('不符：結果＝不相符', dep_bad.result == 'mismatch')
        check('不符：版號不同的模組被抓到', by['construction_payment'].result == 'mismatch'
              and by['construction_payment'].actual == pay.latest_version)
        check('不符：升到一半的模組被抓到（to upgrade）',
              by['construction_audit'].result == 'half' and dep_bad.half_count == 1)
        check('不符：清單沒有但本庫有安裝 → 抓到', by['construction_timeline'].result == 'extra')
        check('不符：不相符數＝2（版號不同＋清單沒有）', dep_bad.mismatch_count == 2, dep_bad.mismatch_count)
        check('明細把問題排最前面', dep_bad.line_ids[0].result == 'half')
        check('不相符的紀錄不算放行發布', dep_bad not in r1._matching_deployments())
        raises('部署紀錄不可刪除', dep_bad.unlink, UserError)
        sp.rollback()

    # 發布前：公告內容空白且有「要公告」紀錄 → 擋
    r1.announce_body = False
    raises('有要公告的紀錄但公告內容空白 → 不能發布', r1.action_publish, UserError)
    r1.action_generate_announcement()
    check('確認後產生的公告標題帶版號', r1.announce_title == '系統更新公告 v1.0.0', r1.announce_title)

    # 退回草稿再確認 → 之前的部署檢查不算數
    r1.action_maint_cancel()
    check('取消維護預告', r1.maint_state == 'cancelled')
    r1.action_back_to_draft()
    wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(
        r1.action_open_confirm_wizard()['res_id'])
    wiz.action_confirm()
    r1.flush_recordset()
    check('退回草稿再確認 → 舊的相符紀錄不算數', not r1._matching_deployments())
    raises('舊紀錄不算數 → 不能發布', r1.action_publish, UserError)
    r1.action_generate_announcement()
    r1.action_check_deployment()

    # ---------- 發布 ----------
    r1.action_publish()
    check('發布 → 已發布、有發布時間', r1.state == 'published' and r1.publish_datetime)
    r2 = Rel.search([('state', '=', 'draft')])
    check('發布後自動建立下一版草稿', len(r2) == 1 and r2 != r1)
    check('下一版草稿自動帶入未排入的紀錄', e_later in r2.sudo().entry_ids and e0 in r2.sudo().entry_ids)
    local = fields.Datetime.context_timestamp(prb, r1.publish_datetime).strftime('%m/%d')
    check('問題單修復版本 → 取最新的版本（e0 在下一版草稿）', prb.fix_release_id == r2, prb.fix_release_display)
    e0.problem_ids = [(3, prb.id)]
    check('只剩已發布版本的紀錄 → 「v1.0.0（已發布 MM/DD）」',
          prb.fix_release_display == 'v1.0.0（已發布 %s）' % local, prb.fix_release_display)
    raises('已發布：改公告 → 擋', lambda: r1.write({'announce_title': 'x'}), UserError)
    raises('已發布：退回草稿 → 擋', r1.action_back_to_draft, UserError)
    raises('已發布：刪除 → 擋', r1.unlink, UserError)
    raises('已發布版本的紀錄仍鎖定', lambda: e1.write({'title': 'x'}), UserError)

    # ---------- 改前版號預設：上一版清單 ----------
    ql = r1.sudo().manifest_line_ids.filtered(lambda l: l.module_name == 'construction_quality')
    ql.version = '18.0.6.3.0'
    d = env['construction.release.entry.line'].sudo()._default_version_before(qual)
    check('沒有上一筆紀錄 → 取最近一版清單的版號（不是資料庫）', d == '18.0.6.3.0', d)

    # ---------- 第二版的三種跳法 ----------
    r2.planned_date = date(2026, 10, 20)
    check('第二版：三種跳法各自的版號', r2._candidate_names() ==
          {'major': 'v2.0.0', 'minor': 'v1.1.0', 'patch': 'v1.0.1'}, r2._candidate_names())
    check('全是修正 → 建議小版本 v1.0.1', r2._suggest_name() == 'v1.0.1', r2._suggest_name())
    e_feat = new_entry(title='新功能一筆', entry_type='feature')
    check('有新功能 → 建議中版本 v1.1.0', r2._suggest_bump() == 'minor' and r2._suggest_name() == 'v1.1.0',
          r2._suggest_name())
    check('大版本永遠不自動建議', r2._suggest_bump() != 'major')
    wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(
        r2.action_open_confirm_wizard()['res_id'])
    check('精靈顯示目前最新版號 v1.0.0', wiz.last_version == 'v1.0.0', wiz.last_version)
    check('精靈建議依據寫出理由', '新功能' in (wiz.suggest_note or ''), wiz.suggest_note)
    wiz.bump = 'major'
    wiz._onchange_bump()
    check('選大版本 → 版號變 v2.0.0', wiz.version_name == 'v2.0.0', wiz.version_name)
    wiz.version_name = 'v1.0.0'
    raises('版號重複 → 擋', wiz.action_confirm, UserError)
    with env.cr.savepoint() as sp:
        r2.unlink()
        check('草稿可以刪；刪了紀錄回到未排入', not e_later.release_id and not e0.release_id)
        sp.rollback()

    # ---------- 權限 ----------
    # 第三階段起：內部使用者讀得到「已發布」的版本（公告回查頁要用），草稿與已確認的看不到
    op_visible = Rel.with_user(u_op).search([])
    check('代操作員只讀得到已發布的版本',
          all(r.state == 'published' for r in op_visible) and r2 not in op_visible,
          op_visible.mapped('state'))
    raises('代操作員讀不到版本裡的更新紀錄', lambda: r1.with_user(u_op).entry_ids, AccessError)
    raises('代操作員讀不到部署紀錄', lambda: env['construction.deployment'].with_user(u_op).search([]), AccessError)
    Menu = env['ir.ui.menu']
    vis = Menu.with_user(u_op)._visible_menu_ids()
    check('代操作員看不到系統版本／部署紀錄選單',
          env.ref('construction_release.menu_release').id not in vis
          and env.ref('construction_release.menu_deployment').id not in vis)
    agent = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ 只有客服', 'login': 'zz_release_agent',
        'groups_id': [(6, 0, [env.ref('base.group_user').id,
                              env.ref('construction_helpdesk.group_helpdesk_agent').id])]})
    check('只有客服的帳號：可讀修復版本文字', prb.with_user(agent).fix_release_display.startswith('v1.0.0'),
          prb.with_user(agent).fix_release_display)
    check('只有客服的帳號：讀得到版本名稱', r1.with_user(agent).name == 'v1.0.0')
    raises('只有客服的帳號：讀不到版本裡的更新紀錄', lambda: r1.with_user(agent).entry_ids, AccessError)
    raises('只有客服的帳號：讀不到更新紀錄', lambda: Entry.with_user(agent).search([]), AccessError)
    try:
        env['construction.problem'].with_user(agent).get_views([(False, 'form'), (False, 'list')])
        check('只有客服的帳號：問題單 get_views 正常', True)
    except Exception as e:
        check('只有客服的帳號：問題單 get_views 正常', False, repr(e))

    # ---------- get_views ----------
    for model, kinds in (('construction.release', ('list', 'form', 'search')),
                         ('construction.deployment', ('list', 'form', 'search')),
                         ('construction.problem', ('list', 'form')),
                         ('construction.release.entry', ('list', 'form', 'search')),
                         ('construction.release.confirm.wizard', ('form',))):
        try:
            env[model].with_user(admin).get_views([(False, k) for k in kinds])
            check('get_views %s' % model, True)
        except Exception as e:
            check('get_views %s' % model, False, repr(e))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT release_p2')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

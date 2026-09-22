# -*- coding: utf-8 -*-
"""第三、四階段驗收：更新公告（後台跳窗／前台跳窗／回查頁）與維護橫幅（全程 rollback）。

⚠️ 跳窗與橫幅「畫面上有沒有真的出現」程式測不到，最後要人工登入確認。
   這裡測的是資料層與版面掛點：誰該看到、誰不該看到、已讀何時寫入、
   模板有沒有真的掛進 web.frontend_layout 與抽屜。

docker exec pg18-odoo bash -lc 'echo "exec(open(\"/mnt/extra-addons/construction_release/tests/shell_phase34.py\").read())" | odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=warn'
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, fn, exc=Exception):
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc as e:
        results.append((True, name, '%s: %s' % (type(e).__name__, str(e).splitlines()[0][:60])))
        return
    except Exception as e:
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, e)))
        return
    results.append((False, name, 'did not raise'))


env.cr.execute('SAVEPOINT release_p34')
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

    def new_entry(**kw):
        vals = {'entry_type': 'fix', 'title': '測試紀錄', 'reason': '原因',
                'change': '同日多期估驗的累計會正確加總', 'method': '做法',
                'commits': '07258fb', 'announce': 'yes',
                'line_ids': [(0, 0, {'module_id': pay.id, 'version_before': '18.0.1.8.0',
                                     'version_after': '18.0.1.8.1'})]}
        vals.update(kw)
        return Entry.create(vals)

    # ---------- 造一個已發布的版本 ----------
    r1 = Rel.create({})
    new_entry()
    r1.action_pull_entries()
    r1.action_generate_announcement()
    wiz = env['construction.release.confirm.wizard'].with_user(admin).browse(
        r1.action_open_confirm_wizard()['res_id'])
    wiz.action_confirm()
    r1.action_generate_announcement()
    now = fields.Datetime.now()
    r1.write({'maint_start': now, 'maint_end': now + timedelta(hours=1)})
    r1.action_maint_announce()

    # ---------- 維護橫幅 ----------
    m = Rel._active_maintenance()
    check('已發布預告 → 有橫幅資料', m and m['id'] == r1.id, m)
    check('橫幅標題是預告時間', m and '系統維護預告' in m['headline'], m and m['headline'])
    check('橫幅帶預告內容', m and '屬正常現象' in m['message'])
    # 🔴 時區：橫幅要給「還沒登入的人」看，那時沒有使用者時區可用 →
    #    發布預告當下把時區存起來，不能用 context_timestamp（會變成 UTC）
    check('發布預告時記下時區', r1.maint_tz == admin.tz, r1.maint_tz)
    import pytz as _pytz
    from odoo import fields as _f
    expect = _pytz.utc.localize(r1.maint_start).astimezone(
        _pytz.timezone(r1.maint_tz)).strftime('%Y-%m-%d %H:%M')
    check('橫幅時間用預告時區換算（不是 UTC）', expect in m['headline'], (expect, m['headline']))
    with env.cr.savepoint() as sp:
        # 模擬未登入的使用者（沒有時區）讀橫幅：仍要顯示同一個牆上時間
        pub = env.ref('base.public_user')
        m_pub = env['construction.release'].with_user(pub)._active_maintenance()
        check('未登入也看到同一個時間', m_pub and expect in m_pub['headline'],
              m_pub and m_pub['headline'])
        sp.rollback()
    with env.cr.savepoint() as sp:
        r1.write({'maint_start': now - timedelta(hours=3), 'maint_end': now - timedelta(hours=1)})
        m2 = Rel._active_maintenance()
        check('過了預計結束時間仍未發布 → 橫幅繼續顯示、換句話說',
              m2 and m2['overrun'] and '仍在進行中' in m2['headline'], m2 and m2['headline'])
        sp.rollback()
    with env.cr.savepoint() as sp:
        r1.action_maint_cancel()
        check('取消維護預告 → 橫幅收起', Rel._active_maintenance() is None)
        sp.rollback()

    # ---------- 公告：發布前不跳 ----------
    check('還沒發布 → 沒有公告可跳', not Rel._unread_announcements(admin))
    r1.action_check_deployment()
    r1.action_publish()
    check('發布後 → 橫幅收起', Rel._active_maintenance() is None)

    # ---------- 後台跳窗資料 ----------
    notices = Rel.with_user(admin).get_startup_notices()
    check('admin 有一則未讀公告', len(notices['announcements']) == 1, notices['announcements'])
    a0 = notices['announcements'][0]
    check('公告內容＝標題、版號、發布日、內容',
          a0['version'] == r1.name and a0['title'] == r1.announce_title
          and a0['body'] == r1.announce_body and a0['publish_date'],
          a0)
    check('公告不含模組版號等內部資訊',
          set(a0) == {'id', 'version', 'title', 'body', 'publish_date'}, list(a0))
    check('代操作員也會跳', len(Rel.with_user(u_op).get_startup_notices()['announcements']) == 1)

    # ---------- 按「知道了」才算已讀 ----------
    check('只是查詢不算已讀', admin not in r1.read_user_ids)
    Rel.with_user(admin).mark_announcements_read([r1.id])
    check('按知道了 → 寫入已讀', admin in r1.read_user_ids)
    check('已讀後不再跳', not Rel.with_user(admin).get_startup_notices()['announcements'])
    check('前後台共用同一份已讀名單（同一個欄位）',
          'read_user_ids' in env['construction.release']._fields)
    check('別人沒按還是會跳', len(Rel.with_user(u_op).get_startup_notices()['announcements']) == 1)

    # ---------- 新帳號不會被歷史公告轟炸 ----------
    u_new = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ 新進人員', 'login': 'zz_release_new',
        'groups_id': [(6, 0, [env.ref('base.group_user').id])]})
    # ⚠️ create_date 用的是 PostgreSQL 的「交易開始時間」，而發布時間用的是真實時鐘，
    #    同一個交易裡新建的帳號 create_date 反而比發布時間早 → 這裡明寫成發布之後
    env.cr.execute("UPDATE res_users SET create_date = %s WHERE id = %s",
                   (r1.publish_datetime + timedelta(seconds=1), u_new.id))
    u_new.invalidate_recordset(['create_date'])
    check('帳號建立後才算 → 新帳號不跳歷史公告',
          not Rel.with_user(u_new).get_startup_notices()['announcements'])
    check('新帳號仍看得到維護橫幅欄位（目前沒有預告）',
          Rel.with_user(u_new).get_startup_notices()['maintenance'] is None)

    # ---------- 回查頁 ----------
    check('回查頁列出已發布公告（不限帳號建立日）', r1 in Rel._published_announcements())
    check('回查頁資料同樣只有四個欄位',
          set(Rel._announcement_payload(r1)[0]) == {'id', 'version', 'title', 'body', 'publish_date'})

    # ---------- 權限 ----------
    r_draft = Rel.search([('state', '=', 'draft')])
    check('代操作員讀得到已發布版本', Rel.with_user(u_op).search([]) == r1)
    check('代操作員讀不到草稿（record rule）', r_draft and r_draft not in Rel.with_user(u_op).search([]))
    raises('代操作員讀不到版本裡的更新紀錄（欄位層級）',
           lambda: r1.with_user(u_op).entry_ids, AccessError)
    raises('代操作員讀不到版本清單', lambda: r1.with_user(u_op).manifest_line_ids, AccessError)
    # 已發布的版本先被「內容定案」擋下（UserError），退一步也還有 record rule（AccessError）
    raises('代操作員改不了已發布的公告', lambda: r1.with_user(u_op).write({'announce_title': 'x'}))
    raises('代操作員改不了草稿（連看都看不到）',
           lambda: r_draft.with_user(u_op).write({'announce_title': 'x'}), AccessError)
    check('代操作員讀得到公告內容',
          r1.with_user(u_op).announce_title == r1.announce_title
          and r1.with_user(u_op).name == r1.name)

    # ---------- 選單 ----------
    Menu = env['ir.ui.menu']
    vis_op = Menu.with_user(u_op)._visible_menu_ids()
    check('代操作員看得到「更新公告」選單',
          env.ref('construction_release.menu_release_announcement_root').id in vis_op)
    check('代操作員看不到「版本管理」選單',
          env.ref('construction_release.menu_release_root').id not in vis_op)

    # ---------- 前台版面掛點 ----------
    arch = env.ref('web.frontend_layout').with_context(inherit_branding=False)._get_combined_arch()
    txt = arch if isinstance(arch, str) else str(arch)
    from lxml import etree
    txt = etree.tostring(arch, encoding='unicode') if not isinstance(arch, str) else arch
    check('維護橫幅掛進 web.frontend_layout', 'cy-maint-banner' in txt)
    check('公告跳窗掛進 web.frontend_layout', 'cyReleaseAnnouncement' in txt)
    check('橫幅在 main 之前（登入頁也看得到）', txt.index('cy-maint-banner') < txt.index('<main>'))
    drawer = env.ref('construction_portal.portal_v10_drawer')._get_combined_arch()
    dtxt = etree.tostring(drawer, encoding='unicode') if not isinstance(drawer, str) else drawer
    check('抽屜入口已換成更新公告', '/construction/announcements' in dtxt)
    check('抽屜不再有 v11.0 佔位', 'ChienYi Portal v11.0' not in dtxt)

    # ---------- 前台路由 ----------
    # shell 沒有 request，拿不到 routing map → 直接看 controller 上的路由宣告
    from odoo.addons.construction_release.controllers.portal_announcement import (
        ReleaseAnnouncementPortal)

    def routes_of(fn):
        r = getattr(fn, 'original_routing', None) or getattr(fn, 'routing', None) or {}
        return r.get('routes', [])

    check('前台回查頁路由存在',
          '/construction/announcements' in routes_of(ReleaseAnnouncementPortal.portal_announcement_list),
          routes_of(ReleaseAnnouncementPortal.portal_announcement_list))
    check('前台已讀路由存在（type=json）',
          '/construction/announcements/read' in routes_of(
              ReleaseAnnouncementPortal.portal_announcement_mark_read))

    # ---------- 前台回查頁模板 ----------
    # 整頁渲染會先卡在 portal_v10_header 需要 request（shell 沒有），
    # 那個錯誤與本模板無關卻會讓「渲染失敗」看起來像缺陷 → 改驗模板內容
    page = env.ref('construction_release.portal_announcement_list')._get_combined_arch()
    ptxt = etree.tostring(page, encoding='unicode') if not isinstance(page, str) else page
    check('回查頁沿用前台版面與頁首',
          'web.frontend_layout' in ptxt and 'construction_portal.portal_v10_header' in ptxt)
    check('回查頁顯示系統版本與發布日', "n['version']" in ptxt and "n['publish_date']" in ptxt)
    check('回查頁沒有任何模組版號欄位', 'manifest' not in ptxt and 'module' not in ptxt)

    # ---------- get_views ----------
    for user, label in ((admin, 'admin'), (u_op, '代操作員')):
        try:
            env['construction.release'].with_user(user).get_views(
                [(env.ref('construction_release.view_release_announcement_list').id, 'list'),
                 (env.ref('construction_release.view_release_announcement_form').id, 'form')])
            check('get_views 更新公告（%s）' % label, True)
        except Exception as e:
            check('get_views 更新公告（%s）' % label, False, repr(e))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT release_p34')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

# -*- coding: utf-8 -*-
"""第一階段驗收：更新紀錄（odoo shell 執行，全程 rollback，不留資料）。

⚠️ odoo shell 從 stdin 逐行執行，區塊內空行會截斷 → 一律用 exec(open(...).read())：
docker exec pg18-odoo bash -lc 'echo "exec(open(\"/mnt/extra-addons/construction_release/tests/shell_phase1.py\").read())" | odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=warn'
"""
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.construction_release.models.module_version import custom_module_names, parse_version

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, fn, exc=Exception):
    # 每個預期失敗的動作包在自己的 savepoint：SQL 錯誤會讓整個交易失效
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


env.cr.execute('SAVEPOINT release_p1')
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
    Entry = env['construction.release.entry'].with_user(admin)
    Line = env['construction.release.entry.line'].with_user(admin)
    Module = env['ir.module.module']
    pay = Module.search([('name', '=', 'construction_payment')])
    qual = Module.search([('name', '=', 'construction_quality')])

    # ---------- 模組範圍 ----------
    names = custom_module_names()
    check('範圍含自有模組', 'construction_payment' in names and 'construction_release' in names)
    check('範圍含第三方（非 construction_ 前綴）',
          all(n in names for n in ('dobtor_doc_editor', 'base_geoengine', 'spreadsheet_oca', 'web_leaflet_lib')))
    check('範圍含未安裝的模組（web_responsive）', 'web_responsive' in names)
    check('範圍不含 Odoo 內建（base／mail／project）', not {'base', 'mail', 'project'} & set(names), names[:5])

    # ---------- 版號解析 ----------
    check('parse 18.0.1.7.2', parse_version('18.0.1.7.2') == (1, 7, 2))
    check('parse 拒絕四段 18.0.1.8', parse_version('18.0.1.8') is None)
    check('parse 拒絕 17.0 開頭', parse_version('17.0.1.0.0') is None)
    check('版號用數字比較：1.10.0 > 1.9.0', parse_version('18.0.1.10.0') > parse_version('18.0.1.9.0'))

    # ---------- 是否公告沒有預設值 ----------
    defaults = Entry.default_get(['announce', 'user_id', 'date'])
    check('「是否公告」沒有預設值', not defaults.get('announce'), defaults)
    check('登記人預設目前使用者', defaults.get('user_id') == admin.id)

    base_vals = {
        'entry_type': 'fix', 'title': '同日多期估驗累計算錯',
        'reason': '同一天建立兩期估驗，第 2 期累計沒算進第 1 期，且不報錯',
        'change': '同日多期估驗的累計會依期別順序正確加總',
        'method': '改依日期＋建立順序取上一期',
        'commits': '07258fb, 3a91c2e', 'announce': 'yes',
    }

    def vals(**kw):
        v = dict(base_vals)
        v.update(kw)
        return v

    # ---------- 正常建立 ----------
    e1 = Entry.create(vals(date='2026-09-01', line_ids=[(0, 0, {
        'module_id': pay.id, 'version_before': '18.0.1.7.2', 'version_after': '18.0.1.8.0'})]))
    check('編號 UPD-xxxx', e1.name.startswith('UPD-') and len(e1.name) == 8, e1.name)
    check('模組名稱文字欄自動帶入', e1.line_ids.module_name == 'construction_payment')
    check('編號序號為 no_gap', env.ref('construction_release.seq_release_entry').implementation == 'no_gap')

    # ---------- 改前版號預設＝上一筆的改後 ----------
    e2 = Entry.create(vals(date='2026-09-05', title='第二筆', line_ids=[(0, 0, {
        'module_id': pay.id, 'version_after': '18.0.1.8.1'})]))
    check('改前預設＝上一筆的改後（18.0.1.8.0）', e2.line_ids.version_before == '18.0.1.8.0',
          e2.line_ids.version_before)
    check('接得起來 → 沒有不連續提醒', not e2.line_ids.continuity_warning and not e2.has_continuity_warning)

    # 沒有上一筆 → 退回資料庫版號（construction_quality 沒有任何紀錄）
    d = Line._default_version_before(qual)
    check('沒有上一筆 → 資料庫實際安裝版號', d == qual.latest_version, d)
    # 改後版號預設＝manifest（installed_version，名字相反）
    check('installed_version＝manifest、latest_version＝DB（兩者此刻相同）',
          qual.installed_version == qual.latest_version, (qual.installed_version, qual.latest_version))

    # 同一天兩筆：以建立順序（id）判斷上一筆
    e3 = Entry.create(vals(date='2026-09-05', title='同日第二筆', line_ids=[(0, 0, {
        'module_id': pay.id, 'version_after': '18.0.1.8.2'})]))
    check('同日：取 id 較小的那筆當上一筆', e3.line_ids.version_before == '18.0.1.8.1',
          e3.line_ids.version_before)

    # ---------- 不連續只警告不擋 ----------
    e4 = Entry.create(vals(date='2026-09-10', title='跳號', line_ids=[(0, 0, {
        'module_id': pay.id, 'version_before': '18.0.1.9.0', 'version_after': '18.0.2.0.0'})]))
    check('不連續可以存檔', e4.id)
    check('不連續有提醒且指出上一筆', e4.has_continuity_warning and e3.name in (e4.line_ids.continuity_warning or ''),
          e4.line_ids.continuity_warning)
    # 往前補登一筆較早的紀錄：不影響「之前的上一筆」判斷
    check('較早紀錄的上一筆不會抓到較晚的紀錄', e1.line_ids.continuity_warning is False or not e1.line_ids.continuity_warning)

    # ---------- 版號規則：擋 ----------
    raises('改後＝改前 → 擋', lambda: Entry.create(vals(line_ids=[(0, 0, {
        'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.4.0'})])), ValidationError)
    raises('改後＜改前 → 擋', lambda: Entry.create(vals(line_ids=[(0, 0, {
        'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.3.9'})])), ValidationError)
    raises('版號格式四段 → 擋', lambda: Entry.create(vals(line_ids=[(0, 0, {
        'module_id': qual.id, 'version_before': '18.0.6.4', 'version_after': '18.0.6.5.0'})])), ValidationError)
    raises('版號未改、全用預設（資料庫＝manifest）→ 擋', lambda: Entry.create(vals(line_ids=[(0, 0, {
        'module_id': qual.id})])), ValidationError)
    raises('Odoo 內建模組（mail）→ 擋', lambda: Entry.create(vals(line_ids=[(0, 0, {
        'module_id': Module.search([('name', '=', 'mail')]).id,
        'version_before': '18.0.1.0.0', 'version_after': '18.0.1.1.0'})])), ValidationError)
    raises('同一筆紀錄同模組列兩次 → 擋', lambda: Entry.create(vals(line_ids=[
        (0, 0, {'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.5.0'}),
        (0, 0, {'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.5.0'})])))
    raises('沒有受影響模組 → 擋', lambda: Entry.create(vals()), ValidationError)
    raises('刪光受影響模組 → 擋', lambda: e1.write({'line_ids': [(5, 0, 0)]}), ValidationError)

    ok_line = [(0, 0, {'module_id': qual.id, 'version_before': '18.0.6.4.0', 'version_after': '18.0.6.5.0'})]
    # ---------- 三欄與其他必填 ----------
    for f, label in (('reason', '原因'), ('change', '改變'), ('method', '做法')):
        v = vals(line_ids=ok_line)
        v.pop(f)
        raises('%s 未填 → 擋' % label, lambda v=v: Entry.create(v))
        raises('%s 只打空白 → 擋' % label, lambda f=f: Entry.create(vals(line_ids=ok_line, **{f: '   \n '})),
               ValidationError)
    v = vals(line_ids=ok_line)
    v.pop('announce')
    raises('是否公告未選 → 擋', lambda: Entry.create(v))
    raises('標題超過 20 字 → 擋', lambda: Entry.create(vals(line_ids=ok_line, title='一' * 21)), ValidationError)
    check('標題剛好 20 字可存', Entry.create(vals(line_ids=ok_line, title='一' * 20)).id)
    raises('commit 空白 → 擋', lambda: Entry.create(vals(line_ids=ok_line, commits='  ')))
    raises('commit 非十六進位 → 擋', lambda: Entry.create(vals(line_ids=ok_line, commits='fix-bug')), ValidationError)
    raises('commit 太短（6 碼）→ 擋', lambda: Entry.create(vals(line_ids=ok_line, commits='07258f')), ValidationError)

    # ---------- 問題單關聯 ----------
    prb = env['construction.problem'].search([], limit=1)
    if prb:
        e1.problem_ids = [(4, prb.id)]
        check('可關聯系統問題單', prb in e1.problem_ids)
    else:
        check('可關聯系統問題單（庫內無問題單，只驗欄位型別）',
              Entry._fields['problem_ids'].comodel_name == 'construction.problem')

    # ---------- 權限 ----------
    raises('代操作員（uid6）讀不到更新紀錄', lambda: Entry.with_user(u_op).search([]), AccessError)
    raises('代操作員讀不到受影響模組', lambda: Line.with_user(u_op).search([]), AccessError)
    Menu = env['ir.ui.menu']
    root = env.ref('construction_release.menu_release_root')
    check('代操作員看不到「版本管理」選單', root.id not in Menu.with_user(u_op)._visible_menu_ids())
    check('管理員看得到「版本管理」選單', root.id in Menu.with_user(admin)._visible_menu_ids())

    # ---------- get_views ----------
    for model in ('construction.release.entry',):
        try:
            env[model].with_user(admin).get_views([(False, 'list'), (False, 'form'), (False, 'search')])
            check('get_views %s' % model, True)
        except Exception as e:
            check('get_views %s' % model, False, repr(e))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT release_p1')
    env.cr.rollback()

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print('%s %s %s' % ('✅' if passed else '❌', name, detail if not passed else ''))
print('==== %d/%d 通過 ====' % (ok, len(results)))

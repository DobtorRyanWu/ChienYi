# -*- coding: utf-8 -*-
"""前台帳號讀通報單明細（odoo shell 執行，全程 rollback，不留資料）。

docker exec pg18-odoo bash -lc 'echo "exec(open(\"/mnt/extra-addons/construction_notification_slip/tests/shell_portal_access.py\").read())" | odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=error'

前台通報單詳情頁（construction_portal 的 portal_construction_slip_detail）逐列顯示明細，
其中「金額是否手填」is_manual_amount 是非儲存 compute，會讀契約工項的 tax_misc_rate／
is_lump_sum／parent_id。前台帳號對 project.task 有記錄規則與欄位白名單限制 →
以前只要通報單有明細，前台帳號開詳情頁就 403。
"""
from odoo.exceptions import AccessError

results = []


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


env.cr.execute('SAVEPOINT portal_access')
try:
    portal = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'ZZ 前台測試（rollback）', 'login': 'zz_portal_access_test',
        'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                              env.ref('construction_supervision_base.group_portal_subscriber').id])],
    })
    lines = env['reservation.notification.slip.line'].search([], limit=200)
    check('有明細可測', bool(lines), len(lines))
    pl = lines.with_user(portal)
    env.invalidate_all()
    # 先在乾淨快取下以前台身分算一次（若先用 sudo 算，值會留在共用快取裡，測不出問題）
    try:
        mine = {l.id: l.is_manual_amount for l in pl}
    except AccessError as e:
        mine = None
        check('前台帳號（乾淨快取）算 is_manual_amount', False, str(e)[:160])
    env.invalidate_all()
    for fname in ('is_manual_amount', 'description', 'item_no', 'unit', 'planned_qty',
                  'actual_qty', 'unit_price', 'planned_amount', 'actual_amount',
                  'completion_rate', 'display_item_no'):
        try:
            vals = [getattr(l, fname) for l in pl]
            check(f'前台帳號讀明細 {fname}', True, f'{len(vals)} 列')
        except AccessError as e:
            check(f'前台帳號讀明細 {fname}', False, str(e)[:160])
    # 後台（內部帳號）同一欄位的值不受影響：前台算出來的要與 sudo 算的完全相同
    env.invalidate_all()
    sup = {l.id: l.is_manual_amount for l in lines.sudo()}
    check('前台與後台算出的 is_manual_amount 完全相同', mine == sup,
          'mine=None' if mine is None else sum(1 for k in sup if sup[k] != mine.get(k)))
    # 權限沒有被放寬：前台帳號仍然不能直接讀契約工項的 tax_misc_rate
    task = lines.mapped('task_id')[:1]
    try:
        task.with_user(portal).read(['tax_misc_rate'])
        check('前台帳號仍不能直接讀契約工項（權限沒有被放寬）', False, 'read 成功了')
    except AccessError:
        check('前台帳號仍不能直接讀契約工項（權限沒有被放寬）', True)
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT portal_access')

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print(('PASS ' if passed else 'FAIL ') + name + (('  — ' + str(detail)) if detail else ''))
print(f'\n{ok}/{len(results)} passed')

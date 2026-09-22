import json
from odoo.exceptions import AccessError, UserError
from odoo.addons.base.models.res_users import name_selection_groups
R = []
def check(name, cond, detail=''):
    R.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)) if (not cond and detail != '') else ''))

G = env['res.groups']; U = env['res.users'].with_context(no_reset_password=True)
sa = env.ref('construction_supervision_base.group_supervisor_admin')
op = env.ref('construction_supervision_base.group_operator')
mgr = env.ref('construction_supervision_base.group_engineering_manager')
sysg = env.ref('base.group_system')
guser = env.ref('base.group_user')
cat = env.ref('construction_supervision_base.module_category_supervision_special')

# ── 結構
dd = [(k, gs.mapped('name')) for app, k, gs, cn in G.get_groups_by_application() if app == cat]
check('下拉＝代操作員／工程管理者', dd == [('selection', ['代操作員', '工程管理者'])], dd)
check('group_supervisor_admin 改名「工程後台使用者」且無分類', sa.name == '工程後台使用者' and not sa.category_id)
check('工程管理者 implied＝代操作員＋設定', mgr.implied_ids == (op | sysg))
check('代操作員 implied 不變', op.implied_ids == sa)
arch = env.ref('base.user_groups_view').arch
check('使用者表單已重建（含新下拉欄位）', name_selection_groups([op.id, mgr.id]) in arch)

# ── 與調整前逐筆比對（資料庫查詢）
SNAPNAME = 'snap_after.json'
exec(open('/tmp/snap.py').read())
out = json.load(open('/tmp/snap_after.json'))
before = json.load(open('/tmp/snap_before.json'))
for k in ('sa_acl', 'sa_rule', 'sa_trans', 'op_acl', 'op_rule', 'op_trans', 'u6_groups', 'u6_action'):
    n = len(before[k]) if isinstance(before[k], list) else before[k]
    check(f'{k} 與調整前逐筆相同（{n}）', out[k] == before[k])
added = set(out['u2_groups']) - set(before['u2_groups']); removed = set(before['u2_groups']) - set(out['u2_groups'])
check('使用者2 只多了工程管理者＋它帶的代操作員、沒少任何群組', added == {'construction_supervision_base.group_engineering_manager', 'construction_supervision_base.group_operator'} and not removed, (added, removed))
check('使用者2 首頁維持原狀', out['u2_action'] == before['u2_action'], out['u2_action'])

# ── 各帳號行為
u2 = env['res.users'].browse(2); u6 = env['res.users'].browse(6)
def can_manage(u):
    return any(u.has_group(x) for x in ('construction_supervision_base.group_portal_subscriber',
                                         'construction_supervision_base.group_portal_leader',
                                         'base.group_system', 'construction_supervision_base.group_operator'))
def can_unlock(u):
    sh = env['daily.log.sheet'].search([], limit=1).with_user(u)
    sh.invalidate_recordset(['can_unlock'])
    return sh.can_unlock
def settings_ok(u):
    try:
        env['res.config.settings'].with_user(u).check_access('create'); return True
    except AccessError:
        return False
check('工程管理者(2)：有設定／代操作員／工程後台使用者', all(g in u2.groups_id for g in (sysg, op, sa, mgr)))
check('工程管理者(2)：前台 _can_manage', can_manage(u2))
check('工程管理者(2)：日誌可解鎖', can_unlock(u2))
check('工程管理者(2)：能進系統設定', settings_ok(u2))
check('代操作員(6)：沒有設定、不是工程管理者', sysg not in u6.groups_id and mgr not in u6.groups_id)
check('代操作員(6)：前台 _can_manage', can_manage(u6))
check('代操作員(6)：日誌可解鎖', can_unlock(u6))
check('代操作員(6)：進系統設定 AccessError', not settings_ok(u6))
biz = sorted({a.model_id.model for a in env['ir.model.access'].search([
    ('group_id', '=', sa.id), ('perm_read', '=', True), ('perm_write', '=', True),
    ('perm_create', '=', True), ('perm_unlink', '=', True)])})
bad = [(m, o) for m in biz for o in ('read', 'write', 'create', 'unlink') if not env[m].with_user(u6).has_access(o)]
check(f'代操作員(6)：{len(biz)} 個 model（工程後台使用者有全權者）讀增改刪全通', not bad, bad[:5])
expect = {'res.users': 'r', 'res.company': 'r', 'res.groups': 'r', 'ir.ui.menu': 'r', 'ir.model.access': '', 'ir.rule': ''}
got = {m: ('r' if env[m].with_user(u6).has_access('read') else '') +
          ('W' if any(env[m].with_user(u6).has_access(o) for o in ('write', 'create', 'unlink')) else '')
       for m in expect}
check('代操作員(6)：系統層只能讀／ACL 與 rule 全擋', got == expect, got)

# ── 空白帳號、升級、降級、首頁（臨時帳號，最後 rollback）
blank = U.create({'name': 'ZZ 空白', 'login': 'zz_perm_blank', 'groups_id': [(6, 0, [guser.id])]})
check('空白帳號：沒有工程後台使用者／代操作員／工程管理者', not (blank.groups_id & (sa | op | mgr)))
readable = [m for m in biz if env[m].with_user(blank).has_access('read')]
print(f'INFO 空白帳號在上述 {len(biz)} 個 model 中仍可讀 {len(readable)} 個（來自其他群組的 ACL）：{readable}')

F = name_selection_groups([op.id, mgr.id])
t = U.create({'name': 'ZZ 升降級', 'login': 'zz_perm_updown', 'groups_id': [(6, 0, [guser.id])]})
t.write({F: op.id}); t.invalidate_recordset()
check('畫面下拉設成代操作員', op in t.groups_id and mgr not in t.groups_id and sysg not in t.groups_id)
t.write({F: mgr.id}); t.invalidate_recordset()
check('畫面下拉 代操作員→工程管理者：直接改即可', all(g in t.groups_id for g in (mgr, sysg, op, sa)))
check('工程管理者：降級按鈕會顯示', t.is_engineering_manager)
t.action_downgrade_to_operator(); t.invalidate_recordset()
ref_u = U.create({'name': 'ZZ 對照', 'login': 'zz_perm_ref', 'groups_id': [(6, 0, [guser.id])]})
ref_u.write({F: op.id}); ref_u.invalidate_recordset()
diff = sorted(((t.groups_id - ref_u.groups_id) | (ref_u.groups_id - t.groups_id)).mapped('full_name'))
check('降級後權限與「直接設成代操作員」完全相同（無殘留）', not diff, diff)
check('降級後按鈕隱藏', not t.is_engineering_manager)
# 對照：只改下拉會殘留
t2 = U.create({'name': 'ZZ 只改下拉', 'login': 'zz_perm_dd', 'groups_id': [(6, 0, [guser.id])]})
t2.write({F: mgr.id}); t2.write({F: op.id}); t2.invalidate_recordset()
check('對照組：只改下拉確實殘留設定（證明按鈕必要）', sysg in t2.groups_id)
try:
    u2.with_user(u2).action_downgrade_to_operator(); check('不能降級自己', False)
except UserError:
    check('不能降級自己', True)
t.write({F: mgr.id})
try:
    t.with_user(u6).action_downgrade_to_operator(); check('代操作員不能執行降級', False)
except (AccessError, UserError):
    check('代操作員不能執行降級', True)
h1 = U.create({'name': 'ZZ 首頁op', 'login': 'zz_perm_h1', 'groups_id': [(6, 0, [op.id])]})
h2 = U.create({'name': 'ZZ 首頁mgr', 'login': 'zz_perm_h2', 'groups_id': [(6, 0, [mgr.id])]})
check('首頁：代操作員仍自動設成工程案件', h1.action_id.id == env.ref('construction_supervision_base.action_supervision_project').id)
check('首頁：工程管理者不被改', not h2.action_id)
vid = env.ref('base.view_users_form').id
a2 = env['res.users'].with_user(u2).get_views([(vid, 'form')])['views']['form']['arch']
a6 = env['res.users'].with_user(u6).get_views([(vid, 'form')])['views']['form']['arch']
check('使用者表單：工程管理者看得到降級按鈕', 'action_downgrade_to_operator' in a2)
check('使用者表單：代操作員看不到降級按鈕', 'action_downgrade_to_operator' not in a6)
print(f'RESULT {sum(R)}/{len(R)}')
env.cr.rollback()
print('殘留臨時帳號', env['res.users'].with_context(active_test=False).search_count([('login', 'like', 'zz_perm_')]))

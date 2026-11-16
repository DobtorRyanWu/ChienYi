# -*- coding: utf-8 -*-
"""前台成員規則排除「未開始／終止」工程（2026-11-16，使用者選 B）。

背景：工程規則 supervision_project_portal_member_rule 早就排除 draft／terminated（成員看不到
未開始與終止的工程，前台頁面的工程閘門也擋），但工程底下的資料（日誌、檢查、估驗、資料夾、工項…）
的成員規則只看「是不是成員」——成員經 RPC 照樣讀得到看不到的工程底下的資料（11-16 實測：
資料夾、估驗、工項都讀得到）。改成：每一條前台成員規則的成員條件都 AND 同一路徑的工程狀態條件。
老闆規則（公司範圍 (1=1)）不動。

兩段：
A. 結構：列舉前台群組（含主管／現場的寫入規則，它們 perm_read 也是 True、與成員規則 OR）裡所有
   含成員條件的讀取規則，斷言每個成員條件都和「同一路徑的 state not in [draft, terminated]」AND 在一起
   ——以後新增成員規則忘了狀態條件就會紅。
B. 行為：成員經 ORM 讀不到未開始／終止工程底下的資料，讀得到施工中工程的資料。
"""

from odoo.osv import expression
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

PORTAL = 'base.group_portal'
LEADER = 'construction_supervision_base.group_portal_leader'      # 主管
FIELD = 'construction_supervision_base.group_portal_user'         # 現場人員
VIEWER = 'construction_supervision_base.group_portal_viewer'      # 定期閱覽者
PORTAL_MEMBER_GROUPS = (PORTAL, LEADER, FIELD, VIEWER)
MEMBER_FIELD = 'member_user_ids'
EXCLUDED_STATES = ['draft', 'terminated']
# construction_portal 自己就定義了 30 條以上的成員規則；少於這個數＝規則沒載入，A 段會是空集合恆真
MIN_MEMBER_RULES = 30
# 例外（規則 xmlid → 理由）。目前沒有：只檢查「成員條件」那一項，同一條規則裡的其他放行分支
# （不屬任何工程的 project_id = False、行事曆的權責人 responsible_user_id = user）不受影響，不必列例外。
EXCEPTIONS = {}


def _domain_tree(domain):
    """把正規化後的前序 domain 轉成樹：('&'|'|', [子節點…])、('!', [子節點])、或葉（條件 tuple）。
    同一運算子的巢狀節點攤平，方便判斷「哪些條件 AND 在一起」。"""
    pos = 0

    def parse():
        nonlocal pos
        token = domain[pos]
        pos += 1
        if token in ('&', '|'):
            children = []
            for child in (parse(), parse()):
                if isinstance(child, tuple) and len(child) == 2 and child[0] == token:
                    children.extend(child[1])
                else:
                    children.append(child)
            return (token, children)
        if token == '!':
            return ('!', [parse()])
        return tuple(token)

    tree = parse()
    return tree


def _member_leaves_without_state(tree, parent=None):
    """回傳沒有和同一路徑狀態條件 AND 在一起的成員條件。"""
    bad = []
    if len(tree) == 2 and tree[0] in ('&', '|', '!'):
        for child in tree[1]:
            bad += _member_leaves_without_state(child, tree)
        return bad
    path = tree[0]
    if not (isinstance(path, str) and path.split('.')[-1] == MEMBER_FIELD):
        return bad
    prefix = path[:-len(MEMBER_FIELD)]
    expected = (prefix + 'state', 'not in', EXCLUDED_STATES)
    siblings = parent[1] if parent and parent[0] == '&' else []
    if not any(len(s) == 3 and s[0] == expected[0] and s[1] == expected[1]
               and sorted(s[2]) == sorted(expected[2]) for s in siblings if isinstance(s, tuple)):
        bad.append(path)
    return bad


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalMemberStateScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.contractor = make_contractor(env, '狀態範圍測試營造')
        cls.projects = {}
        for state in ('construction', 'draft', 'terminated'):
            cls.projects[state] = env['project.project'].create({
                'name': '狀態範圍 %s' % state, 'code': 'MSS-%s' % state.upper(),
                'project_type': 'general', 'state': state, 'company_id': env.company.id,
                **contractor_project_vals(cls.contractor)})
        cls.field = cls._mk_user('mss_field', FIELD)
        cls.leader = cls._mk_user('mss_leader', LEADER)
        for project in cls.projects.values():
            for user in (cls.field, cls.leader):
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})

    @classmethod
    def _mk_user(cls, login, group):
        return cls.env['res.users'].create({
            'name': login, 'login': login, 'groups_id': [(6, 0, [cls.env.ref(group).id])],
            **contractor_user_vals(cls.contractor)})

    # ═══ A. 結構 ══════════════════════════════════════════════════════
    def test_a_tree_helper(self):
        """前提：判斷函式本身是對的（AND 在一起才算；OR 在一起、路徑不同都不算）。"""
        member = ('project_id.member_user_ids', 'in', [1])
        state = ('project_id.state', 'not in', EXCLUDED_STATES)
        other_state = ('task_id.project_id.state', 'not in', EXCLUDED_STATES)
        cases = [
            ([member], ['project_id.member_user_ids']),
            ([member, state], []),
            (['|', ('project_id', '=', False), '&', member, state], []),
            (['|', member, state], ['project_id.member_user_ids']),
            ([member, other_state], ['project_id.member_user_ids']),
            ([('site_type', '=', 'project'), member, state], []),
        ]
        for domain, expected in cases:
            with self.subTest(domain=domain):
                tree = _domain_tree(expression.normalize_domain(domain))
                self.assertEqual(_member_leaves_without_state(tree), expected)

    def test_a_every_portal_member_rule_excludes_draft_and_terminated(self):
        groups = self.env['res.groups'].browse([self.env.ref(x).id for x in PORTAL_MEMBER_GROUPS])
        Rule = self.env['ir.rule'].sudo()
        rules = Rule.search([('groups', 'in', groups.ids), ('perm_read', '=', True),
                             ('domain_force', 'like', MEMBER_FIELD)])
        self.assertGreaterEqual(len(rules), MIN_MEMBER_RULES, '前台成員規則沒載入？')
        ctx = Rule._eval_context()
        xmlids = rules.get_external_id()
        missing = []
        for rule in rules:
            if xmlids.get(rule.id) in EXCEPTIONS:
                continue
            domain = expression.normalize_domain(safe_eval(rule.domain_force, ctx))
            for path in _member_leaves_without_state(_domain_tree(domain)):
                missing.append('%s（%s：%s）' % (xmlids.get(rule.id) or rule.name, rule.model_id.model, path))
        self.assertFalse(missing, '這些前台成員規則沒排除未開始／終止工程：\n' + '\n'.join(sorted(missing)))

    # ═══ B. 行為 ══════════════════════════════════════════════════════
    def _records_per_project(self):
        """每個工程各建一份工程底下的資料：資料夾、工項、自主檢查（＋有裝的話估驗）。"""
        env = self.env
        itype = env['self.inspection.type'].create({'name': '狀態範圍樣板'})
        out = {}
        for state, project in self.projects.items():
            recs = [
                env['supervision.folder'].create({'name': '狀態範圍資料夾', 'project_id': project.id}),
                env['project.task'].create({'name': '狀態範圍工項', 'project_id': project.id}),
                env['general.self.inspection'].create({
                    'project_id': project.id, 'inspection_type_id': itype.id,
                    'inspection_date': '2026-11-16', 'sub_project_name': '狀態範圍分項'}),
            ]
            if 'payment.estimate' in env:
                recs.append(env['payment.estimate'].create({'project_id': project.id}))
            out[state] = recs
        return out

    def test_b_member_cannot_read_data_of_draft_or_terminated_project(self):
        records = self._records_per_project()
        self.env.invalidate_all()
        # 主管另有寫入規則（perm_read 也是 True、與成員規則 OR），兩種角色都要擋
        for user in (self.field, self.leader):
            for state in ('draft', 'terminated'):
                self.assertFalse(self.projects[state].with_user(user).has_access('read'),
                                 '前提：成員本來就讀不到 %s 工程' % state)
                for rec in records[state]:
                    with self.subTest(user=user.login, state=state, model=rec._name):
                        self.assertFalse(rec.with_user(user).has_access('read'),
                                         '成員不可經 RPC 讀 %s 工程底下的 %s' % (state, rec._name))
                        # 用 search_count：工項的預設排序欄位 item_no_sort 不在前台可讀欄位白名單，
                        # 前台帳號帶預設排序 search 工項本來就會 AccessError（與本案無關）
                        self.assertEqual(
                            self.env[rec._name].with_user(user).search_count([('id', '=', rec.id)]), 0)

    def test_b_member_still_reads_data_of_active_project(self):
        """正當入口：施工中工程照常讀得到（資料夾、工項、自主檢查、估驗）。"""
        records = self._records_per_project()
        self.env.invalidate_all()
        for user in (self.field, self.leader):
            self.assertTrue(self.projects['construction'].with_user(user).has_access('read'))
            for rec in records['construction']:
                with self.subTest(user=user.login, model=rec._name):
                    self.assertTrue(rec.with_user(user).has_access('read'))

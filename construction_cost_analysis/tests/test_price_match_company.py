# -*- coding: utf-8 -*-
"""價格庫比對限同公司、成本分析公司隔離（18.0.2.1.0）

背景（2026-10-23）：正式站 jt 是多家監造公司共用的庫，新案要把廷暉、和建的契約單價分析寫進價格庫。
原本比對「不以 company 過濾」（當時假設單庫單公司），寫進去之後任泰做成本分析會比對到別家公司的單價；
兩家公司都有同名同單位的項目時，還會變成「多個候選」而比對不到任何一筆。
比對公司、明細公司、來源工程公司三者都是分析的 company_id，別家的單價就不會被存進本公司的明細。
價格庫與成本分析都有全域公司規則，所以測試一律用「真實使用者」跑——superuser 不受規則限制。
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

NAME, UNIT = '價格比對測試工項，丙種', 'm2'
ADMIN_GROUP = 'construction_supervision_base.group_supervisor_admin'


@tagged('post_install', '-at_install', 'construction_cost_analysis')
class TestPriceMatchSameCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': '價格比對測試 B 公司'})
        Cat, Item = cls.env['price.library.category'], cls.env['price.library.item']
        cls.item_a = Item.create({
            'name': NAME, 'unit': UNIT, 'unit_price': 100.0, 'company_id': cls.company_a.id,
            'category_id': Cat.create({'name': '比對測試 A', 'company_id': cls.company_a.id}).id})
        cls.item_b = Item.create({
            'name': NAME, 'unit': UNIT, 'unit_price': 120.0, 'company_id': cls.company_b.id,
            'category_id': Cat.create({'name': '比對測試 B', 'company_id': cls.company_b.id}).id})
        cls.project_a = cls.env['project.project'].create({
            'name': '價格比對測試工程 A', 'company_id': cls.company_a.id})
        # 代操：兩家公司都有權限、都勾選，目前公司是 B
        cls.user = cls.env['res.users'].create({
            'name': '價格比對測試代操', 'login': 'price_match_operator',
            'company_id': cls.company_b.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref(ADMIN_GROUP).id])],
        })

    def _env(self, *companies):
        return self.env(user=self.user, context={'allowed_company_ids': [c.id for c in companies]})

    def _analysis(self, env, vals, name=NAME):
        analysis = env['cost.analysis'].create(dict({'name': '價格比對測試'}, **vals))
        line = env['cost.analysis.line'].create({
            'planning_id': analysis.id, 'name': name, 'unit': UNIT, 'quantity': 1.0})
        analysis.action_import_suggested_prices()
        return analysis, line

    def test_rig(self):
        # 兩家公司的項目正規化後同名同單位——不分公司比對時，這正是「多個候選」的情況
        self.assertEqual(self.item_a.name_normalized, self.item_b.name_normalized)

    def test_matches_analysis_company_and_stores_in_same_company(self):
        env = self._env(self.company_b, self.company_a)
        _analysis, line = self._analysis(env, {
            'company_id': self.company_a.id, 'import_mode': 'project', 'source_project_id': self.project_a.id})
        self.assertEqual(line.match_status, 'matched')
        self.assertEqual(line.library_item_id, self.item_a)
        self.assertEqual(line.company_id, self.company_a, '單價只能存進同公司的明細')

    def test_source_project_must_belong_to_analysis_company(self):
        # 代操切在 B、沒改公司就選 A 的工程：不允許（否則 A 的單價會存進 B 公司的明細）
        with self.assertRaises(ValidationError):
            self._env(self.company_b, self.company_a)['cost.analysis'].create({
                'name': '價格比對測試', 'import_mode': 'project', 'source_project_id': self.project_a.id})

    def test_other_company_item_is_never_used(self):
        # 只有 A 公司有這一項：B 公司的分析不可比對到它（即使使用者兩家都勾）
        only_a = self.env['price.library.item'].create({
            'name': NAME + '（僅A）', 'unit': UNIT, 'unit_price': 999.0, 'company_id': self.company_a.id,
            'category_id': self.item_a.category_id.id})
        _analysis, line = self._analysis(self._env(self.company_b, self.company_a), {'import_mode': 'xml'},
                                         name=only_a.name)
        self.assertFalse(line.library_item_id)
        self.assertEqual(line.match_status, 'none')

    def test_analysis_is_company_scoped(self):
        analysis, _line = self._analysis(self._env(self.company_b, self.company_a), {'import_mode': 'xml'})
        env_a = self._env(self.company_a)
        self.assertFalse(env_a['cost.analysis'].search([('id', '=', analysis.id)]))
        self.assertFalse(env_a['cost.analysis.line'].search([('planning_id', '=', analysis.id)]))

    def test_company_change_with_foreign_matches_blocked(self):
        # XML 模式先用 B 比對、再把分析改成 A：B 的項目與建議單價會跟著明細搬到 A，必須擋
        env = self._env(self.company_b, self.company_a)
        analysis, line = self._analysis(env, {'import_mode': 'xml'})
        self.assertEqual(line.library_item_id, self.item_b)
        with self.assertRaises(ValidationError):
            analysis.write({'company_id': self.company_a.id})

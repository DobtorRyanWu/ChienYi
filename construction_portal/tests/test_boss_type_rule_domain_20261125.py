# -*- coding: utf-8 -*-
"""前台老闆對自主檢查樣板（含四張明細表）的規則自己的 domain（2026-11-25，W5 A1）。

原本五條老闆規則是 [(1, '=', 1)]。現在別家公司工程的樣板被 construction_quality 的全域規則擋住，
行為上看不出來；這裡直接打在「這條規則自己的 domain」上：取出 domain_force、用老闆的規則求值環境算出
domain，再用 sudo 搜尋，別家公司工程綁定的樣板（與明細）不可在結果裡，全域樣板與本公司工程的要在。
"""

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

BOSS = 'construction_supervision_base.group_portal_subscriber'
RULES = (
    ('construction_portal.self_inspection_type_portal_boss_rule', 'self.inspection.type', None),
    ('construction_portal.self_inspection_type_item_portal_boss_rule', 'self.inspection.type.item', 'type_id'),
    ('construction_portal.self_inspection_type_stage_portal_boss_rule', 'self.inspection.type.stage', 'type_id'),
    ('construction_portal.self_inspection_type_timing_portal_boss_rule', 'self.inspection.type.timing', 'type_id'),
    ('construction_portal.self_inspection_type_measure_portal_boss_rule', 'self.inspection.type.measure', 'type_id'),
)


@tagged('post_install', '-at_install', 'construction_portal')
class TestBossTypeRuleDomain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        contractor = make_contractor(env, '老闆樣板規則營造')
        cls.other_company = env['res.company'].create({'name': '老闆樣板規則他公司'})
        cls.boss = env['res.users'].create({
            'name': 'bt_boss', 'login': 'bt_boss',
            'groups_id': [(6, 0, [env.ref(BOSS).id])], **contractor_user_vals(contractor)})
        vals = {'project_type': 'general', 'state': 'construction', **contractor_project_vals(contractor)}
        cls.own_project = env['project.project'].create(
            dict(vals, name='bt 本公司工程', code='BT-OWN', company_id=env.company.id))
        cls.foreign_project = env['project.project'].with_company(cls.other_company).create(
            dict(vals, name='bt 他公司工程', code='BT-FOREIGN', company_id=cls.other_company.id))
        Type = env['self.inspection.type']
        cls.types = {
            'global': Type.create({'name': 'bt 全域樣板'}),
            'own': Type.create({'name': 'bt 本公司樣板', 'project_id': cls.own_project.id}),
            'foreign': Type.create({'name': 'bt 他公司樣板', 'project_id': cls.foreign_project.id}),
        }
        for itype in cls.types.values():
            env['self.inspection.type.item'].create({
                'type_id': itype.id, 'name': itype.name + ' 項目', 'stage_id': itype.stage_ids[:1].id})
            env['self.inspection.type.measure'].create({
                'type_id': itype.id, 'name': itype.name + ' 量測', 'template': '丈量___位置'})

    def _rule_hits(self, xmlid, model):
        """用老闆的規則求值環境算 domain，sudo 搜尋；回傳命中的紀錄。"""
        rule = self.env.ref(xmlid)
        ctx = rule.with_user(self.boss)._eval_context()
        domain = safe_eval(rule.domain_force, ctx)
        return self.env[model].sudo().with_context(active_test=False).search(domain)

    def test_boss_rules_exclude_other_company_templates(self):
        """修前五條都是 (1=1)：別家公司工程的樣板與明細在結果裡；修後不在，全域與本公司的在。"""
        for xmlid, model, path in RULES:
            with self.subTest(rule=xmlid):
                hits = self._rule_hits(xmlid, model)
                owner = (lambda r: r) if path is None else (lambda r: r[path])
                hit_types = hits.mapped(lambda r: owner(r).id)
                for key in ('global', 'own'):
                    self.assertIn(self.types[key].id, hit_types, '%s 的紀錄應命中' % key)
                self.assertNotIn(self.types['foreign'].id, hit_types, '他公司工程的樣板不可命中')

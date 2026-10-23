# -*- coding: utf-8 -*-
"""人機下拉依「案件所屬公司」過濾（18.0.1.4.0）

背景（2026-10-23）：正式站 jt 是多家監造公司共用的庫。人員機具設定（personnel.type）原本
下拉不分公司——日誌明細、人機主檔、批次新增精靈的 domain 都只看 active／record_type——
新案匯入廷暉、和建自己的工種與機具後，任泰的日誌下拉也會跟著變長、出現同名重複。
改成只列「共用（company_id 空白）＋案件所屬公司」的項目。

既有項目由 migration 一律改成共用：今天大家都看得到全部，全部改共用＝升級前後每個人看到的
清單完全一樣（dev 實查 23,545 筆明細裡有 18,021 筆引用了「公司≠案件公司」的項目，
只改一部分一定有人的下拉少東西）。
"""
import importlib.util
import os

from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

MIGRATION = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         'migrations', '18.0.1.4.0', 'post-migrate.py')


@tagged('post_install', '-at_install', 'construction_equipment')
class TestPersonnelTypeCompanyDomain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        PT = cls.env['personnel.type']
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': '人機過濾測試 B 公司'})
        cls.shared = PT.create({'name': '人機過濾測試共用工', 'record_type': 'personnel', 'company_id': False})
        cls.own_a = PT.create({'name': '人機過濾測試 A 工', 'record_type': 'personnel',
                               'company_id': cls.company_a.id})
        cls.own_b = PT.create({'name': '人機過濾測試 B 工', 'record_type': 'personnel',
                               'company_id': cls.company_b.id})
        cls.mine = cls.shared | cls.own_a | cls.own_b

    def _selectable(self, model, field, values):
        """用欄位定義的 domain（前端下拉實際套用的那一個）搜尋，回傳三筆測試資料中選得到的"""
        dom = self.env[model]._fields[field].domain
        dom = safe_eval(dom, values) if isinstance(dom, str) else list(dom or [])
        return self.env['personnel.type'].search(dom + [('id', 'in', self.mine.ids)])

    def test_rig(self):
        # 不加公司條件時三筆都選得到 → 下面各測試若只選到兩筆，是公司條件擋的，不是資料沒建好
        got = self.env['personnel.type'].search([('active', '=', True), ('id', 'in', self.mine.ids)])
        self.assertEqual(got, self.mine)

    def test_detail_dropdown_only_shared_and_project_company(self):
        got = self._selectable('daily.log.man.machine.detail', 'personnel_type_id',
                               {'project_company_id': self.company_a.id})
        self.assertEqual(got, self.shared | self.own_a)

    def test_man_machine_dropdown_only_shared_and_project_company(self):
        got = self._selectable('daily.log.man.machine', 'personnel_type_id',
                               {'record_type': 'personnel', 'company_id': self.company_b.id})
        self.assertEqual(got, self.shared | self.own_b)

    def test_wizard_dropdown_only_shared_and_project_company(self):
        got = self._selectable('daily.log.add.man.machine.wizard', 'selected_type_ids',
                               {'project_company_id': self.company_a.id})
        self.assertEqual(got, self.shared | self.own_a)

    def test_wizard_view_does_not_override_field_domain(self):
        # view 上的 domain 屬性會蓋掉欄位定義的 domain；過濾只寫在欄位上，view 不得再寫一份
        arch = etree.fromstring(self.env.ref('construction_equipment.daily_log_add_man_machine_wizard_form').arch)
        self.assertFalse(arch.xpath('//field[@name="selected_type_ids"]/@domain'))

    def test_new_type_defaults_to_shared(self):
        # 在 A 公司建的工種（沒指定公司）要共用：B 公司工程的下拉也選得到，
        # 否則「在別家公司的工程下建工種」會從那個工程的下拉消失
        new = self.env['personnel.type'].with_company(self.company_a).create(
            {'name': '人機過濾測試新建工', 'record_type': 'personnel'})
        self.assertFalse(new.company_id)
        dom = safe_eval(self.env['daily.log.man.machine.detail']._fields['personnel_type_id'].domain,
                        {'project_company_id': self.company_b.id})
        self.assertIn(new, self.env['personnel.type'].search(dom))

    def test_migration_makes_existing_types_shared(self):
        spec = importlib.util.spec_from_file_location('equipment_post_migrate_1_4_0', MIGRATION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, '18.0.1.3.0')
        self.env.invalidate_all()
        left = self.env['personnel.type'].with_context(active_test=False).search_count(
            [('company_id', '!=', False)])
        self.assertEqual(left, 0, 'migration 後不應再有掛公司的既有人機項目')

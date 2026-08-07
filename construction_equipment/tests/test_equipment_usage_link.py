# -*- coding: utf-8 -*-
"""A4 / A5 / C3 — 機具設備主檔與施工日誌的人機使用從來沒有關聯過。

代操 2026-08-06 回報「機具設備新增」時跳：

    Invalid field daily.log.man.machine.equipment_id in leaf ('equipment_id', '=', 9)

根因：`supervision.equipment._compute_usage_stats()` 去 `daily.log.man.machine`
查 `equipment_id` 與 `equipment_hours`，但那兩個欄位在
`daily.log.man.machine` 與 `daily.log.man.machine.detail` **都不存在**——
日誌那端只有一個自由文字的 `specific_equipment_name`（實查 0 筆使用）。
於是設備主檔一存檔、compute 一跑就炸。

連帶症狀 A5：設備列表依「所屬工程」分組時全部落在「無」。

修法採「真的把兩邊接起來」而非只止血，因為實查
`supervision_equipment` 筆數為 0、`specific_equipment_name` 使用數為 0，
**沒有任何既有資料需要回填**，成本極低。
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_equipment')
class TestEquipmentUsageLink(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'A4 測試工程',
            'code': 'A4-TEST',
            'project_type': 'general',
        })
        cls.category = cls.env['supervision.equipment.category'].create({
            'name': 'A4 測試分類',
        })

    def _make_equipment(self, name='A4 測試設備'):
        return self.env['supervision.equipment'].create({
            'name': name,
            'category_id': self.category.id,
            'project_id': self.project.id,
        })

    def test_create_equipment_does_not_crash(self):
        """A4：建立機具設備不得因 _compute_usage_stats 查不存在的欄位而爆。"""
        eq = self._make_equipment()
        self.assertTrue(eq.id)
        # 觸發 compute（原本就是這一步炸的）
        self.assertEqual(eq.total_usage_hours, 0.0,
                         '尚無使用紀錄時累計使用時數應為 0')

    def test_detail_has_equipment_id(self):
        """C3：人機明細要有指向設備主檔的外鍵，不能只有自由文字。"""
        fields_ = self.env['daily.log.man.machine.detail']._fields
        self.assertIn('equipment_id', fields_,
                      'daily.log.man.machine.detail 缺少 equipment_id')
        self.assertEqual(fields_['equipment_id'].comodel_name,
                         'supervision.equipment')

    def test_usage_hours_sums_linked_details(self):
        """使用時數要從掛在該設備上的人機明細加總出來。"""
        eq = self._make_equipment('A4 挖土機')
        other = self._make_equipment('A4 吊車')
        Detail = self.env['daily.log.man.machine.detail']
        ptype = self.env['personnel.type'].search(
            [('record_type', '=', 'equipment')], limit=1)
        if not ptype:
            self.skipTest('環境無 record_type=equipment 的人機項目定義')
        # 明細的 daily_log_id 是 NOT NULL，得先有一張日誌；
        # 而日誌有 _check_progress_schedule_exists，工程得先有進度表
        self.env['progress.schedule'].create({
            'project_id': self.project.id,
            'version': 1,
            'calculation_mode': 'weekly',
            'change_date': '2026-08-07',
            'state': 'active',   # 約束找的是 state='active' 的那一張
        })
        employee = self.env['hr.employee'].create({'name': 'A4 測試填表人'})
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'employee_id': employee.id,
            'log_date': '2026-08-07',
        })
        for hrs in (3.0, 4.5):
            Detail.create({
                'daily_log_id': sheet.id,
                'personnel_type_id': ptype.id,
                'equipment_id': eq.id,
                'hours': hrs,
            })
        Detail.create({
            'daily_log_id': sheet.id,
            'personnel_type_id': ptype.id,
            'equipment_id': other.id,
            'hours': 99.0,
        })
        eq.invalidate_recordset(['total_usage_hours'])
        self.assertEqual(eq.total_usage_hours, 7.5,
                         '只該加總掛在本設備上的明細（3.0 + 4.5）')

    def test_project_id_required(self):
        """A5：所屬工程留空會讓列表全部落在「無」，改為必填。

        實查現有 supervision_equipment 筆數為 0，改必填不會影響既有資料。
        """
        self.assertTrue(
            self.env['supervision.equipment']._fields['project_id'].required,
            'supervision.equipment.project_id 應為必填')

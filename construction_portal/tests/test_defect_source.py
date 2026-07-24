# -*- coding: utf-8 -*-
"""C2 回歸測試 — 前台一般式缺失改讀 supervision.defect（157 筆真資料）。

原始 bug（稽核 C2）：`_defect_model()` 對一般式回傳 general.defect.improvement
（只有 07-14 批次 10 筆測試資料），真缺失 157 筆在 supervision.defect（匯入路由本就
寫這裡）→ 前台缺失頁近乎零筆。修法：一般式改讀 supervision.defect，並以前台相容層
（別名欄位 + Selection 值對映 + portal_workflow_state）讓共用模板/路由零改名相容。

本測試鎖定：(1) _defect_model 回 supervision.defect；(2) 相容層讀寫別名欄位/狀態對映
正確；(3) create 用 general 欄位名寫入會落到 supervision 真欄位；(4) 方法別名可呼叫。
"""

from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal


@tagged('post_install', '-at_install', 'construction_portal')
class TestDefectSource(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.project = cls.env['project.project'].create({
            'name': 'C2 缺失來源測試工程', 'code': 'C2-DEF',
            'state': 'construction', 'company_id': cls.env.company.id,
        })

    def test_defect_model_is_supervision(self):
        """一般式專案 → _defect_model 回 supervision.defect（不再是 general）。"""
        with MockRequest(self.env):
            self.assertEqual(self.ctrl._defect_model(self.project), 'supervision.defect')

    def test_compat_read_and_state_mapping(self):
        d = self.env['supervision.defect'].create({
            'project_id': self.project.id,
            'description': '牆面裂縫', 'location': 'B1',
            'defect_type': 'safety', 'source': 'daily_check', 'state': 'open',
        })
        # 讀別名欄位 → 橋接到 supervision 真欄位
        self.assertEqual(d.defect_description, '牆面裂縫')
        self.assertEqual(d.defect_location, 'B1')
        # Selection 值對映
        self.assertEqual(d.defect_category, 'safety')       # safety→safety
        self.assertEqual(d.source_type, 'daily_check')
        # 狀態詞彙對映：open → 'notified'（前台顯示為「可提交改善」）
        self.assertEqual(d.portal_workflow_state, 'notified')
        # check_type dummy 不 500
        self.assertFalse(d.check_type)

    def test_compat_create_with_general_field_names(self):
        """create 用 general 欄位名/類別值（模板/路由現況）→ 落到 supervision 真欄位。"""
        d = self.env['supervision.defect'].create({
            'project_id': self.project.id,
            'defect_description': '鋼筋外露', 'defect_location': '3F 樑',
            'defect_category': 'workmanship',   # general 值 → 映射 defect_type
            'source_type': 'daily_check',
            'check_type': 'construction',       # supervision 無此概念 → 被 inverse 吸收
        })
        self.assertEqual(d.description, '鋼筋外露')
        self.assertEqual(d.location, '3F 樑')
        self.assertEqual(d.defect_type, 'quality')   # workmanship → quality
        self.assertEqual(d.source, 'daily_check')

    def test_action_aliases_callable(self):
        d = self.env['supervision.defect'].create({
            'project_id': self.project.id, 'description': 'x',
            'defect_type': 'quality', 'source': 'daily_check', 'state': 'action_taken',
        })
        d.action_verify_pass()   # 別名 → action_verify
        self.assertEqual(d.state, 'verified')

    def test_photo_save_creates_attachment_m2m(self):
        """_defect_save_photos 對 supervision.defect 建 ir.attachment 掛 before_photo_ids。"""
        from odoo.addons.construction_portal.controllers.portal import _defect_save_photos

        class _F:
            filename = 'p.jpg'
            mimetype = 'image/jpeg'
            def read(self):
                return b'x'
        d = self.env['supervision.defect'].create({
            'project_id': self.project.id, 'description': 'x',
            'defect_type': 'quality', 'source': 'daily_check',
        })
        n = _defect_save_photos(self.env, d, [_F()], 'before')
        self.assertEqual(n, 1)
        self.assertEqual(len(d.before_photo_ids), 1)
        self.assertEqual(d.before_photo_ids[0]._name, 'ir.attachment')
        self.assertFalse(d.before_photo_ids[0].public)   # M0.6：非 public

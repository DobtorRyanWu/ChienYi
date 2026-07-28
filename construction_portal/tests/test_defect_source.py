# -*- coding: utf-8 -*-
"""前台缺失來源模型回歸測試。

背景：系統曾並存兩套一般式缺失模型 —— general.defect.improvement（實際在用）與
supervision.defect（NCR，停用）。C2 一度把前台一般式改讀 NCR，前提是「真資料在 NCR」，
該前提在本部署不成立。NCR 現已整個移除。

本測試鎖定移除後的契約：
  (1) _defect_model 依工程類型回 general / reservation，不會再出現 NCR
  (2) _browse_defect 只在這兩個模型間尋找
  (3) _defect_save_photos 一律走 .photo 子模型（三階段），不再有 M2M→ir.attachment 分支
"""

from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.controllers.portal_utils import (
    _defect_save_photos)


class _FakeUpload:
    """模擬 werkzeug FileStorage。"""
    filename = 'p.jpg'
    mimetype = 'image/jpeg'

    def read(self):
        return b'x'


@tagged('post_install', '-at_install', 'construction_portal')
class TestDefectSource(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.general_project = cls.env['project.project'].create({
            'name': '缺失來源測試工程（一般式）', 'code': 'DEF-GEN',
            'project_type': 'general',
            'state': 'construction', 'company_id': cls.env.company.id,
        })
        cls.reservation_project = cls.env['project.project'].create({
            'name': '缺失來源測試工程（預約式）', 'code': 'DEF-RSV',
            'project_type': 'reservation',
            'state': 'construction', 'company_id': cls.env.company.id,
        })
        # 缺失編號需要工程層級前綴設定，否則 _compute_defect_no 會 raise UserError
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.general_project.id,
            'supervision_prefix': 'TSTQA',
            'contractor_prefix': 'TSTQR',
        })

    def _make_defect(self, **overrides):
        vals = {
            'project_id': self.general_project.id,
            'record_type': 'supervision',
            'check_type': 'construction',
            'defect_category': 'workmanship',
            'defect_description': '牆面裂縫',
            'defect_location': 'B1',
            'source_type': 'daily_check',
            'state': 'notified',
        }
        vals.update(overrides)
        return self.env['general.defect.improvement'].create(vals)

    def test_supervision_defect_model_is_gone(self):
        """NCR 模型已整個移除，不應再存在於 registry。"""
        self.assertNotIn('supervision.defect', self.env)

    def test_defect_model_by_project_type(self):
        """一般式 → general；預約式 → reservation。"""
        with MockRequest(self.env):
            self.assertEqual(
                self.ctrl._defect_model(self.general_project),
                'general.defect.improvement')
            self.assertEqual(
                self.ctrl._defect_model(self.reservation_project),
                'reservation.defect.improvement')

    def test_defect_model_never_returns_ncr(self):
        """任何工程類型都不會回到 NCR。"""
        with MockRequest(self.env):
            for project in (self.general_project, self.reservation_project, False):
                self.assertNotEqual(
                    self.ctrl._defect_model(project), 'supervision.defect')

    def test_general_defect_carries_source_description(self):
        """來源登錄編號欄位存在且可寫（兩段式匯入的接合鍵）。"""
        d = self._make_defect(source_description='QA-001')
        self.assertEqual(d.source_description, 'QA-001')

    def test_defect_no_generated_from_prefix(self):
        """缺失編號 = 前綴 + 檢查類型首字 + 民國日期 + 當日序號。"""
        d = self._make_defect(found_date='2026-07-28')
        self.assertTrue(d.defect_no.startswith('TSTQA-施1150728_'),
                        f'非預期的缺失編號：{d.defect_no}')

    def test_portal_workflow_state_is_state_itself(self):
        """general 的前台流程狀態就是 state 本身（不再需要值對映）。"""
        d = self._make_defect(state='improving')
        self.assertEqual(d.portal_workflow_state, 'improving')

    def test_photo_save_creates_photo_line_not_attachment_m2m(self):
        """照片一律走 .photo 子模型，且支援 before/during/after 三階段。"""
        d = self._make_defect()
        for stage, field in (('before', 'before_photo_ids'),
                             ('during', 'during_photo_ids'),
                             ('after', 'after_photo_ids')):
            n = _defect_save_photos(self.env, d, [_FakeUpload()], stage)
            self.assertEqual(n, 1)
            lines = getattr(d, field)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]._name, 'general.defect.improvement.photo')
            self.assertEqual(lines[0].photo_stage, stage)

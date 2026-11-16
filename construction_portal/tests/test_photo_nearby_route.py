# -*- coding: utf-8 -*-
"""附近照片路由 /construction/<id>/photos/api/nearby 回歸測試。

原 bug：portal_photo.py 用了 math.cos() 卻沒 import math，只要座標有效就 NameError。
"""
from odoo.addons.website.tools import MockRequest
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)
from odoo.tests.common import TransactionCase, tagged

VIEWER = 'construction_supervision_base.group_portal_viewer'
LAT = 25.0330
LNG = 121.5654
NEAR_OFFSET = 0.001  # 約 100 公尺，落在預設 1 公里內
PNG_B64 = (b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')


@tagged('post_install', '-at_install', 'construction_portal')
class TestPhotoNearbyRoute(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(cls.env, '附近照片測試營造')
        cls.project = cls.env['project.project'].create({
            'name': '附近照片測試工程', 'code': 'NEARBY-1', 'state': 'construction',
            'company_id': cls.env.company.id, **contractor_project_vals(cls.contractor)})
        att = cls.env['ir.attachment'].create({
            'name': 'nearby.png', 'datas': PNG_B64, 'mimetype': 'image/png',
            'public': False, 'res_model': 'supervision.photo'})
        cls.photo = cls.env['supervision.photo'].create({
            'project_id': cls.project.id, 'attachment_id': att.id,
            'contractor_company_id': cls.contractor.id,
            'latitude': LAT + NEAR_OFFSET, 'longitude': LNG + NEAR_OFFSET})
        cls.member = cls.env['res.users'].create({
            'name': 'nearby_member', 'login': 'nearby_member',
            'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])],
            **contractor_user_vals(cls.contractor)})
        cls.env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.member.id})

    def _nearby(self, **post):
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=self.member)):
            return self.ctrl.portal_photos_map_nearby(self.project.id, **post)

    def test_nearby_returns_photos_with_distance(self):
        """有效座標：不得 NameError，回傳的照片非空且每筆帶距離。"""
        res = self._nearby(lat=LAT, lng=LNG, radius=1.0)
        self.assertNotIn('error', res)
        self.assertTrue(res['photos'], '1 公里內有一張照片，不該是空的')
        for item in res['photos']:
            self.assertIn('distance', item)
            self.assertLessEqual(item['distance'], 1.0)

    def test_nearby_zero_coordinate_returns_empty(self):
        """座標為 0 走提早返回，與修前行為一致。"""
        self.assertEqual(self._nearby(lat=0, lng=0), {'photos': []})

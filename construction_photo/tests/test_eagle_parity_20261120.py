# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：照片的拍攝日期可以晚於現在。

舊系統（EAGLE）對這些輸入沒有檢查：上傳照片不驗證拍攝日期（後端 models/schemas/image.js、前端 Pictures.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（PH-02）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_photo')
class TestEagleParityPhoto(TransactionCase):

    def test_shot_at_in_future_allowed(self):
        project = self.env['project.project'].create({
            'name': '回復原版照片', 'code': 'EP-PH', 'company_id': self.env.company.id})
        att = self.env['ir.attachment'].create({
            'name': 'ep_future.jpg', 'raw': b'x', 'mimetype': 'image/jpeg',
            'res_model': 'supervision.photo', 'res_id': 0})
        future = fields.Datetime.now() + timedelta(days=2)
        photo = self.env['supervision.photo'].create({
            'project_id': project.id, 'attachment_id': att.id, 'shot_at': future})
        self.env.flush_all()
        self.assertEqual(photo.shot_at, future)

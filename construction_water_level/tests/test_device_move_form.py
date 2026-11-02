# -*- coding: utf-8 -*-
"""B11 — 在表單上把設備從工程場域改到社區場域，存檔不可跳「工程案件與場域不一致」（2026-11-02）。

project_id 在表單上是 readonly，onchange 把它清空的值不會被存檔（Odoo 18 對唯讀欄位只在
force_save 時才寫），於是只剩 site_id 改了、project_id 還在 → constrains 擋下。
用 odoo.tests.Form 走真實表單的 onchange／唯讀規則重現。
"""

from odoo.tests import Form, common, tagged


@tagged('post_install', '-at_install', 'construction_water_level')
class TestDeviceMoveForm(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({'name': 'B11 水位工程'})
        cls.project_site = cls.env['water.level.site'].create({
            'name': 'B11 工程場域', 'site_type': 'project', 'project_id': cls.project.id})
        site_vals = {'name': 'B11 社區場域', 'site_type': 'community'}
        # 社區模組有裝時，社區場域必須有管理方
        if 'owner_partner_id' in cls.env['water.level.site']._fields:
            site_vals['owner_partner_id'] = cls.env['res.partner'].create({'name': 'B11 管委會'}).id
        cls.community_site = cls.env['water.level.site'].create(site_vals)
        cls.device = cls.env['water.level.device'].create({
            'name': 'B11 站', 'site_id': cls.project_site.id, 'device_uid': 'B11-MOVE-01'})

    def test_move_project_device_to_community_site_via_form(self):
        self.assertEqual(self.device.project_id, self.project, '前置：工程設備帶有 project_id')
        with Form(self.device) as form:
            form.site_id = self.community_site
        self.assertEqual(self.device.site_id, self.community_site)
        self.assertFalse(self.device.project_id, '社區場域的設備不應再有工程案件')

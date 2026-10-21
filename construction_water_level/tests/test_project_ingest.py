# -*- coding: utf-8 -*-
"""工程這一側在拆模組後仍然成立的兩件事。

1. **上報寫入的讀值要帶 project_id**。ingest 走原生 SQL，stored related 不會自動算；
   拆模組前是核心直接把 project_id 寫進 INSERT，拆完改由本模組經
   `_ingest_extra_columns()` 擴充點補上。拿掉那個覆寫，這支測試就會紅——
   工程前台的權限 rule 走 device_id.project_id，但後台依工程篩讀值、報表都看 reading.project_id。
2. 工程場域一定要綁工程案件（約束從核心搬過來，不能在搬家途中掉了）。
"""

from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestProjectIngest(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({'name': '水位測試工程（拆模組）'})
        cls.site = cls.env['water.level.site'].create({
            'name': '測試工程場域', 'site_type': 'project', 'project_id': cls.project.id,
        })
        cls.device = cls.env['water.level.device'].create({
            'name': '測試站', 'site_id': cls.site.id, 'device_uid': 'TEST-SPLIT-PROJ-01',
        })

    def test_device_inherits_project_from_site(self):
        self.assertEqual(self.device.project_id, self.project)

    def test_ingest_writes_project_id(self):
        result = self.device.ingest_readings([
            {'ts': datetime(2026, 10, 20, 1, 0), 'value': 1.25, 'seq_no': 1},
            {'ts': datetime(2026, 10, 20, 1, 1), 'value': 1.30, 'seq_no': 2},
        ])
        self.assertEqual(result['accepted'], 2)
        readings = self.env['water.level.reading'].search([('device_id', '=', self.device.id)])
        self.assertEqual(len(readings), 2)
        self.assertEqual(readings.project_id, self.project,
                         'ingest 走原生 SQL，project_id 必須由 _ingest_extra_columns 明寫')

    def test_project_site_requires_project(self):
        with self.assertRaises(ValidationError):
            self.env['water.level.site'].create({'name': '沒綁工程', 'site_type': 'project'})

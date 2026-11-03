# -*- coding: utf-8 -*-
"""照片：表單不提供「新增」；經緯度不被分組加總（2026-11-03）。

* 照片一定要有檔案（attachment_id required），空白表單新增只會建出沒有照片的紀錄，
  上傳一律走「批次上傳照片」精靈。
* latitude／longitude 是 Float，預設 aggregator='sum'，依日期分組的清單
  分組列會把經緯度加總成無意義的數字。
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_photo')
class TestPhotoNoCreateAndAggregator(TransactionCase):

    def test_views_do_not_offer_create(self):
        res = self.env['supervision.photo'].get_views(
            [(False, 'form'), (False, 'list'), (False, 'kanban')])
        for vtype in ('form', 'list', 'kanban'):
            root = etree.fromstring(res['views'][vtype]['arch'])
            self.assertEqual(
                root.get('create'), 'false',
                '照片的 %s 檢視不該提供「新增」' % vtype)

    def test_gps_fields_not_summed(self):
        info = self.env['supervision.photo'].fields_get(
            ['latitude', 'longitude'], ['aggregator'])
        for name in ('latitude', 'longitude'):
            self.assertFalse(
                info[name].get('aggregator'),
                '%s 不該有 aggregator（分組列會加總經緯度）' % name)

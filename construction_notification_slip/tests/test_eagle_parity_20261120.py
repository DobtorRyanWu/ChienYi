# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：通報單裡舊系統沒有的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的通報單每一欄離開輸入框就存，狀態是下拉自己選，沒有依狀態鎖欄位或擋動作
（前端 components/resource/m_appointment/AppointmentSheet.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（NS 開頭的編號）。
退單（新功能）之後整張唯讀的規則不動。
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged

FORM_XMLID = 'construction_notification_slip.view_reservation_notification_slip_form'
# 已結案後照舊系統還能改的欄位（NS-14）
EDITABLE_AFTER_CLOSED = ('location', 'location_detail', 'latitude', 'longitude', 'detail_line_ids')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipForm(TransactionCase):

    def test_closed_slip_fields_not_readonly_in_form(self):
        """NS-14：已結案的通報單，明細與施工地點在表單上不再唯讀；退單後照舊唯讀。"""
        arch = etree.fromstring(self.env.ref(FORM_XMLID).arch)
        for name in EDITABLE_AFTER_CLOSED:
            nodes = arch.xpath("//field[@name='%s']" % name)
            self.assertTrue(nodes, name)
            readonly = nodes[0].get('readonly') or ''
            self.assertNotIn('closed', readonly, '%s 已結案後不該唯讀' % name)
            self.assertIn('cancelled', readonly, '%s 退單後仍要唯讀' % name)
        add_button = arch.xpath("//button[@name='action_open_add_lines_wizard']")[0]
        self.assertNotIn('closed', add_button.get('invisible') or '', '已結案後「加入工項」按鈕不該消失')

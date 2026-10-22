# -*- coding: utf-8 -*-
"""社區前台的可見性：成員看得到自己的社區，非成員什麼都看不到。

**這個測試在防什麼**
拆模組前，事件（water.level.event）、事件影像（event.frame）、日摘要（reading.daily）
給了 base.group_portal 讀取 ACL，卻**沒有任何 record rule**——Odoo 的規則是「這個群組
在這個模型上沒有 rule 就是全開」，所以任何前台帳號都讀得到所有場域（含別的社區、
含工程）的事件與日摘要。拆模組時把 ACL 與成員制 rule 綁在同一個模組一起給。
拿掉 security/water_level_security.xml 裡事件那三條 rule，test_outsider_sees_no_event
與 test_outsider_sees_no_daily 會紅（2026-10-20 實測）。容量曲線同一個洞，見
test_outsider_sees_no_tank_curve。

另外釘住兩件搬家途中容易掉的事：事件建立時帶入蓄水池、社區場域必填管委會。
"""

from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import common, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCommunityAccess(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = new_test_user(cls.env, login='wl_comm_member', groups='base.group_portal')
        cls.outsider = new_test_user(cls.env, login='wl_comm_outsider', groups='base.group_portal')
        owner = cls.env['res.partner'].create({'name': '測試管委會（權限）'})
        cls.site = cls.env['water.level.site'].create({
            'name': '測試社區（權限）', 'site_type': 'community',
            'owner_partner_id': owner.id, 'member_user_ids': [(6, 0, [cls.member.id])],
        })
        cls.tank = cls.env['water.level.tank'].create({
            'name': '一號池', 'site_id': cls.site.id,
            'bottom_elevation': 0.0, 'full_elevation': 3.0, 'effective_volume_m3': 30.0,
        })
        cls.device = cls.env['water.level.device'].create({
            'name': '一號池水位計', 'site_id': cls.site.id, 'tank_id': cls.tank.id,
            'device_uid': 'TEST-COMM-ACCESS-01', 'alert_direction': 'low',
        })
        cls.event = cls.env['water.level.event'].create({
            'device_id': cls.device.id, 'event_type': 'offline', 'severity': 'warning',
            'start_ts': fields.Datetime.now(),
        })
        cls.daily = cls.env['water.level.reading.daily'].create({
            'device_id': cls.device.id, 'day': date(2026, 10, 20),
        })

    # ---------- 事件／日摘要：原本的權限洞 ----------

    def test_outsider_sees_no_event(self):
        Event = self.env['water.level.event'].with_user(self.outsider)
        self.assertFalse(Event.search([('id', '=', self.event.id)]),
                         '非成員的前台帳號不該搜得到別人社區的事件')
        with self.assertRaises(AccessError):
            Event.browse(self.event.id).read(['name'])

    def test_outsider_sees_no_daily(self):
        Daily = self.env['water.level.reading.daily'].with_user(self.outsider)
        self.assertFalse(Daily.search([('id', '=', self.daily.id)]))

    def test_member_sees_own_event_and_daily(self):
        self.assertEqual(
            self.env['water.level.event'].with_user(self.member).search(
                [('id', '=', self.event.id)]), self.event)
        self.assertEqual(
            self.env['water.level.reading.daily'].with_user(self.member).search(
                [('id', '=', self.daily.id)]), self.daily)

    # ---------- 場域／蓄水池：搬家後仍是成員制 ----------

    def test_outsider_sees_no_site_or_tank(self):
        self.assertFalse(self.env['water.level.site'].with_user(self.outsider).search(
            [('id', '=', self.site.id)]))
        self.assertFalse(self.env['water.level.tank'].with_user(self.outsider).search(
            [('id', '=', self.tank.id)]))

    def test_outsider_sees_no_tank_curve(self):
        """容量曲線同樣是「有 portal ACL、沒有 rule」的洞（審查時發現，拆分前就存在）。"""
        curve = self.env['water.level.tank.curve'].create({
            'tank_id': self.tank.id, 'elevation': 1.0, 'volume_m3': 10.0})
        Curve = self.env['water.level.tank.curve']
        self.assertFalse(Curve.with_user(self.outsider).search([('id', '=', curve.id)]))
        self.assertEqual(Curve.with_user(self.member).search([('id', '=', curve.id)]), curve)

    def test_member_sees_site_and_tank(self):
        self.assertEqual(self.env['water.level.site'].with_user(self.member).search(
            [('id', '=', self.site.id)]), self.site)
        self.assertEqual(self.env['water.level.tank'].with_user(self.member).search(
            [('id', '=', self.tank.id)]), self.tank)

    # ---------- 搬家途中容易掉的行為 ----------

    def test_event_records_tank_at_creation(self):
        """拆模組前由核心兩個建立點各自寫 tank_id；拆完改由本模組覆寫 create 帶入。"""
        self.assertEqual(self.event.tank_id, self.tank)
        opened = self.env['water.level.monitor']._open_event(
            self.device, 'level_low', 'warning', '測試')
        self.assertEqual(opened.tank_id, self.tank)

    def test_community_site_requires_owner(self):
        with self.assertRaises(ValidationError):
            self.env['water.level.site'].create({'name': '沒有管委會', 'site_type': 'community'})

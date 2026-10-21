# -*- coding: utf-8 -*-
"""有歷史資料的監測站不准改掛到別的場域。

**這個測試在防什麼**

讀值、事件、日摘要都靠「哪一台設備」判斷屬於哪個場域，前台的成員 rule 也是。
內部使用者若把設備改掛到另一個場域，那台的整段歷史就會變成新場域的成員看得到
（例如 A 社區的水位紀錄跑到 B 社區的管委會眼前）。

讀值保存期滿會被清掉、日摘要還在，所以三種紀錄各自都要擋，不能只看讀值。
"""

from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import common, tagged

from .common import site_vals


@tagged('post_install', '-at_install')
class TestDeviceSiteLock(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Site = cls.env['water.level.site']
        cls.site_a = Site.create(site_vals(cls.env, '場域鎖測試 A'))
        cls.site_b = Site.create(site_vals(cls.env, '場域鎖測試 B'))

    def _device(self, uid):
        return self.env['water.level.device'].create({
            'name': uid, 'site_id': self.site_a.id, 'device_uid': uid})

    def test_device_without_history_can_move(self):
        device = self._device('TEST-SITE-LOCK-EMPTY')
        device.write({'site_id': self.site_b.id})
        self.assertEqual(device.site_id, self.site_b)

    def test_rewriting_same_site_is_allowed(self):
        device = self._device('TEST-SITE-LOCK-SAME')
        self.env['water.level.reading'].create({
            'device_id': device.id, 'ts': datetime(2026, 10, 20, 8, 0), 'value': 1.0})
        device.write({'site_id': self.site_a.id, 'name': '改名不換場域'})
        self.assertEqual(device.name, '改名不換場域')

    def test_device_with_reading_cannot_move(self):
        device = self._device('TEST-SITE-LOCK-READING')
        self.env['water.level.reading'].create({
            'device_id': device.id, 'ts': datetime(2026, 10, 20, 8, 0), 'value': 1.0})
        with self.assertRaisesRegex(UserError, '不能改掛到別的監測場域'):
            device.write({'site_id': self.site_b.id})
        self.assertEqual(device.site_id, self.site_a)

    def test_device_with_only_daily_summary_cannot_move(self):
        # 讀值已過保存期被清掉、只剩日摘要
        device = self._device('TEST-SITE-LOCK-DAILY')
        self.env['water.level.reading.daily'].create({
            'device_id': device.id, 'day': date(2026, 10, 20)})
        with self.assertRaisesRegex(UserError, '不能改掛到別的監測場域'):
            device.write({'site_id': self.site_b.id})

    def test_device_with_only_event_cannot_move(self):
        device = self._device('TEST-SITE-LOCK-EVENT')
        self.env['water.level.event'].create({
            'device_id': device.id, 'event_type': 'level_high',
            'start_ts': datetime(2026, 10, 20, 8, 0)})
        with self.assertRaisesRegex(UserError, '不能改掛到別的監測場域'):
            device.write({'site_id': self.site_b.id})

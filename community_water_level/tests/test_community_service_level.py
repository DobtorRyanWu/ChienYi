# -*- coding: utf-8 -*-
"""方案等級設在社區、設備跟著社區（2026-10-21 使用者定案）。

core 的三個方案檢查點（影像 402、即時告警、雜湊鏈 cron）都讀**設備**的等級，前台的功能開關讀**場域**的等級——
兩邊不一致時，前台說有、core 說沒有（或反過來），所以要守的是「社區場域底下每一台設備（含停用的）都等於場域」。
"""

from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.community_water_level.controllers.portal_community_water import CommunityWaterPortal
from odoo.addons.water_level_core.models.water_level_device import LEVEL_ADVANCED, LEVEL_BASIC, LEVEL_FLAGSHIP


@tagged('post_install', '-at_install')
class TestCommunityServiceLevel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env['res.partner'].create({'name': '測試管委會（方案）'})
        cls.Site = cls.env['water.level.site']
        cls.Device = cls.env['water.level.device']

    def _site(self, name, **vals):
        return self.Site.create(dict({'name': name, 'site_type': 'community', 'owner_partner_id': self.owner.id}, **vals))

    def _device(self, site, uid, **vals):
        return self.Device.create(dict({'name': uid, 'device_uid': uid, 'site_id': site.id}, **vals))

    def test_new_device_takes_the_site_level(self):
        site = self._site('方案甲社區', service_level=LEVEL_FLAGSHIP)
        device = self._device(site, 'SL-TAKE-1')
        self.assertEqual(device.service_level, LEVEL_FLAGSHIP, '社區場域建設備沒帶等級，要跟著場域')
        self.assertTrue(device.feature_realtime_alert, 'core 的即時告警開關讀設備等級，跟著場域才開得起來')

    def test_changing_site_level_moves_every_device_including_archived(self):
        site = self._site('方案乙社區')
        live = self._device(site, 'SL-SYNC-LIVE')
        archived = self._device(site, 'SL-SYNC-OLD')
        archived.active = False
        site.service_level = LEVEL_ADVANCED
        self.assertEqual(live.service_level, LEVEL_ADVANCED)
        self.assertEqual(archived.service_level, LEVEL_ADVANCED,
                         '停用的設備也要跟著改，否則重新啟用時前台與 core 會各說各話')

    def test_device_level_cannot_drift_from_its_community(self):
        site = self._site('方案丙社區', service_level=LEVEL_ADVANCED)
        device = self._device(site, 'SL-DRIFT-1')
        with self.assertRaises(ValidationError):
            device.service_level = LEVEL_FLAGSHIP
        with self.assertRaises(ValidationError):
            self._device(site, 'SL-DRIFT-2', service_level=LEVEL_BASIC)

    def test_level_at_least(self):
        site = self._site('方案丁社區', service_level=LEVEL_ADVANCED)
        self.assertTrue(site._community_level_at_least(LEVEL_BASIC))
        self.assertTrue(site._community_level_at_least(LEVEL_ADVANCED), '等於門檻要放行（>= 不是 >）')
        self.assertFalse(site._community_level_at_least(LEVEL_FLAGSHIP))

    def test_migration_takes_the_highest_level_of_its_devices(self):
        """既有庫升級時，場域取旗下（含停用）設備的最高等級——不讓客戶掉功能。

        遷移前的狀態（設備等級各自不同）在新約束下建不出來，只能用 SQL 直接寫回舊狀態。
        空庫 -i 不會跑 migrations，所以直接呼叫遷移方法（L2⑫）。"""
        mixed = self._site('遷移混合社區')
        empty = self._site('遷移空社區', service_level=LEVEL_ADVANCED)
        devices = self._device(mixed, 'MIG-B') | self._device(mixed, 'MIG-A') | self._device(mixed, 'MIG-F')
        legacy = {'MIG-B': LEVEL_BASIC, 'MIG-A': LEVEL_ADVANCED, 'MIG-F': LEVEL_FLAGSHIP}
        for device in devices:
            self.env.cr.execute('UPDATE water_level_device SET service_level = %s WHERE id = %s',
                                (legacy[device.device_uid], device.id))
        self.env.cr.execute('UPDATE water_level_device SET active = FALSE WHERE id = %s',
                            (devices.filtered(lambda d: d.device_uid == 'MIG-F').id,))
        self.env.cr.execute("UPDATE water_level_site SET service_level = %s WHERE id IN %s",
                            (LEVEL_BASIC, (mixed.id, empty.id)))
        self.env.invalidate_all()

        result = self.Site._community_migrate_service_levels()

        self.assertEqual(mixed.service_level, LEVEL_FLAGSHIP, '最高的那台是停用的旗艦，也要算進去')
        self.assertEqual(set(devices.with_context(active_test=False).mapped('service_level')), {LEVEL_FLAGSHIP})
        self.assertEqual(empty.service_level, LEVEL_BASIC, '沒有設備的社區＝基本')
        self.assertEqual(result[mixed.id], (LEVEL_BASIC, LEVEL_FLAGSHIP))


@tagged('post_install', '-at_install')
class TestCommunityLocalTime(TransactionCase):
    """社區頁的時間一律台灣時區，不跟著帳號——管委會帳號常常沒設時區，沒設就會印成 UTC。"""

    def test_last_reading_stamp_is_taiwan_time(self):
        owner = self.env['res.partner'].create({'name': '測試管委會（時區）'})
        site = self.env['water.level.site'].create({'name': '時區社區', 'site_type': 'community',
                                                    'owner_partner_id': owner.id})
        tank = self.env['water.level.tank'].create({'name': '時區池', 'site_id': site.id, 'bottom_elevation': 0.0,
                                                    'full_elevation': 3.0, 'effective_volume_m3': 30.0})
        device = self.env['water.level.device'].create({'name': '時區表', 'device_uid': 'TZ-1', 'site_id': site.id,
                                                        'tank_id': tank.id})
        # UTC 10-20 16:30＝台灣 10-21 00:30（換日那一側才抓得到「印成 UTC」的錯）
        device.write({'last_seen': datetime(2026, 10, 20, 16, 30)})
        payload = CommunityWaterPortal()._community_tank_payload(tank)
        self.assertEqual(payload['last_ts'], '10/21 00:30')
        self.assertIsInstance(payload['last_ts_age_h'], int)

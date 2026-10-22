# -*- coding: utf-8 -*-
"""社區頁一定要回得到 /my。

只有一個社區的人，/community 會直接導回那個社區的頁面——原本社區頁的返回連結寫死 /community，
於是按「‹」原地不動、整頁沒有任何路回 /my（2026-10-21 使用者在 8071 實際踩到）。
斷言打在使用者拿到的東西上：頁首返回連結的 href，以及跟過去之後實際停在哪一頁。
"""

import re

from odoo.tests import HttpCase, new_test_user, tagged

PASSWORD = 'cw-nav-Pass-2026'
BACK_LINK = re.compile(r'<a\b[^>]*\bclass="cw-header-back"[^>]*>')
HREF = re.compile(r'\bhref="([^"]*)"')


@tagged('post_install', '-at_install')
class TestCommunityPageNavigation(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.single = new_test_user(cls.env, login='cw_nav_single', password=PASSWORD,
                                   groups='base.group_portal')
        cls.multi = new_test_user(cls.env, login='cw_nav_multi', password=PASSWORD,
                                  groups='base.group_portal')
        owner = cls.env['res.partner'].create({'name': '測試管委會（導覽）'})
        Site = cls.env['water.level.site']
        cls.site_a = Site.create({'name': '導覽測試甲社區', 'site_type': 'community',
                                  'owner_partner_id': owner.id,
                                  'member_user_ids': [(6, 0, [cls.single.id, cls.multi.id])]})
        cls.site_b = Site.create({'name': '導覽測試乙社區', 'site_type': 'community',
                                  'owner_partner_id': owner.id,
                                  'member_user_ids': [(6, 0, [cls.multi.id])]})

    def _back_href(self, user, site):
        self.authenticate(user.login, PASSWORD)
        res = self.url_open('/community/%s/water' % site.id)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.url.endswith('/community/%s/water' % site.id), '前提不成立：沒有停在社區頁 %s' % res.url)
        tags = BACK_LINK.findall(res.text)
        self.assertEqual(len(tags), 1, '頁首應該恰好有一個返回連結，找到 %d 個' % len(tags))
        return HREF.search(tags[0]).group(1)

    def test_single_community_member_can_get_back_to_my(self):
        href = self._back_href(self.single, self.site_a)
        self.assertEqual(href, '/my', '只有一個社區的人，返回要回到 /my')
        res = self.url_open(href)
        self.assertTrue(res.url.endswith('/my'), '跟著返回連結走，應該停在 /my，實際停在 %s' % res.url)

    def test_multi_community_member_goes_back_to_the_list(self):
        href = self._back_href(self.multi, self.site_a)
        self.assertEqual(href, '/community', '有兩個社區的人，返回要回到社區清單')
        res = self.url_open(href)
        self.assertTrue(res.url.endswith('/community'), '兩個社區的人在清單頁不該被自動導走，實際停在 %s' % res.url)

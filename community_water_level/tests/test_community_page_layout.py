# -*- coding: utf-8 -*-
"""社區水情頁的大螢幕兩欄版面，靠樣板與 CSS 之間的約定成立。

community_water.css 在 ≥1200px 把 #wlApp 排成左右兩欄：左欄 .cw-col-side（站名列、池卡片、時間範圍），
右欄 .cw-col-main（歷程圖、地圖）。這兩層包裝少了或放錯，CSS 不會報錯、頁面也照樣 200，
只是大螢幕默默退回單欄——所以把約定寫成測試。放寬寬度只掛在水情頁（.cw-water），
社區清單頁不跟著變寬。實際排版（各寬度的位置、地圖不缺塊）在 water-odoo/tools/check_community_layout.py。
"""

from lxml import html

from odoo.tests import HttpCase, new_test_user, tagged

PASSWORD = 'cw-layout-Pass-2026'
SIDE = "//div[@id='wlApp']/div[contains(concat(' ', @class, ' '), ' cw-col-side ')]"
MAIN = "//div[@id='wlApp']/div[contains(concat(' ', @class, ' '), ' cw-col-main ')]"
WATER_APP = "//div[contains(concat(' ', @class, ' '), ' cw-app ') and contains(concat(' ', @class, ' '), ' cw-water ')]"


@tagged('post_install', '-at_install')
class TestCommunityPageLayout(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='cw_layout_user', password=PASSWORD, groups='base.group_portal')
        owner = cls.env['res.partner'].create({'name': '測試管委會（版面）'})
        Site = cls.env['water.level.site']
        cls.site = Site.create({'name': '版面測試甲社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                                'member_user_ids': [(6, 0, [cls.user.id])]})
        # 第二個社區讓 /community 停在清單頁（只有一個社區會被直接導進去）
        Site.create({'name': '版面測試乙社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                     'member_user_ids': [(6, 0, [cls.user.id])]})
        cls.env['water.level.tank'].create({
            'name': '版面一號池', 'site_id': cls.site.id,
            'bottom_elevation': 0.0, 'full_elevation': 3.0, 'effective_volume_m3': 30.0,
        })

    def _page(self, url):
        self.authenticate(self.user.login, PASSWORD)
        res = self.url_open(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.url.endswith(url), '前提不成立：沒有停在 %s，實際 %s' % (url, res.url))
        return html.fromstring(res.content)

    def test_water_page_splits_into_side_and_main_columns(self):
        doc = self._page('/community/%s/water' % self.site.id)
        self.assertEqual(len(doc.xpath(WATER_APP)), 1, '水情頁外框要帶 cw-water，大螢幕的放寬規則才套得上')
        self.assertEqual(len(doc.xpath(SIDE)), 1, '#wlApp 底下要恰好一個左欄 .cw-col-side')
        self.assertEqual(len(doc.xpath(MAIN)), 1, '#wlApp 底下要恰好一個右欄 .cw-col-main')
        for node_id in ('wlTanks', 'wlRanges'):
            self.assertEqual(len(doc.xpath("%s//*[@id='%s']" % (SIDE, node_id))), 1, '#%s 要在左欄' % node_id)
        for node_id in ('wlChart', 'wlMapCard'):
            self.assertEqual(len(doc.xpath("%s//*[@id='%s']" % (MAIN, node_id))), 1, '#%s 要在右欄' % node_id)
        # DOM 順序＝手機版由上而下的順序：池 → 時間範圍 → 圖表 → 地圖
        order = [el.get('id') for el in doc.xpath("//*[@id='wlTanks' or @id='wlRanges' or @id='wlChart' or @id='wlMapCard']")]
        self.assertEqual(order, ['wlTanks', 'wlRanges', 'wlChart', 'wlMapCard'])

    def test_site_list_page_does_not_widen(self):
        doc = self._page('/community')
        self.assertTrue(doc.xpath("//ul[contains(@class, 'cw-site-list')]"), '前提不成立：沒有看到社區清單')
        self.assertFalse(doc.xpath(WATER_APP), '社區清單頁不該帶 cw-water（大螢幕放寬只給水情頁）')

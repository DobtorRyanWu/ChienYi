# -*- coding: utf-8 -*-
"""社區前台的事件清單、詳情、簽收、事件影像、單一事件 PDF。

斷言打在使用者拿到的東西上：HTTP 狀態、頁面文字、影像位元組、資料庫裡簽收欄位的值。
門的規則（交接定案）：不是成員＝讀不到；別社區的事件／影像 id 帶到自己社區的網址下＝不存在（404）；
方案不含（影像、PDF 要進階）＝路由端擋，不能只藏按鈕。
"""

import base64
import hashlib
import re
from datetime import datetime

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.water_level_core.models.water_level_device import LEVEL_ADVANCED, LEVEL_BASIC

PASSWORD = 'cw-events-Pass-2026'
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')         # 簽收表單裡的
JS_CSRF = re.compile(r'csrf_token["\s]*[:=]\s*"([^"]+)"')          # 版面 script 裡的（每頁都有，綁目前 session）
# 1×1 透明 PNG：影像路由回的位元組要能拿來比 sha256
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
NOT_FOUND = 404


@tagged('post_install', '-at_install')
class TestCommunityEvents(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adv_member = new_test_user(cls.env, login='cw_ev_adv', password=PASSWORD, groups='base.group_portal')
        cls.adv_member2 = new_test_user(cls.env, login='cw_ev_adv2', password=PASSWORD, groups='base.group_portal')
        cls.basic_member = new_test_user(cls.env, login='cw_ev_basic', password=PASSWORD, groups='base.group_portal')
        cls.outsider = new_test_user(cls.env, login='cw_ev_out', password=PASSWORD, groups='base.group_portal')
        owner = cls.env['res.partner'].create({'name': '測試管委會（事件）'})
        Site = cls.env['water.level.site']
        cls.adv_site = Site.create({'name': '事件進階社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                                    'service_level': LEVEL_ADVANCED,
                                    'member_user_ids': [(6, 0, [cls.adv_member.id, cls.adv_member2.id])]})
        cls.basic_site = Site.create({'name': '事件基本社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                                      'service_level': LEVEL_BASIC,
                                      'member_user_ids': [(6, 0, [cls.basic_member.id])]})
        cls.adv_event, cls.adv_frame = cls._event_with_frame(cls.adv_site, 'EV-ADV')
        cls.basic_event, cls.basic_frame = cls._event_with_frame(cls.basic_site, 'EV-BASIC')

    @classmethod
    def _event_with_frame(cls, site, uid):
        device = cls.env['water.level.device'].create({'name': uid, 'device_uid': uid, 'site_id': site.id})
        event = cls.env['water.level.event'].create({
            'device_id': device.id, 'event_type': 'level_high', 'severity': 'critical',
            'start_ts': datetime(2026, 10, 20, 16, 30), 'peak_value': 2.5})
        attachment = cls.env['ir.attachment'].create({
            'name': '%s.png' % uid, 'raw': PNG, 'mimetype': 'image/png', 'res_model': 'water.level.event.frame'})
        frame = cls.env['water.level.event.frame'].create({
            'event_id': event.id, 'ts': datetime(2026, 10, 20, 16, 31), 'kind': 'peak',
            'attachment_id': attachment.id, 'frame_hash': hashlib.sha256(PNG).hexdigest(), 'byte_size': len(PNG)})
        attachment.res_id = frame.id
        return event, frame

    def _get(self, user, url):
        self.authenticate(user.login, PASSWORD)
        return self.url_open(url)

    def _urls(self, site, event, frame):
        base = '/community/%s/events' % site.id
        return {
            'detail': '%s/%s' % (base, event.id),
            'frame': '%s/%s/frames/%s' % (base, event.id, frame.id),
            'pdf': '%s/%s/report.pdf' % (base, event.id),
        }

    # ---------- 門 ----------

    def test_outsider_reaches_nothing(self):
        res = self._get(self.outsider, '/community/%s/events' % self.adv_site.id)
        self.assertNotIn(self.adv_event.name, res.text, '非成員的事件清單不能出現別人的事件')
        for kind, url in self._urls(self.adv_site, self.adv_event, self.adv_frame).items():
            res = self.url_open(url)
            self.assertEqual(res.status_code, NOT_FOUND, '非成員打 %s 要 404（%s）' % (kind, url))

    def test_foreign_ids_under_own_site_are_not_found(self):
        """basic 成員把進階社區的事件／影像 id 換到自己社區的網址下。"""
        self.authenticate(self.basic_member.login, PASSWORD)
        for kind, url in self._urls(self.basic_site, self.adv_event, self.adv_frame).items():
            self.assertEqual(self.url_open(url).status_code, NOT_FOUND, '別社區的 %s 不能拿到（%s）' % (kind, url))
        # 自己社區的事件、別社區的影像
        url = '/community/%s/events/%s/frames/%s' % (self.adv_site.id, self.adv_event.id, self.basic_frame.id)
        self.authenticate(self.adv_member.login, PASSWORD)
        self.assertEqual(self.url_open(url).status_code, NOT_FOUND, '影像不屬於這個事件')

    def test_event_list_shows_only_own_site_and_hides_acked_by_default(self):
        res = self._get(self.adv_member, '/community/%s/events' % self.adv_site.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.adv_event.name, res.text)
        self.assertNotIn(self.basic_event.name, res.text)
        self.adv_event.sudo().write({'ack_user_id': self.adv_member.id, 'ack_at': datetime(2026, 10, 21, 1, 0)})
        self.assertNotIn(self.adv_event.name, self.url_open('/community/%s/events' % self.adv_site.id).text,
                         '預設只列未處理（未簽收）')
        self.assertIn(self.adv_event.name, self.url_open('/community/%s/events?filter=all' % self.adv_site.id).text)

    def test_detail_time_is_taiwan_time(self):
        res = self._get(self.adv_member, self._urls(self.adv_site, self.adv_event, self.adv_frame)['detail'])
        self.assertIn('2026-10-21 00:30', res.text, 'UTC 10-20 16:30 要顯示成台灣 10-21 00:30')

    # ---------- 方案 ----------

    def test_basic_plan_gets_no_frames_or_pdf(self):
        urls = self._urls(self.basic_site, self.basic_event, self.basic_frame)
        res = self._get(self.basic_member, urls['detail'])
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(urls['frame'], res.text, '基本方案的詳情頁不給影像')
        self.assertEqual(self.url_open(urls['frame']).status_code, NOT_FOUND, '基本方案直接打影像網址也要擋')
        self.assertEqual(self.url_open(urls['pdf']).status_code, NOT_FOUND, '基本方案直接打 PDF 網址也要擋')

    def test_advanced_plan_gets_the_exact_frame_bytes_and_the_pdf(self):
        urls = self._urls(self.adv_site, self.adv_event, self.adv_frame)
        res = self._get(self.adv_member, urls['detail'])
        self.assertIn(urls['frame'], res.text, '進階方案的詳情頁要有影像')
        frame = self.url_open(urls['frame'])
        self.assertEqual(frame.status_code, 200)
        self.assertEqual(hashlib.sha256(frame.content).hexdigest(), self.adv_frame.frame_hash,
                         '回傳的位元組要等於上傳時的雜湊（不是灰色預設圖）')
        pdf = self.url_open(urls['pdf'])
        self.assertEqual(pdf.status_code, 200)
        # 測試模式下 Odoo 不跑 wkhtmltopdf、回 HTML；真的 PDF 在 E2E 打開看
        self.assertIn(self.adv_event.name, pdf.text)

    def test_frame_whose_attachment_belongs_elsewhere_is_refused(self):
        stray = self.env['ir.attachment'].create({'name': 'stray.png', 'raw': PNG, 'mimetype': 'image/png',
                                                  'res_model': 'res.partner', 'res_id': self.adv_member.partner_id.id})
        frame = self.env['water.level.event.frame'].create({
            'event_id': self.adv_event.id, 'ts': datetime(2026, 10, 20, 16, 32), 'attachment_id': stray.id})
        res = self._get(self.adv_member, self._urls(self.adv_site, self.adv_event, frame)['frame'])
        self.assertEqual(res.status_code, NOT_FOUND, '附件不是這個 frame 的，不能借 frame 的路由串出去')

    # ---------- 簽收 ----------

    def _ack(self, user, event, site, note):
        detail = self._urls(site, event, self.adv_frame)['detail']
        page = self._get(user, detail)
        token = CSRF.search(page.text)
        self.assertTrue(token, '前提不成立：詳情頁沒有簽收表單（%s）' % user.login)
        return self.url_open(detail + '/ack', data={'csrf_token': token.group(1), 'note': note})

    def test_ack_records_who_when_and_does_not_touch_the_event_state(self):
        before = self.adv_event.read(['state', 'end_ts', 'protected_from_ts', 'protected_to_ts'])[0]
        res = self._ack(self.adv_member, self.adv_event, self.adv_site, '已通知水電行到場')
        self.assertEqual(res.status_code, 200)
        self.adv_event.invalidate_recordset()
        self.assertEqual(self.adv_event.ack_user_id, self.adv_member)
        self.assertTrue(self.adv_event.ack_at)
        self.assertEqual(self.adv_event.ack_note, '已通知水電行到場')
        after = self.adv_event.read(['state', 'end_ts', 'protected_from_ts', 'protected_to_ts'])[0]
        self.assertEqual(before, after, '簽收不結束事件、不動保全區段')
        bodies = ' '.join(self.adv_event.message_ids.mapped('body'))
        self.assertIn('已通知水電行到場', bodies, '簽收要進事件的 chatter 留稽核')

    def test_second_ack_does_not_overwrite_the_first(self):
        self._ack(self.adv_member, self.adv_event, self.adv_site, '第一位')
        page = self._get(self.adv_member2, self._urls(self.adv_site, self.adv_event, self.adv_frame)['detail'])
        self.assertIn(self.adv_member.name, page.text, '已簽收的事件要顯示誰簽的')
        self.assertIsNone(CSRF.search(page.text), '已簽收就不再給簽收表單')
        # 繞過畫面直接 POST（表單是舊頁面留下的）也不能覆寫——用第二位自己 session 的 token
        token = JS_CSRF.search(page.text)
        self.assertTrue(token, '前提不成立：頁面上找不到第二位自己的 csrf token')
        self.url_open(self._urls(self.adv_site, self.adv_event, self.adv_frame)['detail'] + '/ack',
                      data={'csrf_token': token.group(1), 'note': '第二位'})
        self.adv_event.invalidate_recordset()
        self.assertEqual(self.adv_event.ack_user_id, self.adv_member)
        self.assertEqual(self.adv_event.ack_note, '第一位')

    def test_ack_without_csrf_is_refused(self):
        self.authenticate(self.adv_member.login, PASSWORD)
        self.url_open(self._urls(self.adv_site, self.adv_event, self.adv_frame)['detail'] + '/ack',
                      data={'note': '沒有 token'})
        self.adv_event.invalidate_recordset()
        self.assertFalse(self.adv_event.ack_user_id)

    def test_outsider_cannot_ack(self):
        # token 要用外人自己 session 的：拿成員的 token 會先被 CSRF 擋下，就測不到「非成員」這一道
        self.authenticate(self.outsider.login, PASSWORD)
        token = JS_CSRF.search(self.url_open('/my').text)
        self.assertTrue(token, '前提不成立：/my 頁上找不到外人自己的 csrf token')
        self.url_open(self._urls(self.adv_site, self.adv_event, self.adv_frame)['detail'] + '/ack',
                      data={'csrf_token': token.group(1), 'note': '外人'})
        self.adv_event.invalidate_recordset()
        self.assertFalse(self.adv_event.ack_user_id, '非成員不能簽收')

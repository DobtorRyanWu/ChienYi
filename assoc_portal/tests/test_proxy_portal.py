"""會員前台的委託與積分頁（計畫 §4、§7、§8）。"""

from datetime import timedelta

from odoo import fields
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .common import PASSWORD, PortalCase


@tagged('post_install', '-at_install')
class TestPortalProxy(HttpCase, PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.holder = cls.new_member('M7H01')
        cls.meeting = cls.env['assoc.meeting'].create({
            'name': '前台委託測試大會', 'kind': 'assembly',
            'company_id': cls.company.id, 'date_begin': fields.Datetime.now()})
        # 要開放報到才會有名冊；前台只列名冊已建好的場次（draft 場次選了必然失敗）
        cls.meeting.action_open_checkin()

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)

    def post(self, path, **fields_):
        # csrf 從「我的資料」頁的上傳表單拿：委託頁在「沒有開放中的會議」時不會渲染表單
        page = self.url_open('/my/assoc/profile')
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        return self.url_open(path, data=dict(csrf_token=csrf, **fields_))

    def proxies(self):
        return self.env['assoc.meeting.proxy'].sudo().search(
            [('principal_member_id', '=', self.member.id)])

    def test_portal_proxy_stays_requested(self):
        """前台委託一律停在待收書面：人團法要的是書面委託。"""
        response = self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                             holder_no=self.holder.member_no, holder_name=self.holder.name,
                             purpose='attend')
        self.assertIn('proxy=ok', response.url)
        proxy = self.proxies()
        self.assertEqual(len(proxy), 1)
        self.assertEqual(proxy.state, 'requested')
        self.assertEqual(proxy.channel, 'portal')
        self.assertFalse(proxy.paper_received)

    def test_holder_must_match_number_and_name(self):
        """只比對編號的話，打錯一碼就把票投給別人。"""
        response = self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                             holder_no=self.holder.member_no, holder_name='不是這個名字')
        self.assertIn('proxy=no_holder', response.url)
        self.assertFalse(self.proxies())

    def test_cannot_delegate_after_the_deadline(self):
        self.meeting.sudo().proxy_deadline = fields.Datetime.now() - timedelta(hours=1)
        response = self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                             holder_no=self.holder.member_no, holder_name=self.holder.name)
        self.assertIn('proxy=closed', response.url)

    def test_cannot_delegate_twice_for_the_same_meeting(self):
        self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                  holder_no=self.holder.member_no, holder_name=self.holder.name)
        other = self.new_member('M7H02')
        self.meeting.sudo().action_build_roster()
        response = self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                             holder_no=other.member_no, holder_name=other.name)
        self.assertIn('proxy=duplicate', response.url)
        self.assertEqual(len(self.proxies()), 1)

    def test_cannot_delegate_to_another_company(self):
        stranger = self.new_member('M7X01', company=self.other_company)
        response = self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                             holder_no=stranger.member_no, holder_name=stranger.name)
        self.assertIn('proxy=no_holder', response.url)

    def test_member_can_cancel_own_proxy(self):
        self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                  holder_no=self.holder.member_no, holder_name=self.holder.name)
        proxy = self.proxies()
        response = self.post('/my/assoc/proxies/%s/cancel' % proxy.id)
        self.assertIn('proxy=cancelled', response.url)
        self.assertEqual(proxy.state, 'cancelled')

    def test_cannot_cancel_someone_elses_proxy(self):
        """路由硬帶 principal_member_id：少了它，任何會員都能取消別人的委託。

        csrf_token 一定要是真的——送假的話請求在 CSRF 就被擋，
        測到的是 CSRF 而不是這道守衛（守衛拿掉測試照樣會過）。
        """
        other = self.new_member('M7H03')
        self.meeting.sudo().action_build_roster()
        foreign = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, other, self.holder, channel='portal')
        # 先證明同一組 csrf 對自己的委託是有效的（否則下面的否定斷言可能恆真）
        self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                  holder_no=self.holder.member_no, holder_name=self.holder.name)
        mine = self.proxies()
        self.assertEqual(len(mine), 1)
        self.assertIn('proxy=cancelled',
                      self.post('/my/assoc/proxies/%s/cancel' % mine.id).url)

        response = self.post('/my/assoc/proxies/%s/cancel' % foreign.id)
        self.assertNotEqual(foreign.state, 'cancelled', '不能取消別人的委託')
        self.assertNotIn('proxy=cancelled', response.url)

    def _seminar(self, name):
        return self.env['assoc.meeting'].sudo().create({
            'name': name, 'kind': 'seminar', 'company_id': self.company.id,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(hours=2), 'credit_points': 4})

    def test_credits_page_lists_only_own_records(self):
        seminar = self._seminar('積分頁研討會')
        # **要開放報到**：這一支原本只叫 `action_build_roster()`、把場次留在 draft，
        # 等於斷言「籌備中的場次也要列出來」——而那正是外洩（課程名稱與日期都還
        # 沒對外公告）。改成開放報到之後它驗的才是正常情況，外洩那一面由下一支守。
        seminar.action_open_checkin()
        page = self.url_open('/my/assoc/credits')
        self.assertEqual(page.status_code, 200)
        self.assertIn('積分頁研討會', page.text)

    def test_credits_page_hides_meetings_still_in_preparation(self):
        """籌備中的場次補建名冊後不可以出現在積分頁。

        `action_build_roster()` 在 draft 就跑得動（按鈕只對 closed 隱藏），
        而樣板直接印 `meeting_id.name` 與 `date_begin`。
        """
        seminar = self._seminar('還沒公告的研討會')
        seminar.action_build_roster()
        self.assertEqual(seminar.state, 'draft')
        self.assertTrue(
            self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', seminar.id), ('member_id', '=', self.member.id)]),
            '名冊要真的建起來，否則這條測試是空的（M-C）')
        self.assertNotIn('還沒公告的研討會', self.url_open('/my/assoc/credits').text)

    def test_certificate_pdf_hides_meetings_still_in_preparation(self):
        """**列表關了不等於 PDF 關了。**

        證明 PDF 原本只驗 `member_id` 與 `credit_status`，少了 `kind` 與
        `meeting_id.state` 兩道——紅隊實跑把一份含未公告研討會名稱、日期與
        認可文號的 PDF 抓出來。`action_credit_override` 是正當的補件入口，
        而它不看大會狀態，所以 eligible 是到得了的狀態。
        """
        seminar = self._seminar('PDF 不可外洩的研討會')
        seminar.action_build_roster()
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', seminar.id), ('member_id', '=', self.member.id)])
        attendance.with_user(self.admin_user).action_credit_override(
            'eligible', 4, '補件認可')
        self.assertEqual(attendance.credit_status, 'eligible')
        self.assertEqual(seminar.state, 'draft')
        self.env.cr.flush()
        self.assertEqual(
            self.url_open('/my/assoc/credits/%s/certificate' % attendance.id).status_code,
            404)

    def test_certificate_pdf_is_only_for_seminars(self):
        """大會不給繼續教育積分——對它簽發「積分證明」是實質無效的官方文件。"""
        assembly = self.env['assoc.meeting'].sudo().create({
            'name': '不該有積分證明的大會', 'kind': 'assembly',
            'company_id': self.company.id, 'date_begin': fields.Datetime.now()})
        assembly.action_open_checkin()
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', assembly.id), ('member_id', '=', self.member.id)])
        attendance.with_user(self.admin_user).action_credit_override(
            'eligible', 0, '測試')
        self.env.cr.flush()
        self.assertEqual(
            self.url_open('/my/assoc/credits/%s/certificate' % attendance.id).status_code,
            404)

    def test_certificate_pdf_still_works_for_a_real_seminar(self):
        """反向控制：證明上面兩條擋的是「未公告」與「不是研討會」，不是 PDF 壞了。"""
        seminar = self._seminar('正常的研討會')
        seminar.action_open_checkin()
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', seminar.id), ('member_id', '=', self.member.id)])
        attendance.with_user(self.admin_user).action_credit_override(
            'eligible', 4, '補件認可')
        self.env.cr.flush()
        response = self.url_open('/my/assoc/credits/%s/certificate' % attendance.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')

    def test_gifts_page_hides_campaigns_on_unannounced_meetings(self):
        """禮品頁是同一個洞的第三條路：活動名稱實務上就是場次名稱。"""
        meeting = self.env['assoc.meeting'].sudo().create({
            'name': '還沒公告的大會', 'kind': 'assembly',
            'company_id': self.company.id, 'date_begin': fields.Datetime.now()})
        meeting.action_build_roster()
        campaign = self.env['assoc.gift.campaign'].sudo().create({
            'name': '還沒公告的大會紀念品', 'company_id': self.company.id,
            'meeting_id': meeting.id, 'eligibility': 'active_members'})
        self.env['assoc.gift.item'].sudo().create({
            'campaign_id': campaign.id, 'name': '保溫瓶', 'delivery': 'pickup',
            'unit_value': 100})
        campaign.action_ready()
        self.assertTrue(
            self.env['assoc.gift.entitlement'].sudo().search([
                ('campaign_id', '=', campaign.id), ('member_id', '=', self.member.id)]),
            '權利列要真的建起來，否則這條測試是空的（M-C）')
        self.env.cr.flush()
        body = self.url_open('/my/assoc/gifts').text
        self.assertNotIn('還沒公告的大會紀念品', body)
        self.assertNotIn('保溫瓶', body)

    def test_gifts_page_shows_campaigns_on_announced_meetings(self):
        """反向控制：公告之後要看得到。"""
        meeting = self.env['assoc.meeting'].sudo().create({
            'name': '已公告的大會', 'kind': 'assembly',
            'company_id': self.company.id, 'date_begin': fields.Datetime.now()})
        meeting.action_open_checkin()
        campaign = self.env['assoc.gift.campaign'].sudo().create({
            'name': '已公告的大會紀念品', 'company_id': self.company.id,
            'meeting_id': meeting.id, 'eligibility': 'active_members'})
        self.env['assoc.gift.item'].sudo().create({
            'campaign_id': campaign.id, 'name': '馬克杯', 'delivery': 'pickup',
            'unit_value': 100})
        campaign.action_ready()
        self.env.cr.flush()
        self.assertIn('已公告的大會紀念品', self.url_open('/my/assoc/gifts').text)

    def test_certificate_only_for_eligible_records(self):
        seminar = self.env['assoc.meeting'].sudo().create({
            'name': '證明測試', 'kind': 'seminar', 'company_id': self.company.id,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(hours=2), 'credit_points': 4})
        # **要開放報到**：留在 draft 的話擋住它的是「未公告場次」那一道，
        # 這支就隔離不到 `credit_status` 了（mutation #63 當場存活抓到的就是這個，
        # L2⑥：防線互相遮蔽）。
        seminar.action_open_checkin()
        att = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', seminar.id), ('member_id', '=', self.member.id)])
        self.assertEqual(att.credit_status, 'pending')
        self.assertEqual(
            self.url_open('/my/assoc/credits/%s/certificate' % att.id).status_code, 404)

    def test_cannot_download_another_members_certificate(self):
        """證明上有姓名與課程紀錄，路由一定要硬帶 member_id。"""
        # 讓它變成可下載的狀態（eligible），排除「因為不符資格才 404」這個混淆
        other_att = self._eligible_attendance(self.holder, '別人的研討會')
        self.assertEqual(
            self.url_open('/my/assoc/credits/%s/certificate' % other_att.id).status_code, 404)

    def _eligible_attendance(self, member, name):
        seminar = self.env['assoc.meeting'].sudo().create({
            'name': name, 'kind': 'seminar', 'company_id': self.company.id,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(hours=2), 'credit_points': 4})
        # 同上：不開放報到的話，呼叫端想隔離的那一道會被「未公告場次」先擋掉
        seminar.action_open_checkin()
        att = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', seminar.id), ('member_id', '=', member.id)])
        from odoo.addons.assoc_base.tools import GUARD
        from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import GUARD_CREDIT
        att.with_context(**{GUARD_CREDIT: GUARD}).write(
            {'credit_status': 'eligible', 'credit_points': 4})
        self.env.cr.flush()
        return att

    def test_certificate_refuses_when_pdf_generator_is_unavailable(self):
        """產不出 PDF 時要擋下來。

        核心在 wkhtmltopdf 不可用時會**退回 HTML**，不檢查的話會把一份 HTML
        標成 application/pdf 送出去。
        （真的把 PDF 產出來的驗證在 tools/e2e/e2e_m7_meeting.py：測試庫沒有
        `report.url`，真的呼叫 wkhtmltopdf 會卡住。）
        """
        att = self._eligible_attendance(self.member, '自己的研討會')
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport.'
                   'get_wkhtmltopdf_state', return_value='broken'):
            response = self.url_open('/my/assoc/credits/%s/certificate' % att.id)
        self.assertNotEqual(response.content[:4], b'%PDF')
        self.assertNotIn('application/pdf', response.headers.get('Content-Type', ''),
                         'HTML 退路不能被標成 PDF')

    def test_cancel_during_session_is_refused_with_a_message(self):
        """開議後撤回已生效的委託 → 友善提示，不是 500。

        前台路由擁有的是「把 `_cancel` 丟的 UserError 轉成看得懂的頁面」，
        閘門本身在模型裡（另有測試）。
        """
        self.post('/my/assoc/proxies/new', meeting_id=self.meeting.id,
                  holder_no=self.holder.member_no, holder_name=self.holder.name)
        proxy = self.proxies()
        proxy.sudo()._mark_paper_received()
        # 讓它生效：受託人要先親自出席，而且要有足夠的親自出席人數撐起 1/3
        Attendance = self.env['assoc.meeting.attendance'].sudo()
        for member_no in ('M7F01', 'M7F02', 'M7F03'):
            extra = self.new_member(member_no)
            self.meeting.sudo().action_build_roster()
            Attendance._checkin_by_code(self.meeting.sudo(), extra.sudo().barcode)
        Attendance._checkin_by_code(self.meeting.sudo(), self.holder.sudo().barcode)
        self.assertEqual(proxy.sudo()._try_activate(), 'active')
        self.meeting.sudo().action_start_session()
        self.env.cr.flush()

        response = self.post('/my/assoc/proxies/%s/cancel' % proxy.id)
        self.assertIn('proxy=too_late', response.url)
        self.assertEqual(proxy.sudo().state, 'active', '開議後不能撤回')

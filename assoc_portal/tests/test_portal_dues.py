"""前台繳費頁與繳款提醒（計畫 §4、§5）。"""

from datetime import date

from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_payment import GUARD_PAYMENT

from .common import PASSWORD, PortalCase


@tagged('post_install', '-at_install')
class TestPortalDues(HttpCase, PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finance_user = cls.env['res.users'].create({
            'name': '出納（前台）', 'login': 'm8_portal_finance',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_portal.group_assoc_finance').id])],
        })
        cls.period = cls.env['assoc.dues.period'].sudo().create({
            'name': '2026 常年會費', 'company_id': cls.company.id, 'fee_type': 'annual',
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31), 'amount': 3000})
        cls.period.sudo().action_generate_dues()

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)

    def dues(self, member=None):
        return self.env['assoc.dues'].sudo().search([
            ('period_id', '=', self.period.id), ('member_id', '=', (member or self.member).id)])

    def pay(self, member=None):
        member = member or self.member
        payment = self.env['assoc.payment'].with_user(self.finance_user).create({
            'company_id': self.company.id, 'member_id': member.id, 'payer_name': member.name})
        payment.action_bind_dues(self.dues(member).ids)
        payment.action_post()
        return payment

    def test_dues_page_lists_own_records(self):
        page = self.url_open('/my/assoc/dues')
        self.assertEqual(page.status_code, 200)
        self.assertIn('2026 常年會費', page.text)
        self.assertIn('會費待繳', page.text)

    def test_receipt_downloads_the_stored_file(self):
        """收據下載走存檔、當附件、不快取。

        測試環境不驗 `%PDF`：Odoo 在 `test_enable` 下會刻意退回 HTML
        （`ir_actions_report.py:1011`，避免測試呼叫 wkhtmltopdf 卡住）。
        真的產出 PDF 的驗證在 tools/e2e/e2e_m8_dues.py。
        """
        payment = self.pay()
        self.env.cr.flush()
        response = self.url_open('/my/assoc/receipts/%s' % payment.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content, '要有內容')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_cannot_download_another_members_receipt(self):
        other = self.new_member('M8P02')
        self.period.sudo().action_generate_dues()
        foreign = self.pay(other)
        self.env.cr.flush()
        self.assertEqual(
            self.url_open('/my/assoc/receipts/%s' % foreign.id).status_code, 404)

    def test_voided_receipt_is_hidden_from_the_portal(self):
        """作廢的收據前台看不到（它還留著是為了稽核）。"""
        payment = self.pay()
        payment.with_user(self.finance_user).action_void('支票退票')
        self.env.cr.flush()
        self.assertEqual(self.url_open('/my/assoc/receipts/%s' % payment.id).status_code, 404)

    def test_pass_page_shows_membership_only_when_fee_is_current(self):
        page = self.url_open('/my/assoc/pass')
        self.assertIn('會費待繳', page.text)
        self.member.sudo().fee_paid_opening = date(2099, 12, 31)
        self.env.cr.flush()
        self.assertIn('會籍有效', self.url_open('/my/assoc/pass').text)

    def test_receipt_report_cannot_be_rendered_over_http(self):
        """收據只有一份：過帳當下存下來的那一份。

        `/report/pdf/...` 會用**現值**重新渲染，於是同一個收據號碼可以印出
        兩份內容不同的文件。核心的 `report_routes` 不檢查報表的 `groups_id`
        （web/controllers/report.py），所以擋不能靠那個。
        """
        payment = self.pay()
        self.authenticate(self.finance_user.login, PASSWORD)
        for url in ('/report/pdf/assoc_portal.report_receipt/%s' % payment.id,
                    '/report/html/assoc_portal.report_receipt/%s' % payment.id,
                    '/report/pdf/assoc_portal.action_report_receipt/%s' % payment.id):
            response = self.url_open(url)
            self.assertNotEqual(response.status_code, 200, url)
            self.assertNotIn(b'%PDF', response.content[:8], url)

    def test_receipt_route_refuses_a_foreign_attachment(self):
        """前台收據是 sudo 串流附件內容，所以要回頭確認附件屬於這張收款。"""
        payment = self.pay()
        stranger = self.env['ir.attachment'].sudo().create({
            'name': '別人的文件.pdf', 'type': 'binary', 'datas': b'JVBERi0x',
            'res_model': 'assoc.member', 'res_id': self.member.id})
        payment.sudo().with_context(**{GUARD_PAYMENT: GUARD}).write(
            {'receipt_attachment_id': stranger.id})
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/assoc/receipts/%s' % payment.id)
        self.assertEqual(response.status_code, 404)
    def test_prepaid_future_period_is_not_shown_as_valid(self):
        """只預繳明年那期的人，前台要顯示「會費待繳」。

        模型層有測（`test_prepaying_a_future_period_is_not_yet_eligible`），
        但前台頁自己算一次 `fee_valid`——那裡改成只看 `fee_paid_until`
        不會有任何測試紅，而 `fee_paid_until` 已經是明年的日期了。

        本年度那筆未繳的應繳要先刪掉：留著的話連續計算會在它那裡就斷掉，
        `fee_paid_until` 根本不會是明年，測不到要測的東西。
        """
        self.dues().sudo().unlink()
        future = date.today().year + 1
        period = self.env['assoc.dues.period'].sudo().create({
            'name': '%s 常年會費' % future, 'company_id': self.company.id,
            'fee_type': 'annual', 'date_from': date(future, 1, 1),
            'date_to': date(future, 12, 31), 'amount': 3000})
        period.action_generate_dues()
        payment = self.env['assoc.payment'].with_user(self.finance_user).create({
            'company_id': self.company.id, 'member_id': self.member.id,
            'payer_name': self.member.name})
        payment.action_bind_dues(self.env['assoc.dues'].sudo().search([
            ('period_id', '=', period.id), ('member_id', '=', self.member.id)]).ids)
        payment.action_post()
        self.assertEqual(self.member.fee_paid_until, date(future, 12, 31))
        self.assertEqual(self.member.coverage_from, date(future, 1, 1))
        self.env.cr.flush()
        # 繳費頁
        page = self.url_open('/my/assoc/dues').text
        self.assertIn('會費待繳', page, '涵蓋還沒開始，不能顯示會籍有效')
        self.assertNotIn('會籍有效', page)
        # **電子會員證是另一個判斷點**（報到台看的就是這張卡上的徽章），
        # 它自己算一次 `fee_valid`，所以要分別驗
        card = self.url_open('/my/assoc/pass').text
        self.assertIn('會費待繳', card, '會員證上也不能顯示會籍有效')
        self.assertNotIn('會籍有效', card)

@tagged('post_install', '-at_install')
class TestDuesReminder(PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finance_user = cls.env['res.users'].create({
            'name': '出納（提醒）', 'login': 'm8_reminder',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_portal.group_assoc_finance').id])],
        })
        cls.period = cls.env['assoc.dues.period'].sudo().create({
            'name': '2026 常年會費', 'company_id': cls.company.id, 'fee_type': 'annual',
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31), 'amount': 3000})
        cls.period.sudo().action_generate_dues()

    def dues(self, member=None):
        return self.env['assoc.dues'].sudo().search([
            ('period_id', '=', self.period.id), ('member_id', '=', (member or self.member).id)])

    def test_reminder_queues_the_mail_without_sending(self):
        """信留在佇列：`assoc.mail.hold` 讓排程不會真的寄出去。"""
        Mail = self.env['mail.mail'].sudo()
        before = Mail.search_count([('state', '=', 'outgoing')])
        result = self.dues().with_user(self.finance_user).action_send_reminder()
        self.assertEqual((result['sent'], result['skipped']), (1, 0))
        self.assertEqual(Mail.search_count([('state', '=', 'outgoing')]), before + 1)
        self.assertEqual(Mail.search_count([('state', '=', 'exception')]), 0)
        self.assertEqual(self.dues().reminder_count, 1)
        self.assertTrue(self.dues().last_reminder_at)

    def test_reminder_counts_up(self):
        dues = self.dues().with_user(self.finance_user)
        dues.action_send_reminder()
        dues.action_send_reminder()
        self.assertEqual(self.dues().reminder_count, 2, '次數要累加，不是重設')

    def test_member_without_email_is_reported_not_silently_skipped(self):
        other = self.new_member('M8R02')       # 沒有 Email
        self.period.sudo().action_generate_dues()
        result = self.dues(other).with_user(self.finance_user).action_send_reminder()
        self.assertEqual((result['sent'], result['skipped']), (0, 1))
        self.assertEqual(result['skipped_names'], [other.name],
                         '回傳值要說得出「誰」沒收到，不只是幾個')
        self.assertEqual(self.dues(other).reminder_count, 0)
        messages = other.message_ids.mapped('body')
        self.assertTrue(any('沒有 Email' in body for body in messages),
                        '承辦要看得出來誰沒收到')

    def test_paid_dues_are_not_reminded(self):
        payment = self.env['assoc.payment'].with_user(self.finance_user).create({
            'company_id': self.company.id, 'member_id': self.member.id,
            'payer_name': self.member.name})
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        result = self.dues().with_user(self.finance_user).action_send_reminder()
        self.assertEqual((result['sent'], result['skipped']), (0, 0))

    def test_period_reminder_covers_every_unpaid_member(self):
        """期別上的整批入口要真的送出去。

        這支測試鎖的是一個複製貼上留下的坑：期別曾經有一份 `action_send_reminder`
        的完整複本，裡面判斷 `dues.state != 'unpaid'`——期別的 state 是
        draft/open/closed，永遠不等於 unpaid，所以每一筆都被 `continue` 跳過，
        承辦按下去只會得到「寄了 0 封」而且不報錯。
        """
        with_mail = self.new_member('M8R03')
        with_mail.sudo().email = 'm8r03@example.com'
        self.new_member('M8R04')               # 沒有 Email，算 skipped
        self.period.sudo().action_generate_dues()
        unpaid = self.env['assoc.dues'].sudo().search_count([
            ('period_id', '=', self.period.id), ('state', '=', 'unpaid')])
        Mail = self.env['mail.mail'].sudo()
        before = Mail.search_count([('state', '=', 'outgoing')])
        result = self.period.with_user(self.finance_user).action_send_reminder()
        self.assertEqual(result['sent'] + result['skipped'], unpaid,
                         '每一筆未繳都要被處理到')
        self.assertGreaterEqual(result['sent'], 2)
        self.assertGreaterEqual(result['skipped'], 1, '沒有 Email 的要列出來')
        self.assertEqual(Mail.search_count([('state', '=', 'outgoing')]),
                         before + result['sent'])
        self.assertEqual(Mail.search_count([('state', '=', 'exception')]), 0)

    def test_reminder_button_returns_a_notification_not_raw_data(self):
        """按鈕的回傳值必須是 action，不能是資料 dict。

        Odoo 的 `call_button` 只要收到 object 就當成 action 用，而資料 dict
        沒有 `type` → 前端丟「can't handle actions of type undefined」的
        錯誤對話框。**交易其實已經提交**：承辦看到失敗會再按一次，
        四百人的公會就是 800 封排隊信與虛增的提醒次數。
        """
        no_mail = self.new_member('M8R05')          # 沒有 Email
        self.period.sudo().action_generate_dues()
        action = self.period.with_user(self.finance_user).button_send_reminder()
        self.assertEqual(action.get('type'), 'ir.actions.client')
        self.assertEqual(action.get('tag'), 'display_notification')
        params = action['params']
        self.assertIn(no_mail.name, params['message'], '沒有 Email 的人要顯示在畫面上')
        self.assertEqual(params['type'], 'warning')
        self.assertTrue(params['sticky'], '有人沒收到就不能自動消失')

    def test_dues_form_button_also_returns_a_notification(self):
        action = self.dues().with_user(self.finance_user).button_send_reminder()
        self.assertEqual(action.get('tag'), 'display_notification')

    def test_reminder_queues_even_when_the_hold_is_off(self):
        """進佇列這件事不能是「靠郵件 hold 才成立」的。

        `force_send=True` 在 hold 開著時行為完全一樣（`mail.send()` 直接 return），
        所以平常測不出差別；hold 一解除就有差——會在交易內同步寄出。
        這裡把 hold 關掉、mock 真正的寄送層，證明是 `force_send=False` 在起作用。
        """
        from unittest.mock import patch
        self.env['ir.config_parameter'].sudo().set_param('assoc.mail.hold', '0')
        Mail = self.env['mail.mail'].sudo()
        before = Mail.search_count([('state', '=', 'outgoing')])
        with patch('odoo.addons.base.models.ir_mail_server.IrMailServer.send_email') as sender:
            self.dues().with_user(self.finance_user).action_send_reminder()
        self.assertFalse(sender.called, 'force_send=False 才不會在交易內直接寄出')
        self.assertEqual(Mail.search_count([('state', '=', 'outgoing')]), before + 1)

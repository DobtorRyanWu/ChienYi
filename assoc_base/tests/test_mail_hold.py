"""郵件暫停寄送：兩層都要攔，而且參數不存在時預設 hold。"""

from unittest.mock import patch

from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.tests import TransactionCase, tagged

SEND_EMAIL = 'odoo.addons.base.models.ir_mail_server.IrMailServer.send_email'


@tagged('post_install', '-at_install')
class TestMailHold(TransactionCase):

    def _new_mail(self):
        return self.env['mail.mail'].sudo().create({
            'subject': '測試',
            'email_from': 'noreply@example.com',
            'email_to': 'someone@example.com',
            'body_html': '<p>測試</p>',
        })

    def _set_hold(self, value):
        param = self.env['ir.config_parameter'].sudo()
        if value is None:
            param.search([('key', '=', 'assoc.mail.hold')]).unlink()
        else:
            param.set_param('assoc.mail.hold', value)

    def test_hold_keeps_mail_outgoing(self):
        self._set_hold('1')
        mail = self._new_mail()
        with patch(SEND_EMAIL) as mocked:
            mail.send()
        mocked.assert_not_called()
        self.assertEqual(mail.state, 'outgoing')

    def test_missing_param_means_hold(self):
        """乾淨的新資料庫沒有這個參數，也不能寄出去。"""
        self._set_hold(None)
        mail = self._new_mail()
        with patch(SEND_EMAIL) as mocked:
            mail.send()
        mocked.assert_not_called()
        self.assertEqual(mail.state, 'outgoing')

    def test_queue_processing_also_held(self):
        self._set_hold('1')
        mail = self._new_mail()
        with patch(SEND_EMAIL) as mocked:
            self.env['mail.mail'].sudo().process_email_queue(ids=mail.ids)
        mocked.assert_not_called()
        self.assertEqual(mail.state, 'outgoing')
        self.assertFalse(mail.failure_reason)

    def test_direct_send_email_bypass_is_blocked(self):
        """event 等模組會直接呼叫 send_email，不經 mail.mail。"""
        self._set_hold('1')
        message = self.env['ir.mail_server'].build_email(
            'noreply@example.com', ['someone@example.com'], '測試', '內容')
        with patch('smtplib.SMTP.connect') as connect:
            with self.assertRaises(MailDeliveryException):
                self.env['ir.mail_server'].send_email(message)
        connect.assert_not_called()

    def test_hold_off_sends(self):
        self._set_hold('0')
        mail = self._new_mail()
        with patch(SEND_EMAIL) as mocked:
            mail.send()
        mocked.assert_called()

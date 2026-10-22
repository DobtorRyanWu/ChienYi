"""M6 測試共用：假金鑰、公會管理員、建立會員與開通流程。"""

import base64
import os
import re

from odoo.tests import TransactionCase
from odoo.tools import config

TEST_KEY = base64.b64encode(os.urandom(32)).decode()
VALID_ID = 'A123456789'
VALID_ID_2 = 'B234567894'
PASSWORD = 'Str0ngPassw0rd!'

# /my 首頁的原生入口卡（核心 portal.portal_docs_entry 的輸出形狀）
_INDEX_CARD = re.compile(
    r'<div class="(o_portal_index_card[^"]*)">\s*<a href="([^"]+)"[^>]*>'
    r'(?:\s*<div class="o_portal_icon[^"]*">\s*<img src="([^"]+)")?')


def index_cards(html):
    """回傳 {href: (class 清單, 圖示網址或 None)}；同一個 href 出現兩次就是重複入口，直接報錯。"""
    cards = {}
    for classes, href, icon in _INDEX_CARD.findall(html):
        if href in cards:
            raise AssertionError('入口卡重複：%s' % href)
        cards[href] = (classes.split(), icon or None)
    return cards


def visible_card_urls(html):
    """看得到的入口卡（核心對沒有計數的卡片加 d-none，要等 JS 計數完才顯示）。"""
    return {href for href, (classes, _icon) in index_cards(html).items() if 'd-none' not in classes}


class PortalCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_key = config.options.get('assoc_pii_key')
        config.options['assoc_pii_key'] = TEST_KEY
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].create({'name': '他公會（M6）'})
        cls.admin_user = cls.env['res.users'].create({
            'name': '公會管理員（M6）', 'login': 'm6_admin',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_admin').id])],
        })
        cls.member = cls.new_member('M6001', VALID_ID, 'm6001@example.com')

    @classmethod
    def tearDownClass(cls):
        if cls._old_key is None:
            config.options.pop('assoc_pii_key', None)
        else:
            config.options['assoc_pii_key'] = cls._old_key
        super().tearDownClass()

    @classmethod
    def new_member(cls, member_no, national_id=None, email=None, company=None):
        company = company or cls.env.company
        partner = cls.env['res.partner'].create({
            'name': '會員 %s' % member_no, 'company_id': company.id, 'email': email})
        vals = {'partner_id': partner.id, 'member_no': member_no, 'company_id': company.id}
        if national_id:
            vals['national_id'] = national_id
        return cls.env['assoc.member'].create(vals)

    def grant(self, member=None, user=None):
        member = member or self.member
        member.with_user(user or self.admin_user).action_grant_portal()
        return member.sudo().user_id

    def print_notice(self, member=None, user=None):
        member = member or self.member
        action = member.with_user(user or self.admin_user).action_print_activation()
        return action['data']['token']

    def activate(self, member=None, password=PASSWORD):
        member = member or self.member
        token = self.print_notice(member)
        found, _user, _nonce = self.env['assoc.member'].sudo()._member_from_token(token)
        self.assertTrue(found, '剛印出來的 token 應該有效')
        member._consume_activation(password)
        return token


class RecordingCrypt:
    """包住 `_crypt_context()`，把每次 `verify_and_update` 收到的雜湊記下來。

    等時的判準是「每次嘗試恰好跑一次 verify、而且用的是同輪數的雜湊」，
    三支測試都要數同一件事，所以包裝只寫一次。
    """

    def __init__(self, inner, calls):
        self._inner = inner
        self._calls = calls

    def verify_and_update(self, secret, hashed):
        self._calls.append(hashed or '')
        return self._inner.verify_and_update(secret, hashed)

    def __getattr__(self, name):
        return getattr(self._inner, name)

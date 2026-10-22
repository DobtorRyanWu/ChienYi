import base64
import io
from datetime import date, timedelta

from freezegun import freeze_time

from PIL import Image
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.assoc_base.tools import ASSOC_TZ
from .common import guild_today


@tagged('post_install', '-at_install')
class TestAssocMember(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': '測試公會乙'})
        cls.today = guild_today()      # 公會時區，不是 UTC（見 common.guild_today）
        cls.Member = cls.env['assoc.member']

    @freeze_time('2026-01-01 17:00:00')          # 台北 1/2 01:00、薩摩亞中途島 1/1 06:00
    def test_membership_does_not_move_with_the_viewer_timezone(self):
        """會籍是**公會當地發生的事實**，不隨看的人的時區改變。

        第十一輪紅隊實跑：核心在**首次登入**會用瀏覽器 cookie 覆寫 `tz`
        （`res_users.py:946-949`，條件含 `not user.login_date`），所以
        `action_grant_portal` 寫的 `ASSOC_TZ` 撐不過第一次登入；而前台路由的
        `sudo()` **不換 uid**，於是判定跟著會員自己設的時區跑。

        **時間必須凍結。** 第一版沒凍結、只是把 context 的 tz 換掉，
        結果那條 mutant 照樣存活：挑的兩個時區在跑測試的那個時刻與台北
        **剛好同一天**，所以那個 rig 根本沒有改變任何結果（L2③／⑰：
        先證明這個 rig 真的有效，再往下）。這裡固定在 UTC 17:00——
        那一刻台北已經是 1/2，而 UTC−11 還是 1/1，兩邊必然不同日。

        也**不要用 `is_voter_eligible` 當量尺**：它是 stored compute，
        context 根本進不去（第一版的第二個錯）。要走真的會讀 context 的那條路：
        非儲存的 `_fee_is_current()` 與 `is_voter_eligible` 的 search 方法。
        """
        member = self._member('TZ01', fee_paid_opening=date(2026, 1, 1))   # 台北的「昨天」
        for tz_name in ('Pacific/Midway', 'Pacific/Kiritimati', ASSOC_TZ, False):
            shifted = member.with_context(tz=tz_name)
            self.assertFalse(
                shifted._fee_is_current(),
                'tz=%s：會籍到 1/1，而公會的今天是 1/2，不該還有效' % tz_name)
            found = self.Member.with_context(tz=tz_name).search(
                [('id', '=', member.id), ('is_voter_eligible', '=', True)])
            self.assertFalse(found, 'tz=%s：選舉人名冊的篩選也不該被推移' % tz_name)

    def _member(self, no, company=None, **vals):
        company = company or self.company_a
        # 聯絡人必須屬於同一個公會（_check_partner_company）
        partner = self.env['res.partner'].create({'name': f'會員{no}', 'company_id': company.id})
        return self.Member.create({
            'partner_id': partner.id,
            'member_no': no,
            'company_id': company.id,
            **vals,
        })

    def test_member_no_unique_per_company(self):
        self._member('A001')
        # 不同公會可以用同一個編號
        self._member('A001', company=self.company_b)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self._member('A001')

    def test_barcode_generated_unique_and_rotatable(self):
        m1 = self._member('B001')
        m2 = self._member('B002')
        self.assertTrue(m1.barcode.isdigit())
        self.assertNotEqual(m1.barcode, m2.barcode)
        old = m1.barcode
        m1.action_rotate_barcode()
        self.assertNotEqual(m1.barcode, old)

    @freeze_time('2026-09-24 21:37:00')     # 台北已是 9/25、UTC 還是 9/24 —— 兩邊差一天的那 8 小時
    def test_voter_eligibility(self):
        """**時間要凍結在「台北與 UTC 不同日」的那一刻。**

        會籍判定釘死公會時區（`tools.assoc_today`），而這支測試原本用
        `fields.Date.today()`（UTC）當「今天」。兩者在 UTC 16:00–24:00 差一天，
        於是這支只在那 8 小時紅——2026-09-24 21:37 UTC 實際踩到，
        連帶讓 M8／M9／M10 的 mutation 全部以「基準就是紅的」中止。
        凍在那個瞬間，它就不再看跑測試的時段。
        """
        today = guild_today()
        cases = [
            ({'fee_paid_opening': today + timedelta(days=30)}, True),
            ({'fee_paid_opening': today}, True),
            ({'fee_paid_opening': today - timedelta(days=1)}, False),
            ({}, False),  # 沒有繳費紀錄視為不具選舉權
            ({'fee_paid_opening': today + timedelta(days=30), 'active': False}, False),
        ]
        for i, (vals, expected) in enumerate(cases):
            with self.subTest(vals=vals):
                member = self._member(f'E{i:03d}', **vals)
                self.assertEqual(member.is_voter_eligible, expected)

    def test_company_isolation_rule(self):
        staff = self.env['res.users'].create({
            'name': '甲公會職員',
            'login': 'assoc_staff_a',
            'company_id': self.company_a.id,
            'company_ids': [(6, 0, [self.company_a.id])],
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])],
        })
        own = self._member('C001')
        foreign = self._member('C001', company=self.company_b)
        Member = self.Member.with_user(staff)
        self.assertEqual(Member.search([('member_no', '=', 'C001')]), own)
        with self.assertRaises(AccessError):
            foreign.with_user(staff).read(['name'])

    def test_staff_is_read_only_and_cannot_read_barcode(self):
        """職員不能改會員資料（否則投票中可對調姓名／編號），也讀不到會員卡條碼（否則可複製會員卡代人報到）。"""
        staff = self.env['res.users'].create({
            'name': '唯讀職員', 'login': 'assoc_staff_ro',
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])],
        })
        member = self._member('R001')
        self.assertEqual(member.with_user(staff).read(['member_no'])[0]['member_no'], 'R001')
        with self.assertRaises(AccessError):
            member.with_user(staff).write({'member_no': 'R999'})
        with self.assertRaises(AccessError):
            member.with_user(staff).read(['barcode'])

    def test_card_qr_is_square_png(self):
        """QR 必須是正方形：barcode() 預設 600×100 會拉扁到手機掃不到。"""
        member = self._member('Q001')
        uri = member._card_qr_data_uri()
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        image = Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1])))
        self.assertEqual(image.size[0], image.size[1])

"""會費繳至的連續計算（計畫 §2.3）。

這是 M8 最關鍵的正確性主張：`fee_paid_until` 決定誰在選舉人名冊上。
三個容易寫錯的地方各有對應的測試：
- 跳繳一期不能把後面那期算進來（fail-closed）
- 預繳未來期的人今天還不算有效（資格在查詢時判斷，不在 stored compute 裡）
- 作廢收款之後繳至日要**退回去**（所以 state 一律走 ORM，不能用 raw SQL）
"""

from datetime import date, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import PortalCase


@tagged('post_install', '-at_install')
class TestFeeContinuity(PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finance_user = cls.env['res.users'].create({
            'name': '出納（M8）', 'login': 'm8_finance',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_portal.group_assoc_finance').id])],
        })
        cls.today = fields.Date.today()

    def new_period(self, name, year, fee_type='annual'):
        return self.env['assoc.dues.period'].with_user(self.finance_user).create({
            'name': name, 'company_id': self.company.id, 'fee_type': fee_type,
            'date_from': date(year, 1, 1), 'date_to': date(year, 12, 31), 'amount': 3000})

    def dues_of(self, period, member=None):
        return self.env['assoc.dues'].sudo().search([
            ('period_id', '=', period.id), ('member_id', '=', (member or self.member).id)])

    def settle(self, period, member=None, waive=False):
        """把某一期結清（免繳或走完整的收款→過帳）。"""
        dues = self.dues_of(period, member)
        if waive:
            dues.with_user(self.finance_user).action_waive('年中入會')
            return None
        payment = self.env['assoc.payment'].with_user(self.finance_user).create({
            'company_id': self.company.id, 'member_id': (member or self.member).id,
            'payer_name': (member or self.member).name})
        payment.action_bind_dues(dues.ids)
        payment.action_post()
        return payment

    # ------------------------------------------------------------------
    def test_opening_alone_sets_the_coverage(self):
        """還沒有任何期別時，繳至＝期初值，而且沒有起算日限制。"""
        self.member.sudo().fee_paid_opening = self.today + timedelta(days=30)
        self.assertEqual(self.member.fee_paid_until, self.today + timedelta(days=30))
        self.assertFalse(self.member.coverage_from)
        self.assertTrue(self.member.is_voter_eligible)

    def test_unpaid_period_does_not_extend(self):
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        self.assertEqual(self.dues_of(period).state, 'unpaid')
        self.assertFalse(self.member.fee_paid_until, '未繳不能延伸')

    def test_paid_period_extends(self):
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))
        self.assertEqual(self.member.coverage_from, date(2026, 1, 1))

    def test_waived_period_also_extends(self):
        """年中入會那一期通常是免繳：它要算進連續，否則後面全部接不上。"""
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        self.settle(period, waive=True)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))

    def test_consecutive_periods_chain(self):
        for year in (2026, 2027, 2028):
            period = self.new_period('%s 常年會費' % year, year)
            period.action_generate_dues()
            self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(2028, 12, 31))
        self.assertEqual(self.member.coverage_from, date(2026, 1, 1))

    def test_a_skipped_year_stops_the_chain(self):
        """跳繳：2026 繳了、2027 沒繳、2028 繳了 → 只算到 2026 年底。"""
        first = self.new_period('2026 常年會費', 2026)
        first.action_generate_dues()
        self.settle(first)
        middle = self.new_period('2027 常年會費', 2027)
        middle.action_generate_dues()
        last = self.new_period('2028 常年會費', 2028)
        last.action_generate_dues()
        self.settle(last)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31),
                         '中間斷一期，後面那期不能算進來')

    def test_a_missing_dues_row_stops_the_chain(self):
        """漏產應繳列也要 fail-closed：不能因為「沒有這一期的紀錄」就當成繳過。"""
        first = self.new_period('2026 常年會費', 2026)
        first.action_generate_dues()
        self.settle(first)
        gap = self.new_period('2027 常年會費', 2027)   # 不產應繳列
        last = self.new_period('2028 常年會費', 2028)
        last.action_generate_dues()
        self.settle(last)
        self.assertFalse(gap.dues_ids)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))

    def test_non_annual_periods_do_not_extend(self):
        """研討會報名費、入會費不是常年會費，不能延伸會籍。"""
        period = self.new_period('2026 研討會報名費', 2026, fee_type='seminar')
        period.action_generate_dues()
        self.settle(period)
        self.assertFalse(self.member.fee_paid_until)

    def test_prepaying_a_future_period_is_not_yet_eligible(self):
        """只預繳明年那期的人，今天還不算有效。

        這是「資格在查詢時判斷」的理由：把它寫進 stored compute 的話，
        跨過 1/1 不會自己重算（沒有任何欄位變動），答案會停在去年。
        """
        future = self.today.year + 1
        period = self.new_period('%s 常年會費' % future, future)
        period.action_generate_dues()
        self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(future, 12, 31))
        self.assertEqual(self.member.coverage_from, date(future, 1, 1))
        self.assertFalse(self.member.is_voter_eligible, '涵蓋還沒開始')
        self.assertFalse(self.member._fee_is_current())
        # search 的補集也要抓得到他：`fee_paid_until` 是未來日期，
        # 只有 `coverage_from > today` 那一支條件會命中
        Member = self.env['assoc.member'].sudo()
        self.assertIn(self.member, Member.search([('is_voter_eligible', '=', False)]))
        self.assertNotIn(self.member, Member.search([('is_voter_eligible', '=', True)]))
        # 到了起算日當天就有效——不需要任何重算
        self.assertTrue(self.member._fee_is_current(date(future, 1, 1)))

    def test_eligible_search_matches_the_compute(self):
        current = self.new_period('%s 常年會費' % self.today.year, self.today.year)
        current.action_generate_dues()
        self.settle(current)
        Member = self.env['assoc.member'].sudo()
        eligible = Member.search([('is_voter_eligible', '=', True)])
        self.assertIn(self.member, eligible)
        self.assertNotIn(self.member, Member.search([('is_voter_eligible', '=', False)]))

    def test_voiding_a_payment_rolls_the_coverage_back(self):
        """作廢之後繳至日要退回去——退票的人不能還留在選舉人名冊上。

        這就是「state 一律走 ORM」的理由：raw SQL 改 state 不會觸發 stored compute。
        """
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        payment = self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))
        payment.with_user(self.finance_user).action_void('支票退票')
        self.assertFalse(self.member.fee_paid_until, '作廢後繳至日要退回去')
        self.assertEqual(self.dues_of(period).state, 'unpaid')
        self.assertFalse(self.dues_of(period).payment_id, '解綁後才能重開新收款')

    def test_reopening_after_void(self):
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        payment = self.settle(period)
        payment.with_user(self.finance_user).action_void('支票退票')
        again = self.settle(period)
        self.assertEqual(again.state, 'posted')
        self.assertNotEqual(again.receipt_no, payment.receipt_no, '重開要拿新號碼')
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))

    def test_manual_opening_is_not_wiped_on_create(self):
        """可手填的初始值不能併進唯讀 compute（§16 通則 7）。

        create 之後 compute 會重算；如果期初值本身就是 compute 的產物，
        新建會員時手填的日期會被清掉。
        """
        partner = self.env['res.partner'].create(
            {'name': '新會員', 'company_id': self.company.id})
        member = self.env['assoc.member'].create({
            'partner_id': partner.id, 'member_no': 'M8NEW', 'company_id': self.company.id,
            'fee_paid_opening': date(2027, 6, 30)})
        self.assertEqual(member.fee_paid_opening, date(2027, 6, 30))
        self.assertEqual(member.fee_paid_until, date(2027, 6, 30))

    def test_fee_paid_until_cannot_be_written_directly(self):
        """它是算出來的：直接寫要被擋掉。

        **沒有 inverse 的 stored compute 仍然寫得進去**，而且值會留著直到某個
        依賴變動才重算——不擋的話，一行 RPC 就能把自己塞進選舉人名冊。
        """
        from odoo.exceptions import AccessError
        for field in ('fee_paid_until', 'coverage_from'):
            with self.assertRaises(AccessError, msg=field):
                self.member.sudo().write({field: date(2099, 12, 31)})
        self.assertNotEqual(self.member.fee_paid_until, date(2099, 12, 31))

    def test_settling_a_period_never_shortens_the_opening(self):
        """結清一期不能讓繳至日倒退。

        舊系統遷過來的「期初繳至」可能比本年度期別的迄日還晚（已預繳）。
        `coverage = dues.date_to` 若是無條件指派，出納收了本年度的錢之後，
        繳至日會從 2027-06-30 縮回 2026-12-31——繳錢反而讓會籍提早到期，
        而這個欄位決定誰在選舉人名冊上。遷移後每一位已預繳的會員都會中。
        """
        self.member.sudo().fee_paid_opening = date(2027, 6, 30)
        period = self.new_period('2026 常年會費', 2026)
        period.action_generate_dues()
        self.assertEqual(self.member.fee_paid_until, date(2027, 6, 30), '未繳時維持期初值')
        self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(2027, 6, 30),
                         '繳錢不能讓繳至日倒退')

    def test_later_periods_still_extend_past_the_opening(self):
        """但接下去的期別照樣往後延——「不倒退」不等於「凍結」。"""
        self.member.sudo().fee_paid_opening = date(2027, 6, 30)
        for year in (2026, 2027, 2028):
            period = self.new_period('%s 常年會費' % year, year)
            period.action_generate_dues()
            self.settle(period)
        self.assertEqual(self.member.fee_paid_until, date(2028, 12, 31))

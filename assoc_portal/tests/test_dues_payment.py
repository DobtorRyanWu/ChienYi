"""收款、收據號與守衛（計畫 §2.3、P23）。

出納對應繳與收款都有寫入 ACL，所以守衛必須擋得住「帶 context 的 RPC」：
不開收據就把自己標成已繳，等於延長會籍並改變選舉人名冊。
"""

from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_dues import GUARD_DUES
from odoo.addons.assoc_portal.models.assoc_payment import GUARD_PAYMENT

from .common import PortalCase


@tagged('post_install', '-at_install')
class TestDuesPayment(PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finance_user = cls.env['res.users'].create({
            'name': '出納（收款）', 'login': 'm8_cashier',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_portal.group_assoc_finance').id])],
        })
        cls.staff_user = cls.env['res.users'].create({
            'name': '職員（唯讀）', 'login': 'm8_staff',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_staff').id])],
        })
        cls.period = cls.env['assoc.dues.period'].sudo().create({
            'name': '2026 常年會費', 'company_id': cls.company.id, 'fee_type': 'annual',
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31), 'amount': 3000})
        cls.period.sudo().action_generate_dues()

    def dues(self, member=None):
        return self.env['assoc.dues'].sudo().search([
            ('period_id', '=', self.period.id), ('member_id', '=', (member or self.member).id)])

    def draft_payment(self, member=None):
        member = member or self.member
        return self.env['assoc.payment'].with_user(self.finance_user).create({
            'company_id': self.company.id, 'member_id': member.id, 'payer_name': member.name})

    # ---- 守衛 ----
    def test_payment_cannot_point_at_another_guilds_member(self):
        """收款單的 `member_id` 不可以指向別家公會的會員。

        **公會 rule 檢查的是這張收款單的公會，不是 `member_id` 指向的那張會員的公會。**
        少了 `check_company=True`，台北的出納可以在自己公會建一張收款單、把
        `member_id` 指向新北的會員，再 `read(['member_id'])` 拿回 display_name
        「N001 王志明」——逐一換 id 就列舉出別家公會的完整會員名冊
        （第十四輪 red-team 實跑）。`assoc.dues` 當時沒被打穿是巧合：
        它的 `member_no` 是 stored related，create 時必須先讀 member 才觸發 rule。
        """
        outsider = self.new_member('X9001', company=self.other_company)
        with self.assertRaises(Exception) as caught:
            self.env['assoc.payment'].with_user(self.finance_user).create({
                'company_id': self.company.id,
                'member_id': outsider.id,
                'payer_name': '列舉測試',
            })
        # 不論是 _check_company 還是 rule 擋的，都不可以留下那一列
        self.assertFalse(
            self.env['assoc.payment'].sudo().search([('member_id', '=', outsider.id)]),
            '別家公會的會員不可以出現在任何一張收款單上：%s' % caught.exception)

    def test_dues_state_needs_the_sentinel(self):
        """truthy context 是可偽造的：`call_kw` 會把前端送來的 context 直接套進 env。"""
        dues = self.dues().with_user(self.finance_user)
        for context in ({}, {'assoc_dues_post': True}, {'assoc_dues_post': 1}):
            with self.assertRaises(UserError, msg=str(context)):
                dues.with_context(**context).write({'state': 'paid'})
        dues.with_context(**{GUARD_DUES: GUARD}).write({'state': 'paid'})
        self.assertEqual(self.dues().state, 'paid')

    def test_dues_cannot_be_created_paid(self):
        """只看 vals 的守衛擋不住 `default_state`（§16 通則 1）。"""
        other = self.new_member('M8D02')
        with self.assertRaises(UserError):
            self.env['assoc.dues'].with_user(self.finance_user).with_context(
                default_state='paid').create({
                    'period_id': self.period.id, 'member_id': other.id, 'amount_due': 3000})

    def test_payment_system_fields_need_the_sentinel_even_in_draft(self):
        """草稿也要擋：被 RPC 寫成 posted 就占掉一個 no_gap 號碼，而 no_gap 不能跳號。"""
        payment = self.draft_payment()
        for vals in ({'state': 'posted'}, {'receipt_no': 'FAKE-1'}, {'amount_total': 99}):
            with self.assertRaises(UserError, msg=str(vals)):
                payment.write(vals)
            with self.assertRaises(UserError, msg=str(vals)):
                payment.with_context(assoc_payment_post=True).write(vals)

    def test_payment_cannot_be_created_with_any_system_field_preset(self):
        """初值清單要**逐欄**試過。

        只試 `default_state` 的話，清單裡少列一欄也不會有人發現——
        而少列的那一欄就是可以在 create 當下塞進去的那一欄
        （`receipt_no` 佔號、`amount_total` 造假金額、
        `receipt_attachment_id` 讓前台 sudo 串流別人的檔案）。
        """
        Payment = self.env['assoc.payment'].with_user(self.finance_user)
        stranger = self.env['ir.attachment'].sudo().create({
            'name': '別人的文件.pdf', 'type': 'binary', 'datas': b'JVBERi0x',
            'res_model': 'assoc.member', 'res_id': self.member.id})
        for default in ({'default_state': 'posted'}, {'default_receipt_no': 'FAKE-1'},
                        {'default_amount_total': 99999},
                        {'default_receipt_attachment_id': stranger.id},
                        {'default_posted_by_uid': self.env.uid},
                        {'default_void_reason': '假的'}):
            with self.assertRaises(UserError, msg=str(default)):
                Payment.with_context(**default).create({
                    'company_id': self.company.id, 'member_id': self.member.id,
                    'payer_name': self.member.name})

    def test_staff_cannot_post(self):
        """要斷言**訊息**，不能只斷言例外型別。

        職員對 `assoc.dues` 只有唯讀 ACL，所以就算拿掉 `require_finance`，
        寫入時照樣會丟 Odoo 的泛用 `AccessError`——而它繼承 `UserError`，
        `assertRaises` 兩種情況都會過，守衛被 ACL「代打」而測試看不出來。
        """
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        with self.assertRaises(AccessError) as caught:
            payment.with_user(self.staff_user).action_post()
        self.assertIn('只有出納或公會管理員', str(caught.exception))

    # ---- 綁定 ----
    def test_binding_refuses_another_members_dues(self):
        """條件 UPDATE 一定要帶 member 與 company：少了它們可以鎖住別人的應繳。"""
        other = self.new_member('M8D03')
        self.period.sudo().action_generate_dues()
        payment = self.draft_payment()
        with self.assertRaises(UserError):
            payment.action_bind_dues(self.dues(other).ids)
        self.assertFalse(self.dues(other).payment_id)

    def test_binding_refuses_another_companys_dues(self):
        other_period = self.env['assoc.dues.period'].sudo().create({
            'name': '他公會 2026', 'company_id': self.other_company.id, 'fee_type': 'annual',
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31), 'amount': 3000})
        stranger = self.new_member('M8X01', company=self.other_company)
        other_dues = self.env['assoc.dues'].sudo().create({
            'period_id': other_period.id, 'member_id': stranger.id, 'amount_due': 3000})
        payment = self.draft_payment()
        with self.assertRaises(UserError):
            payment.action_bind_dues(other_dues.ids)
        self.assertFalse(other_dues.payment_id)

    def test_two_drafts_cannot_take_the_same_dues(self):
        first, second = self.draft_payment(), self.draft_payment()
        first.action_bind_dues(self.dues().ids)
        with self.assertRaises(UserError):
            second.action_bind_dues(self.dues().ids)

    # ---- 過帳與收據 ----
    def test_posting_sets_receipt_and_freezes_amount(self):
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        self.assertEqual(payment.state, 'posted')
        self.assertTrue(payment.receipt_no)
        self.assertEqual(payment.amount_total, 3000)
        self.assertTrue(payment.receipt_attachment_id, '收據要存檔，重印不重算')
        self.assertEqual(len(payment.receipt_sha256), 64)
        self.assertEqual(self.dues().state, 'paid')

    def test_receipt_numbers_are_consecutive(self):
        other = self.new_member('M8D04')
        self.period.sudo().action_generate_dues()
        numbers = []
        for member in (self.member, other):
            payment = self.draft_payment(member)
            payment.action_bind_dues(self.dues(member).ids)
            payment.action_post()
            numbers.append(payment.receipt_no)
        self.assertEqual(len(set(numbers)), 2)
        serials = [int(no.split('-')[-1]) for no in numbers]
        self.assertEqual(serials[1], serials[0] + 1, 'no_gap 序號要連號')

    def test_receipt_number_uses_taipei_date(self):
        """`ir_sequence` 預設取 UTC 日期：台北 1/1 00:00–08:00 會落到前一年。"""
        from unittest.mock import patch
        import datetime as dt

        class FakeDatetime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                # UTC 是 2025-12-31 17:30，台北已經是 2026-01-01 01:30
                utc = dt.datetime(2025, 12, 31, 17, 30, tzinfo=dt.timezone.utc)
                return utc.astimezone(tz) if tz else utc.replace(tzinfo=None)

        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        with patch('odoo.addons.assoc_portal.models.assoc_payment.datetime', FakeDatetime):
            payment.action_post()
        self.assertTrue(payment.receipt_no.startswith('2026-'),
                        '收據號要用台北當日的年度，拿到的是 %s' % payment.receipt_no)

    def test_posted_payment_cannot_be_edited_or_deleted(self):
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        with self.assertRaises(UserError):
            payment.write({'payer_name': '改抬頭'})
        with self.assertRaises(UserError):
            payment.unlink()

    def test_draft_can_be_deleted_and_releases_the_dues(self):
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.unlink()
        self.assertFalse(self.dues().payment_id)
        self.assertEqual(self.dues().state, 'unpaid')

    # ---- 作廢 ----
    def test_void_keeps_the_receipt_and_needs_a_reason(self):
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        attachment = payment.receipt_attachment_id
        with self.assertRaises(UserError):
            payment.action_void('')
        payment.action_void('支票退票')
        self.assertEqual(payment.state, 'voided')
        self.assertTrue(payment.receipt_no, '收據號碼不能消失')
        self.assertEqual(payment.receipt_attachment_id, attachment, '原收據存檔要留著')

    def test_void_writes_audit(self):
        Audit = self.env['assoc.audit.log'].sudo()
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        before_post = Audit.search_count([('action', '=', 'receipt_post')])
        payment.action_post()
        self.assertEqual(Audit.search_count([('action', '=', 'receipt_post')]), before_post + 1)
        before_void = Audit.search_count([('action', '=', 'receipt_void')])
        payment.action_void('支票退票')
        self.assertEqual(Audit.search_count([('action', '=', 'receipt_void')]), before_void + 1)

    # ---- 免繳 ----
    def test_waive_needs_a_reason_and_finance(self):
        dues = self.dues()
        with self.assertRaises(UserError):
            dues.with_user(self.finance_user).action_waive('')
        # 同 test_staff_cannot_post：要斷言訊息，否則唯讀 ACL 會替守衛代打
        with self.assertRaises(AccessError) as caught:
            dues.with_user(self.staff_user).action_waive('理由')
        self.assertIn('只有出納或公會管理員', str(caught.exception))
        dues.with_user(self.finance_user).action_waive('年中入會')
        self.assertEqual(self.dues().state, 'waived')

    # ---- 逾期篩選 ----
    def test_overdue_search_does_not_return_everything(self):
        """非儲存 compute 沒有 search 時，篩選會靜默回傳全部。"""
        Dues = self.env['assoc.dues'].sudo()
        self.period.sudo().due_date = fields.Date.today() - timedelta(days=1)
        overdue = Dues.search([('is_overdue', '=', True)])
        self.assertIn(self.dues(), overdue)
        self.period.sudo().due_date = fields.Date.today() + timedelta(days=30)
        self.assertNotIn(self.dues(), Dues.search([('is_overdue', '=', True)]))
        self.assertIn(self.dues(), Dues.search([('is_overdue', '=', False)]))

    def test_mirror_fields_cannot_be_written(self):
        """期別的鏡像欄位（related store）不能直接寫。

        related 預設 readonly → 沒有 inverse → 等同「沒有 inverse 的 stored compute」：
        寫得進去而且值會留著。出納對應繳有寫入 ACL，少了這道守衛就能把
        `date_to` 改到 2030 年，把「會費繳至」延長四年而不留任何軌跡；
        改 `company_id` 還能把應繳列推到別的公會。
        """
        dues = self.dues().with_user(self.finance_user)
        for vals in ({'date_to': date(2030, 12, 31)}, {'date_from': date(2020, 1, 1)},
                     {'fee_type': 'other'}, {'company_id': self.other_company.id},
                     {'member_no': 'X999'}):
            with self.assertRaises(AccessError, msg=str(vals)):
                dues.write(vals)
        self.assertEqual(self.dues().date_to, date(2026, 12, 31))

    def test_posting_rechecks_that_the_dues_belong_to_the_member(self):
        """草稿的 `member_id` 還能改，所以過帳當下要再確認一次。

        綁定時檢查過「這些應繳屬於這位會員」，但那之後把收款改指到別人身上，
        就會開出一張抬頭是 B、實際沖銷 A 的應繳的收據（A 的會籍照樣延長）。
        """
        other = self.new_member('M8D05')
        self.period.sudo().action_generate_dues()
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.write({'member_id': other.id, 'payer_name': other.name})
        with self.assertRaises(UserError):
            payment.action_post()
        self.assertEqual(self.dues().state, 'unpaid')
        self.assertFalse(payment.receipt_no, '被擋下來就不該占掉收據號碼')

    def test_closing_a_period_stops_new_dues(self):
        """期別的 `closed` 要真的到得了。

        原本沒有任何程式把期別設成 closed，於是 `action_generate_dues` 的
        「已結清不能再產生」與表單上兩個條件都是永遠走不到的死分支。
        """
        self.assertEqual(self.period.state, 'open')
        with self.assertRaises(AccessError):
            self.period.with_user(self.staff_user).action_close()
        self.period.with_user(self.finance_user).action_close()
        self.assertEqual(self.period.state, 'closed')
        with self.assertRaises(UserError):
            self.period.with_user(self.finance_user).action_generate_dues()
        with self.assertRaises(UserError):
            self.period.with_user(self.finance_user).action_close()

    # ---- 期別（三鏡頭審查 F1／F6）----
    def test_period_definition_locks_once_dues_exist(self):
        """期別產生應繳之後，定義欄位就不能再改。

        `assoc.dues` 的 date_from/date_to 是期別的 related store，改**期別**
        會經由它們一路推到每一位已繳會員的 `fee_paid_until`（選舉人名冊的依據），
        而且收據上印的期間已經發出去了——等於不開收據就把全期所有人的會籍延長。
        擋住 `assoc.dues` 那一側卻不擋來源，是把攻擊者指向另一扇開著的門。
        """
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))
        period = self.period.with_user(self.finance_user)
        for vals in ({'date_to': date(2030, 12, 31)}, {'date_from': date(2020, 1, 1)},
                     {'fee_type': 'other'}, {'amount': 1}):
            with self.assertRaises(AccessError, msg=str(vals)):
                period.write(vals)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))
        # 改名稱與繳款期限是正常作業，不該被鎖
        period.write({'name': '2026 常年會費（更名）', 'due_date': date(2026, 6, 30)})

    def test_overlapping_annual_periods_are_refused(self):
        """同一公會的常年會費期別不得重疊。

        連續計算是一期接一期往後走；兩個起日相同的期別誰先誰後會給出不同答案
        （一期已繳一期未繳時，先掃到哪一期就決定停不停）。
        """
        Period = self.env['assoc.dues.period'].with_user(self.finance_user)
        with self.assertRaises(UserError):
            Period.create({
                'name': '2026 補收差額', 'company_id': self.company.id, 'fee_type': 'annual',
                'date_from': date(2026, 7, 1), 'date_to': date(2027, 6, 30), 'amount': 500})
        # 非常年會費不參與計算，不受限
        Period.create({
            'name': '2026 研討會報名費', 'company_id': self.company.id, 'fee_type': 'seminar',
            'date_from': date(2026, 7, 1), 'date_to': date(2026, 7, 1), 'amount': 500})
        # 他公會同一年也不受影響（出納對別家公會沒有 create 權，所以用 sudo 建）
        self.env['assoc.dues.period'].sudo().create({
            'name': '他公會 2026', 'company_id': self.other_company.id, 'fee_type': 'annual',
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31), 'amount': 3000})

    # ---- 應繳的身分欄位（F2）----
    def test_dues_identity_fields_are_immutable(self):
        """`period_id`／`member_id` 建立後不能改，已處理的也不能改金額。

        兩者都不在鏡像欄位裡：把一筆**已繳**的應繳改掛到自建的 2030 期別，
        或搬給別人，都能在不開收據的情況下改變會籍長度。
        """
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        payment.action_post()
        other = self.new_member('M8D06')
        far = self.env['assoc.dues.period'].sudo().create({
            'name': '2030 常年會費', 'company_id': self.company.id, 'fee_type': 'annual',
            'date_from': date(2030, 1, 1), 'date_to': date(2030, 12, 31), 'amount': 3000})
        dues = self.dues().with_user(self.finance_user)
        with self.assertRaises(AccessError):
            dues.write({'period_id': far.id})
        with self.assertRaises(AccessError):
            dues.write({'member_id': other.id})
        with self.assertRaises(AccessError):
            dues.write({'amount_due': 1})
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))

    # ---- 免繳的軌跡（F5）----
    def test_waive_writes_audit(self):
        """免繳同樣延長會籍而且不開收據——沒有軌跡的話這是最安靜的一條路。"""
        Audit = self.env['assoc.audit.log'].sudo()
        before = Audit.search_count([('action', '=', 'dues_waive')])
        self.dues().with_user(self.finance_user).action_waive('年中入會')
        self.assertEqual(Audit.search_count([('action', '=', 'dues_waive')]), before + 1)
        self.assertEqual(self.member.fee_paid_until, date(2026, 12, 31))

    def test_waive_refuses_dues_already_bound_to_a_draft(self):
        """綁進草稿收款的應繳不能改成免繳。

        不擋的話那張草稿從此過不了帳，而且它丟出來的訊息是
        「有應繳已經被處理過了，請重新整理後再試」——與實情
        （被自己人改成免繳）對不上，承辦會一直重新整理。
        """
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        with self.assertRaises(UserError):
            self.dues().with_user(self.finance_user).action_waive('年中入會')
        self.assertEqual(self.dues().state, 'unpaid')
        payment.action_post()      # 草稿還是過得了帳
        self.assertEqual(self.dues().state, 'paid')

    def test_posting_rejects_dues_that_changed_behind_its_back(self):
        """綁定之後、過帳之前狀態被改掉，過帳要擋下來。

        公開路徑目前做不出這個情境（已綁進草稿的應繳不准改免繳、
        別的收款也綁不到它），但帶哨兵的寫入做得到，而且日後新增的路徑
        隨時可能做得到——所以這道重查不能省。
        """
        payment = self.draft_payment()
        payment.action_bind_dues(self.dues().ids)
        self.dues().with_context(**{GUARD_DUES: GUARD}).write({'state': 'paid'})
        with self.assertRaises(UserError):
            payment.action_post()
        self.assertFalse(payment.receipt_no, '被擋下來就不該占掉收據號碼')

    def test_staff_cannot_send_reminders(self):
        """提醒信那條路的 `require_finance` 是**唯一**的防線。

        `action_send_reminder` 內部用 `dues.sudo().write(...)` 更新提醒次數，
        sudo 繞過了 ACL——少了群組檢查，唯讀職員用 RPC 就能灌提醒信、
        改計數、在每位會員的 chatter 留紀錄。
        """
        with self.assertRaises(AccessError) as caught:
            self.dues().with_user(self.staff_user).action_send_reminder()
        self.assertIn('只有出納或公會管理員', str(caught.exception))
        self.assertEqual(self.dues().reminder_count, 0)

    def test_period_can_be_fixed_after_deleting_unissued_dues(self):
        """打錯日期的補救路徑：把未繳的應繳刪掉，期別就能改回來。

        鎖的判準必須是「**有沒有應繳列**」而不是狀態：用狀態的話，
        按下「產生應繳」的那一刻 state 就是 open，期別從此永遠改不回來——
        連 sudo 都不行，而且沒有任何回到 draft 的路。
        真正要擋的是「已經有人依這個期間繳了錢」，那由應繳列的存在代表。
        """
        period = self.period.with_user(self.finance_user)
        self.assertTrue(period.dues_ids, '這一期已經產生過應繳')
        with self.assertRaises(AccessError):
            period.write({'date_to': date(2026, 6, 30)})
        period.dues_ids.sudo().unlink()          # 全部未繳，刪得掉
        period.write({'date_to': date(2026, 6, 30)})
        self.assertEqual(period.date_to, date(2026, 6, 30))

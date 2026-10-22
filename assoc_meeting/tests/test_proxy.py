"""委託出席（人民團體法 §38，計畫 §7）。"""

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_meeting.models.assoc_meeting_proxy import GUARD_PROXY

from .common import MeetingCase


@tagged('post_install', '-at_install')
class TestProxy(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('P%03d' % no) for no in range(1, 11)}
        cls.meeting = cls.new_meeting('委託測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()

    def present(self, *numbers):
        for no in numbers:
            self.scan(self.meeting, self.members[no].sudo().barcode)

    def register(self, principal, holder, **kw):
        return self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[principal], self.members[holder], **kw)

    # ---- 書面閘門 ----
    def test_portal_proxy_needs_paper_before_it_takes_effect(self):
        self.present(1, 2, 3)
        proxy = self.register(4, 1, channel='portal')
        self.assertEqual(proxy._try_activate(), 'need_paper')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'absent')
        proxy._mark_paper_received()
        self.assertEqual(proxy._try_activate(), 'active')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'proxy')

    def test_desk_paper_proxy_takes_effect_immediately(self):
        self.present(1, 2, 3)
        proxy = self.register(4, 1, channel='desk_paper', paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active')

    def test_channel_cannot_be_changed_by_rpc(self):
        """改成 desk_paper 就等於繞過書面閘門，所以所有欄位都要哨兵才寫得動。"""
        proxy = self.register(4, 1, channel='portal')
        with self.assertRaises(UserError):
            proxy.with_user(self.admin_user).write({'channel': 'desk_paper'})
        with self.assertRaises(UserError):
            proxy.with_user(self.admin_user).with_context(assoc_proxy=True).write(
                {'paper_received': True})

    def test_activation_sql_re_checks_the_paper_gate(self):
        """生效 SQL 自己也要帶書面閘門。

        Python 那道在 `_try_activate`；如果有人（現在或以後）直接呼叫
        `_activate_attend`，少了 SQL 這道就會讓沒收到書面的前台委託生效。
        注意順序：出席列先更新、委託書後更新，所以 0 列時必須 raise 讓整筆回滾。
        """
        self.present(1, 2, 3)
        proxy = self.register(4, 1, channel='portal')      # 停在 requested、沒收到書面
        with self.assertRaises(UserError):
            proxy._activate_attend()
        self.assertEqual(proxy.state, 'requested')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'absent',
                         '委託書沒生效，出席列也不能留下半套狀態')

    # ---- 1/3 上限 ----
    def test_one_third_limit(self):
        """3 人親自出席才容得下 1 件委託；第 2 件要等到第 6 人到場。"""
        self.present(1, 2)
        first = self.register(7, 1, paper_received=True)
        self.assertEqual(first._try_activate(), 'waiting', '2 人出席撐不起 1 件委託')
        self.present(3)
        self.assertEqual(first._try_activate(), 'active')
        second = self.register(8, 2, paper_received=True)
        self.assertEqual(second._try_activate(), 'waiting')
        self.present(4, 5, 6)
        self.assertEqual(second._try_activate(), 'active')

    def test_holder_can_only_represent_one_person(self):
        self.present(1, 2, 3, 4, 5, 6)
        self.assertEqual(self.register(7, 1, paper_received=True)._try_activate(), 'active')
        second = self.register(8, 1, paper_received=True)
        self.assertEqual(second._try_activate(), 'rejected')
        self.assertIn('已代理', second.cancel_reason)

    def test_holder_must_be_present(self):
        self.present(1, 2, 3)
        proxy = self.register(4, 5, paper_received=True)   # 受託人 5 沒到
        with self.assertRaises(UserError):
            proxy._try_activate()

    def test_requested_does_not_hold_the_holder_slot(self):
        """requested 不佔名額：否則有人可以用大量申請把某個受託人卡死。"""
        self.present(1, 2, 3)
        self.register(4, 1, channel='portal')          # 停在 requested
        second = self.register(5, 1, paper_received=True)
        self.assertEqual(second._try_activate(), 'active')

    def test_principal_attending_in_person_supersedes_the_proxy(self):
        self.present(1, 2, 3)
        proxy = self.register(4, 1, paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active')
        self.assertEqual(self.meeting.proxy_count, 1)
        self.scan(self.meeting, self.members[4].sudo().barcode)
        att = self.attendance_of(self.meeting, self.members[4])
        self.assertEqual(att.state, 'present')
        self.assertEqual(proxy.state, 'superseded')
        self.assertEqual(self.meeting.proxy_count, 0)

    def test_cancel_releases_the_attendance(self):
        self.present(1, 2, 3)
        proxy = self.register(4, 1, paper_received=True)
        proxy._try_activate()
        proxy.action_cancel('委託人改為親自出席')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'absent')
        self.assertEqual(proxy.state, 'cancelled')

    # ---- 禮品代領 ----
    def test_gift_proxy_does_not_touch_attendance(self):
        self.present(1)
        proxy = self.register(4, 1, purpose='gift', paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'absent',
                         '禮品代領不是出席')
        self.assertEqual(self.meeting.proxy_count, 0)

    def test_gift_proxy_limit_is_one_too(self):
        self.present(1)
        self.register(4, 1, purpose='gift', paper_received=True)._try_activate()
        second = self.register(5, 1, purpose='gift', paper_received=True)
        self.assertEqual(second._try_activate(), 'rejected')

    def test_gift_and_attend_are_independent(self):
        self.present(1, 2, 3)
        self.assertEqual(self.register(4, 1, paper_received=True)._try_activate(), 'active')
        self.assertEqual(
            self.register(4, 2, purpose='gift', paper_received=True)._try_activate(), 'active')

    # ---- 約束 ----
    def test_cannot_delegate_to_self(self):
        """要驗訊息，不能只驗例外型別：這裡有好幾道約束都丟 ValidationError。"""
        with self.assertRaises(ValidationError) as err:
            self.register(4, 4)
        self.assertIn('不能委託給自己', str(err.exception))

    def test_cross_company_is_refused(self):
        """要驗訊息：拿掉跨公會檢查後，名冊檢查會接手丟同一種例外。"""
        other_company = self.env['res.company'].create({'name': '他公會（委託）'})
        stranger = self.new_member('Z001', company=other_company)
        # 讓他在自己公會的名冊上，排除「因為不在名冊所以被擋」這個混淆
        their_meeting = self.env['assoc.meeting'].sudo().create({
            'name': '他公會大會（委託）', 'kind': 'assembly',
            'company_id': other_company.id, 'date_begin': self.begin})
        their_meeting.action_build_roster()
        with self.assertRaises(ValidationError) as err:
            self.env['assoc.meeting.proxy'].sudo()._new_proxy(
                self.meeting, self.members[1], stranger)
        self.assertIn('同一公會', str(err.exception))

    def test_seminar_has_no_attend_proxy(self):
        seminar = self.new_meeting('研討會（無委託）', kind='seminar')
        seminar.with_user(self.admin_user).action_open_checkin()
        with self.assertRaises(ValidationError):
            self.env['assoc.meeting.proxy'].sudo()._new_proxy(
                seminar, self.members[1], self.members[2])

    def test_one_principal_one_proxy_per_purpose(self):
        from psycopg2.errors import UniqueViolation
        from odoo.tools import mute_logger
        self.present(1, 2, 3)
        self.register(4, 1, paper_received=True)
        with self.assertRaises(UniqueViolation), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.register(4, 2, paper_received=True)
                self.env.flush_all()

    def test_non_admin_cannot_create_directly(self):
        """連 ACL 都沒有 create 權的角色（現在的報到台就是）。"""
        with self.assertRaises(AccessError):
            self.env['assoc.meeting.proxy'].with_user(self.desk_user).create({
                'meeting_id': self.meeting.id,
                'principal_member_id': self.members[4].id,
                'holder_member_id': self.members[1].id})

    def test_create_check_is_a_second_layer_behind_the_acl(self):
        """有 create 權但不是管理員的角色，仍然不能直接建委託書。

        上一條測試擋住它的其實是 ACL；這一條才驗得到模型裡那道檢查。
        這不是多餘的：日後只要有人為了別的功能（例如 M9 禮品現場登錄）
        給報到台 create 權，ACL 那層就沒了，模型這層要接得住。
        """
        self.env['ir.model.access'].sudo().create({
            'name': '測試用：報到台可建委託書',
            'model_id': self.env.ref('assoc_meeting.model_assoc_meeting_proxy').id,
            'group_id': self.env.ref('assoc_meeting.group_meeting_desk').id,
            'perm_read': True, 'perm_create': True})
        self.env['ir.model.access'].call_cache_clearing_methods()
        with self.assertRaises(AccessError):
            self.env['assoc.meeting.proxy'].with_user(self.desk_user).create({
                'meeting_id': self.meeting.id,
                'principal_member_id': self.members[4].id,
                'holder_member_id': self.members[1].id})

    def test_direct_create_is_forced_to_backend_channel(self):
        proxy = self.env['assoc.meeting.proxy'].with_user(self.admin_user).create({
            'meeting_id': self.meeting.id,
            'principal_member_id': self.members[4].id,
            'holder_member_id': self.members[1].id,
            'channel': 'desk_paper', 'paper_received': True})
        self.assertEqual(proxy.channel, 'backend')

    def test_create_cannot_start_active(self):
        with self.assertRaises(UserError):
            self.env['assoc.meeting.proxy'].with_user(self.admin_user).with_context(
                default_state='active').create({
                    'meeting_id': self.meeting.id,
                    'principal_member_id': self.members[4].id,
                    'holder_member_id': self.members[1].id})

    # ---- FIFO 與開會前的斷言 ----
    def test_fifo_activates_in_holder_checkin_order(self):
        """名額只有 1 個時，受託人**先報到**的那件要先生效。

        兩個細節讓這條容易寫成恆真：
        - 用 6 人出席（容量 2）的話兩件都會 active，排序拿掉也照樣綠 → 用 3 人。
        - `cr.now()` 每個交易只算一次並快取（`sql_db.py:527-532`），
          同一個測試交易裡所有報到的 `checkin_at` 完全相同，排序會退到登記順序。
          正式環境每次掃碼是獨立交易所以會不同；測試要自己造出先後。
        """
        from datetime import timedelta
        from odoo.addons.assoc_base.tools import GUARD
        from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import GUARD_CHECKIN
        self.present(1, 2, 3)                       # 容量 1
        base = self.attendance_of(self.meeting, self.members[1]).checkin_at
        self.attendance_of(self.meeting, self.members[2]).with_context(
            **{GUARD_CHECKIN: GUARD}).write({'checkin_at': base + timedelta(minutes=5)})
        later = self.register(9, 2, paper_received=True)    # 先登記，但受託人 2 後報到
        earlier = self.register(8, 1, paper_received=True)  # 後登記，受託人 1 先報到
        results = dict(self.meeting._activate_waiting_proxies())
        self.assertEqual(results[earlier.id], 'active', '受託人先報到的要先生效')
        self.assertEqual(results[later.id], 'waiting')

    def test_start_session_refuses_when_ratio_broken(self):
        """委託生效後有人取消，比例可能反過來不成立。"""
        self.present(1, 2, 3)
        proxy = self.register(4, 1, paper_received=True)
        proxy._try_activate()
        # 直接把一個人的出席退回（模擬後台更正），比例就破了
        self.attendance_of(self.meeting, self.members[3]).with_context(
            **{'assoc_checkin': GUARD}).write({'state': 'absent', 'checkin_at': False})
        with self.assertRaises(UserError):
            self.meeting.with_user(self.admin_user).action_start_session()

    def test_start_session_activates_waiting_proxies(self):
        """開會前要把候補的委託處理掉。

        先讓它 active 再呼叫 `action_start_session` 的話，pending 清單是空的——
        把那行接線整條刪掉測試照樣綠。
        """
        self.present(1, 2)                          # 容量 0
        proxy = self.register(4, 1, paper_received=True)
        self.assertEqual(proxy._try_activate(), 'waiting')
        self.present(3)                             # 容量 1
        self.meeting.with_user(self.admin_user).action_start_session()
        self.assertEqual(proxy.state, 'active', '開會前應該把候補的委託處理掉')
        self.assertEqual(self.meeting.state, 'in_session')


@tagged('post_install', '-at_install')
class TestProxyGuards(MeetingCase):
    """三鏡頭審查（2026-09-19）抓到的守衛缺口。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('Q%03d' % no) for no in range(1, 8)}
        cls.meeting = cls.new_meeting('守衛測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()

    def present(self, *numbers):
        for no in numbers:
            self.scan(self.meeting, self.members[no].sudo().barcode)

    def active_proxy(self, principal=4, holder=1):
        self.present(1, 2, 3)
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[principal], self.members[holder], paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active')
        return proxy

    # ---- critical：散會後取消會回頭改掉法定人數 ----
    def test_cannot_cancel_once_the_session_has_opened(self):
        """生效的委託在開議之後不能撤回。

        設計前提是「生效當下成立就一直成立」，但那只證明了 present 單調遞增——
        proxied 有一條會員／管理員都走得到的減少路徑。不擋的話，
        法定人數可以在議程進行中、甚至散會之後被改掉，
        而系統沒有決議時點的出席快照。
        """
        proxy = self.active_proxy()
        self.meeting.with_user(self.admin_user).action_start_session()
        self.assertEqual(self.meeting.proxy_count, 1)
        with self.assertRaises(UserError):
            proxy.with_user(self.admin_user).action_cancel('開議後反悔')
        self.meeting.with_user(self.admin_user).action_close_meeting()
        with self.assertRaises(UserError):
            proxy.with_user(self.admin_user).action_cancel('事後反悔')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'proxy')
        self.assertEqual(self.meeting.proxy_count, 1, '散會後的法定人數不能再被動')

    # ---- 取消要有權限：報到台對委託書只有讀取 ACL ----
    def test_desk_cannot_cancel_by_rpc(self):
        proxy = self.active_proxy()
        with self.assertRaises(AccessError):
            proxy.with_user(self.desk_user).action_cancel('報到台用 RPC 取消')
        self.assertEqual(proxy.state, 'active')

    # ---- 每人只能代理 1 人：取消後不能再代下一位 ----
    def test_holder_slot_is_consumed_permanently(self):
        """人團法 §38 是「每人只能代理 1 人」，不是「同時只持有 1 件」。

        只看當下狀態的話，報到台可以「登記→生效→取消→再登記下一位」，
        同一個人就代理了任意多人。
        """
        first = self.active_proxy(principal=4, holder=1)
        first.with_user(self.admin_user).action_cancel('改為親自出席')
        self.assertEqual(first.state, 'cancelled')
        second = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[5], self.members[1], paper_received=True)
        self.assertEqual(second._try_activate(), 'rejected')
        self.assertIn('已代理', second.cancel_reason)

    # ---- 散會後不能讓委託生效 ----
    def test_cannot_activate_after_the_meeting_is_over(self):
        self.present(1, 2, 3)
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], paper_received=True)
        self.meeting.with_user(self.admin_user).action_close_meeting()
        self.assertEqual(proxy._try_activate(), 'meeting_closed')
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'absent')

    # ---- 刪委託書會留下無主的「委託出席」 ----
    def test_activated_proxy_cannot_be_deleted(self):
        """`attendance.proxy_id` 是 ondelete='set null'：三種 ondelete 裡唯一
        「破壞看起來像成功」的那種——刪掉之後出席列還算進法定人數，卻查不到依據。
        """
        proxy = self.active_proxy()
        with self.assertRaises(UserError):
            proxy.sudo().unlink()
        self.assertEqual(self.attendance_of(self.meeting, self.members[4]).state, 'proxy')

    def test_never_activated_proxy_can_be_deleted(self):
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], channel='portal')
        proxy.sudo().unlink()

    # ---- 半套狀態不能留下來 ----
    def test_failed_activation_leaves_nothing_behind(self):
        """出席列先寫、委託書後寫；中間失敗要整筆退回。

        `raise` 本身不回滾，而報到台 controller 會把 UserError 轉成回應 →
        交易照常 commit。用 raw SQL 反查才看得到快取以外的真值。
        """
        self.present(1, 2, 3)
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], channel='portal')
        # **不能用 assertRaises**：`TransactionCase._assertRaises` 自己就包了一層
        # savepoint（common.py:497），例外一丟就整個回滾，於是「少了 savepoint
        # 會留下半套狀態」這件事永遠看不到。要手動接。
        raised = None
        try:
            proxy._activate_attend()
        except UserError as err:
            raised = err
        self.assertIsNotNone(raised, '書面閘門沒過，SQL 應該回 0 列並 raise')
        self.env.invalidate_all()
        att = self.attendance_of(self.meeting, self.members[4])
        self.env.cr.execute(
            "SELECT state, proxy_id FROM assoc_meeting_attendance WHERE id = %s", [att.id])
        self.assertEqual(self.env.cr.fetchone(), ('absent', None), '不能留下半套狀態')
        self.assertEqual(proxy.state, 'requested')

    # ---- 掃描檔是證據，要存得進去 ----
    def test_admin_can_attach_the_paper_scan(self):
        import base64
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], channel='portal')
        proxy.with_user(self.admin_user).write({
            'paper_file': base64.b64encode(b'%PDF-1.4 scan'), 'paper_file_name': 'proxy.pdf'})
        self.assertEqual(proxy.sudo().paper_file_name, 'proxy.pdf')

    def test_evidence_exception_does_not_open_the_state_fields(self):
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], channel='portal')
        with self.assertRaises(UserError):
            proxy.with_user(self.admin_user).write(
                {'paper_file_name': 'x.pdf', 'paper_received': True})

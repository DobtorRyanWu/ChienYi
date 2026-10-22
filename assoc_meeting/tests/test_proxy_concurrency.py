"""兩台報到台同時代簽（計畫 §7）。

用真連線 + Barrier，不用測試交易：TransactionCase 全部跑在同一個 cursor 上，
永遠不會出現 40001，也就驗不到「1/3 上限有沒有被序列化」這件事。

`@tagged('-standard', 'assoc_concurrency')` → 平常不跑，要用
`--test-tags assoc_concurrency` 明確指定。
"""

import threading
import uuid

from odoo import SUPERUSER_ID, api, fields
from odoo.sql_db import db_connect
from odoo.tests import TransactionCase, tagged
from odoo.tools import config, mute_logger


@tagged('-standard', 'assoc_concurrency')
class TestProxyConcurrency(TransactionCase):

    def setUp(self):
        super().setUp()
        self.db_name = self.env.cr.dbname
        # `Registry._lock` 在模組載入（測試就跑在載入過程裡）期間由載入執行緒持有，
        # 而 `api.Environment()` 會去拿它（api.py:583 → registry.py:88-95）——
        # 別的執行緒一建 Environment 就卡死。核心的 `enter_test_mode` 正是為此
        # 把它換成 DummyRLock（registry.py:979-987）。
        # 我們的 worker 走 `db_connect()` 而不是 `registry.cursor()`，所以仍是真的獨立連線。
        # cleanup 是 LIFO：leave 要先註冊才會最後執行，否則資料清理會再卡一次。
        self.registry.enter_test_mode(self.env.cr)
        self.addCleanup(self.registry.leave_test_mode)
        # 這個測試用真連線並且 commit，資料不會隨測試交易回滾 →
        # 每次用不重複的編號，並在結束時自己清掉（否則第二次跑會撞唯一約束）
        self.tag = uuid.uuid4().hex[:6].upper()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        def run(env):
            env.cr.execute("""
                DELETE FROM assoc_meeting_proxy WHERE meeting_id IN
                    (SELECT id FROM assoc_meeting WHERE name LIKE %s);
                DELETE FROM assoc_meeting_attendance WHERE meeting_id IN
                    (SELECT id FROM assoc_meeting WHERE name LIKE %s);
                DELETE FROM assoc_meeting WHERE name LIKE %s;
                DELETE FROM assoc_member WHERE member_no LIKE %s;
            """, ['%%%s%%' % self.tag, '%%%s%%' % self.tag, '%%%s%%' % self.tag,
                  'CC%s%%' % self.tag])
            return True
        self._in_new_cursor(run)

    def _in_new_cursor(self, func, *args):
        """開一條真的連線跑 func(env, *args)，結束時 commit。"""
        registry = self.env.registry
        with db_connect(self.db_name).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            try:
                result = func(env, *args)
                cr.commit()
                return result
            except Exception as err:      # noqa: BLE001  併發的例外要帶回主執行緒判讀
                cr.rollback()
                return err

    def test_two_desks_cannot_break_the_one_third_limit(self):
        """3 人親自出席只容得下 1 件委託。兩台同時代簽，必須只有一件成功。

        少了 `UPDATE meeting.proxy_serial` 這道序列化，兩邊會各自讀到
        present=3／proxy=0，於是各自算出「加上我這件還是 1/3」→ 兩件都生效。
        """
        setup = self._in_new_cursor(self._build_fixture)
        self.assertNotIsInstance(setup, Exception, setup)
        meeting_id, proxy_ids = setup

        barrier = threading.Barrier(2)
        results = {}

        def worker(index, proxy_id):
            def run(env):
                proxy = env['assoc.meeting.proxy'].browse(proxy_id)
                barrier.wait(timeout=30)
                return proxy._try_activate()
            try:
                with mute_logger('odoo.sql_db'):
                    results[index] = self._in_new_cursor(run)
            except BaseException as err:          # noqa: BLE001  執行緒裡的例外不能靜靜消失
                results[index] = err

        threads = [threading.Thread(target=worker, args=(i, pid))
                   for i, pid in enumerate(proxy_ids)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=45)

        def check(env):
            meeting = env['assoc.meeting'].browse(meeting_id)
            return meeting.proxy_count, meeting.present_count

        proxy_count, present_count = self._in_new_cursor(check)
        self.assertEqual(present_count, 3)
        self.assertLessEqual(3 * proxy_count, present_count,
                             '委託出席不得超過親自出席的 1/3（results=%s）' % results)
        self.assertEqual(proxy_count, 1, '恰好一件應該成功：%s' % results)

    # ------------------------------------------------------------------
    def _build_fixture(self, env):
        from odoo.addons.assoc_base.tools import GUARD
        company = env.company
        members = []
        for index in range(1, 7):
            partner = env['res.partner'].create(
                {'name': '併發會員 %s-%s' % (self.tag, index), 'company_id': company.id})
            members.append(env['assoc.member'].create({
                'partner_id': partner.id, 'member_no': 'CC%s%03d' % (self.tag, index),
                'company_id': company.id}))
        meeting = env['assoc.meeting'].create({
            'name': '併發代簽測試 %s' % self.tag, 'kind': 'assembly',
            'company_id': company.id, 'date_begin': fields.Datetime.now()})
        meeting.action_open_checkin()
        Attendance = env['assoc.meeting.attendance']
        for member in members[:3]:      # 3 人親自出席
            Attendance._checkin_by_code(meeting, member.barcode)
        Proxy = env['assoc.meeting.proxy']
        proxies = [
            Proxy._new_proxy(meeting, members[3], members[0], paper_received=True),
            Proxy._new_proxy(meeting, members[4], members[1], paper_received=True),
        ]
        return meeting.id, [proxy.id for proxy in proxies]

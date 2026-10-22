"""改屆次 vs 凍結名冊的真連線競態（第五輪 skeptic）。

用真連線，不用測試交易：TransactionCase 全部跑在同一個 cursor 上，永遠不會出現
40001，也就驗不到「兩個交易的先後順序」這件事（L2⑫：單交易測試在結構上看不到它）。
這裡**不需要執行緒**：危險的順序是「改屆次那個請求的快照早於凍結的提交、而它對
屆次那一列的寫入晚於凍結的提交」，兩條連線在同一個執行緒裡依序推進就排得出來，
而且每次都排出同一個順序（不靠 Barrier 碰運氣）。

`@tagged('-standard', 'assoc_concurrency')` → 平常不跑，要用
`--test-tags assoc_concurrency` 明確指定。
"""

import random
import uuid

from psycopg2.errors import SerializationFailure

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import UserError
from odoo.sql_db import db_connect
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('-standard', 'assoc_concurrency')
class TestTermFreezeRace(TransactionCase):

    def setUp(self):
        super().setUp()
        self.db_name = self.env.cr.dbname
        # 同 `assoc_meeting/tests/test_proxy_concurrency.py`：`Registry._lock` 在模組
        # 載入期間被持有，別的連線一建 Environment 就卡死，`enter_test_mode` 換成
        # DummyRLock。cleanup 是 LIFO，leave 要先註冊才會最後執行。
        self.registry.enter_test_mode(self.env.cr)
        self.addCleanup(self.registry.leave_test_mode)
        # 真連線會 commit，資料不隨測試交易回滾 → 不重複的名字、結束時自己清
        self.tag = uuid.uuid4().hex[:6].upper()
        # `unique(company_id, term_no)`：挑一個測試共用工廠（第 12 屆）碰不到的號
        self.term_no = random.randint(10000, 99999)
        self.addCleanup(self._cleanup)

    def _in_new_cursor(self, func):
        """開一條真的連線跑 func(env)，成功就 commit；例外原樣帶回來判讀。"""
        with db_connect(self.db_name).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            try:
                result = func(env)
                cr.commit()
                return result
            except Exception as err:      # noqa: BLE001  例外要帶回來判讀，不是吞掉
                cr.rollback()
                return err

    def _cleanup(self):
        def run(env):
            env.cr.execute("""
                DELETE FROM assoc_election_log WHERE election_id IN
                    (SELECT id FROM assoc_election WHERE name LIKE %(tag)s);
                DELETE FROM assoc_election_voter WHERE election_id IN
                    (SELECT id FROM assoc_election WHERE name LIKE %(tag)s);
                DELETE FROM assoc_election WHERE name LIKE %(tag)s;
                DELETE FROM assoc_meeting WHERE name LIKE %(tag)s;
                DELETE FROM assoc_term WHERE term_no IN (%(term_no)s, %(next_no)s);
            """, {'tag': '%%%s%%' % self.tag, 'term_no': self.term_no,
                  'next_no': self.term_no + 1})
            return True
        self._in_new_cursor(run)

    def _build_fixture(self, env):
        company = env.company
        meeting = env['assoc.meeting'].create({
            'name': '屆次競態 %s' % self.tag, 'company_id': company.id,
            'date_begin': fields.Datetime.now()})
        term = env['assoc.term'].create({
            'company_id': company.id, 'term_no': self.term_no,
            'date_from': fields.Date.today(), 'state': 'current'})
        election = env['assoc.election'].create({
            'name': '屆次競態 %s' % self.tag, 'company_id': company.id,
            'meeting_id': meeting.id, 'term_id': term.id,
            'director_seats': 1, 'director_alt': 0,
            'supervisor_seats': 0, 'supervisor_alt': 0,
        })
        return term.id, election.id

    def test_renumbering_after_a_committed_freeze_cannot_use_a_stale_snapshot(self):
        """凍結先提交、改屆次那個請求的快照比它早：改屆次不可以成功。

        **這一支是「寫，不是只鎖」的理由。** 第四輪 `action_ready` 只對屆次那一列下
        `SELECT … FOR UPDATE`。REPEATABLE READ 底下，對方等到凍結提交後**沿用舊快照**
        （只有本交易改過那一列才會讓它丟 40001），於是它讀到「沒有選舉有屆次快照」、
        守衛放行 → 後台第 13 屆、鏈上與票上第 12 屆。當時兩處註解都寫「對方會重讀」，
        那是 READ COMMITTED 的行為（第五輪 skeptic 推論，主對話用兩條連線實測證實）。
        """
        fixture = self._in_new_cursor(self._build_fixture)
        self.assertIsInstance(fixture, tuple, '建 fixture 失敗：%r' % (fixture,))
        term_id, election_id = fixture

        renamer = db_connect(self.db_name).cursor()
        try:
            # 改屆次的請求：快照在第一句 SQL 就固定（Odoo 的請求一進來就會查 session／使用者）
            renamer.execute('SELECT 1')
            frozen = self._in_new_cursor(
                lambda env: env['assoc.election'].browse(election_id).action_ready())
            self.assertIs(frozen, True, '凍結名冊本身要成功：%r' % (frozen,))
            env = api.Environment(renamer, SUPERUSER_ID, {})
            try:
                # 40001 會先被 sql_db 以 ERROR 記一筆再往外丟——那是預期中的訊號，
                # 不是這支測試的失敗
                with mute_logger('odoo.sql_db'):
                    env['assoc.term'].browse(term_id).write({'term_no': self.term_no + 1})
                    env.flush_all()
                outcome = 'written'
            except SerializationFailure:
                outcome = 'serialization_failure'     # Odoo 會整個請求重跑
            except UserError:
                outcome = 'blocked'
        finally:
            renamer.rollback()
            renamer.close()
        self.assertNotEqual(
            outcome, 'written',
            '凍結已經提交，改屆次卻在舊快照裡通過了守衛：後台與鏈上、票上的屆次會不一樣')

        # 重跑（Odoo 對 40001 的處置）：新快照看得到凍結，守衛要擋下來
        retried = self._in_new_cursor(
            lambda env: env['assoc.term'].browse(term_id).write({'term_no': self.term_no + 1}))
        self.assertIsInstance(retried, UserError, '重跑時守衛要擋下：%r' % (retried,))

        def numbers(env):
            return (env['assoc.term'].browse(term_id).term_no,
                    env['assoc.election'].browse(election_id).term_no)
        term_now, frozen_snapshot = self._in_new_cursor(numbers)
        self.assertEqual(term_now, frozen_snapshot,
                         '後台的屆次要等於凍結在選舉與鏈上的那一個')


    def test_freezing_after_a_committed_renumbering_uses_the_new_number(self):
        """反方向：改屆次先提交、凍結名冊那個請求的快照比它早——凍結要用新的號次。

        L2⑫：防線成不成立取決於呼叫幾何時，要換一種幾何再跑一次。這個順序**區分不了**
        「寫」與「只鎖」（對方已經改過那一列，`FOR UPDATE` 一樣會吃 40001——第七輪
        simplifier）；它守的是「`action_ready` 這一側要碰屆次那一列」：整句拿掉的話，
        凍結會在舊快照裡讀到舊號次 → 鏈上與票上是舊的、後台是新的。
        """
        fixture = self._in_new_cursor(self._build_fixture)
        self.assertIsInstance(fixture, tuple, '建 fixture 失敗：%r' % (fixture,))
        term_id, election_id = fixture

        freezer = db_connect(self.db_name).cursor()
        try:
            freezer.execute('SELECT 1')          # 凍結那個請求的快照在這裡固定
            renumbered = self._in_new_cursor(
                lambda env: env['assoc.term'].browse(term_id).write({'term_no': self.term_no + 1}))
            self.assertIs(renumbered, True, '改屆次本身要成功（還沒有任何凍結）：%r' % (renumbered,))
            env = api.Environment(freezer, SUPERUSER_ID, {})
            try:
                with mute_logger('odoo.sql_db'):
                    env['assoc.election'].browse(election_id).action_ready()
                    env.flush_all()
                outcome = 'frozen'
            except SerializationFailure:
                outcome = 'serialization_failure'     # Odoo 會整個請求重跑
        finally:
            freezer.rollback()
            freezer.close()
        self.assertEqual(outcome, 'serialization_failure',
                         '改屆次已經提交，凍結卻在舊快照裡讀到舊號次並寫進鏈與選票')

        # 重跑：新快照看得到新的號次
        frozen = self._in_new_cursor(
            lambda env: env['assoc.election'].browse(election_id).action_ready())
        self.assertIs(frozen, True, '重跑時凍結要成功：%r' % (frozen,))

        def numbers(env):
            return (env['assoc.term'].browse(term_id).term_no,
                    env['assoc.election'].browse(election_id).term_no)
        term_now, frozen_snapshot = self._in_new_cursor(numbers)
        self.assertEqual(term_now, frozen_snapshot)
        self.assertEqual(frozen_snapshot, self.term_no + 1)

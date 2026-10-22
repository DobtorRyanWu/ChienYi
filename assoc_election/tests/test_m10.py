"""M10：號次抽籤、大螢幕與跑馬燈、監票封存包、監票員逐場權限（計畫 §10、§3）。

這一批的共同主張是「**可驗證**」：號次抽得出同一個結果、螢幕上看到的數字
與資料庫一致、封存包在**沒有 Odoo 的電腦上**重算得出同樣的結論。
"""

import base64
import csv
import hashlib
import io
import importlib.util
import json
import marshal
import os
import random
import struct
import subprocess
import sys
import uuid as uuid_lib
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_election import verify_core
from odoo.addons.assoc_election.models.assoc_election import GUARD_BOX, GUARD_STATE

from .common import AssocElectionCase, seal_ballots


class ElectionCase(AssocElectionCase):
    """M10 共用：把選舉推到指定狀態。

    `action_count` 在測試交易裡過不了快照檢查（它刻意要求「開票是獨立操作」），
    所以照既有測試的做法直接跑後面三段。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.officer = cls.env['res.users'].create({
            'name': '選務（M10）', 'login': 'm10_officer',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_election.group_election_officer').id])],
        })

    def open_election(self):
        self._open()

    def run_to_counted(self):
        self._open()
        m = self._mid
        # 票數要有明確區別：跨越當選／候補界線的同票會要求監票員先抽籤，
        # 那是另一條路徑（test_tally 驗過），這裡不要卡在它上面
        self._cast('A01', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A03', director=[m('A01'), m('A02'), m('A04')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()


@tagged('post_install', '-at_install')
class TestBallotNumberDraw(ElectionCase):

    def test_entropy_gives_a_reproducible_order(self):
        """系統抽籤要能被任何人用同一條公式重算。

        亂數本身是監票員現場擲骰產生的——系統只負責「用它算出一個可重算的結果」。
        自己產生隨機性的話，沒有人能驗證它不是挑出來的。
        """
        self.election.draw_entropy = '3-5-1-6'
        self.election.action_ready()
        numbers = {c.member_no: c.ballot_number
                   for c in self.election.candidate_ids if c.office == 'director'}
        self.assertEqual(sorted(numbers.values()), list(range(1, len(numbers) + 1)))

        # 用封存包裡的同一條公式重算
        group = sorted(numbers)
        seed = verify_core.draw_seed(self.election.uuid, 'director', '3-5-1-6', group)
        import random
        order = list(group)
        random.Random(seed).shuffle(order)
        expected = {member_no: index for index, member_no in enumerate(order, start=1)}
        self.assertEqual(numbers, expected, '公式重算的結果必須與系統一致')

        # 上面那段是拿同一支函式驗它自己——它證明「重算得出同樣結果」，
        # 但證明不了「亂數有進到種子裡」。少了下面這行，把 entropy 從公式裡
        # 拿掉也不會有任何測試變紅（承辦就能預先算好一組喜歡的號次）。
        self.assertNotEqual(
            verify_core.draw_seed(self.election.uuid, 'director', 'A', group),
            verify_core.draw_seed(self.election.uuid, 'director', 'B', group),
            '不同的亂數必須得到不同的種子')

    def test_draw_is_recorded_in_the_chain_payload(self):
        """號次併入既有的 ballot_ready payload（P19），不新增 log action、不改鏈驗證。"""
        self.election.draw_entropy = 'abc'
        self.election.action_ready()
        entry = self.election.log_ids.sorted('seq')[-1]
        self.assertEqual(entry.action, 'state_change')
        self.assertEqual(entry.payload['draw_method'], 'system')
        self.assertEqual(entry.payload['draw_entropy'], 'abc')
        self.assertTrue(entry.payload['ballot_numbers'])
        self.assertTrue(self.election._verify_chain(), '鏈驗證不受影響')

    def test_manual_numbers_are_validated(self):
        """實體抽籤的結果：只驗每個職位 1..n 不重複。"""
        directors = self.election.candidate_ids.filtered(lambda c: c.office == 'director')
        for index, candidate in enumerate(directors, start=1):
            candidate.ballot_number = index
        supervisors = self.election.candidate_ids.filtered(lambda c: c.office == 'supervisor')
        for index, candidate in enumerate(supervisors, start=1):
            candidate.ballot_number = index
        self.election.action_ready()
        self.assertEqual(self.election.log_ids.sorted('seq')[-1].payload['draw_method'], 'manual')

    def test_duplicate_manual_numbers_are_refused(self):
        directors = self.election.candidate_ids.filtered(lambda c: c.office == 'director')
        for candidate in directors:
            candidate.ballot_number = 1         # 全部都填 1
        with self.assertRaises(UserError) as caught:
            self.election.action_ready()
        self.assertIn('不重複', str(caught.exception))

    def test_no_entropy_and_no_numbers_means_no_draw(self):
        self.election.action_ready()
        self.assertEqual(self.election.log_ids.sorted('seq')[-1].payload['draw_method'], 'none')
        self.assertFalse(any(self.election.candidate_ids.mapped('ballot_number')))

    def test_entropy_cannot_be_changed_after_freeze(self):
        """凍結之後改亂數就能挑一個喜歡的號次結果出來。"""
        self.election.draw_entropy = 'first'
        self.election.action_ready()
        with self.assertRaises(UserError):
            self.election.draw_entropy = 'second'


@tagged('post_install', '-at_install')
class TestScreenPayload(ElectionCase):

    def payload(self):
        from odoo.addons.assoc_election.controllers.screen import _screen_payload
        return _screen_payload(self.election)

    def test_ballot_ready_shows_only_the_roster_size(self):
        self.election.action_ready()
        data = self.payload()
        self.assertEqual(data['roster'], self.election.voter_count)
        self.assertNotIn('voted', data)

    def test_voting_shows_progress_and_chain_head(self):
        self.open_election()
        data = self.payload()
        self.assertEqual(data['voted'], 0)
        self.assertEqual(data['roster'], self.election.voter_count)
        self.assertTrue(data['chain_head'])
        self.assertEqual(len(data['chain_head']), 16)

    def test_screen_shows_both_entropies_for_the_room_to_witness(self):
        """兩組抽籤亂數都要上大螢幕——那是監票員當場唯一看得到它們的地方。

        離線驗算的結尾叫監票員拿這兩個值對「當場擲出來的那一組」，
        而螢幕是他抄下來的來源。原本這兩個欄位在 payload 上**一個測試都沒有**
        （第六輪 simplifier 指出：`draw_entropy` 在測試裡出現 11 次全是設值，
        從來沒有人斷言它出現在 payload 裡），所以把它拿掉也不會有人發現。

        號次亂數在凍結名冊時就要看得到（那時候才抽號次）；
        同票亂數在關票後填，所以關票、開票、公告三個狀態都要繼續顯示。
        """
        self.election.draw_entropy = '4-2-6'
        self.election.action_ready()
        self.assertEqual(self.payload().get('draw_entropy'), '4-2-6',
                         '名冊審定時就要看得到號次亂數')

        self.election.action_open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        self.election.tie_entropy = '7-7-7'
        self.assertEqual(self.payload().get('tie_entropy'), '7-7-7',
                         '關票後要看得到同票亂數')

        seal_ballots(self.election)   # 關票後、開票前的封箱

        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.assertEqual(self.payload().get('tie_entropy'), '7-7-7',
                         '開票後仍要看得到（監票員可能那時才抄）')
        self.election.action_publish()
        self.assertEqual(self.payload().get('tie_entropy'), '7-7-7',
                         '公告後仍要看得到')

    def test_counted_shows_no_numbers_but_keeps_the_anchor(self):
        """票開完了但還沒公告，螢幕先跑出**票數**等於提前公告。

        鏈頭不是結果，給它不會洩漏誰當選——而且監票員在會場抄下來的那一串
        要有地方可以再看一次。原本開票後就不再顯示鏈頭，
        封存包唯一的包外錨點事後在系統裡找不到任何可比對的值（抗辯實測）。
        """
        self.run_to_counted()
        data = self.payload()
        self.assertEqual(data['state'], 'counted')
        self.assertEqual(data['message'], '開票完成，待公告')
        for key in ('voted', 'roster', 'result'):
            self.assertNotIn(key, data, '公告前不得出現 %s' % key)
        self.assertEqual(len(data['chain_head']), 16)

    def test_published_still_shows_the_chain_head(self):
        """公告後也要看得到鏈頭：監票員回家用封存包對照時要找得到這個值。"""
        self.run_to_counted()
        self.election.action_publish()
        data = self.payload()
        self.assertEqual(len(data['chain_head']), 16)
        self.assertGreater(data['chain_length'], 0)

    def test_published_shows_the_frozen_result(self):
        self.run_to_counted()
        self.election.action_publish()
        data = self.payload()
        self.assertTrue(data['result']['offices'])
        rows = data['result']['offices'][0]['rows']
        self.assertTrue(all({'rank', 'name', 'votes', 'result'} <= set(row) for row in rows))

    def test_poll_writes_nothing(self):
        """投票進行中 election 這一列不能被碰（D4）：
        RR 下對已更新提交的列讀寫會 40001，尖峰時整場投票都會退避重試。
        用 `xmin` 證明——它只在該列被寫過才會變。
        """
        self.open_election()
        self.env.flush_all()
        self.env.cr.execute("SELECT xmin::text FROM assoc_election WHERE id = %s", [self.election.id])
        before = self.env.cr.fetchone()[0]
        for _ in range(3):
            self.payload()
        self.env.flush_all()
        self.env.cr.execute("SELECT xmin::text FROM assoc_election WHERE id = %s", [self.election.id])
        self.assertEqual(self.env.cr.fetchone()[0], before, '輪詢不得寫入 election 列')


@tagged('post_install', '-at_install')
class TestTicker(ElectionCase):

    def ticker(self, companies=None):
        return self.env['assoc.election']._ticker_elections(companies)

    def test_only_published_and_opted_in(self):
        self.run_to_counted()
        self.assertNotIn(self.election, self.ticker(), '未公告的不上跑馬燈')
        self.election.action_publish()
        self.assertIn(self.election, self.ticker())
        self.election.show_on_ticker = False
        self.assertNotIn(self.election, self.ticker(), '關掉就不顯示')

    def test_show_on_ticker_is_the_only_field_writable_after_publish(self):
        self.run_to_counted()
        self.election.action_publish()
        self.election.show_on_ticker = False        # 允許
        with self.assertRaises(UserError):
            self.election.name = '改名字'

    def test_company_filter_ignores_garbage(self):
        from odoo.addons.assoc_election.controllers.screen import AssocScreen
        parse = AssocScreen._company_ids
        self.assertEqual(parse('1,2'), [1, 2])
        self.assertEqual(parse("1,'; DROP TABLE"), [1])
        self.assertEqual(parse(None), [])
        self.assertEqual(parse('abc'), [])
        # 這條路由是 auth='public'，壞輸入不能變成 500：
        # `isdigit()` 對上標數字 '²' 回 True，接著 int() 直接爆
        self.assertEqual(parse('1,²,3'), [1, 3])
        # JSON 路由的參數可以是任何型別，`.split` 會 AttributeError
        self.assertEqual(parse([1, 2]), [])
        self.assertEqual(parse({'a': 1}), [])
        # **全是數字也可能炸**：Python 3.11 起 int() 對超過 4300 位的字串
        # 直接 ValueError（CVE-2020-10735 的對策）。實跑複現過公開路由回 500。
        self.assertEqual(parse('9' * 5000), [])
        self.assertEqual(parse('1,' + '9' * 5000 + ',3'), [1, 3])


@tagged('post_install', '-at_install')
class TestLiveSeal(TransactionCase):
    """`verify_core.live_seal()` 的契約——**逐條分支**。

    這支是純函式，而線上（`action_count`／`action_seal_ballots`／`action_void_seal`）
    與離線（封存包裡的驗算腳本）用的是同一份。兩條 mutant
    （「seq 重複時靜默後者勝」「voided_seq 不驗型別」）在只有整合測試時**都存活**：
    整合測試走的是正常鏈，走不到這些分支。
    L2⑯ 的修法：把斷言下沉到那支共用函式的契約，不要指望上層碰得到。
    """

    def entry(self, seq, action, payload=None):
        return {'seq': seq, 'action': action, 'payload': payload or {}}

    def test_no_seal_at_all_is_legal(self):
        """封箱功能上線前的舊資料：沒有封箱不是錯。"""
        seq, payload, voids, problem = verify_core.live_seal([self.entry(1, 'state_change')])
        self.assertEqual((seq, payload, voids, problem), (None, None, [], None))

    def test_one_seal_is_the_live_one(self):
        seq, payload, _voids, problem = verify_core.live_seal(
            [self.entry(3, 'ballots_sealed', {'ballots_digest': 'AAA'})])
        self.assertEqual((seq, payload.get('ballots_digest'), problem), (3, 'AAA', None))

    def test_two_live_seals_is_a_problem(self):
        """封了、改了、再封一次——不可以當成「沒封」放行。"""
        _s, _p, _v, problem = verify_core.live_seal(
            [self.entry(3, 'ballots_sealed'), self.entry(4, 'ballots_sealed')])
        self.assertIn('同時有效', problem or '')

    def test_duplicate_seq_is_a_problem_not_last_one_wins(self):
        """seq 重複時**不可以**靜默取後者——這支的整個立論就是不取最後一筆。

        鏈上 seq 重複另有 `verify_chain` 的連號檢查會抓，但那是**別人**在守；
        這支自己的契約不能有這個洞（第十二輪 skeptic）。
        """
        _s, _p, _v, problem = verify_core.live_seal([
            self.entry(3, 'ballots_sealed', {'ballots_digest': 'AAA'}),
            self.entry(3, 'ballots_sealed', {'ballots_digest': 'BBB'})])
        self.assertIn('共用 seq', problem or '')

    def test_voiding_moves_the_live_seal_forward(self):
        seq, payload, voids, problem = verify_core.live_seal([
            self.entry(3, 'ballots_sealed', {'ballots_digest': 'AAA'}),
            self.entry(4, 'ballots_seal_voided', {'voided_seq': 3, 'reason': '還原備份'}),
            self.entry(5, 'ballots_sealed', {'ballots_digest': 'BBB'})])
        self.assertEqual((seq, payload.get('ballots_digest'), problem), (5, 'BBB', None))
        self.assertEqual(voids, [(4, 3, '還原備份')])

    def test_all_seals_voided_is_legal_recoverable_state(self):
        """作廢完還沒重封——出口要走得通，不可以判成鏈壞掉。

        第一版把它判成 problem，於是唯一的出口自己把門關上了（作廢之後封不了箱）。
        """
        seq, payload, voids, problem = verify_core.live_seal([
            self.entry(3, 'ballots_sealed'),
            self.entry(4, 'ballots_seal_voided', {'voided_seq': 3})])
        self.assertEqual((seq, payload, problem), (None, None, None))
        self.assertEqual(len(voids), 1)

    def test_void_must_point_at_an_existing_earlier_seal(self):
        for label, entries in (
            ('指的封箱不存在', [self.entry(4, 'ballots_seal_voided', {'voided_seq': 9})]),
            ('指到自己後面', [self.entry(3, 'ballots_seal_voided', {'voided_seq': 4}),
                              self.entry(4, 'ballots_sealed')]),
            ('同一筆作廢兩次', [self.entry(3, 'ballots_sealed'),
                               self.entry(4, 'ballots_seal_voided', {'voided_seq': 3}),
                               self.entry(5, 'ballots_seal_voided', {'voided_seq': 3})]),
        ):
            with self.subTest(label):
                self.assertTrue(verify_core.live_seal(entries)[3], label)

    def test_voided_seq_type_is_checked_instead_of_raising(self):
        """payload 完全由寫鏈的人控制——純函式不可以丟例外。

        `voided_seq` 是 list 之類的不可雜湊值時，`in` 會 TypeError：
        離線被 except 收成乾淨 FAIL，線上卻是在 `_compute_ballots_sealed` 裡炸掉、
        表單整個開不起來，而錯誤訊息與作廢無關（第十二輪 skeptic）。
        """
        for bad in ([1], None, '3', 3.0, True, {'a': 1}):
            with self.subTest(repr(bad)):
                _s, _p, _v, problem = verify_core.live_seal([
                    self.entry(3, 'ballots_sealed'),
                    self.entry(4, 'ballots_seal_voided', {'voided_seq': bad})])
                self.assertIn('不是整數', problem or '', repr(bad))


@tagged('post_install', '-at_install')
class TestArchive(ElectionCase):

    def build(self):
        self.run_to_counted()
        self.election.action_publish()
        self.election.action_build_archive()
        return self.election.sudo()._archive_blob()

    def test_archive_contains_everything_needed_offline(self):
        blob = self.build()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = set(archive.namelist())
        self.assertLessEqual(
            {'result.json', 'digests.txt', 'ballots_plain.csv', 'roster.csv', 'log.csv',
             'candidates.csv', 'receipts.csv', 'verify_core.py', 'verify_digest.py'}, names)
        self.assertEqual(len(self.election.archive_sha256), 64)

    def test_verify_script_runs_green_offline(self):
        """封存包要在**沒有 Odoo 的電腦上**跑得起來並回 0。

        這是整個封存包唯一的意義：監票員自己驗得出來。
        用 subprocess 跑，確認它真的沒有 import Odoo。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             'stdout=%s stderr=%s' % (proc.stdout, proc.stderr[-800:]))
            self.assertCheck(proc.stdout, 'chain', 'OK')
            self.assertCheck(proc.stdout, 'recount', 'OK')

    def test_verify_script_fails_when_a_ballot_is_changed(self):
        """改一列就要驗不過——不然這份封存包等於裝飾品。"""
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'ballots_plain.csv'
            lines = path.read_text(encoding='utf-8-sig').splitlines()
            self.assertGreater(len(lines), 1, '要有票才驗得出來')
            parts = lines[1].split(',')
            parts[1] = '999999'                 # 把某一張票改投給不存在的人
            lines[1] = ','.join(parts)
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'ballots_digest', 'FAIL')

    def assertCheck(self, out, name, expect):
        """驗算腳本的某一項是 OK、FAIL 還是 N/A（不適用）——**逐行比對**。

        `assertIn('FAIL chain', out)` 會被 `FAIL chain_complete` 滿足，
        於是「鏈沒在驗」的 mutant 照樣被判成抓到了（實跑踩過）。
        檢查項的名字互為前綴時，子字串比對就是一把壞掉的尺。

        `expect='N/A'` 是「鏈上沒有這個欄位可以當基準」。**它必須與 OK 分得開**：
        把不適用印成 OK，就是把「沒跑」說成「通過」（M-A）。
        """
        prefix = '%s %s' % ({'OK': 'OK  ', 'FAIL': 'FAIL', 'N/A': 'N/A '}[expect], name)
        # 名字後面只能是行尾或空白：`FAIL chain` 不可以被 `FAIL chain_complete` 滿足，
        # 但 `FAIL files_present  ——少了：…` 這種帶說明的要算數
        hit = [row for row in out.splitlines()
               if row.startswith(prefix) and not row[len(prefix):len(prefix) + 1].strip()]
        self.assertTrue(hit, '找不到「%s」這一行，實際輸出：%s'
                        % (prefix.strip(), out.splitlines()[:24]))

    def checklist(self, out):
        """逐項檢查清單那一區（OK／FAIL／N/A 與它們的註腳）。

        **斷言 N/A 的註腳一定要切這一區**，但理由在第三輪換了一次：
        第二輪刻意讓同一句話在總結段重複印（監票員記得的是最後那一段），
        於是 `assertIn(那句話, out)` 被總結段滿足、「逐項不印了」照樣綠
        （第四輪 mutation 實測 #28／#31／#32 存活）；第三輪 simplifier
        把那份重複收斂掉之後，**現在的滿足來源是對帳區**——
        「名冊基準」那一列印著「（見下面【程式驗不到的部分】）」，
        所以 `assertIn('見下面', out)` 一樣恆真。
        **一條寫著過期理由的註解，就是下一個人拿來刪防線的依據**
        （L1⑲；第四輪 simplifier 查到這一句已經對不上現況）。
        """
        return out.split('【拿這幾個數字', 1)[0]

    def naSummary(self, out):
        """【程式驗不到的部分】裡「這包驗不到」那一段。

        反過來的那一半：斷言總結段的話要切這一區，否則會被**逐項**的那一句
        或「凍結名冊那一筆」那段說明滿足（實測 #30 存活）。
        """
        head = '項**這包驗不到**'
        self.assertIn(head, out, '總結段不見了')
        return out.split(head, 1)[-1].split('【本包驗證過', 1)[0].split('【下列名單', 1)[0]

    def factValue(self, out, label):
        """對帳區（【拿這幾個數字去跟你在現場看到的對】）某一列的**值**。

        為什麼不用 `assertIn(值, out)`：`meeting_date` 的值是 `2026-10-15`，
        而鏈上每一筆的 ts 是 UTC ISO（`2026-10-15T08:…`），示範資料的大會日
        又正好是跑測試的當天——於是那個斷言是被**鏈的時間戳**滿足的，恆真。
        實測：把 `meeting_date` 整個從鏈上拿掉（mutant「年月日不進稽核鏈」）
        照樣全綠（M-B：綠是別的東西滿足了我的斷言）。
        """
        head = '【拿這幾個數字去跟你在現場看到的對】'
        self.assertIn(head, out, '對帳區整段不見了')
        rows = out.split(head, 1)[1].splitlines()
        # 標籤後面只能接空白或行尾——標籤互為前綴時子字串比對就是壞掉的尺（同 assertCheck）
        hit = [row for row in rows if row.startswith('  ' + label)
               and not row[2 + len(label):3 + len(label)].strip()]
        self.assertEqual(len(hit), 1, '對帳區沒有唯一的「%s」那一列，實際：%s'
                         % (label, rows[:16]))
        return hit[0][2 + len(label):].strip()

    def assertFact(self, out, label, expect):
        """對帳區某一列的值要**等於** expect；只要片段的話用 `factValue`。"""
        self.assertEqual(self.factValue(out, label), expect)

    def _relabel(self, folder, filenames):
        """把改過的檔重算指紋塞回 digests.txt（模擬會順手改指紋的竄改者）。

        **會新增指紋表裡沒有的項目**：塞一支 `csv.py` 進來的竄改者當然會登記它。
        只想更新既有項目的呼叫端（`_tamper_files`）自己先過濾。
        """
        path = Path(folder) / 'digests.txt'
        digests = json.loads(path.read_text(encoding='utf-8'))
        for name in filenames:
            digests['files'][name] = hashlib.sha256(
                (Path(folder) / name).read_bytes()).hexdigest()
        path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')

    def _tamper_and_verify(self, filename, mutate, relabel=False):
        return self._tamper_files({filename: mutate}, relabel=relabel)

    def _tamper_files(self, mutations, relabel=False):
        """解開封存包、改一個或多個檔、再跑一次離線驗算。回傳 (returncode, stdout)。

        **編碼要跟原檔一致**：CSV 是 utf-8-sig、JSON 是純 utf-8。
        寫錯的話驗算腳本會在解析時就炸掉，測試看起來「有抓到」
        其實只是讓它崩潰——那不能證明檢查項有效（這個坑踩過兩次）。

        `relabel=True` 會把 digests.txt 的逐檔指紋一起改成新的值，模擬一個
        **會順手把摘要一起改掉的**竄改者。沒有這個選項的話，
        每一支竄改測試都只會卡在 `file:` 那一項，證明不了它想證明的那一項。
        """
        def encoding_of(name):
            return 'utf-8-sig' if name.endswith('.csv') else 'utf-8'

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            for filename, mutate in mutations.items():
                path = Path(folder) / filename
                path.write_text(mutate(path.read_text(encoding=encoding_of(filename))),
                                encoding=encoding_of(filename))
            if relabel:
                # `digests.txt` 自己不在指紋表裡（它就是指紋表），登記進去反而
                # 會多生一項 `files_present` FAIL，掩蓋測試真正想證明的那一項
                listed = json.loads((Path(folder) / 'digests.txt')
                                    .read_text(encoding='utf-8')).get('files', {})
                self._relabel(folder, [name for name in mutations if name in listed])
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            return proc.returncode, proc.stdout

    def test_verify_script_catches_a_tampered_chain(self):
        """改稽核鏈的內容要驗不過。

        只斷言「有印 OK chain」是不夠的——把那項檢查寫成恆真也會印 OK。
        要證明它**抓得到**，就得真的改壞一筆。
        """
        def mutate(text):
            # 用 csv 模組解析：payload 欄是 JSON，裡面有逗號，
            # `split(',')` 切出來的欄位根本對不上
            rows = list(csv.reader(io.StringIO(text)))
            rows[1][4] = '{"tampered": true}'      # 第一筆紀錄的 payload
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('log.csv', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain', 'FAIL')

    def test_verify_script_catches_a_tampered_vote_count(self):
        """改開票結果裡的票數要驗不過（重點票這一項的存在理由）。"""
        def mutate(text):
            data = json.loads(text)
            office = sorted(data['offices'])[0]
            data['offices'][office]['ranking'][0]['votes'] += 99
            return json.dumps(data, ensure_ascii=False)

        code, out = self._tamper_and_verify('result.json', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'recount', 'FAIL')

    def test_verify_script_catches_a_swapped_winner_even_with_matching_digests(self):
        """把「誰當選」換掉、**連摘要一起改**，仍然要驗不過。

        這是整包封存檔最要緊的一件事：公告的內容就是「誰當選」。
        竄改者當然會順手把 digests.txt 的摘要一起改成新的——所以摘要
        **不能**拿封存包裡的 digests.txt 當基準（那是竄改者自己放的），
        要拿稽核鏈裡 `counted` 那一筆的 payload：鏈是自己串自己的，
        而鏈頭在投票當天就被監票員抄在紙上了。
        """
        swapped = {}

        def swap_result(text):
            data = json.loads(text)
            office = sorted(data['offices'])[0]
            ranking = data['offices'][office]['ranking']
            self.assertGreater(len(ranking), 1, '要有兩個人以上才換得動')
            ranking[0]['result'], ranking[-1]['result'] = (
                ranking[-1]['result'], ranking[0]['result'])
            swapped.update(data)
            return json.dumps(data, ensure_ascii=False)

        def restate_digest(text):
            # 竄改者當然會把 result_digest 重算後塞回 digests.txt。
            # 這一步做**對**，測試才證明得了「基準不是 digests.txt」。
            digests = json.loads(text)
            digests['result_digest'] = verify_core.result_digest(swapped)
            return json.dumps(digests, ensure_ascii=False)

        code, out = self._tamper_files(
            {'result.json': swap_result, 'digests.txt': restate_digest}, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'result_digest', 'FAIL')
        self.assertCheck(out, 'digests_match_chain', 'FAIL')

    # ------------------------------------------------------------------
    # 第七輪：抽籤的兩個種子、「有沒有抽過籤」、呼叫幾何、統計分項、雜訊檔
    # ------------------------------------------------------------------
    WITNESSED_DICE = 'DICE-WITNESSED-777'

    def run_to_counted_with_a_boundary_tie(self):
        """造一場**跨越當選／候補界線的同票**（理事應選 3、候補 1）。

        三位投票人輪流圈四位候選人 → A03 三票、其餘各兩票；兩票那一群占名次
        2–4，跨過「第 3 名」這條界線，依選罷辦法必須抽籤。
        `run_to_counted` 刻意避開這條路徑，所以同票這一段長期沒有封存包測試。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A02'), m('A03'), m('A04')], supervisor=[m('A05')])
        self._cast('A03', director=[m('A03'), m('A04'), m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        self.election.tie_entropy = self.WITNESSED_DICE     # 監票員當場擲、全場看著上牆
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()

    def build_with_a_tie(self):
        self.run_to_counted_with_a_boundary_tie()
        ties = self.election.result_json['offices']['director']['boundary_ties']
        self.assertTrue(ties, '這個場次必須真的有跨界同票，否則下面的測試什麼都沒證明')
        self.election.action_publish()
        self.election.action_build_archive()
        return self.election.sudo()._archive_blob()

    def _swap_the_tie_using(self, seed_field):
        """回傳一個 mutate_result：換一組亂數，並把名次表改成**用那組算出來的**結果。

        竄改者不會留下自相矛盾的包——他會把 result.json 改成內部完全自洽的一份。
        `seed_field` 是被換掉的那個種子輸入：`tie_entropy` 或 `ballots_digest`。
        兩個都要有測試，因為只比對 `tie_entropy` 的單行修法擋不住第二個
        （第七輪 skeptic 的變體 B：**只**改 `ballots_digest` 也換得掉當選人）。
        """
        def mutate(data):
            block = data['offices']['director']
            rows = {row['member_id']: row for row in block['ranking']}
            entrants = sorted(rows, key=lambda mid: str(rows[mid]['member_no']))
            tally = {mid: rows[mid]['votes'] for mid in rows}
            honest = [row['member_id']
                      for row in sorted(block['ranking'], key=lambda row: row['rank'])]
            for attempt in range(1, 500):
                forged = 'FORGED-%03d' % attempt
                seeds = {'ballots_digest': data['ballots_digest'],
                         'tie_entropy': data['tie_entropy'], seed_field: forged}
                ranked, _ties = verify_core.rank_office(
                    entrants, tally, block['seats'], block['alternates'],
                    seeds['ballots_digest'], 'director', seeds['tie_entropy'])
                if ranked != honest:
                    break
            else:
                self.fail('找不到會換出不同名單的亂數')
            data[seed_field] = forged
            block['ranking'] = [
                dict(rows[member_id], rank=rank,
                     result=verify_core.outcome_for(rank, tally[member_id],
                                                    block['seats'], block['alternates']))
                for rank, member_id in enumerate(ranked, start=1)]
        return mutate

    def _unpack(self, blob, folder):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            archive.extractall(folder)

    def _assert_tie_seed_is_bound(self, seed_field):
        blob = self.build_with_a_tie()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._reforge_tail(folder, self._swap_the_tie_using(seed_field))
        self.assertNotEqual(code, 0, out)
        # 重算用的是鏈上那一份，所以名次對不起來
        self.assertCheck(out, 'ranking', 'FAIL')
        # 而且「包裡寫的」與「鏈上釘的」不一致本身就是一項 FAIL
        self.assertCheck(out, 'seeds_match_chain', 'FAIL')
        # 印給監票員比對骰子的那一組，仍然是鏈上的honest值
        self.assertIn(self.WITNESSED_DICE, out)
        return out

    def test_verify_script_binds_the_tie_entropy_to_the_chain(self):
        """同票抽籤的亂數要取自**鏈上**那一筆，不是取自被驗的 result.json。

        名額已經改綁凍結名冊了，但決定「同票誰當選」的兩個種子沒有。
        第七輪抗辯實跑：改 `result['tie_entropy']` 並重鑄 counted／published 兩筆，
        30/30 OK、退出碼 0、紙本錨點吻合，而理事第 3 名（當選）與第 4 名（候補）
        被對調——腳本印出的亂數還是監票員手上那一組。
        """
        self._assert_tie_seed_is_bound('tie_entropy')

    def test_verify_script_binds_the_ballots_digest_seed_to_the_chain(self):
        """**第二個種子也要綁**：只改 `result['ballots_digest']` 同樣換得掉當選人。

        它在腳本裡除了當抽籤種子之外沒有第二個用途（`ballots_digest` 那一項
        驗的是從 CSV 重算的值對鏈上那一份，不是 result.json 這一欄），
        所以只比對 `tie_entropy` 的單行修法擋不住（skeptic 變體 B）。
        """
        self._assert_tie_seed_is_bound('ballots_digest')

    def test_verify_script_recomputes_whether_a_draw_happened(self):
        """「這場有沒有抽過籤」要由重算決定，不能由 payload 單方面宣告。

        `rank_office` 每次都算得出誰跟誰同票、跨不跨界線，但回傳值原本被丟掉。
        把 counted payload 的 `boundary_ties` 清成 `[]`，腳本就印「本場沒有抽籤」，
        而且同票亂數整段包在 `if ties:` 裡——**連那組要跟骰子對的值都不會印出來**。
        第五輪好不容易把兩組亂數都搬上驗算，一個欄位就把它整段關掉。
        """
        blob = self.build_with_a_tie()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._reforge_tail(
                folder, lambda data: None,
                mutate_payload=lambda payload: payload.update(boundary_ties=[]))
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'boundary_ties_match_recount', 'FAIL')
        self.assertIn('本場有 1 組同票', out, '有沒有同票由重算決定，不由 payload 決定')
        self.assertIn(self.WITNESSED_DICE, out, '要比對的亂數一定要印出來')

    def test_verify_script_prints_the_tie_entropy_even_with_no_ties(self):
        """沒有同票的場次也要把那一格印出來——「未填」與「沒印」不是同一件事。"""
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn('同票抽籤亂數：', proc.stdout)
        self.assertIn('從票數重算，本場沒有跨越當選／候補界線的同票', proc.stdout)

    def test_verify_script_catches_a_forged_valid_invalid_split(self):
        """有效票／無效票的**分項**也要對，不能只對總和。

        把理事的「有效 3／無效 0」改成「2／1」，總和不變、選票一張都沒動，
        原本 30/30 全綠（第七輪 skeptic 實跑）。而這兩個數字經 `_report_offices`
        印進**結果公告 PDF**，腳本給監票員的名單又不含票數統計——人工那關也照不到。
        """
        def mutate(data):
            block = data['offices']['director']
            total = block['valid_ballots'] + block['invalid_ballots']
            self.assertGreater(total, 1, '至少要有兩張票才改得動')
            # **只動這兩格**：順手把 invalid_reasons 也改掉的話，擋下來的是
            # 廢票原因那一句，這個測試就證明不了分項比對（實跑踩到：mutant 存活）
            block['valid_ballots'], block['invalid_ballots'] = total - 1, 1

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._reforge_tail(folder, mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballot_count_agrees', 'FAIL')

    def test_verify_script_catches_a_relabelled_invalid_reason_total(self):
        """廢票的**原因分布**也要對——張數與有效／無效都對得上時只剩它擋得住。

        把一張票改成空白票（合法的廢票），統計誠實更新，唯獨把原因從「空白」
        寫成「超額圈選」：張數 3=3、有效 2、無效 1 全部對得上。
        廢票原因會進結果公告，而它進不了 `ballot_hash`。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            path = Path(folder) / 'ballots_plain.csv'
            rows_in = list(csv.DictReader(io.StringIO(
                path.read_text(encoding='utf-8-sig'))))
            spoiled = rows_in[0]
            office = spoiled['office']
            spoiled.update(choices='', status='invalid', invalid_reason='blank')
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(rows_in[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows_in)
            path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            self._relabel(folder, ['ballots_plain.csv'])
            digest = verify_core.ballots_digest(self.election.uuid, [
                (row['office'], [int(one) for one in row['choices'].split() if one],
                 row['status']) for row in rows_in])

            def own_up(data):
                block = data['offices'][office]
                block['valid_ballots'] -= 1
                block['invalid_ballots'] += 1
                block['invalid_reasons'] = {'over_mark': 1}     # ← 唯一的謊

            code, out = self._reforge_tail(
                folder, own_up,
                mutate_payload=lambda payload: payload.update(ballots_digest=digest))
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballots_digest', 'OK')
        self.assertCheck(out, 'ballot_status', 'OK')
        self.assertCheck(out, 'ballot_count_agrees', 'FAIL')

    def test_verify_script_ignores_but_names_operating_system_noise(self):
        """`.DS_Store` 要忽略並點名；`.py` 不是雜訊，維持硬 FAIL。

        `.DS_Store` 是 Finder **開過資料夾就會生**的，在 Finder 裡看不見也刪不掉，
        而監票員唯一的操作方式就是點進去看。把它判成 FAIL 的後果不是這一次
        驗不過，是教會監票員「FAIL files_present 是正常的」——而真正的程式碼
        注入露出來的正好是同一行檢查。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            (Path(folder) / '.DS_Store').write_bytes(b'\x00Finder')
            (Path(folder) / 'Thumbs.db').write_bytes(b'\x00Windows')
            noisy = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(noisy.returncode, 0, noisy.stdout)
            self.assertCheck(noisy.stdout, 'files_present', 'OK')
            self.assertIn('.DS_Store', noisy.stdout, '忽略也要點名')
            self.assertIn('Thumbs.db', noisy.stdout)
            # **程式碼不是雜訊**：放寬白名單的人不可以順手把 .py 也放進來
            (Path(folder) / 'notes.py').write_text('# 這不是雜訊\n', encoding='utf-8')
            code = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(code.returncode, 0, code.stdout)
            self.assertCheck(code.stdout, 'files_present', 'FAIL')

    def test_verify_script_catches_a_swapped_formula_file(self):
        """**換掉 `verify_core.py` 並把它那一列從指紋表刪掉。**

        那是實際被 `exec` 的公式檔——換掉它等於換掉每一個比較。而這條路徑上
        其他三道全部放行：`missing` 過（檔案在）、`file:` 迴圈跳過它（不在表裡）、
        `unexpected` 過（它在白名單上）。只剩 `extra`（資料夾裡有、指紋表沒登記）
        會紅，而第九輪之前**沒有任何 mutant 或測試碰過那個子句**
        （第九輪 simplifier 點名，並預測加了 mutant 會 STILL GREEN）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            core_path = Path(folder) / 'verify_core.py'
            # 讓 `display()` 不再消毒——換掉公式檔就是換掉每一個比較
            core_path.write_text(
                core_path.read_text(encoding='utf-8').replace(
                    "    safe = printable(value)", "    safe = str(value)"),
                encoding='utf-8')
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            del digests['files']['verify_core.py']      # 連指紋一起拿掉
            digests_path.write_text(json.dumps(digests, ensure_ascii=False),
                                    encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'files_present', 'FAIL')
        self.assertIn('verify_core.py', proc.stdout, '要點名是哪個檔沒登記')

    def test_verify_script_is_not_hijacked_when_run_through_a_symlink(self):
        """**這道防線是「呼叫幾何」相依的**，所以要用另一種幾何測一次。

        第六輪把封存包目錄從 `sys.path` 拔掉，但比對用的是 `abspath`，
        而 CPython 放進 `sys.path[0]` 的是**解過符號連結**的路徑——兩邊規則不同，
        過濾式一個也濾不掉。macOS 的 `/tmp` 與 `$TMPDIR` 預設就是符號連結，
        監票員解壓到暫存資料夾再執行就會中；第七輪實跑：31 OK／0 FAIL／退出碼 0，
        而印出去的當選名單被 `csv.py` 改寫。
        既有四支測試一律 `cwd=包內`＋相對檔名，釘死了唯一能成立的那一種幾何。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as parent:
            real = Path(parent) / 'real'
            real.mkdir()
            self._unpack(blob, real)
            link = Path(parent) / 'link'
            os.symlink(real, link)
            outside = Path(parent) / 'cwd'
            outside.mkdir()
            script = str(link / 'verify_digest.py')
            honest = subprocess.run([sys.executable, script], cwd=outside,
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(honest.returncode, 0,
                             '誠實包經符號連結、從包外呼叫也要綠：%s %s'
                             % (honest.stdout, honest.stderr[-400:]))
            # 同一個幾何下塞一支 csv.py：被 import 到的話腳本會在第一行就退出 0
            (real / 'csv.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
            proc = subprocess.run([sys.executable, script], cwd=outside,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0,
                                '封存包目錄仍留在 sys.path 上：%s' % proc.stdout)
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')

    # ------------------------------------------------------------------
    # 第八輪：票匭的承諾時點、統一消毒層、對帳數字一律顯示
    # ------------------------------------------------------------------
    def test_sealing_blocks_the_gap_between_close_and_count(self):
        """**封箱之後改票，開票要被擋下來。**

        第十輪 red-team 實跑的攻擊：關票之後、開票之前下一句
        `UPDATE assoc_election_ballot SET choices = …`（每職位張數與 status 全不動，
        所以 `_assert_ballot_count` 擋不到），再照正常按鈕開票公告產包——
        稽核鏈一個位元都沒偽造、`_verify_chain()` 回 True、離線驗算 31 項全 OK
        退出碼 0，而當選名單整組換掉。
        封箱把「票匭長這樣」釘進鏈，開票時再比對一次。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A03', director=[m('A01'), m('A02'), m('A04')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)

        # red-team 那一句 SQL：只換「圈了誰」，張數一張都不動
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE assoc_election_ballot SET choices = %s::jsonb
             WHERE election_id = %s AND office = 'director'
        """, [json.dumps([m('A04')]), self.election.id])
        self.env.invalidate_all()
        self.election._assert_ballot_count()     # 張數斷言擋不到，先證明這件事

        # **`_assert_snapshot()` 要先繞開。** 它在單交易的測試裡必然 raise
        # （那是它的設計），於是 `assertRaises(UserError)` 會為了**錯的理由**通過，
        # 而拆掉封箱守衛的 mutant 照樣存活——第一版就是這樣寫的，三條全存活。
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None):
            with self.assertRaises(UserError) as caught:
                self.election.action_count()
        self.assertIn('封存', str(caught.exception), '擋下來的必須是封箱那道守衛')

    def test_ballots_cannot_be_sealed_twice(self):
        """只能封一次。允許重封＝允許「改完再封」，這道防線就沒了。

        **要在 `closed` 狀態測。** 用 `run_to_counted()` 的話狀態已經是 `counted`，
        擋下來的會是「只有關票之後可以封箱」那道狀態守衛——為了錯的理由通過
        （第一版就是這樣寫的，mutant 存活）。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)
        self.assertTrue(self.election.ballots_sealed)
        with self.assertRaises(UserError) as caught:
            seal_ballots(self.election)
        self.assertIn('重封', str(caught.exception))

    def test_sealing_must_be_its_own_request(self):
        """封箱與關票不可以在同一個請求裡。

        這是整段設計的前提：封箱的快照要晚於關票的 commit，才看得到
        `closing` 期間**設計上允許**收下的在途票。第八輪把摘要寫進關票那一筆
        就是敗在這裡（摘要漏掉在途票 → 誠實的選舉在開票時卡死、26 場既有
        已公告選舉回頭驗不過）。而第十一輪 skeptic 指出：這個前提原本
        **沒有任何程式在守**，任何把 close 與 seal 寫進同一個請求的便利按鈕
        都會靜默退回那個版本，而且全套測試沒有一支會紅。

        這支**刻意不繞開** `_assert_snapshot()`——單交易正是「前提為假」的那種
        幾何，所以在這裡它必然 raise，拆掉那一行的 mutant 就會存活不了。
        真正走得通的那條路由 HTTP E2E 證明（三個分開的請求）。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        with self.assertRaises(UserError) as caught:
            self.election.action_seal_ballots()      # 與關票同一個交易
        self.assertIn('獨立', str(caught.exception),
                      '擋下來的必須是快照斷言，不是別的守衛')
        self.assertFalse(self.election.ballots_sealed, '被擋下來就不該留下封箱紀錄')

    def test_counting_requires_a_seal(self):
        """沒封箱不給開票——否則這道防線靠的是「承辦記得按」，那等於沒有防線。"""
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        self.assertFalse(self.election.ballots_sealed)
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None):
            with self.assertRaises(UserError) as caught:
                self.election.action_count()
        self.assertIn('封存票匭', str(caught.exception),
                      '擋下來的必須是「沒封箱」，不是快照斷言')

    def test_voiding_a_seal_lets_a_stuck_election_recover(self):
        """封箱之後票匭對不上時，要有一條**入鏈的**出口。

        原本這場選舉就卡死了：不能開票（摘要不符）、不能重封（只能封一次）、
        `action_cancel` 不吃 `closed`、也刪不掉。對一場誠實但資料被動到的選舉，
        唯一的復原手段是下 SQL——等於把公會推去繞過整個系統，而且完全無痕
        （第十一輪紅隊 medium）。出口擋不住舞弊，但它看得見：作廢與重封
        各自都是鏈上一筆，監票員在第一次封箱抄的鏈頭從此不再是鏈頭。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A02')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)
        # 票匭被動到（還原備份／修復腳本／有人動手腳都是這個形狀）
        self.env.cr.execute(
            "UPDATE assoc_election_ballot SET choices = %s::jsonb "
            "WHERE election_id = %s AND office = 'director' "
            "AND id = (SELECT min(id) FROM assoc_election_ballot "
            "          WHERE election_id = %s AND office = 'director')",
            [json.dumps([m('A03')]), self.election.id, self.election.id])
        self.env.invalidate_all()
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None):
            with self.assertRaises(UserError) as caught:
                self.election.action_count()
            self.assertIn('封存當下不符', str(caught.exception))
            # 卡死：也不能重封
            with self.assertRaises(UserError):
                self.election.action_seal_ballots()

            # 出口：公會管理員寫下原因後作廢
            with self.assertRaises(UserError) as caught:
                self.election.action_void_seal()
            self.assertIn('原因', str(caught.exception), '沒寫原因不可以作廢')
            self.election.with_context(**{GUARD_STATE: GUARD}).seal_void_reason = '還原備份導致票匭變動'
            self.election.action_void_seal()

            # 作廢那一筆在鏈上，而且指名它作廢的是哪一筆
            voided = [log for log in self.election.log_ids if log.action == 'ballots_seal_voided']
            self.assertEqual(len(voided), 1)
            self.assertEqual(voided[0].payload['reason'], '還原備份導致票匭變動')
            # **用完要清空**：不清的話「請先寫原因」那道閘第二次永遠不會 FAIL，
            # 下一次作廢會掛著上一次的說明而管理員什麼都沒寫（L1：改完之後
            # 什麼情況它還會 FAIL？）
            self.assertFalse(self.election.seal_void_reason, '作廢完原因欄位要清空')
            self.assertTrue(self.election._verify_chain(), '作廢之後鏈還是要驗得過')

            # 重新封箱之後開得了票
            self.assertFalse(self.election.ballots_sealed, '作廢之後就是「沒有現行封箱」')
            self.election.action_seal_ballots()
            self.election.action_count()
        self.assertEqual(self.election.state, 'counted')

    def test_void_is_limited_to_the_guild_admin(self):
        """作廢封箱不是承辦的動作——理由該由辦選舉以外的人記錄。"""
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)
        officer = self.env['res.users'].create({
            'name': '只有選務', 'login': 'm10_officer_only',
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_officer').id])]})
        # **原因也不能是承辦寫的。** 原本這一行用 GUARD context 寫，正好掩蓋了
        # 「承辦不帶任何 guard 就寫得進去」——被把關的只有那一下點擊，
        # 而鏈上掛著管理員名字的那句話可以是承辦打的（第十二輪 skeptic）。
        with self.assertRaises(AccessError):
            self.election.with_user(officer).write({'seal_void_reason': '承辦自己打的字'})
        self.election.seal_void_reason = '試試看'
        # **要斷言擋下來的是哪一道。** 只寫 `assertRaises(AccessError)` 的話，
        # 拆掉群組守衛的 mutant 照樣被擋——承辦讀不到 `seal_void_reason`
        # （欄位有 groups=）一樣丟 AccessError，於是測試為了**錯的理由**通過。
        # 我自己加的欄位層 groups= 把群組守衛遮蔽掉了，那條 mutant 前天是 RED、
        # 全量 sweep 跑到它時變成 STILL GREEN（L2⑥，本輪第三次）。
        with self.assertRaises(AccessError) as caught:
            self.election.with_user(officer).action_void_seal()
        self.assertIn('限公會管理員', str(caught.exception),
                      '擋下來的必須是群組守衛，不是「讀不到那個欄位」')

    def test_counting_checks_the_stored_invalid_reason(self):
        """`invalid_reason` 在線上全程沒有人守，而離線必驗——偵測要搬到還救得回來的時點。

        `_compute_results()` 是從 `choices` 重算的，完全不讀 `status` 與
        `invalid_reason`；而封箱的摘要只涵蓋 `(office, choices, status)`。
        所以關票之後把某一列的 `invalid_reason` 寫壞，票照開、公告照發，
        而監票封存包**永遠過不了**——那時已經不可逆（第十一輪紅隊 medium）。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[])       # 監事空白票
        self.election.action_start_closing()
        self.election.action_close()
        self.env.cr.execute(
            "UPDATE assoc_election_ballot SET invalid_reason = 'over_mark' "
            "WHERE election_id = %s AND status = 'invalid'", [self.election.id])
        self.env.invalidate_all()
        seal_ballots(self.election)          # 封箱的摘要抓不到它（不在公式裡）
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None):
            with self.assertRaises(UserError) as caught:
                self.election.action_count()
        self.assertIn('有效／無效判定', str(caught.exception),
                      '擋下來的必須是廢票原因對帳，不是別的守衛')

    def test_verify_rejects_a_void_with_no_live_seal_after_counting(self):
        """「作廢過、沒有現行封箱、票卻已經開了」——線上走不出這個組合。

        `action_count` 要求有**現行**封箱，所以這個形狀只可能是有人繞過系統寫的。
        它是作廢出口帶進來的新失敗模式：攻擊者可以不重封、直接把封箱作廢掉，
        讓 `ballots_sealed_matches` 沒有東西可比而空過
        （L1⑨「沒有東西要驗」不等於「證據被刪了」的反面：這裡上游明說有票開過）。
        """
        blob = self.build()
        seal_seq = next(log.seq for log in self.election.log_ids
                        if log.action == 'ballots_sealed')
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def void_the_seal(rows):
                # 在封箱那一列後面插一筆作廢，其餘原封不動（seq 由 _rebuild_chain 重編）
                out = []
                for row in rows:
                    out.append(row)
                    if row[3] == 'ballots_sealed':
                        out.append([row[0], row[1], row[2], 'ballots_seal_voided',
                                    json.dumps({'voided_seq': seal_seq, 'reason': '刪掉它'}),
                                    row[5], row[6]])
                return out

            self._rebuild_chain(folder, void_the_seal)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'ballots_sealed_matches', 'FAIL')

    def test_report_tells_the_observer_to_copy_the_seal(self):
        """離線報表要把**封箱那一筆**標成「釘得住結果」，並叫監票員抄它。

        第十一輪紅隊：機制是有效的（保留封箱那一筆、只重鑄 counted/published →
        `FAIL ballots_sealed_matches`），**失效的是指引**——鏈表原本用
        `seq >= seq_counted` 分類，於是把封箱那一筆印成「證明不了誰當選」，
        而它正是唯一抓得到「關票後改票」的那個值。照著舊指引做的監票員，
        手上的值在那個攻擊下原封不動。
        指引錯了，機制再對也沒有用——所以這件事要有測試守著。
        """
        blob = self.build()
        seal_seq = next(log.seq for log in self.election.log_ids
                        if log.action == 'ballots_sealed')
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout)
        rows = [line for line in proc.stdout.splitlines()
                if line.strip().startswith('seq %-3s ballots_sealed' % seal_seq)
                or line.strip().startswith('seq %s   ballots_sealed' % seal_seq)]
        self.assertTrue(rows, '鏈表裡找不到封箱那一筆：%s' % proc.stdout[-600:])
        self.assertIn('票匭與當選名單都釘住', rows[0],
                      '封箱那一筆必須被標成釘得住結果，否則監票員會去抄錯的值')
        self.assertIn('最早釘得住票匭的是「封箱」那一筆（seq %s）' % seal_seq, proc.stdout,
                      '要明講該抄哪一個')

    def test_a_second_seal_entry_cannot_unlock_a_third_seal(self):
        """鏈上已經有兩筆封箱時，第三次按「封箱」仍然要被擋。

        `_sealed_entry()` 在「超過一筆」時回 None——那是它對**開票**的正確語意
        （重複等於沒封）。但重封守衛原本也問它，於是鏈上一旦有兩筆，
        第三次封箱不會被擋：操作者收到「成功」，而選舉其實已經永久開不了票，
        稽核鏈還能被無限灌筆（第十一輪 skeptic 實跑）。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        Log = self.env['assoc.election.log'].sudo()
        for _ in range(2):        # 直接入鏈兩筆（模擬持 DB 權限者灌進來的）
            Log._append(self.election, 'ballots_sealed', {
                'ballots_digest': self.election._compute_ballots_digest(),
                'ballot_count': self.election._assert_ballot_count()})
        self.assertIsNone(self.election._sealed_entry(), '兩筆＝取不到唯一那一筆')
        with self.assertRaises(UserError) as caught:
            seal_ballots(self.election)
        # 訊息要講出真正的問題（「有兩筆同時有效」），而不是含混的「不能重封」——
        # 兩者的處置不同：一個是手殘連按，一個是有人往鏈上灌東西。
        self.assertIn('2 筆封箱同時有效', str(caught.exception))
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None):
            with self.assertRaises(UserError) as counting:
                self.election.action_count()
        self.assertIn('2 筆封箱同時有效', str(counting.exception),
                      '開票也要被同一個理由擋下來，而不是說「還沒封箱」')

    def test_counting_compares_the_sealed_ballot_count(self):
        """摘要相等不蘊含筆數相等——票數要另外對帳（L1⑧）。

        封箱 payload 記了 `ballot_count`，而原本線上線下都沒有人比對它，
        是一個永遠不會 FAIL 的裝飾（第十一輪三個鏡頭都指到）。
        這裡讓「現在數出來的張數」與封箱那一筆不同，開票必須拒絕。
        """
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)
        real = self.election._assert_ballot_count()
        with patch.object(type(self.election), '_assert_snapshot', lambda self: None), \
             patch.object(type(self.election), '_assert_ballot_count',
                          lambda self: real + 1):
            with self.assertRaises(UserError) as caught:
                self.election.action_count()
        self.assertIn('張數', str(caught.exception),
                      '擋下來的必須是票數對帳，不是別的守衛')

    def test_verify_script_catches_a_tamper_after_sealing(self):
        """離線也要抓得到：封箱那一筆記的票匭與包裡的選票對不上。"""
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            path = Path(folder) / 'ballots_plain.csv'
            rows_in = list(csv.DictReader(io.StringIO(
                path.read_text(encoding='utf-8-sig'))))
            rows_in[0]['choices'] = str(self._mid('A04'))
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(rows_in[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows_in)
            path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            self._relabel(folder, ['ballots_plain.csv'])
            digest = verify_core.ballots_digest(self.election.uuid, [
                (row['office'], [int(one) for one in row['choices'].split() if one],
                 row['status']) for row in rows_in])
            # 竄改者把**開票**那一筆的摘要改對了（那一筆在紙本錨點之後，重鑄得掉），
            # 但**封箱**那一筆改不動——它在監票員抄鏈頭的時點之前
            code, out = self._reforge_tail(
                folder, lambda data: None,
                mutate_payload=lambda payload: payload.update(ballots_digest=digest))
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballots_digest', 'OK')          # 開票那一筆已被改對
        self.assertCheck(out, 'ballots_sealed_matches', 'FAIL')

    def test_in_flight_ballot_does_not_break_an_honest_election(self):
        """**關票同時投出的在途票，不可以讓一場乾淨的選舉卡死。**

        `closing` 的定義就是「已停止領票，**在途選票仍可投出**」，而關票的 UPDATE
        會等那些交易釋放 FOR SHARE。第八輪我把票匭摘要寫進關票那一筆，
        但摘要在等鎖**之前**就求值了，而 Odoo 的 cursor 是 REPEATABLE READ
        ——於是被設計明文允許收下的票不在摘要裡，`_verify_chain()` 回 False、
        `action_publish()` 永久拒絕、`action_cancel` 不吃 counted，選舉永遠卡住。
        第九輪撤回那個欄位；這支測試釘住「關票那一筆不得帶票匭摘要」，
        免得有人再加回來。（真正的在途競態要兩條連線才複現得出來，
        那是 `@tagged('-standard','assoc_concurrency')` 的範圍；這裡釘的是不變量。）
        """
        self.run_to_counted()
        closed = [log for log in self.election.log_ids
                  if (log.payload or {}).get('to') == 'closed']
        self.assertEqual(len(closed), 1)
        self.assertNotIn('ballots_digest', closed[0].payload,
                         '關票那一筆不可以帶票匭摘要：它看不到在途選票，'
                         '而「票被刪掉」會被它認證成「票匭沒被動過」')
        self.assertTrue(self.election._verify_chain())

    def test_verify_script_sanitises_the_chain_state_column(self):
        """鏈表的狀態欄也是承辦寫的。

        `state = payload['to'] or action`——非 `state_change` 的紀錄（`reissue`
        那類）沒有 `to`，於是印出去的是 `action`，而那個字串完全由承辦控制。
        第八輪 red-team 實跑：改成帶 `\x1b[3J\x1b[2J\x1b[H` 的字串並重算雜湊，
        31 項全 OK、退出碼 0，而監票員螢幕被清屏重繪成假的全綠畫面＋掉包名單。
        注入在**檔案內容**裡，`unzip` 與 `python -m zipfile -e` 都清不掉。
        這是同一個 bug 類的第三次（姓名、檔名、狀態欄），所以修法是把 `print`
        換成統一消毒的包裝層，而不是再補第三處。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            evil = 'reissue\x1b[3J\x1b[2J\x1b[H OK   everything'
            # payload 不帶 `to` → 腳本會退回去印 action，那就是注入點
            code, out = self._append_transitions(folder, [{'reason': 'x'}], action=evil)
        self.assertNotEqual(code, 0, out)
        self.assertNotIn('\x1b', out,
                         '逃逸字元不得原樣進到監票員的終端機：%s' % out[:400])
        self.assertIn('reissue', out, '狀態欄本身還是要看得到')

    def test_verify_script_always_shows_the_numbers_to_cross_check(self):
        """對帳數字要**一律**印，不是只在 FAIL 時印。

        它們原本只放在 `notes` 裡，而 `notes` 只在 FAIL 時顯示——於是監票員
        在「一切正常」的情況下看不到任何一個能跟現場記憶對帳的數字。
        而票匭與名冊的竄改在包內是自洽的（投票人數、收據碼張數、名冊已投列數
        在開票那一刻全是同一張表的下游），所以人腦記憶是唯一的獨立來源。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        # **斷言值，不要只斷言標籤。** 標籤是無條件印出去的，所以八個值全部印成空白
        # 這支測試照樣綠——那證明的是「那幾行存在」，不是「監票員拿得到數字」
        # （第九輪 simplifier：這是第三個循環自證的測試，前兩個是 all_checks_ran
        # 與綁凍結候選人清單那一段）。
        printed = {}
        for line in proc.stdout.splitlines():
            if line.startswith('  ') and '　' not in line:
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    printed[parts[0]] = parts[1].strip()
        for label in ('投票人數（鏈上記的）', '收據碼張數', '各職位選票張數',
                      '各職位有效／無效', '跨界同票組數（重算）'):
            self.assertIn(label, printed, '全綠時也要看得到「%s」' % label)
            self.assertTrue(printed[label], '「%s」印出來是空的' % label)
        # 至少一項要對得上真值，否則「印了東西」也可能是印錯的東西
        self.assertEqual(printed['投票人數（鏈上記的）'], str(self.election.voted_count))
        self.assertEqual(printed['收據碼張數'], str(self.election.voted_count))

    def test_verify_script_states_the_limits_that_match_the_chain(self):
        """【程式驗不到的部分】講的話必須與**這一包的鏈**相符。

        這一段錯過兩次，兩次都是「機制改了、印出去的字沒跟著改」：
        第八輪寫「票匭摘要最早在關票那一筆」，第九輪撤回那個機制卻沒改文字，
        於是它一邊叫人「關票當下抄鏈頭」、一邊在四行後把關票標成「證明不了誰當選」
        （第十輪 skeptic 與 red-team 各自指到）。
        所以這支測試不再只比對兩個子字串——**它從鏈上讀出事實，再要求文字與之相符**。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            log_rows = list(csv.DictReader(io.StringIO(
                (Path(folder) / 'log.csv').read_text(encoding='utf-8-sig'))))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        sealed = [row for row in log_rows if row['action'] == 'ballots_sealed']
        self.assertEqual(len(sealed), 1, '這包應該有封箱紀錄（run_to_counted 會封）')
        # 有封箱 → 必須印出關票與封箱的時間讓人判斷那段空窗，而**不可以**
        # 再說「這包沒有封箱紀錄」
        self.assertIn('關票→封箱那段', proc.stdout)
        self.assertNotIn('這包沒有封箱紀錄', proc.stdout)
        closed_ts = next(row['ts'] for row in log_rows
                         if json.loads(row['payload']).get('to') == 'closed')
        self.assertIn(closed_ts, proc.stdout, '關票時間要印出來給人比對')
        self.assertIn(sealed[0]['ts'], proc.stdout, '封箱時間要印出來')
        # 而「投票進行中驗不到」這一句在兩種情況下都必須在
        self.assertIn('證明不了', proc.stdout)

    def test_verify_script_says_when_the_package_has_no_seal(self):
        """沒有封箱的包（加這個功能之前產生的）要**明講**，不可以靜靜地通過。

        `ballots_sealed_matches` 在沒有封箱時是「沒有東西與它矛盾」，
        不是「驗過了」——這個差別要寫給監票員看，否則又是一次
        「『全部 OK』替一個它撐不起來的結論背書」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            # 模擬舊包：把封箱那一筆從鏈上拿掉並整條重算
            code, out = self._rebuild_chain(
                folder, lambda body: [row for row in body if row[3] != 'ballots_sealed'])
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'ballots_sealed_matches', 'OK')
        self.assertIn('這包沒有封箱紀錄', out)
        self.assertIn('不是「驗過了」', out)

    def test_verify_script_catches_a_deleted_write_in_row(self):
        """`candidates_match_result` 要**雙向**：result.json 有、CSV 沒有也要 FAIL。

        名單外得票（write-in）的當選人正好是這種列——`ballot_numbers` 只蓋得住
        凍結時就登記過的候選人，所以整列刪掉原本零 FAIL（第八輪 skeptic F7）。
        """
        def mutate(text):
            rows_in = list(csv.reader(io.StringIO(text)))
            self.assertGreater(len(rows_in), 2, '至少要有兩列候選人')
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows_in[:-1])
            return buffer.getvalue()

        code, out = self._tamper_and_verify('candidates.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'candidates_match_result', 'FAIL')

    def test_verify_script_catches_a_duplicated_ranking_row(self):
        """名次表複製一列也要 FAIL——`dict` 會無聲吃掉重複的 member_id。"""
        def mutate(data):
            block = data['offices']['director']
            block['ranking'] = block['ranking'] + [dict(block['ranking'][-1])]

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._reforge_tail(folder, mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ranking', 'FAIL')

    def test_verify_script_names_a_vacant_seat_instead_of_printing_nothing(self):
        """「席位從缺」要用說的。空白的那一格與「程式印壞了」在人眼裡一樣。"""
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def vacate(data):
                for block in data['offices'].values():
                    for row in block['ranking']:
                        row['result'] = 'none'

            code, out = self._reforge_tail(folder, vacate)
        # 名次與結果對不上會 FAIL（那是對的），重點是**有把「從缺」講出來**
        self.assertIn('席位從缺', out, out[-1200:])

    def test_verify_script_rejects_a_duplicated_open_entry(self):
        """離線不可以比線上鬆：任何狀態重複都要 FAIL。

        原本只驗四個必要狀態唯一，於是鏈上可以有兩筆 `open`；而監票員名單取的是
        `unique_transition(…, 'open')`，重複就回 None → 整段退化成
        「（沒有任何監票員）」而所有檢查照樣全綠（第八輪 skeptic F5）。
        """
        def duplicate_open(body):
            index = next(i for i, row in enumerate(body)
                         if json.loads(row[4]).get('to') == 'open')
            return body[:index + 1] + [list(body[index])] + body[index + 1:]

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, duplicate_open)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_complete', 'FAIL')
        self.assertCheck(out, 'chain', 'OK')        # 整條鏈重算過，是自洽的
        self.assertIn('沒有任何監票員', out, '重複的 open 會讓監票員名單整段消失')

    def test_unique_transition_refuses_to_pick_when_a_state_repeats(self):
        """取基準的那支函式：**重複就回 None**，不可以「取最後一筆」。

        第四輪的洞就是「畫記號取第一筆、取基準取最後一筆」——往鏈尾追加
        一筆 `counted`，基準就整個易主，而監票員抄的舊鏈頭照樣成立。
        線上 `_verify_chain` 與離線腳本共用這支函式。
        第八輪加了「所有狀態都必須唯一」之後，封存包那條路徑會先被擋下來，
        於是**沒有任何封存包等級的測試能再殺掉這條 mutant**——所以改成
        直接釘住這支共用函式的契約（它的存在理由就是這個行為）。
        """
        rows = [(1, 'counted', {'which': 'first'}), (2, 'counted', {'which': 'second'})]
        self.assertIsNone(verify_core.unique_transition(rows, 'counted'),
                          '重複的狀態不可以挑一筆出來當基準')
        self.assertEqual(verify_core.unique_transition(rows[:1], 'counted'),
                         {'which': 'first'})
        self.assertIsNone(verify_core.unique_transition(rows, 'published'), '不存在就回 None')

    def test_verify_script_rejects_a_chain_without_the_counted_entry(self):
        """開票那一筆被拿掉要走 `chain_complete`，**不可以退化成 data_shape**。

        `bool(anchor)`／`bool(ready)` 看起來被別的檢查蘊含，實際上它們是
        `seq_of['...']` 的 KeyError 短路守衛：少了它們，「少一筆狀態」會從
        乾淨的 `FAIL chain_complete` 變成看不懂的 `FAIL data_shape`，
        而且後面所有檢查整批不跑。第十輪拆開 mutant 才發現沒人守這件事。
        """
        def drop_counted(body):
            return [row for row in body if json.loads(row[4]).get('to') != 'counted']

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, drop_counted)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_complete', 'FAIL')
        self.assertNotIn('FAIL data_shape', out,
                         '少一筆狀態要走 chain_complete，不要退化成 data_shape')

    def test_verify_script_rejects_a_chain_without_the_ready_entry(self):
        """凍結名冊那一筆被拿掉，同上——而且它是名額與姓名的錨點。"""
        def drop_ready(body):
            return [row for row in body if json.loads(row[4]).get('to') != 'ballot_ready']

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, drop_ready)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_complete', 'FAIL')
        self.assertNotIn('FAIL data_shape', out)

    def test_verify_script_rejects_close_after_count(self):
        """把關票排到開票**之後**也要 FAIL。

        整條鏈重建之後每一筆的雜湊都算得出來、首尾相接，所以「狀態都在、都唯一」
        還不夠——順序本身要驗。既有測試只走過 `ballot_ready` 與 `closed` 對調
        那一對，`closed < counted` 這一句從來沒有人證明過（第十輪 simplifier 預測
        拆開後會存活，實跑證實）。
        """
        def swap_closed_and_counted(body):
            closed = next(row for row in body if json.loads(row[4]).get('to') == 'closed')
            counted = next(row for row in body if json.loads(row[4]).get('to') == 'counted')
            out = list(body)
            i, j = out.index(closed), out.index(counted)
            out[i], out[j] = out[j], out[i]
            return out

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, swap_closed_and_counted)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain', 'OK')          # 重算過，鏈自己是自洽的
        self.assertCheck(out, 'chain_complete', 'FAIL')

    def test_verify_script_rejects_a_reordered_chain(self):
        """整條鏈重建、把狀態順序打亂也要 FAIL。

        有 DB 權限的人可以整條重造（公式公開、無金鑰），所以「每個狀態都在、
        都唯一、鏈也自洽」還不夠——順序本身要驗。把凍結名冊那一筆排到關票
        之後，票匭的承諾就變成「先關票再凍結名冊」那種說不通的順序。
        第八輪之前沒有任何測試或 mutant 走過這條路。
        """
        def move_ready_after_closed(body):
            ready = next(row for row in body if json.loads(row[4]).get('to') == 'ballot_ready')
            rest = [row for row in body if row is not ready]
            index = next(i for i, row in enumerate(rest)
                         if json.loads(row[4]).get('to') == 'closed')
            return rest[:index + 1] + [ready] + rest[index + 1:]

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, move_ready_after_closed)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain', 'OK')        # 重算過，鏈自己是自洽的
        self.assertCheck(out, 'chain_complete', 'FAIL')

    def test_verify_script_rejects_a_chain_without_the_close_entry(self):
        """關票那一筆被整個拿掉也要乾淨地 FAIL——票匭的承諾就記在那一筆上。"""
        def drop_closed(body):
            return [row for row in body if json.loads(row[4]).get('to') != 'closed']

        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            code, out = self._rebuild_chain(folder, drop_closed)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_complete', 'FAIL')
        self.assertNotIn('FAIL data_shape', out,
                         '少一筆狀態要走 chain_complete，不要退化成看不懂的 data_shape')

    def test_verify_script_never_prints_raw_control_characters(self):
        """檔名是竄改者寫的，而它會被逐字 print 到監票員的終端機上。

        帶 ANSI 逃逸序列的檔名可以把整個畫面重繪：第七輪 red-team 實跑，
        一包當選人被對調的偽造包在螢幕上顯示 20+ 項全 OK、印出偽造贏家名單、
        published 鏈頭與紙本吻合，唯一破綻是退出碼 1——而腳本自述的服務對象
        「多半不是工程師」，不會去打 `echo $?`。
        `core.display` 的 docstring 早就點名這一招，但只接到「會員姓名」那條路徑；
        `files_present` 的 note 與 `file:` 這個檢查項名是另外兩條。
        （Info-ZIP 的 `unzip` 會清掉檔名控制字元，`python -m zipfile -e` 不會——
        「只有 Python 的監票員」正好落在生效那一側。）
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            evil = '\x1b[2J\x1b[H OK  everything_is_fine.txt'
            (Path(folder) / evil).write_bytes(b'')
            self._relabel(folder, [evil])       # 竄改者當然會順手登記進指紋表
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'files_present', 'FAIL')
        self.assertNotIn('\x1b', proc.stdout, '逃逸字元不得原樣進到監票員的終端機')

    def test_verify_script_survives_a_legacy_console_encoding(self):
        """**合法的包在 cp950 下不可以崩潰**——比漏報更糟的是誤判。

        zh-TW Windows 的 locale 編碼是 cp950，它編不出 ✔／✘／↳（也編不出
        不少人名用字）。原本印完 31 項全 OK 之後在鏈表那一行 UnicodeEncodeError、
        退出碼 1，而要跟紙本比對的那張表**一列都沒印出來**（第七輪 red-team 實測）。
        """
        # **用真實的觸發條件**：罕用字人名。原本靠腳本自己印的 ✔／✘ 來觸發，
        # 但第八輪把鏈表改成純文字之後誠實包裡就沒有 cp950 編不出的字了，
        # 那支測試於是變成恆真（mutation 立刻抓到：改成 strict 仍然全綠）。
        # 姓名才是這個問題的真正來源——台灣的名冊裡罕用字很常見。
        self.members['A01'].partner_id.name = '王𠮷明'
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run(
                [sys.executable, 'verify_digest.py'], cwd=folder,
                capture_output=True, text=True, timeout=120,
                env=dict(os.environ, PYTHONIOENCODING='cp950'),
                encoding='cp950', errors='replace')
        self.assertEqual(proc.returncode, 0,
                         'stdout=%s stderr=%s' % (proc.stdout[-1200:], proc.stderr[-600:]))
        chain_rows = [line for line in proc.stdout.splitlines() if ' seq ' in line]
        self.assertGreaterEqual(len(chain_rows), 4,
                                '鏈表一列都沒印出來：%s' % proc.stdout[-1200:])

    def test_verify_script_survives_a_non_object_payload(self):
        """payload 被改成合法的 `[]` 時，要乾淨地 FAIL，不要在結尾吐 traceback。

        上面的檢查照常印 `FAIL data_shape`，但結尾那張鏈表的
        `entry['payload'].get('to')` 在大 try **外面** AttributeError——
        整份驗算唯一的包外錨點又一次被截斷（第七輪 red-team 實測）。
        """
        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            rows[1][4] = '[]'
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('log.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'data_shape', 'FAIL')
        self.assertIn('【兩組抽籤亂數】', out, '結尾的人工指引要一路印到底')

    def test_verify_script_catches_a_tampered_invalid_reason(self):
        """只改 `invalid_reason` 這一欄也要驗不過。

        這一欄進不了 `ballot_hash`（改公式會讓已公告的摘要全部作廢），
        所以靠重算把它綁住。少了這一項，把有效票標成「廢票／超額圈選」
        再連摘要一起改，六項檢查會全綠。
        """
        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            rows[1][3] = 'over_mark'            # 第一張票的無效原因
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('ballots_plain.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballot_status', 'FAIL')

    def test_verify_script_refuses_an_empty_ranking(self):
        """名次表被整個清空時，重點票要**失敗**而不是無事通過。

        `all()` 對空序列恆為真：原本把 ranking 清成 `[]`，
        「每個人的票數都對」這句話在數學上就成立了。
        """
        def mutate(text):
            data = json.loads(text)
            for office in data['offices'].values():
                office['ranking'] = []
            return json.dumps(data, ensure_ascii=False)

        code, out = self._tamper_and_verify('result.json', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'recount', 'FAIL')

    def test_verify_script_catches_a_deleted_winner_row(self):
        """把某個當選人整列從名次表刪掉也要驗不過。

        只驗「表上的人票數對」是單向的：刪掉的人不在表上，就沒有人去比對他。
        所以另一個方向也要驗——重算出有票的人，都必須出現在名次表上。
        """
        def mutate(text):
            data = json.loads(text)
            office = sorted(data['offices'])[0]
            data['offices'][office]['ranking'] = data['offices'][office]['ranking'][1:]
            return json.dumps(data, ensure_ascii=False)

        code, out = self._tamper_and_verify('result.json', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'recount', 'FAIL')

    def test_verify_script_catches_a_truncated_chain(self):
        """把稽核鏈的尾巴砍掉要驗不過。

        `verify_chain` 是從頭往後串的，砍掉最後幾筆之後**剩下的部分照樣首尾相接**、
        每一筆的雜湊也都算得出來——鏈本身抓不到這件事。
        擋得住的是「一包已公告的封存檔，鏈上一定要先有 counted 再有 published」。
        """
        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            header, body = rows[0], rows[1:]
            keep = [row for row in body if json.loads(row[4]).get('to') != 'published']
            self.assertLess(len(keep), len(body), '要真的砍掉一筆才驗得出來')
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows([header] + keep)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('log.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_complete', 'FAIL')

    def test_verify_script_catches_a_forged_vote_table(self):
        """改 `candidates.csv` 的票數與當選結果、**連指紋一起改**，也要驗不過。

        red-team 實跑複現：這份「候選人得票表」原本只靠 `digests.txt` 的逐檔指紋，
        而那份指紋就在同一個 zip 裡——把票數全改 999、結果全改「當選」，
        再重算那一個檔的指紋，20 項全 OK、退出碼 0、**稽核鏈頭與竄改前一模一樣**
        （也就是監票員抄在紙上的那一串照樣對得上）。
        現在它綁回鏈上的 `result.json`，同一招就失效了。
        """
        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            for row in rows[1:]:
                row[6], row[8] = '999', 'elected'      # votes、result
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('candidates.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'candidates_match_result', 'FAIL')

    def test_verify_script_catches_a_forged_receipt_list(self):
        """改收據碼清單也要驗不過。

        會員唯一能親自核對的就是「我的碼在不在這份清單裡」。
        改掉它等於能讓某些會員以為自己的票不見了，而驗算全綠。
        """
        def mutate(text):
            lines = text.splitlines()
            self.assertGreater(len(lines), 1, '要有收據碼才驗得出來')
            lines[1] = 'FAKECODE0000'
            return '\n'.join(lines) + '\n'

        code, out = self._tamper_and_verify('receipts.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'receipts_digest', 'FAIL')

    def test_verify_script_names_what_it_cannot_verify(self):
        """「全部 OK」不可以被誤讀成「整包都驗過了」。

        `result.pdf` 每次產生的位元組都不同、沒辦法重算，而它看起來最像官方文件。
        所以腳本要**明講驗不到它**，並把從已錨定的 `result.json` 算出來的
        當選名單印出來，讓監票員拿去對 PDF。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr[-400:])
            self.assertIn('程式驗不到的部分', proc.stdout)
            self.assertIn('result.pdf', proc.stdout)
            self.assertIn('本包驗證過的當選與候補名單', proc.stdout)
            elected = self.election.result_json['offices']['director']['ranking'][0]
            self.assertIn(elected['name'], proc.stdout, '名單要印得出來才能拿去對 PDF')

    def test_verify_script_catches_an_edited_candidates_file(self):
        """逐檔指紋的**雜湊比對**那一段要有人證明過它會紅。

        `candidates.csv` 的內容現在另有 `candidates_match_result` 與 `ballot_numbers`
        兩道綁著，所以這支不再是「那個檔的唯一防線」——
        它現在不可取代的理由是：全套測試裡只有它斷言過一條 `file:*` 是 FAIL，
        也就是只有它證明得了那段雜湊比對不是恆真的。
        """
        code, out = self._tamper_and_verify(
            'candidates.csv',
            lambda text: text + 'director,9,999999,X999,冒名者,write_in,99,1,elected\n')
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'file:candidates.csv', 'FAIL')

    def test_verify_script_catches_a_deleted_digest_table(self):
        """把 `digests.txt` 的整張 `files` 表刪掉——九項逐檔檢查要**不能**無聲消失。

        原本那個迴圈只走這張表，表不在就跑零次：抗辯實跑把整個鍵刪掉，
        檢查項從 24 掉到 15、退出碼 0、一行 FAIL 都沒有。
        """
        def mutate(text):
            digests = json.loads(text)
            digests.pop('files', None)
            return json.dumps(digests, ensure_ascii=False)

        code, out = self._tamper_and_verify('digests.txt', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'files_present', 'FAIL')

    def test_verify_script_catches_a_file_hidden_in_a_subfolder(self):
        """**子目錄不能是藏東西的地方。**

        原本只掃頂層，`mkdir 公會官方文件 && cp … 正式公告.pdf` 完全隱形、
        全綠通過（抗辯實測）——而這道檢查的設計目的正是「不讓人塞一份
        看起來像官方文件的東西進來」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            hidden = Path(folder) / '公會官方文件'
            hidden.mkdir()
            (hidden / '正式公告.txt').write_text('本會宣布由冒名者當選', encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')
            self.assertIn('正式公告.txt', proc.stdout, 'FAIL 要講清楚是哪個檔')

    def test_verify_script_survives_a_write_in_only_election(self):
        """**零登記候選人、全靠名單外得票**的場次是合法的（§6 明文），不可以誤報。

        原本姓名檢查用 `bool(frozen_names)` 防恆真，而那種場次的
        `ballot_ready` payload 裡候選人清單是空的 → 合法的封存包直接 FAIL。
        假警報比漏報更糟：監票員從此不信這份驗算。
        """
        self.election.candidate_ids.unlink()
        self.election.draw_entropy = '5-5-5'      # 零候選人也可以填亂數，這是合法組合
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A01')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.election.action_publish()
        self.election.action_build_archive()
        blob = self.election.sudo()._archive_blob()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             '全靠 write-in 的合法場次不可以驗不過：%s' % proc.stdout)
            self.assertCheck(proc.stdout, 'names_match_roster', 'OK')
            # **號次抽籤那一項也要過**：`action_ready` 只要填了亂數就回報
            # `draw_method='system'`、`ballot_numbers=[]`，而原本的判準是
            # 「號次不能是空的」→ 系統自己產的真封存包被自己判 FAIL、退出碼 1
            # （第五輪抗辯實跑）。這與姓名那一項是同一個洞，當時沒有掃過來。
            self.assertCheck(proc.stdout, 'draw', 'OK')
            # **姓名對凍結清單那一項一位都沒比到，但這個包有 `roster_digest`**：姓名由
            # 逐列摘要與名次表比對釘住，零比對不是空真 → OK（使用者 2026-10-20 裁決；
            # 第五輪曾判 N/A，結果同一份輸出一邊說「不適用、可能被拿掉」一邊說「都釘住」）。
            self.assertCheck(proc.stdout, 'names_match_frozen_candidates', 'OK')
            self.assertIn('票匭與當選名單都釘住', proc.stdout)
            self.assertNotIn('當選人是誰  ——', proc.stdout)

    def test_verify_script_survives_a_vacant_seat(self):
        """**席位從缺是合法結果**，不可以被判成竄改。

        §6 允許零登記候選人；全體投空白就是該席次從缺——線上完全放行、
        照樣產包。而原本 `ranking` 對空的名次表一律判 FAIL，
        於是系統自己產的合法封存包被自己的驗算說「被動過」
        （第六輪抗辯造了三場真場次實跑）。
        這與已修的「零登記但有 write-in 得票」是同一個 L3 教訓的姊妹案例：
        當初只補了有得票那一半。
        """
        # 監事沒有人登記，全體投空白 → 監事席次從缺
        self.election.candidate_ids.filtered(lambda c: c.office == 'supervisor').unlink()
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[])
        self._cast('A02', director=[m('A02')], supervisor=[])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.election.action_publish()
        self.election.action_build_archive()
        self.assertEqual(
            self.election.result_json['offices']['supervisor']['ranking'], [],
            '監事應該是從缺（名次表空的）')
        blob = self.election.sudo()._archive_blob()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             '席位從缺的合法封存包不可以驗不過：%s' % proc.stdout)
            self.assertCheck(proc.stdout, 'ranking', 'OK')
            self.assertCheck(proc.stdout, 'candidates_match_result', 'OK')

    def test_verify_script_catches_a_renamed_write_in_winner(self):
        """名單外得票（write-in）的當選人改名也要抓得到。

        那種人**不在** `ballot_ready` 的候選人清單裡，只綁凍結名冊的話沒有人管得到他。
        改綁 `roster.csv`（被 `roster_final_digest` 錨在鏈上，而且涵蓋每一位選舉人）
        才蓋得住。測試一定要挑沒登記的那一位——挑有登記的會被凍結名冊那條先抓到，
        對應的 mutant 就存活了（實跑踩過）。
        """
        self._open()
        m = self._mid
        # A06 是合格會員但沒登記候選人：給他票就是 write-in
        self._cast('A01', director=[m('A06')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A06')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.election.action_publish()
        self.election.action_build_archive()
        write_in = self.members['A06']
        frozen = self.election.log_ids.filtered(
            lambda log: log.payload.get('to') == 'ballot_ready').payload['candidates']
        self.assertFalse([item for item in frozen if write_in.member_no in item],
                         'A06 必須不在凍結名冊的候選人清單裡，否則測不到這件事')

        def mutate(text):
            data = json.loads(text)
            for row in data['offices']['director']['ranking']:
                if row['member_id'] == write_in.id:
                    row['name'] = '冒名者'
            return json.dumps(data, ensure_ascii=False)

        blob = self.election.sudo()._archive_blob()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'result.json'
            path.write_text(mutate(path.read_text(encoding='utf-8')), encoding='utf-8')
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            digests['files']['result.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
            digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'names_match_roster', 'FAIL')

    def test_verify_script_reports_broken_shapes_as_a_clean_fail(self):
        """資料**形狀**壞掉（不是 JSON 解不開）也要印得出看得懂的 FAIL。

        原本只擋 parse：`files` 是字串、`result.json` 是陣列、`log.csv` 少一欄
        都會直接吐 traceback、一行 FAIL 都沒有（抗辯實跑五種）。
        而且原本守它的那句斷言查的是 **stdout**，Python 的 traceback 走 **stderr**
        ——那句在任何情況下都不會紅（本專案第八次「測試瞄錯地方」）。
        """
        def to_string(text):
            digests = json.loads(text)
            digests['files'] = '不是字典'
            return json.dumps(digests, ensure_ascii=False)

        blob = self.build()
        for filename, mutate in (('digests.txt', to_string),
                                 ('result.json', lambda text: '[]'),
                                 ('log.csv', lambda text: 'seq\n1\n')):
            with tempfile.TemporaryDirectory() as folder:
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    archive.extractall(folder)
                path = Path(folder) / filename
                encoding = 'utf-8-sig' if filename.endswith('.csv') else 'utf-8'
                path.write_text(mutate(path.read_text(encoding=encoding)), encoding=encoding)
                proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                      capture_output=True, text=True, timeout=120)
                self.assertNotEqual(proc.returncode, 0, filename)
                self.assertNotIn('Traceback', proc.stderr,
                                 '%s 讓腳本吐 traceback 而不是 FAIL' % filename)
                self.assertIn('FAIL', proc.stdout, '%s 沒有印出任何 FAIL' % filename)

    def test_verify_script_catches_a_ghost_candidate_row(self):
        """在 `candidates.csv` 追加一列「幽靈當選人」——要驗不過。

        `candidates_match_result` 原本對 `result.json` 裡沒有的鍵直接 `continue`
        （為了放過「退選又零票」的人），於是追加一列 rank1 elected 連看都不看
        （抗辯實跑：24 項全綠）。多出來的列只允許是退選且零票。
        """
        code, out = self._tamper_and_verify(
            'candidates.csv',
            lambda text: text + 'director,9,999999,Z99,幽靈理事,confirmed,99,1,elected\n',
            relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'candidates_match_result', 'FAIL')

    def test_verify_script_fails_cleanly_on_broken_json(self):
        """`result.json` 壞掉要印出看得懂的 FAIL，不要吐 traceback。

        監票員多半不是工程師；一個 traceback 與「驗不過」在他眼裡是同一件事，
        但他沒辦法判斷是資料被動過還是工具壞了。
        """
        code, out = self._tamper_and_verify('result.json', lambda text: '{壞掉的 JSON')
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'data_shape', 'FAIL')
        self.assertNotIn('Traceback', out)

    def test_verify_script_catches_a_deleted_file(self):
        """把檔案連同它在 `digests.txt` 的那一列一起刪掉，也要驗不過。

        逐檔指紋那個迴圈只走 `digests.txt` 列出來的項目——刪檔又刪列，
        一行 FAIL 都不會有（抗辯實測）。所以另外要求「該有的檔都在」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            (Path(folder) / 'receipts.csv').unlink()
            path = Path(folder) / 'digests.txt'
            digests = json.loads(path.read_text(encoding='utf-8'))
            digests['files'].pop('receipts.csv', None)
            path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')

    def test_verify_script_binds_ballot_numbers_to_the_chain(self):
        """號次被改掉要驗不過，而且**連指紋一起改**也一樣。

        號次凍結名冊時就寫進稽核鏈了，所以 candidates.csv 上的號次
        有一個獨立於這個檔的基準可以比。
        """
        self.election.draw_entropy = '3-1-4-1-5'

        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            rows[1][1] = str(int(rows[1][1] or 0) + 7)      # 把第一位候選人的號次改掉
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('candidates.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballot_numbers', 'FAIL')

    def test_verify_script_recomputes_the_draw(self):
        """系統抽籤的結果要能用同一條公式重算出來（`draw` 這一項）。"""
        self.election.draw_entropy = '3-1-4-1-5'
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr[-500:])
            self.assertCheck(proc.stdout, 'draw', 'OK')
            self.assertIn('3-1-4-1-5', proc.stdout, '亂數要印出來給監票員比對紙本')

    def test_verify_script_recomputes_who_was_elected(self):
        """**線上把名次算錯，離線要抓得到。**

        只重算票數是不夠的：票數全對、名次算錯（程式 bug，或有人在伺服器上動手腳）
        照樣全綠。抗辯代理實跑過——把線上的排名反轉，1 票的人當選、4 票的人落選，
        `_verify_chain()` 回 True、離線驗算 20 項全 OK、退出碼 0。
        而排名需要的東西全都在已錨定的 `result.json` 裡（得票、名額、選票摘要、
        同票亂數），所以重算完全做得到，只是原本沒做。

        做法：把**線上**的排名函式換成「倒過來」。鏈會忠實記下那個錯的結果，
        所以鏈、摘要、票數統計全部都會是對的——只有 `ranking` 這一項該紅。
        """
        honest_rank = verify_core.rank_office        # 先抓原件，否則 patch 之後會無限遞迴

        def reversed_rank(entrants, votes, seats, alternates, digest, office, entropy):
            ranked, ties = honest_rank(entrants, votes, seats, alternates,
                                       digest, office, entropy)
            return list(reversed(ranked)), ties

        with patch.object(verify_core, 'rank_office', reversed_rank):
            blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'ranking', 'FAIL')
            # 鏈與票數都沒被動過：抓到的就是「名次與票數對不起來」這一件事
            self.assertCheck(proc.stdout, 'chain', 'OK')
            self.assertCheck(proc.stdout, 'recount', 'OK')
            self.assertCheck(proc.stdout, 'result_digest', 'OK')

    def test_verify_script_prints_the_whole_chain_for_paper_comparison(self):
        """監票員在會場抄下的鏈頭**不會**等於包裡的鏈頭。

        大螢幕顯示的是投票當下的鏈頭，而封存包是公告之後才做的，中間隔了好幾筆。
        原本只印包裡那一個值，監票員拿紙本一對永遠對不上——唯一的包外錨點
        等於形同虛設（抗辯實測：螢幕給 seq2/3/4、包裡印 seq6、後台顯示 seq7）。
        整條鏈已經逐筆重算過，所以印出 seq→雜湊對照表讓人去找就夠了。
        """
        # 先抓再建包：`archive_built` 是在 zip 做好**之後**才入鏈的，
        # 它本來就不可能出現在自己描述的那一包裡（雞生蛋）
        self.run_to_counted()
        self.election.action_publish()
        heads = [log.entry_hash[:16] for log in self.election.log_ids.sorted('seq')]
        self.election.action_build_archive()
        blob = self.election.sudo()._archive_blob()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            for head in heads:
                self.assertIn(head, proc.stdout,
                              '每一筆的雜湊都要印出來，監票員才找得到自己抄的那一串')

    def _reforge_tail(self, folder, mutate_result, mutate_payload=None):
        """保留鏈的前段、**重鑄 counted 與 published 兩筆**。

        這是有資料庫權限的人真正會做的事：監票員在投票進行中抄下的鏈頭
        （`open` 那一筆）原封不動，他只要以最後一筆「✘」的雜湊為 prev
        往後重接，`verify_chain` 照樣首尾相接。兩個抗辯代理各自實跑複現過。
        """
        path = Path(folder) / 'log.csv'
        rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        header, body = rows[0], rows[1:]
        keep = [row for row in body
                if json.loads(row[4]).get('to') not in ('counted', 'published')]
        prev = keep[-1][6]
        result_path = Path(folder) / 'result.json'
        data = json.loads(result_path.read_text(encoding='utf-8'))
        mutate_result(data)
        result_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        for row in body[len(keep):]:
            payload = json.loads(row[4])
            if payload.get('to') == 'counted':
                payload['result_digest'] = verify_core.result_digest(data)
                if mutate_payload:
                    mutate_payload(payload)
            row[4] = verify_core.canonical_json(payload)
            row[5] = prev
            row[6] = verify_core.chain_hash(
                self.election.uuid, int(row[0]), row[1], int(row[2]), row[3], payload, prev)
            prev = row[6]
            keep.append(row)
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator='\n').writerows([header] + keep)
        path.write_text(buffer.getvalue(), encoding='utf-8-sig')
        digests_path = Path(folder) / 'digests.txt'
        digests = json.loads(digests_path.read_text(encoding='utf-8'))
        digests['chain_head'] = prev
        for name in ('log.csv', 'result.json'):
            digests['files'][name] = hashlib.sha256(
                (Path(folder) / name).read_bytes()).hexdigest()
        digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
        proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                              capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout

    def _rebuild_chain(self, folder, transform, digests_update=None):
        """讓 transform 重排／增刪鏈上的列，然後**整條重算雜湊**再跑驗算。

        `_append_transitions` 只能加在尾巴，而加在尾巴一定會同時打壞
        「published 必須是最後一筆」——於是想單獨驗「狀態重複」的測試
        會被別的子句先擋下來，那條 mutant 就假存活（第八輪實際踩到）。
        這支讓攻擊者能在鏈**中間**動手腳，跟真正有 DB 權限的人一樣。
        """
        path = Path(folder) / 'log.csv'
        rows_in = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        header, body = rows_in[0], transform(rows_in[1:])
        prev = verify_core.sha256_hex(self.election.uuid)
        for seq, row in enumerate(body, start=1):
            payload = json.loads(row[4])
            row[0] = str(seq)
            row[4] = verify_core.canonical_json(payload)
            row[5] = prev
            row[6] = verify_core.chain_hash(self.election.uuid, seq, row[1], int(row[2]),
                                            row[3], payload, prev)
            prev = row[6]
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator='\n').writerows([header] + body)
        path.write_text(buffer.getvalue(), encoding='utf-8-sig')
        digests_path = Path(folder) / 'digests.txt'
        digests = json.loads(digests_path.read_text(encoding='utf-8'))
        digests['chain_head'] = prev
        digests['chain_length'] = len(body)
        # **會重算摘要的竄改者也會改 digests.txt**：只改鏈上那幾個值的話，
        # `digests_match_chain` 先紅，測到的是那一道、不是呼叫端要驗的事——
        # 第六輪的整組對調測試就是這樣，攻擊包其實是 FAIL 包（第七輪 skeptic）。
        digests.update(digests_update or {})
        digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
        self._relabel(folder, ['log.csv'])
        proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                              capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout

    def _append_transitions(self, folder, payloads, mutate_result=None, action='state_change'):
        """在鏈尾**追加**紀錄（不動既有的任何一筆）。

        這是第四輪兩個抗辯代理各自獨立找到的攻擊：監票員抄的 `published` 雜湊
        位元組不變、照樣出現在表裡、照樣標 ✔，但腳本取基準時用的是
        「最後一筆 counted／ballot_ready」，於是追加就能讓基準整個易主。
        而且不必手改 zip——線上流程（改票→重算→`_append`→按產生封存包）
        自己就做得出這樣一包，因為線上的 `_verify_chain()` 也取最後一筆。
        """
        path = Path(folder) / 'log.csv'
        rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        header, body = rows[0], rows[1:]
        prev, seq = body[-1][6], int(body[-1][0])
        if mutate_result:
            result_path = Path(folder) / 'result.json'
            data = json.loads(result_path.read_text(encoding='utf-8'))
            mutate_result(data)
            result_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        for payload in payloads:
            seq += 1
            row = [str(seq), body[-1][1], body[-1][2], action,
                   verify_core.canonical_json(payload), prev, '']
            row[6] = verify_core.chain_hash(self.election.uuid, seq, row[1], int(row[2]),
                                            action, payload, prev)
            prev = row[6]
            body.append(row)
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator='\n').writerows([header] + body)
        path.write_text(buffer.getvalue(), encoding='utf-8-sig')
        digests_path = Path(folder) / 'digests.txt'
        digests = json.loads(digests_path.read_text(encoding='utf-8'))
        for name in ('log.csv', 'result.json'):
            digests['files'][name] = hashlib.sha256(
                (Path(folder) / name).read_bytes()).hexdigest()
        digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
        proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                              capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout

    def test_verify_script_catches_an_appended_counted_entry(self):
        """**往鏈尾追加**一筆 `counted` 就能換掉當選名單——要驗不過。

        這一條前三輪全部漏掉：我用「第一筆」畫 ✔、卻用「最後一筆」當基準。
        攻擊者不必改動任何既有紀錄，監票員抄的 published 雜湊位元組不變、
        照樣標 ✔，而所有摘要的基準已經換成追加的那一筆（兩個抗辯代理各自實跑：
        24 項全綠、退出碼 0、當選人被掉包）。
        擋法是「每個狀態只能出現一次，而且 published 必須是最後一筆」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def swap_winner(data):
                ranking = data['offices']['director']['ranking']
                ranking[0]['result'], ranking[-1]['result'] = (
                    ranking[-1]['result'], ranking[0]['result'])

            # **追加 counted 之後要把 published 也補上**，否則「published 必須是最後
            # 一筆」那道會先擋下來，測不到「基準取的是唯一那一筆還是最後一筆」
            # （實跑發現這樣寫會讓對應的 mutant 存活）。真的攻擊者當然會補。
            forged = dict(self.election.log_ids.filtered(
                lambda log: log.payload.get('to') == 'counted').payload)
            tail = dict(self.election.log_ids.filtered(
                lambda log: log.payload.get('to') == 'published').payload)
            code, out = self._append_transitions(folder, [forged, tail], swap_winner)
            self.assertNotEqual(code, 0, out)
            self.assertCheck(out, 'chain_complete', 'FAIL')
            # 鏈仍然首尾相接、published 仍然是最後一筆——抓到的是「同一個狀態出現兩次」
            self.assertCheck(out, 'chain', 'OK')

    def test_verify_script_catches_anything_appended_after_published(self):
        """`published` 之後不可以再有紀錄。

        追加的若不是重複狀態（例如再接一筆 `cancelled`），「每個狀態只能出現一次」
        那道擋不到——但錨點之後還能往下接，本身就代表這包不是公告當下的那一份。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            code, out = self._append_transitions(
                folder, [{'from': 'published', 'to': 'cancelled'}])
            self.assertNotEqual(code, 0, out)
            self.assertCheck(out, 'chain_complete', 'FAIL')
            self.assertCheck(out, 'chain', 'OK')

    def test_online_chain_verification_rejects_a_duplicated_state(self):
        """線上的 `_verify_chain()` 也要擋重複狀態。

        不擋的話**系統自己**會蓋章產出偽造包：有伺服器權限的人改票、用模組自己的
        函式重算、`_append` 追加兩筆、按下「產生封存包」——而 `action_build_archive`
        會先驗鏈，驗過才做（抗辯實跑複現整條路徑）。
        """
        self.run_to_counted()
        self.election.action_publish()
        self.assertTrue(self.election._verify_chain(), '正常的鏈要驗得過')
        # **追加的要是重複的 `published`**：追加 counted 的話，
        # 「最後一筆必須等於目前狀態」那條會先擋下來，隔離不到重複狀態這一條
        # （實跑發現那樣寫會讓對應的 mutant 存活）。
        published = self.election.log_ids.filtered(
            lambda log: log.payload.get('to') == 'published')
        self.env['assoc.election.log'].sudo()._append(
            self.election, 'state_change', dict(published.payload))
        self.assertFalse(self.election._verify_chain(), '重複的狀態要驗不過')
        with self.assertRaises(UserError):
            self.election.action_build_archive()

    def test_verify_script_catches_a_forged_seat_count(self):
        """重鑄鏈之後把**應選名額**改大，讓候補變當選——要驗不過。

        名額是在凍結名冊（`ballot_ready`）那一筆入鏈的，而那一筆**在監票員抄鏈頭之前**，
        所以連重造鏈的人也動不了它。原本 `ranking` 用 `result.json` 自己的 seats 重算
        （又是拿被驗物件當基準）：只把 seats 由 3 改成 4 再重鑄 counted／published，
        1 票的人就從候補變當選而 24 項全綠（抗辯實跑）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def bump_seats(data):
                # **攻擊者不會只改名額**——他改名額就是為了讓某個人變成當選，
                # 所以標籤也要一起改。只改名額的話 `ranking` 自己仍然自洽，
                # 測不出「名次是用哪一份名額算的」（實跑發現 mutant 存活）。
                office = data['offices']['director']
                office['seats'] += 1
                promoted = [row for row in office['ranking']
                            if row['result'] == 'alternate']
                self.assertTrue(promoted, '要有候補才示範得了「候補變當選」')
                promoted[0]['result'] = 'elected'

            code, out = self._reforge_tail(folder, bump_seats)
            self.assertNotEqual(code, 0, out)
            self.assertCheck(out, 'seats_match_frozen_roster', 'FAIL')
            # 名次也要紅：它必須用**凍結名冊那一筆**的名額重算，
            # 而不是用 result.json 自己寫的（那是被驗的物件）
            self.assertCheck(out, 'ranking', 'FAIL')
            # 鏈本身是接得起來的——這正是重點：抓到的不是鏈，是名額
            self.assertCheck(out, 'chain', 'OK')

    def test_verify_script_catches_a_forged_candidate_name(self):
        """重鑄鏈之後把當選人的**姓名**換掉——要驗不過。

        姓名同樣在凍結名冊那一筆入鏈。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def rename_winner(data):
                data['offices']['director']['ranking'][0]['name'] = '冒名者'

            code, out = self._reforge_tail(folder, rename_winner)
            self.assertNotEqual(code, 0, out)
            self.assertCheck(out, 'names_match_roster', 'FAIL')
            self.assertCheck(out, 'chain', 'OK')

    def test_verify_script_catches_a_renamed_winner_even_when_the_roster_agrees(self):
        """連名冊一起改名、摘要也一起重算——**凍結名冊那一筆**還是會紅。

        第七輪我為此加了「當選人姓名也要對回 `ballot_ready` 的候選人清單」那半段，
        第八輪 simplifier 證明它是 `roster_count_matches_freeze` 的真子集：
        那一項比的是 `roster.csv` 正規化後的摘要對 **`ballot_ready`** 的
        `roster_digest`，而姓名是 `roster_line` 的欄位之一、涵蓋每一位選舉人。
        所以那半段已刪；這支測試改成**證明包含關係**——同一個攻擊，
        抓到它的是凍結名冊那一項。
        （教訓：我當時的 mutant 紅了，但紅的理由是「我指名的那一項變 OK」，
        不是「監票員會被騙」——L2 的反向形狀。）
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            data = json.loads((Path(folder) / 'result.json').read_text(encoding='utf-8'))
            target = data['offices']['director']['ranking'][0]['member_id']
            forged = '冒名者'

            roster_path = Path(folder) / 'roster.csv'
            roster_rows = list(csv.DictReader(io.StringIO(
                roster_path.read_text(encoding='utf-8-sig'))))
            hit = [row for row in roster_rows if int(row['member_id']) == target]
            self.assertTrue(hit, '當選人必須在名冊裡，否則這個測試沒測到東西')
            for row in hit:
                row['name'] = forged
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(roster_rows[0]),
                                    lineterminator='\n')
            writer.writeheader()
            writer.writerows(roster_rows)
            roster_path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            # 竄改者會把名冊摘要一起重算：塞回鏈上那一筆，也塞回 digests.txt
            new_digest = verify_core.roster_digest([
                verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                        row['state'], row['voted_at'])
                for row in roster_rows])
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            digests['roster_final_digest'] = new_digest
            digests_path.write_text(json.dumps(digests, ensure_ascii=False),
                                    encoding='utf-8')
            self._relabel(folder, ['roster.csv'])

            code, out = self._reforge_tail(
                folder,
                lambda result: result['offices']['director']['ranking'][0].update(name=forged),
                mutate_payload=lambda payload: payload.update(
                    roster_final_digest=new_digest))
        self.assertNotEqual(code, 0, out)
        # 竄改者把 counted 那一筆的名冊摘要改對了，所以 roster_digest 是綠的……
        self.assertCheck(out, 'roster_digest', 'OK')
        # ……但 ballot_ready 那一筆在紙本錨點之前，改不動
        self.assertCheck(out, 'roster_count_matches_freeze', 'FAIL')
        self.assertCheck(out, 'chain', 'OK')

    def test_verify_script_says_which_chain_entries_protect_the_result(self):
        """**鏈頭只保護「那一筆以前」**，所以要逐筆標明哪幾筆算數。

        監票員在投票進行中抄的是 `open` 那一筆，而「誰當選」在 `counted` 才產生——
        永遠在紙本之後。保留前段、只重鑄 counted 與 published 兩筆就能換掉當選人
        （兩個抗辯代理各自實跑複現），而監票員抄的那一串照樣出現在表裡。
        所以不能只說「找到就好」：開票之前的那幾筆要明白標成「證明不了當選名單」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout)
        marks = {}
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == 'seq' and '←' in line:
                marks[parts[2]] = line.split('←', 1)[1].strip()
        before = '只證明開票之前的流程，**證明不了誰當選**'
        self.assertEqual(marks.get('ballot_ready'), before)
        self.assertEqual(marks.get('open'), before, '投票中抄的鏈頭釘不住結果')
        # **關票那一筆也只算「之前」。** 第八輪曾給它一層「票匭釘住」，
        # 第九輪撤回：實跑證明保留 seq1–5 不動、只重鑄 counted/published，
        # 就能改寫「誰投了票」與全部收據碼而關票鏈頭逐字元相同；
        # 承辦甚至可以在關票**之後**刪票。關票保證得了的不比投票中那幾筆多。
        self.assertEqual(marks.get('closed'), before,
                         '關票那一筆保證不了票匭：事後刪票鏈頭照樣吻合')
        self.assertEqual(marks.get('counted'), '票匭與當選名單都釘住')
        self.assertEqual(marks.get('published'), '票匭與當選名單都釘住')

    def test_archive_build_does_not_move_the_chain_head(self):
        """**產生封存包不可以讓鏈頭前進**。

        它曾經是鏈上的一筆，於是系統裡顯示的鏈頭（含 archive_built）與封存包裡印的
        （只到 published）永遠差一筆——監票員照指示抄下螢幕上的值，回家一對就被
        腳本告知「中間被換過」。每重建一次封存包再差一筆（抗辯實測）。
        軌跡改記在稽核表，那本來就是它的用途。
        """
        self.run_to_counted()
        self.election.action_publish()
        head_before = self.election.log_ids.filtered('is_head').entry_hash
        length_before = len(self.election.log_ids)
        self.election.action_build_archive()
        self.assertEqual(self.election.log_ids.filtered('is_head').entry_hash, head_before)
        self.assertEqual(len(self.election.log_ids), length_before)
        self.election.action_build_archive()      # 重建也一樣
        self.assertEqual(len(self.election.log_ids), length_before)
        trail = self.env['assoc.audit.log'].sudo().search(
            [('action', '=', 'archive_build')], limit=1, order='id desc')
        self.assertTrue(trail, '軌跡要留在稽核表')
        self.assertEqual(trail.detail.get('election_id'), self.election.id)

    def test_verify_script_catches_a_stuffed_roster(self):
        """名冊凍結後偷加選舉人再補票——要驗不過。

        **摘要只證明「這份資料沒被改」，不證明「沒有被加進來」**：雜湊是對最終狀態
        算的，所以偷加人之後每個摘要都會重新算得漂漂亮亮（第五輪抗辯實跑：
        26 項全綠、退出碼 0、候補變當選）。拆穿它的數字就躺在鏈上——
        凍結那一筆記了 `roster_count` 與凍結當下的 `roster_digest`。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'roster.csv'
            text = path.read_text(encoding='utf-8-sig')
            path.write_text(text + '999999,Z99,人頭,eligible,\n', encoding='utf-8-sig')
            self._relabel(folder, ['roster.csv'])
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'roster_count_matches_freeze', 'FAIL')

    def test_verify_script_catches_a_forged_voted_flag(self):
        """把沒來的人標成「已投票」再補票——要驗不過。

        這個變體躲得過列數檢查（列數沒變），但「投了幾票」有三個獨立來源：
        鏈上 counted 那一筆的 `voted`、名冊標 voted 的列數、收據碼張數。
        收據碼與 `state='voted'` 是同一句 UPDATE 寫的，是硬不變量。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'roster.csv'
            rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
            flipped = False
            for row in rows[1:]:
                if row[3] != 'voted':
                    row[3] = 'voted'
                    flipped = True
                    break
            self.assertTrue(flipped, '要有沒投票的人才示範得了')
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            self._relabel(folder, ['roster.csv'])
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'voted_count_agrees', 'FAIL')

    def test_verify_script_catches_extra_ballots(self):
        """選票張數必須等於投票人數 × 職位數（線上開票前就斷言的那一條）。"""
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'ballots_plain.csv'
            text = path.read_text(encoding='utf-8-sig')
            path.write_text(text + 'director,%s,valid,\n' % self._mid('A01'),
                            encoding='utf-8-sig')
            self._relabel(folder, ['ballots_plain.csv'])
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'ballot_count_agrees', 'FAIL')

    def test_verify_script_catches_a_ballot_the_result_owns_up_to(self):
        """多塞一張票、**連 result.json 的統計與鏈上摘要一起改**——仍然要驗不過。

        既有的 `catches_extra_ballots` 沒有更新 result.json，於是被「分項對不上」
        那一句擋下來；真正比對「每個職位的張數 == 投票人數」的那一句，
        從來沒有人證明過它會失敗（第七輪把 mutant 拆開才看見）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            path = Path(folder) / 'ballots_plain.csv'
            path.write_text(path.read_text(encoding='utf-8-sig') + 'director,,invalid,blank\n',
                            encoding='utf-8-sig')
            self._relabel(folder, ['ballots_plain.csv'])
            ballot_rows = list(csv.DictReader(io.StringIO(
                path.read_text(encoding='utf-8-sig'))))
            digest = verify_core.ballots_digest(self.election.uuid, [
                (row['office'], [int(one) for one in row['choices'].split() if one],
                 row['status']) for row in ballot_rows])

            def own_up(data):
                block = data['offices']['director']
                block['invalid_ballots'] = (block['invalid_ballots'] or 0) + 1
                reasons = dict(block.get('invalid_reasons') or {})
                reasons['blank'] = reasons.get('blank', 0) + 1
                block['invalid_reasons'] = reasons

            code, out = self._reforge_tail(
                folder, own_up,
                mutate_payload=lambda payload: payload.update(ballots_digest=digest))
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'ballots_digest', 'OK')       # 摘要已被一起改過
        self.assertCheck(out, 'ballot_status', 'OK')        # 那張空白票本身是合法形狀
        self.assertCheck(out, 'ballot_count_agrees', 'FAIL')

    def test_verify_script_catches_a_tampered_chain_length(self):
        """`digests.txt` 說的鏈長要等於實際筆數。

        它是那個檔裡唯一能獨立顯示「鏈被砍尾」的欄位，而原本完全沒人比對
        （第六輪抗辯實跑：那個檔的六個欄位全改仍 30 項全綠）。
        """
        def mutate(text):
            digests = json.loads(text)
            digests['chain_length'] = 999
            return json.dumps(digests, ensure_ascii=False)

        code, out = self._tamper_and_verify('digests.txt', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'digests_match_chain', 'FAIL')

    def test_verify_script_catches_a_tampered_chain_head(self):
        """`chain_head` 這一項也要有人證明過它會紅。

        全套測試原本沒有任何一支斷言它 FAIL、66 條 mutation 也沒有一條打它——
        **沒有人證明過它會紅**，正是我自己寫在 L1 的「驗收閘恆真」形狀
        （第五輪 simplifier 指出）。
        """
        def mutate(text):
            digests = json.loads(text)
            digests['chain_head'] = 'f' * 64
            return json.dumps(digests, ensure_ascii=False)

        code, out = self._tamper_and_verify('digests.txt', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'chain_head', 'FAIL')

    def test_verify_script_catches_a_file_hidden_as_a_nested_digests(self):
        """子目錄裡叫 `digests.txt` 的檔不可以隱形。

        排除條件原本比的是**檔名**不是相對路徑，於是每個子目錄都能藏一個檔
        （第五輪兩個抗辯代理各自實跑：26 項全綠）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            hidden = Path(folder) / '公會正式公告'
            hidden.mkdir()
            (hidden / 'digests.txt').write_text('偽造的公告', encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')

    def test_verify_script_catches_a_reissue_tail_pretending_to_be_published(self):
        """追加一筆 `action='reissue'` 但 payload 寫 `to: published` 也要擋。

        「published 必須是最後一筆」原本只看 payload 的標籤、不看 `action`
        （第五輪兩個代理各自實跑：26 項全綠，✔ 表格還把它印成第二筆 published）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            code, out = self._append_transitions(
                folder, [{'to': 'published', 'note': '尾巴垃圾'}], action='reissue')
            self.assertNotEqual(code, 0, out)
            self.assertCheck(out, 'chain_complete', 'FAIL')

    def test_verify_script_catches_an_escaping_digest_key(self):
        """指紋表的鍵是竄改者控制的，不可以拿去組路徑就讀。

        `HERE / '/etc/hostname'` 會直接跳出封存包資料夾（pathlib 對絕對路徑的行為），
        指到 `/dev/zero` 還會讓 `read_bytes()` 一路吃記憶體（第五輪抗辯實跑）。
        M13 第五輪起守衛改成「只讀檔案清單上的名字」（符號連結也跟著讀，見
        `test_an_off_list_entry_in_the_fingerprint_table_is_never_read`）。
        """
        def mutate(text):
            digests = json.loads(text)
            digests['files']['/etc/hostname'] = 'f' * 64
            return json.dumps(digests, ensure_ascii=False)

        code, out = self._tamper_and_verify('digests.txt', mutate)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'file:/etc/hostname', 'FAIL')
        self.assertIn('封存包檔案清單以外的檔', out)

    def test_verify_script_refuses_an_injected_module(self):
        """封存包裡多一支 `csv.py` 就能劫持驗算器——要擋下來。

        腳本在**被驗的資料夾**裡執行，而那就是 `sys.path[0]`。塞一支 `csv.py`
        遮蔽標準庫，就能改寫 `builtins.print`（把 FAIL 換成 OK）與 `sys.exit`，
        而 `log.csv`／`verify_core.py`／`verify_digest.py` 位元組完全不動——
        紙本鏈頭與兩個公布指紋全部吻合，30 項全 OK、退出碼 0，當選人被對調
        （第六輪抗辯實跑）。兩道防線：`sys.path` 先拔掉自己的資料夾、
        檔案清單改成白名單（多一個檔就是多一個，登記在指紋表裡也不行）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            (Path(folder) / 'csv.py').write_text(
                'import builtins\n'
                '_real = builtins.print\n'
                'builtins.print = lambda *a, **k: _real(\n'
                '    *[str(x).replace("FAIL ", "OK   ") for x in a], **k)\n',
                encoding='utf-8')
            self._relabel(folder, ['csv.py'])       # 竄改者當然會登記進去
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')
            self.assertIn('csv.py', proc.stdout, 'FAIL 要指名是哪個檔')
            # 而且它不可以真的被載入——被載入的話 print 會被改寫、FAIL 會消失
            self.assertIn('FAIL', proc.stdout, '注入的模組似乎生效了')

    def test_verify_script_ignores_a_poisoned_pycache(self):
        """`__pycache__` 裡放一份惡意 bytecode 也不能生效。

        保持 `verify_core.py` 位元組不變、另附標頭對齊的 .pyc，CPython 會直接用
        那份 bytecode 而不回讀 .py——**指紋對得上，跑的卻不是那份程式碼**。
        修法是不用 `import`，改成讀原始位元組 `compile()` 後執行。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            # **要造一份有效的 pyc**：隨便寫幾個位元組的話 CPython 會因為
            # magic 不符直接拒絕、回頭讀 .py——那樣測試什麼都沒證明。
            # 標頭＝magic(4)＋flags(4)＋mtime(4)＋size(4)，對齊那份 .py 才會被採用。
            source_path = Path(folder) / 'verify_core.py'
            stat = source_path.stat()
            poisoned = compile(
                "exec(open('verify_core.py').read())\n"
                "print('POISONED-PYC-RAN')\n", str(source_path), 'exec')
            header = (importlib.util.MAGIC_NUMBER
                      + struct.pack('<III', 0, int(stat.st_mtime) & 0xFFFFFFFF,
                                    stat.st_size & 0xFFFFFFFF))
            cache = Path(folder) / '__pycache__'
            cache.mkdir()
            (cache / ('verify_core.%s.pyc' % sys.implementation.cache_tag)).write_bytes(
                header + marshal.dumps(poisoned))
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotIn('POISONED-PYC-RAN', proc.stdout,
                             '__pycache__ 裡的 bytecode 被採用了')
            self.assertNotIn('Traceback', proc.stderr, proc.stderr[-400:])
            self.assertCheck(proc.stdout, 'files_present', 'FAIL')
            self.assertCheck(proc.stdout, 'chain', 'OK')

    def test_verify_script_sanitises_names_before_printing(self):
        """姓名含換行不可以偽造印出來的當選名單。

        那個姓名一路**誠實地**進名冊摘要、結果摘要與稽核鏈，所以每一項檢查都是綠的；
        但印出來的權威名單會多一列幽靈當選人（第六輪抗辯實跑：30/30 OK、退出碼 0）。
        摘要仍然用原值算，**只有顯示要消毒**。
        原本守它的斷言是 `assertIn(姓名, stdout)`——注入的字串本身就包含那個姓名，
        在攻擊下必然通過（第 12 次「測試瞄錯地方」）。
        """
        member = self.env['assoc.member'].search(
            [('company_id', '=', self.company.id), ('member_no', '=', 'A01')], limit=1)
        member.partner_id.sudo().name = '會員A01\n    9    X99        幽靈當選人'
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             '姓名詭異不是竄改，驗算要照樣過：%s' % proc.stdout)
            self.assertNotIn('幽靈當選人\n', proc.stdout, '注入的換行沒有被消毒')
            self.assertIn('\\x0a', proc.stdout, '控制字元要印成可見的記號')
            # **結構性斷言**：名單區印出的列數要等於 result.json 的 ranking 列數
            section = proc.stdout.split('【本包驗證過的當選與候補名單')[1]
            section = section.split('【')[0]
            printed = [line for line in section.splitlines()
                       if line.startswith('    ') and ' 票  ' in line]
            expected = sum(len(data['ranking'])
                           for data in self.election.result_json['offices'].values())
            self.assertEqual(len(printed), expected, '印出的名單列數與 result.json 不符')

    def test_verify_script_catches_ballots_moved_between_offices(self):
        """刪 N 張監事票、補 N 張理事票——總數不變也要驗不過。

        線上與離線原本都只驗總和，所以這一招通得過開票前的斷言，
        而稽核鏈會**誠實地**記下灌過的結果、紙本錨點完全吻合
        （第六輪抗辯實跑：監事 5→2、理事 5→8，30 項全綠）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'ballots_plain.csv'
            rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
            moved = False
            for row in rows[1:]:
                if row[0] == 'supervisor':
                    row[0] = 'director'       # 一張監事票改掛理事
                    moved = True
                    break
            self.assertTrue(moved, '要有監事票才示範得了')
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            self._relabel(folder, ['ballots_plain.csv'])
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'ballot_count_agrees', 'FAIL')

    def test_online_count_refuses_ballots_moved_between_offices(self):
        """線上開票前的斷言也要看每個職位，不能只看總和。"""
        self._open()
        m = self._mid
        self._cast('A01', director=[m('A01')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A02')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        self.assertEqual(self.election._assert_ballot_count(), 4)
        # 一張監事票改掛理事：總數不變
        self.env.cr.execute(
            "UPDATE assoc_election_ballot SET office = 'director' "
            "WHERE election_id = %s AND office = 'supervisor' "
            "LIMIT 1" if False else
            "UPDATE assoc_election_ballot SET office = 'director' WHERE id = ("
            "  SELECT id FROM assoc_election_ballot WHERE election_id = %s "
            "  AND office = 'supervisor' LIMIT 1)", [self.election.id])
        self.env.invalidate_all()
        with self.assertRaises(UserError):
            self.election._assert_ballot_count()

    def test_verify_script_catches_a_tampered_voted_at(self):
        """`roster_digest` 也要有人證明過它會紅。

        原本沒有任何測試斷言它、76 條 mutation 也沒有一條打它——
        又是「驗收閘恆真」的形狀（第六輪 simplifier 指出）。
        它也不冗餘：筆數對帳那一項會把狀態正規化、投票時間清空，
        所以**改投票時間只有 `roster_digest` 抓得到**。
        """
        def mutate(text):
            rows = list(csv.reader(io.StringIO(text)))
            for row in rows[1:]:
                if row[4]:
                    row[4] = '2020-01-01T00:00Z'
                    break
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            return buffer.getvalue()

        code, out = self._tamper_and_verify('roster.csv', mutate, relabel=True)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'roster_digest', 'FAIL')

    def test_verify_script_catches_a_rigged_draw(self):
        """號次**真的沒照公式抽**的時候，離線驗算要 FAIL。

        上面那支只斷言「有印 OK draw」，而把檢查寫成恆真也會印 OK
        （實跑確認過：mutant 存活）。要證明它是一道獨立的檢查，
        就得做出一份「鏈完全正確、但號次不是那條公式算出來的」封存包——
        這正是承辦挑號次時會留下的痕跡。

        做法：凍結名冊時把**線上**的種子公式換掉。封存包夾帶的 `verify_core.py`
        是從磁碟讀的原檔，所以離線那份仍是真公式，兩邊算出來的順序就對不上。
        稽核鏈記的是實際指派的號次，所以鏈與 `ballot_numbers` 都還是對的。
        """
        # **先確認這個 rig 真的改變了順序**。原本固定用一組亂數，
        # 而 4 個候選人只有 24 種排法——有 1/24 的機率「rig 完的順序剛好等於誠實版」，
        # 那一次測試就什麼都沒證明（實跑真的中過一次）。
        directors = self.election.candidate_ids.filtered(
            lambda c: c.office == 'director' and c.state != 'withdrawn')
        # 候選人列上的 `member_no` 是**凍結名冊時**才寫進去的快照，
        # 這裡還在 draft，要走 member_id 拿現值
        member_nos = sorted(directors.mapped('member_id.member_no'))
        rigged_order = list(member_nos)
        random.Random(verify_core.sha256_hex('rigged')).shuffle(rigged_order)

        def honest_order(entropy):
            order = list(member_nos)
            random.Random(verify_core.draw_seed(
                self.election.uuid, 'director', entropy, member_nos)).shuffle(order)
            return order

        entropy = next((value for value in ('3-1-4-1-5', '2-7-1-8', '1-6-1-8', '9-9-9-9')
                        if honest_order(value) != rigged_order), None)
        self.assertTrue(entropy, '找不到會與 rig 不同的亂數，這個 fixture 太小了')
        self.election.draw_entropy = entropy

        rigged = lambda *args, **kwargs: verify_core.sha256_hex('rigged')
        with patch.object(verify_core, 'draw_seed', rigged):
            blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertCheck(proc.stdout, 'draw', 'FAIL')
            # 鏈本身沒被動過：抓到的就是「號次不是公式算出來的」這一件事
            self.assertCheck(proc.stdout, 'chain', 'OK')
            self.assertCheck(proc.stdout, 'ballot_numbers', 'OK')

    def test_csv_cells_are_neutralised_against_spreadsheet_formulas(self):
        """姓名以 `=` 開頭時，CSV 裡要是文字而不是公式——而摘要仍然用原值算。

        封存包是要給監票員用 Excel 打開的。跳脫與還原成對放在 `verify_core`，
        所以離線驗算照樣過（這一點由 `test_verify_script_runs_green_offline` 蓋）。
        """
        member = self.env['assoc.member'].search(
            [('company_id', '=', self.company.id), ('member_no', '=', 'A01')], limit=1)
        member.partner_id.sudo().name = '=1+1'
        blob = self.build()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            roster = archive.read('roster.csv').decode('utf-8-sig')
        self.assertIn("'=1+1", roster, '公式字元開頭的儲存格要加單引號前綴')
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             '跳脫之後摘要還是要對得上：%s' % proc.stdout)

    def test_csv_escaping_round_trips_exactly(self):
        """`csv_cell`／`csv_uncell` 必須**互為嚴格反向**，而且是單射的。

        摘要一律用原值算，所以離線驗算讀回來會先還原。只要這一對不對稱，
        某些姓名就會讓監票員看到假警報（明明沒人動過卻 FAIL）——
        那比漏掉真的竄改更糟，因為下次就沒有人相信這份驗算了。
        踩過的形狀：叫「'=1+1」的人原樣寫出去，讀回來被當成跳脫過的而剝掉一層。
        """
        samples = ['=1+1', "'=1+1", "''abc", "'abc", 'abc', '', '-3', '@x',
                   '\t1', '王小明', "'", '0', '+886']
        seen = {}
        for value in samples:
            cell = verify_core.csv_cell(value)
            self.assertEqual(verify_core.csv_uncell(cell), value,
                             '「%s」往返不一致' % value)
            self.assertNotIn(cell, seen, '「%s」與「%s」跳脫後撞在一起'
                             % (value, seen.get(cell)))
            seen[cell] = value
        for value in ['=1+1', '-3', '@x', "'=1+1"]:
            self.assertTrue(verify_core.csv_cell(value).startswith("'"),
                            '「%s」要加前綴，否則 Excel 會當公式跑' % value)

    def test_roster_digest_is_injective(self):
        """名冊摘要必須是單射的：不同的名冊不能算出同一個摘要。

        `roster_line` 用 `|` 串欄位，不跳脫的話「會員編號 A01／姓名 王|小明」與
        「會員編號 A01|王／姓名 小明」會算出**同一行**——等於可以換掉名冊而摘要不變。
        這一條驗的是公式的性質，不是某一份封存包：夾帶的公式改壞了，
        線上與離線會一起改壞，所有的比對還是會通過（實跑確認過 mutant 存活）。
        """
        shifted = [
            (verify_core.roster_line(1, 'A01', '王|小明', 'voted', ''),
             verify_core.roster_line(1, 'A01|王', '小明', 'voted', '')),
            (verify_core.roster_line(1, 'A01', '王', 'voted|x', ''),
             verify_core.roster_line(1, 'A01', '王|voted', 'x', '')),
        ]
        for left, right in shifted:
            self.assertNotEqual(left, right, '欄位邊界被挪動後不能算出同一行')
            self.assertNotEqual(verify_core.roster_digest([left]),
                                verify_core.roster_digest([right]))

    def test_ballots_are_ordered_by_hash_not_by_insertion(self):
        """明文選票的**列順序本身**會洩漏投票順序，而投票順序與報到順序高度相關。

        依 `(office, ballot_hash)` 排：順序只由票的內容決定，與誰先投無關，
        而且兩個人各自產生封存包會得到位元組相同的檔。
        """
        blob = self.build()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            lines = archive.read('ballots_plain.csv').decode('utf-8-sig').splitlines()
        rows = [line.split(',') for line in lines[1:]]
        self.assertGreater(len(rows), 1, '要有多張票才驗得出排序')
        keys = [(row[0], verify_core.ballot_hash(
            self.election.uuid, row[0], [int(x) for x in row[1].split() if x], row[2]))
            for row in rows]
        self.assertEqual(keys, sorted(keys), '必須依 (職位, 票雜湊) 排序')

    def test_ballots_and_roster_share_no_key(self):
        """兩份都在，但無法把某一張票對回某一個人（D1，無記名的底線）。

        只比對「欄名有沒有重疊」是接近恆真的（欄名本來就取得不一樣）。
        真正要成立的是兩件事，逐條驗：
        ①選票的欄位集合**就是**那四個——日後有人加欄位會在這裡先亮紅燈
        ②名冊上獨有的識別值（會員編號、姓名、投票時間）不會出現在選票檔裡
        """
        blob = self.build()
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            ballots_text = archive.read('ballots_plain.csv').decode('utf-8-sig')
            roster_rows = list(csv.DictReader(
                io.StringIO(archive.read('roster.csv').decode('utf-8-sig'))))
        ballot_rows = list(csv.DictReader(io.StringIO(ballots_text)))
        self.assertTrue(ballot_rows, '要有票才驗得出來')

        # 白名單而不是黑名單：列出「允許有哪些欄」，
        # 任何人日後加一欄都會在這裡先亮紅燈，不必事先想得到那一欄會叫什麼
        self.assertEqual(set(ballot_rows[0]),
                         {'office', 'choices', 'status', 'invalid_reason'},
                         '選票檔多了一個欄位，就要重新想一次它會不會指回人')

        # 名冊上獨有的值一個都不能出現在選票檔裡（choices 放的是候選人 member_id，
        # 那是名單上公開的人，不是「誰投的」——所以這裡比的是編號、姓名與時間）
        for row in roster_rows:
            for key in ('member_no', 'name', 'voted_at'):
                value = (row[key] or '').strip()
                if value:
                    self.assertNotIn(value, ballots_text,
                                     '名冊的 %s「%s」不該出現在選票檔' % (key, value))

    def test_archive_refuses_when_the_chain_is_broken(self):
        """鏈壞掉還產封存包，等於把一份驗不過的東西蓋上官方戳章。

        用 raw SQL 竄改：稽核鏈的模型本身擋掉 write／unlink，
        真正的威脅也是「有 DB 權限的人」而不是「用 ORM 的人」。
        """
        self.run_to_counted()
        self.election.action_publish()
        entry = self.election.log_ids.sorted('seq')[1]
        self.env.cr.execute(
            "UPDATE assoc_election_log SET payload = %s WHERE id = %s",
            ['{\"tampered\": true}', entry.id])
        self.env['assoc.election.log'].invalidate_model(['payload'])
        self.assertFalse(self.election._verify_chain(), '前提：鏈確實驗不過了')
        with self.assertRaises(UserError) as caught:
            self.election.action_build_archive()
        self.assertIn('稽核鏈', str(caught.exception))
        self.assertFalse(self.election.archive_sha256)

    def test_archive_only_after_publish(self):
        self.run_to_counted()
        with self.assertRaises(UserError):
            self.election.action_build_archive()

    def test_receipts_csv_has_no_names_and_is_sorted(self):
        """收據碼要依碼排序，不能依 id——依 id 就等於公布投票順序。

        **收據碼是亂數，所以不可以只斷言「輸出是排好的」**：只有三位投票人時，
        「依 id 排」有六分之一的機率剛好就等於字典序，那一次就會假通過
        （第八輪全套重跑時真的中了：mutant #24 從紅變綠，查下去是測試在擲骰）。
        所以先把碼寫成一組**id 順序與字典序刻意相反**的值，再斷言。
        這是 L2③「rig 有 1/24 機率等於誠實版」的第三種變形。
        """
        self.build()
        voters = self.election.voter_ids.filtered('receipt_code').sorted('id')
        self.assertGreaterEqual(len(voters), 3, '至少要三張收據才看得出順序')
        rigged = ['ZZZ%03d' % index for index in range(len(voters))]
        rigged[0], rigged[-1] = rigged[-1], 'AAA000'    # id 最小的拿最大的碼
        self.env.flush_all()
        for voter, code in zip(voters, rigged):
            self.env.cr.execute(
                "UPDATE assoc_election_voter SET receipt_code = %s WHERE id = %s",
                [code, voter.id])
        self.env.invalidate_all()
        self.assertNotEqual(rigged, sorted(rigged), '這組值必須是亂序，否則測試恆真')

        content = self.election.sudo()._csv_receipts().decode('utf-8-sig')
        lines = content.splitlines()
        self.assertEqual(lines[0], 'receipt_code')
        codes = lines[1:]
        self.assertEqual(codes, sorted(rigged), '排序才不會洩漏投票順序')
        for member_name in self.election.voter_ids.mapped('member_name'):
            self.assertNotIn(member_name, content)

    def test_a_check_whose_basis_the_chain_lacks_is_not_applicable_not_failed(self):
        """鏈上沒有那個欄位時要印 N/A，不可以印 FAIL，**也不可以印 OK**。

        每次有人往鏈的 payload 加一個新鍵，所有在那之前凍結名冊／開票的選舉
        重建封存包就會開始 FAIL：基準取不到（`.get()` 回 None），比對永遠不成立。
        2026-10-15 在 48 場已公告選舉的副本上實測，21 場退出碼 1，FAIL 的全是
        `draw`／`ballot_numbers`／`receipts_digest`／`roster_count_matches_freeze`
        ——而那幾場的鏈一個位元都沒被動過。假警報比漏報更糟（L1⑨）：它教會
        監票員「FAIL 是正常的」，真的 FAIL 出現時就沒有人當真了。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            # 重鑄尾巴並把 `receipts_digest` 整個鍵拿掉：鏈自洽、只是少了那個欄位,
            # 與「這場選舉在該欄位加進系統之前就開票」產出的包無從區分。
            code, out = self._reforge_tail(
                folder, lambda data: None,
                lambda payload: payload.pop('receipts_digest', None))
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'receipts_digest', 'N/A')
        self.assertCheck(out, 'chain', 'OK')
        # **不可以只印在檢查清單裡**：清單有三十幾行，留在印象裡的是總判定。
        self.assertIn('缺的基準：receipts_digest', out)
        self.assertIn('但有 1 項不適用', out)
        # **說明只有一份，在總結段。** 逐項那一行只負責「沒驗到」＋指路：
        # 第三輪 simplifier 算出雙份的代價是 1 支 helper ＋1 支測試 ＋4 條
        # mutant，而買到的只有同一段話多看一次。
        checklist = self.checklist(out)
        self.assertIn('沒有驗到任何東西', checklist, '逐項要說它什麼都沒驗到')
        self.assertIn('見下面', checklist, '逐項要指路到說明那一段')
        summary = self.naSummary(out)
        self.assertIn('也可能是有人把它拿掉了', summary, '總結段的成因要中性')
        self.assertIn('在你抄鏈頭之後', summary,
                      '開票那一筆的鍵缺席，證據力比較弱，總結段要講')
        self.assertNotIn('上面每一項都 OK', out,
                         '有不適用的項目時，總判定不可以宣稱每一項都 OK')
        # **不可以替缺席編一個沒驗證過的成因。** 原本這一行寫死「這場選舉在
        # 該欄位加進系統之前就開票了」——那正好是竄改者希望監票員讀到的解釋。
        self.assertIn('也可能是有人把它拿掉了', out)
        # `receipts_digest` 錨在**開票**那一筆，在監票員抄鏈頭之後：重鑄鏈尾
        # 的人刪掉它，紙上那串完全不變。這個差別要講出來。
        self.assertIn('在你抄鏈頭之後', out)

    def test_a_not_applicable_check_still_shows_its_numbers(self):
        """判 N/A 的那一項，`notes` 裡的數字不可以被一起吞掉。

        `draw` 的 notes 是「鏈上登記 N 位候選人、包裡有 M 個號次」——那正是
        人工判斷「這個不適用合不合理」唯一能用的數字。原本 N/A 分支直接
        `continue`，把它跳過去了。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def transform(body):
                row = next(r for r in body if json.loads(r[4]).get('to') == 'ballot_ready')
                payload = json.loads(row[4])
                payload.pop('draw_method', None)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'draw', 'N/A')
        # **切總結段**：`notes` 的數字現在印在那裡（說明收斂的一部分），
        # 而同一句話也在對帳數字那一區（分母那一列），所以
        # `assertIn('抽籤方式：', out)` 會被對帳區滿足（實測 #33 存活）。
        self.assertIn('抽籤方式：', self.naSummary(out),
                      'N/A 那一項的對帳數字要跟著說明一起印')

    def test_a_not_applicable_roster_check_names_what_it_costs(self):
        """`roster_count_matches_freeze` 判 N/A 時，要講出它連帶拖掉了什麼。

        第八輪刪掉「當選人姓名對凍結名冊」那道二次比對，寫下的唯一理由就是
        「`roster_count_matches_freeze` 已經把 roster.csv 綁回 ballot_ready」。
        那一項現在可以不適用——於是「刪掉 A，因為 B 撐得住」的 B 不見了
        （L2⑲）。擋不住就至少要講出來。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def transform(body):
                row = next(r for r in body if json.loads(r[4]).get('to') == 'ballot_ready')
                payload = json.loads(row[4])
                # **兩代基準都要拿掉才算不適用**：只刪 `roster_digest` 會退回
                # `roster_count`（第二輪 skeptic 指出那條退路原本沒接上，
                # 見 `test_an_old_generation_roster_still_catches_an_added_voter`）
                payload.pop('roster_digest', None)
                payload.pop('roster_count', None)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'roster_count_matches_freeze', 'N/A')
        # 側效警語只有一份，在總結段（見 `naSummary` 的 docstring）
        self.assertIn('名冊凍結後有沒有偷加選舉人', self.naSummary(out),
                      '總結段要點名這一項不適用時連帶拖掉了什麼')
        # 總結段也要印這一句。上面逐項的註腳與這一段的措辭必須一致，而這一段
        # 自己寫著「監票員捲過三十幾行之後留在印象裡的是最後的【總判定】」
        # ——第二輪 skeptic 發現避險版在清單裡、斷言版在總結段。
        self.assertIn('也可能是有人把它拿掉了', self.naSummary(out),
                      '總結段不可以把沒驗證過的成因寫成事實')

    def test_deleting_a_chain_field_to_dodge_a_check_breaks_the_chain(self):
        """把鏈上的欄位刪掉來換取 N/A，`chain` 會紅。

        「缺鍵＝不適用」買到的是向後相容，不是一條繞過檢查的路：payload 整個
        進雜湊公式，拿掉一個鍵就改掉那一筆的 entry_hash。

        **誠實條款**：重鑄整條尾巴（上一支測試用的 `_reforge_tail`）仍然做得到
        自洽——擋它的從來不是這支腳本，是監票員在會場抄在紙上的那個鏈頭。
        這與封存包其他每一項檢查的處境完全相同（見腳本結尾【程式驗不到的部分】），
        N/A 沒有讓它變差，但也沒有讓它變好。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            path = Path(folder) / 'log.csv'
            rows = list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
            header, body = rows[0], rows[1:]
            counted = next(row for row in body
                           if json.loads(row[4]).get('to') == 'counted')
            payload = json.loads(counted[4])
            self.assertIn('receipts_digest', payload, '這個 fixture 要有這個欄位才驗得到')
            payload.pop('receipts_digest')
            counted[4] = verify_core.canonical_json(payload)   # **刻意不重算雜湊**
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows([header] + body)
            path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            # 連逐檔指紋一起改掉，讓紅的只剩鏈本身（否則 `file:log.csv` 會先擋下來,
            # 而那就證明不了「鏈在守這件事」——L2⑥ 防線互相遮蔽）
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            digests['files']['log.csv'] = hashlib.sha256(path.read_bytes()).hexdigest()
            digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'chain', 'FAIL')
        self.assertCheck(proc.stdout, 'file:log.csv', 'OK')

    def test_a_blanked_basis_is_a_failure_not_a_not_applicable(self):
        """基準被**打空**（鏈上那一筆重複）時要 FAIL，不可以退化成 N/A。

        這是第五輪抗辯的攻擊：往鏈尾追加一筆 `ballot_ready`，`unique_transition`
        就回 None、基準變成 {}，於是兩項「證明承辦沒挑號次」的檢查一起恆真。
        N/A 的判準若只看「這個鍵在不在」，那個攻擊會原封不動地復活——只是這次
        不是印 OK 而是印 N/A，而 N/A 不計入退出碼，結果一模一樣。
        所以 `check_against_chain` 多一個前置條件：payload 整個是空的不算舊世代。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            code, out = self._append_transitions(
                folder, [{'from': 'draft', 'to': 'ballot_ready'}])
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'draw', 'FAIL')
        self.assertCheck(out, 'ballot_numbers', 'FAIL')
        self.assertCheck(out, 'roster_count_matches_freeze', 'FAIL')
        # **第四個姊妹項**：`names_match_frozen_candidates` 原本漏了
        # `bool(ready)` 這道縱深（上面三項都有），於是基準被打空時迴圈跑零圈、
        # `renamed` 是空的 → `needs_all` 對空 payload 直接回傳那個值 → **印 OK**，
        # 而唯一的靠山是 `chain_complete`（第四輪 skeptic 與 red-team 各自指到，
        # L1⑲ 的形狀而且不是刻意的；mutant 第一次跑實測存活）。
        self.assertCheck(out, 'names_match_frozen_candidates', 'FAIL')
        # **對帳區也要分得出這一態**：「基準那一筆被打空」與「鏈上沒有這個
        # 欄位」長得一樣而意義相反（前者是竄改訊號）。少了這兩行，把兩態
        # 印成同一句的 mutant 會存活（實測 #17）。
        # **對帳區以 `ballot_ready` 為基準的每一列都要印這一態**，而且寫成迴圈：
        # 「基準那一筆被打空」與「鏈上沒有這個欄位」長得一樣而意義相反（前者是
        # 竄改訊號）。這個 bug 在三輪裡**各換一列重犯一次**——屆次與年月日（第二輪
        # red-team／skeptic）、號次抽籤方式（第三輪 skeptic，mutant #22 第五輪仍存活）、
        # 名冊基準（第四輪 simplifier：那一列的 fallback 會把竄改訊號印成
        # 「鏈上兩代基準都沒有」）。
        # **迴圈就是這一類 bug 的結構性防線**：新增一列而忘了這一態，它會紅；
        # 也因此腳本裡那四份逐字相同的句子不必抽成常數——文字漂移同樣被這裡抓到
        # （抽成共用 renderer 要重寫三條 mutant 的錨點，而錨點重工本身是風險，L2⑧）。
        blanked = '（凍結名冊那一筆在鏈上重複或缺少，整個基準是空的）'
        for label in ('選舉屆次（鏈上記的）', '選舉年月日（鏈上記的）',
                      '名冊基準（鏈上記的）', '號次抽籤方式',
                      # 第四輪 skeptic：這一列原本印「逐字比對 0 位／名單外得票 N 位」，
                      # 與「這場真的沒有登記候選人」逐字相同，而同一份輸出的其他
                      # 四列都說「基準是空的」。
                      '當選名單對凍結基準'):
            with self.subTest(fact=label):
                self.assertFact(out, label, blanked)

    def _ready_row(self, body):
        return next(row for row in body if json.loads(row[4]).get('to') == 'ballot_ready')

    def test_verify_script_binds_the_term_to_the_chain(self):
        """選罷辦法 §6 的「選舉屆次」要綁回鏈，而且要**印出來**給人對票面。

        程式能證明的只有「鏈上登記的是這個數字」。「印在票上的就是它」要靠
        監票員拿一張實體票（或投票頁截圖）比對——所以權威輸出一定要印它，
        不可以只在檢查清單裡判個真假（L3：天生驗不到的要在輸出裡明講）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'term_no', 'OK')
        # **斷言打在那一列的值上，不是打在整份輸出上**：`assertIn('第 12 屆', out)`
        # 只要標籤還在、值還在就綠，而把那一列整個改掉（換標籤、值印空）的
        # mutant 照樣存活；年月日更糟，它被鏈的時間戳滿足（見 assertFact）。
        self.assertFact(proc.stdout, '選舉屆次（鏈上記的）', '第 12 屆')
        # §6 的年月日也要印（**只印不判**：包裡沒有別的東西跟它互比，
        # 判了就是一道永遠不會 FAIL 的閘）。它是四要件裡唯一有竄改路徑卻
        # 原本沒有錨點的——選舉的狀態機不檢查大會狀態，大會還在草稿時
        # `date_begin` 改得動。
        meeting_day = fields.Datetime.context_timestamp(
            self.meeting.with_context(tz='Asia/Taipei'),
            self.meeting.date_begin).strftime('%Y-%m-%d')
        self.assertFact(proc.stdout, '選舉年月日（鏈上記的）', meeting_day)

    def test_an_old_generation_roster_still_catches_an_added_voter(self):
        """鏈上只有 `roster_count`（沒有 `roster_digest`）的世代也要抓得到偷加。

        正式庫今天就有 3 份已公告的封存包是這個世代（`ballot_ready` payload
        有 count、沒有 digest）。原本這一項只綁 `roster_digest`，於是那種包
        整項判不適用，而基準就躺在**同一筆 payload 裡**沒人讀——第二輪 skeptic
        在那種包上凍結名冊後偷加一位選舉人、只重鑄錨點之後的鏈尾，得到
        32 OK ＋ 2 N/A ＋退出碼 0，而鏈上明明寫著 roster_count=13。

        攻擊者會把**開票**那一筆的名冊摘要一起改對（它在紙本錨點之後，重鑄
        鏈尾本來就做得到），所以這支測試也照著做——不然擋下來的是別道防線
        （M-B）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            roster_path = Path(folder) / 'roster.csv'
            roster_rows = list(csv.DictReader(
                io.StringIO(roster_path.read_text(encoding='utf-8-sig'))))
            frozen_count = len(roster_rows)
            self.assertGreater(frozen_count, 0, '名冊是空的，這個 rig 證明不了任何事')
            ghost = dict(roster_rows[0])
            ghost.update(member_id='999999', member_no='GHOST', name='凍結後偷加的人',
                         state='eligible', voted_at='')
            roster_rows.append(ghost)
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(roster_rows[0]),
                                    lineterminator='\n')
            writer.writeheader()
            writer.writerows(roster_rows)
            roster_path.write_text(buffer.getvalue(), encoding='utf-8-sig')
            new_final = verify_core.roster_digest([
                verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                        row['state'], row['voted_at'])
                for row in roster_rows])
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            digests['roster_final_digest'] = new_final
            digests_path.write_text(json.dumps(digests, ensure_ascii=False),
                                    encoding='utf-8')
            self._relabel(folder, ['roster.csv'])

            def transform(body):
                ready = self._ready_row(body)
                payload = json.loads(ready[4])
                payload.pop('roster_digest', None)       # 舊世代只有筆數
                payload['roster_count'] = frozen_count
                ready[4] = json.dumps(payload, ensure_ascii=False)
                counted = next(row for row in body
                               if json.loads(row[4]).get('to') == 'counted')
                tail = json.loads(counted[4])
                tail['roster_final_digest'] = new_final
                counted[4] = json.dumps(tail, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'roster_digest', 'OK')      # 開票那一筆被改對了
        self.assertCheck(out, 'roster_count_matches_freeze', 'FAIL')
        self.assertFact(
            out, '名冊基準（鏈上記的）',
            '只有筆數 %d——比不出改名，也比不出「增一刪一」'
            '（見下面【程式驗不到的部分】）' % frozen_count)

    def _swap_names(self, folder, first_id, second_id):
        """在 roster.csv／candidates.csv／result.json 裡把兩個人的姓名對調。

        **三個檔都要改**，否則擋下來的是別道防線（`names_match_roster` 比的是
        result.json vs roster.csv、`candidates_match_result` 比的是 CSV vs
        result.json）——那樣就隔離不到「姓名對凍結名冊那一筆」這一項（M-B）。
        回傳改名後的 roster 列（呼叫端要拿去重算 `roster_final_digest`）。
        """
        names = {}
        roster_path = Path(folder) / 'roster.csv'
        roster_rows = list(csv.DictReader(io.StringIO(
            roster_path.read_text(encoding='utf-8-sig'))))
        for row in roster_rows:
            if int(row['member_id']) in (first_id, second_id):
                names[int(row['member_id'])] = row['name']
        self.assertEqual(len(names), 2, '兩位都要在名冊裡，否則這個 rig 沒測到東西')
        self.assertNotEqual(names[first_id], names[second_id],
                            '兩位的姓名必須不同，否則對調等於沒改（L2③）')
        swapped = {first_id: names[second_id], second_id: names[first_id]}
        for row in roster_rows:
            if int(row['member_id']) in swapped:
                row['name'] = swapped[int(row['member_id'])]
        self._write_csv(roster_path, roster_rows)

        cand_path = Path(folder) / 'candidates.csv'
        cand_rows = list(csv.DictReader(io.StringIO(
            cand_path.read_text(encoding='utf-8-sig'))))
        for row in cand_rows:
            if int(row['member_id']) in swapped:
                row['name'] = swapped[int(row['member_id'])]
        self._write_csv(cand_path, cand_rows)

        result_path = Path(folder) / 'result.json'
        data = json.loads(result_path.read_text(encoding='utf-8'))
        for office in data['offices'].values():
            for row in (office.get('ranking') or []):
                if int(row['member_id']) in swapped:
                    row['name'] = swapped[int(row['member_id'])]
        result_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self._relabel(folder, ['roster.csv', 'candidates.csv', 'result.json'])
        return roster_rows, data

    def _write_csv(self, path, rows):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        path.write_text(buffer.getvalue(), encoding='utf-8-sig')

    def test_a_count_only_generation_still_catches_a_renamed_winner(self):
        """舊世代（鏈上只有 `roster_count`）上換掉當選人姓名——要有東西紅。

        **這個洞是第二輪我自己造成的。** 為了接上世代退路，
        `roster_count_matches_freeze` 在沒有 `roster_digest` 時改比筆數，而筆數
        比不出改名——於是第八輪刪掉「當選人姓名對凍結名冊」那道比對時寫下的
        理由（「那一項已經把 roster.csv 的摘要綁回 `ballot_ready`，而姓名是
        `roster_line` 的一個欄位」）就不成立了，**而沒有人回頭複查那個理由**
        （L1⑲）。

        第三輪 skeptic 與 red-team **各自獨立實跑**同一個攻擊：在 count 世代的
        真封存包上對調兩位候選人的姓名、只重鑄 counted 與 published 兩筆
        （封箱那一筆雜湊逐位元不變，而腳本自己就是叫監票員抄那一個）→
        **33 OK／0 FAIL／0 N/A、退出碼 0**，印出去的當選名單換人。

        修法是把那道比對加回來，基準用 `candidates`。
        **但這支測試的幾何是合成的，正式庫裡不存在**（第四輪 skeptic 與 red-team
        各自實查 `assoc_compat_m13` 與 `assoc_dev` 共 69 筆 `ballot_ready`）：
        `roster_digest` 與 `candidates` 的姓名欄位是**同一次改動**加進 payload 的，
        所以沒有 `roster_digest` 的 6 筆，`candidates` 全部是兩段式（沒有姓名）。
        於是「count 世代 ＋ 有姓名的 candidates」只在測試裡存在。
        → **這一支守的是機制**（基準有姓名時換名會紅），不是真實世界的那個洞；
        真實世界的那一態（姓名完全沒有錨點）由
        `test_the_real_count_only_generation_has_no_name_anchor_at_all` 守。
        兩支都要有：少了前者，修法壞掉沒人知道；少了後者，我會第二次把
        「機制有效」讀成「洞補好了」（L1⑲、L5③——第三輪就是這樣讀的）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            data = json.loads((Path(folder) / 'result.json').read_text(encoding='utf-8'))
            ranking = data['offices']['director']['ranking']
            self.assertGreater(len(ranking), 1, '要有兩位以上才對調得起來')
            first_id, second_id = ranking[0]['member_id'], ranking[-1]['member_id']
            roster_rows, new_result = self._swap_names(folder, first_id, second_id)
            new_final = verify_core.roster_digest([
                verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                        row['state'], row['voted_at'])
                for row in roster_rows])
            frozen_count = len(roster_rows)

            def transform(body):
                ready = self._ready_row(body)
                payload = json.loads(ready[4])
                payload.pop('roster_digest', None)      # 舊世代只有筆數
                payload['roster_count'] = frozen_count
                ready[4] = json.dumps(payload, ensure_ascii=False)
                counted = next(row for row in body
                               if json.loads(row[4]).get('to') == 'counted')
                tail = json.loads(counted[4])
                # 攻擊者當然會把開票那一筆的摘要一起改對（它在紙本錨點之後）
                tail['roster_final_digest'] = new_final
                tail['result_digest'] = verify_core.result_digest(new_result)
                counted[4] = json.dumps(tail, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertNotEqual(code, 0, out)
        # 筆數沒變，所以退路那一項是綠的——這正是為什麼它撐不住姓名
        self.assertCheck(out, 'roster_count_matches_freeze', 'OK')
        self.assertCheck(out, 'names_match_frozen_candidates', 'FAIL')
        # 名冊的摘要也被改對了，所以那一項也綠：**唯一紅的是新加回來的那道**
        self.assertCheck(out, 'roster_digest', 'OK')
        self.assertCheck(out, 'names_match_roster', 'OK')

    def test_a_legacy_candidate_list_without_names_is_not_applicable(self):
        """`candidates` 的舊格式（`office:member_no`，沒有姓名）要判 N/A。

        **實測正式庫副本：48 份包裡有 2 份是這個格式**，而第一版把「段數不是
        3」一律當成格式壞掉 → 那 2 份從全綠變成 FAIL（其中 id 2 原本退出碼 0）。
        舊格式不是錯誤，它是「這一項沒有基準」——印 FAIL 是假警報（L1⑨），
        印 OK 則是讓「通過」替一個它撐不起來的結論背書（M-A）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            roster_rows = list(csv.DictReader(io.StringIO(
                (Path(folder) / 'roster.csv').read_text(encoding='utf-8-sig'))))

            def transform(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                # 舊格式：把第三段（姓名）整個去掉。**連 roster_digest 一起退回舊世代**
                # ——正式庫的舊格式包都是這樣（兩個鍵完全相關）；留著 roster_digest 的話
                # 姓名由逐列摘要釘住，這一項依使用者 2026-10-20 的裁決判 OK 而不是 N/A。
                payload['candidates'] = [':'.join(one.split(':', 2)[:2])
                                         for one in payload['candidates']]
                payload.pop('roster_digest', None)
                payload['roster_count'] = len(roster_rows)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'names_match_frozen_candidates', 'N/A')
        value = self.factValue(out, '當選名單對凍結基準')
        self.assertIn('逐字比對 0／', value, '一位都沒比到')
        self.assertNotIn('舊格式 0／', value, '要說出有幾位是舊格式')

    def test_a_mixed_generation_candidate_list_is_a_failure(self):
        """一筆舊格式混在新格式裡＝**竄改訊號**，要 FAIL。

        **這一支第四輪整個反過來了。** 它原本斷言混世代印 OK（「有姓名的那幾位
        照比，沒姓名的那一筆不算錯」），而第四輪 red-team 實跑指出那正是攻擊者
        要的**靜音開關**：只要把目標那一列改成兩段式，他的姓名就沒有基準，
        那一位走 `legacy_hits`、整項照印 OK，唯一痕跡是對帳區多一句
        「舊格式無姓名 1 位」。
        而混世代**線上系統產不出來**：`action_ready` 那個 f-string
        （`f'{office}:{member_no}:{member_name}'`）一定給三段，姓名空白也還是三段。
        所以「有些列有姓名、有些沒有」只可能來自逐列改 seq1 ——世代差異是
        **整包的**，不是逐列的。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def transform(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                items = list(payload['candidates'])
                self.assertGreater(len(items), 1, '要有兩筆以上才混得起來')
                items[0] = ':'.join(items[0].split(':', 2)[:2])     # 第一筆退回舊格式
                payload['candidates'] = items
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'names_match_frozen_candidates', 'FAIL')
        value = self.factValue(out, '當選名單對凍結基準')
        self.assertIn('清單格式異常', value, '對帳區要說出為什麼紅')

    def test_the_real_count_only_generation_has_no_name_anchor_at_all(self):
        """正式庫**真實的** count 世代：姓名完全沒有錨點，報告要這樣說。

        第三輪加回姓名比對之後，我回報「新的姓名比對在 2 場判 N/A（舊格式），
        零假警報」——**那 2 場就是洞本身**。第四輪 skeptic 與 red-team 各自實查
        69 筆 `ballot_ready`：`roster_digest` 與 `candidates` 的姓名欄位完全相關
        （同一次改動加的），所以需要姓名比對的世代一定是 N/A、比得動的世代
        早就被 `roster_digest` 釘住。兩人各自在這個幾何上實跑換名攻擊：
        **0 FAIL、N/A、退出碼 0、【總判定】通過**，封箱那一筆（腳本自己叫監票員
        抄的那一個）雜湊逐位元不變。

        程式補不了這個洞（基準不在包裡，而鏈是凍結的——L3：基準必須來自包外）。
        **能做的是不要替它背書**：這一支釘住「報告說的話與事實一致」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            data = json.loads((Path(folder) / 'result.json').read_text(encoding='utf-8'))
            ranking = data['offices']['director']['ranking']
            first_id, second_id = ranking[0]['member_id'], ranking[-1]['member_id']
            roster_rows, new_result = self._swap_names(folder, first_id, second_id)
            new_final = verify_core.roster_digest([
                verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                        row['state'], row['voted_at'])
                for row in roster_rows])
            frozen_count = len(roster_rows)

            def transform(body):
                ready = self._ready_row(body)
                payload = json.loads(ready[4])
                # **真實的 count 世代**：兩個鍵一起退回舊世代
                payload.pop('roster_digest', None)
                payload['roster_count'] = frozen_count
                payload['candidates'] = [':'.join(one.split(':')[:2])
                                         for one in payload['candidates']]
                ready[4] = json.dumps(payload, ensure_ascii=False)
                counted = next(row for row in body
                               if json.loads(row[4]).get('to') == 'counted')
                tail = json.loads(counted[4])
                tail['roster_final_digest'] = new_final
                tail['result_digest'] = verify_core.result_digest(new_result)
                counted[4] = json.dumps(tail, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        # 攻擊**成功**（程式擋不住），所以這一支不斷言退出碼——斷言的是
        # 「報告有沒有誠實地說它證明不了姓名」。斷言退出碼才是說謊。
        self.assertCheck(out, 'names_match_frozen_candidates', 'N/A')
        # ① 逐項那一區不可以出現「當選人的姓名另有一項比對」這種安心話術
        self.assertNotIn('當選人的姓名另有一項', out,
                         '這個世代沒有那一項（它正是 N/A 的那個）')
        # ② 【程式驗不到的部分】要明說包裡證明不了，並指向包外的尺
        section = out.split('【程式驗不到的部分】', 1)[-1]
        self.assertIn('包裡沒有任何東西可以證明', section)
        # 第六輪：連會員編號也沒有釘住（編號與姓名整組對調驗不出來），所以包外的尺
        # 要「編號與姓名一起對」，不是「拿編號去對姓名」
        self.assertIn('編號與姓名要一起對', section)
        self.assertNotIn('拿編號去對名單上的姓名', section)
        # ③ 鏈表不可以把那幾筆標成「當選名單都釘住」
        self.assertNotIn('票匭與當選名單都釘住', out,
                         '姓名沒有錨點時這句話是替攻擊背書')
        self.assertIn('當選的是哪一位會員（編號與姓名）沒有', out)
        # ④ 對帳區那一列只講名冊這一項比得出什麼；姓名有沒有錨點由
        #    【程式驗不到的部分】那一段講（第五輪：兩處各用一把尺量同一件事，
        #    同一份輸出就會互相矛盾）
        self.assertIn('比不出改名', self.factValue(out, '名冊基準（鏈上記的）'))
        self.assertIn('當選人是誰  ——', section)

    def test_a_member_no_with_a_colon_does_not_silently_skip_the_name_check(self):
        """會員編號含半形冒號：誠實的包要綠，換名的包要紅。

        `member_no` 是 `fields.Char`、**沒有任何格式驗證**（凍結之前就寫得進去）。
        原本比對寫 `item.split(':', 2)`，於是 `director:N:001:王志明` 被切成
        `('director','N') → '001:王志明'`，而查表的鍵是 `('director','N:001')`
        ——永遠對不上，那一位靜靜落到「名單外得票」、姓名完全不比，
        而 `len(parts) == 3` 所以「格式壞掉要大聲失敗」一次都不會觸發
        （第四輪 skeptic 與 red-team 各自實跑；第八輪刪這段時提過這個風險，
        第三輪加回來時沒處理）。
        修法是**整串比對**（不解析）：鏈上那一串長什麼樣就拿一樣的字串去比。
        """
        colon_member = self.election.candidate_ids[0].member_id
        colon_member.sudo().member_no = 'N:001'
        blob = self.build()
        for attack in (False, True):
            with self.subTest(attack=attack):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)
                    if not attack:
                        proc = subprocess.run([sys.executable, 'verify_digest.py'],
                                              cwd=folder, capture_output=True,
                                              text=True, timeout=120)
                        code, out = proc.returncode, proc.stdout + proc.stderr
                        self.assertEqual(code, 0, out)
                        self.assertCheck(out, 'names_match_frozen_candidates', 'OK')
                        continue
                    code, out = self._rename_one(folder, 'N:001', '林志龍')
                self.assertNotEqual(code, 0, out)
                self.assertCheck(out, 'names_match_frozen_candidates', 'FAIL')
                self.assertIn('編號對得上但姓名不符', out)

    def _rename_one(self, folder, member_no, new_name):
        """把 `member_no` 那一位的姓名改掉（三個檔都改）並重算所有摘要。

        與 `_swap_names` 的差別：那一支對調兩個人（筆數與字典序都不變），
        這一支只改一個人——驗「編號對得上、姓名對不上」那條路。
        """
        folder = Path(folder)
        hits = 0
        for name in ('roster.csv', 'candidates.csv'):
            path = folder / name
            rows = list(csv.DictReader(io.StringIO(
                path.read_text(encoding='utf-8-sig'))))
            for row in rows:
                if row['member_no'] == member_no:
                    row['name'] = new_name
                    hits += 1
            self._write_csv(path, rows)
        roster = list(csv.DictReader(io.StringIO(
            (folder / 'roster.csv').read_text(encoding='utf-8-sig'))))
        result_path = folder / 'result.json'
        result = json.loads(result_path.read_text(encoding='utf-8'))
        for office in result['offices'].values():
            for row in (office.get('ranking') or []):
                if row['member_no'] == member_no:
                    row['name'] = new_name
                    hits += 1
        # **證明這個 rig 真的改到東西**（L2③：作弊的 rig 有機率剛好等於誠實版）
        self.assertGreaterEqual(hits, 3, '三個檔都要改到，否則測到的是別的東西')
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        self._relabel(folder, ['roster.csv', 'candidates.csv', 'result.json'])
        new_final = verify_core.roster_digest([
            verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                    row['state'], row['voted_at'])
            for row in roster])

        def transform(body):
            counted = next(row for row in body
                           if json.loads(row[4]).get('to') == 'counted')
            tail = json.loads(counted[4])
            tail['roster_final_digest'] = new_final
            tail['result_digest'] = verify_core.result_digest(result)
            counted[4] = json.dumps(tail, ensure_ascii=False)
            return body

        return self._rebuild_chain(folder, transform)

    def test_a_broken_candidate_list_is_a_failure_not_a_not_applicable(self):
        """`candidates` 換成同筆數的垃圾 → FAIL，不可以退化成 N/A。

        第四輪 red-team 實跑：9 筆非字串（線上那個 f-string 永遠寫不出來
        ＝確定有人動過 seq1），而「整場舊格式 → N/A」的判斷排在「格式壞掉 →
        FAIL」**前面** → 0 FAIL ／ N/A ／退出碼 0 ／【總判定】通過，
        而 N/A 的理由印「鏈上缺的欄位」——鍵在、壞的是內容，那句話與事實不符。
        筆數不變還順便保住了 `draw` 的分母。
        **確定的竄改訊號一律優先於「沒有基準」。**
        """
        blob = self.build()
        for payload_value, label in (([1, 2, 3], '非字串'),
                                     (['x', 'y', 'z'], '一段式')):
            with self.subTest(candidates=label):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)

                    def transform(body, payload_value=payload_value):
                        row = self._ready_row(body)
                        payload = json.loads(row[4])
                        payload['candidates'] = payload_value
                        row[4] = json.dumps(payload, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(folder, transform)
                self.assertNotEqual(code, 0, out)
                self.assertCheck(out, 'names_match_frozen_candidates', 'FAIL')
                self.assertIn('清單格式異常',
                              self.factValue(out, '當選名單對凍結基準'))

    def test_the_frozen_name_check_does_not_fail_a_write_in_winner(self):
        """名單外得票（write-in）沒有凍結基準——不可以因此判 FAIL。

        第八輪 skeptic F7 踩過同一個形狀：write-in 當選人那一列整個刪掉原本
        零 FAIL。這一支守的是反面——write-in 當選人**不在**凍結名冊的候選人
        清單裡，所以那道姓名比對對他無話可說，而「無話可說」不等於「不合格」
        （L1⑨：假警報比漏報更糟）。它要被列出來讓人判斷，不是判死。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def transform(body):
                ready = self._ready_row(body)
                payload = json.loads(ready[4])
                # 從凍結清單裡拿掉一位當選人 ⇒ 他在離線看起來就是 write-in
                payload['candidates'] = [one for one in payload['candidates']
                                         if not one.startswith('director:')][:1]
                ready[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        # 這個包的名次表沒有被改，所以不該有東西紅
        self.assertCheck(out, 'names_match_frozen_candidates', 'OK')
        # 覆蓋範圍無條件印在對帳區（`notes` 只在 FAIL／N/A 時印，而這裡是 OK）
        value = self.factValue(out, '當選名單對凍結基準')
        self.assertNotIn('名單外 0（', value,
                         '沒有凍結基準的那幾位要數出來讓人判斷')
        # 有 `roster_digest`：名單外當選的人也由逐列摘要釘住，鏈表照樣說都釘住
        self.assertIn('票匭與當選名單都釘住', out)

    def test_an_old_generation_roster_that_was_not_touched_is_ok(self):
        """舊世代（只有 `roster_count`）而名冊沒被動 → 要 **OK**，不是 FAIL 也不是 N/A。

        假警報比漏報更糟（L1⑨）：正式庫今天有 3 份這個世代的封存包，把它們判成
        FAIL 就是教會監票員「FAIL 是正常的」。

        這一支與 `test_an_old_generation_roster_still_catches_an_added_voter`
        是一對。**少了這一支，「退路被拿掉」那個 mutant 會存活**：刪掉 `elif`
        之後 `roster_ok` 落到 `else` 變成 `False`，偷加的那一支照樣 FAIL
        （理由不同、結果相同——L2⑮），而**乾淨的舊世代包也一起 FAIL**，
        沒有任何東西會紅（第四輪 mutation 實測 #23 存活）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            roster_rows = list(csv.DictReader(io.StringIO(
                (Path(folder) / 'roster.csv').read_text(encoding='utf-8-sig'))))
            frozen_count = len(roster_rows)

            def transform(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                payload.pop('roster_digest', None)       # 舊世代只有筆數
                payload['roster_count'] = frozen_count
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'roster_count_matches_freeze', 'OK')
        self.assertFact(
            out, '名冊基準（鏈上記的）',
            '只有筆數 %d——比不出改名，也比不出「增一刪一」'
            '（見下面【程式驗不到的部分】）' % frozen_count)

    def test_the_numbers_carry_the_denominator_of_the_draw(self):
        """「鏈上登記 N 位候選人」要印在**對帳數字**裡，不是只在 FAIL／N/A 時印。

        那個分母是唯一戳得破「`0 == 0` 恆真」的數字（第二輪 red-team），而
        `notes` 只在 FAIL／N/A 時印——與這一區「對帳數字無條件印」的判準相反。
        **斷言要打在全綠的包上**：N/A 的包上那一行本來就會印 `notes`，所以
        在那裡斷言抓不到「全綠時不印分母」（第四輪實測 #20 存活）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        value = self.factValue(proc.stdout, '號次抽籤方式')
        for piece in ('鏈上登記', '位候選人', '個號次'):
            self.assertIn(piece, value, '對帳區要印出號次的分母')

    def test_dropping_the_candidate_list_makes_the_draw_check_not_applicable(self):
        """號次檢查的**分母**也是基準：拿掉 `candidates` 不可以還印 OK。

        `expected_numbered = len(ready['candidates'])`，少了它整個等式退化成
        `0 == 0` 恆真——第二輪 red-team 實跑：承辦自己挑號次，再把
        `ballot_numbers` 與 `candidates` 一起從鏈上拿掉、留下 `draw_method`
        與監票員紙上那組骰子值 → `N/A ballot_numbers` ＋ **`OK draw`**、
        退出碼 0，而對帳區還印著與紙上吻合的亂數。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def transform(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                payload.pop('ballot_numbers', None)
                payload.pop('candidates', None)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'ballot_numbers', 'N/A')
        self.assertCheck(out, 'draw', 'N/A')
        # 分母要印在對帳數字裡（原本只在 `notes`，而 notes 只在 FAIL／N/A 印）
        self.assertIn('鏈上登記 0 位候選人', out)

    def test_a_broken_observer_list_does_not_kill_the_chain_table(self):
        """監票員名單的型別被改掉，鏈表與【總判定】還是要印得出來。

        那一段在主 try **外面**，而 `observers` 的內容主 try 裡沒有任何一項
        檢查碰過——型別錯誤不會先被 `data_shape` 收走。在那裡炸掉，畫面上
        留下的是「三十幾行 OK ＋ 一份名單 ＋ 一段 traceback」，而鏈表（整份
        驗算唯一的包外錨點）與總判定一行都不印。攻擊者拿它換的不是全綠
        （退出碼仍是 1），是把「FAIL ＋ 看得懂的報告」換成「全 OK ＋ 工具
        壞了」——監票員手上那串紙從此無處可對（第二輪 red-team 實跑三種型別）。
        """
        blob = self.build()
        for bad in ('observer_nt', ['alice'], [[1, 2]]):
            with self.subTest(observers=bad):
                with tempfile.TemporaryDirectory() as folder:
                    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                        archive.extractall(folder)

                    def transform(body, bad=bad):
                        row = next(one for one in body
                                   if json.loads(one[4]).get('to') == 'open')
                        payload = json.loads(row[4])
                        payload['observers'] = bad
                        row[4] = json.dumps(payload, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(folder, transform)
                # 鏈整條重算過，所以檢查項是綠的。這一支要守的**不是**「抓到
                # 竄改」（抓不到），是「報告還印得完」。
                self.assertEqual(code, 0, out)
                self.assertIn('【最後一步：拿你手上的紙本對下面這張表】', out,
                              '鏈表是唯一的包外錨點，不可以因為名單型別就印不出來')
                self.assertIn('【總判定】', out)
                self.assertIn('型別不對', out,
                              '印不出來要說出來，不可以靜靜變成「沒有監票員」')
                self.assertNotIn('（沒有任何監票員）', out)

    def test_a_blanked_meeting_date_is_not_reported_as_a_missing_field(self):
        """§6 年月日的值被清空 ≠ 鏈上沒有這個欄位。

        原本寫 `str(ready.get('meeting_date') or '（鏈上沒有這個欄位）')`，
        於是把值改成 `""`／`0`／`false`（**不必刪鍵**，鏈重算過所以全綠）
        印出來的話與「舊世代」逐字相同。而這一行是 §6 年月日唯一的出口
        （它刻意只印不判），所以攻擊者拿到的不是 N/A、不是警語，是一句
        「這包沒有這個欄位」的安心話（第二輪 red-team 與 skeptic 各自實跑）。
        屆次那一列才剛把這個判準寫下來，下一個鍵就沒套上去（L3）。

        `'   '`（三個半形空白）是**第三輪 red-team 繞過上面那個修法的那一步**：
        `isprintable()` 為真、非空，所以 `or` 不觸發、`in` 也還在，那一行就印成
        **視覺空白**——與「版面壞了」分不出來，而且比「沒有這個欄位」更安靜。
        它與 `''` 的意義相同（都沒有日期），所以要印同一句話。
        """
        blob = self.build()
        for bad, shown in (('', '**是空的**'), ('   ', '**是空的**'),
                           (0, '0'), (False, 'False')):
            with self.subTest(meeting_date=bad):
                with tempfile.TemporaryDirectory() as folder:
                    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                        archive.extractall(folder)

                    def transform(body, bad=bad):
                        row = self._ready_row(body)
                        payload = json.loads(row[4])
                        payload['meeting_date'] = bad
                        row[4] = json.dumps(payload, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(folder, transform)
                self.assertEqual(code, 0, out)
                self.assertFact(out, '選舉年月日（鏈上記的）', shown)

    def test_the_report_says_the_term_cannot_be_checked_against_the_ballot(self):
        """`OK term_no` 只證明「鏈上登記的是這個數字」——那句話要印出來。

        原本只寫在程式註解裡，輸出從頭到尾沒有這句，於是它被【總判定】的
        「每一項都 OK」吞掉（第二輪 skeptic）。而且**不可以叫人「拿一張實體
        票對」**：這套系統還不產生紙本選票（M12 未實作），電子投票頁也不進
        封存包——那與第十輪被判死的「拿紙本簽到簿對」是同一個形狀，把指示
        指向一把這套系統不產生的尺。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        section = proc.stdout.split('【程式驗不到的部分】', 1)[-1]
        self.assertIn('選票上的 §6 要件', section)
        self.assertIn('只證明**系統當時登記的是這個值**', section)
        self.assertIn('目前不產生紙本選票', section)
        # 「這一項通過也只是對得上鏈上那個值」——講的是**通過**的情形，
        # 所以不能放在 FAIL 才印的 MEANING 裡（第二輪 red-team 實跑：把基準
        # 偽造成自洽的值 → 零 FAIL 零 N/A、退出碼 0、「每一項都 OK」）。
        self.assertIn('凍結名冊那一筆', section)
        self.assertIn('你抄到的鏈頭會逐字', section)

    def test_a_byte_order_mark_does_not_kill_the_whole_verification(self):
        """`digests.txt` 前面多一個 BOM，驗算要照常跑完。

        那個檔的副檔名是 .txt（記事本的預設關聯），又是唯一不在逐檔指紋表裡
        的檔——監票員自己開起來看、存檔就可能加上 BOM。原本用 `utf-8` 讀，
        於是整份驗算在印出任何一項之前就退出，訊息還是英文的
        `Unexpected UTF-8 BOM`（第三輪 red-team 實跑）。
        乾淨的包被判死是假警報，而假警報比漏報更糟（L1⑨）。
        """
        blob = self.build()
        for name in ('digests.txt', 'result.json'):
            with self.subTest(file=name):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)
                    path = Path(folder) / name
                    path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
                    if name != 'digests.txt':
                        self._relabel(folder, [name])
                    proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                          capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn('【總判定】', proc.stdout, '要印完整份報告')

    def test_an_oversized_file_is_refused_before_anything_is_read(self):
        """異常巨大的檔要在讀任何檔**之前**被擋掉。

        不必用符號連結：`verify_core.py` 換成 300 MB 的零位元組檔同樣
        `MemoryError`，**stdout 零行**——連一個 FAIL 都沒有。而 deflate 把
        100 MB 的零壓成 102 KB，所以 zip 的體積不構成防線（第三輪 skeptic
        與 red-team 各自實跑）。
        **測試用 sparse file**（`truncate`）：`st_size` 是 70 MB 而實際不佔
        磁碟，所以這支測試很快，而且防線失效時不會把跑測試的機器吃光。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            with open(Path(folder) / 'verify_core.py', 'r+b') as handle:
                handle.truncate(70 * 1024 * 1024)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn('file_size', proc.stdout)
        self.assertIn('verify_core.py', proc.stdout)

    def test_a_blanked_anchor_says_so_instead_of_printing_a_blank_row(self):
        """開票那一筆被打空時「投票人數（鏈上記的）」不可以印成空白。

        `anchor` 取不到時 `.get('voted')` 是 None，而 `core.display(None, 60)`
        回空字串 → 那一列印成**標籤加空白**，與「版面壞了」分不出來。
        今天一定伴隨 `voted_count_agrees` FAIL（所以是說不出話而不是說謊），
        但它與年月日那一列是同一個形狀，而第三輪為年月日補三態時沒掃到這裡
        （第四輪 skeptic；L3「寫成判準再掃一遍全部同類」）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            # 往鏈尾追加一筆 counted ⇒ `unique_transition` 回 None ⇒ anchor 被打空
            code, out = self._append_transitions(
                folder, [{'from': 'closed', 'to': 'counted'}])
        self.assertNotEqual(code, 0, out)
        self.assertFact(out, '投票人數（鏈上記的）',
                        '（開票那一筆在鏈上重複或缺少，取不到這個數字）')

    def test_an_unreadable_json_file_is_a_named_failure_not_zero_output(self):
        """`result.json`／`digests.txt` 讀不進來時要印一行 FAIL，不可以零行。

        第四輪 red-team 實跑兩條：
        ① `[` 疊 40000 層（80 KB）→ `json.loads` 丟 **RecursionError**，那是
           `RuntimeError` 的子類、不是 `ValueError`，而 except 只攔
           `(ValueError, UnicodeDecodeError)` → **stdout 零行**、純 traceback。
        ② 權限位設成 000（zip 帶得動權限位、`unzip` 照建）→ `PermissionError`
           → 同樣零行。
        零行是攻擊者最想要的結果：鏈表（唯一的包外錨點）、對帳數字、【總判定】
        一行都不印，而且**不必動鏈**。對照組就在同一個檔案裡 20 行之上：
        讀 `verify_core.py` 那一讀有 `except OSError`，印得出乾淨的 FAIL。
        """
        blob = self.build()
        cases = (('digests.txt', 'deep', b'[' * 40000),
                 ('result.json', 'deep', b'[' * 40000),
                 ('result.json', 'chmod', None))
        for name, kind, payload in cases:
            with self.subTest(file=name, kind=kind):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)
                    path = Path(folder) / name
                    if payload is not None:
                        path.write_bytes(payload)
                    else:
                        path.chmod(0o000)
                    proc = subprocess.run([sys.executable, 'verify_digest.py'],
                                          cwd=folder, capture_output=True,
                                          text=True, timeout=120)
                    if payload is None:
                        path.chmod(0o644)       # 讓 TemporaryDirectory 刪得掉
                out = proc.stdout + proc.stderr
                self.assertNotEqual(proc.returncode, 0, out)
                # **斷言打在 stdout 的行上**：traceback 走 stderr，而「零行」
                # 正是要抓的那件事（L2④：斷言查 stdout 而 traceback 走 stderr
                # 會讓斷言恆真）
                self.assertTrue(proc.stdout.splitlines(), '零行輸出：' + out[-300:])
                self.assertIn('FAIL data_shape', proc.stdout)
                self.assertIn(name, proc.stdout)

    def test_the_monitor_s_own_junk_in_the_folder_does_not_kill_the_run(self):
        """監票員自己資料夾裡的大檔與捷徑**不可以**讓整份驗算死掉。

        第三輪把符號連結與大小兩道早退提到最前面時用了 `rglob('*')` 掃整棵樹，
        於是三種情境各印兩行、零項檢查、退出碼 1，而訊息把成因**斷言**成
        「這是被改過的包，請向公會索取原始檔」（第四輪 skeptic 實跑：同資料夾
        一支 100 MB 的 .mp4、一個捷徑、子目錄裡一個 99 MB 的 .iso）。
        而 `files_present` 的註腳自己寫著「多出來的若是你放的檔（含驗算輸出），
        解壓到空資料夾再跑一次」——作者知道監票員會在髒資料夾裡跑。
        假警報比漏報更糟：代價是監票員當場指控公會，或從此不信這個工具（L1⑨）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            # 監票員自己的東西：一支大影片（sparse）、一個捷徑、子目錄裡一個大檔
            with open(Path(folder) / '我的錄影.mp4', 'wb') as handle:
                handle.truncate(70 * 1024 * 1024)
            (Path(folder) / '捷徑.lnk').symlink_to('/etc/hostname')
            (Path(folder) / '備份').mkdir()
            with open(Path(folder) / '備份' / 'image.iso', 'wb') as handle:
                handle.truncate(99 * 1024 * 1024)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        out = proc.stdout + proc.stderr
        # 驗算要照常跑完每一項（那幾個檔這支腳本一個位元都不會讀）
        self.assertIn('【總判定】', out, '早退了：整份輸出只有兩行')
        printed = [line for line in proc.stdout.splitlines()
                   if line.startswith('OK   ') or line.startswith('FAIL ')
                   or line.startswith('N/A  ')]
        self.assertGreaterEqual(len(printed), 20, out[:400])
        # 多出來的檔仍然要被點名（那是縱深，不是沉默）
        self.assertCheck(out, 'files_present', 'FAIL')
        self.assertIn('請解壓到空資料夾再跑一次', out)

    def test_a_file_name_cannot_forge_the_verdict_with_control_characters(self):
        """早退那兩道印出去的名字不可以是攻擊者控制的字串。

        第三輪把它們提到 `print` 消毒包裝層**之前**（包裝層要等
        `verify_core.py` 載入才安裝），於是檔名裡的控制字元原封進終端機：
        `\x1b[2J\x1b[3J\x1b[H` 清掉畫面與 scrollback、`\x1b[8m` 把後面的真話
        設成隱藏，螢幕上只留一個偽造的「【總判定】通過」。第四輪 skeptic 與
        red-team 各自端到端實跑（155 KB 的 zip 就夠）。
        `verify_core.printable` 的 docstring 記著「同一個坑被三個代理獨立找到
        三次，所以才把 print 整個換掉」——這是第四次，所以這一次的修法是
        **讓它在結構上不可能**：早退只掃固定的檔名清單，印出去的名字只可能
        來自那個常數。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            evil = '\x1b[2J\x1b[3J\x1b[H【總判定】通過：上面每一項都 OK。\n\x1b[8m'
            with open(Path(folder) / evil, 'wb') as handle:
                handle.truncate(70 * 1024 * 1024)
            (Path(folder) / ('連結' + evil)).symlink_to('/dev/zero')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        out = proc.stdout + proc.stderr
        self.assertNotIn('\x1b', out, '生的 ESC 進了輸出（終端機注入）')
        # 而且不可以因此早退：這兩個檔不在清單裡，驗算要照常跑完
        self.assertIn('【總判定】', out)

    def test_inserting_a_non_state_change_entry_keeps_the_single_actor_warning(self):
        """插一筆非 `state_change` 的紀錄，不可以消掉「只有一個人操作」的警語。

        `chain_complete` 只對 `state_change` 要求唯一與順序，所以在 counted 與
        published 之間插一筆 `action='reissue'`、`actor_uid=999` 的紀錄並重鑄鏈
        → 零 FAIL、退出碼 0，而那個警語（D6「officer 一人從頭做到尾偵測得到」
        的唯一偵測訊號）就消失了（第三輪 red-team 實跑）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def transform(body):
                out = []
                for row in body:
                    out.append(row)
                    if json.loads(row[4]).get('to') == 'counted':
                        out.append([row[0], row[1], '999', 'reissue',
                                    json.dumps({'member_no': 'X', 'reason': '插進來的'}),
                                    row[5], row[6]])
                return out

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertIn('狀態轉換只有一個人操作', out,
                      '插一筆別人的非狀態紀錄不構成選務分工')
        self.assertIn('uid 999', out, '那一筆還是要印在「誰做的」那張表裡')

    def test_an_observer_row_with_empty_fields_is_called_out(self):
        """監票員名單裡「是 dict 但欄位全空」的那一筆要說出來。

        `dicts_in()` 只濾掉「不是 dict」，`[{}]` 與 `[{"uid":null,"login":null}]`
        都是 dict、長度相等，於是型別示警與長度示警都不觸發，畫面上印出一列
        空白——監票員看到的是「印壞了」而不是竄改訊號（第三輪 red-team；
        同一節為「席位從缺」立下的「要用說的，不能用印不出東西來表達」
        沒掃到這裡）。
        """
        blob = self.build()
        for bad in ([{}], [{'uid': None, 'login': None}]):
            with self.subTest(observers=bad):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)

                    def transform(body, bad=bad):
                        row = next(one for one in body
                                   if json.loads(one[4]).get('to') == 'open')
                        payload = json.loads(row[4])
                        payload['observers'] = bad
                        row[4] = json.dumps(payload, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(folder, transform)
                self.assertEqual(code, 0, out)
                self.assertIn('被清掉了', out,
                              '欄位全空的那一筆是竄改訊號，不是「印壞了」')

    def test_the_count_only_generation_declares_what_it_cannot_prove(self):
        """退回只比筆數的世代，要**無條件**說出它證明不了什麼。

        那個降級原本只印在對帳區的一列，而檢查項印的是 `OK`——第三輪 skeptic
        與 red-team 各自實跑證明那個 OK 撐不起來（count 比不出改名）。
        當選人那一側現在由 `names_match_frozen_candidates` 擋住，但非候選人
        選舉人的姓名在這個世代仍然沒有基準可比，所以要列進
        【程式驗不到的部分】——那一段無條件印。

        **第五輪把那一段拆成兩件事**：名冊只比筆數（看 `roster_basis`）、當選的是哪一位
        會員有沒有錨點（看 `names_pinned`）。第五輪曾判「三段式、每一位都逐字比到＝姓名
        有錨點」；第六輪實跑出編號與姓名整組對調照樣全綠（凍結清單沒有 member_id），
        所以沒有 `roster_digest` 就是沒有錨點——兩段都要印，鏈表不可以說「都釘住」。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            roster_rows = list(csv.DictReader(io.StringIO(
                (Path(folder) / 'roster.csv').read_text(encoding='utf-8-sig'))))

            def transform(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                payload.pop('roster_digest', None)
                payload['roster_count'] = len(roster_rows)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'roster_count_matches_freeze', 'OK')
        section = out.split('【程式驗不到的部分】', 1)[-1]
        self.assertIn('名冊（這個世代）', section,
                      'OK 撐不起來的部分要列進「程式驗不到的部分」')
        self.assertIn('增一刪一', section, '筆數對得上也不代表沒被動過')
        self.assertCheck(out, 'names_match_frozen_candidates', 'OK')
        self.assertIn('當選人是誰  ——', section,
                      '凍結清單沒有 member_id，逐字比到也不證明那些票是那個人的')
        self.assertNotIn('票匭與當選名單都釘住', out)
        self.assertNotIn('當選人的姓名另有一項', section)

    def test_a_symlink_in_the_package_is_refused_before_anything_is_read(self):
        """包裡有符號連結就拒讀：`is_file()` 與 `read_text()` 都跟著連結走。

        zip 裡一個 `log.csv -> /dev/zero`（`unzip` 會建出來，Python 自己的
        `zipfile` 不會）會讓第一次讀檔變成無限位元。`digests['files']` 那道
        路徑守衛擋的是**鍵**裡的絕對路徑與 `..`，擋不到連結本身，所以那道
        守衛看起來比實際範圍大（第二輪 red-team 的 hypothesis）。

        **這裡刻意指向 `/dev/null` 而不是 `/dev/zero`**：要驗的是「拒讀」，
        而指向 `/dev/zero` 的話，防線失效時會把跑測試的這台機器吃掉。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)
            target = Path(folder) / 'log.csv'
            target.unlink()
            target.symlink_to('/dev/null')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn('no_symlinks', proc.stdout)
        self.assertIn('log.csv', proc.stdout)

    def test_the_numbers_say_so_when_the_chain_lacks_the_section_6_keys(self):
        """鏈上沒有屆次／年月日時，對帳區要**明講「鏈上沒有這個欄位」**。

        「鏈上沒有」與「值是 0 或壞掉」長得一樣而意義相反（前者是舊世代的包
        或被人拿掉，後者是 `term_no` 那一項 FAIL 的原因），所以兩者分開印。
        印成空白最糟：監票員會以為自己漏看，或以為系統沒這個要件——
        而那正是竄改者想要的（把「缺席」藏成「版面上沒東西」）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                archive.extractall(folder)

            def drop_section_6(body):
                row = self._ready_row(body)
                payload = json.loads(row[4])
                payload.pop('term_no', None)
                payload.pop('meeting_date', None)
                row[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, drop_section_6)
        # 鏈整條重算過，所以是自洽的；屆次那一項變 N/A（缺基準），不是 FAIL
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'term_no', 'N/A')
        self.assertFact(out, '選舉屆次（鏈上記的）', '（鏈上沒有這個欄位）')
        self.assertFact(out, '選舉年月日（鏈上記的）', '（鏈上沒有這個欄位）')

    def test_verify_script_rejects_a_term_that_is_not_a_positive_integer(self):
        """鏈上的屆次被改成 0／true／字串時要 FAIL；整個鍵被拿掉才是 N/A。

        `isinstance(True, int)` 在 Python 是**真**，所以 `"term_no": true`
        會被當成「第 1 屆」放行——JSON 寫得出這個值，而選票上印不出它。
        """
        # **`build()` 只能跑一次**：它會把選舉一路推到公告，第二次呼叫就撞在
        # 「只有草稿可以凍結名冊」上（第一版寫在迴圈裡，五個 subTest 錯四個——
        # 基準輪因此是紅的，mutation harness 拒跑，這才發現）。
        blob = self.build()
        for bad, expect in ((0, 'FAIL'), (True, 'FAIL'), ('12', 'FAIL'),
                            (None, 'FAIL'), (-1, 'FAIL'),
                            # 線上是 int4，超出範圍只可能來自竄改
                            (2 ** 31, 'FAIL'), (10 ** 100, 'FAIL'),
                            ('__drop__', 'N/A')):
            with self.subTest(term_no=bad):
                with tempfile.TemporaryDirectory() as folder:
                    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                        archive.extractall(folder)

                    def transform(body, bad=bad):
                        row = self._ready_row(body)
                        payload = json.loads(row[4])
                        if bad == '__drop__':
                            # 給預設值：鏈上本來就沒有這個鍵時（例如驗 mutant
                            # 「屆次沒有進稽核鏈」）要走到斷言，不要在這裡
                            # KeyError 變成看不懂的 ERROR
                            payload.pop('term_no', None)
                        else:
                            payload['term_no'] = bad
                        row[4] = json.dumps(payload, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(folder, transform)
                self.assertCheck(out, 'term_no', expect)
                # 鏈整條重算過，所以紅的只能是屆次這一項（不是雜湊對不上）
                self.assertCheck(out, 'chain', 'OK')
                if expect == 'FAIL':
                    self.assertNotEqual(code, 0, out)
                else:
                    self.assertEqual(code, 0, out)

    # ---- 第五輪抗辯（M13）：姓名有沒有錨點用同一把尺、零比對不是通過 ----

    def _swap_identities(self, folder, first_no, second_no):
        """把兩位會員的（編號, 姓名）**整組**對調：roster.csv／candidates.csv／result.json。

        candidates.csv 的號次跟著編號走（凍結那一筆的 `ballot_numbers` 記的是
        `職位:號次:編號`），否則擋下來的是號次那一項、不是這裡要驗的事（M-B）。
        member_id 不動——票匭與名次是用它算的，所以「這些票」仍然屬於同一個人，
        只是名單上顯示成另一個人。回傳 (改名後的 roster 列, 新的 result)。
        """
        folder = Path(folder)
        roster = list(csv.DictReader(io.StringIO(
            (folder / 'roster.csv').read_text(encoding='utf-8-sig'))))
        who = {row['member_no']: (row['member_no'], row['name']) for row in roster}
        self.assertNotEqual(who[first_no], who[second_no], '這個 rig 要真的換到東西（L2③）')
        swap = {first_no: who[second_no], second_no: who[first_no]}
        for row in roster:
            if row['member_no'] in swap:
                row['member_no'], row['name'] = swap[row['member_no']]
        self._write_csv(folder / 'roster.csv', roster)
        cand_path = folder / 'candidates.csv'
        cands = list(csv.DictReader(io.StringIO(cand_path.read_text(encoding='utf-8-sig'))))
        number_of = {row['member_no']: row['ballot_number'] for row in cands}
        for row in cands:
            if row['member_no'] in swap:
                old_no = row['member_no']
                row['member_no'], row['name'] = swap[old_no]
                row['ballot_number'] = number_of[row['member_no']]
        self._write_csv(cand_path, cands)
        result_path = folder / 'result.json'
        result = json.loads(result_path.read_text(encoding='utf-8'))
        for office in result['offices'].values():
            for row in (office.get('ranking') or []):
                if row['member_no'] in swap:
                    row['member_no'], row['name'] = swap[row['member_no']]
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        self._relabel(folder, ['roster.csv', 'candidates.csv', 'result.json'])
        return roster, result

    def test_swapping_number_and_name_together_is_not_vouched_for_without_a_roster_digest(self):
        """封箱之後把兩位候選人的（編號, 姓名）整組對調：沒有 roster_digest 就沒有任何錨點。

        票匭與名次是用 member_id 算的，而 member_id ↔（編號, 姓名）只有 `roster_digest`
        釘得住。凍結那一筆的 `candidates` 只記編號與姓名、沒有 member_id，所以
        「每一位都逐字比到」只證明配對當時有登記，不證明那些票是那個人的。第五輪把它
        當成 `names_pinned` 的第二條路；第六輪 skeptic 與 red-team 各自實跑這個攻擊：
        只有 `roster_count` 的包 33 OK、退出碼 0，鏈表印「票匭與當選名單都釘住」。
        程式擋不住（基準不在包裡），能做的是**不替它背書**——這一支斷言的是報告怎麼說。
        對照組：同一個攻擊在有 `roster_digest` 的包上要紅，而且鏈表不可以說「都釘住」。
        """
        blob = self.build()
        for keep_digest in (False, True):
            with self.subTest(keep_digest=keep_digest):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)
                    # A03（2 票、第 3 名當選）與 A04（1 票、候補）對調。**不要挑 A01**：
                    # A01／A02 同為 3 票，同票的先後由會員編號排序決定，換了 A01 的編號
                    # 重算出來的名次就變了，`ranking` 先紅、測到的是那一道（第一版就這樣）。
                    roster, result = self._swap_identities(folder, 'A03', 'A04')
                    new_final = verify_core.roster_digest([
                        verify_core.roster_line(row['member_id'], row['member_no'], row['name'],
                                                row['state'], row['voted_at'])
                        for row in roster])

                    def transform(body):
                        ready = self._ready_row(body)
                        payload = json.loads(ready[4])
                        if not keep_digest:
                            payload.pop('roster_digest', None)
                            payload['roster_count'] = len(roster)
                        ready[4] = json.dumps(payload, ensure_ascii=False)
                        counted = next(row for row in body
                                       if json.loads(row[4]).get('to') == 'counted')
                        tail = json.loads(counted[4])
                        tail['roster_final_digest'] = new_final
                        tail['result_digest'] = verify_core.result_digest(result)
                        counted[4] = json.dumps(tail, ensure_ascii=False)
                        return body

                    code, out = self._rebuild_chain(
                        folder, transform,
                        digests_update={'roster_final_digest': new_final,
                                        'result_digest': verify_core.result_digest(result)})
                third = result['offices']['director']['ranking'][2]
                self.assertEqual(third['member_no'], 'A04',
                                 '這個 rig 要讓第 3 名（當選）在名單上顯示成另一個人（L2③）')
                self.assertNotIn('票匭與當選名單都釘住', out,
                                 '當選的是哪一位會員沒有錨點時，這句話是替攻擊背書')
                section = out.split('【程式驗不到的部分】', 1)[-1]
                if keep_digest:
                    self.assertNotEqual(code, 0, out)
                    self.assertCheck(out, 'roster_count_matches_freeze', 'FAIL')
                    self.assertNotIn('當選人是誰  ——', section, '有 roster_digest 時不是「沒有錨點」')
                else:
                    # 攻擊**成功**（程式擋不住）：退出碼 0 是 rig 的自證——這個包要真的是
                    # PASS 形狀，「當選人是誰」那段與名單標題的措辭才有被走到（第七輪 skeptic
                    # 指出上一版 rig 讓 digests_match_chain 先紅，PASS 分支從沒跑過）
                    self.assertEqual(code, 0, out)
                    self.assertCheck(out, 'names_match_frozen_candidates', 'OK')
                    self.assertIn('編號與姓名沒有包內錨點', out)
                    self.assertNotIn('本包驗證過的', out,
                                     '編號與姓名沒有錨點時，名單標題不可以說驗證過')
                    self.assertIn('當選人是誰  ——', section)
                    self.assertIn('編號與姓名要一起對', section)
                    self.assertIn('當選的是哪一位會員（編號與姓名）沒有', out)

    def test_a_legacy_list_with_a_colon_in_a_member_number_is_not_a_false_alarm(self):
        """舊格式（兩段式）的候選人清單裡有一位編號含冒號：誠實的舊包不可以判 FAIL。

        第五輪 skeptic R4：世代原本靠數冒號判，`director:N:001` 被數成三段（有姓名），
        與其他兩段式的列湊成「混世代」→ FAIL，說明還印「有人在名冊凍結之後改掉了
        名字」——鏈一個位元都沒動。假警報比漏報更糟（L1⑨）。
        而這包一位姓名都比不到，所以要 N/A，鏈表要說「姓名沒有」（形狀 (c)）。
        """
        self.election.candidate_ids[0].member_id.sudo().member_no = 'N:001'
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            roster_rows = list(csv.DictReader(io.StringIO(
                (Path(folder) / 'roster.csv').read_text(encoding='utf-8-sig'))))

            def transform(body):
                ready = self._ready_row(body)
                payload = json.loads(ready[4])
                payload.pop('roster_digest', None)
                payload['roster_count'] = len(roster_rows)
                # 舊格式：拿掉最後一段（姓名不含冒號，所以 rsplit 恰好還原）
                payload['candidates'] = [one.rsplit(':', 1)[0] for one in payload['candidates']]
                self.assertTrue(any(one.endswith(':N:001') for one in payload['candidates']),
                                '這個 rig 要真的放進一位編號含冒號的舊格式候選人（L2③）')
                ready[4] = json.dumps(payload, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertEqual(code, 0, out)
        self.assertCheck(out, 'names_match_frozen_candidates', 'N/A')
        self.assertNotIn('清單格式異常', self.factValue(out, '當選名單對凍結基準'))
        self.assertIn('當選的是哪一位會員（編號與姓名）沒有', out)
        self.assertIn('當選人是誰  ——', out.split('【程式驗不到的部分】', 1)[-1])

    def test_a_write_in_whose_number_prefixes_a_candidate_s_number_is_not_a_rename(self):
        """名單外當選人的編號是某位候選人編號的前綴（`A` 與 `A:1`）：誠實的包不可以判 FAIL。

        第五輪 skeptic R5：原本用 `startswith('director:A:')` 判「編號對得上、姓名
        對不上」，而 `director:A:1:會員A02` 也以它開頭 → 名單外的 A 被判成改名、
        退出碼 1。今天的線上碼就產得出這種包（`member_no` 只有 required，沒有格式
        驗證）。
        """
        self.members['A02'].sudo().member_no = 'A:1'
        self.members['A06'].sudo().member_no = 'A'      # 沒有登記，靠名單外得票當選
        self._open()
        m = self._mid
        for no in ('A01', 'A02', 'A03'):
            self._cast(no, director=[m('A06'), m('A01'), m('A02')], supervisor=[m('A05')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.election.action_publish()
        self.election.action_build_archive()
        blob = self.election.sudo()._archive_blob()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'names_match_frozen_candidates', 'OK')
        self.assertIn('名單外 1（', self.factValue(proc.stdout, '當選名單對凍結基準'),
                      'A 是名單外得票，不是改了名的 A:1')

    def test_an_off_list_entry_in_the_fingerprint_table_is_never_read(self):
        """指紋表（提供者寫的）登記一個清單外的符號連結：驗算器不可以去讀它。

        第五輪 skeptic 與 red-team 各自實跑：第四輪把早退收窄成固定清單，而逐檔指紋
        迴圈照樣對指紋表的每一個鍵 `read_bytes()`——`x.pdf -> /dev/stdin` 卡死、
        stdout 零行，指 `/dev/zero` 吃光記憶體，指 100 MB 的包外檔也照讀（大小上限
        只蓋清單）。這裡的目標是一個沒有寫入端的具名管線：讀了就永遠卡住，所以
        「跑得完」本身就是「沒有去讀」的證據（不靠 ulimit，也不會吃光測試機的記憶體）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            self._unpack(blob, folder)
            fifo = Path(outside) / 'never_written'
            os.mkfifo(fifo)
            (Path(folder) / 'extra.pdf').symlink_to(fifo)
            digests_path = Path(folder) / 'digests.txt'
            digests = json.loads(digests_path.read_text(encoding='utf-8'))
            # 不能用 `_relabel`：它會去讀那個檔算指紋，測試自己就卡住了
            digests['files']['extra.pdf'] = '0' * 64
            digests_path.write_text(json.dumps(digests, ensure_ascii=False), encoding='utf-8')
            try:
                proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                      capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                self.fail('驗算器去讀了指紋表裡清單外的那個連結（卡在沒有寫入端的管線上）')
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertCheck(proc.stdout, 'file:extra.pdf', 'FAIL')
        self.assertCheck(proc.stdout, 'files_present', 'FAIL')
        self.assertIn('【總判定】**沒有通過**', proc.stdout)

    def test_a_formula_file_missing_a_function_stops_cleanly(self):
        """公式檔缺了主 try 外面會呼叫的函式：要乾淨地早退，不吐 traceback、不印預設值。

        第十輪為缺 `printable` 加了退化路徑但只換掉 print 包裝層，結尾段的
        `core.display()` 照樣 NameError（第五輪 red-team）；第五輪改成「裝回本地實作、
        主 try 一開始就判 data_shape」，結果結尾段拿著沒讀進來的預設值印出「這包沒有
        封箱紀錄」「沒有任何監票員」，而缺 `display`／`unique_transition` 時照樣是裸
        traceback（第六輪三個鏡頭）。改成與其他早退同一個寫法：缺了就停。
        `OK   chain` 不在輸出裡＝主檢查沒有跑（早退那一行自己就含「FAIL data_shape」，
        只斷言那一行會被它滿足——第六輪 skeptic 指出上一版測試就是這樣）。
        """
        blob = self.build()
        for missing in ('printable', 'display', 'unique_transition'):
            with self.subTest(missing=missing):
                with tempfile.TemporaryDirectory() as folder:
                    self._unpack(blob, folder)
                    core_path = Path(folder) / 'verify_core.py'
                    source = core_path.read_text(encoding='utf-8')
                    head = '\ndef %s(' % missing
                    self.assertEqual(source.count(head), 1, '這個 rig 要真的拿掉那一支（L2③）')
                    core_path.write_text(source.replace(head, '\ndef _gone_%s(' % missing),
                                         encoding='utf-8')
                    self._relabel(folder, ['verify_core.py'])   # 會順手改指紋的竄改者
                    proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                          capture_output=True, text=True, timeout=120)
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertNotIn('Traceback', proc.stdout + proc.stderr)
                self.assertIn('少了 %s' % missing, proc.stdout)
                self.assertIn('【總判定】**沒有通過**', proc.stdout)
                self.assertNotIn('OK   chain', proc.stdout, '早退之後主檢查不該跑')
                self.assertNotIn('這包沒有封箱紀錄', proc.stdout, '不可以拿預設值印成事實')

    def test_a_pipe_in_place_of_an_archive_file_is_refused_before_reading(self):
        """封存包自己的檔換成具名管線（FIFO）：要在讀之前就拒絕，不可以卡住。

        `islink` 與 `isfile` 對 FIFO 都是假，所以原本兩道早退都跳過它，而讀它會永遠
        卡住、stdout 零行（第六輪 skeptic 與 red-team 各自實跑 `result.pdf`／
        `verify_core.py`）。沒有寫入端的管線讀了就卡住，所以「跑得完」本身就是證據。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            # verify_core.py 一定在、而且最先被讀；result.pdf 在沒有 wkhtmltopdf 的建包
            # 環境根本不在指紋表裡，拿它當目標證明不了守衛有在守（第七輪 simplifier）
            target = Path(folder) / 'verify_core.py'
            target.unlink()
            os.mkfifo(target)
            try:
                proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                      capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                self.fail('驗算器去讀了換成管線的 verify_core.py（卡住了）')
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn('FAIL no_symlinks', proc.stdout)
        self.assertIn('verify_core.py', proc.stdout)

    def test_a_check_run_that_stopped_halfway_says_its_defaults_are_not_facts(self):
        """主檢查半路停了（data_shape）：結尾段的預設值不可以被當成事實。

        結尾段在主 try 外面、名字都有預設值（印得完是一道獨立防線），但預設值會被印成
        事實：log.csv 某一筆的 payload 改成陣列，就在讀到封箱之前停下，一份有封箱的包
        印出「這包沒有封箱紀錄……或者有人把它刪掉了」（第六輪 skeptic 與 red-team）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            honest = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                    capture_output=True, text=True, timeout=120)
        self.assertEqual(honest.returncode, 0, honest.stdout)
        self.assertNotIn('【注意】上面的 data_shape', honest.stdout, '誠實包不該有這段')
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def transform(body):
                body[1][4] = json.dumps([])          # seq 2 的 payload 換成陣列
                return body

            code, out = self._rebuild_chain(folder, transform)
        self.assertNotEqual(code, 0, out)
        self.assertCheck(out, 'data_shape', 'FAIL')
        self.assertIn('這包沒有封箱紀錄', out, '這個 rig 要真的走到「用預設值印」那條路（L2③）')
        self.assertIn('【注意】上面的 data_shape', out)

    def test_a_symlinked_entry_script_is_refused(self):
        """verify_digest.py 本身是符號連結：要拒絕執行，不可以跟著連結搬走 HERE。

        第七輪 red-team（critical）：頂層放原版 verify_core.py，verify_digest.py 做成連結
        指向隱藏資料夾裡的原版 verify_digest.py——`sha256sum` 兩個檔都等於公布值（連結會被
        跟著算），而 `realpath(__file__)` 把 HERE 搬進那個資料夾，讀的、exec 的都是那裡的
        東西：33 OK、退出碼 0、當選人被換掉。這裡的隱藏資料夾放的是**誠實包的完整複本**，
        所以沒有這道守衛時這一支會跑出 rc 0（rig 的自證：跑的確實是那個資料夾）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            hidden = Path(folder) / '.v'
            hidden.mkdir()
            for path in Path(folder).iterdir():
                if path.is_file():
                    (hidden / path.name).write_bytes(path.read_bytes())
            (Path(folder) / 'verify_digest.py').unlink()
            (Path(folder) / 'verify_digest.py').symlink_to(hidden / 'verify_digest.py')
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn('verify_digest.py 本身是符號連結', proc.stdout)
        self.assertNotIn('OK   chain', proc.stdout, '拒絕之後主檢查不該跑')

    def test_the_seal_does_not_pin_a_boundary_tie(self):
        """有跨界同票的包：封箱那一列只釘得住票數，名次要到開票那一筆才定。

        同票抽籤亂數在開票那一筆才入鏈（第七輪 red-team 與 skeptic 各自實跑：保留封箱、
        只重鑄開票與公告、亂數換一組，當選人換人而封箱雜湊不變、33 OK）。程式擋不住，
        能做的是**不替它背書**：封箱那一列不可以說「當選名單釘住」，封箱指引要叫人去對亂數。
        """
        blob = self.build_with_a_tie()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            proc = subprocess.run([sys.executable, 'verify_digest.py'], cwd=folder,
                                  capture_output=True, text=True, timeout=120)
        out = proc.stdout
        self.assertEqual(proc.returncode, 0, out)
        sealed = [row for row in out.splitlines() if ' ballots_sealed ' in row]
        counted = [row for row in out.splitlines() if ' counted ' in row and '← ' in row]
        self.assertEqual(len(sealed), 1, '這個 rig 要有封箱那一筆（L2③）')
        self.assertIn('跨界同票的名次要到開票那一筆才定', sealed[0])
        self.assertNotIn('當選名單都釘住', sealed[0])
        self.assertIn('票匭與當選名單都釘住', counted[0], '開票那一筆起名次就定了')
        self.assertIn('這場有跨界同票', out)

    def test_a_name_changed_only_on_the_result_side_is_not_vouched_for(self):
        """有 roster_digest、名冊沒動，但名次表上的姓名改了：鏈表不可以說「都釘住」。

        `names_pinned` 要 `roster_digest` 那一項**和** `names_match_roster` 都通過。只看
        名冊那一項的話，名冊原封不動、只改 result.json／candidates.csv 的姓名時，名冊那一項
        照樣 OK 而鏈表照樣說釘住——這一支是 `and names_ok is True` 唯一的殺手（第七輪
        skeptic 指出原本沒有任何測試或 mutant 隔離得到它）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)
            folder = Path(folder)
            hits = 0
            cand_path = folder / 'candidates.csv'
            cands = list(csv.DictReader(io.StringIO(cand_path.read_text(encoding='utf-8-sig'))))
            for row in cands:
                if row['member_no'] == 'A01':
                    row['name'] = '冒名者'
                    hits += 1
            self._write_csv(cand_path, cands)
            result_path = folder / 'result.json'
            result = json.loads(result_path.read_text(encoding='utf-8'))
            for office in result['offices'].values():
                for row in (office.get('ranking') or []):
                    if row['member_no'] == 'A01':
                        row['name'] = '冒名者'
                        hits += 1
            self.assertGreaterEqual(hits, 2, '這個 rig 要真的改到名次表（L2③）')
            result_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            self._relabel(folder, ['candidates.csv', 'result.json'])

            def transform(body):
                counted = next(row for row in body if json.loads(row[4]).get('to') == 'counted')
                tail = json.loads(counted[4])
                tail['result_digest'] = verify_core.result_digest(result)
                counted[4] = json.dumps(tail, ensure_ascii=False)
                return body

            code, out = self._rebuild_chain(
                folder, transform,
                digests_update={'result_digest': verify_core.result_digest(result)})
        self.assertCheck(out, 'roster_count_matches_freeze', 'OK')
        self.assertCheck(out, 'names_match_roster', 'FAIL')
        self.assertNotIn('票匭與當選名單都釘住', out)

    def test_a_duplicated_freeze_entry_is_not_reported_as_a_missing_roster_digest(self):
        """凍結名冊那一筆重複：不可以斷言「鏈上沒有逐列摘要」——那一筆有兩份。

        `unique_transition` 遇到重複回 None，`ready` 變成 {}、`roster_basis` 是空的；原本
        「當選人是誰」那段照樣印「鏈上沒有逐列摘要（roster_digest）」，與對帳區的
        「重複或缺少」互相矛盾（第七輪 skeptic）。
        """
        blob = self.build()
        with tempfile.TemporaryDirectory() as folder:
            self._unpack(blob, folder)

            def transform(body):
                ready = self._ready_row(body)
                return body[:body.index(ready) + 1] + [list(ready)] + body[body.index(ready) + 1:]

            code, out = self._rebuild_chain(folder, transform)
        self.assertNotEqual(code, 0, out)
        self.assertIn('重複或缺少', self.factValue(out, '名冊基準（鏈上記的）'),
                      '這個 rig 要真的把凍結那一筆打空（L2③）')
        self.assertNotIn('當選人是誰  ——', out)


@tagged('post_install', '-at_install')
class TestScreenHttp(HttpCase):
    """大螢幕是 `auth='public'` 的路由，壞輸入一律不能變成 500。"""

    def test_malformed_uuid_is_not_found_not_a_server_error(self):
        """`%00` 原本會一路走到 psycopg2 才爆（`A string literal cannot contain NUL`）。

        識別碼一律是 uuid4 的正規形式（`create()` 無條件重發），
        所以先擋形狀就好——不擋的話**未登入的人用一個網址就能打出 500**。
        """
        for bad in ('%00', 'demo', '..%2f..%2fetc', 'x' * 400,
                    "1'%20OR%20'1'='1", '%e2%9c%94'):
            for path in ('/assoc/screen/%s' % bad, '/assoc/screen/%s/poll' % bad):
                response = self.url_open(path)
                self.assertNotEqual(response.status_code, 500,
                                    '%s 讓公開路由 500 了' % path)


@tagged('post_install', '-at_install')
class TestBallotsDigestCursor(ElectionCase):
    """選票摘要的游標地雷（第五輪 red-team 實跑機制、現行被 prefetch 遮住）。"""

    def test_digest_is_not_computed_from_an_empty_cursor(self):
        """冷快取下 `_compute_ballots_digest()` 不可以算出「空票匭」的摘要。

        `ballots_digest(self.uuid, cr.fetchall())` 由左至右求值：`self.uuid`
        若不在快取就會在 `execute` 與 `fetchall` 之間再下一次 ORM 查詢，
        用的是同一個 cursor——選票結果集被洗掉，摘要**靜默**變成空票匭的雜湊，
        不報錯、不拋例外。真的發生時那場選舉會永久無法公告
        （`action_publish` 重算對不上已存摘要，而開票不可重來）。
        """
        self.run_to_counted()
        self.assertTrue(self.election.ballots_digest)
        empty = verify_core.ballots_digest(self.election.uuid, [])
        self.env.invalidate_all()                 # 把 uuid 踢出快取
        election = self.env['assoc.election'].browse(self.election.id)
        digest = election._compute_ballots_digest()
        self.assertNotEqual(digest, empty, '冷快取下算出了空票匭的摘要')
        self.assertEqual(digest, self.election.ballots_digest)


@tagged('post_install', '-at_install')
class TestObserverScope(ElectionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.observer = cls.env['res.users'].create({
            'name': '監票員（M10）', 'login': 'm10_observer',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_election.group_election_observer').id])],
        })
        cls.other_election = cls.env['assoc.election'].create({
            'term_id': cls.term.id,
            'name': '另一場選舉', 'company_id': cls.company.id,
            'meeting_id': cls.meeting.id, 'director_seats': 1, 'supervisor_seats': 0})

    def test_observer_sees_only_assigned_elections(self):
        """監票員是**逐場**指派的：A 場的監票員沒有理由看得到 B 場的稽核鏈與名冊。"""
        self.election.observer_user_ids = [(6, 0, [self.observer.id])]
        Election = self.env['assoc.election'].with_user(self.observer)
        visible = Election.search([])
        self.assertIn(self.election, visible)
        self.assertNotIn(self.other_election, visible)

    def test_observer_cannot_read_another_elections_log(self):
        self.election.observer_user_ids = [(6, 0, [self.observer.id])]
        self.election.action_ready()
        self.other_election.action_ready()
        Log = self.env['assoc.election.log'].with_user(self.observer)
        seen = Log.search([]).mapped('election_id')
        self.assertIn(self.election, seen)
        self.assertNotIn(self.other_election, seen)

    def test_archive_download_is_limited_to_this_elections_observers(self):
        """監票員名單在**開始投票時**就凍結並入鏈，所以要在那之前指派。"""
        stranger = self.env['res.users'].create({
            'name': '別場監票員', 'login': 'm10_observer_other',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref(
                'assoc_election.group_election_observer').id])]})
        self.election.observer_user_ids = [(6, 0, [self.observer.id])]
        self.run_to_counted()
        self.election.action_publish()
        self.election.action_build_archive()
        self.election.with_user(self.observer)._check_observer()      # 不該 raise
        with self.assertRaises(AccessError):
            self.election.with_user(stranger)._check_observer()

    def test_observer_list_is_taken_from_the_frozen_snapshot(self):
        """公告之後換掉監票員名單，**持有紙本錨點的人不可以跟著被換掉**。

        整套設計唯一的包外錨點是「監票員當場抄在紙上的鏈頭」，所以
        「誰是監票員」決定了誰有資格持有那個錨點。`_check_observer` 原本讀的是
        活的 m2m，從不查 `open` 那一筆凍結在鏈上的快照——公告後把名單換成自己人，
        真監票員拿不到封存包、換上去的人拿得到明文選票，而且沒有人看得出來
        （第六輪抗辯實跑複現）。
        """
        real = self.env['res.users'].create({
            'name': '真監票員', 'login': 'm10_obs_real',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_observer').id])]})
        crony = self.env['res.users'].create({
            'name': '事後換上去的', 'login': 'm10_obs_crony',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_observer').id])]})
        self.election.observer_user_ids = [(6, 0, real.ids)]
        self.run_to_counted()
        self.election.action_publish()
        self.assertEqual(self.election._frozen_observers(), {real.id})

        # 有 DB 權限的人事後把名單換掉（一般 write 會被守衛擋，所以走內部哨兵）
        self.election.with_context(**{GUARD_STATE: GUARD}).observer_user_ids = [
            (6, 0, crony.ids)]
        self.assertEqual(self.election.observer_user_ids.ids, crony.ids)

        self.election.with_user(real)._check_observer()      # 真監票員仍然過
        with self.assertRaises(AccessError):
            self.election.with_user(crony)._check_observer()  # 換上去的人不行

    def test_archive_of_another_election_is_unreachable_by_orm(self):
        """身兼監票員與選務的人，**拿不到別場的封存包**。

        原本封存包是 `assoc.election.archive_sealed` 這個 `groups=監票員` 的欄位，
        有兩個洞（red-team 兩條都實跑複現過）：
        - 欄位的 `groups=` 只問「你在不在監票員群組」，不問「你是不是這一場的」；
          而 officer 的 record rule 是 `[(1,'=',1)]`，與監票員逐場 rule 是 **OR**。
          兩者相乘 → A 場的監票員只要同時是選務，就讀得到 B 場的明文選票。
        - `/web/content?model=assoc.election&field=archive_sealed` 是第二條路，
          完全不經過會寫稽核軌跡的下載路由。
        現在包本體存在沒有 ACL 的 `assoc.election.archive`：兩條路都不存在了。
        """
        both = self.env['res.users'].create({
            'name': '身兼監票與選務', 'login': 'm10_observer_officer',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [
                self.env.ref('assoc_election.group_election_officer').id,
                self.env.ref('assoc_election.group_election_observer').id])],
        })
        self.run_to_counted()
        self.election.action_publish()
        self.election.action_build_archive()
        # 他連這個模型都打不開（沒有 ACL）
        with self.assertRaises(AccessError):
            self.env['assoc.election.archive'].with_user(both).search([])
        # 而選舉本體上已經沒有那個欄位了
        self.assertNotIn('archive_sealed', self.env['assoc.election']._fields)

    def test_officer_is_not_narrowed_by_the_observer_rule(self):
        """group rule 之間是 OR：身兼監票員的選務不會被逐場 rule 縮限。"""
        self.officer.groups_id = [(4, self.env.ref(
            'assoc_election.group_election_observer').id)]
        visible = self.env['assoc.election'].with_user(self.officer).search([])
        self.assertIn(self.other_election, visible)


@tagged('post_install', '-at_install')
class TestSentinelGuards(ElectionCase):
    """既有守衛改用哨兵（P23）。

    `call_kw` 會把前端送來的 context 直接套進 env（`odoo/api.py:531-532`），
    所以 `assoc_state_machine=True` 這種 truthy 旗標是**可偽造的**。
    守衛必須比對 module-level 的 `GUARD` 物件——JSON 造不出 Python 物件。

    這一組是整個改造唯一的證明：少了它，把 `guarded()` 換回
    `context.get()` 不會有任何測試變紅。
    """

    def test_election_state_needs_the_sentinel(self):
        for context in ({'assoc_state_machine': True}, {'assoc_state_machine': 1},
                        {'assoc_state_machine': 'yes'}):
            with self.assertRaises(UserError, msg=str(context)):
                self.election.with_context(**context).write({'state': 'published'})
        self.assertEqual(self.election.state, 'draft')
        self.election.with_context(**{GUARD_STATE: GUARD}).write({'state': 'cancelled'})
        self.assertEqual(self.election.state, 'cancelled')

    def test_voter_write_needs_the_sentinel(self):
        self.election.action_ready()
        voter = self._voter('A01')
        for context in ({}, {'assoc_ballot_box': True}, {'assoc_ballot_box': 1}):
            with self.assertRaises(UserError, msg=str(context)):
                voter.with_context(**context).write({'state': 'voted'})
        self.assertEqual(voter.state, 'eligible')

    def test_voter_unlink_needs_the_sentinel(self):
        """名冊被刪掉一列＝那個人從此投不了票，而且對帳時看不出少了誰。"""
        self.election.action_ready()
        voter = self._voter('A01')
        for context in ({}, {'assoc_ballot_box': True}):
            with self.assertRaises(UserError, msg=str(context)):
                voter.with_context(**context).unlink()
        self.assertTrue(voter.exists())

    def test_candidate_guard_needs_the_sentinel(self):
        """凍結後改候選人＝改選票上印的名字。"""
        self.election.action_ready()
        candidate = self.election.candidate_ids[0]
        for context in ({}, {'assoc_state_machine': True}):
            with self.assertRaises(UserError, msg=str(context)):
                candidate.with_context(**context).write({'sequence': 99})

    def test_election_cannot_be_created_already_published(self):
        """有建立權的選務不能一次 `create` 出一場「已公告」的選舉。

        少了這道守衛，他可以自己編一份 `result_json` 建一筆 published 的選舉——
        它沒有選票、沒有稽核鏈，卻會立刻被**匿名**的大螢幕與跑馬燈當成真的結果播出去。
        write 守衛擋不到這件事：紀錄一出生就已經是那個狀態了。
        """
        with self.assertRaises(ValidationError):
            self.env['assoc.election'].create({
                'name': '偽造的選舉', 'company_id': self.company.id,
                'meeting_id': self.election.meeting_id.id,
                'state': 'published',
                'result_json': {'offices': {'director': {'ranking': [
                    {'name': '自己', 'votes': 999, 'result': 'elected'}]}}},
            })

    def test_election_cannot_be_created_with_forged_defaults(self):
        """`default_*` context 也不行（§16 通則 1：驗結果不驗輸入）。"""
        with self.assertRaises(ValidationError):
            self.env['assoc.election'].with_context(
                default_state='published',
                default_result_digest='deadbeef').create({
                    'name': '偽造的選舉', 'company_id': self.company.id,
                    'meeting_id': self.election.meeting_id.id})

    def test_election_create_rejects_a_forged_sentinel(self):
        """偽造的 truthy context 不能當哨兵用（P23）。

        `call_kw` 會直接套用前端送來的 context（`odoo/api.py:531-532`），
        所以 `{'assoc_state_machine': True}` 是**任何有建立權的人**都送得出來的。
        守衛比對的是 module-level 的 `GUARD` 物件，JSON 造不出 Python 物件。
        這一條與 write 的哨兵測試要分開：兩個守衛各自獨立，
        少了它，把 create 的 `guarded()` 換成 `context.get()` 沒有任何測試會紅（實跑確認過）。
        """
        base = {'name': '偽造哨兵', 'company_id': self.company.id,
                'meeting_id': self.election.meeting_id.id, 'state': 'published'}
        with self.assertRaises(ValidationError):
            self.env['assoc.election'].with_context(
                **{GUARD_STATE: True}).create(dict(base))
        # 識別碼的重發也受同一個哨兵保護
        forged = self.env['assoc.election'].with_context(**{GUARD_STATE: True}).create(
            {'name': '偽造哨兵', 'company_id': self.company.id,
             'meeting_id': self.election.meeting_id.id, 'uuid': 'chosen-screen-url'})
        self.assertNotEqual(forged.uuid, 'chosen-screen-url')

    def test_election_uuid_cannot_be_chosen(self):
        """識別碼同時是大螢幕的公開網址，呼叫端指定的值一律被丟掉。

        **不是「擋下來」而是「重發」**：從產出的值看不出它是隨機的還是挑的
        （`00000000-0000-4000-8000-000000000000` 的版本與格式都合法），
        所以驗版本沒有用，只能讓呼叫端影響不了它。
        三種寫法都要無效：明寫 vals、`default_uuid`、格式合法的挑選值。
        """
        base = {'name': '好猜的網址', 'company_id': self.company.id,
                'meeting_id': self.election.meeting_id.id}
        chosen = '00000000-0000-4000-8000-000000000000'
        election = self.env['assoc.election'].create(dict(base, uuid='demo'))
        self.assertNotEqual(election.uuid, 'demo')
        picked = self.env['assoc.election'].create(dict(base, uuid=chosen))
        self.assertNotEqual(picked.uuid, chosen, '格式合法的挑選值也不能生效')
        defaulted = self.env['assoc.election'].with_context(
            default_uuid=chosen).create(dict(base))
        self.assertNotEqual(defaulted.uuid, chosen)
        # 而且發出來的真的是 uuid4
        self.assertEqual(uuid_lib.UUID(election.uuid).version, 4)
        self.assertNotEqual(election.uuid, picked.uuid)

    def test_voter_cannot_be_created_voted(self):
        """`default_state='voted'` 會建出「已投票」的名冊列——那個人從此領不到票。

        用**不在名冊上**的會員（X99 會費過期）：拿名冊上的人來試會先撞
        `unique(election_id, member_id)`，測試就以錯誤的理由通過。
        """
        self.election.action_ready()
        with self.assertRaises(ValidationError):
            self.env['assoc.election.voter'].with_context(
                default_state='voted').create({
                    'election_id': self.election.id,
                    'member_id': self.ineligible.id,
                    'member_no': 'X99', 'member_name': '會員X99'})

    def test_candidate_cannot_be_created_as_write_in(self):
        """`default_state='write_in'` 會繞過凍結名冊的選舉權檢查。"""
        with self.assertRaises(UserError):
            self.env['assoc.election.candidate'].with_context(
                default_state='write_in').create({
                    'election_id': self.election.id, 'office': 'director',
                    'member_id': self.members['A06'].id})

    def test_roster_create_strips_forged_defaults(self):
        """內部建立帶哨兵時**不能**把前端送來的 `default_*` 一起帶進去。

        `with_context()` 是疊加：哨兵讓 `check_created` 直接放行，
        於是哨兵反而成了繞過守衛的鑰匙（M9 在禮品模組實跑複現過）。
        """
        self.election.with_context(
            default_state='voted', default_receipt_code='FAKE-00000').action_ready()
        states = set(self.election.voter_ids.mapped('state'))
        self.assertEqual(states, {'eligible'}, '名冊不能被 default_* 污染')
        self.assertFalse(any(self.election.voter_ids.mapped('receipt_code')))

    def test_officer_can_build_but_cannot_read_the_archive(self):
        """產生封存包是**選務**的動作，但內容只有本場監票員拿得到。

        封存包本體存在沒有 ACL 的 `assoc.election.archive`，所以「選務讀不到」
        不是靠欄位的 `groups=`（那只問群組、不問是不是這一場），
        而是靠「這個模型對所有非 superuser 都關著」。
        """
        self.run_to_counted()
        self.election.action_publish()
        self.election.with_user(self.officer).action_build_archive()
        self.assertEqual(len(self.election.archive_sha256), 64)
        with self.assertRaises(AccessError):
            self.env['assoc.election.archive'].with_user(self.officer).search([])

    def test_ballot_page_shows_and_orders_by_number(self):
        """號次的意義就是**印在選票上**讓會員照號碼找人。

        抽了號次卻不送到投票頁，等於只是在資料庫裡記一個沒人看得到的數字——
        而選票的排序正是號次唯一會影響到選民的地方。
        """
        self.election.draw_entropy = '7-7-7'
        self.election.action_ready()
        offices = {office['code']: office for office in self.election._ballot_offices()}
        directors = offices['director']['candidates']
        numbers = [cand['ballot_number'] for cand in directors]
        self.assertEqual(numbers, sorted(numbers), '選票要依號次排序')
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        by_no = {cand['member_no']: cand['ballot_number'] for cand in directors}
        stored = {c.member_no: c.ballot_number
                  for c in self.election.candidate_ids if c.office == 'director'}
        self.assertEqual(by_no, stored, '選票上的號次要與抽籤結果一致')

    def test_ballot_page_without_numbers_still_works(self):
        """沒抽號次的場次照樣要出得了選票（號次是選配）。"""
        self.election.action_ready()
        directors = {office['code']: office
                     for office in self.election._ballot_offices()}['director']['candidates']
        self.assertTrue(directors)
        self.assertTrue(all(cand['ballot_number'] == 0 for cand in directors))

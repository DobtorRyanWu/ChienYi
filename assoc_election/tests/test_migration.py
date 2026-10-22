import importlib.util
import pathlib
from unittest.mock import patch

from odoo import fields

from .common import AssocElectionCase

# 升級腳本的檔名帶連字號，`import` 進不來，只能照路徑載入。
MIGRATION_PATH = (pathlib.Path(__file__).resolve().parent.parent
                  / 'migrations' / '18.0.1.2.0' / 'post-migrate.py')

# 這份清單是「升級前就凍結了名冊、票面上不會有屆次」的狀態（票面在凍結那一步
# 就定了；`ballot_ready` 還沒發票，但它的票面一樣定了），與 migration 裡的
# `IN_FLIGHT_STATES` 是同一個命題，**但故意各寫一份**：兩邊共用一個常數的話，
# 改了那個常數兩邊一起動，這支測試就變成恆真的閘（L1①）。
ROSTER_ALREADY_FROZEN = ('ballot_ready', 'open', 'closing', 'closed', 'counted')
NOT_AFFECTED = ('draft', 'cancelled', 'published')


def load_migration():
    spec = importlib.util.spec_from_file_location('assoc_m1320_post_migrate', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationVictimList(AssocElectionCase):
    """升級腳本點名「選票上不會有屆次」的場次。

    **為什麼需要這一支**：mutation harness 跑的是 `-i`（乾淨庫全新安裝），
    而 Odoo 的 migration 只在 `-u`（升級既有庫）時執行——所以改
    `IN_FLIGHT_STATES` 在那個呼叫幾何下**結構上不可能**讓任何測試變紅，
    第六輪 mutation 的 #37 因此假存活（L2⑫：測試釘死了唯一能成立的呼叫幾何）。
    這裡直接呼叫 `migrate()`，把缺的那個幾何補回來。
    """

    def _election(self, state):
        """造一場「升級前就存在、沒有屆次」的選舉。

        state 用 SQL 直寫而不是走狀態機：migration 面對的是資料庫裡**已經有的列**，
        不是透過狀態機造出來的列，而正當入口（`action_ready`）今天就會要求屆次，
        根本造不出這種資料。
        **`term_no` 寫 NULL，不是 0**：真的升級時這個欄位沒有 default，Odoo 新增欄位
        不會回填既有的列（容器 `fields.py:1139-1150`），所以受害者身上是 NULL。
        原本寫 0，而 migration 的 domain `('term_no','=',0)` 碰巧展開成
        `= 0 OR IS NULL` 所以兩種都中——哪天有人把它改寫成原生 SQL `= 0`，
        這幾支照綠、真升級卻一場都點不到（L2⑫；第五輪 skeptic）。
        """
        election = self.env['assoc.election'].create({
            'name': f'舊場次-{state}', 'company_id': self.company.id,
            'meeting_id': self.meeting.id, 'term_id': self.term.id,
            'director_seats': 1, 'director_alt': 0,
            'supervisor_seats': 0, 'supervisor_alt': 0,
        })
        self.env.cr.execute('UPDATE assoc_election SET state = %s, term_no = NULL WHERE id = %s',
                            (state, election.id))
        self.env.invalidate_all()
        return election

    def _run(self):
        """跑 migration，回傳它點名的 id 集合。"""
        module = load_migration()
        # patch `_logger` 而不是解析文字：從輸出判成敗一律解析**值**，
        # 不比子字串（M-A）。
        with patch.object(module, '_logger') as logger:
            module.migrate(self.env.cr, '18.0.1.1.0')
        named = [call.args for call in logger.warning.call_args_list
                 if '選票上不會有選舉屆次' in call.args[0]]
        if not named:
            return set()
        self.assertEqual(len(named), 1, '點名的警告應該只有一通')
        return set(named[0][-1])

    def test_every_state_whose_roster_is_already_frozen_gets_named(self):
        made = {state: self._election(state) for state in ROSTER_ALREADY_FROZEN}
        self.assertEqual(
            self._run(), {election.id for election in made.values()},
            '「已經凍結名冊」的每一個狀態都要被點名——集合要**相等**，'
            '不是「有包含」：少點名一個是漏報，多點名一個是假警報，兩個方向都要紅')

    def test_states_that_are_not_affected_are_left_alone(self):
        # **對照組不可以省**：沒有它的話，只要那通警告的文字改掉（`_run()` 就抓不到、
        # 回傳空集合），這一項立刻變成恆真的閘——「找不到目標」必須長得像失敗，
        # 不可以長得像通過（M-A）。
        control = self._election('counted')
        for state in NOT_AFFECTED:
            self._election(state)
        self.assertEqual(self._run(), {control.id},
                         'draft／cancelled 還沒凍結名冊、published 那一屆已經選完公告，'
                         '點名它們只會製造假警報（L1⑨：假警報比漏報更糟）；'
                         '而對照組那一場必須照樣被點名')

    def test_an_election_that_already_has_a_term_is_not_named(self):
        control = self._election('counted')      # 同上，對照組兼警告文字的哨兵
        election = self._election('closed')
        self.env.cr.execute('UPDATE assoc_election SET term_no = 12 WHERE id = %s', (election.id,))
        self.env.invalidate_all()
        self.assertEqual(self._run(), {control.id},
                         '有屆次的場次不該被點名——否則這道警告對每一場都亮，沒有人會再看它')

    def test_the_two_lists_split_every_election_state(self):
        """兩份清單合起來要**剛好**是選舉狀態的全集（第五輪 simplifier）。

        各寫一份擋得住「migration 清單縮短」（上面那支會紅），擋不住第三個方向：
        日後新增第 9 個狀態時，兩份清單都不會提到它、也沒有任何東西會紅
        （L2：列舉式的測試只證明列到的那幾項）。這一支把「兩份清單是 Selection
        的一個分割」釘成硬不變量，而不必共用常數。
        """
        states = set(dict(self.env['assoc.election']._fields['state'].selection))
        self.assertEqual(set(ROSTER_ALREADY_FROZEN) | set(NOT_AFFECTED), states,
                         '新增選舉狀態時要先決定它算不算受害者')
        self.assertFalse(set(ROSTER_ALREADY_FROZEN) & set(NOT_AFFECTED),
                         '一個狀態不可以同時是受害者又不受影響')

    def test_the_rig_itself_actually_changes_the_answer(self):
        """證明上面那組斷言不是恆真的：同一支 `_run()` 在有受害者與沒有受害者時
        回傳不同的東西（L2③：先驗證這個 rig 真的改變了結果，再往下）。"""
        self.assertEqual(self._run(), set(), '還沒造任何舊場次時應該零點名')
        victim = self._election('counted')
        self.assertEqual(self._run(), {victim.id})

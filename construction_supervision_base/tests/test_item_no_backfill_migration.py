# -*- coding: utf-8 -*-
"""18.0.6.7.4 migration：空的 item_no 依專案補成 1、2…，之後 NOT NULL 設得上去。

jt 2026-11-13 的 -u 報「Table 'project_task': unable to set NOT NULL on column 'item_no'」。
2026-11-16 唯讀查 jt：6 列 hr_timesheet 內部任務的 item_no 是 NULL，欄位從來沒設成 NOT NULL。

這裡在測試交易裡做出同樣的狀態（欄位可為 NULL、幾列 item_no 空、衍生欄位是空值時的算法），
先證明 NOT NULL 設不上去（修前），跑完 pre／post-migrate 後再證明設得上去、衍生欄位也重算了（修後）。
DDL 會跟著測試交易一起 rollback。
"""
import importlib.util
import os

import psycopg2

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

MIGRATION_VERSION = '18.0.6.7.4'
INSTALLED_VERSION = '18.0.6.7.3'  # 升級前 DB 裡的版本；migrate() 收到 None 代表新裝，會直接跳過


def _load_migration(script):
    path = os.path.join(get_module_path('construction_supervision_base'),
                        'migrations', MIGRATION_VERSION, script)
    spec = importlib.util.spec_from_file_location(
        'item_no_backfill_%s' % script.replace('-', '_').replace('.py', ''), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestItemNoBackfillMigration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project']
        Task = cls.env['project.task']
        cls.project_a = Project.create({
            'name': '回填測試 A', 'code': 'BACKFILL-A', 'project_type': 'general'})
        cls.project_b = Project.create({
            'name': '回填測試 B', 'code': 'BACKFILL-B', 'project_type': 'general'})
        # 先用 ORM 建好（create 會補號），再在測試裡用 SQL 把 item_no 改成空的
        cls.a_training = Task.create({'name': 'Training', 'project_id': cls.project_a.id})
        cls.a_meeting = Task.create({'name': 'Meeting', 'project_id': cls.project_a.id})
        cls.a_numbered = Task.create({
            'name': '本來就有號', 'project_id': cls.project_a.id, 'item_no': '7'})
        cls.b_parent = Task.create({'name': '培訓', 'project_id': cls.project_b.id})
        cls.b_child = Task.create({
            'name': '子工項', 'project_id': cls.project_b.id,
            'parent_id': cls.b_parent.id, 'item_no': '3'})

    def _make_jt_state(self):
        """做出 jt 的狀態：item_no 可為 NULL；NULL 與空字串各有；衍生欄位是 item_no 空時的算法。"""
        self.env.flush_all()
        cr = self.env.cr
        cr.execute('ALTER TABLE project_task ALTER COLUMN item_no DROP NOT NULL')
        empty_ids = (self.a_training.id, self.b_parent.id)
        cr.execute("""
            UPDATE project_task
               SET item_no = CASE WHEN id = %s THEN '' ELSE NULL END,
                   item_no_path = '', item_no_sort = '', display_item_no = '',
                   full_item_path = name
             WHERE id IN %s
        """, (self.a_meeting.id, empty_ids + (self.a_meeting.id,)))
        # 子工項：父項 item_no 空時，路徑只有自己的編號
        cr.execute("""
            UPDATE project_task SET item_no_path = '3', item_no_sort = '000003'
             WHERE id = %s
        """, (self.b_child.id,))
        self.env.invalidate_all()

    def _set_not_null(self):
        self.env.cr.execute('ALTER TABLE project_task ALTER COLUMN item_no SET NOT NULL')

    def _item_no(self, task):
        self.env.cr.execute('SELECT item_no FROM project_task WHERE id = %s', (task.id,))
        return self.env.cr.fetchone()[0]

    def test_backfill_then_not_null(self):
        self._make_jt_state()
        self.assertIsNone(self._item_no(self.a_training))
        self.assertEqual(self._item_no(self.a_meeting), '')

        # 修前：有 NULL 時 NOT NULL 設不上去（就是 jt -u 那行 ERROR）
        with self.assertRaises(psycopg2.errors.NotNullViolation), \
                mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self._set_not_null()

        _load_migration('pre-migrate.py').migrate(self.env.cr, INSTALLED_VERSION)

        # 依專案、依 id 補 1、2…；本來就有號的不動
        self.assertEqual(self._item_no(self.a_training), '1')
        self.assertEqual(self._item_no(self.a_meeting), '2')
        self.assertEqual(self._item_no(self.a_numbered), '7')
        self.assertEqual(self._item_no(self.b_parent), '1')
        self.assertEqual(self._item_no(self.b_child), '3')

        # 修後：NOT NULL 設得上去
        self._set_not_null()

        _load_migration('post-migrate.py').migrate(self.env.cr, INSTALLED_VERSION)
        self.env.invalidate_all()

        self.assertEqual(self.a_training.item_no_path, '1')
        self.assertEqual(self.a_training.item_no_sort, '000001')
        self.assertEqual(self.a_training.display_item_no, '1')
        self.assertEqual(self.a_training.full_item_path, '1 Training')
        self.assertEqual(self.a_meeting.item_no_path, '2')
        self.assertEqual(self.b_parent.item_no_path, '1')
        # 子工項的路徑要跟著父項重算
        self.assertEqual(self.b_child.item_no_path, '1.3')
        self.assertEqual(self.b_child.item_no_sort, '000001.000003')

    def test_fresh_install_is_skipped(self):
        """新裝（version=None）不動資料。"""
        self._make_jt_state()
        _load_migration('pre-migrate.py').migrate(self.env.cr, None)
        self.assertIsNone(self._item_no(self.a_training))

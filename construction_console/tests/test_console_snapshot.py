# -*- coding: utf-8 -*-
"""控台快照（合約 §8.3）：replace_snapshot 的整批替換與伺服器端檢查、誰能寫、狀態欄位、清單畫面。

斷言打在看得到的結果：快照有哪幾列（逐 remote_id 比，兩個方向）、失敗原因、被拒＋訊息。
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

PULLER = 'construction_console.group_console_puller'
MANAGER = 'construction_console.group_console_manager'
VIEWER = 'construction_console.group_console_user'
COMPUTED_AT = '2026-11-05 01:00:00'
COMPUTED_AT_2 = '2026-11-05 02:00:00'
# 與租戶端 dash_console_overview() 每列的鍵相同（測試這邊獨立寫一份）
ROW_KEYS = (
    'remote_id', 'name', 'code', 'state', 'state_label', 'active', 'contractor_companies', 'supervision_company',
    'workday_elapsed', 'workday_total', 'workday_note', 'workday_state', 'workday_state_label',
    'log_today', 'log_today_label', 'today_photo_count',
    'open_defect_count', 'overdue_defect_count', 'pending_test_count',
    'latest_estimate_no', 'latest_estimate_date', 'estimate_cum_amount', 'estimate_month_amount',
    'progress_planned', 'progress_actual', 'progress_variance', 'has_schedule',
    'denied_keys', 'error_keys',
)
SUP_X = {'name': '監造 甲', 'vat': '04595257'}
SUP_Y = {'name': '監造 丙', 'vat': False}
HOURS_JUST_FRESH = 1
HOURS_LONG_AGO = 30


def make_row(remote_id, open_defects=1, **overrides):
    row = {
        'remote_id': remote_id, 'name': f'工程 {remote_id}', 'code': f'C-{remote_id}',
        'state': 'construction', 'state_label': '施工中', 'active': True,
        'contractor_companies': [{'name': '營造 A', 'vat': '00501503'}, {'name': '營造 B', 'vat': False}],
        'supervision_company': dict(SUP_X),
        'workday_elapsed': 10, 'workday_total': 100, 'workday_note': False, 'workday_state': 'ok',
        'workday_state_label': '正常', 'log_today': 'missing', 'log_today_label': '未填',
        'today_photo_count': 2, 'open_defect_count': open_defects, 'overdue_defect_count': 0,
        'pending_test_count': 3, 'latest_estimate_no': 4, 'latest_estimate_date': '2026-10-31',
        'estimate_cum_amount': 1000000.0, 'estimate_month_amount': 0.0,
        'progress_planned': 50.0, 'progress_actual': 45.5, 'progress_variance': -4.5,
        'has_schedule': True, 'denied_keys': False, 'error_keys': False,
    }
    assert set(row) == set(ROW_KEYS)
    row.update(overrides)
    return row


@tagged('post_install', '-at_install', 'construction_console')
class TestConsoleSnapshot(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.puller = Users.create({'name': '拉資料', 'login': 'console_puller_t',
                                   'groups_id': [(6, 0, [cls.env.ref(PULLER).id])]})
        cls.manager = Users.create({'name': '控台管理', 'login': 'console_manager_t',
                                    'groups_id': [(6, 0, [cls.env.ref(MANAGER).id])]})
        cls.viewer = Users.create({'name': '控台檢視', 'login': 'console_viewer_t',
                                   'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])]})
        cls.tenant = cls.env['console.tenant'].create({'name': '監造 甲', 'db_name': 'tenant_a',
                                                       'url': 'https://a.example.com'})
        cls.other = cls.env['console.tenant'].create({'name': '監造 乙', 'db_name': 'tenant_b'})

    # ── 工具 ───────────────────────────────────────────────────────────
    def _replace(self, rows, count, computed_at=COMPUTED_AT, tenant=None, user=None):
        tenant = (tenant or self.tenant).with_user(user or self.puller)
        return tenant.replace_snapshot(rows, count, computed_at)

    def _snapshot(self, tenant=None):
        tenant = tenant or self.tenant
        return {p.remote_id: (p.name, p.open_defect_count) for p in tenant.project_ids}

    def _seed(self):
        """先放一份 2 筆的快照（之後的拒寫要保留它）。"""
        result = self._replace([make_row(1), make_row(2, open_defects=5)], 2)
        self.assertEqual(result, {'ok': True, 'count': 2})
        self.tenant.invalidate_recordset()
        return self._snapshot()

    # ── 成功替換 ────────────────────────────────────────────────────────
    def test_replace_success_replaces_whole_set(self):
        before = self._seed()
        self.assertEqual(before, {1: ('工程 1', 1), 2: ('工程 2', 5)})
        self.assertEqual(self.tenant.data_computed_at, fields.Datetime.to_datetime(COMPUTED_AT))
        self.assertTrue(self.tenant.last_success_at)
        self.assertEqual(self.tenant.pull_state, 'ok')
        # 第二次：舊列全部換掉（2 不見、3 出現；1 的值更新），不是附加
        result = self._replace([make_row(1, open_defects=9), make_row(3)], 2, COMPUTED_AT_2)
        self.assertEqual(result, {'ok': True, 'count': 2})
        self.tenant.invalidate_recordset()
        self.assertEqual(self._snapshot(), {1: ('工程 1', 9), 3: ('工程 3', 1)})
        self.assertEqual(self.tenant.data_computed_at, fields.Datetime.to_datetime(COMPUTED_AT_2))
        self.assertEqual(self._snapshot(self.other), {}, '別的租戶不受影響')
        row = self.tenant.project_ids.filtered(lambda p: p.remote_id == 1)
        self.assertEqual(row.contractor_display, '營造 A（00501503）、營造 B')
        self.assertEqual(row.contractor_vats, '00501503')
        self.assertEqual((row.supervision_company_display, row.supervision_company_vat), ('監造 甲（04595257）', '04595257'))

    def test_zero_to_zero_accepted(self):
        """從來沒有工程的租戶回 0 筆：可以寫（0→0 不是「從大於 0 變成 0」）。"""
        self.assertEqual(self._replace([], 0), {'ok': True, 'count': 0})
        self.assertTrue(self.tenant.last_success_at)
        self.assertFalse(self.tenant.last_failure_at)

    # ── 伺服器端檢查：拒寫、記失敗、舊快照保留 ──────────────────────────
    def _assert_rejected(self, result, before, needle):
        self.assertIs(result['ok'], False)
        self.assertIn(needle, result['reason'])
        self.tenant.invalidate_recordset()
        self.assertEqual(self._snapshot(), before, '舊快照必須原封保留')
        self.assertEqual(self.tenant.data_computed_at, fields.Datetime.to_datetime(COMPUTED_AT), '資料時間不可前進')
        self.assertIn(needle, self.tenant.last_failure_reason, '失敗原因要記在租戶上')
        self.assertTrue(self.tenant.last_failure_at)
        self.assertEqual(self.tenant.pull_state, 'failed')

    def test_count_mismatch_rejected(self):
        """拉回 2 筆、租戶原生 SQL 說有 3 筆 → 拒寫（兩個方向：多一筆也拒）。"""
        before = self._seed()
        result = self._replace([make_row(1), make_row(3)], 3, COMPUTED_AT_2)
        self._assert_rejected(result, before, '筆數不符')
        self.assertIn('3', result['reason'])
        result = self._replace([make_row(1), make_row(3), make_row(4)], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, '筆數不符')

    def test_drop_to_zero_rejected(self):
        before = self._seed()
        result = self._replace([], 0, COMPUTED_AT_2)
        self._assert_rejected(result, before, '變成 0')

    def test_bad_row_keys_rejected(self):
        """鍵要完全相同：少一個（租戶版本不對）、多一個（例如多送了人名）都拒。"""
        before = self._seed()
        missing = make_row(3)
        del missing['error_keys']
        result = self._replace([make_row(1), missing], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, '鍵不符')
        self.assertIn('error_keys', result['reason'])
        extra = make_row(3, inspector_name='王小明')
        result = self._replace([make_row(1), extra], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, '鍵不符')
        self.assertIn('inspector_name', result['reason'])

    def test_bad_value_type_rejected(self):
        before = self._seed()
        result = self._replace([make_row(1), make_row(3, open_defect_count='很多')], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, '型別不符')
        result = self._replace([make_row(1), make_row(3, contractor_companies=[{'name': 'X'}])], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, '型別不符')
        # 監造公司：必須是一家公司（名稱＋統編兩個鍵）；空值、缺鍵、清單都拒
        for bad in (False, {'name': 'X'}, [dict(SUP_X)], {'name': '', 'vat': False}):
            result = self._replace([make_row(1), make_row(3, supervision_company=bad)], 2, COMPUTED_AT_2)
            self._assert_rejected(result, before, '型別不符')
            self.assertIn('supervision_company', result['reason'], repr(bad))

    def test_duplicate_remote_id_rejected(self):
        before = self._seed()
        result = self._replace([make_row(7), make_row(7)], 2, COMPUTED_AT_2)
        self._assert_rejected(result, before, 'remote_id 重複')

    def test_replace_is_one_transaction(self):
        """建新列途中出錯 → 刪掉的舊列也回來（同一個交易）。"""
        before = self._seed()
        Project = type(self.env['console.tenant.project'])

        # 用一般函式，不用 MagicMock：Odoo 會掃描類別屬性找 _ondelete／_constrains 標記並快取，
        # MagicMock 什麼屬性都「有」，會被當成刪除鉤子留在快取裡（實測讓後面的測試 unlink 時爆）
        def broken_create(model, vals_list):
            raise RuntimeError('寫到一半')
        with patch.object(Project, 'create', broken_create), self.assertRaises(RuntimeError):
            self._replace([make_row(1), make_row(3)], 2, COMPUTED_AT_2)
        self.env.invalidate_all()
        self.assertEqual(self._snapshot(), before)

    # ── 誰能寫 ─────────────────────────────────────────────────────────
    def test_only_puller_can_write_snapshot(self):
        for user in (self.manager, self.viewer):
            with self.assertRaises(AccessError, msg=user.login) as ctx:
                self._replace([make_row(1)], 1, user=user)
            self.assertIn('控台拉資料', str(ctx.exception))
            with self.assertRaises(AccessError, msg=user.login):
                self.tenant.with_user(user).sudo().replace_snapshot([make_row(1)], 1, COMPUTED_AT)
            with self.assertRaises(AccessError, msg=user.login):
                self.tenant.with_user(user).record_pull_failure('假的失敗')
        self.assertEqual(self._snapshot(), {})
        self.assertFalse(self.tenant.last_failure_at)
        # 放行的方向：拉資料帳號寫得進去
        self.assertEqual(self._replace([make_row(1)], 1)['ok'], True)

    def test_status_fields_protected(self):
        """資料時間、成功／失敗紀錄任何帳號都不能直接寫（拉資料帳號也不行，只能走方法）。"""
        for user in (self.manager, self.puller):
            for field_name in ('last_success_at', 'data_computed_at', 'last_failure_at', 'last_failure_reason'):
                value = '正常' if field_name == 'last_failure_reason' else fields.Datetime.now()
                with self.assertRaises(AccessError, msg=f'{user.login} {field_name}') as ctx:
                    self.tenant.with_user(user).write({field_name: value})
                self.assertIn('只由拉資料程式寫入', str(ctx.exception))
        with self.assertRaises(AccessError):
            self.env['console.tenant'].with_user(self.manager).create(
                {'name': '丙', 'db_name': 'tenant_c', 'last_success_at': fields.Datetime.now()})
        # 一般欄位照常可改、可建
        self.tenant.with_user(self.manager).write({'url': 'https://b.example.com'})
        self.env['console.tenant'].with_user(self.manager).create({'name': '丙', 'db_name': 'tenant_c'})

    def test_snapshot_rows_read_only(self):
        self._seed()
        row = self.tenant.project_ids[:1]
        for user in (self.manager, self.puller, self.viewer):
            self.assertEqual(row.with_user(user).read(['name'])[0]['name'], row.name, '讀得到')
            with self.assertRaises(AccessError):
                row.with_user(user).write({'open_defect_count': 0})
            with self.assertRaises(AccessError):
                row.with_user(user).unlink()

    def test_record_pull_failure_keeps_snapshot(self):
        before = self._seed()
        self.assertTrue(self.tenant.with_user(self.puller).record_pull_failure('租戶 tenant_a 拒絕登入'))
        self.tenant.invalidate_recordset()
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(self.tenant.last_failure_reason, '租戶 tenant_a 拒絕登入')
        self.assertEqual(self.tenant.pull_state, 'failed')
        with self.assertRaises(ValidationError):
            self.tenant.with_user(self.puller).record_pull_failure('')

    # ── 拉取狀態 ────────────────────────────────────────────────────────
    def test_pull_state(self):
        tenant = self.env['console.tenant'].create({'name': '丁', 'db_name': 'tenant_d'})
        self.assertEqual(tenant.pull_state, 'never')
        now = fields.Datetime.now()
        tenant.sudo().write({'last_success_at': now - timedelta(hours=HOURS_JUST_FRESH)})
        tenant.invalidate_recordset()
        self.assertEqual(tenant.pull_state, 'ok')
        tenant.sudo().write({'last_success_at': now - timedelta(hours=HOURS_LONG_AGO)})
        tenant.invalidate_recordset()
        self.assertEqual(tenant.pull_state, 'stale', '太久沒成功＝資料過時（拉資料程式沒在跑也看得出來）')
        tenant.sudo().write({'last_failure_at': now})
        tenant.invalidate_recordset()
        self.assertEqual(tenant.pull_state, 'failed')
        tenant.sudo().write({'last_success_at': now + timedelta(seconds=1)})
        tenant.invalidate_recordset()
        self.assertEqual(tenant.pull_state, 'ok', '之後成功過就恢復正常（上次失敗仍保留在欄位上）')
        self.assertTrue(tenant.last_failure_at)

    def test_db_name_format(self):
        with self.assertRaises(ValidationError):
            self.env['console.tenant'].create({'name': 'x', 'db_name': 'Bad-Name'})

    # ── 清單畫面 ────────────────────────────────────────────────────────
    def test_group_by_supervision_company(self):
        """同一租戶（jt 這種多家共用的庫）底下兩家監造公司的工程：清單可依監造公司分組、各組合計分得開。"""
        rows = [make_row(1, open_defects=2), make_row(2, open_defects=3),
                make_row(3, open_defects=7, supervision_company=dict(SUP_Y))]
        self.assertEqual(self._replace(rows, 3)['ok'], True)
        Project = self.env['console.tenant.project'].with_user(self.viewer)
        views = Project.get_views([(False, 'list'), (False, 'search')])
        self.assertIn('name="supervision_company_display"', views['views']['list']['arch'])
        self.assertIn("'group_by': 'supervision_company_display'", views['views']['search']['arch'])
        groups = {name: (count, total) for name, count, total in Project._read_group(
            [('tenant_id', '=', self.tenant.id)], ['supervision_company_display'],
            ['__count', 'open_defect_count:sum'])}
        self.assertEqual(groups, {'監造 甲（04595257）': (2, 5), '監造 丙': (1, 7)})

    def test_list_views_and_totals(self):
        self._seed()
        self._replace([make_row(11, open_defects=4)], 1, tenant=self.other)
        Project = self.env['console.tenant.project'].with_user(self.viewer)
        views = Project.get_views([(False, 'list'), (False, 'search')])
        arch = views['views']['list']['arch']
        for name in ('tenant_data_computed_at', 'tenant_last_failure_at', 'open_defect_count', 'error_keys'):
            self.assertIn(f'name="{name}"', arch)
        self.env['console.tenant'].with_user(self.viewer).get_views([(False, 'list'), (False, 'form')])
        # 依租戶分組的合計（畫面分組列顯示的就是這個）
        # 只看本測試的兩個租戶（控台庫可能已有端到端留下的真資料）
        groups = {tenant.id: total for tenant, total in Project._read_group(
            [('tenant_id', 'in', (self.tenant | self.other).ids)], ['tenant_id'], ['open_defect_count:sum'])}
        self.assertEqual(groups, {self.tenant.id: 6, self.other.id: 4})
        # 不該加總的欄位（期數、工作天、進度%）沒有 aggregator
        for name in ('remote_id', 'latest_estimate_no', 'workday_total', 'progress_planned'):
            self.assertFalse(Project._fields[name].aggregator, name)

# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools


class TestTaskStatistics(models.Model):
    """
    契約工項檢試驗統計報表

    使用 SQL View 自動聚合統計每個「工項 × 檢試驗項目」的檢試驗數據：
    - 進行了幾次檢驗
    - 總進場/抽樣數量
    - 合格/不合格/待判定統計
    - 合格率
    """
    _name = 'supervision.test.task.statistics'
    _description = '契約工項檢試驗統計'
    _auto = False  # 不自動建立資料表，使用 SQL View
    _order = 'project_id, task_id, standard_id'

    # === 維度欄位 ===
    task_id = fields.Many2one(
        'project.task',
        string='契約工項',
        readonly=True)

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        readonly=True)

    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        readonly=True)

    task_name = fields.Char(
        string='工項名稱',
        readonly=True)

    item_no = fields.Char(
        string='工項編號',
        readonly=True)

    standard_name = fields.Char(
        string='檢試驗名稱',
        readonly=True)

    # === 統計指標 ===
    test_record_count = fields.Integer(
        string='實際檢驗次數',
        readonly=True,
        help='總共進行了幾次檢驗')

    total_in_site_quantity = fields.Float(
        string='總進場數量',
        digits=(16, 4),
        readonly=True,
        help='所有檢驗記錄的進場數量加總')

    total_sample_quantity = fields.Float(
        string='總抽樣數量',
        digits=(16, 4),
        readonly=True,
        help='所有檢驗記錄的抽樣數量加總')

    pass_count = fields.Integer(
        string='合格次數',
        readonly=True)

    fail_count = fields.Integer(
        string='不合格次數',
        readonly=True)

    pending_count = fields.Integer(
        string='待判定次數',
        readonly=True)

    pass_rate = fields.Float(
        string='合格率 (%)',
        digits=(5, 2),
        readonly=True,
        help='合格次數 / (合格次數 + 不合格次數) * 100')

    # === 達標判定（Python computed，即時計算）===
    required_count = fields.Integer(
        string='需檢驗合格次數',
        compute='_compute_qualification',
        help='依據頻率條件和累計施工數量計算')

    shortage = fields.Integer(
        string='尚需合格次數',
        compute='_compute_qualification',
        help='max(0, 需檢驗合格次數 - 合格次數)')

    is_qualified = fields.Boolean(
        string='是否達標',
        compute='_compute_qualification',
        search='_search_is_qualified',
        help='合格次數 >= 需檢驗合格次數')

    @api.depends('standard_id', 'task_id', 'project_id', 'pass_count')
    def _compute_qualification(self):
        """計算需檢驗次數與是否達標"""
        LogLine = self.env['daily.log.line']
        for rec in self:
            if not rec.standard_id or not rec.task_id:
                rec.required_count = 0
                rec.shortage = 0
                rec.is_qualified = True
                continue

            # 取得該工項的最新累計施工數量
            latest_line = LogLine.search([
                ('work_item_id', '=', rec.task_id.id),
                ('sheet_id.supervision_project_id', '=', rec.project_id.id),
            ], order='date desc, id desc', limit=1)
            cumulative_qty = latest_line.cumulative_qty if latest_line else 0.0

            # 計算需檢驗次數（統一入口：頻率條件 + 自訂公式）
            required = rec.standard_id.calculate_required_tests(cumulative_qty)

            rec.required_count = required
            rec.shortage = max(0, required - rec.pass_count)
            rec.is_qualified = rec.pass_count >= required if required > 0 else True

    def _search_is_qualified(self, operator, value):
        """搜尋是否達標：遍歷所有記錄計算"""
        all_records = self.search([])
        if operator == '=' and value is True:
            qualified_ids = all_records.filtered(lambda r: r.is_qualified).ids
        elif operator == '=' and value is False:
            qualified_ids = all_records.filtered(lambda r: not r.is_qualified).ids
        else:
            qualified_ids = []
        return [('id', 'in', qualified_ids)]

    def init(self):
        """建立資料庫 View"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    t.id AS task_id,
                    pp.id AS project_id,
                    ts.id AS standard_id,
                    t.name AS task_name,
                    t.item_no,
                    ts.name AS standard_name,
                    COUNT(tr.id) AS test_record_count,
                    COALESCE(SUM(tr.in_site_quantity), 0) AS total_in_site_quantity,
                    COALESCE(SUM(tr.sample_quantity), 0) AS total_sample_quantity,
                    SUM(CASE WHEN tr.result = 'pass' THEN 1 ELSE 0 END) AS pass_count,
                    SUM(CASE WHEN tr.result = 'fail' THEN 1 ELSE 0 END) AS fail_count,
                    SUM(CASE WHEN tr.result = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                    CASE
                        WHEN SUM(CASE WHEN tr.result IN ('pass', 'fail') THEN 1 ELSE 0 END) > 0
                        THEN (SUM(CASE WHEN tr.result = 'pass' THEN 1 ELSE 0 END)::float /
                              SUM(CASE WHEN tr.result IN ('pass', 'fail') THEN 1 ELSE 0 END)) * 100
                        ELSE 0
                    END AS pass_rate
                FROM project_task t
                INNER JOIN project_project pp ON pp.id = t.project_id
                INNER JOIN test_standard_task_rel rel ON rel.task_id = t.id
                INNER JOIN supervision_test_standard ts ON ts.id = rel.standard_id
                LEFT JOIN supervision_test_record tr
                    ON tr.task_id = t.id AND tr.standard_id = ts.id
                WHERE t.active = true
                GROUP BY t.id, pp.id, ts.id, t.name, t.item_no, ts.name
            )
        """)

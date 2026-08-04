# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.osv import expression


class TestStandard(models.Model):
    """
    檢試驗項目管理

    對應舊系統: testStandard

    管理工程的檢試驗項目，包含：
    - 試驗工項/材料設定
    - 依據方法與規範要求
    - 頻率與下限設定
    - 取樣規則與條件
    - 關聯契約工項
    """
    _name = 'supervision.test.standard'
    _description = '檢試驗項目'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'
    _rec_names_search = ['name', 'material']  # 讓 name_search / display_name 搜尋同時比對兩個欄位

    # === 基本資料 ===
    name = fields.Char(
        string='項目名稱',
        required=True,
        tracking=True,
        help='檢試驗項目名稱')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='排序順序')

    active = fields.Boolean(
        string='啟用',
        default=True)

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # === 需求2: 檢驗項目資訊 (舊系統欄位對應) ===
    material = fields.Char(
        string='試驗工項',
        required=True,
        tracking=True,
        help='舊系統欄位: material')

    describe = fields.Text(
        string='依據之方法',
        help='舊系統欄位: describe，說明檢驗依據的標準方法')

    norm = fields.Text(
        string='規範之要求',
        help='舊系統欄位: norm，規範要求的標準值或範圍')

    standard = fields.Text(
        string='頻率及下限',
        help='舊系統欄位: standard，取樣頻率和最低要求')

    unit = fields.Char(
        string='檢查單位',
        help='舊系統欄位: unit，檢驗數量的計量單位')

    # === 取樣規則 ===
    sampling_size = fields.Char(
        string='取樣大小',
        help='每次取樣的數量或規格')

    sampling_conditions = fields.Text(
        string='檢驗頻率條件',
        help='舊系統欄位: conditions (a~f 參數規則)，定義取樣頻率的各項條件')

    # === 檢驗頻率條件 (結構化) ===
    frequency_condition_ids = fields.One2many(
        'supervision.test.frequency.condition',
        'standard_id',
        string='檢驗頻率條件',
        help='結構化的檢驗頻率條件設定')

    # === 契約工項關聯 ===
    # 注意：規格書中的 project.contract.item 對應現有系統的 project.task
    task_ids = fields.Many2many(
        'project.task',
        'test_standard_task_rel',
        'standard_id',
        'task_id',
        string='關聯契約工項',
        domain="[('supervision_project_id', '=', project_id), ('is_summary_item', '=', False)]",
        help='舊系統欄位: payItems，此檢試驗項目適用的契約工項')

    # === 檢驗記錄 ===
    test_record_ids = fields.One2many(
        'supervision.test.record',
        'standard_id',
        string='檢驗記錄')

    test_record_count = fields.Integer(
        string='檢驗次數',
        compute='_compute_test_record_count',
        store=True)

    # === 統計欄位 ===
    total_in_site_quantity = fields.Float(
        string='累計進場數量',
        compute='_compute_statistics',
        store=True,
        digits=(16, 4))

    total_sample_quantity = fields.Float(
        string='累計抽樣數量',
        compute='_compute_statistics',
        store=True,
        digits=(16, 4))

    overall_sample_rate = fields.Float(
        string='整體抽樣率 (%)',
        compute='_compute_statistics',
        store=True,
        digits=(5, 2))

    pass_count = fields.Integer(
        string='合格次數',
        compute='_compute_statistics',
        store=True)

    fail_count = fields.Integer(
        string='不合格次數',
        compute='_compute_statistics',
        store=True)

    pass_rate = fields.Float(
        string='合格率 (%)',
        compute='_compute_statistics',
        store=True,
        digits=(5, 2))

    # === 自訂公式 ===
    use_custom_formula = fields.Boolean(
        string='使用自訂公式',
        default=False,
        help='啟用後，自訂公式的計算結果會與頻率條件的結果相加')

    custom_formula_description = fields.Char(
        string='公式說明',
        help='例如：同一爐號質量超過50t取2支，超過100t每50t加1支')

    custom_formula = fields.Text(
        string='計算公式',
        help='Python 表達式，回傳應檢驗次數（整數）')

    custom_warning_formula = fields.Text(
        string='預警公式',
        help='Python 表達式，回傳下一個預警門檻數量')

    custom_formula_variable_ids = fields.One2many(
        'supervision.test.formula.variable',
        'standard_id',
        string='自定義變數')

    # === 備註 ===
    note = fields.Text(string='備註')

    @api.depends('test_record_ids')
    def _compute_test_record_count(self):
        """計算檢驗記錄數量"""
        for rec in self:
            rec.test_record_count = len(rec.test_record_ids)

    @api.depends(
        'test_record_ids',
        'test_record_ids.in_site_quantity',
        'test_record_ids.sample_quantity',
        'test_record_ids.result'
    )
    def _compute_statistics(self):
        """計算統計數據"""
        for rec in self:
            records = rec.test_record_ids
            rec.total_in_site_quantity = sum(records.mapped('in_site_quantity'))
            rec.total_sample_quantity = sum(records.mapped('sample_quantity'))

            if rec.total_in_site_quantity:
                rec.overall_sample_rate = (rec.total_sample_quantity / rec.total_in_site_quantity) * 100
            else:
                rec.overall_sample_rate = 0.0

            rec.pass_count = len(records.filtered(lambda r: r.result == 'pass'))
            rec.fail_count = len(records.filtered(lambda r: r.result == 'fail'))

            total_judged = rec.pass_count + rec.fail_count
            if total_judged:
                rec.pass_rate = (rec.pass_count / total_judged) * 100
            else:
                rec.pass_rate = 0.0

    @api.depends('name', 'material')
    def _compute_display_name(self):
        for rec in self:
            # 優先顯示試驗工項 (material)，若無則顯示項目名稱 (name)
            rec.display_name = rec.material if rec.material else rec.name

    @api.model
    def _search_display_name(self, operator, value):
        """支援依名稱(name)與試驗工項(material)搜尋，並做 CJK 逐字比對。
        ⚠️ Odoo 18 已移除 _name_search hook；display_name 搜尋改走 _search_display_name，
        故原本的 _name_search 覆寫其實是死碼（從未被呼叫）。"""
        if value and operator in ('ilike', 'like', '=ilike', '=like'):
            terms = [t.strip() for t in value.split() if t.strip()]
            if terms:
                def per_char(fname):
                    return expression.AND([
                        [(fname, operator, '%' + '%'.join(list(t)) + '%')]
                        for t in terms
                    ])
                return expression.OR([per_char('name'), per_char('material')])
        return super()._search_display_name(operator, value)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當專案變更時，更新 task_ids 的 domain"""
        if self.project_id:
            return {
                'domain': {
                    'task_ids': [
                        ('supervision_project_id', '=', self.project_id.id),
                        ('is_summary_item', '=', False),  # 只能選最細項
                        ('active', '=', True),
                    ],
                }
            }
        else:
            # 沒有專案時，domain 設為不可能成立，防止選擇
            return {
                'domain': {
                    'task_ids': [('id', '=', False)],
                }
            }

    @api.onchange('task_ids')
    def _onchange_task_ids(self):
        """當嘗試新增工項但未選擇專案時，給予警告"""
        if not self.project_id and self.task_ids:
            # 清空已選擇的工項
            self.task_ids = False
            return {
                'warning': {
                    'title': '操作錯誤',
                    'message': '請先選擇「所屬工程」後，再設定關聯契約工項！',
                }
            }

    # =========================================================================
    # 統一計算入口
    # =========================================================================

    def calculate_required_tests(self, cumulative_qty, daily_qty=0):
        """
        統一入口：頻率條件 + 自訂公式（並存相加）

        :param cumulative_qty: 累計完成數量
        :param daily_qty: 本日/本批施工數量（預設 0，用於每日計量型公式）
        :return: int, 總共需要的檢驗次數
        """
        self.ensure_one()
        if cumulative_qty <= 0:
            return 0

        total = 0

        # 標準頻率條件
        conditions = self.frequency_condition_ids.filtered('active')
        total += conditions.calculate_total_required_tests(cumulative_qty)

        # 自訂公式（結果相加）
        if self.use_custom_formula and self.custom_formula:
            total += self._eval_custom_formula(cumulative_qty, daily_qty=daily_qty)

        return total

    def _eval_custom_formula(self, cumulative_qty, daily_qty=0):
        """
        評估自訂公式

        :param cumulative_qty: 累計完成數量
        :param daily_qty: 本日/本批施工數量（預設 0）
        :return: int, 公式計算的檢驗次數

        公式可用變數：
          - cumulative_qty: 累計數量
          - daily_qty: 本日數量（用於「每日澆築量」型頻率）
        """
        from odoo.tools.safe_eval import safe_eval
        variables = {
            'cumulative_qty': cumulative_qty,
            'daily_qty': daily_qty or 0,
        }
        for var in self.custom_formula_variable_ids:
            variables[var.name] = var.value
        try:
            return int(safe_eval(self.custom_formula, variables))
        except Exception:
            return 0

    def _eval_custom_warning_formula(self, cumulative_qty):
        """
        評估自訂預警公式

        :param cumulative_qty: 累計完成數量
        :return: float or None, 下一個預警門檻數量
        """
        if not self.custom_warning_formula:
            return None
        from odoo.tools.safe_eval import safe_eval
        variables = {'cumulative_qty': cumulative_qty}
        for var in self.custom_formula_variable_ids:
            variables[var.name] = var.value
        try:
            result = safe_eval(self.custom_warning_formula, variables)
            if result and result > cumulative_qty:
                return float(result)
        except Exception:
            pass
        return None

    def action_open_formula_template_wizard(self):
        """開啟套用公式範本精靈"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '套用公式範本',
            'res_model': 'apply.formula.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_standard_id': self.id,
            },
        }

    def action_view_test_records(self):
        """查看檢驗記錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '檢驗記錄',
            'res_model': 'supervision.test.record',
            'view_mode': 'list,form',
            'domain': [('standard_id', '=', self.id)],
            'context': {
                'default_standard_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    # =========================================================================
    # 統計查詢方法（供前台串接）
    # =========================================================================

    @api.model
    def get_test_statistics_by_task(self, project_id):
        """
        取得指定工程的所有工項檢驗統計

        以「工項 × 檢試驗項目」為維度，回傳每一組的：
        - 需檢驗次數（由頻率條件 + 累計施工數量計算）
        - 實際檢驗次數、合格次數、不合格次數
        - 是否達標（合格次數 >= 需檢驗次數）

        :param project_id: int, supervision.project ID
        :return: list of dict
        """
        sup_project = self.env['project.project'].browse(project_id)
        if not sup_project.exists():
            return []

        standards = self.search([
            ('project_id', '=', project_id),
            ('active', '=', True),
        ])

        result = []
        TestRecord = self.env['supervision.test.record']
        LogLine = self.env['daily.log.line']

        for standard in standards:
            for task in standard.task_ids:
                # 取得該工項的最新累計施工數量
                latest_line = LogLine.search([
                    ('work_item_id', '=', task.id),
                    ('sheet_id.supervision_project_id', '=', project_id),
                ], order='date desc, id desc', limit=1)
                cumulative_qty = latest_line.cumulative_qty if latest_line else 0.0

                # 計算需檢驗次數（統一入口）
                required_count = standard.calculate_required_tests(cumulative_qty)

                # 計算實際檢驗次數、合格、不合格
                records = TestRecord.search([
                    ('project_id', '=', project_id),
                    ('standard_id', '=', standard.id),
                    ('task_id', '=', task.id),
                ])
                actual_count = len(records)
                pass_count = len(records.filtered(lambda r: r.result == 'pass'))
                fail_count = len(records.filtered(lambda r: r.result == 'fail'))

                # 達標 = 合格次數 >= 需檢驗次數
                is_qualified = pass_count >= required_count if required_count > 0 else True
                shortage = max(0, required_count - pass_count)

                result.append({
                    'task_id': task.id,
                    'task_name': task.name,
                    'task_item_no': task.item_no or '',
                    'standard_id': standard.id,
                    'standard_name': standard.name,
                    'cumulative_qty': cumulative_qty,
                    'required_count': required_count,
                    'actual_count': actual_count,
                    'pass_count': pass_count,
                    'fail_count': fail_count,
                    'is_qualified': is_qualified,
                    'shortage': shortage,
                })

        return result

    @api.model
    def get_unqualified_tasks(self, project_id):
        """
        取得指定工程中未達檢驗次數標準的工項清單（供前台預警通知）

        只回傳 is_qualified = False 的項目

        :param project_id: int, supervision.project ID
        :return: list of dict
        """
        all_stats = self.get_test_statistics_by_task(project_id)
        return [s for s in all_stats if not s['is_qualified']]

    def action_view_statistics(self):
        """查看檢試驗統計分析

        指向 supervision.test.task.statistics（SQL View，以「工項 × 檢試驗項目」
        為維度），而非 supervision.test.record 的原始檢驗記錄。
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 統計分析',
            'res_model': 'supervision.test.task.statistics',
            'view_mode': 'list,pivot,graph',
            'views': [
                (self.env.ref(
                    'construction_test.view_test_task_statistics_tree').id, 'list'),
                (self.env.ref(
                    'construction_test.view_test_task_statistics_pivot').id, 'pivot'),
                (self.env.ref(
                    'construction_test.view_test_task_statistics_graph').id, 'graph'),
            ],
            'search_view_id': self.env.ref(
                'construction_test.view_test_task_statistics_search').id,
            'domain': [('standard_id', '=', self.id)],
            'context': {'create': False},
        }

# -*- coding: utf-8 -*-

from odoo import models, fields, tools


class CostAnalysisReport(models.Model):
    """
    成本分析報表

    對應舊系統：成本分析
    業務說明：
    - 分析契約金額 vs 實際執行金額
    - 計算各工項損益
    - 支援多維度分析 (按工項/按廠商/按月份)

    技術說明：
    - 使用資料庫視圖 (_auto = False)
    - 即時從 project.task 計算
    - 支援 group_operator 彙總
    """
    _name = 'cost.analysis.report'
    _description = '成本分析報表'
    _auto = False
    _order = 'project_id, item_no'

    # === 基本資訊 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='工程案件',
        readonly=True)

    task_id = fields.Many2one(
        'project.task',
        string='契約工項',
        readonly=True)

    item_no = fields.Char(
        string='工項編號',
        readonly=True)

    item_name = fields.Char(
        string='工項名稱',
        readonly=True)

    unit = fields.Char(
        string='單位',
        readonly=True)

    company_id = fields.Many2one(
        'res.company',
        string='承包廠商',
        readonly=True)

    # === 契約金額 (預算) ===
    contract_qty = fields.Float(
        string='契約數量',
        readonly=True,
        group_operator='sum')

    contract_price = fields.Float(
        string='契約單價',
        readonly=True)

    contract_amount = fields.Float(
        string='契約金額',
        readonly=True,
        group_operator='sum')

    # === 實際執行 ===
    actual_qty = fields.Float(
        string='實際數量',
        readonly=True,
        group_operator='sum')

    actual_amount = fields.Float(
        string='實際金額',
        readonly=True,
        group_operator='sum')

    # === 差異分析 ===
    qty_variance = fields.Float(
        string='數量差異',
        readonly=True,
        group_operator='sum',
        help='實際數量 - 契約數量')

    amount_variance = fields.Float(
        string='金額差異',
        readonly=True,
        group_operator='sum',
        help='實際金額 - 契約金額')

    variance_rate = fields.Float(
        string='差異率 (%)',
        readonly=True,
        help='(實際金額 - 契約金額) / 契約金額 * 100')

    # === 損益分析 ===
    profit_loss = fields.Float(
        string='損益',
        readonly=True,
        group_operator='sum',
        help='契約金額 - 實際金額 (正值為盈餘)')

    profit_loss_rate = fields.Float(
        string='損益率 (%)',
        readonly=True,
        help='(契約金額 - 實際金額) / 契約金額 * 100')

    def init(self):
        """建立資料庫視圖"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    t.id AS id,
                    t.id AS task_id,
                    sp.id AS project_id,
                    t.assigned_company_id AS company_id,
                    t.item_no,
                    t.name AS item_name,
                    t.unit,

                    -- 契約金額
                    COALESCE(t.planned_qty, 0) AS contract_qty,
                    COALESCE(t.unit_price, 0) AS contract_price,
                    COALESCE(t.planned_amount, 0) AS contract_amount,

                    -- 實際執行
                    COALESCE(t.actual_qty, 0) AS actual_qty,
                    COALESCE(t.actual_amount, 0) AS actual_amount,

                    -- 差異分析
                    (COALESCE(t.actual_qty, 0) - COALESCE(t.planned_qty, 0)) AS qty_variance,
                    (COALESCE(t.actual_amount, 0) - COALESCE(t.planned_amount, 0)) AS amount_variance,
                    CASE
                        WHEN COALESCE(t.planned_amount, 0) > 0
                        THEN ((COALESCE(t.actual_amount, 0) - COALESCE(t.planned_amount, 0))
                              / t.planned_amount * 100)
                        ELSE 0
                    END AS variance_rate,

                    -- 損益分析 (契約金額 - 實際成本)
                    (COALESCE(t.planned_amount, 0) - COALESCE(t.actual_amount, 0)) AS profit_loss,
                    CASE
                        WHEN COALESCE(t.planned_amount, 0) > 0
                        THEN ((COALESCE(t.planned_amount, 0) - COALESCE(t.actual_amount, 0))
                              / t.planned_amount * 100)
                        ELSE 0
                    END AS profit_loss_rate

                FROM project_task t
                LEFT JOIN project_project pp ON t.project_id = pp.id
                LEFT JOIN supervision_project sp ON sp.project_id = pp.id
                WHERE (COALESCE(t.planned_amount, 0) > 0 OR COALESCE(t.actual_amount, 0) > 0)
                  AND sp.id IS NOT NULL
            )
        """ % self._table)


class CostAnalysisSummary(models.Model):
    """
    成本分析摘要

    按專案彙總的成本分析
    業務說明：
    - 顯示契約總金額、變更金額、現行契約金額
    - 追蹤實際執行金額與執行率
    - 追蹤估驗金額與估驗率
    - 計算預估損益

    技術說明：
    - 使用資料庫視圖 (_auto = False)
    - 整合 contract_change 模組的變更欄位
    - 整合 payment_estimate 的估驗資料
    """
    _name = 'cost.analysis.summary'
    _description = '成本分析摘要'
    _auto = False
    _order = 'project_id'

    # === 基本資訊 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='工程案件',
        readonly=True)

    project_name = fields.Char(
        string='工程名稱',
        readonly=True)

    project_code = fields.Char(
        string='工程編號',
        readonly=True)

    project_state = fields.Char(
        string='工程狀態',
        readonly=True)

    # === 契約總金額 ===
    total_contract_amount = fields.Float(
        string='契約總金額',
        readonly=True,
        help='原始契約金額')

    # === 變更金額 ===
    total_change_amount = fields.Float(
        string='變更金額',
        readonly=True,
        help='累計變更金額')

    # === 現行契約金額 ===
    current_contract_amount = fields.Float(
        string='現行契約金額',
        readonly=True,
        help='原始契約金額 + 累計變更金額')

    # === 實際執行 ===
    total_actual_amount = fields.Float(
        string='實際執行金額',
        readonly=True,
        help='所有工項的實際完成金額彙總')

    execution_rate = fields.Float(
        string='執行率 (%)',
        readonly=True,
        help='實際執行金額 / 現行契約金額 * 100')

    # === 估驗金額 ===
    total_estimate_amount = fields.Float(
        string='估驗金額',
        readonly=True,
        help='已核定估驗金額彙總')

    estimate_rate = fields.Float(
        string='估驗率 (%)',
        readonly=True,
        help='估驗金額 / 現行契約金額 * 100')

    # === 損益 ===
    profit_loss = fields.Float(
        string='預估損益',
        readonly=True,
        help='現行契約金額 - 實際執行金額')

    profit_loss_rate = fields.Float(
        string='損益率 (%)',
        readonly=True,
        help='預估損益 / 現行契約金額 * 100')

    # === 統計欄位 ===
    task_count = fields.Integer(
        string='工項數',
        readonly=True)

    completed_task_count = fields.Integer(
        string='已完成工項',
        readonly=True)

    def init(self):
        """建立資料庫視圖"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sp.id AS id,
                    sp.id AS project_id,
                    pp.name AS project_name,
                    sp.code AS project_code,
                    sp.state AS project_state,

                    -- 契約金額 (優先使用 original_contract_amount，否則用 contract_amount)
                    COALESCE(sp.original_contract_amount, sp.contract_amount, 0) AS total_contract_amount,

                    -- 變更金額
                    COALESCE(sp.total_change_amount, 0) AS total_change_amount,

                    -- 現行契約金額 (優先使用 current_contract_amount，否則用 contract_amount)
                    COALESCE(sp.current_contract_amount, sp.contract_amount, 0) AS current_contract_amount,

                    -- 實際執行金額 (彙總工項的 actual_amount)
                    COALESCE(task_summary.total_actual, 0) AS total_actual_amount,

                    -- 執行率
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount, 0) > 0
                        THEN (COALESCE(task_summary.total_actual, 0) /
                              COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS execution_rate,

                    -- 估驗金額 (彙總已核定的估驗單)
                    COALESCE(estimate_summary.total_estimate, 0) AS total_estimate_amount,

                    -- 估驗率
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount, 0) > 0
                        THEN (COALESCE(estimate_summary.total_estimate, 0) /
                              COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS estimate_rate,

                    -- 損益
                    (COALESCE(sp.current_contract_amount, sp.contract_amount, 0) -
                     COALESCE(task_summary.total_actual, 0)) AS profit_loss,

                    -- 損益率
                    CASE
                        WHEN COALESCE(sp.current_contract_amount, sp.contract_amount, 0) > 0
                        THEN ((COALESCE(sp.current_contract_amount, sp.contract_amount, 0) -
                               COALESCE(task_summary.total_actual, 0)) /
                              COALESCE(sp.current_contract_amount, sp.contract_amount) * 100)
                        ELSE 0
                    END AS profit_loss_rate,

                    -- 工項統計
                    COALESCE(task_summary.task_count, 0) AS task_count,
                    COALESCE(task_summary.completed_count, 0) AS completed_task_count

                FROM supervision_project sp
                LEFT JOIN project_project pp ON sp.project_id = pp.id

                -- 工項彙總子查詢
                LEFT JOIN (
                    SELECT
                        t.project_id,
                        SUM(COALESCE(t.actual_amount, 0)) AS total_actual,
                        COUNT(t.id) AS task_count,
                        COUNT(CASE WHEN t.actual_date_end IS NOT NULL THEN 1 END) AS completed_count
                    FROM project_task t
                    WHERE t.active = true
                    GROUP BY t.project_id
                ) task_summary ON task_summary.project_id = pp.id

                -- 估驗彙總子查詢
                LEFT JOIN (
                    SELECT
                        pe.project_id,
                        SUM(COALESCE(pe.subtotal, 0)) AS total_estimate
                    FROM payment_estimate pe
                    WHERE pe.state = 'approved'
                    GROUP BY pe.project_id
                ) estimate_summary ON estimate_summary.project_id = sp.id
            )
        """ % self._table)

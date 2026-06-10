# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CostAnalysisImportProjectWizard(models.TransientModel):
    """
    從專案匯入成本分析精靈

    流程：
    1. 選擇專案（state != 'closed'）
    2. 輸入成本分析名稱與預算總價
    3. 確認匯入 → 建立 cost.analysis
    4. 遍歷 project.task → 建立 cost.analysis.line
    5. 保留父子關係
    """
    _name = 'cost.analysis.import.project.wizard'
    _description = '從專案匯入成本分析精靈'

    # === 來源專案 ===
    source_project_id = fields.Many2one(
        'supervision.project',
        string='來源專案',
        required=True,
        domain="[('state', '!=', 'closed'), ('company_id', '=', company_id)]",
        help='選擇要匯入的專案（不可選已結案專案）')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company)

    # === 成本分析資訊 ===
    planning_name = fields.Char(
        string='成本分析名稱',
        required=True,
        help='新建成本分析的名稱')

    total_budget = fields.Monetary(
        string='預算總價',
        required=True,
        currency_field='currency_id',
        help='契約預算總價')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        default=lambda self: self.env.company.currency_id,
        required=True)

    # === 預覽資訊 ===
    task_count = fields.Integer(
        string='工項數',
        compute='_compute_task_count',
        help='來源專案的工項數量')

    estimated_amount = fields.Monetary(
        string='預估總金額',
        compute='_compute_estimated_amount',
        currency_field='currency_id',
        help='來源專案的契約金額')

    @api.depends('source_project_id')
    def _compute_task_count(self):
        """計算工項數量"""
        for wizard in self:
            if wizard.source_project_id:
                wizard.task_count = len(wizard.source_project_id.task_ids)
            else:
                wizard.task_count = 0

    @api.depends('source_project_id')
    def _compute_estimated_amount(self):
        """計算預估總金額"""
        for wizard in self:
            if wizard.source_project_id:
                wizard.estimated_amount = wizard.source_project_id.contract_amount
            else:
                wizard.estimated_amount = 0.0

    @api.onchange('source_project_id')
    def _onchange_source_project_id(self):
        """當選擇專案時，自動填入成本分析名稱與預算總價"""
        if self.source_project_id:
            self.planning_name = self.source_project_id.name
            self.total_budget = self.source_project_id.contract_amount

    # === 執行匯入 ===
    def action_import(self):
        """
        執行匯入

        建立 cost.analysis 與 cost.analysis.line
        保留父子關係
        """
        self.ensure_one()

        if not self.source_project_id:
            raise UserError(_('請選擇來源專案'))

        # 1. 建立 cost.analysis
        planning = self.env['cost.analysis'].create({
            'name': self.planning_name,
            'company_id': self.company_id.id,
            'import_mode': 'project',
            'source_project_id': self.source_project_id.id,
            'total_budget': self.total_budget,
            'state': 'draft',
        })

        # 2. 取得所有工項（包含彙總項）
        tasks = self.source_project_id.task_ids.sorted(lambda t: (t.sequence, t.item_no or '', t.id))

        if not tasks:
            raise UserError(_('來源專案沒有工項'))

        # 3. 建立 task_id 到 line 的映射（用於建立父子關係）
        task_to_line = {}

        # 4. 遍歷所有工項並建立 cost.analysis.line
        for task in tasks:
            # 決定 parent_id
            parent_line_id = False
            if task.parent_id and task.parent_id.id in task_to_line:
                parent_line_id = task_to_line[task.parent_id.id].id

            # 建立 cost.analysis.line
            line = self.env['cost.analysis.line'].create({
                'planning_id': planning.id,
                'parent_id': parent_line_id,
                'sequence': task.sequence,
                'item_no': task.item_no,
                'name': task.name,
                'unit': task.unit,
                'unit_id': task.unit_id.id if task.unit_id else False,
                'ref_item_code': task.ref_item_code or False,
                'task_id': task.id,
                'quantity': task.planned_qty,
                'contract_unit_price': task.unit_price,
            })

            # 記錄映射
            task_to_line[task.id] = line

        # 5. 返回新建的成本分析
        return {
            'type': 'ir.actions.act_window',
            'name': _('成本分析'),
            'res_model': 'cost.analysis',
            'res_id': planning.id,
            'view_mode': 'form',
            'target': 'current',
        }

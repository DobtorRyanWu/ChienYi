# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError


class AddSlipLineWizardLine(models.TransientModel):
    """Wizard 選擇行：顯示可用工項供勾選"""
    _name = 'add.slip.line.wizard.line'
    _description = '加入通報單工項選擇行'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'add.slip.line.wizard', ondelete='cascade')

    selected = fields.Boolean(string='選取', default=False)

    task_id = fields.Many2one('project.task', string='契約工項')

    sequence = fields.Integer(string='排序', default=10)

    # 直接賦值欄位（非 related，避免 TransientModel 解析問題）
    name = fields.Char(string='項目及說明')
    parent_name = fields.Char(string='父工項')
    item_no = fields.Char(string='項目編號')
    unit = fields.Char(string='單位')
    unit_price = fields.Float(string='單價')


class AddSlipLineWizard(models.TransientModel):
    """加入通報單詳細表項目 Wizard（直接列出可選工項）"""
    _name = 'add.slip.line.wizard'
    _description = '加入通報單詳細表項目'

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, readonly=True)

    project_id = fields.Many2one(
        'supervision.project', string='所屬工程',
        related='slip_id.project_id', readonly=True)

    search_term = fields.Char(string='搜尋')

    line_ids = fields.One2many(
        'add.slip.line.wizard.line', 'wizard_id',
        string='可用工項')

    def _get_task_domain(self, slip):
        """取得可用工項的 domain（排除已加入的）"""
        existing_task_ids = slip.detail_line_ids.filtered(
            'task_id').mapped('task_id').ids
        return [
            ('supervision_project_id', '=', slip.project_id.id),
            ('is_summary_item', '=', False),
            ('id', 'not in', existing_task_ids),
        ]

    def _task_to_line_vals(self, task):
        """將 task 轉為 wizard line 的值"""
        return {
            'task_id': task.id,
            'name': task.name or '',
            'parent_name': task.parent_id.name if task.parent_id else '',
            'item_no': task.item_no or '',
            'unit': task.unit or '',
            'unit_price': task.unit_price or 0.0,
            'sequence': task.sequence,
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        slip_id = res.get('slip_id') or self.env.context.get('default_slip_id')
        if slip_id:
            slip = self.env['reservation.notification.slip'].browse(slip_id)
            domain = self._get_task_domain(slip)
            tasks = self.env['project.task'].search(
                domain, order='sequence, item_no, id')
            res['line_ids'] = [
                Command.create(self._task_to_line_vals(t))
                for t in tasks
            ]
        return res

    @api.onchange('search_term')
    def _onchange_search_term(self):
        if not self.slip_id:
            return
        # 記住已勾選的 task_id
        selected_task_ids = set(
            self.line_ids.filtered('selected').mapped('task_id').ids
        )
        # 查詢符合條件的工項
        domain = self._get_task_domain(self.slip_id)
        if self.search_term:
            domain += ['|', '|',
                ('name', 'ilike', self.search_term),
                ('item_no', 'ilike', self.search_term),
                ('parent_id.name', 'ilike', self.search_term),
            ]
        tasks = self.env['project.task'].search(
            domain, order='sequence, item_no, id')
        task_ids_in_result = set(tasks.ids)

        new_lines = []
        # 保留已勾選但不在搜尋結果中的項目
        for line in self.line_ids.filtered('selected'):
            if line.task_id.id not in task_ids_in_result:
                new_lines.append(Command.create({
                    'task_id': line.task_id.id,
                    'name': line.name,
                    'parent_name': line.parent_name,
                    'item_no': line.item_no,
                    'unit': line.unit,
                    'unit_price': line.unit_price,
                    'sequence': line.sequence,
                    'selected': True,
                }))
                task_ids_in_result.add(line.task_id.id)

        # 加入搜尋結果
        for t in tasks:
            vals = self._task_to_line_vals(t)
            vals['selected'] = t.id in selected_task_ids
            new_lines.append(Command.create(vals))

        self.line_ids = [Command.clear()] + new_lines

    def action_add_lines(self):
        """將勾選的工項建立為通報單明細"""
        self.ensure_one()
        selected = self.line_ids.filtered(
            lambda l: l.selected and l.task_id)
        if not selected:
            raise UserError('請至少勾選一個契約工項')

        SlipLine = self.env['reservation.notification.slip.line']
        for line in selected:
            task = line.task_id
            SlipLine.create({
                'slip_id': self.slip_id.id,
                'task_id': task.id,
                'item_no': task.item_no or '',
                'description': task.name or '',
                'unit': task.unit or '',
                'unit_price': task.unit_price or 0.0,
            })

        return {'type': 'ir.actions.act_window_close'}

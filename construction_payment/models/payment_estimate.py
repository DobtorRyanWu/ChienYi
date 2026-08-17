# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class PaymentEstimate(models.Model):
    """
    估驗計價

    重構版本：
    - 以「匯入工程案件」為核心操作流程
    - 簡化狀態為 草稿→待核定→已核定→已歸檔
    - 移除多公司架構、驗收單關聯、保留款等
    """
    _name = 'payment.estimate'
    _description = '估驗計價'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'estimate_no asc, id desc'

    # ⚠️ 必須是 DEFERRABLE INITIALLY DEFERRED，不能用普通 UNIQUE。
    #
    # `_resequence_estimate_no()` 是逐筆 write，排序變動時中間狀態必然撞號——
    # 例如 1,2,3 要重排成 3,1,2，寫第一筆就跟現有的 1 相撞。
    # 2026-08-07 實測（交易內加約束、觸發排列置換、再 rollback）：
    #     普通 UNIQUE(project_id, estimate_no)  → UniqueViolation
    #     同樣操作 + DEFERRABLE INITIALLY DEFERRED → 通過
    # 延遲到 COMMIT 才檢查，中間過程允許暫時重複，最終狀態仍保證唯一。
    #
    # 這個約束長期記為 BLOCKED，因為舊資料有重複；2026-08-07 清掉 9 張
    # 無工程無明細的孤兒估驗（ids 113-116、137-141）後，重複組數歸零才得以建立。
    _sql_constraints = [
        ('unique_project_estimate_no',
         'UNIQUE (project_id, estimate_no) DEFERRABLE INITIALLY DEFERRED',
         '同一工程的估驗次數不能重複。'),
    ]

    # === 基本資訊 ===
    name = fields.Char(
        '估驗名稱',
        readonly=True,
        copy=False,
        help='自動產生，格式：第N次估驗計價'
    )
    estimate_no = fields.Integer(
        '次數',
        readonly=True,
        copy=False,
        help='同一工程中自動遞增'
    )

    # === 工程資訊區塊（全部 readonly，由匯入帶入）===
    project_id = fields.Many2one(
        'project.project',
        '所屬工程',
        ondelete='cascade',
        readonly=True,
        tracking=True,
        index=True
    )
    # 2026-08-18 移除 slip_id：估驗計價與通報單在功能上無關。
    #   估驗詳細表的結構是「契約詳細價目表 × 期別」（群組/項次/單價全繼承自契約），
    #   通報單不出現在計價單上；模型的每一項計算（估驗次數重排、前期累計、可估數量、
    #   唯一性約束）也都以 project + estimate_date + task 為軸，從不經過 slip。
    #   兩者只是透過共同的 project.task 產生關聯，是兄弟而非父子——
    #   原本的 slip_id 是「精靈的取數捷徑」被誤升格成資料模型。
    #   實證：一期估驗橫跨多張通報單、一張通報單的量也會被切到多期
    #   （P11001 第 15/16 次橫跨第 7、8 期；第 6 次 11-28 完工卻在第 8 期才估），
    #   所以單值 M2O、M2M、由 task_id 反查三種形狀沒有一種表達得了。
    contract_no = fields.Char(
        '契約編號',
        related='project_id.contract_no',
        store=True,
        readonly=True
    )
    contract_amount = fields.Monetary(
        '契約金額',
        related='project_id.contract_amount',
        store=True,
        readonly=True
    )

    # === 估驗資訊區塊 ===
    estimate_date = fields.Date(
        '估驗日期',
        tracking=True,
        help='估驗截止日期，施工日誌累計以此日期為節點'
    )
    submitted_date = fields.Datetime(
        '提出日期',
        readonly=True
    )
    submitted_by_id = fields.Many2one(
        'res.users',
        '提出人',
        readonly=True
    )
    approved_by_id = fields.Many2one(
        'res.users',
        '核定人',
        readonly=True
    )
    approved_date = fields.Datetime(
        '核定日期',
        readonly=True
    )

    # === 金額 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    subtotal = fields.Monetary(
        '本次估驗總金額',
        compute='_compute_subtotal',
        store=True,
        tracking=True
    )

    # === 計價明細 ===
    line_ids = fields.One2many(
        'payment.estimate.line',
        'estimate_id',
        '估驗計價表',
        copy=True
    )

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('pending_approval', '待核定'),
        ('approved', '已核定'),
        ('archived', '已歸檔'),
    ], default='draft', tracking=True, string='狀態')

    # === 計算欄位 ===
    @api.depends('line_ids.estimate_amount', 'line_ids.is_summary_item')
    def _compute_subtotal(self):
        """計算本次估驗總金額（只加總葉節點，避免彙總列重複計算）"""
        for rec in self:
            leaf_lines = rec.line_ids.filtered(lambda l: not l.is_summary_item)
            rec.subtotal = sum(leaf_lines.mapped('estimate_amount'))

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立後依估驗日期重排次數與名稱

        次數（第N次）以 estimate_date 先後決定，而非建立順序。故建立時先給暫定名稱，
        再對受影響工程呼叫 _resequence_estimate_no 依日期整體重排。
        """
        for vals in vals_list:
            if not vals.get('name'):
                estimate_no = vals.get('estimate_no') or 1
                vals['name'] = f'第{estimate_no}次估驗計價'
        records = super().create(vals_list)
        if not self.env.context.get('_skip_estimate_resequence'):
            for project in records.mapped('project_id'):
                self._resequence_estimate_no(project.id)
        return records

    def write(self, vals):
        """估驗日期變動時，重排該工程所有估驗單的次數（第N次依日期先後）"""
        res = super().write(vals)
        if 'estimate_date' in vals and not self.env.context.get('_skip_estimate_resequence'):
            for project in self.mapped('project_id'):
                self._resequence_estimate_no(project.id)
        return res

    @api.model
    def _resequence_estimate_no(self, project_id):
        """依 estimate_date 先後，重排整個工程的 estimate_no 與 name。

        無估驗日期者排在最後（PostgreSQL ASC 預設 NULLS LAST）。以 _skip 旗標
        避免 write 遞迴。
        """
        if not project_id:
            return
        estimates = self.with_context(_skip_estimate_resequence=True).search(
            [('project_id', '=', project_id)],
            order='estimate_date asc, id asc',
        )
        for idx, est in enumerate(estimates, start=1):
            vals = {}
            if est.estimate_no != idx:
                vals['estimate_no'] = idx
            new_name = f'第{idx}次估驗計價'
            if est.name != new_name:
                vals['name'] = new_name
            if vals:
                est.with_context(_skip_estimate_resequence=True).write(vals)

    # === 動作方法 ===
    def action_open_import_wizard(self):
        """開啟匯入工程案件 Wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入工程案件',
            'res_model': 'estimate.import.wizard',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_estimate_id': self.id,
            },
        }

    def action_submit_estimate(self):
        """提出估驗"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('請先匯入工程案件')
            rec.write({
                'state': 'pending_approval',
                'submitted_by_id': self.env.uid,
                'submitted_date': fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        """核定"""
        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })
        return True

    def action_archive_estimate(self):
        """歸檔"""
        self.write({'state': 'archived'})
        return True

    def action_reset_to_draft(self):
        """退回草稿：僅切換狀態，保留明細與工程資訊

        （原本會清空 line_ids 與 project_id，導致填寫的資料全失、且因清空工程而從
        依工程分組的清單中消失。退回草稿的語意應僅為狀態回退，不應銷毀資料。）
        """
        for rec in self:
            if rec.state != 'pending_approval':
                raise UserError('只有「待核定」狀態才能退回草稿')
            rec.write({
                'state': 'draft',
                'submitted_by_id': False,
                'submitted_date': False,
            })
        return True

    def action_backfill_summary_lines(self):
        """一鍵補列：將彙總工項補進現有估驗單並重排序號

        - 僅處理草稿／待核定且已有所屬工程的估驗單
        - 既有行重排序號；既有彙總列數量正規化為 1
        - 缺少的工項新建明細（彙總列依「一式」慣例 qty=1）
        - 已核定／已歸檔不受影響
        """
        Task = self.env['project.task']
        updated = 0
        for est in self:
            if est.state not in ('draft', 'pending_approval') or not est.project_id:
                continue

            # 取得工程全部有效工項（含彙總項），依樹狀順序
            tasks = Task.search([
                ('supervision_project_id', '=', est.project_id.id),
                ('active', '=', True),
            ], order='sequence, id')
            if not tasks:
                continue

            existing = {l.task_id.id: l for l in est.line_ids}
            new_lines = []
            for idx, task in enumerate(tasks, start=1):
                seq = idx * 10
                if task.id in existing:
                    line = existing[task.id]
                    line.sequence = seq
                    # 既有彙總列：數量正規化為 1（一式）
                    if task.is_summary_item:
                        line.contract_qty = 1.0
                        line.approved_qty = 1.0
                        line.estimate_qty = 1.0
                else:
                    new_lines.append(Command.create(
                        self.env['payment.estimate.line']._prepare_line_vals(task, seq)
                    ))
            if new_lines:
                est.write({'line_ids': new_lines})
            updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '補列完成',
                'message': f'已處理 {updated} 筆估驗單，補上彙總項並重排序號。',
                'type': 'success',
                'sticky': False,
            },
        }


class PaymentEstimateLine(models.Model):
    """
    估驗計價明細

    欄位說明：
    - contract_qty: 原始契約數量（變更前）
    - approved_qty: 變更後核定數量（現行 planned_qty）
    - available_qty: 本次可估驗數量（施工日誌截至估驗日期的累計）
    - estimate_qty: 本次估驗數量（唯一可編輯欄位）
    - cumulative_estimate_qty: 累計估驗數量（歷次已核定 + 本次）
    """
    _name = 'payment.estimate.line'
    _description = '估驗計價明細'
    _order = 'sequence, id'

    # === 關聯 ===
    estimate_id = fields.Many2one(
        'payment.estimate',
        '估驗單',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer('序號', default=10)

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task',
        '工項',
        required=True,
        readonly=True
    )
    is_summary_item = fields.Boolean(
        '彙總項',
        related='task_id.is_summary_item',
        store=True,
        readonly=True,
        help='有子項的父工項，於估驗表以「一式」呈現（數量固定為 1、金額為子項小計）'
    )

    # === 工項資訊（readonly）===
    description = fields.Char(
        '項目及說明',
        related='task_id.name',
        store=True,
        readonly=True
    )
    parent_item_name = fields.Char(
        '父工項路徑',
        compute='_compute_parent_item_name',
        store=True,
        readonly=True
    )
    item_no = fields.Char(
        '項目編號',
        related='task_id.item_no',
        store=True,
        readonly=True
    )
    unit = fields.Char(
        '單位',
        related='task_id.unit',
        store=True,
        readonly=True
    )

    # === 數量與單價（readonly，由匯入帶入）===
    contract_qty = fields.Float(
        '原始契約數量',
        digits=(16, 4),
        readonly=True,
        help='原始契約數量（變更前）'
    )
    approved_qty = fields.Float(
        '變更後核定數量',
        digits=(16, 4),
        readonly=True,
        help='經契約變更後的現行數量'
    )
    unit_price = fields.Float(
        '單價',
        digits=(16, 2),
        readonly=True
    )

    # === 估驗數量（唯一可編輯）===
    estimate_qty = fields.Float(
        '本次估驗數量',
        digits=(16, 4),
        help='本次估驗的數量（唯一可編輯欄位）'
    )

    # === 計算欄位 ===
    available_qty = fields.Float(
        '本次可估驗數量',
        digits=(16, 4),
        compute='_compute_available_qty',
        readonly=True,
        help='施工日誌截至估驗日期的累計完成數量（即時計算，日誌更新後自動反映）'
    )
    previous_approved_qty = fields.Float(
        '前期已核定累計數量',
        digits=(16, 4),
        compute='_compute_previous_approved_qty',
        readonly=True,
        help='估驗日期早於本次、且已核定的估驗單，本工項的估驗數量合計。'
             '不依賴本次估驗數量，故本表即時編輯時保持穩定'
    )
    cumulative_estimate_qty = fields.Float(
        '累計估驗數量',
        digits=(16, 4),
        compute='_compute_cumulative',
        readonly=True,
        help='前期已核定累計 + 本次（純算術，即時更新；非儲存以反映他單核定）'
    )
    estimate_amount = fields.Float(
        '本次估驗金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True,
        readonly=True,
        help='單價 × 本次估驗數量'
    )
    cumulative_estimate_amount = fields.Float(
        '累計估驗金額',
        digits=(16, 2),
        compute='_compute_cumulative',
        readonly=True,
        help='單價 × 累計估驗數量（非儲存）'
    )

    # === 備註 ===
    note = fields.Text('備註', readonly=True)

    # === 建立 vals helper ===
    @api.model
    def _prepare_line_vals(self, task, sequence):
        """依工項產生估驗明細 vals（不含 estimate_id）

        彙總項採「一式」慣例：數量固定 1、單價 0（金額由子項加總）。
        葉節點：契約量/核定量/單價由工項帶入，本次估驗量預設 0。
        """
        if task.is_summary_item:
            return {
                'task_id': task.id,
                'sequence': sequence,
                'contract_qty': 1.0,
                'approved_qty': 1.0,
                'unit_price': 0.0,
                'estimate_qty': 1.0,
            }
        contract_qty = task.planned_qty
        if getattr(task, 'original_planned_qty', 0):
            contract_qty = task.original_planned_qty
        return {
            'task_id': task.id,
            'sequence': sequence,
            'contract_qty': contract_qty,
            'approved_qty': task.planned_qty,
            'unit_price': task.unit_price,
            'estimate_qty': 0.0,
        }

    # === 計算方法 ===
    @api.depends('task_id.parent_id', 'task_id.parent_id.full_item_path')
    def _compute_parent_item_name(self):
        """計算父工項路徑"""
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.full_item_path or ''
            else:
                line.parent_item_name = ''

    @api.model
    def _get_cumulative_qty_at(self, task, date):
        """取得某工項截至指定日期的施工日誌累計完成量"""
        if not task or not date:
            return 0.0
        last_log = self.env['daily.log.line'].search([
            ('work_item_id', '=', task.id),
            ('date', '<=', date),
        ], order='date desc, id desc', limit=1)
        return last_log.cumulative_qty if last_log else 0.0

    @api.depends('task_id', 'estimate_id.estimate_date', 'estimate_id.project_id')
    def _compute_available_qty(self):
        """計算本次可估驗數量（本期完成量）

        本期 = 累計到(本次估驗日) − 累計到(前一張估驗單估驗日)
        前一張：同工程、估驗日較早、排除自己，依日期取最近一筆（不論狀態）。
        彙總項採「一式」慣例固定回 1。
        """
        for line in self:
            if line.is_summary_item:
                line.available_qty = 1.0
                continue
            if not line.task_id or not line.estimate_id.estimate_date:
                line.available_qty = 0.0
                continue
            this_date = line.estimate_id.estimate_date
            cumulative_to_date = self._get_cumulative_qty_at(line.task_id, this_date)

            prev_estimate = self.env['payment.estimate'].search([
                ('project_id', '=', line.estimate_id.project_id.id),
                ('estimate_date', '<', this_date),
                ('id', '!=', line.estimate_id.id),
            ], order='estimate_date desc, id desc', limit=1)
            prev_cumulative = 0.0
            if prev_estimate:
                prev_cumulative = self._get_cumulative_qty_at(
                    line.task_id, prev_estimate.estimate_date
                )
            line.available_qty = cumulative_to_date - prev_cumulative

    def _get_descendant_leaf_lines(self):
        """取得同一估驗單中，屬於本彙總項底下的所有葉節點明細行"""
        self.ensure_one()
        if not self.task_id or not self.estimate_id:
            return self.browse()
        descendant_ids = set(self.env['project.task'].search([
            ('id', 'child_of', self.task_id.id),
        ]).ids)
        return self.estimate_id.line_ids.filtered(
            lambda l: l.task_id.id in descendant_ids and not l.is_summary_item
        )

    @api.depends('estimate_qty', 'unit_price', 'is_summary_item',
                 'estimate_id.line_ids.estimate_qty',
                 'estimate_id.line_ids.unit_price')
    def _compute_amounts(self):
        """計算本次估驗金額（彙總項加總底下葉節點，避免重複計算）"""
        for line in self:
            if line.is_summary_item:
                leaf_lines = line._get_descendant_leaf_lines()
                line.estimate_amount = sum(
                    l.unit_price * l.estimate_qty for l in leaf_lines
                )
            else:
                line.estimate_amount = line.unit_price * line.estimate_qty

    @api.depends('task_id', 'is_summary_item',
                 'estimate_id.project_id', 'estimate_id.estimate_date')
    def _compute_previous_approved_qty(self):
        """前期已核定累計數量：估驗日期「早於本次」且已核定的估驗單合計。

        以 estimate_date 作為先後判定（次數是「數量+1」不代表時間先後，日期最保險）。
        本值不依賴本次 estimate_qty，故在估驗表即時編輯時保持穩定，
        累計欄位得以純算術（前期 + 本次）即時重算。非儲存：他單核定後重讀即更新。
        """
        for line in self:
            est = line.estimate_id
            if (line.is_summary_item or not line.task_id
                    or not est.project_id or not est.estimate_date):
                line.previous_approved_qty = 0.0
                continue
            prev_lines = self.search([
                ('task_id', '=', line.task_id.id),
                ('estimate_id.project_id', '=', est.project_id.id),
                # archived 是「已核定後歸檔」，其數量仍為有效核定量，須一併計入前期累計，
                # 否則前期估驗一歸檔，後期累計就會漏掉該期數量。
                ('estimate_id.state', 'in', ('approved', 'archived')),
                ('estimate_id.estimate_date', '<', est.estimate_date),
            ])
            line.previous_approved_qty = sum(prev_lines.mapped('estimate_qty'))

    @api.depends('estimate_qty', 'unit_price', 'previous_approved_qty', 'is_summary_item',
                 'estimate_id.line_ids.estimate_qty',
                 'estimate_id.line_ids.unit_price',
                 'estimate_id.line_ids.previous_approved_qty')
    def _compute_cumulative(self):
        """計算累計估驗數量與金額（純算術，即時更新）

        葉節點：累計 = 前期已核定累計 + 本次；金額 = 單價 × 累計。
        彙總項：數量採「一式」固定 1；金額 = 底下葉節點的 單價×(前期+本次) 之和
                （直接讀葉節點原始欄位算術，不讀其計算欄位，避免計算順序造成讀到舊值）。
        """
        for line in self:
            if line.is_summary_item:
                leaf_lines = line._get_descendant_leaf_lines()
                line.cumulative_estimate_qty = 1.0
                line.cumulative_estimate_amount = sum(
                    l.unit_price * (l.previous_approved_qty + l.estimate_qty)
                    for l in leaf_lines
                )
                continue
            line.cumulative_estimate_qty = line.previous_approved_qty + line.estimate_qty
            line.cumulative_estimate_amount = line.unit_price * line.cumulative_estimate_qty

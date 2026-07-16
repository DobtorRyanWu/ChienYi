# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ContractChangeOrder(models.Model):
    """
    契約變更單

    設計說明 (v5.2): 參考 OCA project_version 設計模式
    - 追蹤金額、數量、工期變更
    - 支援新增、修改、刪除工項
    - 累計計算當前契約狀態

    狀態流程:
    draft -> submitted -> reviewing -> approved -> applied
                                   -> rejected
    """
    _name = 'contract.change.order'
    _description = '契約變更單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, create_date desc'

    # === 基本資訊 ===
    name = fields.Char(
        string='變更編號',
        required=True,
        copy=False,
        readonly=True,
        default='/',
        tracking=True,
        help='系統自動編號')

    sequence = fields.Integer(
        string='序號',
        default=10,
        help='變更順序（Odoo 列表排序用，非「第幾次變更」）')

    change_no = fields.Integer(
        string='本專案第幾次變更',
        compute='_compute_change_no',
        store=True,
        help='此變更單在所屬工程中的變更次序（1-based，依建立先後）。'
             '「第N次契約變更」標示一律以此為準，不可用 sequence。')

    @api.depends('project_id', 'project_id.change_order_ids', 'create_date')
    def _compute_change_no(self):
        for order in self:
            if not order.project_id:
                order.change_no = 0
                continue
            siblings = order.project_id.change_order_ids.sorted(
                key=lambda o: (o.create_date or fields.Datetime.now(), o.id))
            try:
                order.change_no = list(siblings).index(order) + 1
            except ValueError:
                order.change_no = 0

    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        ondelete='cascade',
        tracking=True,
        domain="[('state', 'in', ['construction', 'completion', 'acceptance'])]",
        help='關聯的工程案件（透過「匯入工程案件」設定）')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        help='管理公司 (繼承自工程案件)')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='project_id.currency_id',
        store=True)

    # === 變更資訊 ===
    change_reason = fields.Selection([
        ('design', '設計變更'),
        ('site_condition', '現場條件變更'),
        ('owner_request', '業主需求'),
        ('regulation', '法規要求'),
        ('price_adjustment', '物價調整'),
        ('other', '其他'),
    ], string='變更原因',
       required=True,
       default='design',
       tracking=True)

    change_reason_detail = fields.Text(
        string='變更說明',
        tracking=True,
        help='詳細說明變更原因與內容')

    other_reason_detail = fields.Char(
        string='其他原因說明',
        tracking=True,
        help='當變更原因選擇「其他」時，請說明具體原因')

    change_date = fields.Date(
        string='變更日期',
        default=fields.Date.context_today,
        tracking=True)

    # === 原始契約資訊（= 頂層彙總項變更前金額加總，非快照）===
    original_contract_amount = fields.Monetary(
        string='變更前契約金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='執行變更前的契約金額（= 各頂層彙總項變更前金額加總）')

    # === 本次變更金額 ===
    change_amount = fields.Monetary(
        string='本次變更金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='本次變更增減金額 (正:增加, 負:減少) = 變更後 - 變更前')

    change_amount_rate = fields.Float(
        string='變更比率 (%)',
        compute='_compute_amount_totals',
        store=True,
        digits=(16, 4),
        help='變更金額佔原契約金額的百分比（小數，如 0.2567 = 25.67%）')

    # === 變更後金額 ===
    new_contract_amount = fields.Monetary(
        string='變更後契約金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='變更後的契約總金額（= 各頂層彙總項變更後金額加總）')

    # === 變更明細 ===
    line_ids = fields.One2many(
        'contract.change.order.line',
        'change_order_id',
        string='變更明細',
        copy=True)

    line_count = fields.Integer(
        string='明細筆數',
        compute='_compute_line_count')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('applied', '已套用'),
        ('rejected', '已駁回'),
    ], string='狀態',
       default='draft',
       tracking=True,
       index=True)

    # === 審核資訊 ===
    submitted_by_id = fields.Many2one(
        'res.users',
        string='提送人',
        readonly=True)

    submitted_date = fields.Datetime(
        string='提送時間',
        readonly=True)

    reviewed_by_id = fields.Many2one(
        'res.users',
        string='審核人',
        readonly=True)

    reviewed_date = fields.Datetime(
        string='審核時間',
        readonly=True)

    approved_by_id = fields.Many2one(
        'res.users',
        string='核定人',
        readonly=True)

    approved_date = fields.Datetime(
        string='核定時間',
        readonly=True)

    applied_by_id = fields.Many2one(
        'res.users',
        string='套用人',
        readonly=True)

    applied_date = fields.Datetime(
        string='套用時間',
        readonly=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        readonly=True)

    # === 備註 ===
    notes = fields.Html(
        string='備註')

    # === 權限計算欄位 ===
    is_change_leader = fields.Boolean(
        compute='_compute_is_change_leader',
        string='是否為專案負責人')

    @api.depends('project_id.project_leader_id')
    def _compute_is_change_leader(self):
        is_admin = self.env.user.has_group(
            'construction_supervision_base.group_supervisor_admin')
        for rec in self:
            leader = rec.project_id.project_leader_id
            # 未設定負責人時不限制；管理者永遠有權限
            rec.is_change_leader = (
                is_admin or
                not leader or
                self.env.user == leader
            )

    # === 計算欄位 ===
    @api.depends('line_ids')
    def _compute_line_count(self):
        for order in self:
            order.line_count = len(order.line_ids)

    @api.depends('line_ids.original_amount', 'line_ids.new_amount',
                 'line_ids.item_level')
    def _compute_amount_totals(self):
        """契約金額一律以「頂層彙總項（item_level == 0）加總」為單一真實來源。

        概念（薪資統計類比）：各頂層「部門」彙總項各自由下而上算出（明細端
        wizard 已含稅什費 tax_misc_rate 比率），再加總所有頂層彙總項。
          變更前 = Σ 頂層 original_amount
          變更後 = Σ 頂層 new_amount
          本次變更 = 變更後 - 變更前
        不再使用「快照 original + Σ change」的鏈式累積（會逐次累積誤差）。
        """
        for order in self:
            top = order.line_ids.filtered(lambda l: l.item_level == 0)
            order.original_contract_amount = sum(top.mapped('original_amount'))
            order.new_contract_amount = sum(top.mapped('new_amount'))
            order.change_amount = (
                order.new_contract_amount - order.original_contract_amount)
            if order.original_contract_amount:
                order.change_amount_rate = (
                    order.change_amount / order.original_contract_amount)
            else:
                order.change_amount_rate = 0.0

    # === Onchange ===
    # 註：original_contract_amount 已改為由明細（頂層彙總項）計算，
    #     不再於選擇工程時快照 current_contract_amount（避免鏈式累積誤差）。

    # === 約束 ===
    @api.constrains('line_ids')
    def _check_line_ids(self):
        """檢查變更明細"""
        for order in self:
            if order.state != 'draft' and not order.line_ids:
                raise ValidationError('契約變更單必須至少包含一筆變更明細！')

    # === 狀態動作 ===
    def action_submit(self):
        """提送審查"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以提送！')
        if not self.project_id:
            raise UserError('請先透過「匯入工程案件」設定所屬工程！')
        if not self.line_ids:
            raise UserError('請先新增變更明細！')

        # 註：original_contract_amount 由 _compute_amount_totals 自明細計算，無需快照。

        self.write({
            'state': 'submitted',
            'submitted_by_id': self.env.uid,
            'submitted_date': fields.Datetime.now(),
        })

    def action_review(self):
        """開始審查"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError('只有已提送狀態可以開始審查！')

        self.write({
            'state': 'reviewing',
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_approve(self):
        """核定通過"""
        self.ensure_one()
        if self.state != 'reviewing':
            raise UserError('只有審查中狀態可以核定！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能核定！')

        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })

    def action_reject(self):
        """開啟駁回精靈"""
        self.ensure_one()
        if self.state not in ('submitted', 'reviewing'):
            raise UserError('只有已提送或審查中狀態可以駁回！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能駁回！')

        return {
            'type': 'ir.actions.act_window',
            'name': '駁回變更單',
            'res_model': 'contract.change.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_change_order_id': self.id,
            },
        }

    def action_do_reject(self, reason):
        """執行駁回"""
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'rejection_reason': reason,
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_apply(self):
        """套用變更"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('只有已核定狀態可以套用變更！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能套用變更！')

        # 套用變更至工項
        self._apply_changes_to_tasks()

        # 更新專案契約金額與工期
        self._update_project_contract()

        self.write({
            'state': 'applied',
            'applied_by_id': self.env.uid,
            'applied_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        """重設為草稿"""
        self.ensure_one()
        if self.state not in ('submitted', 'rejected'):
            raise UserError('只有已提送或已駁回狀態可以重設為草稿！')

        vals = {
            'state': 'draft',
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'rejection_reason': False,
        }
        if self.state == 'approved':
            vals.update({
                'approved_by_id': False,
                'approved_date': False,
            })
        self.write(vals)

    # === 套用變更邏輯 ===
    def _apply_changes_to_tasks(self):
        """套用變更至工項"""
        self.ensure_one()
        ProjectTask = self.env['project.task']

        # ── 新增(add)：拓樸建立（父先於子）──────────────────────────
        # 支援「本次新增的彙總群組」：子項以 parent_line_id 指向同變更的群組新增列，
        # 該群組此時尚非 task；故先建父群組、記入 line2task，子項再用它解析 parent_id。
        # （借鏡標單匯入 tender_import_wizard 的 task_map 階層建立法。）
        add_lines = self.line_ids.filtered(lambda l: l.change_type == 'add')
        line2task = {}
        pending = list(add_lines)
        guard = 0
        while pending:
            guard += 1
            if guard > 50:
                raise UserError('契約變更新增項父子關係解析超過上限，疑有循環參照。')
            progressed = False
            still = []
            for line in pending:
                if line.parent_line_id:
                    ptask = line2task.get(line.parent_line_id.id)
                    if not ptask:
                        still.append(line)          # 父群組尚未建立 → 下一輪
                        continue
                    parent_id = ptask.id
                elif line.parent_task_id:
                    parent_id = line.parent_task_id.id
                else:
                    parent_id = False               # 新增的頂層彙總群組
                line2task[line.id] = self._create_added_task(line, parent_id)
                progressed = True
            pending = still
            if pending and not progressed:
                raise UserError(
                    '契約變更新增項找不到父項（缺父或循環）：%s'
                    % '、'.join(l.item_name or '?' for l in pending))

        # ── 修改/歸零/刪除（與新增無相依，順序無關）─────────────────
        for line in self.line_ids:
            if line.change_type == 'modify' and line.task_id:
                # 凍結原始契約數量（僅第一次變更時）
                if not line.task_id.original_planned_qty:
                    line.task_id.original_planned_qty = line.task_id.planned_qty
                # 修改工項
                line.task_id.write({
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],  # 新增到 Many2many
                })
                # 建立版本記錄
                next_version = max(line.task_id.version_ids.mapped('version') or [0]) + 1
                self.env['project.task.version'].create({
                    'task_id': line.task_id.id,
                    'version': next_version,
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_date': self.change_date or fields.Date.today(),
                    'change_reason': self.name,
                    'change_order_id': self.id,
                })
                
            elif line.change_type == 'zero_out' and line.task_id:
                # 歸零：工項保留、數量歸零（保留原單價供參考），並建立版本記錄
                if not line.task_id.original_planned_qty:
                    line.task_id.original_planned_qty = line.task_id.planned_qty
                line.task_id.write({
                    'planned_qty': 0.0,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],
                })
                next_version = max(line.task_id.version_ids.mapped('version') or [0]) + 1
                self.env['project.task.version'].create({
                    'task_id': line.task_id.id,
                    'version': next_version,
                    'planned_qty': 0.0,
                    'unit_price': line.task_id.unit_price,  # 保留原單價
                    'change_date': self.change_date or fields.Date.today(),
                    'change_reason': self.name,
                    'change_order_id': self.id,
                })

            elif line.change_type == 'delete' and line.task_id:
                # 標記刪除 (不實際刪除，保留歷史)
                line.task_id.write({
                    'active': False,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],  # 新增到 Many2many
                })

        # ── 結構變更後，整個專案以樹狀 DFS 重編 sequence ──────────────
        # 新增/刪除會讓同父 max+10 的序號跨越下一彙總項區間造成亂序；
        # 重編後保證「父 < 子孫 < 下一兄弟」，徹底消除跨彙總項撞號。
        if self.project_id and self.project_id:
            ProjectTask._resequence_project_sequence(self.project_id.id)

    def _create_added_task(self, line, parent_id):
        """建立一筆新增工項 task（parent_id 已由拓樸解析：既有彙總項或本次新建群組）。
        回傳建立的 project.task。item_level/planned_amount 由 compute 自動處理。"""
        self.ensure_one()
        ProjectTask = self.env['project.task']
        display_unit = ProjectTask._normalize_unit_display(line.unit)
        vals = {
            'project_id': self.project_id.id,
            'name': line.item_name,
            'item_no': line.item_no,
            'planned_qty': line.new_qty,
            'unit': display_unit,
            'unit_id': ProjectTask._resolve_uom_id(display_unit),
            'unit_price': line.new_unit_price,
            'change_order_id': self.id,
            'specification': line.specification or '',
            'ref_item_code': line.ref_item_code or '',
        }
        if line.ref_item_code:
            product = self.env['product.product'].search(
                [('default_code', '=', line.ref_item_code)], limit=1)
            if product:
                vals['product_id'] = product.id
        # 排序：排在同父既有子項之後（避免新增項用預設 sequence 擠到最前造成亂序）
        if parent_id:
            vals['parent_id'] = parent_id
            parent = ProjectTask.browse(parent_id)
            siblings = parent.child_ids
            base_seq = max(siblings.mapped('sequence')) if siblings else (parent.sequence or 0)
            vals['sequence'] = base_seq + 10
        else:
            top = ProjectTask.search([('project_id', '=', vals['project_id']),
                                      ('parent_id', '=', False)])
            vals['sequence'] = (max(top.mapped('sequence')) if top else 0) + 10

        task = ProjectTask.create(vals)
        task.write({'change_order_ids': [(4, self.id)]})
        if task.version_ids:
            task.version_ids[0].write({
                'change_order_id': self.id,
                'change_date': self.change_date or fields.Date.today(),
                'change_reason': self.name,
            })
        return task

    def _update_project_contract(self):
        """契約變更套用時不修改 contract_end_date（預定契約完工日）。
        該欄位由進度表啟用（_do_activate）時寫回 adjusted_end_date，確保單一更新來源。
        contract_amount 由 ORM 依賴追蹤（task_ids.planned_amount）自動重算。
        """
        pass

    # === CRUD 覆寫 ===
    def _generate_change_order_name(self):
        """產生變更編號：{工程編號}-CHG-{N:02d}"""
        self.ensure_one()
        if not self.project_id:
            return '/'
        # 計算此工程已有的變更單數量（排除自身）
        existing_count = self.search_count([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
        ])
        n = existing_count + 1
        return f"{self.project_id.code}-CHG-{n:02d}"

    @api.model_create_multi
    def create(self, vals_list):
        # 先建立記錄取得 id，再依工程編號產生變更編號
        records = super().create(vals_list)
        for record in records:
            if record.name == '/' and record.project_id:
                record.name = record._generate_change_order_name()
        return records

    def write(self, vals):
        result = super().write(vals)
        # 當 project_id 首次設定時，自動產生變更編號
        if vals.get('project_id'):
            for record in self:
                if record.name == '/':
                    record.name = record._generate_change_order_name()
        return result

    def unlink(self):
        for order in self:
            if order.state not in ('draft', 'rejected'):
                raise UserError('只有草稿或已駁回的變更單可以刪除！')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': '/',
            'state': 'draft',
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'approved_by_id': False,
            'approved_date': False,
            'applied_by_id': False,
            'applied_date': False,
            'rejection_reason': False,
        })
        return super().copy(default)

    # === 匯入工程案件 ===
    def action_open_import_wizard(self):
        """開啟匯入工程案件精靈"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入工程案件',
            'res_model': 'contract.change.wizard',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_change_order_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }


    # === 檢視動作 ===
    def action_view_lines(self):
        """查看變更明細"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '變更明細',
            'res_model': 'contract.change.order.line',
            'view_mode': 'list,form',
            'domain': [('change_order_id', '=', self.id)],
            'context': {
                'default_change_order_id': self.id,
            },
        }


class ContractChangeRejectWizard(models.TransientModel):
    """駁回精靈"""
    _name = 'contract.change.reject.wizard'
    _description = '契約變更駁回精靈'

    change_order_id = fields.Many2one(
        'contract.change.order',
        string='變更單',
        required=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        required=True)

    def action_confirm(self):
        """確認駁回"""
        self.ensure_one()
        self.change_order_id.action_do_reject(self.rejection_reason)
        return {'type': 'ir.actions.act_window_close'}

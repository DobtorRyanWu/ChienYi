# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ProjectTask(models.Model):
    """
    契約工項擴展

    擴展 project.task 支援：
    - 廠商分配 (assigned_company_id)
    - 預算追蹤 (planned_qty, unit_price, planned_amount)
    - 時間計畫 (planned_date_start, planned_date_end)
    - 實際執行追蹤 (actual_qty, actual_amount, completion_rate)
    """
    _inherit = 'project.task'

    # === 排序欄位 ===
    # 注意: active 欄位由 Odoo 標準 project.task 提供，無需定義
    # active=False 的工項會自動從列表中隱藏
    
    sequence = fields.Integer(
        string='排序',
        default=10,
        index=True,
        help='工項顯示順序，數字越小越前面')

    # === 工項編號 ===
    item_no = fields.Char(
        string='工項編號', index=True, copy=False, required=True,
        help='契約工項編號，自動產生但可手動修改')

    # === 階層結構 ===
    item_level = fields.Integer(
        string='項次層級',
        default=0,
        help='0=大項次, 1=次項次, 2=小項次...')

    ref_item_code = fields.Char(
        string='參考工項代碼',
        index=True,
        help='標單中的 refItemCode，用於對應價格庫')

    is_summary_item = fields.Boolean(
        string='彙總項目',
        compute='_compute_is_summary_item',
        store=True,
        help='標示此項次是否為彙總項(有子項次)')

    @api.depends('child_ids')
    def _compute_is_summary_item(self):
        for task in self:
            task.is_summary_item = bool(task.child_ids)

    # === 廠商分配 ===
    assigned_company_id = fields.Many2one(
        'res.company', string='承包廠商', index=True,
        domain="[('company_type', '=', 'contractor')]",
        tracking=True,
        help='此工項分配給哪家施工廠商執行')

    assignment_date = fields.Date(
        string='分配日期',
        help='工項分配給廠商的日期')

    assigned_by_id = fields.Many2one(
        'res.users', string='分配人',
        help='執行分配操作的使用者')

    # === 分配狀態 ===
    assignment_state = fields.Selection([
        ('unassigned', '未分配'),
        ('assigned', '已分配'),
        ('in_progress', '執行中'),
        ('completed', '已完成'),
        ('accepted', '已驗收'),
    ], string='分配狀態', default='unassigned',
       compute='_compute_assignment_state', store=True, tracking=True)

    @api.depends('assigned_company_id', 'stage_id', 'stage_id.is_acceptance_stage')
    def _compute_assignment_state(self):
        for task in self:
            if not task.assigned_company_id:
                task.assignment_state = 'unassigned'
            elif task.stage_id and task.stage_id.is_acceptance_stage:
                task.assignment_state = 'accepted'
            elif task.actual_date_end:
                task.assignment_state = 'completed'
            elif task.actual_date_start:
                task.assignment_state = 'in_progress'
            else:
                task.assignment_state = 'assigned'

    # === 預算欄位 (契約價量) ===
    # 這三個欄位僅對「契約工項」(隸屬 supervision.project 的 task) 必填。
    # 使用 view 層 required="1" + @api.constrains 檢查 (_check_contract_task_required)
    # 代替欄位層 required=True，避免 project_todo 等其他模組建立的 task
    # 因 NOT NULL 約束而無法建立 (見 _check_contract_task_required 的說明)。
    planned_qty = fields.Float(
        string='契約數量', digits=(16, 4),
        help='契約預估數量 (預算)')

    unit = fields.Char(
        string='單位',
        help='計量單位，如：M, M2, M3, 式')

    unit_price = fields.Float(
        string='契約單價', digits=(16, 2),
        help='契約預估單價')

    planned_amount = fields.Float(
        string='契約金額',
        compute='_compute_planned_amount', store=True,
        help='planned_qty x unit_price (預算上限)')

    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        for task in self:
            task.planned_amount = task.planned_qty * task.unit_price

    @api.constrains('project_id', 'unit')
    def _check_contract_task_required(self):
        """契約工項 (隸屬 supervision.project) 必須填寫單位。

        非契約 task (如 project_todo 建立的 Training / Meeting / Time Off、
        Odoo 原生 project 的一般任務) 則不受限制，保持 project.task 欄位
        層面的「可選」語意，避免 DB NOT NULL 擋住其他模組的 create。

        planned_qty / unit_price 為 Float，0 是合法值 (變更工項原契約數量
        可能為 0)，改由 view 層 required="1" 做 UX 提醒，不在此強制。
        """
        if not self:
            return
        SupProj = self.env['supervision.project'].sudo()
        project_ids = {t.project_id.id for t in self if t.project_id}
        if not project_ids:
            return
        contract_project_ids = set(
            SupProj.search([('project_id', 'in', list(project_ids))]).mapped('project_id').ids
        )
        if not contract_project_ids:
            return
        for task in self:
            if not task.project_id or task.project_id.id not in contract_project_ids:
                continue
            if not task.unit:
                raise ValidationError(
                    f'契約工項「{task.name or task.item_no or task.id}」必須填寫「單位」'
                )

    # === 實際執行欄位 ===
    actual_qty = fields.Float(
        string='實際完成數量', digits=(16, 4), readonly=True,
        help='已核定的估驗數量彙總，由施工日誌自動計算')

    actual_amount = fields.Float(
        string='實際請款金額',
        compute='_compute_actual_amount', store=True,
        help='actual_qty x unit_price')

    @api.depends('actual_qty', 'unit_price')
    def _compute_actual_amount(self):
        for task in self:
            task.actual_amount = task.actual_qty * task.unit_price

    # === 對比分析 ===
    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate', store=True,
        help='actual_amount / planned_amount x 100')

    qty_remaining = fields.Float(
        string='剩餘數量',
        compute='_compute_completion_rate', store=True,
        help='planned_qty - actual_qty')

    budget_status = fields.Selection([
        ('under', '低於預算'),
        ('on_budget', '符合預算'),
        ('over', '超出預算'),
    ], string='預算狀態',
       compute='_compute_completion_rate', store=True)

    @api.depends('planned_qty', 'planned_amount', 'actual_qty', 'actual_amount')
    def _compute_completion_rate(self):
        for task in self:
            task.qty_remaining = task.planned_qty - task.actual_qty

            if task.planned_amount:
                task.completion_rate = (task.actual_amount / task.planned_amount) * 100
                if task.completion_rate < 95:
                    task.budget_status = 'under'
                elif task.completion_rate <= 100:
                    task.budget_status = 'on_budget'
                else:
                    task.budget_status = 'over'
            else:
                task.completion_rate = 0.0
                task.budget_status = False

    # === 時間計畫欄位 ===
    planned_date_start = fields.Datetime(
        string='預定開始時間', tracking=True,
        help='工項預定開始時間')

    planned_date_end = fields.Datetime(
        string='預定完成時間', tracking=True,
        help='工項預定完成時間')

    planned_duration = fields.Float(
        string='預定工期(天)',
        compute='_compute_planned_duration', store=True)

    @api.depends('planned_date_start', 'planned_date_end')
    def _compute_planned_duration(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                delta = task.planned_date_end - task.planned_date_start
                task.planned_duration = delta.total_seconds() / 86400  # 轉換為天數
            else:
                task.planned_duration = 0.0

    # === 實際執行時間 ===
    actual_date_start = fields.Datetime(
        string='實際開始時間', tracking=True)

    actual_date_end = fields.Datetime(
        string='實際完成時間', tracking=True)

    actual_duration = fields.Float(
        string='實際工期(天)',
        compute='_compute_actual_duration', store=True)

    @api.depends('actual_date_start', 'actual_date_end')
    def _compute_actual_duration(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                delta = task.actual_date_end - task.actual_date_start
                task.actual_duration = delta.total_seconds() / 86400
            else:
                task.actual_duration = 0.0

    # === 時程對比分析 ===
    schedule_variance = fields.Float(
        string='時程差異(天)',
        compute='_compute_schedule_variance', store=True,
        help='負值=超前, 正值=落後')

    schedule_status = fields.Selection([
        ('ahead', '超前'),
        ('on_schedule', '正常'),
        ('delayed', '落後'),
    ], string='時程狀態',
       compute='_compute_schedule_variance', store=True)

    @api.depends('planned_date_end', 'actual_date_end', 'assignment_state')
    def _compute_schedule_variance(self):
        for task in self:
            if task.planned_date_end and task.actual_date_end:
                delta = (task.actual_date_end - task.planned_date_end).days
                task.schedule_variance = delta
                if delta < -1:
                    task.schedule_status = 'ahead'
                elif delta <= 1:
                    task.schedule_status = 'on_schedule'
                else:
                    task.schedule_status = 'delayed'
            elif task.planned_date_end and task.assignment_state == 'in_progress':
                # 執行中：與現在時間比較
                now = fields.Datetime.now()
                delta = (now - task.planned_date_end).days
                task.schedule_variance = delta if delta > 0 else 0
                task.schedule_status = 'delayed' if delta > 0 else 'on_schedule'
            else:
                task.schedule_variance = 0.0
                task.schedule_status = False

    # === 工程相關 ===
    supervision_project_id = fields.Many2one(
        'supervision.project', string='工程案件',
        compute='_compute_supervision_project', store=True,
        help='關聯的工程案件主檔')

    @api.depends('project_id')
    def _compute_supervision_project(self):
        SupervisionProject = self.env['supervision.project']
        for task in self:
            if task.project_id:
                supervision = SupervisionProject.search([
                    ('project_id', '=', task.project_id.id)
                ], limit=1)
                task.supervision_project_id = supervision.id if supervision else False
            else:
                task.supervision_project_id = False
    
    # === 工程案件狀態 ===
    project_state = fields.Selection(
        related='supervision_project_id.state',
        string='工程狀態',
        store=True,
        help='從工程案件繼承的狀態，用於控制欄位唯讀')
    
    is_project_approved = fields.Boolean(
        string='工程已核定',
        compute='_compute_is_project_approved',
        store=True,
        help='工程案件已核定，工項資料變為唯讀')
    
    @api.depends('supervision_project_id.state')
    def _compute_is_project_approved(self):
        for task in self:
            if task.supervision_project_id:
                task.is_project_approved = task.supervision_project_id.state in (
                    'construction', 'completion', 'acceptance', 'closed', 'suspended', 'terminated'
                )
            else:
                task.is_project_approved = False

    # === 備註 ===
    construction_notes = fields.Text(
        string='施工說明',
        help='工項施工注意事項或說明')

    specification = fields.Text(
        string='規格說明',
        help='工項規格或技術要求')

    # === 約束 ===
    @api.constrains('planned_date_start', 'planned_date_end')
    def _check_planned_dates(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                if task.planned_date_end < task.planned_date_start:
                    raise ValidationError('預定完成時間必須晚於預定開始時間')

    @api.constrains('actual_date_start', 'actual_date_end')
    def _check_actual_dates(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                if task.actual_date_end < task.actual_date_start:
                    raise ValidationError('實際完成時間必須晚於實際開始時間')

    @api.constrains('planned_qty', 'unit_price')
    def _check_positive_values(self):
        for task in self:
            if task.planned_qty < 0:
                raise ValidationError('契約數量不可為負數')
            if task.unit_price < 0:
                raise ValidationError('契約單價不可為負數')

    # === 動作方法 ===
    def action_assign_to_contractor(self):
        """開啟分配廠商精靈"""
        self.ensure_one()
        if not self.supervision_project_id:
            raise UserError('此工項未關聯工程案件，無法分配廠商')

        return {
            'type': 'ir.actions.act_window',
            'name': '分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': self.supervision_project_id.id,
            },
        }

    def action_start_work(self):
        """開始施工"""
        for task in self:
            if not task.assigned_company_id:
                raise UserError('請先分配廠商才能開始施工')
            if not task.actual_date_start:
                task.actual_date_start = fields.Datetime.now()

    def action_complete_work(self):
        """完成施工"""
        for task in self:
            if not task.actual_date_start:
                raise UserError('尚未開始施工，無法標記完成')
            if not task.actual_date_end:
                task.actual_date_end = fields.Datetime.now()

    def action_batch_assign(self):
        """批次分配工項"""
        if not self:
            raise UserError('請先選擇要分配的工項')

        # 檢查是否都屬於同一個專案
        projects = self.mapped('supervision_project_id')
        if len(projects) > 1:
            raise UserError('批次分配的工項必須屬於同一個工程案件')
        if not projects:
            raise UserError('選取的工項未關聯工程案件')

        return {
            'type': 'ir.actions.act_window',
            'name': '批次分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': projects[0].id,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        """覆寫建立方法以自動產生工項編號"""
        for vals in vals_list:
            # 如果沒有提供 item_no，自動產生
            if not vals.get('item_no'):
                vals['item_no'] = self._generate_item_no(
                    vals.get('parent_id'),
                    vals.get('project_id')
                )
            
            # 如果沒有提供 sequence，自動計算
            if not vals.get('sequence'):
                vals['sequence'] = self._calculate_sequence(
                    vals.get('parent_id'),
                    vals.get('project_id')
                )
        
        return super().create(vals_list)
    
    def _generate_item_no(self, parent_id, project_id):
        """自動產生工項編號（中文數字）"""
        if not project_id:
            return '1'
        
        # 取得同父項下的兄弟工項
        domain = [('project_id', '=', project_id)]
        if parent_id:
            domain.append(('parent_id', '=', parent_id))
        else:
            domain.append(('parent_id', '=', False))
        
        siblings = self.search(domain, order='sequence desc', limit=1)
        
        if not siblings:
            # 沒有兄弟工項，從頭開始
            next_number = 1
        else:
            # 嘗試從最後一個兄弟的 item_no 解析數字
            last_item_no = siblings[0].item_no or ''
            next_number = self._parse_and_increment(last_item_no)
        
        # 根據層級決定編號格式
        if parent_id:
            parent = self.browse(parent_id)
            level = parent.item_level + 1
        else:
            level = 0
        
        return self._number_to_chinese(next_number, level)
    
    def _parse_and_increment(self, item_no):
        """從工項編號解析數字並遞增"""
        if not item_no:
            return 1
        
        # 嘗試轉換中文數字
        num = self._chinese_to_number(item_no)
        if num > 0:
            return num + 1
        
        # 嘗試解析阿拉伯數字
        import re
        match = re.search(r'\d+', item_no)
        if match:
            return int(match.group()) + 1
        
        return 1
    
    def _number_to_chinese(self, num, level):
        """數字轉中文"""
        if level == 0:
            # 第一層：壹貳參...
            chinese_upper = ['', '壹', '貳', '參', '肆', '伍', '陸', '柒', '捌', '玖', '拾']
            if num <= 10:
                return chinese_upper[num]
            else:
                # 超過10的話，用組合方式
                if num < 20:
                    return '拾' + (chinese_upper[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_upper[tens] + '拾' + (chinese_upper[ones] if ones else '')
        elif level == 1:
            # 第二層：一二三...
            chinese_lower = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
            if num <= 10:
                return chinese_lower[num]
            else:
                if num < 20:
                    return '十' + (chinese_lower[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_lower[tens] + '十' + (chinese_lower[ones] if ones else '')
        else:
            # 第三層及以下：1, 2, 3...
            return str(num)
    
    def _chinese_to_number(self, chinese_str):
        """中文轉數字"""
        if not chinese_str:
            return 0
        
        # 大寫數字對應
        upper_map = {
            '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5,
            '陸': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10
        }
        # 小寫數字對應
        lower_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        # 嘗試直接對應
        if chinese_str in upper_map:
            return upper_map[chinese_str]
        if chinese_str in lower_map:
            return lower_map[chinese_str]
        
        # 嘗試解析組合（如：拾壹、十一）
        result = 0
        if '拾' in chinese_str or '十' in chinese_str:
            parts = chinese_str.replace('拾', '|').replace('十', '|').split('|')
            if len(parts) == 2:
                tens_str, ones_str = parts
                tens = upper_map.get(tens_str, lower_map.get(tens_str, 1 if not tens_str else 0))
                ones = upper_map.get(ones_str, lower_map.get(ones_str, 0))
                result = tens * 10 + ones
        
        return result
    
    def _calculate_sequence(self, parent_id, project_id):
        """計算 sequence 值"""
        if not project_id:
            return 10
        
        # 取得同父項下的最大 sequence
        domain = [('project_id', '=', project_id)]
        if parent_id:
            domain.append(('parent_id', '=', parent_id))
        else:
            domain.append(('parent_id', '=', False))
        
        siblings = self.search(domain, order='sequence desc', limit=1)
        
        if not siblings:
            return 10
        
        return siblings[0].sequence + 10
    
    def write(self, vals):
        """覆寫寫入方法以記錄分配資訊"""
        if 'assigned_company_id' in vals:
            if vals['assigned_company_id']:
                vals['assignment_date'] = fields.Date.today()
                vals['assigned_by_id'] = self.env.uid
            else:
                vals['assignment_date'] = False
                vals['assigned_by_id'] = False
        return super().write(vals)


class ProjectTaskType(models.Model):
    """專案階段擴展 - 增加工程相關屬性"""
    _inherit = 'project.task.type'

    is_construction_stage = fields.Boolean(
        string='施工階段',
        help='標記此階段為施工執行階段')

    is_acceptance_stage = fields.Boolean(
        string='驗收階段',
        help='標記此階段為驗收完成階段')

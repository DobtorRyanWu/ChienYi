# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class CheckTestRequirementWizard(models.TransientModel):
    """檢查檢驗需求精靈"""
    _name = 'check.test.requirement.wizard'
    _description = '檢查檢驗需求精靈'
    
    # ===================================================================
    # 欄位定義
    # ===================================================================
    
    project_id = fields.Many2one(
        'supervision.project',
        string='工程案件',
        required=True,
        default=lambda self: self._default_project_id(),
        help='要檢查的工程案件'
    )
    
    check_date = fields.Date(
        string='檢查日期',
        required=True,
        default=fields.Date.today,
        help='檢查此日期之前（含當天）的所有施工記錄'
    )
    
    # 統計資訊（唯讀）
    standard_count = fields.Integer(
        string='檢驗項目數',
        compute='_compute_statistics',
        help='此工程設定的檢驗項目總數'
    )
    
    task_count = fields.Integer(
        string='關聯工項數',
        compute='_compute_statistics',
        help='需要檢驗的契約工項數量'
    )
    
    # ===================================================================
    # 預設值方法
    # ===================================================================
    
    def _default_project_id(self):
        """從 context 取得預設專案"""
        # 如果是從檢驗記錄頁面開啟，可能會有 default_project_id
        project_id = self.env.context.get('default_project_id')
        if project_id:
            return project_id
        
        # 否則取得目前施工中的專案（如果只有一個）
        projects = self.env['supervision.project'].search([
            ('state', '=', 'construction')
        ])
        if len(projects) == 1:
            return projects.id
        
        return False
    
    @api.depends('project_id')
    def _compute_statistics(self):
        """計算統計資訊"""
        for wizard in self:
            if wizard.project_id:
                # 檢驗項目數
                standards = self.env['supervision.test.standard'].search([
                    ('project_id', '=', wizard.project_id.id),
                    ('active', '=', True),
                ])
                wizard.standard_count = len(standards)
                
                # 關聯工項數（去重）
                tasks = standards.mapped('task_ids')
                wizard.task_count = len(tasks)
            else:
                wizard.standard_count = 0
                wizard.task_count = 0
    
    # ===================================================================
    # 核心方法
    # ===================================================================
    
    def action_check_requirements(self):
        """執行檢查並建立需要的檢驗記錄"""
        self.ensure_one()
        
        if not self.project_id:
            raise UserError('請選擇工程案件')
        
        # 1. 查詢該工程的所有檢試驗項目設定
        standards = self.env['supervision.test.standard'].search([
            ('project_id', '=', self.project_id.id),
            ('active', '=', True),
        ])
        
        if not standards:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '檢查完成',
                    'message': '此工程尚未設定任何檢驗項目',
                    'type': 'warning',
                }
            }
        
        TestRecord = self.env['supervision.test.record']
        created_records = self.env['supervision.test.record']
        
        # 記錄檢查的統計
        check_summary = {
            'standards_checked': 0,
            'tasks_checked': 0,
            'records_created': 0,
        }
        
        # 檢查 daily_log 模組是否已安裝
        try:
            DailyLogLine = self.env['daily.log.line']
        except KeyError:
            # daily_log 模組未安裝，返回提示
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '功能不可用',
                    'message': '此功能需要安裝「施工日誌」模組(construction_daily_log)才能使用',
                    'type': 'warning',
                }
            }
        
        for standard in standards:
            check_summary['standards_checked'] += 1
            
            # 2. 對每個關聯的工項進行檢查
            for task in standard.task_ids:
                check_summary['tasks_checked'] += 1
                
                # 3. 查詢該工項的最新累計完成數量（從 daily_log）
                try:
                    latest_log = DailyLogLine.search([
                        ('work_item_id', '=', task.id),
                        ('date', '<=', self.check_date),
                    ], order='date desc', limit=1)
                except:
                    # 如果查詢失敗，跳過此工項
                    continue
                
                if not latest_log:
                    # 該工項尚無施工記錄，跳過
                    continue
                
                cumulative_qty = latest_log.cumulative_qty
                
                if not cumulative_qty or cumulative_qty <= 0:
                    # 累計數量為0，跳過
                    continue
                
                # 4. 根據檢驗條件計算應有的檢驗次數（統一入口）
                required_count = standard.calculate_required_tests(
                    cumulative_qty
                )
                
                if required_count <= 0:
                    # 不需要檢驗，跳過
                    continue
                
                # 5. 查詢已有的檢驗記錄數
                existing_count = TestRecord.search_count([
                    ('project_id', '=', self.project_id.id),
                    ('task_id', '=', task.id),
                    ('standard_id', '=', standard.id),
                ])
                
                # 6. 建立缺少的檢驗記錄
                shortage = required_count - existing_count
                if shortage > 0:
                    for i in range(shortage):
                        record = TestRecord.create({
                            'name': '/',
                            'project_id': self.project_id.id,
                            'task_id': task.id,
                            'standard_id': standard.id,
                            'auto_created': True,
                            'trigger_log_line_id': latest_log.id,
                            'trigger_cumulative_qty': cumulative_qty,
                            'in_site_date': latest_log.date,
                        })
                        created_records |= record
                        check_summary['records_created'] += 1
        
        # 7. 顯示結果
        if created_records:
            message = f"""檢查完成！
            
檢查了 {check_summary['standards_checked']} 個檢驗項目
涵蓋 {check_summary['tasks_checked']} 個契約工項
新建立 {check_summary['records_created']} 筆檢驗記錄
            
這些記錄已標記為「系統自動建立」，請填寫相關資料。"""
            
            return {
                'type': 'ir.actions.act_window',
                'name': '新建立的檢驗需求',
                'res_model': 'supervision.test.record',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_records.ids)],
                'context': {
                    'search_default_auto_pending': 1,
                },
                'target': 'current',
            }
        else:
            message = f"""檢查完成！
            
檢查了 {check_summary['standards_checked']} 個檢驗項目
涵蓋 {check_summary['tasks_checked']} 個契約工項
目前無需新增檢驗記錄
            
所有應檢驗的項目都已建立記錄。"""
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '檢查完成',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
    


class CheckTestRequirementCron(models.AbstractModel):
    """定期任務：檢查檢驗需求"""
    _name = 'check.test.requirement.cron'
    _description = '定期檢查檢驗需求'
    
    def _cron_check_test_requirements(self):
        """
        定期任務方法（每天執行）
        
        自動檢查所有施工中的工程，建立需要的檢驗記錄
        """
        # 查詢所有施工中的工程
        projects = self.env['supervision.project'].search([
            ('state', '=', 'construction')
        ])
        
        if not projects:
            return
        
        wizard_obj = self.env['check.test.requirement.wizard']
        total_created = 0
        
        for project in projects:
            # 為每個工程建立精靈並執行檢查
            wizard = wizard_obj.create({
                'project_id': project.id,
                'check_date': fields.Date.today(),
            })
            
            # 執行檢查（但不顯示結果）
            result = wizard.action_check_requirements()
            
            # 記錄日誌
            if result.get('res_model') == 'supervision.test.record':
                # 有建立新記錄
                domain = result.get('domain', [])
                if domain:
                    count = self.env['supervision.test.record'].search_count(domain)
                    total_created += count
                    project.message_post(
                        body=f'定期檢查：自動建立 {count} 筆檢驗需求記錄',
                        subject='檢驗需求自動檢查',
                    )
        
        # 記錄到系統日誌
        if total_created > 0:
            self.env['ir.logging'].sudo().create({
                'name': 'check.test.requirement.cron',
                'type': 'server',
                'level': 'INFO',
                'message': f'定期檢查檢驗需求：共建立 {total_created} 筆檢驗記錄',
                'path': 'construction_test',
                'func': '_cron_check_test_requirements',
            })

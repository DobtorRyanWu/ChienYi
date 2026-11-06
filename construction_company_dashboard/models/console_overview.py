# -*- coding: utf-8 -*-
"""控台取資料方法（合約 §8.1）：project.project.dash_console_overview()。

全系統唯一的 sudo 計算例外（合約 §1-5）：
* 開頭先查呼叫者（env.user，不因 env.su 跳過）是「控台讀取」群組，否則 AccessError；
* 通過後才 sudo、active_test=False 讀全部工程（含封存、終止），指標讀 §5.2 的同一組 dash_ 欄位（合約 §1-4，不另算）；
* 只回合計數字與狀態、工程名稱與代碼、營造廠與監造公司的名稱與統一編號；**不回照片、明細、任何人名**——
  回傳的鍵是下面兩個白名單常數，多一個鍵就是多洩一項（測試另寫一份獨立清單鎖住）；
* `project_count` 用原生 SQL 另外數（與 ORM 的結果獨立），給控台與拉資料程式比對：
  ORM 這一條路若少拿（被規則、篩選、程式錯誤吃掉），上游看得到兩個數字不同而拒寫，不會把少的當成全部。
* 控台讀取帳號自己直接讀業務模型一律被拒（rule_scope 的 console 分支，線 A），所以這是它唯一的資料來源。

指標群組讀取失敗時（dash_error_keys），數字欄位是 0 但 error_keys 有值：控台要顯示「讀取失敗」，不可把 0 當真（合約 §1-8）。
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError

# 回傳頂層的鍵
OVERVIEW_KEYS = ('computed_at', 'project_count', 'projects')

# 每個工程一列的鍵（合約 §8.1、§5.2 的數值與狀態欄位）。照片只給張數；最近一期估驗只給期數與日期；
# dash_progress_svg 不給（是圖不是數值，控台若存成 Html 等於把租戶產生的標記搬進控台）。
PROJECT_ROW_KEYS = (
    'remote_id', 'name', 'code', 'state', 'state_label', 'active',
    'contractor_companies', 'supervision_company',
    'workday_elapsed', 'workday_total', 'workday_note', 'workday_state', 'workday_state_label',
    'log_today', 'log_today_label',
    'today_photo_count',
    'open_defect_count', 'overdue_defect_count',
    'pending_test_count',
    'latest_estimate_no', 'latest_estimate_date', 'estimate_cum_amount', 'estimate_month_amount',
    'progress_planned', 'progress_actual', 'progress_variance', 'has_schedule',
    'denied_keys', 'error_keys',
)
# 營造廠每家、監造公司的鍵：名稱、統一編號（res.company.vat）
# 監造公司＝工程的 company_id（管理公司，必填）：jt 這種多家監造公司共用的庫，控台靠它分出工程屬於哪家
CONTRACTOR_KEYS = ('name', 'vat')

# 「工程總數」的原生 SQL：整張表（含封存），與 ORM 的 sudo＋active_test=False 應相同
PROJECT_COUNT_SQL = 'SELECT count(*) FROM project_project'

DENY_MESSAGE = '控台取資料方法只限「控台讀取」帳號呼叫。'


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.model
    def dash_console_overview(self):
        """控台取資料（合約 §8.1）。回傳 {'computed_at', 'project_count', 'projects': [每個工程一列]}。"""
        # 判定用 env.user：別的帳號 sudo() 進來仍然被拒（sudo 不改 env.user）
        if not self.env.user._dash_is_console_reader():
            raise AccessError(DENY_MESSAGE)
        computed_at = fields.Datetime.now()
        projects = self._dash_console_projects()
        # 原生 SQL 另外數，不經 ORM（不受規則、active、程式篩選影響）
        self.env.cr.execute(PROJECT_COUNT_SQL)
        (project_count,), = self.env.cr.fetchall()
        return {
            'computed_at': fields.Datetime.to_string(computed_at),
            'project_count': project_count,
            'projects': [project._dash_console_row() for project in projects],
        }

    @api.model
    def _dash_console_projects(self):
        """全部工程（sudo、含封存）；呼叫端已確認是控台讀取帳號。"""
        return self.sudo().with_context(active_test=False).search([], order='id')

    def _dash_console_row(self):
        """一個工程的總覽列（只有白名單鍵；空值一律 False，XML-RPC 不收 None）。"""
        self.ensure_one()
        latest = self.dash_latest_estimate_id
        return {
            'remote_id': self.id,
            'name': self.name or False,
            'code': self.code or False,
            'state': self.state or False,
            'state_label': self._dash_console_label('state', self.state),
            'active': bool(self.active),
            'contractor_companies': [self._dash_console_company(company) for company in self.contractor_company_ids],
            'supervision_company': self._dash_console_company(self.company_id),
            'workday_elapsed': self.dash_workday_elapsed,
            'workday_total': self.dash_workday_total,
            'workday_note': self.dash_workday_note or False,
            'workday_state': self.dash_workday_state or False,
            'workday_state_label': self._dash_console_label('dash_workday_state', self.dash_workday_state),
            'log_today': self.dash_log_today or False,
            'log_today_label': self._dash_console_label('dash_log_today', self.dash_log_today),
            'today_photo_count': self.dash_today_photo_count,
            'open_defect_count': self.dash_open_defect_count,
            'overdue_defect_count': self.dash_overdue_defect_count,
            'pending_test_count': self.dash_pending_test_count,
            'latest_estimate_no': latest.estimate_no if latest else False,
            'latest_estimate_date': fields.Date.to_string(latest.estimate_date) if latest.estimate_date else False,
            'estimate_cum_amount': self.dash_estimate_cum_amount,
            'estimate_month_amount': self.dash_estimate_month_amount,
            'progress_planned': self.dash_progress_planned,
            'progress_actual': self.dash_progress_actual,
            'progress_variance': self.dash_progress_variance,
            'has_schedule': bool(self.dash_has_schedule),
            'denied_keys': self.dash_denied_keys or False,
            'error_keys': self.dash_error_keys or False,
        }

    @api.model
    def _dash_console_company(self, company):
        """一家公司的名稱與統一編號（只有 CONTRACTOR_KEYS 兩個鍵）。"""
        return {'name': company.name, 'vat': company.vat or False}

    def _dash_console_label(self, field_name, value):
        """Selection 的顯示文字（程式裡的固定字串，不是使用者輸入）；沒值回 False。"""
        if not value:
            return False
        return dict(self._fields[field_name]._description_selection(self.env)).get(value, value)

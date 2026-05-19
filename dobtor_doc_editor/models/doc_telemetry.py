"""監控與遙測模型（P2-4）。

提供兩個 model 收集前端 runtime 觀察資料：
    - doc.editor.error.log     ：JS 錯誤 / unhandled promise rejection
    - doc.editor.perf.metric   ：Web Vitals (LCP/FID/CLS) + 業務 timing
                                 （load_ms / first_render_ms / save_latency_ms）

設計取捨：
    - 不外接 Sentry / Datadog（避免商業依賴與資料外流）
    - 用 Odoo model 儲存 → 後台可直接查看、可 join 既有的 res.users
    - 自動清理：cron 每天清 30 天前的記錄（避免無限長大）
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DocEditorErrorLog(models.Model):
    """前端錯誤紀錄。"""

    _name = 'doc.editor.error.log'
    _description = '文件編輯器錯誤紀錄'
    _order = 'create_date desc'

    doc_id = fields.Many2one('doc.document', string='文件', ondelete='set null', index=True)
    user_id = fields.Many2one('res.users', string='使用者', ondelete='set null', index=True)
    company_id = fields.Many2one('res.company', string='公司', ondelete='set null')
    error_type = fields.Selection([
        ('js_error', 'JS Error'),
        ('promise_rejection', 'Unhandled Promise'),
        ('canvas_error', 'Canvas Editor Error'),
        ('save_failure', 'Save Failure'),
        ('import_failure', 'Import Failure'),
        ('export_failure', 'Export Failure'),
        ('other', '其他'),
    ], string='錯誤類別', required=True, default='other', index=True)
    message = fields.Char(string='訊息', size=512)
    stack_trace = fields.Text(string='Stack trace')
    user_agent = fields.Char(string='User Agent', size=256)
    url = fields.Char(string='URL', size=512)
    extra = fields.Json(string='額外資料', help='前端附帶的 context (例: docId, action)')

    @api.model
    def gc_old_logs(self, days=30):
        """Cron 用：清理 N 天前的錯誤紀錄。"""
        from datetime import timedelta
        threshold = fields.Datetime.now() - timedelta(days=days)
        old = self.search([('create_date', '<', threshold)])
        n = len(old)
        if n:
            old.unlink()
            _logger.info("doc.editor.error.log: gc removed %d old entries", n)
        return n


class DocEditorPerfMetric(models.Model):
    """前端效能指標紀錄。

    每筆代表一個 metric event。常見 metric_type 與其單位：
        load_doc_ms          載入文件總耗時
        first_render_ms      首次渲染完成
        save_latency_ms      save round-trip
        web_vitals_lcp_ms    Largest Contentful Paint
        web_vitals_fid_ms    First Input Delay
        web_vitals_cls       Cumulative Layout Shift（無單位 0-1）
        canvas_set_value_ms  executeSetValue 耗時
    """

    _name = 'doc.editor.perf.metric'
    _description = '文件編輯器效能指標'
    _order = 'create_date desc'

    doc_id = fields.Many2one('doc.document', string='文件', ondelete='set null', index=True)
    user_id = fields.Many2one('res.users', string='使用者', ondelete='set null', index=True)
    metric_type = fields.Char(string='指標類型', required=True, index=True)
    value = fields.Float(string='值', required=True, help='毫秒 / 秒 / 比率（依 metric_type 而定）')
    page_count = fields.Integer(string='文件頁數', help='如為文件層級的 metric')
    extra = fields.Json(string='額外資料')

    @api.model
    def gc_old_metrics(self, days=14):
        """Cron 用：清理 N 天前的效能紀錄（保留期較短，量大）。"""
        from datetime import timedelta
        threshold = fields.Datetime.now() - timedelta(days=days)
        old = self.search([('create_date', '<', threshold)])
        n = len(old)
        if n:
            old.unlink()
            _logger.info("doc.editor.perf.metric: gc removed %d old entries", n)
        return n

    @api.model
    def aggregate_recent(self, metric_type, hours=24):
        """簡易彙總：min / max / mean / count。

        給 admin dashboard 或 health-check 用。
        """
        from datetime import timedelta
        threshold = fields.Datetime.now() - timedelta(hours=hours)
        recs = self.search([
            ('metric_type', '=', metric_type),
            ('create_date', '>=', threshold),
        ])
        if not recs:
            return {'count': 0}
        values = recs.mapped('value')
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'mean': sum(values) / len(values),
        }

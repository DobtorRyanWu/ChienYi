# -*- coding: utf-8 -*-
"""後台單一工程頁（進度表圖表）的資料與看板設定（合約 §6）。

* get_project_dashboard_data：新模組覆寫；區塊清單用 construction_progress 的 _dashboard_blocks()，本模組在後面加
  today_photos、today_log、estimate 三區塊（合約 §0b-18，不另外複製清單）。
  **每個區塊的錯誤分開**（合約 §1-8）：讀取權不足 → {'status': 'no_access', 'message': '無權限查看'}；
  其他例外 → {'status': 'error', 'message': '讀取失敗'}（記 log）；正常 → 區塊內容多一個 'status': 'ok'；
  模組沒裝 → None（照舊，畫面顯示「模組未安裝」）。原本 `except Exception → None` 不可沿用：
  它把「沒權限」「出錯」「模組沒裝」三件事都變成同一個 None。
* 三個新區塊的數字讀 B 線的 dash_ 欄位（指標只定義一次，合約 §1-4）；欄位被標「無權限」「讀取失敗」就原樣往上報。
* dash_rest_days_readonly：工程表單的例假日欄位，營造方唯讀用（寫入本來就被 §3.3 的拒寫規則擋下，這裡讓畫面也誠實）。
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .project_dashboard import (
    KEY_SEPARATOR, LOG_ERROR, LOG_NO_ACCESS, LOG_NO_CALENDAR, TODAY_PHOTO_LIMIT,
)
from .project_workday import missing_calendar_message

_logger = logging.getLogger(__name__)

# 看板每頁張數（監造方 165 個工程全部算要 7.74 秒，見 reports/B.md §6；一頁只讀當頁卡片）。
# views/dashboard_kanban.xml 的 limit 屬性必須與它相同（tests 逐一比對）。
KANBAN_PAGE_SIZE = 24
LOG_SUMMARY_LIMIT = 120          # 今日日誌明細的工作摘要最多顯示幾個字
BLOCK_NO_ACCESS = 'no_access'
BLOCK_ERROR = 'error'
BLOCK_OK = 'ok'
BLOCK_MESSAGES = {BLOCK_NO_ACCESS: '無權限查看', BLOCK_ERROR: '讀取失敗'}
# 本模組加的三個區塊（方法名在本模型上）；既有七個由 construction_progress 的 _dashboard_blocks() 提供
# （合約 §0b-18：不另外複製清單，兩邊才不會不同步）
NEW_BLOCKS = (
    ('today_photos', '_dashboard_today_photos'),
    ('today_log', '_dashboard_today_log'),
    ('estimate', '_dashboard_estimate'),
)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    dash_rest_days_readonly = fields.Boolean(
        string='例假日唯讀', compute='_compute_dash_rest_days_readonly',
        help='營造方使用者看工程表單的例假日是唯讀（監造方可改）；只給畫面用，寫入權由拒寫規則擋')

    @api.depends_context('uid')
    def _compute_dash_rest_days_readonly(self):
        readonly = self.env.user._dash_is_contractor_side()
        for project in self:
            project.dash_rest_days_readonly = readonly

    # ── 區塊 ─────────────────────────────────────────────────────────────
    def _dashboard_blocks(self):
        """既有區塊（construction_progress）之後接本模組的三個區塊（合約 §6、§0b-18）。"""
        return super()._dashboard_blocks() + [(key, getattr(self, name)) for key, name in NEW_BLOCKS]

    def get_project_dashboard_data(self):
        """單一工程頁的資料；每個區塊獨立錯誤隔離，且分得出「沒權限」與「出錯」（見檔頭）。

        區塊清單用 _dashboard_blocks()（同一份）；不呼叫 super()：它對每個區塊 except Exception → None，
        分不出沒權限與出錯。
        """
        self.ensure_one()
        # 工程本身讀不到（別家的工程）：整頁丟 AccessError，前端顯示「無權限查看」。
        # 不能讓各區塊各自去查——記錄規則會把別家的資料濾成空，新區塊就會顯示「0 張照片」冒充。
        self.check_access('read')
        return {key: self._dash_run_block(key, method) for key, method in self._dashboard_blocks()}

    def _dash_run_block(self, key, method):
        try:
            # savepoint：區塊裡的 SQL 錯誤不能弄壞整個交易，其他區塊還要照常讀
            with self.env.cr.savepoint():
                value = method()
        except AccessError:
            return {'status': BLOCK_NO_ACCESS, 'message': BLOCK_MESSAGES[BLOCK_NO_ACCESS]}
        except Exception:
            _logger.exception('單一工程頁區塊 %s 讀取失敗（工程 %s）', key, self.id)
            return {'status': BLOCK_ERROR, 'message': BLOCK_MESSAGES[BLOCK_ERROR]}
        if value is None:           # 模組沒裝（區塊方法自己回 None）或沒有可顯示的內容：維持 None
            return None
        return dict(value, status=BLOCK_OK)

    def _dash_require_group(self, group):
        """B 線算指標時標了這個群組「無權限」「讀取失敗」→ 區塊原樣往上報，不拿預設值冒充。"""
        self.ensure_one()
        if group in (self.dash_denied_keys or '').split(KEY_SEPARATOR):
            raise AccessError(BLOCK_MESSAGES[BLOCK_NO_ACCESS])
        if group in (self.dash_error_keys or '').split(KEY_SEPARATOR):
            raise UserError(BLOCK_MESSAGES[BLOCK_ERROR])

    def _dashboard_today_photos(self):
        """今日照片（台灣日期，卡片同一份）：最新的 TODAY_PHOTO_LIMIT 張＋全部張數。"""
        self._dash_require_group('photo')
        return {
            'count': self.dash_today_photo_count,
            'limit': TODAY_PHOTO_LIMIT,
            'photos': [{'id': photo.id, 'name': photo.display_name} for photo in self.dash_today_photo_ids],
        }

    def _dashboard_today_log(self):
        """今日日誌：沒填顯示「今日未填」，缺日曆說明缺哪一年（卡片同一份狀態）。"""
        self.ensure_one()
        state = self.dash_log_today
        if state == LOG_NO_ACCESS:
            raise AccessError(BLOCK_MESSAGES[BLOCK_NO_ACCESS])
        if state == LOG_ERROR:
            raise UserError(BLOCK_MESSAGES[BLOCK_ERROR])
        Sheet = self.env['daily.log.sheet'].with_context(active_test=False)
        ((model, domain),) = self._dash_domain('log_today')
        state_labels = dict(Sheet._fields['state']._description_selection(self.env))
        sheets = Sheet.search(domain, order='id')
        today = local_today()
        return {
            'log_state': state,
            'log_state_label': dict(self._fields['dash_log_today'].selection)[state],
            'message': missing_calendar_message([today.year]) if state == LOG_NO_CALENDAR else False,
            'sheets': [{
                'id': sheet.id,
                'name': sheet.display_name,
                'state_label': state_labels.get(sheet.state, sheet.state),
                'summary': (sheet.work_summary or '')[:LOG_SUMMARY_LIMIT],
            } for sheet in sheets],
        }

    def _dashboard_estimate(self):
        """估驗：最近一期（草稿以外期數最大）、累計與本月金額（草稿都不算，合約 §0b-14、§0b-17）。"""
        self._dash_require_group('estimate')
        latest = self.dash_latest_estimate_id
        state_labels = dict(self.env['payment.estimate']._fields['state']._description_selection(self.env))
        return {
            'currency': self.currency_id.symbol or self.currency_id.name,
            'cumulative_amount': self.dash_estimate_cum_amount,
            'month_amount': self.dash_estimate_month_amount,
            'latest': {
                'id': latest.id,
                'name': latest.display_name,
                'estimate_no': latest.estimate_no,
                'estimate_date': fields.Date.to_string(latest.estimate_date) if latest.estimate_date else False,
                'state_label': state_labels.get(latest.state, latest.state),
                'amount': latest.subtotal,
            } if latest else False,
        }

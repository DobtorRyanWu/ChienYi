# -*- coding: utf-8 -*-
"""前台公司儀表板 /construction/dashboard（合約 §7）。

* 卡片清單＝前台「可見工程」條件 _get_portal_projects_domain（已含營造方範圍），再依狀態篩選、分頁；
  卡片讀 project.project 的 dash_ 欄位（線 B，§5.2），公司合計用 get_dash_company_kpis()（與後台同一個方法）。
  畫面層只做格式化與挑文字，不重算任何指標（§1-4），也不提權補算（§1-5）。
* 缺資料、沒權限、出錯一律顯示原因（「無權限查看」「讀取失敗」「缺 YYYY 年政府辦公日曆」「未建進度表」），
  不用 0 或空白冒充（§1-8）。
* 這支 controller 是獨立類別（不繼承 ConstructionPortal），避免同名方法污染整個前台。
"""
import logging

from odoo import http
from odoo.http import request

from ..models.project_dashboard import (
    KEY_SEPARATOR, KPI_AMOUNT_KEYS, LOG_ERROR, LOG_FILLED, LOG_MISSING, LOG_NO_ACCESS,
    LOG_NO_CALENDAR, LOG_NOT_REQUIRED, PROJECT_STATE_CONSTRUCTION, STATUS_ERROR, STATUS_MESSAGES, STATUS_NO_ACCESS,
    STATUS_NOT_APPLICABLE, STATUS_OK, WORKDAY_ERROR, WORKDAY_NO_CALENDAR, WORKDAY_NO_DATES,
)

_logger = logging.getLogger(__name__)

# 一頁幾張卡片：每張卡片都要算一次指標（監造方 165 張全讀約 7.7 秒，線 B 回報 §6），手機上也不適合一次拉太長
CARDS_PER_PAGE = 12
# 縮圖尺寸（走 /construction/img/<att_id>/<w>x<h>?crop=true，與前台首頁照片縮圖同一寫法）
THUMB_SIZE = 96
# 狀態篩選
FILTER_CONSTRUCTION = 'construction'
FILTER_ALL = 'all'
DEFAULT_FILTER = FILTER_CONSTRUCTION

TEXT_NO_ACCESS = STATUS_MESSAGES[STATUS_NO_ACCESS]      # 無權限查看
TEXT_ERROR = STATUS_MESSAGES[STATUS_ERROR]              # 讀取失敗
TEXT_NO_SCHEDULE = '未建進度表'
TEXT_NO_ESTIMATE = '尚無估驗'
TEXT_NO_PHOTO = '今天尚無照片'
# 今日日誌：狀態 → (文字, 色調)；色調對應 CSS 的 .cy-dash-tone-*
LOG_TEXTS = {
    LOG_FILLED: ('已填', 'ok'),
    LOG_MISSING: ('今日未填', 'bad'),
    LOG_NOT_REQUIRED: ('今日免填', 'muted'),
    LOG_NO_CALENDAR: ('缺政府辦公日曆', 'warn'),
    LOG_NO_ACCESS: (TEXT_NO_ACCESS, 'warn'),
    LOG_ERROR: (TEXT_ERROR, 'warn'),
}
TONE_OK, TONE_BAD, TONE_WARN, TONE_MUTED, TONE_NORMAL = 'ok', 'bad', 'warn', 'muted', 'normal'


def _split_keys(value):
    return set(filter(None, (value or '').split(KEY_SEPARATOR)))


def _money(amount, symbol):
    return f'{symbol}{amount:,.0f}'


class ConstructionDashboard(http.Controller):

    # ── 路由 ────────────────────────────────────────────────────────────
    @http.route('/construction/dashboard', type='http', auth='user', website=True)
    def construction_dashboard(self, state=None, page=1, **kw):
        env = request.env
        Project = env['project.project']
        state = state if state in (FILTER_CONSTRUCTION, FILTER_ALL) else DEFAULT_FILTER
        domain = list(Project._get_portal_projects_domain(env.user.partner_id))
        if state == FILTER_CONSTRUCTION:
            domain.append(('state', '=', PROJECT_STATE_CONSTRUCTION))
        total = Project.search_count(domain)
        pages = max((total + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE, 1)
        try:
            page = min(max(int(page), 1), pages)
        except (TypeError, ValueError):
            page = 1
        projects = Project.search(domain, order='name, id', limit=CARDS_PER_PAGE,
                                  offset=(page - 1) * CARDS_PER_PAGE)
        kpis = Project.get_dash_company_kpis()
        company_symbol = env.company.currency_id.symbol or ''
        state_labels = dict(Project._fields['state'].selection)
        values = {
            'page_name': 'construction_dashboard',
            'blocked_message': kpis['blocked_message'],
            'kpi_items': self._kpi_items(kpis, company_symbol),
            'computed_at': kpis['today'],
            'cards': [self._card(project, state_labels) for project in projects],
            'state_filter': state,
            'total': total,
            'page': page,
            'pages': pages,
        }
        return request.render('construction_company_dashboard.portal_company_dashboard', values)

    # ── 公司合計 ────────────────────────────────────────────────────────
    @staticmethod
    def _kpi_items(kpis, symbol):
        """get_dash_company_kpis() 的結果 → 畫面用清單；不適用的指標不顯示，其餘一定有文字。"""
        items = []
        for key, entry in kpis['kpis'].items():
            status = entry['status']
            if status == STATUS_NOT_APPLICABLE:
                continue
            item = {'key': key, 'label': entry['label'], 'ok': status == STATUS_OK, 'value': None,
                    'sub': None, 'message': None}
            if status == STATUS_OK:
                if key in KPI_AMOUNT_KEYS:
                    item.update(value=_money(entry['amount'], symbol), sub=f"{entry['count']} 期")
                else:
                    item['value'] = f"{entry['count']:,}"
            else:
                # 無權限／缺日曆／讀取失敗：顯示 get_dash_company_kpis 給的原因，不是 0
                item['message'] = entry['message'] or STATUS_MESSAGES.get(status, TEXT_ERROR)
            items.append(item)
        return items

    # ── 單張卡片 ────────────────────────────────────────────────────────
    def _card(self, project, state_labels):
        denied = _split_keys(project.dash_denied_keys)
        errors = _split_keys(project.dash_error_keys)
        symbol = project.currency_id.symbol or ''
        return {
            'id': project.id,
            'name': project.name,
            'code': project.code,
            'state': project.state,
            'state_label': state_labels.get(project.state, project.state),
            'workday': self._workday(project),
            'log': self._log(project, denied, errors),
            'defect': self._counts(project, 'defect', denied, errors),
            'test': self._counts(project, 'test', denied, errors),
            'estimate': self._estimate(project, denied, errors, symbol),
            'progress': self._progress(project, denied, errors),
            'photos': self._photos(project, denied, errors),
        }

    @staticmethod
    def _workday(project):
        state = project.dash_workday_state
        if state == WORKDAY_ERROR:
            return {'text': TEXT_ERROR, 'tone': TONE_WARN, 'note': None}
        if state in (WORKDAY_NO_CALENDAR, WORKDAY_NO_DATES):
            return {'text': project.dash_workday_note or TEXT_ERROR, 'tone': TONE_WARN, 'note': None}
        return {'text': f'第 {project.dash_workday_elapsed} / {project.dash_workday_total} 工作天',
                'tone': TONE_NORMAL, 'note': project.dash_workday_note}

    @staticmethod
    def _log(project, denied, errors):
        # 欄位本身已把「無權限／讀取失敗」寫成 Selection 值；群組旗標再保險一次
        if 'log' in denied:
            text, tone = LOG_TEXTS[LOG_NO_ACCESS]
        elif 'log' in errors:
            text, tone = LOG_TEXTS[LOG_ERROR]
        else:
            text, tone = LOG_TEXTS.get(project.dash_log_today, (TEXT_ERROR, TONE_WARN))
        return {'text': text, 'tone': tone}

    @staticmethod
    def _counts(project, group, denied, errors):
        if group in denied:
            return {'text': TEXT_NO_ACCESS, 'ok': False}
        if group in errors:
            return {'text': TEXT_ERROR, 'ok': False}
        if group == 'defect':
            return {'ok': True, 'count': project.dash_open_defect_count,
                    'overdue': project.dash_overdue_defect_count}
        return {'ok': True, 'count': project.dash_pending_test_count}

    @staticmethod
    def _estimate(project, denied, errors, symbol):
        if 'estimate' in denied:
            return {'ok': False, 'text': TEXT_NO_ACCESS}
        if 'estimate' in errors:
            return {'ok': False, 'text': TEXT_ERROR}
        latest = project.dash_latest_estimate_id
        if not latest:
            return {'ok': False, 'text': TEXT_NO_ESTIMATE}
        return {'ok': True, 'latest': f'第 {latest.estimate_no} 期',
                'cum': _money(project.dash_estimate_cum_amount, symbol),
                'month': _money(project.dash_estimate_month_amount, symbol)}

    @staticmethod
    def _progress(project, denied, errors):
        if 'progress' in denied:
            return {'ok': False, 'text': TEXT_NO_ACCESS}
        if 'progress' in errors:
            return {'ok': False, 'text': TEXT_ERROR}
        if not project.dash_has_schedule:
            return {'ok': False, 'text': TEXT_NO_SCHEDULE}
        variance = project.dash_progress_variance
        return {'ok': True, 'planned': f'{project.dash_progress_planned:.1f}%',
                'actual': f'{project.dash_progress_actual:.1f}%',
                'variance': f'{variance:+.1f}%', 'behind': variance < 0,
                'svg': project.dash_progress_svg}

    @staticmethod
    def _photos(project, denied, errors):
        if 'photo' in denied:
            return {'ok': False, 'text': TEXT_NO_ACCESS}
        if 'photo' in errors:
            return {'ok': False, 'text': TEXT_ERROR}
        urls = [f'/construction/img/{photo.attachment_id.id}/{THUMB_SIZE}x{THUMB_SIZE}?crop=true'
                for photo in project.dash_today_photo_ids if photo.attachment_id]
        return {'ok': True, 'count': project.dash_today_photo_count, 'urls': urls, 'empty_text': TEXT_NO_PHOTO}

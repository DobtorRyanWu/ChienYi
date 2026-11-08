# -*- coding: utf-8 -*-
"""公司儀表板指標（合約 §5）：後台看板、前台、控台讀同一份（§1-4）。

* 指標是 project.project 上不儲存的計算欄位（前綴 dash_），compute_sudo=False——用看的人自己的權限算（§1-5）；
  depends_context 含 uid，同一個交易裡不同帳號讀到的不會互相沾到快取。
* 下鑽：一個 _dash_domain(key) 回傳條件，一個 action_dash_drilldown(key) 開清單；欄位計數、公司合計、下鑽都用
  同一個 _dash_domain（卡片數＝下鑽筆數）。
  _dash_domain 回傳 [(模型, 條件), …]：缺失分一般式／預約式兩個模型，「未歸屬」橫跨 8 個模型；
  只有一個來源的指標就一組。self 有值＝限這些工程；self 是空的＝公司合計（不限工程，但要屬於某個工程）。
* 讀不到（沒有該模型的讀取權）→ 該指標標「無權限」（dash_denied_keys），不 sudo 補算、不顯示 0（§1-8）；
  其他例外 → 「讀取失敗」（dash_error_keys），記 log。
* 「今天」＝台灣日期（local_today）。
"""
import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .project_workday import DashMissingCalendar, missing_calendar_message
from .rule_scope import CONTRACTOR_LEVEL

_logger = logging.getLogger(__name__)

# ── 常數 ────────────────────────────────────────────────────────────────
PROJECT_STATE_CONSTRUCTION = 'construction'
COMPANY_TYPE_CONTRACTOR = 'contractor'
DEFECT_MODEL_GENERAL = 'general.defect.improvement'
DEFECT_MODEL_RESERVATION = 'reservation.defect.improvement'
DEFECT_MODELS = (DEFECT_MODEL_GENERAL, DEFECT_MODEL_RESERVATION)
PROJECT_TYPE_RESERVATION = 'reservation'
TEST_NOT_STARTED = 'not_started'
# 估驗金額不算的狀態（合約 §0b-14，照舊系統：舊系統沒有草稿、一提出就存在；新系統的草稿＝尚未提出）
ESTIMATE_EXCLUDED_STATES = ('draft',)
TODAY_PHOTO_LIMIT = 6                               # 卡片最多顯示幾張今日照片（計數另給全部）
PHOTO_ORDER = 'shot_at desc, id desc'
ESTIMATE_LATEST_ORDER = 'estimate_no desc, id desc'
MIN_CONTRACTORS_FOR_UNATTRIBUTED = 2                # 「未歸屬」只看有多家營造廠的工程（一家的會自動帶入）

# 指標群組 → 要讀得到的模型（讀取權不足 → 該群組「無權限」）
GROUP_MODELS = {
    'workday': (),
    'log': ('daily.log.sheet',),
    'photo': ('supervision.photo',),
    'defect': DEFECT_MODELS,
    'test': ('supervision.test.record',),
    'estimate': ('payment.estimate',),
    'progress': ('progress.schedule', 'progress.schedule.line'),
}

# 今日日誌狀態（合約 §5.2 的四種，加上無權限、讀取失敗）
LOG_FILLED = 'filled'
LOG_MISSING = 'missing'
LOG_NOT_REQUIRED = 'not_required'
LOG_NO_CALENDAR = 'no_calendar'
LOG_NO_ACCESS = 'no_access'
LOG_ERROR = 'error'
LOG_TODAY_SELECTION = [
    (LOG_FILLED, '已填'),
    (LOG_MISSING, '未填'),
    (LOG_NOT_REQUIRED, '非工作天或非施工中'),
    (LOG_NO_CALENDAR, '缺政府辦公日曆'),
    (LOG_NO_ACCESS, '無權限查看'),
    (LOG_ERROR, '讀取失敗'),
]
WORKDAY_OK = 'ok'
WORKDAY_ESTIMATED = 'estimated'
WORKDAY_NO_CALENDAR = 'no_calendar'
WORKDAY_NO_DATES = 'no_dates'
WORKDAY_ERROR = 'error'
WORKDAY_STATE_SELECTION = [
    (WORKDAY_OK, '正常'),
    (WORKDAY_ESTIMATED, '含預估'),
    (WORKDAY_NO_CALENDAR, '缺政府辦公日曆'),
    (WORKDAY_NO_DATES, '未設開工日或完工日'),
    (WORKDAY_ERROR, '讀取失敗'),
]
NOTE_ESTIMATED = '含未公告年度（%s），為預估'
NOTE_OVERRUN = '超過 %s 工作天'
NOTE_NO_START = '未設開工日'
NOTE_NO_END = '未設契約完工日'
NOTE_SEPARATOR = '；'
KEY_SEPARATOR = ','

# 公司合計（get_dash_company_kpis）的指標與標籤；_dash_domain 認得的 key 都在這裡
KPI_LABELS = {
    'construction_project': '施工中工程',
    'log_today': '今日已填日誌',
    'log_filled': '今日已填日誌的工程',
    'log_missing': '今日未填日誌的工程',
    'today_photo': '今日照片',
    'open_defect': '待改缺失',
    'overdue_defect': '逾期缺失',
    'pending_test': '檢驗待補',
    'month_estimate': '本月估驗',
    'estimate_cum': '累計估驗（不含草稿）',
    'unattributed': '未歸屬營造廠',
}
KPI_KEYS = tuple(KPI_LABELS)
KPI_GROUP = {
    'construction_project': None,
    'log_today': 'log',
    'log_filled': 'log',
    'log_missing': 'log',
    'today_photo': 'photo',
    'open_defect': 'defect',
    'overdue_defect': 'defect',
    'pending_test': 'test',
    'month_estimate': 'estimate',
    'estimate_cum': 'estimate',
    'unattributed': None,
}
KPI_AMOUNT_KEYS = frozenset({'month_estimate', 'estimate_cum'})
ESTIMATE_AMOUNT_FIELD = 'subtotal'
STATUS_OK = 'ok'
STATUS_NO_ACCESS = 'no_access'
STATUS_NO_CALENDAR = 'no_calendar'
STATUS_ERROR = 'error'
STATUS_NOT_APPLICABLE = 'not_applicable'
STATUS_MESSAGES = {
    STATUS_NO_ACCESS: '無權限查看',
    STATUS_ERROR: '讀取失敗',
    STATUS_NOT_APPLICABLE: '不適用',
}
# 帳號本身被預設拒絕時（合約 §1-7、§13-6）的原因
BLOCKED_TOTP = 'totp_missing'
BLOCKED_SCOPE = 'scope_invalid'
BLOCKED_CONSOLE = 'console_reader'
BLOCKED_MESSAGES = {
    BLOCKED_TOTP: '營造廠主管帳號尚未啟用兩步驟驗證，啟用後才看得到資料',
    BLOCKED_SCOPE: '帳號的範圍公司未設定或不是營造廠，看不到任何資料',
    BLOCKED_CONSOLE: '控台讀取帳號只能呼叫控台取資料方法',
}

# ── 小 S 曲線 SVG（只含數字與固定標記，不含任何使用者字串；合約 §5.2）────────────
SVG_WIDTH = 120
SVG_HEIGHT = 40
SVG_PAD = 2
SVG_MAX_POINTS = 60
PROGRESS_MIN = 0.0
PROGRESS_MAX = 100.0
SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" class="o_dash_scurve" viewBox="0 0 {w} {h}" '
    'width="{w}" height="{h}" preserveAspectRatio="none" role="img" aria-label="進度 S 曲線">'
    '<rect class="o_dash_scurve_frame" x="0.5" y="0.5" width="{fw}" height="{fh}" '
    'fill="none" stroke="#e2e8f0" stroke-width="1"/>'
    '{planned}{actual}{today}'
    '</svg>'
)
SVG_PLANNED = ('<polyline class="o_dash_scurve_planned" fill="none" stroke="#94a3b8" stroke-width="1.2" '
               'stroke-dasharray="3 2" points="{points}"/>')
SVG_ACTUAL = ('<polyline class="o_dash_scurve_actual" fill="none" stroke="#2563eb" stroke-width="1.6" '
              'points="{points}"/>')
SVG_TODAY = ('<line class="o_dash_scurve_today" x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" '
             'stroke="#f97316" stroke-width="1"/>')


def _sample(items, limit):
    """平均取樣到最多 limit 個（保留頭尾）。"""
    if len(items) <= limit:
        return list(items)
    last = len(items) - 1
    picked = sorted({round(i * last / (limit - 1)) for i in range(limit)})
    return [items[i] for i in picked]


def build_progress_svg(chart_data, today):
    """get_progress_chart_data() 的結果 → 小 S 曲線 SVG 字串；沒有任何點回 False。

    只用日期換算出的座標與固定的標籤、顏色；不放工程名稱、版本原因、變更單名稱等任何使用者輸入的字。
    """
    dates = chart_data.get('dates') or []
    if not dates:
        return False
    # 每個日期取最後一點（版本更迭那天有兩點，取新版）
    by_date = {}
    for day_iso, planned, actual in zip(dates, chart_data['planned'], chart_data['actual']):
        by_date[day_iso] = (planned, actual)
    days = sorted(by_date)
    first = date.fromisoformat(days[0])
    last = date.fromisoformat(days[-1])
    span = max((last - first).days, 1)
    inner_w = SVG_WIDTH - 2 * SVG_PAD
    inner_h = SVG_HEIGHT - 2 * SVG_PAD

    def x_of(day):
        return SVG_PAD + (day - first).days / span * inner_w

    def y_of(value):
        value = min(max(float(value or 0.0), PROGRESS_MIN), PROGRESS_MAX)
        return SVG_HEIGHT - SVG_PAD - (value - PROGRESS_MIN) / (PROGRESS_MAX - PROGRESS_MIN) * inner_h

    def points(day_isos, pos):
        return ' '.join(f'{x_of(date.fromisoformat(d)):.1f},{y_of(by_date[d][pos]):.1f}' for d in day_isos)

    planned_days = _sample(days, SVG_MAX_POINTS)
    actual_days = _sample([d for d in days if by_date[d][1] is not None], SVG_MAX_POINTS)
    today_line = ''
    if first <= today <= last:
        today_line = SVG_TODAY.format(x=f'{x_of(today):.1f}', y1=SVG_PAD, y2=SVG_HEIGHT - SVG_PAD)
    return SVG_TEMPLATE.format(
        w=SVG_WIDTH, h=SVG_HEIGHT, fw=SVG_WIDTH - 1, fh=SVG_HEIGHT - 1,
        planned=SVG_PLANNED.format(points=points(planned_days, 0)),
        actual=SVG_ACTUAL.format(points=points(actual_days, 1)) if actual_days else '',
        today=today_line,
    )


def _month_bounds(day):
    start = day.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ── 指標欄位（合約 §5.2；全部不儲存、以看的人的權限算）──────────────────────────
    dash_log_today = fields.Selection(
        LOG_TODAY_SELECTION, string='今日日誌', compute='_compute_dash_indicators', compute_sudo=False,
        help='已填（含編輯中）／未填／非工作天或非施工中／缺政府辦公日曆')
    dash_workday_elapsed = fields.Integer(
        string='已過工作天', compute='_compute_dash_indicators', compute_sudo=False,
        help='開工日（實際開工日，沒有就契約開工日）到今天的工作天數（含頭含尾；已有實際完工日則算到完工日）')
    dash_workday_total = fields.Integer(
        string='總工作天', compute='_compute_dash_indicators', compute_sudo=False,
        help='開工日到契約完工日的工作天數（含頭含尾）')
    dash_workday_note = fields.Char(
        string='工作天備註', compute='_compute_dash_indicators', compute_sudo=False,
        help='「含未公告年度，為預估」「超過 N 工作天」「缺 YYYY 年政府辦公日曆」「未設開工日」等')
    dash_workday_state = fields.Selection(
        WORKDAY_STATE_SELECTION, string='工作天狀態', compute='_compute_dash_indicators', compute_sudo=False)
    dash_today_photo_ids = fields.Many2many(
        'supervision.photo', string='今日照片', compute='_compute_dash_indicators', compute_sudo=False,
        help=f'今天（台灣日期）的照片，最新的 {TODAY_PHOTO_LIMIT} 張')
    dash_today_photo_count = fields.Integer(
        string='今日照片數', compute='_compute_dash_indicators', compute_sudo=False)
    dash_open_defect_count = fields.Integer(
        string='待改缺失', compute='_compute_dash_indicators', compute_sudo=False,
        help='狀態不是已驗證、結案（含草稿與監造內部視角）')
    dash_overdue_defect_count = fields.Integer(
        string='逾期缺失', compute='_compute_dash_indicators', compute_sudo=False)
    dash_pending_test_count = fields.Integer(
        string='檢驗待補', compute='_compute_dash_indicators', compute_sudo=False,
        help='檢試驗紀錄處理狀態＝尚未檢驗')
    dash_latest_estimate_id = fields.Many2one(
        'payment.estimate', string='最近一期估驗', compute='_compute_dash_indicators', compute_sudo=False,
        help='草稿以外期數最大的一期（合約 §0b-17）')
    dash_estimate_cum_amount = fields.Monetary(
        string='累計估驗金額', currency_field='currency_id', compute='_compute_dash_indicators',
        compute_sudo=False, help='草稿以外各期的本次估驗總金額加總（合約 §0b-14，比照舊系統「總計估驗金額」）')
    dash_estimate_month_amount = fields.Monetary(
        string='本月估驗金額', currency_field='currency_id', compute='_compute_dash_indicators',
        compute_sudo=False, help='估驗日期在本月（台灣日期）、草稿以外各期的本次估驗總金額加總（合約 §0b-14）')
    dash_progress_planned = fields.Float(
        string='預定進度(%)', digits=(5, 2), compute='_compute_dash_indicators', compute_sudo=False)
    dash_progress_actual = fields.Float(
        string='實際進度(%)', digits=(5, 2), compute='_compute_dash_indicators', compute_sudo=False)
    dash_progress_variance = fields.Float(
        string='進度差(%)', digits=(5, 2), compute='_compute_dash_indicators', compute_sudo=False)
    dash_has_schedule = fields.Boolean(
        string='已建進度表', compute='_compute_dash_indicators', compute_sudo=False,
        help='有啟用過的進度表（不含草稿）；沒有時畫面顯示「未建進度表」，不顯示 0%')
    dash_progress_svg = fields.Html(
        string='小 S 曲線', sanitize=False, compute='_compute_dash_indicators', compute_sudo=False,
        help='伺服器端產生的 SVG，只含數字與固定標記')
    dash_denied_keys = fields.Char(
        string='無權限的指標', compute='_compute_dash_indicators', compute_sudo=False,
        help='逗號分隔的指標群組（log、photo、defect、test、estimate、progress）：畫面顯示「無權限查看」')
    dash_error_keys = fields.Char(
        string='讀取失敗的指標', compute='_compute_dash_indicators', compute_sudo=False,
        help='逗號分隔的指標群組：畫面顯示「讀取失敗」')

    # ── 計算 ────────────────────────────────────────────────────────────
    @api.model
    def _dash_group_defaults(self, group, status):
        """群組讀不到或讀取失敗時的值（不是 0 的意思：畫面看 dash_denied_keys／dash_error_keys 顯示原因）。"""
        if group == 'workday':
            return {'dash_workday_elapsed': 0, 'dash_workday_total': 0, 'dash_workday_note': False,
                    'dash_workday_state': WORKDAY_ERROR}
        if group == 'log':
            return {'dash_log_today': LOG_NO_ACCESS if status == STATUS_NO_ACCESS else LOG_ERROR}
        if group == 'photo':
            return {'dash_today_photo_ids': [], 'dash_today_photo_count': 0}
        if group == 'defect':
            return {'dash_open_defect_count': 0, 'dash_overdue_defect_count': 0}
        if group == 'test':
            return {'dash_pending_test_count': 0}
        if group == 'estimate':
            return {'dash_latest_estimate_id': False, 'dash_estimate_cum_amount': 0.0,
                    'dash_estimate_month_amount': 0.0}
        if group == 'progress':
            return {'dash_progress_planned': 0.0, 'dash_progress_actual': 0.0, 'dash_progress_variance': 0.0,
                    'dash_has_schedule': False, 'dash_progress_svg': False}
        raise ValueError(group)

    @api.model
    def _dash_group_readable(self, group):
        return all(self.env[model].has_access('read') for model in GROUP_MODELS[group])

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_dash_indicators(self):
        # 還沒存檔的工程（表單 onchange 的 NewId）沒有子資料可數
        real = self.filtered(lambda p: isinstance(p.id, int)).with_context(active_test=False)
        values = {p.id: {} for p in self}
        denied, errors = [], []
        today = local_today()
        index = self.env['construction.official.calendar']._dash_calendar_index()
        fillers = (
            ('workday', lambda: real._dash_fill_workday(today, index)),
            ('log', lambda: real._dash_fill_log(today, index)),
            ('photo', lambda: real._dash_fill_photo()),
            ('defect', lambda: real._dash_fill_defect()),
            ('test', lambda: real._dash_fill_test()),
            ('estimate', lambda: real._dash_fill_estimate()),
            ('progress', lambda: real._dash_fill_progress(today)),
        )
        for group, filler in fillers:
            status = STATUS_OK
            filled = {}
            if not self._dash_group_readable(group):
                status = STATUS_NO_ACCESS
            elif real:
                try:
                    filled = filler()
                except AccessError:
                    status = STATUS_NO_ACCESS
                except Exception:
                    _logger.exception('公司儀表板指標 %s 計算失敗（工程 %s）', group, real.ids[:20])
                    status = STATUS_ERROR
            if status == STATUS_NO_ACCESS:
                denied.append(group)
            elif status == STATUS_ERROR:
                errors.append(group)
            default = self._dash_group_defaults(group, status)
            for project in self:
                values[project.id].update(filled.get(project.id, default) if status == STATUS_OK else default)
        for project in self:
            vals = values[project.id]
            vals['dash_denied_keys'] = KEY_SEPARATOR.join(denied) or False
            vals['dash_error_keys'] = KEY_SEPARATOR.join(errors) or False
            photos = vals.pop('dash_today_photo_ids')
            project.update(vals)
            project.dash_today_photo_ids = self.env['supervision.photo'].browse(photos)

    def _dash_fill_workday(self, today, index):
        result = {}
        for project in self:
            result[project.id] = project._dash_workday_values(today, index)
        return result

    def _dash_workday_values(self, today, index):
        """開工第 X 個工作天／總工作天（合約 §5.2）。缺年度不顯示數字，備註寫「缺 YYYY 年政府辦公日曆」。"""
        self.ensure_one()
        start = self.actual_start_date or self.contract_start_date
        end = self.contract_end_date
        # 已有實際完工日：算到完工日為止（合約 §0b-15；同前台 DAY 計數凍結在 actual_end_date）
        elapsed_to = min(today, self.actual_end_date) if self.actual_end_date else today
        notes = []
        if not start:
            notes.append(NOTE_NO_START)
        if not end:
            notes.append(NOTE_NO_END)
        missing = set()
        if start:
            missing.update(self._dash_missing_years(start, elapsed_to, index))
            if end:
                missing.update(self._dash_missing_years(start, end, index))
        if missing:
            return {'dash_workday_elapsed': 0, 'dash_workday_total': 0,
                    'dash_workday_note': NOTE_SEPARATOR.join([missing_calendar_message(missing)] + notes),
                    'dash_workday_state': WORKDAY_NO_CALENDAR}
        elapsed, estimated = self._dash_count_workdays_detail(start, elapsed_to, index) if start else (0, [])
        total, estimated_total = self._dash_count_workdays_detail(start, end, index) if start and end else (0, [])
        estimated = sorted(set(estimated) | set(estimated_total))
        if estimated:
            notes.insert(0, NOTE_ESTIMATED % '、'.join(str(y) for y in estimated))
        if start and end and elapsed > total:
            notes.append(NOTE_OVERRUN % (elapsed - total))
        if not start or not end:
            state = WORKDAY_NO_DATES
        elif estimated:
            state = WORKDAY_ESTIMATED
        else:
            state = WORKDAY_OK
        return {'dash_workday_elapsed': elapsed, 'dash_workday_total': total,
                'dash_workday_note': NOTE_SEPARATOR.join(notes) or False, 'dash_workday_state': state}

    def _dash_log_today_states(self, today, index):
        """{工程 id: 今日日誌狀態}。日誌以看的人的權限查（今天任何狀態的日誌都算已填，含編輯中）。"""
        if not self:
            return {}
        parts = self._dash_domain('log_today')
        filled = set()
        for model, domain in parts:
            for project, _count in self.env[model]._read_group(domain, ['supervision_project_id'], ['__count']):
                filled.add(project.id)
        states = {}
        for project in self:
            if project.id in filled:
                states[project.id] = LOG_FILLED
            elif project.state != PROJECT_STATE_CONSTRUCTION:
                states[project.id] = LOG_NOT_REQUIRED
            else:
                try:
                    states[project.id] = LOG_MISSING if project._dash_is_workday(today, index) else LOG_NOT_REQUIRED
                except DashMissingCalendar:
                    states[project.id] = LOG_NO_CALENDAR
        return states

    def _dash_fill_log(self, today, index):
        return {pid: {'dash_log_today': state} for pid, state in self._dash_log_today_states(today, index).items()}

    def _dash_fill_photo(self):
        (model, domain), = self._dash_domain('today_photo')
        buckets = {p.id: [] for p in self}
        for photo in self.env[model].search(domain, order=PHOTO_ORDER):
            buckets[photo.project_id.id].append(photo.id)
        return {pid: {'dash_today_photo_ids': ids[:TODAY_PHOTO_LIMIT], 'dash_today_photo_count': len(ids)}
                for pid, ids in buckets.items()}

    def _dash_count_by_project(self, key, aggregate='__count'):
        """依 _dash_domain(key) 的各組條件，以看的人的權限依工程分組加總。"""
        totals = {p.id: 0 for p in self}
        for model, domain in self._dash_domain(key):
            project_field = self._dash_project_field(model)
            for project, value in self.env[model]._read_group(domain, [project_field], [aggregate]):
                totals[project.id] += value or 0
        return totals

    def _dash_fill_defect(self):
        opened = self._dash_count_by_project('open_defect')
        overdue = self._dash_count_by_project('overdue_defect')
        return {p.id: {'dash_open_defect_count': opened[p.id], 'dash_overdue_defect_count': overdue[p.id]}
                for p in self}

    def _dash_fill_test(self):
        pending = self._dash_count_by_project('pending_test')
        return {p.id: {'dash_pending_test_count': pending[p.id]} for p in self}

    def _dash_fill_estimate(self):
        amount = f'{ESTIMATE_AMOUNT_FIELD}:sum'
        cum = self._dash_count_by_project('estimate_cum', amount)
        month = self._dash_count_by_project('month_estimate', amount)
        latest = {}
        # 最近一期也排除草稿（合約 §0b-17，與累計、本月一致：草稿＝尚未提出）
        for estimate in self.env['payment.estimate'].search([('project_id', 'in', self.ids),
                                                             ('state', 'not in', ESTIMATE_EXCLUDED_STATES)],
                                                            order=ESTIMATE_LATEST_ORDER):
            latest.setdefault(estimate.project_id.id, estimate.id)
        return {p.id: {'dash_latest_estimate_id': latest.get(p.id, False),
                       'dash_estimate_cum_amount': cum[p.id], 'dash_estimate_month_amount': month[p.id]}
                for p in self}

    def _dash_fill_progress(self, today):
        """進度相關欄位共用一次 get_progress_chart_data()（合約 §5.1），與單一工程頁的進度摘要同一份數字。"""
        result = {}
        for project in self:
            data = project.get_progress_chart_data()
            values = project._progress_values_on(data, today)
            if values is None:
                result[project.id] = self._dash_group_defaults('progress', STATUS_OK)
                continue
            result[project.id] = {
                'dash_progress_planned': values['planned'],
                'dash_progress_actual': values['actual'],
                'dash_progress_variance': values['variance'],
                'dash_has_schedule': True,
                'dash_progress_svg': build_progress_svg(data, today),
            }
        return result

    # ── 條件（計數、公司合計、下鑽共用）─────────────────────────────────────
    @api.model
    def _dash_project_field(self, model):
        """各模型指向工程的欄位（日誌是 supervision_project_id；工程本身是 id）。"""
        if model == 'project.project':
            return 'id'
        return CONTRACTOR_LEVEL.get(model, 'project_id')

    def _dash_scope(self, model):
        """self 有值＝限這些工程；空＝公司合計（要屬於某個工程）。"""
        field = self._dash_project_field(model)
        return [(field, 'in', self.ids)] if self else [(field, '!=', False)]

    def _dash_defect_model(self):
        """與前台缺失列表、進度模組的缺失摘要一致：依工程類型選模型。"""
        self.ensure_one()
        return DEFECT_MODEL_RESERVATION if self.project_type == PROJECT_TYPE_RESERVATION else DEFECT_MODEL_GENERAL

    def _dash_defect_parts(self, condition_method):
        if not self:
            return [(m, self._dash_scope(m) + getattr(self.env[m], condition_method)()) for m in DEFECT_MODELS]
        by_model = {}
        for project in self:
            by_model.setdefault(project._dash_defect_model(), self.browse())
            by_model[project._dash_defect_model()] |= project
        return [(m, projects._dash_scope(m) + getattr(self.env[m], condition_method)())
                for m, projects in by_model.items()]

    def _dash_domain(self, key):
        """指標 key 的條件：[(模型, 條件), …]（見檔頭）。不認得的 key 丟 UserError。"""
        today = local_today()
        if key == 'construction_project':
            # 施工中工程只算有效工程（合約 §13-5）
            return [('project.project', self._dash_scope('project.project') + [
                ('state', '=', PROJECT_STATE_CONSTRUCTION), ('active', '=', True)])]
        if key == 'log_today':
            return [('daily.log.sheet', self._dash_scope('daily.log.sheet') + [('log_date', '=', today)])]
        if key == 'log_missing':
            projects = self or self.search([('state', '=', PROJECT_STATE_CONSTRUCTION), ('active', '=', True)])
            index = self.env['construction.official.calendar']._dash_calendar_index()
            states = projects._dash_log_today_states(today, index)
            if LOG_NO_CALENDAR in states.values():
                raise DashMissingCalendar([today.year])
            return [('project.project', [('id', 'in', [pid for pid, s in states.items() if s == LOG_MISSING])])]
        if key == 'log_filled':
            # 今日已填日誌的工程數（雛型「已填／應填」的分子；log_today 是張數，一個工程一天可有多張）。
            # 與 log_missing 同一份狀態表 → 已填＋未填＝今天該填的工程數；已填與日曆無關，缺日曆不擋（合約 §0b-33）
            projects = self or self.search([('state', '=', PROJECT_STATE_CONSTRUCTION), ('active', '=', True)])
            index = self.env['construction.official.calendar']._dash_calendar_index()
            states = projects._dash_log_today_states(today, index)
            return [('project.project', [('id', 'in', [pid for pid, s in states.items() if s == LOG_FILLED])])]
        if key == 'today_photo':
            return [('supervision.photo', self._dash_scope('supervision.photo') + [
                ('shot_date', '=', today), ('active', '=', True)])]
        if key == 'open_defect':
            return self._dash_defect_parts('_dash_open_domain')
        if key == 'overdue_defect':
            return self._dash_defect_parts('_dash_overdue_domain')
        if key == 'pending_test':
            return [('supervision.test.record', self._dash_scope('supervision.test.record') + [
                ('processing_status', '=', TEST_NOT_STARTED)])]
        if key == 'month_estimate':
            month_start, month_end = _month_bounds(today)
            return [('payment.estimate', self._dash_scope('payment.estimate') + [
                ('estimate_date', '>=', month_start), ('estimate_date', '<=', month_end),
                ('state', 'not in', ESTIMATE_EXCLUDED_STATES)])]
        if key == 'estimate_cum':
            return [('payment.estimate', self._dash_scope('payment.estimate') + [
                ('state', 'not in', ESTIMATE_EXCLUDED_STATES)])]
        if key == 'unattributed':
            # 工程有多家營造廠、子資料營造廠歸屬空白（合約 §3.5）。工程以看的人的權限找；
            # 「是不是營造廠」看工程承包廠商的公司類型（公司本身可能不在看的人的允許公司內，用 sudo 讀類型，
            # 與 contractor_attribution 判斷單一營造廠的方式相同）
            projects = self or self.with_context(active_test=False).search([])
            multi = projects.filtered(lambda p: len(p.sudo().contractor_company_ids.filtered(
                lambda c: c.company_type == COMPANY_TYPE_CONTRACTOR)) >= MIN_CONTRACTORS_FOR_UNATTRIBUTED)
            return [(model, [(field, 'in', multi.ids), ('contractor_company_id', '=', False)])
                    for model, field in CONTRACTOR_LEVEL.items()]
        raise UserError(f'不認得的儀表板指標：{key}')

    def action_dash_drilldown(self, key, model_name=None):
        """開指標的清單（與計數同一個條件）。有多個來源（缺失兩種、未歸屬 8 種）時要指定 model_name。"""
        parts = self._dash_domain(key)
        if model_name:
            parts = [part for part in parts if part[0] == model_name]
        if len(parts) != 1:
            raise UserError(f'「{KPI_LABELS.get(key, key)}」有 {len(parts)} 個資料來源，請指定要看哪一個。')
        model, domain = parts[0]
        self.env[model].check_access('read')
        return {
            'type': 'ir.actions.act_window',
            'name': KPI_LABELS.get(key, key),
            'res_model': model,
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            # 封存、終止工程底下的事項也算（合約 §5.1）；條件本身已寫明 active 的地方不受影響
            'context': {'active_test': False, 'create': False},
            'target': 'current',
        }

    # ── 公司合計 ──────────────────────────────────────────────────────────
    @api.model
    def _dash_blocked_reason(self):
        """看的人整個被預設拒絕的原因（營造方範圍不合格、營造廠主管未啟用兩步驟驗證、控台讀取帳號）；沒有回 None。"""
        user = self.env.user
        if self.env.su:
            return None
        if user._dash_is_console_reader():
            return BLOCKED_CONSOLE
        if user._dash_is_contractor_side() and not user._dash_scope_ok():
            return BLOCKED_TOTP if user._dash_totp_missing() else BLOCKED_SCOPE
        return None

    @api.model
    def get_dash_company_kpis(self):
        """公司合計（合約 §5.1）：各項直接 search_count(_dash_domain(key))，以看的人的權限、active_test=False。

        回傳 {'today', 'computed_at', 'blocked_reason', 'blocked_message', 'kpis': {key: {
            'label', 'status'（ok／no_access／no_calendar／error／not_applicable）, 'message',
            'count', 'amount'（只有估驗兩項）, 'parts': [{'model', 'label', 'count'}]}}}
        count＝各 parts 的 count 加總；下鑽用 action_dash_drilldown(key, model_name)。
        """
        projects = self.browse().with_context(active_test=False)
        blocked = projects._dash_blocked_reason()
        user = self.env.user
        supervision_like = not user._dash_is_contractor_side() and not user._dash_is_console_reader()
        kpis = {}
        for key in KPI_KEYS:
            entry = {'label': KPI_LABELS[key], 'status': STATUS_OK, 'message': False,
                     'count': None, 'amount': None, 'parts': []}
            if blocked:
                entry.update(status=STATUS_NO_ACCESS, message=BLOCKED_MESSAGES[blocked])
            elif key == 'unattributed' and not supervision_like:
                entry.update(status=STATUS_NOT_APPLICABLE, message=STATUS_MESSAGES[STATUS_NOT_APPLICABLE])
            else:
                entry.update(projects._dash_kpi_values(key))
            kpis[key] = entry
        return {
            'today': local_today().isoformat(),
            'computed_at': fields.Datetime.to_string(fields.Datetime.now()),
            'blocked_reason': blocked or False,
            'blocked_message': BLOCKED_MESSAGES.get(blocked, False),
            'kpis': kpis,
        }

    def _dash_kpi_values(self, key):
        group = KPI_GROUP[key]
        try:
            if group and not self._dash_group_readable(group):
                raise AccessError(STATUS_MESSAGES[STATUS_NO_ACCESS])
            parts = self._dash_domain(key)
            out_parts = []
            amount = 0.0
            for model, domain in parts:
                Model = self.env[model].with_context(active_test=False)
                Model.check_access('read')
                out_parts.append({'model': model, 'label': Model._description, 'count': Model.search_count(domain)})
                if key in KPI_AMOUNT_KEYS:
                    (value,), = Model._read_group(domain, [], [f'{ESTIMATE_AMOUNT_FIELD}:sum'])
                    amount += value or 0.0
            return {'count': sum(p['count'] for p in out_parts), 'parts': out_parts,
                    'amount': amount if key in KPI_AMOUNT_KEYS else None}
        except AccessError:
            return {'status': STATUS_NO_ACCESS, 'message': STATUS_MESSAGES[STATUS_NO_ACCESS]}
        except DashMissingCalendar as exc:
            return {'status': STATUS_NO_CALENDAR, 'message': exc.args[0]}
        except Exception:
            _logger.exception('公司儀表板合計 %s 計算失敗', key)
            return {'status': STATUS_ERROR, 'message': STATUS_MESSAGES[STATUS_ERROR]}

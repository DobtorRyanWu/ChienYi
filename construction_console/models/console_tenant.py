# -*- coding: utf-8 -*-
"""控台的租戶與工程總覽快照（合約 §8.3；命名沿用控台草案第四節）。

* console.tenant：庫名、網址、資料時間（租戶算出快照的時間）、上次成功、上次失敗與原因。
  這四個狀態欄位只能由 replace_snapshot()／record_pull_failure() 以 sudo 寫入，任何帳號直接寫都拒
  （畫面靠它們告訴人「這份數字是什麼時候的、拉壞了沒」，不能被手動蓋掉）。
* console.tenant.project：租戶 dash_console_overview()（§8.1）回來的一列一工程；所有帳號唯讀（ACL 只給讀）。
* replace_snapshot(rows, project_count, computed_at)：拉資料程式呼叫。一個 RPC＝一個交易，
  先整批檢查、全部合格才刪舊列建新列；任何一項不合格 → 不動舊快照、記失敗原因、回 {'ok': False, 'reason'}
  （不丟例外：丟例外整個交易會回滾，失敗原因就記不下來；拉資料程式看到 ok=False 自己丟例外、非 0 退出）。
  伺服器端的筆數檢查（合約 §0b、§8.2）：拉回筆數≠租戶原生 SQL 數的 project_count、或從大於 0 變成 0 → 拒寫。
"""
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

PULLER_GROUP_XMLID = 'construction_console.group_console_puller'
# 庫名格式（控台草案第六節）
DB_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]{2,30}$')
# 上次成功超過這麼久就標「資料過時」——拉資料程式整個沒在跑時（排程被拿掉、主機停機）不會有失敗紀錄，
# 只能靠時間看出來。hypothesis：每天拉一次＋2 小時寬限；排程頻率待部署位置定案（合約 §8.5）後調整。
STALE_AFTER = timedelta(hours=26)
FAILURE_REASON_MAX = 2000                 # 失敗原因最多存幾個字
# 只由拉資料方法寫入的狀態欄位
STATUS_FIELDS = frozenset({'data_computed_at', 'last_success_at', 'last_failure_at', 'last_failure_reason'})
CONTRACTOR_SEPARATOR = '、'
VAT_SEPARATOR = ','

PULL_NEVER = 'never'
PULL_OK = 'ok'
PULL_FAILED = 'failed'
PULL_STALE = 'stale'
PULL_STATE_SELECTION = [
    (PULL_NEVER, '從未成功'),
    (PULL_OK, '正常'),
    (PULL_FAILED, '上次拉取失敗（顯示的是舊快照）'),
    (PULL_STALE, '資料過時（太久沒有成功拉取）'),
]

# 租戶 dash_console_overview() 每列的鍵與型別（合約 §8.1；租戶端常數 PROJECT_ROW_KEYS）。
# 鍵要完全相同：少一個是租戶版本不對，多一個可能是租戶多送了不該送的東西——兩種都拒寫、要人處理。
ROW_SCHEMA = {
    'remote_id': 'int',
    'name': 'str',
    'code': 'str_or_false',
    'state': 'str_or_false',
    'state_label': 'str_or_false',
    'active': 'bool',
    'contractor_companies': 'companies',
    'supervision_company': 'company',
    'workday_elapsed': 'int',
    'workday_total': 'int',
    'workday_note': 'str_or_false',
    'workday_state': 'str_or_false',
    'workday_state_label': 'str_or_false',
    'log_today': 'str_or_false',
    'log_today_label': 'str_or_false',
    'today_photo_count': 'int',
    'open_defect_count': 'int',
    'overdue_defect_count': 'int',
    'pending_test_count': 'int',
    'latest_estimate_no': 'int_or_false',
    'latest_estimate_date': 'date_or_false',
    'estimate_cum_amount': 'num',
    'estimate_month_amount': 'num',
    'progress_planned': 'num',
    'progress_actual': 'num',
    'progress_variance': 'num',
    'has_schedule': 'bool',
    'denied_keys': 'str_or_false',
    'error_keys': 'str_or_false',
}
# 營造廠每家、監造公司（工程的管理公司，租戶端必填）同一個形狀
CONTRACTOR_SCHEMA = {'name': 'str', 'vat': 'str_or_false'}
# 錯誤訊息裡最多列幾個有問題的工程／鍵
REPORT_LIMIT = 5


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _value_ok(kind, value):
    """一個值合不合型別（XML-RPC 傳來的是 int／float／str／bool／list／dict）。"""
    if kind == 'int':
        return _is_int(value)
    if kind == 'int_or_false':
        return value is False or _is_int(value)
    if kind == 'num':
        return _is_int(value) or isinstance(value, float)
    if kind == 'str':
        return isinstance(value, str) and bool(value)
    if kind == 'str_or_false':
        return value is False or isinstance(value, str)
    if kind == 'bool':
        return isinstance(value, bool)
    if kind == 'date_or_false':
        if value is False:
            return True
        try:
            return isinstance(value, str) and bool(fields.Date.to_date(value))
        except ValueError:
            return False
    if kind == 'company':
        return (isinstance(value, dict) and set(value) == set(CONTRACTOR_SCHEMA)
                and all(_value_ok(k, value[f]) for f, k in CONTRACTOR_SCHEMA.items()))
    if kind == 'companies':
        return isinstance(value, list) and all(_value_ok('company', item) for item in value)
    raise ValueError(kind)


def _row_problem(row):
    """一列的問題（字串）；沒問題回 None。"""
    if not isinstance(row, dict):
        return _('不是物件')
    missing = sorted(set(ROW_SCHEMA) - set(row))
    extra = sorted(set(row) - set(ROW_SCHEMA))
    if missing or extra:
        return _('鍵不符（缺 %(missing)s；多 %(extra)s）',
                 missing=', '.join(missing) or '無', extra=', '.join(extra) or '無')
    bad = [key for key, kind in ROW_SCHEMA.items() if not _value_ok(kind, row[key])]
    if bad:
        return _('型別不符：%s', ', '.join(bad[:REPORT_LIMIT]))
    return None


class ConsoleTenant(models.Model):
    _name = 'console.tenant'
    _description = '控台租戶'
    _order = 'name, id'

    name = fields.Char(string='監造公司', required=True)
    db_name = fields.Char(string='資料庫名', required=True, index=True,
                          help='租戶資料庫名，拉資料程式設定檔的 db 要與它相同')
    url = fields.Char(string='網址', help='租戶的正式網址（顯示用；拉資料一律走主機本機 127.0.0.1，見設定檔）')
    project_ids = fields.One2many('console.tenant.project', 'tenant_id', string='工程總覽')
    snapshot_count = fields.Integer(string='快照工程數', compute='_compute_snapshot_count')
    data_computed_at = fields.Datetime(string='資料時間', readonly=True,
                                       help='目前這份快照是租戶在什麼時候算出來的')
    last_success_at = fields.Datetime(string='上次成功', readonly=True)
    last_failure_at = fields.Datetime(string='上次失敗', readonly=True)
    last_failure_reason = fields.Text(string='上次失敗原因', readonly=True)
    pull_state = fields.Selection(PULL_STATE_SELECTION, string='拉取狀態', compute='_compute_pull_state')

    _sql_constraints = [
        ('db_name_uniq', 'unique(db_name)', '資料庫名不可重複'),
    ]

    @api.constrains('db_name')
    def _check_db_name(self):
        for tenant in self:
            if not DB_NAME_PATTERN.match(tenant.db_name or ''):
                raise ValidationError(_('資料庫名「%s」格式不對：小寫英文開頭，只能有小寫英文、數字、底線，3～31 字。',
                                        tenant.db_name))

    def _compute_snapshot_count(self):
        counts = dict(self.env['console.tenant.project']._read_group(
            [('tenant_id', 'in', self.ids)], ['tenant_id'], ['__count']))
        for tenant in self:
            tenant.snapshot_count = counts.get(tenant, 0)

    @api.depends('last_success_at', 'last_failure_at')
    def _compute_pull_state(self):
        now = fields.Datetime.now()
        for tenant in self:
            if tenant.last_failure_at and (not tenant.last_success_at
                                           or tenant.last_failure_at >= tenant.last_success_at):
                tenant.pull_state = PULL_FAILED
            elif not tenant.last_success_at:
                tenant.pull_state = PULL_NEVER
            elif now - tenant.last_success_at > STALE_AFTER:
                tenant.pull_state = PULL_STALE
            else:
                tenant.pull_state = PULL_OK

    # ── 狀態欄位只由拉資料方法寫 ─────────────────────────────────────────
    @api.model
    def _console_check_status_vals(self, vals):
        if not self.env.su and STATUS_FIELDS & set(vals):
            raise AccessError(_('資料時間與成功／失敗紀錄只由拉資料程式寫入，不能手動改（%s）。',
                                ', '.join(sorted(STATUS_FIELDS & set(vals)))))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._console_check_status_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._console_check_status_vals(vals)
        return super().write(vals)

    # ── 拉資料程式呼叫的兩個方法 ─────────────────────────────────────────
    @api.model
    def _console_check_puller(self):
        """呼叫者（env.user，不因 sudo 跳過）必須是「控台拉資料」帳號。"""
        if not self.env.user.has_group(PULLER_GROUP_XMLID):
            raise AccessError(_('只有「控台拉資料」帳號可以寫入工程總覽快照。'))

    def _console_mark_failure(self, reason):
        self.ensure_one()
        self.sudo().write({
            'last_failure_at': fields.Datetime.now(),
            'last_failure_reason': (reason or _('（未提供原因）'))[:FAILURE_REASON_MAX],
        })

    def record_pull_failure(self, reason):
        """拉資料程式在租戶那一端失敗（連不上、key 失效、RPC 錯誤、它自己的檢查不過）時呼叫：只記失敗，快照不動。"""
        self.ensure_one()
        self._console_check_puller()
        if not isinstance(reason, str) or not reason:
            raise ValidationError(_('失敗原因必須是非空字串。'))
        self._console_mark_failure(reason)
        return True

    def _console_snapshot_problem(self, rows, project_count, computed_at):
        """整批檢查；回傳拒寫原因（字串），全部合格回 None。"""
        if not isinstance(rows, list):
            return _('工程列不是清單')
        if not _is_int(project_count) or project_count < 0:
            return _('工程總數（project_count）不是非負整數：%r', project_count)
        try:
            if not (isinstance(computed_at, str) and fields.Datetime.to_datetime(computed_at)):
                return _('資料時間（computed_at）不是日期時間字串：%r', computed_at)
        except ValueError:
            return _('資料時間（computed_at）不是日期時間字串：%r', computed_at)
        if len(rows) != project_count:
            return _('筆數不符：租戶回報工程總數 %(total)s（原生 SQL），拉回 %(got)s 筆；拒寫，保留舊快照（控台伺服器檢查）',
                     total=project_count, got=len(rows))
        old_count = len(self.sudo().project_ids)
        if old_count and not project_count:
            return _('工程數從 %s 變成 0：拒寫，保留舊快照（控台伺服器檢查）。若租戶真的已經沒有工程，請人工確認後處理。',
                     old_count)
        problems = []
        for index, row in enumerate(rows):
            problem = _row_problem(row)
            if problem:
                problems.append(_('第 %(no)s 列：%(problem)s', no=index + 1, problem=problem))
        if problems:
            return _('工程列格式不符（%(count)s 列），拒寫：%(sample)s', count=len(problems),
                     sample='；'.join(problems[:REPORT_LIMIT]))
        remote_ids = [row['remote_id'] for row in rows]
        if len(set(remote_ids)) != len(remote_ids):
            return _('同一個工程出現多次（remote_id 重複），拒寫')
        return None

    def replace_snapshot(self, rows, project_count, computed_at):
        """整批替換這個租戶的工程總覽快照（一個交易）。回 {'ok': True, 'count'} 或 {'ok': False, 'reason'}。"""
        self.ensure_one()
        self._console_check_puller()
        tenant = self.sudo()
        reason = tenant._console_snapshot_problem(rows, project_count, computed_at)
        if reason:
            tenant._console_mark_failure(reason)
            return {'ok': False, 'reason': reason}
        tenant.project_ids.unlink()
        self.env['console.tenant.project'].sudo().create([tenant._console_row_vals(row) for row in rows])
        now = fields.Datetime.now()
        tenant.write({'data_computed_at': computed_at, 'last_success_at': now})
        return {'ok': True, 'count': len(rows)}

    @staticmethod
    def _console_company_display(company):
        return f"{company['name']}（{company['vat']}）" if company['vat'] else company['name']

    def _console_row_vals(self, row):
        companies = row['contractor_companies']
        supervision = row['supervision_company']
        return {
            'tenant_id': self.id,
            'remote_id': row['remote_id'],
            'name': row['name'],
            'code': row['code'],
            'state': row['state'],
            'state_label': row['state_label'],
            'remote_active': row['active'],
            'contractor_display': CONTRACTOR_SEPARATOR.join(
                self._console_company_display(c) for c in companies) or False,
            'contractor_vats': VAT_SEPARATOR.join(sorted(c['vat'] for c in companies if c['vat'])) or False,
            'supervision_company_display': self._console_company_display(supervision),
            'supervision_company_vat': supervision['vat'],
            'workday_elapsed': row['workday_elapsed'],
            'workday_total': row['workday_total'],
            'workday_note': row['workday_note'],
            'workday_state': row['workday_state'],
            'workday_state_label': row['workday_state_label'],
            'log_today': row['log_today'],
            'log_today_label': row['log_today_label'],
            'today_photo_count': row['today_photo_count'],
            'open_defect_count': row['open_defect_count'],
            'overdue_defect_count': row['overdue_defect_count'],
            'pending_test_count': row['pending_test_count'],
            'latest_estimate_no': row['latest_estimate_no'] or 0,
            'latest_estimate_date': row['latest_estimate_date'],
            'estimate_cum_amount': row['estimate_cum_amount'],
            'estimate_month_amount': row['estimate_month_amount'],
            'progress_planned': row['progress_planned'],
            'progress_actual': row['progress_actual'],
            'progress_variance': row['progress_variance'],
            'has_schedule': row['has_schedule'],
            'denied_keys': row['denied_keys'],
            'error_keys': row['error_keys'],
        }


class ConsoleTenantProject(models.Model):
    _name = 'console.tenant.project'
    _description = '控台工程總覽'
    _order = 'tenant_id, code, remote_id'

    tenant_id = fields.Many2one('console.tenant', string='租戶', required=True, ondelete='cascade', index=True)
    remote_id = fields.Integer(string='租戶內工程 id', required=True, aggregator=False)
    name = fields.Char(string='工程名稱')
    code = fields.Char(string='工程編號')
    state = fields.Char(string='狀態代碼', help='租戶的狀態值，存字串（租戶多了新狀態也收得進來）')
    state_label = fields.Char(string='狀態')
    remote_active = fields.Boolean(string='租戶端有效', help='租戶端封存的工程也會列出（未結事項要算）')
    contractor_display = fields.Char(string='營造廠（統編）')
    contractor_vats = fields.Char(string='營造廠統編')
    # 工程的監造公司（租戶端工程的管理公司）：jt 這種多家監造公司共用的庫，同一租戶底下要分得出是哪一家
    supervision_company_display = fields.Char(string='監造公司（統編）', index=True)
    supervision_company_vat = fields.Char(string='監造公司統編')
    workday_elapsed = fields.Integer(string='已過工作天', aggregator=False)
    workday_total = fields.Integer(string='總工作天', aggregator=False)
    workday_note = fields.Char(string='工作天備註')
    workday_state = fields.Char(string='工作天狀態代碼')
    workday_state_label = fields.Char(string='工作天狀態')
    log_today = fields.Char(string='今日日誌代碼')
    log_today_label = fields.Char(string='今日日誌')
    today_photo_count = fields.Integer(string='今日照片')
    open_defect_count = fields.Integer(string='待改缺失')
    overdue_defect_count = fields.Integer(string='逾期缺失')
    pending_test_count = fields.Integer(string='檢驗待補')
    latest_estimate_no = fields.Integer(string='最近一期估驗', aggregator=False, help='0＝尚無估驗')
    latest_estimate_date = fields.Date(string='最近一期估驗日期')
    estimate_cum_amount = fields.Float(string='累計估驗金額', digits=(16, 0))
    estimate_month_amount = fields.Float(string='本月估驗金額', digits=(16, 0))
    progress_planned = fields.Float(string='預定進度(%)', digits=(5, 2), aggregator=False)
    progress_actual = fields.Float(string='實際進度(%)', digits=(5, 2), aggregator=False)
    progress_variance = fields.Float(string='進度差(%)', digits=(5, 2), aggregator=False)
    has_schedule = fields.Boolean(string='已建進度表')
    denied_keys = fields.Char(string='無權限的指標')
    error_keys = fields.Char(string='讀取失敗的指標', help='有值時同列的數字不可當真（租戶算這一組指標時出錯）')
    tenant_data_computed_at = fields.Datetime(related='tenant_id.data_computed_at', string='資料時間')
    tenant_last_failure_at = fields.Datetime(related='tenant_id.last_failure_at', string='上次失敗')
    tenant_pull_state = fields.Selection(related='tenant_id.pull_state', string='拉取狀態')

    _sql_constraints = [
        ('tenant_remote_uniq', 'unique(tenant_id, remote_id)', '同一租戶的工程不可重複'),
    ]

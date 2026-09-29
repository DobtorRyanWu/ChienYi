# -*- coding: utf-8 -*-
"""系統問題單。分級與結案邏輯依《系統問題分級與處理時限標準》v0.3。"""
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .problem_sla import PRIORITY_SELECTION
from .service_ticket import TICKET_ACTIVE_STATES

# 起算日要把 Datetime（UTC）換成台灣日期。stored compute 不能跟著執行者的時區走，
# 否則不同人觸發重算會得到不同日期，所以固定用本系統所在時區。
LOCAL_TZ = pytz.timezone('Asia/Taipei')

WEEKDAYS = '一二三四五六日'

# 選項文字附上簡短判定條件，讓客服在下拉時就有依據（完整標準見表單上的判定標準參考表）
SEVERITY_SELECTION = [
    ('s1', 'S1 致命（錯的值已存進資料庫／寫錯工程、無法登入或停擺、安全告警沒發、資安疑慮）'),
    ('s2', 'S2 嚴重（核心功能不能用，且沒有替代做法）'),
    ('s3', 'S3 中等（有替代做法、只影響部分人，或只是畫面／匯出錯而資料庫正確）'),
    ('s4', 'S4 輕微（不影響功能與資料正確性：錯字、跑版）'),
]
URGENCY_SELECTION = [
    ('u1', 'U1 立即（現場作業中斷，或 3 個工作天內有送件／請款／驗收）'),
    ('u2', 'U2 一般（可暫時替代，外部期限在 2 週內）'),
    ('u3', 'U3 可延後（不影響目前作業，沒有明確期限）'),
]

# P1～P4 代表的層級（分級標準第六節）。修復期限另從「處理時限設定」即時讀取，這裡只放不會變的部分
PRIORITY_MEANING = {
    'p1': ('最緊急', '緊急修補，修好即部署', '須先做暫行措施（停用功能／請客戶暫緩／人工提供正確數字）；一律通知客戶'),
    'p2': ('緊急', '緊急版本', '須先做暫行措施'),
    'p3': ('一般', '下一次例行版本', ''),
    'p4': ('低', '例行版本（排入規劃）', ''),
}
STATE_SELECTION = [
    ('pending_grade', '待分級'),
    ('processing', '處理中'),
    ('pending_deploy', '待部署'),
    ('pending_verify', '待驗證'),
    ('done', '已結案'),
    ('wont_fix', '不處理'),
]
CLOSED_STATES = ('done', 'wont_fix')

# P 表（S × U）。分級標準第四節。刻意寫死：P 表比時限更少變動，要改就改程式、bump 版號。
# 問題單上的 P 是 stored，改這張表不會回頭改既有問題單。
P_MATRIX = {
    ('s1', 'u1'): 'p1', ('s1', 'u2'): 'p1', ('s1', 'u3'): 'p2',
    ('s2', 'u1'): 'p1', ('s2', 'u2'): 'p2', ('s2', 'u3'): 'p3',
    ('s3', 'u1'): 'p2', ('s3', 'u2'): 'p3', ('s3', 'u3'): 'p4',
    ('s4', 'u1'): 'p3', ('s4', 'u2'): 'p4', ('s4', 'u3'): 'p4',
}

# 分級欄位：分級之後只能透過「變更等級」對話框修改（確保每次改判都有原因）
GRADE_FIELDS = (
    'severity', 'urgency', 'special_external_doc', 'special_security', 'special_repeat',
    'manual_priority', 'downgrade_reason',
)

# 只能由系統流程寫入（write() 擋手動修改，流程內以 context helpdesk_system_write 放行）
SYSTEM_FIELDS = (
    'ever_waited_customer', 'close_type', 'wont_fix_reason', 'wont_fix_note', 'duplicate_of_id',
)

DATA_FIX_STATE_SELECTION = [
    ('todo', '待盤點'),
    ('in_progress', '修正中'),
    ('done', '已完成'),
]

# 結案方式（分級標準 v0.3 第九節）。由「結案」按鈕依條件自動判定，不能手選。
CLOSE_TYPE_SELECTION = [
    ('confirmed', '客戶確認'),
    ('no_reply_evidence', '未回覆、附對照結案'),
    ('no_reply_overdue', '逾期未回覆結案'),
    ('internal', '無關聯服務單'),
]

# 「不處理」必須選原因（第九節）。P1 不能選「無法重現」「接受風險」。
WONT_FIX_REASON_SELECTION = [
    ('duplicate', '重複（併入另一張問題單）'),
    ('cannot_reproduce', '無法重現'),
    ('not_system', '不是系統問題（操作錯誤、誤報）'),
    ('risk_accepted', '接受風險（決定不修）'),
]
WONT_FIX_NOT_FOR_P1 = ('cannot_reproduce', 'risk_accepted')

PII_LEAK_SELECTION = [
    ('yes', '有'),
    ('no', '無'),
    ('unknown', '無法判定（視同有）'),
]
NOTIFY_DECISION_SELECTION = [
    ('notify', '通知'),
    ('not_notify', '不通知'),
]


def p_rank(priority):
    """'p1' → 1。數字越小越優先。"""
    return int(priority[1]) if priority else None


def upgraded_priority(matrix_p, external_doc, security, repeat):
    """套用特例（分級標準 v0.3 第五節）。"""
    if security or external_doc:
        return 'p1'                       # 資安、錯誤已流入對外文件：直接 P1（不必先判 S、U）
    if not matrix_p:
        return False
    if repeat:
        return 'p%d' % max(1, p_rank(matrix_p) - 1)   # 二次回報：升一級
    return matrix_p


def hours_between(start, end):
    """兩個 Datetime 相差幾小時（實際經過時間，資安檢核表用）。"""
    if not start or not end:
        return 0.0
    return round((end - start).total_seconds() / 3600.0, 1)


class ConstructionProblem(models.Model):
    _name = 'construction.problem'
    _description = '系統問題單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'title']

    # ------------------------------------------------------------------
    # 基本
    # ------------------------------------------------------------------
    name = fields.Char(string='單號', required=True, readonly=True, copy=False, default='新增')
    title = fields.Char(string='標題', required=True, tracking=True)
    description = fields.Html(
        string='問題說明',
        help='這個問題的具體情況（在哪個畫面、做了什麼、看到什麼）。從服務單轉出時自動帶入服務單的詳細說明。'
             '判斷其他客戶的回報是不是同一個問題，主要就是比對這裡與發生功能。')
    description_summary = fields.Char(
        string='問題說明摘要', compute='_compute_description_summary',
        help='問題說明的前 120 字（純文字），給轉問題單時比對候選用。')
    functional_module_id = fields.Many2one(
        'construction.functional.module', string='發生功能', tracking=True, ondelete='restrict')
    engineer_id = fields.Many2one(
        'res.users', string='負責工程師', tracking=True,
        domain=lambda self: [('groups_id', 'in', self.env.ref(
            'construction_helpdesk.group_helpdesk_agent').id)])
    state = fields.Selection(
        STATE_SELECTION, string='狀態', required=True, default='pending_grade', tracking=True,
        copy=False,
        # Selection 欄位要用 True（Odoo 自帶的展開）；'_read_group_expand_full' 只適用 Many2one，
        # 用在 Selection 會在看板分組時丟 AttributeError: 'list' object has no attribute 'search'
        group_expand=True)
    occurred_version = fields.Char(string='發生時的系統版本')

    # ------------------------------------------------------------------
    # 分級（S、U 刻意沒有預設值：沒判就是沒判）
    # ------------------------------------------------------------------
    severity = fields.Selection(SEVERITY_SELECTION, string='嚴重程度 S', tracking=True)
    urgency = fields.Selection(URGENCY_SELECTION, string='急迫性 U', tracking=True)
    matrix_priority = fields.Selection(
        PRIORITY_SELECTION, string='查表 P', compute='_compute_priorities', store=True)
    special_external_doc = fields.Boolean(
        string='錯誤已流入對外文件', tracking=True,
        help='錯誤已反映在送出去的估驗計價單、施工日誌等文件上。直接 P1，且必須通知客戶。')
    special_security = fields.Boolean(
        string='資安事件', tracking=True, help='直接 P1，並填寫「資安事件」頁籤的檢核表。')
    special_repeat = fields.Boolean(string='二次回報（前次未修好）', tracking=True, help='升一級。')
    upgraded_priority = fields.Selection(
        PRIORITY_SELECTION, string='套用特例後 P', compute='_compute_priorities', store=True)
    manual_priority = fields.Selection(
        PRIORITY_SELECTION, string='人工調整 P', tracking=True,
        help='留空＝採用「套用特例後 P」。調得比它低（降級）時，調整原因必填。')
    downgrade_reason = fields.Text(
        string='調整原因', tracking=True,
        help='人工調整 P 時說明原因。往下調（降級）時必填；往上調可選填。')
    final_priority = fields.Selection(
        PRIORITY_SELECTION, string='最終 P', compute='_compute_priorities', store=True, tracking=True)
    graded_datetime = fields.Datetime(string='分級時間', readonly=True, copy=False)
    grade_guide_html = fields.Html(
        string='判定標準', compute='_compute_grade_guide_html', sanitize=False,
        help='S／U／P 判定標準參考表。P 的修復期限即時讀「處理時限設定」，改了天數這裡跟著變。')
    is_graded = fields.Boolean(string='已分級', compute='_compute_is_graded', store=True)
    ever_upgraded = fields.Boolean(
        string='曾升級改判', readonly=True, copy=False, tracking=True,
        help='分級後又往上改判過。試行期每月檢視一次，看初判準不準。')

    # ------------------------------------------------------------------
    # 關聯
    # ------------------------------------------------------------------
    ticket_ids = fields.One2many('construction.service.ticket', 'problem_id', string='關聯服務單')
    ticket_count = fields.Integer(string='服務單數', compute='_compute_reported_customers', store=True)
    reported_customer_count = fields.Integer(
        string='回報客戶數', compute='_compute_reported_customers', store=True,
        help='關聯服務單的相異客戶公司數（依名稱文字比對；沒填的不算）。純資訊，不影響等級。')

    # ------------------------------------------------------------------
    # 時限（全部以日期計算，不用工作行事曆）
    # 預定修復日 ＝ 計算基準日 ＋ 預期工作天數 ＋ 非工作日天數
    # ------------------------------------------------------------------
    start_date = fields.Date(
        string='起算日', compute='_compute_start_date', store=True,
        help='客戶告知我們的日期：關聯服務單中最早的回報時間。沒有關聯服務單時＝問題單建立日。')
    base_date = fields.Date(
        string='計算基準日', tracking=True, copy=False,
        help='初次分級時＝起算日；改判時＝改判日。')
    base_date_label = fields.Char(string='計算基準日（星期）', compute='_compute_base_date_label')
    expected_work_days = fields.Integer(
        string='預期工作天數', tracking=True, copy=False,
        help='分級／改判時依最終 P 從處理時限設定帶入，可調整。0＝不設天數（P3、P4）。')
    non_working_days = fields.Integer(
        string='非工作日天數', tracking=True, copy=False,
        help='手動輸入：從計算基準日的「隔天」數到預定修復日為止的週末與國定假日。'
             '基準日當天不算。例：週六回報、P1（2 天）→ 日✗ 一① 二② → 填 1，預定修復日＝週二。')
    planned_fix_date = fields.Date(
        string='預定修復日', compute='_compute_planned_fix_date', store=True, tracking=True)
    non_working_to_confirm = fields.Boolean(
        string='非工作日待確認', readonly=True, copy=False,
        help='分級或等級變更後設起來。重新輸入非工作日天數、或按「確認非工作日天數」後清除。')
    fix_done_date = fields.Date(string='修復完成日', tracking=True, copy=False)
    total_days = fields.Integer(
        string='總處理天數', compute='_compute_total_days', store=True, aggregator='avg',
        help='修復完成日 − 起算日（日曆天）。這才是「客戶等了多久」；對外報告服務水準用這個，不用逾時率。')
    is_overdue = fields.Boolean(
        string='逾時', compute='_compute_is_overdue', search='_search_is_overdue',
        help='只代表沒達到內部工作目標（預定修復日），不代表客戶等太久。')

    # ------------------------------------------------------------------
    # 回應／暫行措施：只記錄，不判逾時
    # ------------------------------------------------------------------
    response_datetime = fields.Datetime(string='回應完成時間', tracking=True, copy=False)
    temporary_measure = fields.Text(
        string='暫行措施內容', copy=False,
        help='做了什麼、留下的痕跡放哪裡（沒有痕跡視同未做）：公告→訊息連結＋發送時間＋收件對象；'
             '停用功能→截圖；人工提供正確數字→那份檔案。痕跡請附在下方留言。')
    temporary_datetime = fields.Datetime(string='暫行措施執行時間', tracking=True, copy=False)
    temporary_user_id = fields.Many2one('res.users', string='暫行措施執行人', copy=False)

    # ------------------------------------------------------------------
    # 對客戶的通知（第十節）：凡 P1 一律通知事實與影響範圍，未記錄不得結案
    # ------------------------------------------------------------------
    customer_notice_datetime = fields.Datetime(string='通知客戶時間', tracking=True, copy=False)
    customer_notice_content = fields.Text(
        string='通知內容', copy=False,
        help='告訴客戶什麼事實、影響範圍（哪個功能、哪些工程案件、什麼期間）、客戶該怎麼做。'
             '等級代號不對客戶公布，但後果要說。')

    # ------------------------------------------------------------------
    # 等待客戶（第九節）
    # ------------------------------------------------------------------
    ever_waited_customer = fields.Boolean(
        string='曾等客戶', readonly=True, copy=False, tracking=True,
        help='有關聯服務單進入過「待客戶補件」時自動勾上，不能取消。'
             '統計總處理天數時剔除這張單（等客戶補資料的時間不算我們的）。')

    # ------------------------------------------------------------------
    # 修復驗證與結案（第九節、第十四節）
    # 三件對照：P1 一律要前兩件；「客戶未回覆」或「沒有關聯服務單」的 P1／P2 三件都要
    # ------------------------------------------------------------------
    evidence_before_ids = fields.Many2many(
        'ir.attachment', 'construction_problem_evidence_before_rel', 'problem_id', 'attachment_id',
        string='修復前跑出的失敗', copy=False,
        help='修復前的版本跑出來是失敗的那段原始輸出（截圖或文字檔）。'
             '沒有這一件，「可重跑的驗證」可以是一段不管有沒有修好都印通過的腳本。')
    evidence_after_ids = fields.Many2many(
        'ir.attachment', 'construction_problem_evidence_after_rel', 'problem_id', 'attachment_id',
        string='修復後通過', copy=False)
    evidence_prod_ids = fields.Many2many(
        'ir.attachment', 'construction_problem_evidence_prod_rel', 'problem_id', 'attachment_id',
        string='正式站實測紀錄', copy=False)
    close_type = fields.Selection(
        CLOSE_TYPE_SELECTION, string='結案方式', readonly=True, copy=False, tracking=True,
        help='按「結案」時依條件自動判定。')
    wont_fix_reason = fields.Selection(
        WONT_FIX_REASON_SELECTION, string='不處理原因', readonly=True, copy=False, tracking=True)
    wont_fix_note = fields.Text(string='不處理說明', readonly=True, copy=False)
    duplicate_of_id = fields.Many2one(
        'construction.problem', string='重複於', readonly=True, copy=False, tracking=True)

    # ------------------------------------------------------------------
    # 資安事件（第十一節）：時限一律用實際經過的時間
    # ------------------------------------------------------------------
    sec_discovered_datetime = fields.Datetime(string='發現時間', tracking=True, copy=False)
    sec_contained_datetime = fields.Datetime(
        string='封鎖完成時間', tracking=True, copy=False,
        help='目標：發現後 1 小時內。撤銷憑證、停用被盜帳號、改密碼、封鎖來源。')
    sec_contained_by = fields.Char(
        string='封鎖負責人', tracking=True, copy=False, help='寫人名，不寫角色。')
    sec_pii_leak = fields.Selection(
        PII_LEAK_SELECTION, string='個資外洩判定', tracking=True, copy=False,
        help='目標：發現後 4 小時內。「無法判定」視同「有」。')
    sec_pii_judged_datetime = fields.Datetime(string='判定時間', tracking=True, copy=False)
    sec_scope_estimate = fields.Text(
        string='受影響資料類別與筆數估算', copy=False,
        help='目標：發現後 24 小時內。估不出來要寫原因。')
    sec_scope_datetime = fields.Datetime(string='估算完成時間', tracking=True, copy=False)
    sec_legal_assessment = fields.Text(
        string='法定通知評估', copy=False, help='評估結果與法律意見來源（判定為有／無法判定時必填）。')
    sec_notify_decision = fields.Selection(
        NOTIFY_DECISION_SELECTION, string='是否通知當事人', tracking=True, copy=False)
    sec_not_notify_reason = fields.Text(
        string='不通知的理由', copy=False, help='事後最會被檢視的就是這一格。')
    sec_contain_hours = fields.Float(string='封鎖耗時（小時）', compute='_compute_sec_hours')
    sec_pii_hours = fields.Float(string='判定耗時（小時）', compute='_compute_sec_hours')
    sec_scope_hours = fields.Float(string='估算耗時（小時）', compute='_compute_sec_hours')

    # ------------------------------------------------------------------
    # 資料修正（S1 資料錯誤的第二個交付物，最容易漏掉）
    # ------------------------------------------------------------------
    data_fix_needed = fields.Boolean(string='需要修正既有資料', tracking=True)
    data_fix_scope = fields.Text(
        string='受影響範圍', help='哪些工程案件、哪幾筆、什麼期間。暫行措施階段就要先產出，不要等到盤修。')
    data_fix_method = fields.Text(string='盤點方式')
    data_fix_state = fields.Selection(DATA_FIX_STATE_SELECTION, string='修正狀態', tracking=True)
    data_fix_done_date = fields.Date(string='修正完成日', tracking=True)
    data_fix_backup_location = fields.Char(
        string='原始錯誤值備份位置', tracking=True,
        help='盤修前先備份原始錯誤值。程式一修、盤修一跑，原始值就消失，那是日後對帳或爭議時唯一的證據。')
    data_fix_compare_ids = fields.Many2many(
        'ir.attachment', 'construction_problem_data_fix_compare_rel', 'problem_id', 'attachment_id',
        string='原值／正確值／差額對照', copy=False)
    data_fix_script_ids = fields.Many2many(
        'ir.attachment', 'construction_problem_data_fix_script_rel', 'problem_id', 'attachment_id',
        string='重算腳本或 SQL', copy=False)
    data_fix_days = fields.Integer(
        string='資料盤修天數', copy=False,
        help='分級／改判時依最終 P 從處理時限設定帶入（快照）。0＝不設期限。')
    data_fix_planned_date = fields.Date(
        string='盤修預定日', compute='_compute_data_fix_planned_date', store=True,
        help='修復完成日＋資料盤修天數（日曆天）。盤修要在程式修好上線之後做，所以從修復完成日起算。')
    data_fix_overdue = fields.Boolean(string='盤修逾時', compute='_compute_data_fix_overdue')

    # ------------------------------------------------------------------
    # 已知錯誤
    # ------------------------------------------------------------------
    is_known_error = fields.Boolean(string='已知錯誤', tracking=True)
    known_error_reply = fields.Text(string='客服回覆參考')

    # ==================================================================
    # compute
    # ==================================================================
    @api.depends('severity', 'urgency', 'special_external_doc', 'special_security',
                 'special_repeat', 'manual_priority')
    def _compute_priorities(self):
        for rec in self:
            matrix_p = P_MATRIX.get((rec.severity, rec.urgency), False)
            up_p = upgraded_priority(matrix_p, rec.special_external_doc,
                                     rec.special_security, rec.special_repeat)
            rec.matrix_priority = matrix_p
            rec.upgraded_priority = up_p
            # 人工調整只在已有判定結果時生效（S、U 沒判完就沒有 P）
            rec.final_priority = (rec.manual_priority or up_p) if up_p else False

    @api.depends('description')
    def _compute_description_summary(self):
        from odoo.tools import html2plaintext
        for rec in self:
            text = ' '.join(html2plaintext(rec.description or '').split())
            rec.description_summary = text[:120] + ('…' if len(text) > 120 else '')

    @api.depends('name', 'title')
    def _compute_display_name(self):
        # 下拉選單與清單顯示「單號 標題」：只看單號，客服不可能知道是哪個問題
        for rec in self:
            rec.display_name = ('%s %s' % (rec.name or '', rec.title or '')).strip()

    def _compute_grade_guide_html(self):
        html = self._grade_guide_html()
        for rec in self:
            rec.grade_guide_html = html

    @api.model
    def _grade_guide_html(self):
        """分級標準 v0.2 的 S 表、U 表、P 表與 P 的意義（修復期限讀處理時限設定）。"""
        from markupsafe import Markup, escape
        slas = {s.priority: s for s in self.env['construction.problem.sla'].sudo().search([])}
        th = 'style="padding:4px 8px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;white-space:nowrap"'
        td = 'style="padding:4px 8px;border:1px solid #d0d7de;vertical-align:top"'

        def table(head, rows):
            out = '<table style="border-collapse:collapse;margin:4px 0 12px 0;font-size:0.9em">'
            out += '<tr>' + ''.join('<th %s>%s</th>' % (th, escape(h)) for h in head) + '</tr>'
            for r in rows:
                out += '<tr>' + ''.join('<td %s>%s</td>' % (td, escape(c)) for c in r) + '</tr>'
            return out + '</table>'

        s_rows = [
            ('S1 致命', '錯的值已寫進資料庫（算錯、寫錯、寫到別的工程）或資料遺失；系統無法登入或全面停擺；'
                       '安全告警類功能應發而未發（例：水位告警沒送出）；有資安疑慮。'
                       '畫面沒報錯但金額／數量已存錯，也是 S1'),
            ('S2 嚴重', '核心功能無法完成作業，且沒有替代做法（核心功能：登入、進度表、施工日誌、通報單、'
                       '契約工項與契約變更、估驗計價、自主檢查與缺失改善、檔案上傳下載、水位監測與告警；'
                       '清單外的功能若會卡住清單內的作業，也算 S2）'),
            ('S3 中等', '功能異常或結果不正確，但有替代做法，或只影響部分使用者；'
                       '或只是畫面、圖表、匯出檔錯，而資料庫裡的值是對的'),
            ('S4 輕微', '不影響功能與資料正確性：錯字、跑版、操作不便'),
        ]
        u_rows = [
            ('U1 立即', '現場作業當下中斷無法繼續；或 3 個工作天內有外部期限（送件、請款、驗收）'),
            ('U2 一般', '影響效率或正確性，但可用替代方式撐過；外部期限在 2 週內'),
            ('U3 可延後', '不影響目前作業，且沒有明確期限'),
        ]
        p_matrix = [(s, *[P_MATRIX[(s.lower(), u)].upper() for u in ('u1', 'u2', 'u3')])
                    for s in ('S1', 'S2', 'S3', 'S4')]
        p_rows = []
        for p in ('p1', 'p2', 'p3', 'p4'):
            level, deploy, extra = PRIORITY_MEANING[p]
            sla = slas.get(p)
            p_rows.append((p.upper() + ' ' + level,
                           sla.fix_limit_note if sla else '',
                           (sla.response_target or '') if sla else '',
                           (sla.temporary_target or '—') if sla else '',
                           deploy + ('；' + extra if extra else '')))
        body = (
            '<div style="font-size:0.9em;color:#57606a;margin-bottom:6px">'
            '判定順序：先判 S（由上往下，第一個符合的就是）→ 再判 U → 查 P 表 → 套用特例。'
            '<b>判斷不確定時取較高等級。</b></div>'
            '<b>S 嚴重程度</b>' + table(('等級', '判斷條件'), s_rows) +
            '<b>U 急迫性</b>' + table(('等級', '判斷條件'), u_rows) +
            '<b>P 表（S × U）</b>' + table(('', 'U1 立即', 'U2 一般', 'U3 可延後'), p_matrix) +
            '<b>P 代表的層級</b>（人工調整 P 時的依據）' +
            table(('等級', '修復期限', '回應目標', '暫行措施', '部署方式'), p_rows) +
            '<div style="font-size:0.9em;color:#57606a">特例：錯誤已流入對外文件、資安事件 → 直接 P1；'
            '二次回報（前次未修好）→ 升一級。「影響多個客戶／多個工程案件」不升級（同一套程式，幾乎每張單都成立）。</div>'
        )
        return Markup(body)

    @api.depends('graded_datetime')
    def _compute_is_graded(self):
        for rec in self:
            rec.is_graded = bool(rec.graded_datetime)

    @api.depends('ticket_ids', 'ticket_ids.customer_company')
    def _compute_reported_customers(self):
        for rec in self:
            tickets = rec.ticket_ids
            rec.ticket_count = len(tickets)
            # 客戶公司是文字欄位：去頭尾空白後比對，空白的不算
            rec.reported_customer_count = len({
                (t.customer_company or '').strip() for t in tickets
                if (t.customer_company or '').strip()})

    @api.depends('ticket_ids.report_datetime', 'create_date')
    def _compute_start_date(self):
        for rec in self:
            stamps = [t.report_datetime for t in rec.ticket_ids if t.report_datetime]
            first = min(stamps) if stamps else rec.create_date
            rec.start_date = (pytz.utc.localize(first).astimezone(LOCAL_TZ).date()
                              if first else False)

    @api.depends('base_date')
    def _compute_base_date_label(self):
        for rec in self:
            rec.base_date_label = ('%s（%s）' % (rec.base_date, WEEKDAYS[rec.base_date.weekday()])
                                   if rec.base_date else False)

    @api.depends('base_date', 'expected_work_days', 'non_working_days')
    def _compute_planned_fix_date(self):
        for rec in self:
            if rec.base_date and rec.expected_work_days > 0:
                rec.planned_fix_date = rec.base_date + timedelta(
                    days=rec.expected_work_days + max(rec.non_working_days, 0))
            else:
                rec.planned_fix_date = False

    @api.depends('start_date', 'fix_done_date')
    def _compute_total_days(self):
        for rec in self:
            rec.total_days = ((rec.fix_done_date - rec.start_date).days
                              if rec.start_date and rec.fix_done_date else 0)

    # 非 stored（「今天」每天在變），但要宣告 depends，否則同一交易內改了日期不會重算
    @api.depends('planned_fix_date', 'fix_done_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            planned = rec.planned_fix_date
            if not planned:
                rec.is_overdue = False
            elif rec.fix_done_date:
                rec.is_overdue = rec.fix_done_date > planned
            else:
                rec.is_overdue = today > planned

    @api.depends('sec_discovered_datetime', 'sec_contained_datetime',
                 'sec_pii_judged_datetime', 'sec_scope_datetime')
    def _compute_sec_hours(self):
        for rec in self:
            start = rec.sec_discovered_datetime
            rec.sec_contain_hours = hours_between(start, rec.sec_contained_datetime)
            rec.sec_pii_hours = hours_between(start, rec.sec_pii_judged_datetime)
            rec.sec_scope_hours = hours_between(start, rec.sec_scope_datetime)

    @api.depends('data_fix_needed', 'fix_done_date', 'data_fix_days')
    def _compute_data_fix_planned_date(self):
        for rec in self:
            if rec.data_fix_needed and rec.fix_done_date and rec.data_fix_days > 0:
                rec.data_fix_planned_date = rec.fix_done_date + timedelta(days=rec.data_fix_days)
            else:
                rec.data_fix_planned_date = False

    @api.depends('data_fix_planned_date', 'data_fix_done_date')
    def _compute_data_fix_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            planned = rec.data_fix_planned_date
            if not planned:
                rec.data_fix_overdue = False
            elif rec.data_fix_done_date:
                rec.data_fix_overdue = rec.data_fix_done_date > planned
            else:
                rec.data_fix_overdue = today > planned

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('「逾時」只支援等於／不等於 是或否。'))
        today = fields.Date.context_today(self)
        self.env['construction.problem'].flush_model(['planned_fix_date', 'fix_done_date'])
        # 兩個日期欄位互相比較，domain 表達不了，用 SQL 找出逾時的 id
        self.env.cr.execute("""
            SELECT id FROM construction_problem
             WHERE planned_fix_date IS NOT NULL
               AND ((fix_done_date IS NULL AND planned_fix_date < %s)
                 OR (fix_done_date IS NOT NULL AND fix_done_date > planned_fix_date))
        """, (today,))
        ids = [r[0] for r in self.env.cr.fetchall()]
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', ids)]

    # ==================================================================
    # constraints
    # ==================================================================
    @api.constrains('manual_priority', 'upgraded_priority', 'downgrade_reason')
    def _check_downgrade_reason(self):
        for rec in self:
            if rec.manual_priority and rec.upgraded_priority \
                    and p_rank(rec.manual_priority) > p_rank(rec.upgraded_priority) \
                    and not (rec.downgrade_reason or '').strip():
                raise ValidationError(_(
                    '%(name)s：人工調整為 %(m)s，低於套用特例後的 %(u)s（降級），必須填寫調整原因。',
                    name=rec.name, m=rec.manual_priority.upper(), u=rec.upgraded_priority.upper()))

    @api.constrains('fix_done_date', 'start_date')
    def _check_fix_done_after_start(self):
        # 修復完成日早於起算日 → 總處理天數變負數，會把每月平均靜靜拉低
        for rec in self:
            if rec.fix_done_date and rec.start_date and rec.fix_done_date < rec.start_date:
                raise ValidationError(_(
                    '%(name)s：修復完成日（%(f)s）不能早於起算日（%(s)s，客戶告知我們的那天）。',
                    name=rec.name, f=rec.fix_done_date, s=rec.start_date))

    @api.constrains('expected_work_days', 'non_working_days')
    def _check_days(self):
        for rec in self:
            if rec.expected_work_days < 0 or rec.non_working_days < 0:
                raise ValidationError(_('天數不可為負數。'))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '新增') == '新增':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('construction.problem') or '新增'
        records = super().create(vals_list)
        records._apply_first_grading()
        return records

    def write(self, vals):
        if not self.env.context.get('helpdesk_system_write'):
            # 這幾個欄位只由系統流程寫入（結案判定、不處理對話框、服務單進入待客戶補件）
            locked = [f for f in SYSTEM_FIELDS if f in vals]
            if locked:
                raise UserError(_('%s 由系統依流程自動填寫，不能手動修改。',
                                  '、'.join(self._fields[f].string for f in locked)))
        if not self.env.context.get('helpdesk_regrade'):
            touched = [f for f in GRADE_FIELDS if f in vals]
            graded = self.filtered('graded_datetime')
            if touched and graded:
                raise UserError(_(
                    '%s 已分級，等級相關欄位請用「變更等級」修改（需填改判原因）。',
                    '、'.join(graded.mapped('name'))))
        if 'non_working_days' in vals and 'non_working_to_confirm' not in vals:
            # 客服重新輸入了非工作日天數 → 視為已確認
            vals = dict(vals, non_working_to_confirm=False)
        res = super().write(vals)
        if not self.env.context.get('helpdesk_regrade'):
            self._apply_first_grading()
        return res

    def _apply_first_grading(self):
        """初次分級：最終 P 第一次出現時，記下分級時間並依 P 算時限（快照）。"""
        Sla = self.env['construction.problem.sla']
        for rec in self.filtered(lambda r: r.final_priority and not r.graded_datetime):
            vals = {
                'graded_datetime': fields.Datetime.now(),
                'base_date': rec.start_date,
                'expected_work_days': Sla.get_default_fix_days(rec.final_priority),
                'data_fix_days': Sla.get_data_fix_days(rec.final_priority),
            }
            if vals['expected_work_days']:
                vals['non_working_to_confirm'] = True
            if rec.state == 'pending_grade':
                vals['state'] = 'processing'
            rec.with_context(helpdesk_regrade=True).write(vals)

    # ==================================================================
    # 動作
    # ==================================================================
    def action_confirm_non_working_days(self):
        self.write({'non_working_to_confirm': False})
        return True

    def action_open_regrade(self):
        self.ensure_one()
        if not self.graded_datetime:
            raise UserError(_('尚未分級。請先在表單上判定 S 與 U。'))
        if self.state in CLOSED_STATES:
            # 已結束的單改判會重設計算基準日與預定修復日，把已經定案的時限紀錄改掉
            raise UserError(_('%s 已結案或不處理，不能變更等級。要改判請先「重新開啟」。', self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('變更等級'),
            'res_model': 'construction.problem.regrade.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_problem_id': self.id},
        }

    def _check_state_from(self, allowed):
        for rec in self:
            if rec.state not in allowed:
                raise UserError(_('%s 目前狀態不能執行這個動作。', rec.name))

    def action_to_deploy(self):
        self._check_state_from(('processing',))
        self.write({'state': 'pending_deploy'})
        return True

    def action_to_verify(self):
        """已部署到客戶站台。修復完成日＝部署這天（資料盤修的期限從這天起算）。"""
        self._check_state_from(('pending_deploy',))
        for rec in self:
            vals = {'state': 'pending_verify'}
            if not rec.fix_done_date:
                vals['fix_done_date'] = fields.Date.context_today(rec)
            rec.write(vals)
        return True

    def action_back_to_processing(self):
        self._check_state_from(('pending_deploy', 'pending_verify'))
        self.write({'state': 'processing'})
        return True

    # ------------------------------------------------------------------
    # 結案（分級標準 v0.3 第九節）
    # ------------------------------------------------------------------
    def _active_tickets(self):
        """參與結案判定的關聯服務單（取消的不算）。"""
        self.ensure_one()
        return self.ticket_ids.filtered(lambda t: t.state in TICKET_ACTIVE_STATES + ('done',))

    def _missing_evidence(self, need_prod):
        self.ensure_one()
        missing = []
        if not self.evidence_before_ids:
            missing.append(self._fields['evidence_before_ids'].string)
        if not self.evidence_after_ids:
            missing.append(self._fields['evidence_after_ids'].string)
        if need_prod and not self.evidence_prod_ids:
            missing.append(self._fields['evidence_prod_ids'].string)
        return missing

    def _check_close_prerequisites(self):
        """與結案方式無關、一定要先完成的事。回傳錯誤訊息清單。"""
        self.ensure_one()
        errors = []
        if self.data_fix_needed:
            if self.data_fix_state != 'done':
                errors.append(_('資料修正狀態還不是「已完成」（程式修好之後，既有的錯誤數值不會自動更正）。'))
            missing = []
            if not (self.data_fix_backup_location or '').strip():
                missing.append(self._fields['data_fix_backup_location'].string)
            if not (self.data_fix_scope or '').strip():
                missing.append(self._fields['data_fix_scope'].string)
            if not self.data_fix_compare_ids:
                missing.append(self._fields['data_fix_compare_ids'].string)
            if not self.data_fix_script_ids:
                missing.append(self._fields['data_fix_script_ids'].string)
            if missing:
                errors.append(_('資料修正缺少：%s。', '、'.join(missing)))
        if self.final_priority == 'p1':
            if not self.customer_notice_datetime or not (self.customer_notice_content or '').strip():
                errors.append(_('P1 一律要通知客戶：請填寫「通知客戶時間」與「通知內容」。'))
            missing = self._missing_evidence(need_prod=False)
            if missing:
                errors.append(_('P1 的修正必須附上可重跑的驗證，缺少：%s。', '、'.join(missing)))
        if self.special_security:
            errors += self._security_missing()
        return errors

    def _security_missing(self):
        self.ensure_one()
        missing = [self._fields[f].string for f in (
            'sec_discovered_datetime', 'sec_contained_datetime', 'sec_contained_by',
            'sec_pii_leak', 'sec_pii_judged_datetime', 'sec_scope_estimate', 'sec_scope_datetime')
            if not (self[f].strip() if isinstance(self[f], str) else self[f])]
        if self.sec_pii_leak in ('yes', 'unknown'):
            if not (self.sec_legal_assessment or '').strip():
                missing.append(self._fields['sec_legal_assessment'].string)
            if not self.sec_notify_decision:
                missing.append(self._fields['sec_notify_decision'].string)
            elif self.sec_notify_decision == 'not_notify' and not (self.sec_not_notify_reason or '').strip():
                missing.append(self._fields['sec_not_notify_reason'].string)
        return [_('資安事件檢核表未填齊：%s。', '、'.join(missing))] if missing else []

    def _ticket_wait_note(self, ticket, days):
        """結案被擋時，說明這張服務單還差什麼：在等的就寫哪天滿期（客服不用自己推算），沒在等的寫目前狀態。"""
        if ticket.state == 'waiting_verify' and ticket.waiting_verify_datetime:
            # 用本系統固定時區（同起算日）：使用者沒設時區時 context_timestamp 會退回 UTC
            due = pytz.utc.localize(ticket.waiting_verify_datetime + timedelta(days=days)).astimezone(LOCAL_TZ)
            return _('%(t)s（%(due)s 滿 %(d)s 天）', t=ticket.name, due=due.strftime('%Y-%m-%d %H:%M'), d=days)
        state = dict(ticket._fields['state'].selection).get(ticket.state)
        return _('%(t)s（目前「%(s)s」，尚未請客戶驗證）', t=ticket.name, s=state)

    def _determine_close_type(self):
        """依結案條件判定結案方式；不符合任何一條時丟出說明原因的錯誤。

        回傳 (close_type, 要一併以「逾期未回覆」結案的服務單)。
        """
        self.ensure_one()
        tickets = self._active_tickets()
        p = self.final_priority
        high = p in ('p1', 'p2')
        if tickets.filtered('customer_confirmed'):
            return 'confirmed', tickets.browse()
        if not tickets:
            if high:
                missing = self._missing_evidence(need_prod=True)
                if missing:
                    raise UserError(_(
                        '%(name)s 沒有關聯服務單（沒有客戶可以確認），%(p)s 要附齊三件修復對照才能結案，缺少：%(m)s。',
                        name=self.name, p=p.upper(), m='、'.join(missing)))
            return 'internal', tickets.browse()
        days = self.env['construction.problem.sla'].get_customer_wait_days(p)
        if high:
            limit = fields.Datetime.now() - timedelta(days=days)
            waiting = tickets.filtered(lambda t: t.state == 'waiting_verify')
            not_ready = tickets - waiting.filtered(
                lambda t: t.waiting_verify_datetime and t.waiting_verify_datetime <= limit)
            if not_ready:
                raise UserError(_(
                    '%(name)s 還不能結案：沒有任何一張關聯服務單經客戶確認。\n'
                    '%(p)s 要等全部關聯服務單都在「待客戶驗證」滿 %(d)s 天、而且沒有人回報「仍有問題」，'
                    '才能附對照結案。尚未符合的服務單：\n%(t)s',
                    name=self.name, p=p.upper(), d=days,
                    t='\n'.join('・' + self._ticket_wait_note(t, days) for t in not_ready)))
            missing = self._missing_evidence(need_prod=True)
            if missing:
                raise UserError(_(
                    '%(name)s 客戶未回覆，要附齊三件修復對照才能結案，缺少：%(m)s。',
                    name=self.name, m='、'.join(missing)))
            return 'no_reply_evidence', waiting
        if tickets.filtered('overdue_closed'):
            return 'no_reply_overdue', tickets.browse()
        raise UserError(_(
            '%(name)s 還不能結案：至少要有一張關聯服務單經客戶確認，'
            '或客戶在「待客戶驗證」滿 %(d)s 天未回覆（系統每天自動處理）。',
            name=self.name, d=days))

    def action_done(self):
        self._check_state_from(('processing', 'pending_deploy', 'pending_verify'))
        for rec in self:
            errors = rec._check_close_prerequisites()
            if errors:
                raise UserError(_('%s 還不能結案：\n', rec.name) + '\n'.join('・' + e for e in errors))
            close_type, overdue_tickets = rec._determine_close_type()
            vals = {'state': 'done', 'close_type': close_type}
            if not rec.fix_done_date:
                vals['fix_done_date'] = fields.Date.context_today(rec)
            rec.with_context(helpdesk_system_write=True).write(vals)
            # P1／P2 客戶未回覆、附對照結案：那些一直沒回的服務單一併結案
            overdue_tickets._close_no_reply()
        # 其他關聯服務單不動：各自照自己的規則走（確認、逾期結案、仍有問題）
        return True

    def action_wont_fix(self):
        self._check_state_from(('pending_grade', 'processing', 'pending_deploy', 'pending_verify'))
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('不處理'),
            'res_model': 'construction.problem.wontfix.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_problem_id': self.id},
        }

    def _set_wont_fix(self, reason, note, duplicate_of=False):
        """「不處理」對話框呼叫。P1 不能選無法重現、接受風險。"""
        self.ensure_one()
        self._check_state_from(('pending_grade', 'processing', 'pending_deploy', 'pending_verify'))
        if not reason:
            raise UserError(_('請選擇不處理的原因。'))
        if not (note or '').strip():
            raise UserError(_('請填寫說明。'))
        if self.final_priority == 'p1' and reason in WONT_FIX_NOT_FOR_P1:
            raise UserError(_('P1 不能以「%s」結束。', dict(WONT_FIX_REASON_SELECTION)[reason]))
        if reason == 'duplicate':
            if not duplicate_of:
                raise UserError(_('請選擇重複於哪一張問題單。'))
            if duplicate_of == self:
                raise UserError(_('不能重複於自己。'))
            if duplicate_of.state in CLOSED_STATES:
                raise UserError(_('%s 已經結案，不能併入。請先重新開啟那張，或選另一張。', duplicate_of.name))
        self.with_context(helpdesk_system_write=True).write({
            'state': 'wont_fix',
            'wont_fix_reason': reason,
            'wont_fix_note': note,
            'duplicate_of_id': duplicate_of.id if reason == 'duplicate' else False,
        })
        if reason == 'duplicate':
            tickets = self.ticket_ids
            if tickets:
                # 關聯服務單一起搬過去，並把「曾等客戶」帶過去（等補件的事實不會因為併單消失）
                tickets.write({'problem_id': duplicate_of.id})
                if self.ever_waited_customer and not duplicate_of.ever_waited_customer:
                    duplicate_of.with_context(helpdesk_system_write=True).write({'ever_waited_customer': True})
            duplicate_of.message_post(
                body=_('%(me)s 判定與本單重複並已併入，關聯服務單移過來：%(t)s',
                       me=self.display_name, t='、'.join(tickets.mapped('name')) or '（無）'),
                subtype_xmlid='mail.mt_note')
        return True

    def action_reopen(self):
        self._check_state_from(CLOSED_STATES)
        for rec in self:
            # 重開＝其實沒修好，清掉修復完成日與結案判定（舊值留在修改紀錄裡）
            rec.with_context(helpdesk_system_write=True).write({
                'state': 'processing' if rec.graded_datetime else 'pending_grade',
                'fix_done_date': False,
                'close_type': False,
                'wont_fix_reason': False,
                'wont_fix_note': False,
                'duplicate_of_id': False,
            })
        return True

    def _mark_waited_customer(self):
        """關聯服務單進入「待客戶補件」時呼叫。只會勾上、不會取消。"""
        todo = self.filtered(lambda r: not r.ever_waited_customer)
        if todo:
            todo.with_context(helpdesk_system_write=True).write({'ever_waited_customer': True})

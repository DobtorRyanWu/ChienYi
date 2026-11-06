# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

from .defect_constants import (
    CHECK_TYPE_PREFIX,
    CHECK_TYPE_TO_CATEGORIES,
    CHECK_TYPE_DEFAULT_CATEGORY,
)
from odoo.addons.construction_supervision_base.utils.local_date import local_today

# 「待改」以外的狀態：已驗證、結案（公司儀表板合約 §5.2 dash_open_defect_count；草稿與監造內部視角都算待改）
DEFECT_DONE_STATES = ('verified', 'closed')
# 不算逾期的狀態：已改善之後（與 _compute_overdue 一致）
DEFECT_NOT_OVERDUE_STATES = ('improved', 'verified', 'closed')


class ConstructionDailyDefectMixin(models.AbstractModel):
    """
    每日流水編號缺失改善共用 Mixin

    設計說明：
    - 抽取 general.defect.improvement 與 reservation.defect.improvement 約 90% 的共用邏輯
      （欄位群、逾期計算、每日流水編號、8 個狀態機 action、缺失類別分身欄位、SQL 約束）。
    - 純重構：欄位名/型別與原具體表完全一致（Odoo 升級視為同欄，不掉資料）。
    - 兩張具體表僅保留自己獨有的關聯欄位與差異行為：
        * general  = project_id(direct)/task_id/self_inspection_id/ncr_id/罰款來源/照片…
        * reservation = slip_id/project_id(related)/前綴設定/照片…
    - 具體表所需的 `project_id` 由各自定義（general 為 direct、reservation 為 related）；
      本 Mixin 內所有引用 `project_id` 之處，於具體表建立時解析，皆可運作。
    - 編號欄位統一為 `defect_no`（canonical）；具體表以 `name`(general)/`record_no`(reservation)
      作為 `related='defect_no'` 別名並保留欄位，既有 view 與 FK 不斷。
    """
    _name = 'construction.daily.defect.mixin'
    _description = '每日流水編號缺失改善共用 Mixin'

    # === 缺失編號（canonical；具體表以 name/record_no 作 related 別名）===
    defect_no = fields.Char(
        string='缺失編號',
        copy=False,
        readonly=True,
        compute='_compute_defect_no',
        store=True,
        index=True)

    # 註：company_id 為 related='project_id.company_id'，而 project_id 由各具體表定義
    # （general 為 direct、reservation 為 related），AbstractModel 本身無 project_id，
    # 故 company_id 保留於各具體表，不上移至本 Mixin。

    # === 記錄類型標識 ===
    record_type = fields.Selection([
        ('supervision', '監造'),
        ('contractor', '營造'),
    ], string='記錄類型', required=True, default='supervision',
       tracking=True, index=True,
       help='標識此記錄屬於監造視角或營造視角')

    sequence_number = fields.Integer(
        string='當日序號',
        required=True,
        default=1,
        help='當天同工程同類型的序號，可手動修改')

    # === 檢查類型 ===
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety_env', '安衛及環境清潔檢查'),
    ], string='檢查類型', required=True, default='construction', tracking=True)

    # === 缺失分類 ===
    defect_category = fields.Selection([
        ('material', '材料品質'),
        ('workmanship', '施工品質'),
        ('dimension', '尺寸偏差'),
        ('safety', '安全衛生'),
        ('environment', '環境清潔'),
        ('document', '文件缺漏'),
        ('other', '其他'),
    ], string='缺失類別', required=True, default='workmanship', tracking=True)

    # 缺失類別「分身」欄位：依檢查類型只顯示對應子集（畫面用，真值仍寫回 defect_category）
    defect_category_construction = fields.Selection(
        selection=[
            ('material', '材料品質'),
            ('workmanship', '施工品質'),
            ('dimension', '尺寸偏差'),
            ('document', '文件缺漏'),
            ('other', '其他'),
        ],
        string='缺失類別',
        compute='_compute_defect_category_proxy',
        inverse='_inverse_defect_category_proxy')
    defect_category_safety = fields.Selection(
        selection=[
            ('safety', '安全衛生'),
            ('environment', '環境清潔'),
        ],
        string='缺失類別',
        compute='_compute_defect_category_proxy',
        inverse='_inverse_defect_category_proxy')

    severity = fields.Selection([
        ('minor', '輕微'),
        ('moderate', '中等'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ], string='嚴重程度', required=True, default='minor', tracking=True)

    responsible_party = fields.Selection([
        ('contractor', '承包商'),
        ('subcontractor', '分包商'),
        ('supplier', '供應商'),
        ('design', '設計單位'),
        ('owner', '業主'),
        ('other', '其他'),
    ], string='責任歸屬', tracking=True)

    improvement_progress = fields.Integer(
        string='改善進度 (%)',
        default=0)

    # === 單位資訊 ===
    discovery_unit = fields.Char(
        string='發現單位',
        help='發現缺失的單位名稱')

    discovery_user_id = fields.Many2one(
        'res.users',
        string='發現人',
        default=lambda self: self.env.uid,
        tracking=True)

    improvement_unit = fields.Char(
        string='執行改善單位',
        help='負責改善的單位名稱')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True,
        help='負責執行改善的人員')

    # === 日期 ===
    found_date = fields.Date(
        string='發現日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    notification_date = fields.Date(
        string='通知改善日期',
        default=fields.Date.today,
        tracking=True)

    deadline = fields.Date(
        string='改善期限',
        tracking=True)

    improvement_date = fields.Date(
        string='實際改善日期',
        tracking=True)

    closure_date = fields.Date(
        string='結案日期',
        tracking=True)

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue',
        store=True)

    # === 罰款資訊 ===
    is_fined = fields.Boolean(
        string='是否已罰款',
        default=False,
        tracking=True,
        help='標記此缺失是否已進行罰款處理')

    fine_amount = fields.Monetary(
        string='罰款金額',
        currency_field='currency_id',
        help='罰款金額')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        default=lambda self: self.env.company.currency_id)

    fine_note = fields.Text(
        string='罰款說明',
        help='罰款原因及相關說明')

    # === 缺失內容 ===
    defect_location = fields.Char(
        string='缺失位置',
        help='發生缺失的具體位置')

    defect_description = fields.Text(
        string='缺失具體情形',
        required=True,
        tracking=True)

    defect_cause = fields.Text(
        string='缺失發生原因',
        help='分析缺失發生的根本原因')

    # === 改善資訊 ===
    improvement_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    prevention_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

    improvement_result = fields.Text(
        string='改善結果說明',
        help='改善完成後的結果說明')

    # === 複查資訊 ===
    recheck_date = fields.Date(string='複查日期', tracking=True)

    recheck_result = fields.Selection([
        ('pass', '通過'),
        ('fail', '不通過'),
        ('pending', '待複查'),
    ], string='複查結果', tracking=True)

    recheck_note = fields.Text(string='複查說明')

    # === 缺失改善成果確認（2026-11-06）===
    # EAGLE errorRecord.result（0 符合要求／1 已矯正／2 未矯正／3 其他／4 逾時未矯正）：監造選的結果，列印照它勾。
    # 有填列印照它，沒填自動判斷（construction_template mappings/defect_improvement._outcome）。
    # 只代表「填的當下」：之後狀態一變就清掉（write），與狀態矛盾的組合不准存（_check_outcome_matches_state）。
    outcome_result = fields.Selection([
        ('qualified', '符合要求'),
        ('corrected', '已矯正'),
        ('uncorrected', '未矯正'),
        ('other', '其他'),
        ('timeout', '逾時未矯正'),
    ], string='成果確認', tracking=True, copy=False,
        help='印在「矯正與預防處理紀錄」的缺失改善成果確認。有填照這裡勾；沒填列印時自動判斷。'
             '「已矯正」表單上沒有格子，都不勾。缺失狀態改變時會自動清空。')

    # === 驗證資訊 ===
    verifier_id = fields.Many2one(
        'res.users',
        string='驗證人',
        tracking=True)

    verify_date = fields.Date(
        string='驗證日期')

    verify_result = fields.Selection([
        ('pass', '驗證通過'),
        ('fail', '驗證不通過'),
    ], string='驗證結果', tracking=True)

    verify_comment = fields.Text(
        string='驗證意見')

    # === 結案資訊 ===
    closer_id = fields.Many2one(
        'res.users',
        string='結案人',
        tracking=True)

    close_comment = fields.Text(
        string='結案說明')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('notified', '已通知'),
        ('improving', '改善中'),
        ('improved', '已改善'),
        ('verified', '已驗證'),
        ('closed', '結案'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # 前台流程狀態詞彙（general/reservation 就是 state 本身）。
    # 讓前台共用缺失模板的 workflow gating 用同一欄位，不必比對各模型不同的 state 值集。
    portal_workflow_state = fields.Char(
        string='前台流程狀態', compute='_compute_portal_workflow_state', store=False)

    @api.depends('state')
    def _compute_portal_workflow_state(self):
        for record in self:
            record.portal_workflow_state = record.state

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 來源追溯 ===
    source_description = fields.Char(
        string='來源登錄編號',
        index=True,
        help='自舊系統／彙總表匯入時的原始缺失單號（如 QA-001、Q01-1121007）。\n'
             '供後續補充改善明細比對回配，並保留舊系統編號可回查。')

    # === 逾期計算 ===
    @api.depends('deadline', 'state', 'closure_date')
    def _compute_overdue(self):
        # 台灣日期（fields.Date.today() 是 UTC 日期，台灣早上 8 點才翻轉；合約 §5.3）
        today = local_today()
        for record in self:
            if record.state in DEFECT_NOT_OVERDUE_STATES:
                # 已結案，不算逾期
                record.is_overdue = False
                record.overdue_days = 0
            elif record.deadline:
                if record.closure_date:
                    # 已結案，檢查是否逾期結案
                    record.is_overdue = record.closure_date > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (record.closure_date - record.deadline).days
                    else:
                        record.overdue_days = 0
                else:
                    # 未結案
                    record.is_overdue = today > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (today - record.deadline).days
                    else:
                        record.overdue_days = 0
            else:
                record.is_overdue = False
                record.overdue_days = 0

    # === 公司儀表板的條件（合約 §5.1、§5.2；計數與下鑽共用同一份）===
    @api.model
    def _dash_open_domain(self):
        """待改缺失：狀態不是已驗證、結案（含草稿、含監造內部視角 record_type=supervision）。"""
        return [('state', 'not in', DEFECT_DONE_STATES)]

    @api.model
    def _dash_overdue_domain(self):
        """逾期缺失：還沒改善完成、有期限、期限早於台灣的今天。

        不讀儲存的 is_overdue：它只在期限／狀態變動與每日排程時重算（見下方 _cron_check_overdue），
        排程跑之前會停在昨天的判斷。這裡用日期直接判斷，與 _compute_overdue 對「沒有結案日期」的未改善缺失結果相同。
        """
        return [
            ('state', 'not in', DEFECT_NOT_OVERDUE_STATES),
            ('deadline', '!=', False),
            ('deadline', '<', local_today()),
        ]

    # === 逾期排程（一般式/預約式共用）===
    # 上面的 is_overdue / overdue_days 是 store=True 的計算欄位，但 @api.depends 只有
    # deadline/state/closure_date，**不含「今天」** —— 期限過了不會自己翻成逾期，
    # 必須靠排程定期重算。後台的「一般式/預約式逾期缺失」選單 domain 都是
    # is_overdue = True，沒有排程等於那兩個選單永遠是空的。
    #
    # 這兩支原本各自寫在 general/reservation，且行為不一致：
    # reservation 的 `_cron_check_overdue` 名為檢查、實際只發通知，從不刷新 is_overdue。
    # 上收到 mixin 讓兩邊行為一致。

    @api.model
    def _cron_check_overdue(self):
        """每日刷新 is_overdue / overdue_days。"""
        stale = self.search([
            ('deadline', '!=', False),
            ('state', 'not in', ('improved', 'verified', 'closed')),
        ])
        if stale:
            # 通知 ORM「deadline 變了」→ 依賴它的 store 計算欄位排入重算佇列
            stale.modified(['deadline'])

    @api.model
    def _cron_send_overdue_notification(self):
        """對已逾期且未改善完成的缺失，通知負責人。"""
        overdue = self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ('improved', 'verified', 'closed')),
        ])
        for record in overdue:
            if not record.responsible_user_id:
                continue
            record.message_post(
                body=Markup('缺失 <b>%s</b> 已逾期 %s 天（期限：%s），請儘速完成改善。') % (
                    record.defect_no or record.id, record.overdue_days, record.deadline),
                partner_ids=record.responsible_user_id.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )

    # === 動作方法（6 個逐位相同）===
    # 「符合要求」只能配已驗證／結案；已驗證／結案不能配未矯正／逾時未矯正（2026-11-06 red-team F3：
    # 否則前台顯示改善中、紙上印合格）
    _OUTCOME_NEEDS_CLOSED = ('qualified',)
    _OUTCOME_NEEDS_OPEN = ('uncorrected', 'timeout')
    _OUTCOME_CLOSED_STATES = ('verified', 'closed')

    @api.constrains('outcome_result', 'state')
    def _check_outcome_matches_state(self):
        for rec in self:
            closed = rec.state in self._OUTCOME_CLOSED_STATES
            if rec.outcome_result in self._OUTCOME_NEEDS_CLOSED and not closed:
                raise ValidationError('成果確認「符合要求」只能用在已驗證或結案的缺失。')
            if rec.outcome_result in self._OUTCOME_NEEDS_OPEN and closed:
                raise ValidationError('已驗證或結案的缺失，成果確認不能是「未矯正」或「逾時未矯正」。')

    def write(self, vals):
        """狀態真的改變時清掉成果確認，改回自動判斷（2026-11-06 red-team F1／F2）。

        存的成果確認只代表填的當下（回填的 EAGLE 值、或監造手選）：重開／驗證退回的缺失照舊印
        「符合要求」、回填成「未矯正」的缺失在 Odoo 結案後照舊印「未矯正」，都是錯的。
        同一次 write 同時給了成果確認（例如回填）就照給的值。
        """
        if 'state' in vals and 'outcome_result' not in vals:
            stale = self.filtered(lambda r: r.outcome_result and r.state != vals['state'])
            if stale:
                super(ConstructionDailyDefectMixin, stale).write({'outcome_result': False})
        return super().write(vals)

    def action_notify(self):
        """通知改善"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以通知改善')
            if not record.deadline:
                raise ValidationError('請先設定改善期限')
            record.write({
                'state': 'notified',
                'notification_date': fields.Date.today(),
            })
            if record.responsible_user_id:
                partner = record.responsible_user_id.partner_id
                unit = record.improvement_unit or ''
                record.message_subscribe(partner_ids=partner.ids)
                record.message_post(
                    body=Markup(
                        '缺失 <b>%s</b> 已派發給您%s，請於 <b>%s</b> 前完成改善。<br/>缺失說明：%s'
                    ) % (
                        record.defect_no,
                        Markup('（執行改善單位：%s）') % unit if unit else '',
                        record.deadline,
                        record.defect_description or '（無）',
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_start_improvement(self):
        """開始改善"""
        for record in self:
            if record.state != 'notified':
                raise UserError('只有已通知狀態可以開始改善')
            record.state = 'improving'

    def action_complete_improvement(self):
        """完成改善"""
        for record in self:
            if record.state != 'improving':
                raise UserError('只有改善中狀態可以標記完成')
            if not record.improvement_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'improved',
                'improvement_date': fields.Date.today(),
            })
            if record.discovery_user_id:
                partner = record.discovery_user_id.partner_id
                record.message_post(
                    body=Markup('缺失 <b>%s</b> 已完成改善，請複查。') % record.defect_no,
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_verify_pass(self):
        """驗證通過"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            record.write({
                'state': 'verified',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'pass',
            })

    def action_verify_fail(self):
        """驗證不通過"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            vals = {
                'state': 'improving',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'fail',
            }
            # 手填過「複查結果：通過／待複查」又被驗證退回：以驗證結果為準，不然表單會照舊印
            # 「符合要求」或三格都不勾（construction_template 的 _outcome，2026-11-06）
            if record.recheck_result in ('pass', 'pending'):
                vals['recheck_result'] = False
            record.write(vals)

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'verified':
                raise UserError('只有已驗證狀態可以結案')
            record.write({
                'state': 'closed',
                'closer_id': self.env.uid,
                'closure_date': fields.Date.today(),
            })

    # === 動作方法（2 個行為不同，以 hook 參數化）===
    def _reopen_extra_vals(self):
        """重新開啟時額外重置的欄位（子類可覆寫）。預設不額外重置。"""
        return {}

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('verified', 'closed'):
                raise UserError('只有已驗證或結案狀態可以重新開啟')
            vals = {
                'state': 'improving',
                'closure_date': False,
                # 複查資訊一併清掉（2026-11-06）：殘留的「複查結果：通過」會讓重開的缺失在
                # 矯正與預防處理紀錄印成「符合要求」、附表12 印「改善完成」。預約式本來就清，
                # 一般式沒清——放在 mixin，兩邊同一份
                'recheck_date': False,
                'recheck_result': False,
                'recheck_note': False,
            }
            vals.update(record._reopen_extra_vals())
            record.write(vals)

    # 退回草稿允許的來源狀態與錯誤訊息（子類可覆寫）
    _reset_draft_source_states = ('notified',)
    _reset_draft_error = '只有已通知狀態可以退回草稿'

    def action_reset_draft(self):
        """退回草稿"""
        for record in self:
            if record.state not in self._reset_draft_source_states:
                raise UserError(self._reset_draft_error)
            record.state = 'draft'

    # === 序號即時計算 ===
    @api.onchange('project_id', 'found_date', 'check_type', 'record_type')
    def _onchange_sequence_fields(self):
        """工程、日期、類型變更時，即時計算下一個可用序號"""
        if not (self.project_id and self.found_date):
            return
        origin = self._origin
        # 編輯已存檔記錄時：只有分組(工程/日期/檢查類型/記錄類型)真的改變才重算；
        # 若切回原分組則保留原序號，避免無謂跳號
        if origin and origin.id:
            same_group = (
                origin.project_id.id == self.project_id.id
                and origin.found_date == self.found_date
                and origin.check_type == self.check_type
                and origin.record_type == self.record_type
            )
            if same_group:
                self.sequence_number = origin.sequence_number
                return
        self.sequence_number = self._get_daily_sequence(
            self.project_id.id,
            self.found_date,
            self.check_type or 'construction',
            self.record_type or 'supervision',
            # 排除自己，避免把自己算進去而跳號
            exclude_id=origin.id if origin else False,
        )

    def _get_daily_sequence(self, project_id, found_date, check_type, record_type, exclude_id=None):
        """計算當天同工程同類型的下一個序號"""
        # 確保同一 transaction 內剛建立的記錄已寫入 DB，避免查不到而重複序號
        self.flush_model()
        domain = [
            ('project_id', '=', project_id),
            ('found_date', '=', found_date),
            ('check_type', '=', check_type),
            ('record_type', '=', record_type),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))

        existing = self.search(domain, order='sequence_number desc', limit=1)
        return existing[0].sequence_number + 1 if existing else 1

    # === 編號生成輔助方法 ===
    def _get_minguo_date_string(self, date_obj):
        """將西元日期轉換為民國年格式字串 YYYMMDD"""
        if not date_obj:
            return ''
        minguo_year = date_obj.year - 1911
        return f"{minguo_year}{date_obj.month:02d}{date_obj.day:02d}"

    def _get_check_type_prefix(self, check_type):
        """取得檢查類型對應的首字（讀共用對應表）"""
        return CHECK_TYPE_PREFIX.get(check_type, '施')

    @api.depends('project_id', 'found_date', 'check_type', 'record_type', 'sequence_number')
    def _compute_defect_no(self):
        """自動生成缺失編號：編號前綴-檢查類型首字+民國年月日_序號"""
        for record in self:
            if not record.project_id or not record.found_date:
                record.defect_no = '/'
                continue

            # 從配置表查詢工程的前綴設定
            prefix_config = self.env['defect.improvement.prefix.config'].search([
                ('project_id', '=', record.project_id.id)
            ], limit=1)

            if not prefix_config:
                raise UserError(
                    f'工程「{record.project_id.name}」尚未設定缺失改善編號前綴。\n'
                    f'請至「品質管理 > 缺失改善 > 編號前綴設定」進行設定。'
                )

            # 根據記錄類型取得對應前綴
            if record.record_type == 'supervision':
                prefix = prefix_config.supervision_prefix
            else:
                prefix = prefix_config.contractor_prefix

            check_prefix = self._get_check_type_prefix(record.check_type)
            date_str = self._get_minguo_date_string(record.found_date)
            record.defect_no = f"{prefix}-{check_prefix}{date_str}_{record.sequence_number}"

    # === 缺失類別分身欄位：與真值 defect_category 同步 ===
    @api.depends('defect_category')
    def _compute_defect_category_proxy(self):
        """把真值 defect_category 映射到對應檢查類型的分身欄位"""
        cons = CHECK_TYPE_TO_CATEGORIES['construction']
        safe = CHECK_TYPE_TO_CATEGORIES['safety_env']
        for rec in self:
            rec.defect_category_construction = rec.defect_category if rec.defect_category in cons else False
            rec.defect_category_safety = rec.defect_category if rec.defect_category in safe else False

    def _inverse_defect_category_proxy(self):
        """使用者在分身欄位選的值寫回真值 defect_category"""
        for rec in self:
            if rec.check_type == 'safety_env' and rec.defect_category_safety:
                rec.defect_category = rec.defect_category_safety
            elif rec.check_type == 'construction' and rec.defect_category_construction:
                rec.defect_category = rec.defect_category_construction

    @api.onchange('check_type')
    def _onchange_check_type_reset_category(self):
        """切換檢查類型時，若目前缺失類別不合法則重設為該類型預設值"""
        allowed = CHECK_TYPE_TO_CATEGORIES.get(self.check_type, [])
        if self.defect_category not in allowed:
            self.defect_category = CHECK_TYPE_DEFAULT_CATEGORY.get(self.check_type, False)

    # === SQL 約束 ===
    _sql_constraints = [
        ('defect_no_unique', 'UNIQUE(defect_no)',
         '缺失編號必須唯一！'),
        ('unique_sequence_per_day',
         'UNIQUE(project_id, found_date, check_type, record_type, sequence_number)',
         '同一天同工程同類型的序號不能重複！'),
    ]

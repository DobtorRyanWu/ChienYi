# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ContractChangeOrder(models.Model):
    """
    契約變更單

    設計說明 (v5.2): 參考 OCA project_version 設計模式
    - 追蹤金額、數量、工期變更
    - 支援新增、修改、刪除工項
    - 累計計算當前契約狀態

    狀態流程:
    draft -> submitted -> reviewing -> approved -> applied
                                   -> rejected
    """
    _name = 'contract.change.order'
    _description = '契約變更單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, create_date desc'

    # === 基本資訊 ===
    name = fields.Char(
        string='變更編號',
        required=True,
        copy=False,
        readonly=True,
        default='/',
        tracking=True,
        help='系統自動編號')

    sequence = fields.Integer(
        string='序號',
        default=10,
        help='變更順序（Odoo 列表排序用，非「第幾次變更」）')

    change_no = fields.Integer(
        string='本專案第幾次變更',
        compute='_compute_change_no',
        store=True,
        help='此變更單在所屬工程中的變更次序（1-based，依建立先後）。'
             '「第N次契約變更」標示一律以此為準，不可用 sequence。')

    @api.depends('project_id', 'project_id.change_order_ids', 'create_date')
    def _compute_change_no(self):
        for order in self:
            if not order.project_id:
                order.change_no = 0
                continue
            siblings = order.project_id.change_order_ids.sorted(
                key=lambda o: (o.create_date or fields.Datetime.now(), o.id))
            try:
                order.change_no = list(siblings).index(order) + 1
            except ValueError:
                order.change_no = 0

    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        ondelete='cascade',
        tracking=True,
        domain="[('state', 'in', ['construction', 'completion', 'acceptance'])]",
        help='關聯的工程案件（透過「匯入工程案件」設定）')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        help='管理公司 (繼承自工程案件)')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='project_id.currency_id',
        store=True)

    # === 變更資訊 ===
    change_reason = fields.Selection([
        ('design', '設計變更'),
        ('site_condition', '現場條件變更'),
        ('owner_request', '業主需求'),
        ('regulation', '法規要求'),
        ('price_adjustment', '物價調整'),
        ('other', '其他'),
    ], string='變更原因',
       required=True,
       default='design',
       tracking=True)

    change_reason_detail = fields.Text(
        string='變更說明',
        tracking=True,
        help='詳細說明變更原因與內容')

    other_reason_detail = fields.Char(
        string='其他原因說明',
        tracking=True,
        help='當變更原因選擇「其他」時，請說明具體原因')

    change_date = fields.Date(
        string='變更日期',
        default=fields.Date.context_today,
        tracking=True)

    # === 原始契約資訊（= 頂層彙總項變更前金額加總，非快照）===
    original_contract_amount = fields.Monetary(
        string='變更前契約金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='執行變更前的契約金額（= 各頂層彙總項變更前金額加總）')

    # === 本次變更金額 ===
    change_amount = fields.Monetary(
        string='本次變更金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='本次變更增減金額 (正:增加, 負:減少) = 變更後 - 變更前')

    change_amount_rate = fields.Float(
        string='變更比率 (%)',
        compute='_compute_amount_totals',
        store=True,
        digits=(16, 4),
        help='變更金額佔原契約金額的百分比（小數，如 0.2567 = 25.67%）')

    # === 變更後金額 ===
    new_contract_amount = fields.Monetary(
        string='變更後契約金額',
        currency_field='currency_id',
        compute='_compute_amount_totals',
        store=True,
        help='變更後的契約總金額（= 各頂層彙總項變更後金額加總）')

    # === 發包工程費調整（不經工項的契約金額增減）===
    # 對應變更設計詳細表上「壹 發包工程費」那一列的追加/追減欄。
    # 使用時機：工項完全不動（項數與數量都不變），只調整契約總額。
    # 預約式的契約金額是「上限金額」，工項只是議價單價表，這種變更是常態。
    lump_adjust_amount = fields.Monetary(
        string='發包工程費調整金額',
        currency_field='currency_id',
        tracking=True,
        help='工項不動、只調整契約總額時使用（正數追加、負數追減）。\n'
             '套用後累加至工程的「契約金額調整」，並反映在契約金額、估驗計價等下游。')

    lump_adjust_reason = fields.Char(
        string='調整說明',
        tracking=True,
        help='發包工程費調整的原因，例如「業主追加預算」「上限金額提高」')

    # === 採購法 50% 管制的豁免 ===
    # 實務上機關可能改依其他法源核准變更（實例：111年度北區預約維護第3次變更，
    # 依「不可預見之緊急事故」辦理颱風災後復原、不再引用 50%，並載明累計 808 萬）。
    # 這種情況下 50% 已經不是判準，系統必須讓得出去，但要留下是誰、為什麼放行。
    is_limit_exempt = fields.Boolean(
        string='啟用 50% 管制豁免',
        tracking=True,
        help='本次變更改依其他法源辦理，不受採購法第 22 條 50% 累計變更管制。\n'
             '核定後，本工程之後的契約變更一律沿用此豁免，不必逐張勾選。')

    exempt_reason = fields.Text(
        string='啟用豁免之緣由',
        tracking=True,
        help='勾選豁免時必填。例如：依採購法第22條第1項第3款「不可預見之緊急事故」'
             '辦理，軒蘭諾／梅花／尼莎颱風災後復原，累計 808 萬。')

    # === 變更明細 ===
    line_ids = fields.One2many(
        'contract.change.order.line',
        'change_order_id',
        string='變更明細',
        copy=True)

    line_count = fields.Integer(
        string='明細筆數',
        compute='_compute_line_count')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('applied', '已套用'),
        ('rejected', '已駁回'),
    ], string='狀態',
       default='draft',
       tracking=True,
       index=True)

    # === 審核資訊 ===
    submitted_by_id = fields.Many2one(
        'res.users',
        string='提送人',
        readonly=True)

    submitted_date = fields.Datetime(
        string='提送時間',
        readonly=True)

    reviewed_by_id = fields.Many2one(
        'res.users',
        string='審核人',
        readonly=True)

    reviewed_date = fields.Datetime(
        string='審核時間',
        readonly=True)

    approved_by_id = fields.Many2one(
        'res.users',
        string='核定人',
        readonly=True)

    approved_date = fields.Datetime(
        string='核定時間',
        readonly=True)

    applied_by_id = fields.Many2one(
        'res.users',
        string='套用人',
        readonly=True)

    applied_date = fields.Datetime(
        string='套用時間',
        readonly=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        readonly=True)

    # === 備註 ===
    notes = fields.Html(
        string='備註')

    # === 權限計算欄位 ===
    is_change_leader = fields.Boolean(
        compute='_compute_is_change_leader',
        string='是否為專案負責人')

    @api.depends('project_id.project_leader_id')
    def _compute_is_change_leader(self):
        is_admin = self.env.user.has_group(
            'construction_supervision_base.group_supervisor_admin')
        for rec in self:
            leader = rec.project_id.project_leader_id
            # 未設定負責人時不限制；管理者永遠有權限
            rec.is_change_leader = (
                is_admin or
                not leader or
                self.env.user == leader
            )

    # === 計算欄位 ===
    @api.depends('line_ids')
    def _compute_line_count(self):
        for order in self:
            order.line_count = len(order.line_ids)

    @api.depends('line_ids.original_amount', 'line_ids.new_amount',
                 'line_ids.item_level', 'lump_adjust_amount', 'state',
                 'line_ids.exclude_from_contract_amount',
                 'project_id.contract_amount',
                 'project_id.contract_amount_adjustment')
    def _compute_amount_totals(self):
        """契約金額一律以「頂層彙總項（item_level == 0）加總」為單一真實來源。

        概念（薪資統計類比）：各頂層「部門」彙總項各自由下而上算出（明細端
        wizard 已含稅什費 tax_misc_rate 比率），再加總所有頂層彙總項。
          變更前 = Σ 頂層 original_amount + 歷次契約金額調整
          變更後 = Σ 頂層 new_amount     + 歷次契約金額調整 + 本次發包工程費調整
          本次變更 = 變更後 - 變更前
        不再使用「快照 original + Σ change」的鏈式累積（會逐次累積誤差）。

        「純案例一」（工項完全不動、只填 lump_adjust_amount）時沒有任何明細列，
        Σ 頂層會是 0 —— 此時基數退回工程當前的工項合計
        （contract_amount − contract_amount_adjustment），否則變更前會顯示成 0。
        """
        for order in self:
            top = order.line_ids.filtered(
                lambda l: l.item_level == 0 and not l.exclude_from_contract_amount)
            adjustment = order.project_id.contract_amount_adjustment or 0.0
            lump = order.lump_adjust_amount or 0.0
            # 套用後 lump 已經進了 project.contract_amount_adjustment，
            # 這裡要退回「本單套用前」的累計值，否則變更後金額會把 lump 算兩次。
            adj_before = adjustment - (lump if order.state == 'applied' else 0.0)

            if top:
                # 頂層彙總明細（發包工程費）的新金額已含本次 lump
                # ——由 _apply_lump_to_top_line 寫進去，樣板才抓得到。
                order.original_contract_amount = (
                    sum(top.mapped('original_amount')) + adj_before)
                order.new_contract_amount = (
                    sum(top.mapped('new_amount')) + adj_before)
            else:
                # 完全沒有明細（未經精靈、直接在變更單上填調整金額）：
                # 以工程當前的工項合計為基數（扣掉累計調整才是純工項部分）
                task_base = (order.project_id.contract_amount or 0.0) - adjustment
                order.original_contract_amount = task_base + adj_before
                order.new_contract_amount = task_base + adj_before + lump

            order.change_amount = (
                order.new_contract_amount - order.original_contract_amount)
            if order.original_contract_amount:
                order.change_amount_rate = (
                    order.change_amount / order.original_contract_amount)
            else:
                order.change_amount_rate = 0.0

    def _apply_lump_to_top_line(self, delta):
        """把「發包工程費調整金額」的變化量疊到頂層彙總項那一列變更明細上。

        變更設計詳細表就是把追加/追減寫在「壹 發包工程費」那一列
        （原訂合價 → 變更後合價 → 追加），樣板日後也一律以變更明細為準，
        所以金額不能只存在抬頭欄位，必須落到明細裡。

        頂層彙總明細以 qty=1 / price=總額 儲存，故直接加在 new_unit_price 上。
        傳入的是「變化量」而非絕對值：如此不必額外記住「不含調整的變更後金額」，
        精靈重建明細與使用者事後改抬頭金額都能各自加一次、不重複。
        """
        self.ensure_one()
        if not delta:
            return
        top = self.line_ids.filtered(
            lambda l: l.is_summary_line and l.item_level == 0
            and not l.exclude_from_contract_amount).sorted('sequence')
        if not top:
            return
        line = top[0]
        line.new_unit_price = (line.new_unit_price or 0.0) + delta

    # === 採購法第 22 條：累計變更金額管制 ===
    CHANGE_LIMIT_RATE = 0.5   # 累計變更金額絕對值不得超過原契約金額的 50%

    cumulative_change_amount = fields.Monetary(
        string='累計變更金額(絕對值)',
        currency_field='currency_id',
        compute='_compute_change_limit',
        help='本工程歷次已核定/已套用變更單的變更金額**逐次取絕對值相加**，'
             '再加上本單。追加與追減不互相抵銷（採購法第 22 條）。')

    cumulative_change_rate = fields.Float(
        string='累計變更比率 (%)',
        digits=(16, 4),
        compute='_compute_change_limit',
        help='累計變更金額(絕對值) ÷ 原契約金額（小數，如 0.5 = 50%）')

    is_over_change_limit = fields.Boolean(
        string='超過 50% 管制',
        compute='_compute_change_limit')

    has_change_limit_base = fields.Boolean(
        string='已設定原契約金額',
        compute='_compute_change_limit',
        help='未設定原始契約金額時無法執行 50% 管制')

    @api.depends('change_amount', 'project_id',
                 'project_id.original_contract_amount',
                 'project_id.change_order_ids.state',
                 'project_id.change_order_ids.change_amount')
    def _compute_change_limit(self):
        for order in self:
            base = order.project_id.original_contract_amount or 0.0
            order.has_change_limit_base = bool(base)
            order.cumulative_change_amount = order._cumulative_change_amount()
            if base:
                order.cumulative_change_rate = order.cumulative_change_amount / base
                order.is_over_change_limit = (
                    order.cumulative_change_rate > order.CHANGE_LIMIT_RATE)
            else:
                order.cumulative_change_rate = 0.0
                order.is_over_change_limit = False

    # === 豁免狀態（本單自己勾的，或沿用先前已核定的）===
    limit_exempt_active = fields.Boolean(
        string='不受 50% 管制',
        compute='_compute_limit_exempt')

    limit_exempt_source_id = fields.Many2one(
        'contract.change.order',
        string='豁免來源變更單',
        compute='_compute_limit_exempt',
        help='讓本單免受 50% 管制的那一張變更單')

    limit_exempt_note = fields.Char(
        string='豁免說明',
        compute='_compute_limit_exempt')

    @api.depends('is_limit_exempt', 'project_id',
                 'project_id.change_order_ids.is_limit_exempt',
                 'project_id.change_order_ids.state',
                 'project_id.change_order_ids.change_no')
    def _compute_limit_exempt(self):
        for order in self:
            source = order._resolve_exempt_source()
            order.limit_exempt_source_id = source
            order.limit_exempt_active = bool(source)
            if not source:
                order.limit_exempt_note = False
            elif source == order:
                order.limit_exempt_note = (
                    '本次變更啟用豁免，不適用採購法 50% 累計變更管制')
            else:
                order.limit_exempt_note = (
                    '已依第 %s 次變更（%s）啟用之豁免辦理，'
                    '不適用採購法 50%% 累計變更管制'
                    % (source.change_no or '?', source.name))

    def _resolve_exempt_source(self):
        """回傳讓本單免受 50% 管制的那一張變更單（沒有就回空 recordset）。

        ・本單自己勾了 → 就是自己。
          （必須如此，否則「啟用豁免的那一張」會卡在自己的提送關——它還沒核定，
            按定義就享受不到豁免，永遠核定不了。）
        ・否則 → 本工程最早一張「已核定／已套用且勾了豁免」的變更單。
          只認已核定的，與 50% 累計的計入範圍一致；一張還沒人審過的草稿
          不應該就把全工程的管制拆掉。
        """
        self.ensure_one()
        if self.is_limit_exempt:
            return self
        if not self.project_id:
            return self.browse()
        approved = self.project_id.change_order_ids.filtered(
            lambda o: o.is_limit_exempt and o.state in ('approved', 'applied'))
        if not approved:
            return self.browse()
        return approved.sorted(key=lambda o: (o.change_no or 9999, o.id))[0]

    def _exempt_dependents(self, keep_self=False):
        """哪些已核定／已套用的變更單，會因為本單的豁免消失而變成超標。

        兩種情境的累計基數不一樣，不能共用同一個算式：

        ・keep_self=False（退回草稿／刪除）
          本單會離開累計 → 只算「其他」已核定／已套用的變更單。
        ・keep_self=True（取消豁免勾選）
          本單仍是已核定、金額照樣計入累計 → 要把自己也算進去，
          而且自己也會變成超標的那一張。

        回傳空 recordset 代表沒有人在依賴，可以放行。
        """
        self.ensure_one()
        if not self.is_limit_exempt or not self.project_id:
            return self.browse()
        base = self.project_id.original_contract_amount or 0.0
        if not base:
            return self.browse()

        others = self.project_id.change_order_ids.filtered(
            lambda o: o.id != self.id and o.state in ('approved', 'applied'))
        total = sum(abs(o.change_amount or 0.0) for o in others)
        self_counts = keep_self and self.state in ('approved', 'applied')
        if self_counts:
            total += abs(self.change_amount or 0.0)

        if total <= base * self.CHANGE_LIMIT_RATE:
            return self.browse()

        affected = others.filtered(lambda o: not o.is_limit_exempt)
        if self_counts:
            affected |= self
        return affected

    def _raise_if_exempt_depended_on(self, action_label, keep_self=False):
        """本單的豁免若一撤掉就會讓已核定的變更單違規，就不許動它。"""
        self.ensure_one()
        deps = self._exempt_dependents(keep_self=keep_self)
        if not deps:
            return
        listed = '\n'.join(
            '・第 %s 次變更\u3000%s（%s）'
            % (o.change_no or '?', o.name,
               format(o.change_amount or 0.0, '+,.0f'))
            for o in deps[:8])
        more = ('\n・…共 %d 張' % len(deps)) if len(deps) > 8 else ''
        raise UserError(
            '本變更單啟用的 50%% 管制豁免一旦%s，下列已核定的變更單'
            '將超過採購法 50%% 累計變更管制：\n\n%s%s\n\n'
            '請先處理這些變更單，或改由其中一張自行啟用豁免。'
            % (action_label, listed, more))


    def _cumulative_change_amount(self):
        """Σ|每次變更金額|：已核定/已套用的其他變更單 + 本單。

        逐次取絕對值再相加（不是先相加再取絕對值）—— 採購法第 22 條的算法是
        「第一次變更絕對值 40，第二次就只剩 10 可用」，追加與追減不互相抵銷。
        草稿與已駁回不計入。
        """
        self.ensure_one()
        if not self.project_id:
            return abs(self.change_amount or 0.0)
        others = self.project_id.change_order_ids.filtered(
            lambda o: o.id != self.id and o.state in ('approved', 'applied'))
        return (sum(abs(o.change_amount or 0.0) for o in others)
                + abs(self.change_amount or 0.0))

    def _check_cumulative_change_limit(self):
        """超過採購法 50% 上限一律擋下（提送、核定、套用三處各檢一次）。

        例外：本工程已啟用豁免（本單自己勾了，或先前已核定的變更單勾了）時放行。
        金額與比率照算照顯示 —— 變更設計詳細表仍要載明累計金額，
        只是不再拿 50% 來擋關。
        """
        self.ensure_one()
        if self.limit_exempt_active:
            return
        base = self.project_id.original_contract_amount or 0.0
        if not base:
            # 沒有基數無從管制；不擋，但表單上有警示文字
            return
        others = self.project_id.change_order_ids.filtered(
            lambda o: o.id != self.id and o.state in ('approved', 'applied'))
        prior = sum(abs(o.change_amount or 0.0) for o in others)
        current = abs(self.change_amount or 0.0)
        total = prior + current
        limit = base * self.CHANGE_LIMIT_RATE
        if total > limit:
            raise UserError(
                '超過採購法第 22 條的累計變更金額上限，無法繼續。\n\n'
                f'原契約金額：{base:,.0f}\n'
                f'可用上限（50%）：{limit:,.0f}\n'
                f'歷次已核定變更累計（絕對值）：{prior:,.0f}\n'
                f'本次變更金額（絕對值）：{current:,.0f}\n'
                f'合計：{total:,.0f}\n'
                f'超出：{total - limit:,.0f}\n\n'
                '請調整本次變更金額，或依規定另循程序辦理。')

    # === Onchange ===
    # 註：original_contract_amount 已改為由明細（頂層彙總項）計算，
    #     不再於選擇工程時快照 current_contract_amount（避免鏈式累積誤差）。

    # === 約束 ===
    @api.constrains('line_ids', 'lump_adjust_amount')
    def _check_line_ids(self):
        """檢查變更明細

        例外：只調整發包工程費（工項完全不動）的變更單本來就沒有明細，
        此時以 lump_adjust_amount 非 0 代替「至少一筆明細」的要求。
        """
        for order in self:
            if (order.state != 'draft'
                    and not order.line_ids
                    and not order.lump_adjust_amount):
                raise ValidationError(
                    '契約變更單必須至少包含一筆變更明細，'
                    '或填寫「發包工程費調整金額」！')

    @api.constrains('is_limit_exempt', 'exempt_reason')
    def _check_exempt_reason(self):
        """勾了豁免就必須說明理由 —— 這是拆掉一道法規管制，不能沒有紀錄。"""
        for order in self:
            if order.is_limit_exempt and not (order.exempt_reason or '').strip():
                raise ValidationError(
                    '勾選「啟用 50%% 管制豁免」時，必須填寫「啟用豁免之緣由」！\n'
                    '（例如：依採購法第22條第1項第3款「不可預見之緊急事故」辦理，'
                    '颱風災後復原）')

    # === 狀態動作 ===
    def action_submit(self):
        """提送審查"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以提送！')
        if not self.project_id:
            raise UserError('請先透過「匯入工程案件」設定所屬工程！')
        if not self.line_ids and not self.lump_adjust_amount:
            raise UserError(
                '請先新增變更明細，或填寫「發包工程費調整金額」'
                '（工項不動、只調整契約總額時使用）！')

        # 註：original_contract_amount 由 _compute_amount_totals 自明細計算，無需快照。
        # 採購法第 22 條：累計變更金額絕對值超過原契約金額 50% 一律擋下
        self._check_cumulative_change_limit()

        self.write({
            'state': 'submitted',
            'submitted_by_id': self.env.uid,
            'submitted_date': fields.Datetime.now(),
        })

    def action_review(self):
        """開始審查"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError('只有已提送狀態可以開始審查！')

        self.write({
            'state': 'reviewing',
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_approve(self):
        """核定通過"""
        self.ensure_one()
        if self.state != 'reviewing':
            raise UserError('只有審查中狀態可以核定！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能核定！')
        self._check_cumulative_change_limit()

        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })

    def action_reject(self):
        """開啟駁回精靈"""
        self.ensure_one()
        if self.state not in ('submitted', 'reviewing'):
            raise UserError('只有已提送或審查中狀態可以駁回！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能駁回！')

        return {
            'type': 'ir.actions.act_window',
            'name': '駁回變更單',
            'res_model': 'contract.change.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_change_order_id': self.id,
            },
        }

    def action_do_reject(self, reason):
        """執行駁回"""
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'rejection_reason': reason,
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_apply(self):
        """套用變更"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('只有已核定狀態可以套用變更！')
        if not self.is_change_leader:
            raise UserError('只有專案負責人或系統管理者才能套用變更！')
        self._check_cumulative_change_limit()

        # 套用變更至工項
        self._apply_changes_to_tasks()

        # 更新專案契約金額與工期
        self._update_project_contract()

        self.write({
            'state': 'applied',
            'applied_by_id': self.env.uid,
            'applied_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        """重設為草稿"""
        self.ensure_one()
        if self.state not in ('submitted', 'rejected'):
            raise UserError('只有已提送或已駁回狀態可以重設為草稿！')
        self._raise_if_exempt_depended_on('退回草稿')

        vals = {
            'state': 'draft',
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'rejection_reason': False,
        }
        if self.state == 'approved':
            vals.update({
                'approved_by_id': False,
                'approved_date': False,
            })
        self.write(vals)

    # === 套用變更邏輯 ===
    def _apply_changes_to_tasks(self):
        """套用變更至工項"""
        self.ensure_one()
        ProjectTask = self.env['project.task']

        # ── 新增(add)：拓樸建立（父先於子）──────────────────────────
        # 支援「本次新增的彙總群組」：子項以 parent_line_id 指向同變更的群組新增列，
        # 該群組此時尚非 task；故先建父群組、記入 line2task，子項再用它解析 parent_id。
        # （借鏡標單匯入 tender_import_wizard 的 task_map 階層建立法。）
        add_lines = self.line_ids.filtered(lambda l: l.change_type == 'add')
        line2task = {}
        pending = list(add_lines)
        guard = 0
        while pending:
            guard += 1
            if guard > 50:
                raise UserError('契約變更新增項父子關係解析超過上限，疑有循環參照。')
            progressed = False
            still = []
            for line in pending:
                if line.parent_line_id:
                    ptask = line2task.get(line.parent_line_id.id)
                    if not ptask:
                        still.append(line)          # 父群組尚未建立 → 下一輪
                        continue
                    parent_id = ptask.id
                elif line.parent_task_id:
                    parent_id = line.parent_task_id.id
                else:
                    parent_id = False               # 新增的頂層彙總群組
                line2task[line.id] = self._create_added_task(line, parent_id)
                progressed = True
            pending = still
            if pending and not progressed:
                raise UserError(
                    '契約變更新增項找不到父項（缺父或循環）：%s'
                    % '、'.join(l.item_name or '?' for l in pending))

        # ── 修改/歸零/刪除（與新增無相依，順序無關）─────────────────
        for line in self.line_ids:
            if line.change_type == 'modify' and line.task_id:
                # 凍結原始契約數量（僅第一次變更時）
                if not line.task_id.original_planned_qty:
                    line.task_id.original_planned_qty = line.task_id.planned_qty
                # 修改工項
                line.task_id.write({
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],  # 新增到 Many2many
                })
                # 建立版本記錄
                next_version = max(line.task_id.version_ids.mapped('version') or [0]) + 1
                self.env['project.task.version'].create({
                    'task_id': line.task_id.id,
                    'version': next_version,
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_date': self.change_date or fields.Date.today(),
                    'change_reason': self.name,
                    'change_order_id': self.id,
                })
                
            elif line.change_type == 'zero_out' and line.task_id:
                # 歸零：工項保留、數量歸零（保留原單價供參考），並建立版本記錄
                if not line.task_id.original_planned_qty:
                    line.task_id.original_planned_qty = line.task_id.planned_qty
                line.task_id.write({
                    'planned_qty': 0.0,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],
                })
                next_version = max(line.task_id.version_ids.mapped('version') or [0]) + 1
                self.env['project.task.version'].create({
                    'task_id': line.task_id.id,
                    'version': next_version,
                    'planned_qty': 0.0,
                    'unit_price': line.task_id.unit_price,  # 保留原單價
                    'change_date': self.change_date or fields.Date.today(),
                    'change_reason': self.name,
                    'change_order_id': self.id,
                })

            elif line.change_type == 'delete' and line.task_id:
                # 標記刪除 (不實際刪除，保留歷史)
                line.task_id.write({
                    'active': False,
                    'change_order_id': self.id,
                    'change_order_ids': [(4, self.id)],  # 新增到 Many2many
                })

        # ── 結構變更後，整個專案以樹狀 DFS 重編 sequence ──────────────
        # 新增/刪除會讓同父 max+10 的序號跨越下一彙總項區間造成亂序；
        # 重編後保證「父 < 子孫 < 下一兄弟」，徹底消除跨彙總項撞號。
        if self.project_id and self.project_id:
            ProjectTask._resequence_project_sequence(self.project_id.id)

    def _create_added_task(self, line, parent_id):
        """建立一筆新增工項 task（parent_id 已由拓樸解析：既有彙總項或本次新建群組）。
        回傳建立的 project.task。item_level/planned_amount 由 compute 自動處理。"""
        self.ensure_one()
        ProjectTask = self.env['project.task']
        display_unit = ProjectTask._normalize_unit_display(line.unit)
        vals = {
            'project_id': self.project_id.id,
            'name': line.item_name,
            'item_no': line.item_no,
            'planned_qty': line.new_qty,
            'unit': display_unit,
            'unit_id': ProjectTask._resolve_uom_id(display_unit),
            'unit_price': line.new_unit_price,
            'change_order_id': self.id,
            'specification': line.specification or '',
            'ref_item_code': line.ref_item_code or '',
            'exclude_from_contract_amount': line.exclude_from_contract_amount,
        }
        if line.ref_item_code:
            product = self.env['product.product'].search(
                [('default_code', '=', line.ref_item_code)], limit=1)
            if product:
                vals['product_id'] = product.id
        # 排序：排在同父既有子項之後（避免新增項用預設 sequence 擠到最前造成亂序）
        if parent_id:
            vals['parent_id'] = parent_id
            parent = ProjectTask.browse(parent_id)
            siblings = parent.child_ids
            base_seq = max(siblings.mapped('sequence')) if siblings else (parent.sequence or 0)
            vals['sequence'] = base_seq + 10
        else:
            top = ProjectTask.search([('project_id', '=', vals['project_id']),
                                      ('parent_id', '=', False)])
            vals['sequence'] = (max(top.mapped('sequence')) if top else 0) + 10

        task = ProjectTask.create(vals)
        task.write({'change_order_ids': [(4, self.id)]})
        if task.version_ids:
            task.version_ids[0].write({
                'change_order_id': self.id,
                'change_date': self.change_date or fields.Date.today(),
                'change_reason': self.name,
            })
        return task

    def _update_project_contract(self):
        """契約變更套用時不修改 contract_end_date（預定契約完工日）。
        該欄位由進度表啟用（_do_activate）時寫回 adjusted_end_date，確保單一更新來源。
        contract_amount 由 ORM 依賴追蹤（task_ids.planned_amount）自動重算。

        唯一要主動寫回的是「發包工程費調整金額」：它不經工項，
        累加到工程的 contract_amount_adjustment，contract_amount 再由 compute 帶上。
        欄位在 base 宣告為 readonly，故以 sudo() 寫入。
        """
        self.ensure_one()
        if not self.lump_adjust_amount or not self.project_id:
            return
        project = self.project_id.sudo()
        project.write({
            'contract_amount_adjustment': (
                (project.contract_amount_adjustment or 0.0)
                + self.lump_adjust_amount),
        })
        project.message_post(body=(
            f'契約變更單 <b>{self.name}</b> 套用發包工程費調整：'
            f'{self.lump_adjust_amount:+,.0f}'
            + (f'（{self.lump_adjust_reason}）' if self.lump_adjust_reason else '')
        ))

    # === CRUD 覆寫 ===
    def _generate_change_order_name(self):
        """產生變更編號：{工程編號}-CHG-{N:02d}"""
        self.ensure_one()
        if not self.project_id:
            return '/'
        # 計算此工程已有的變更單數量（排除自身）
        existing_count = self.search_count([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
        ])
        n = existing_count + 1
        return f"{self.project_id.code}-CHG-{n:02d}"

    @api.model_create_multi
    def create(self, vals_list):
        # 先建立記錄取得 id，再依工程編號產生變更編號
        records = super().create(vals_list)
        for record in records:
            if record.name == '/' and record.project_id:
                record.name = record._generate_change_order_name()
        return records

    def write(self, vals):
        # 抬頭的「發包工程費調整金額」改了，頂層彙總明細要跟著動同樣的量，
        # 否則明細與抬頭會對不起來（樣板抓明細就會少掉這筆調整）。
        # 取消豁免前先擋：已核定的後續變更可能正靠它才過得了 50% 管制
        if 'is_limit_exempt' in vals and not vals.get('is_limit_exempt'):
            for order in self:
                if order.is_limit_exempt:
                    order._raise_if_exempt_depended_on('取消豁免', keep_self=True)

        deltas = {}
        if 'lump_adjust_amount' in vals:
            new_lump = vals.get('lump_adjust_amount') or 0.0
            deltas = {r.id: new_lump - (r.lump_adjust_amount or 0.0) for r in self}

        result = super().write(vals)

        for record in self:
            if deltas.get(record.id):
                record._apply_lump_to_top_line(deltas[record.id])
        # 當 project_id 首次設定時，自動產生變更編號
        if vals.get('project_id'):
            for record in self:
                if record.name == '/':
                    record.name = record._generate_change_order_name()
        return result

    def unlink(self):
        for order in self:
            if order.state not in ('draft', 'rejected'):
                raise UserError('只有草稿或已駁回的變更單可以刪除！')
            order._raise_if_exempt_depended_on('刪除')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': '/',
            'state': 'draft',
            # 豁免是「那一次由機關以其他法源核准」的事實，不隨複製繼承
            'is_limit_exempt': False,
            'exempt_reason': False,
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'approved_by_id': False,
            'approved_date': False,
            'applied_by_id': False,
            'applied_date': False,
            'rejection_reason': False,
        })
        return super().copy(default)

    # === 匯入工程案件 ===
    def action_open_import_wizard(self):
        """開啟匯入工程案件精靈"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入工程案件',
            'res_model': 'contract.change.wizard',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_change_order_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }


    # === 檢視動作 ===
    def action_view_lines(self):
        """查看變更明細"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '變更明細',
            'res_model': 'contract.change.order.line',
            'view_mode': 'list,form',
            'domain': [('change_order_id', '=', self.id)],
            'context': {
                'default_change_order_id': self.id,
            },
        }


class ContractChangeRejectWizard(models.TransientModel):
    """駁回精靈"""
    _name = 'contract.change.reject.wizard'
    _description = '契約變更駁回精靈'

    change_order_id = fields.Many2one(
        'contract.change.order',
        string='變更單',
        required=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        required=True)

    def action_confirm(self):
        """確認駁回"""
        self.ensure_one()
        self.change_order_id.action_do_reject(self.rejection_reason)
        return {'type': 'ir.actions.act_window_close'}

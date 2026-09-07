# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PaymentEstimate(models.Model):
    """
    估驗計價

    重構版本：
    - 以「匯入工程案件」為核心操作流程
    - 簡化狀態為 草稿→待核定→已核定→已歸檔
    - 移除多公司架構、驗收單關聯、保留款等
    """
    _name = 'payment.estimate'
    _description = '估驗計價'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'estimate_no asc, id desc'

    # ⚠️ 必須是 DEFERRABLE INITIALLY DEFERRED，不能用普通 UNIQUE。
    #
    # `_resequence_estimate_no()` 是逐筆 write，排序變動時中間狀態必然撞號——
    # 例如 1,2,3 要重排成 3,1,2，寫第一筆就跟現有的 1 相撞。
    # 2026-08-07 實測（交易內加約束、觸發排列置換、再 rollback）：
    #     普通 UNIQUE(project_id, estimate_no)  → UniqueViolation
    #     同樣操作 + DEFERRABLE INITIALLY DEFERRED → 通過
    # 延遲到 COMMIT 才檢查，中間過程允許暫時重複，最終狀態仍保證唯一。
    #
    # 這個約束長期記為 BLOCKED，因為舊資料有重複；2026-08-07 清掉 9 張
    # 無工程無明細的孤兒估驗（ids 113-116、137-141）後，重複組數歸零才得以建立。
    _sql_constraints = [
        ('unique_project_estimate_no',
         'UNIQUE (project_id, estimate_no) DEFERRABLE INITIALLY DEFERRED',
         '同一工程的估驗次數不能重複。'),
    ]

    # === 基本資訊 ===
    name = fields.Char(
        '估驗名稱',
        readonly=True,
        copy=False,
        help='自動產生，格式：第N次估驗計價'
    )
    estimate_no = fields.Integer(
        '次數',
        readonly=True,
        copy=False,
        help='同一工程中自動遞增'
    )

    # === 工程資訊區塊（全部 readonly，由匯入帶入）===
    project_id = fields.Many2one(
        'project.project',
        '所屬工程',
        ondelete='cascade',
        readonly=True,
        tracking=True,
        index=True
    )
    # 2026-08-18 移除 slip_id：估驗計價與通報單在功能上無關。
    #   估驗詳細表的結構是「契約詳細價目表 × 期別」（群組/項次/單價全繼承自契約），
    #   通報單不出現在計價單上；模型的每一項計算（估驗次數重排、前期累計、可估數量、
    #   唯一性約束）也都以 project + estimate_date + task 為軸，從不經過 slip。
    #   兩者只是透過共同的 project.task 產生關聯，是兄弟而非父子——
    #   原本的 slip_id 是「精靈的取數捷徑」被誤升格成資料模型。
    #   實證：一期估驗橫跨多張通報單、一張通報單的量也會被切到多期
    #   （P11001 第 15/16 次橫跨第 7、8 期；第 6 次 11-28 完工卻在第 8 期才估），
    #   所以單值 M2O、M2M、由 task_id 反查三種形狀沒有一種表達得了。
    contract_no = fields.Char(
        '契約編號',
        related='project_id.contract_no',
        store=True,
        readonly=True
    )
    contract_amount = fields.Monetary(
        '契約金額',
        related='project_id.contract_amount',
        store=True,
        readonly=True
    )

    # === 估驗資訊區塊 ===
    estimate_date = fields.Date(
        '估驗日期',
        tracking=True,
        help='估驗截止日期，施工日誌累計以此日期為節點'
    )
    submitted_date = fields.Datetime(
        '提出日期',
        readonly=True
    )
    submitted_by_id = fields.Many2one(
        'res.users',
        '提出人',
        readonly=True
    )
    approved_by_id = fields.Many2one(
        'res.users',
        '核定人',
        readonly=True
    )
    approved_date = fields.Datetime(
        '核定日期',
        readonly=True
    )

    # === 金額 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    subtotal = fields.Monetary(
        '本次估驗總金額',
        compute='_compute_subtotal',
        store=True,
        tracking=True,
        help='契約工項小計 ＋ 有勾「計入估驗總額」的非契約工項'
    )
    contract_subtotal = fields.Monetary(
        '契約工項小計',
        compute='_compute_subtotal',
        store=True,
        help='估驗計價表（契約工項）的葉節點金額合計，即估驗詳細表的「壹 發包工程費」'
    )
    extra_subtotal = fields.Monetary(
        '非契約工項（計入）',
        compute='_compute_subtotal',
        store=True,
        help='非契約工項中有勾「計入估驗總額」者的金額合計，'
             '例：估驗詳細表的「貳 第N次估驗物價調整累計金額」'
    )
    extra_excluded_total = fields.Monetary(
        '非契約工項（不計入）',
        compute='_compute_subtotal',
        store=True,
        help='非契約工項中未勾「計入估驗總額」者的金額合計，'
             '例：估驗詳細表的「參 變賣收入項」（有價廢料變賣，另走解繳鏈）。'
             '本欄不進「本次估驗總金額」，只是把這些項目的金額匯總出來供對帳'
    )

    # === 計價明細 ===
    line_ids = fields.One2many(
        'payment.estimate.line',
        'estimate_id',
        '估驗計價表',
        copy=True
    )

    # === 非契約工項（估驗表上有、契約工項樹裡沒有的項目）===
    # 有價廢料變賣收入、物價調整…等。刻意獨立成兩個新模型，一列都不寫 project.task
    # ——那是契約金額的真相載體，寫進去會污染契約總價／契約變更原金額／採購法第 22 條
    # 累計變更比例，而且專案開工後契約工項全面唯讀，根本也寫不進去。
    # 詳見 models/payment_estimate_extra.py 的模組說明。
    extra_line_ids = fields.One2many(
        'payment.estimate.extra.line',
        'estimate_id',
        '非契約工項',
        copy=True
    )
    extra_line_count = fields.Integer(
        '非契約工項列數',
        compute='_compute_extra_line_count'
    )

    # === 照片 ===
    # 實際專案的照片資料夾裡有明確屬於某一期估驗的照片
    # （例如 `07_估驗計價/第4次/04.1.jpg`），照片收斂後統一掛在
    # supervision.photo 的 estimate_id 上（見 models/supervision_photo.py）。
    photo_ids = fields.One2many(
        'supervision.photo',
        'estimate_id',
        string='照片',
        help='此次估驗計價的照片')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('pending_approval', '待核定'),
        ('approved', '已核定'),
        ('archived', '已歸檔'),
    ], default='draft', tracking=True, string='狀態')

    # === 計算欄位 ===
    manual_amount_line_count = fields.Integer(
        '手動金額工項數',
        compute='_compute_manual_amount_line_count',
        help='本次估驗金額被人工覆寫的工項數（供「解除手動金額」按鈕判斷顯示）'
    )

    @api.depends('line_ids.estimate_amount', 'line_ids.is_summary_item',
                 'extra_line_ids.estimate_amount',
                 'extra_line_ids.extra_item_id',
                 'extra_line_ids.parent_item_id',
                 'extra_line_ids.include_in_subtotal')
    def _compute_subtotal(self):
        """計算本次估驗總金額 ＝ 契約工項小計 ＋ 有勾「計入估驗總額」的非契約工項。

        非契約工項分兩種、行為相反（同一張估驗詳細表上會並存）：
          ・「貳 物價調整」    → 勾計入，進總額（實務上照樣扣 5% 保留款）
          ・「參 變賣收入項」  → 不勾，只算進 extra_excluded_total 供對帳，不進總額
        沒有非契約工項時，本欄與改版前完全相同（extra_* 皆為 0）。

        🔴 非契約工項這一側加總的是**本期的根列**，不是葉列。
        契約工項那一側加總葉列是因為它的彙總項只是顯示用；非契約工項不一樣 ——
        「計入與否」是整個彙總項一起決定的（同一彙總項底下一部分計入、一部分不計入
        在實務上不成立），所以旗標要在彙總層生效。彙總列的 estimate_amount 本來就是
        底下葉列的合計，加總根列剛好把每一筆算到一次，不會重複也不會漏。

        「根列」＝ 沒有父項、或父項的那一列不在本期估驗單裡（後者是防呆：
        子列被單獨帶進來時仍然算得到，不會整批消失）。
        """
        for rec in self:
            leaf_lines = rec.line_ids.filtered(lambda l: not l.is_summary_item)
            rec.contract_subtotal = sum(leaf_lines.mapped('estimate_amount'))

            extra = rec.extra_line_ids
            present = set(extra.mapped('extra_item_id').ids)
            roots = extra.filtered(
                lambda l: not l.parent_item_id or l.parent_item_id.id not in present)
            included = roots.filtered('include_in_subtotal')
            rec.extra_subtotal = sum(included.mapped('estimate_amount'))
            rec.extra_excluded_total = sum(
                (roots - included).mapped('estimate_amount'))

            rec.subtotal = rec.contract_subtotal + rec.extra_subtotal

    @api.depends('extra_line_ids')
    def _compute_extra_line_count(self):
        for rec in self:
            rec.extra_line_count = len(rec.extra_line_ids)

    @api.depends('line_ids.is_amount_manual', 'line_ids.is_summary_item')
    def _compute_manual_amount_line_count(self):
        for rec in self:
            rec.manual_amount_line_count = len(rec.line_ids.filtered(
                lambda l: l.is_amount_manual and not l.is_summary_item
            ))

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立後依估驗日期重排次數與名稱

        次數（第N次）以 estimate_date 先後決定，而非建立順序。故建立時先給暫定名稱，
        再對受影響工程呼叫 _resequence_estimate_no 依日期整體重排。
        """
        for vals in vals_list:
            if not vals.get('name'):
                estimate_no = vals.get('estimate_no') or 1
                vals['name'] = f'第{estimate_no}次估驗計價'
        records = super().create(vals_list)
        if not self.env.context.get('_skip_estimate_resequence'):
            for project in records.mapped('project_id'):
                self._resequence_estimate_no(project.id)
        return records

    def unlink(self):
        """刪掉整張估驗單之前，先用 ORM 把非契約工項明細刪掉。

        🔴 為什麼要特別處理：`extra.line.estimate_id` 是 `ondelete='cascade'`，
        那是**資料庫層**的 ON DELETE CASCADE —— 刪父記錄時 Postgres 直接把子列
        清掉，**Python 的 `extra.line.unlink()` 根本不會被呼叫**。
        於是裡面那段「沒人用的工項定義一併刪掉」的清理完全不會跑，
        整張估驗單刪掉之後留下一堆孤兒定義（實測重現）。
        這正是使用者回報「刪掉之後記錄沒有正確清掉」的來源。

        契約工項明細（line_ids）沒有這個問題 —— 它沒有需要連帶清理的工程層級定義。
        """
        self.mapped('extra_line_ids').unlink()
        return super().unlink()

    def write(self, vals):
        """估驗日期變動時，重排該工程所有估驗單的次數（第N次依日期先後）"""
        res = super().write(vals)
        if 'estimate_date' in vals and not self.env.context.get('_skip_estimate_resequence'):
            for project in self.mapped('project_id'):
                self._resequence_estimate_no(project.id)
        return res

    @api.model
    def _resequence_estimate_no(self, project_id):
        """依 estimate_date 先後，重排整個工程的 estimate_no 與 name。

        無估驗日期者排在最後（PostgreSQL ASC 預設 NULLS LAST）。以 _skip 旗標
        避免 write 遞迴。
        """
        if not project_id:
            return
        estimates = self.with_context(_skip_estimate_resequence=True).search(
            [('project_id', '=', project_id)],
            order='estimate_date asc, id asc',
        )
        for idx, est in enumerate(estimates, start=1):
            vals = {}
            if est.estimate_no != idx:
                vals['estimate_no'] = idx
            new_name = f'第{idx}次估驗計價'
            if est.name != new_name:
                vals['name'] = new_name
            if vals:
                est.with_context(_skip_estimate_resequence=True).write(vals)

    # === 動作方法 ===
    def action_open_import_wizard(self):
        """開啟匯入工程案件 Wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入工程案件',
            'res_model': 'estimate.import.wizard',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_estimate_id': self.id,
            },
        }

    def action_open_manual_amount_wizard(self):
        """開啟「解除手動金額」精靈：逐項挑選要還原為系統計算值的工項"""
        self.ensure_one()
        if not self.manual_amount_line_count:
            raise UserError('本估驗單沒有手動填寫金額的工項。')
        return {
            'type': 'ir.actions.act_window',
            'name': '解除手動金額',
            'res_model': 'estimate.manual.amount.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_estimate_id': self.id,
            },
        }

    def action_submit_estimate(self):
        """提出估驗"""
        for rec in self:
            # 非契約工項也算「有內容」：一張只有變賣收入／物價調整的估驗單不是空單。
            # （實務上每期都會有契約工項，但這個閘門的語意是「不要送出空單」，
            #   不是「一定要有契約工項」。）
            if not rec.line_ids and not rec.extra_line_ids:
                raise UserError('請先匯入工程案件')
            rec.write({
                'state': 'pending_approval',
                'submitted_by_id': self.env.uid,
                'submitted_date': fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        """核定"""
        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })
        return True

    def action_archive_estimate(self):
        """歸檔"""
        self.write({'state': 'archived'})
        return True

    def action_reset_to_draft(self):
        """退回草稿：僅切換狀態，保留明細與工程資訊

        （原本會清空 line_ids 與 project_id，導致填寫的資料全失、且因清空工程而從
        依工程分組的清單中消失。退回草稿的語意應僅為狀態回退，不應銷毀資料。）
        """
        for rec in self:
            if rec.state != 'pending_approval':
                raise UserError('只有「待核定」狀態才能退回草稿')
            rec.write({
                'state': 'draft',
                'submitted_by_id': False,
                'submitted_date': False,
            })
        return True

    def action_backfill_summary_lines(self):
        """一鍵補列：將彙總工項補進現有估驗單並重排序號

        - 僅處理草稿／待核定且已有所屬工程的估驗單
        - 既有行重排序號；既有彙總列數量正規化為 1
        - 缺少的工項新建明細（彙總列依「一式」慣例 qty=1）
        - 已核定／已歸檔不受影響
        """
        Task = self.env['project.task']
        updated = 0
        for est in self:
            if est.state not in ('draft', 'pending_approval') or not est.project_id:
                continue

            # 取得工程全部有效工項（含彙總項），依樹狀順序
            tasks = Task.search([
                ('supervision_project_id', '=', est.project_id.id),
                ], order='sequence, id')
            if not tasks:
                continue

            existing = {l.task_id.id: l for l in est.line_ids}
            new_lines = []
            for idx, task in enumerate(tasks, start=1):
                seq = idx * 10
                if task.id in existing:
                    line = existing[task.id]
                    line.sequence = seq
                    # 既有彙總列：數量正規化為 1（一式）
                    if task.is_summary_item:
                        line.contract_qty = 1.0
                        line.approved_qty = 1.0
                        line.estimate_qty = 1.0
                else:
                    new_lines.append(Command.create(
                        self.env['payment.estimate.line']._prepare_line_vals(task, seq)
                    ))
            if new_lines:
                est.write({'line_ids': new_lines})
            updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '補列完成',
                'message': f'已處理 {updated} 筆估驗單，補上彙總項並重排序號。',
                'type': 'success',
                'sticky': False,
            },
        }

    # === 非契約工項：沿用到下一期 ===
    def _estimates_before(self):
        """本工程裡「排在我前面」的所有期別，由早到晚。

        排序刻意與 `_resequence_estimate_no()` 完全相同（estimate_date asc, id asc），
        所以這裡的順序就是畫面上「第N次」的順序。

        🔴 為什麼不用 domain 直接查：**同一天可能有好幾期**（補建歷史資料時，
        一天之內把十幾期都建出來是常態）。`estimate_date <` 這種寫法在同日時
        整組落空 —— 使用者實測就踩到：兩期都是當天日期，「帶入上期項目」
        回「上一期沒有非契約工項」。日期不足以定序，必須連 id 一起比，
        而那在 domain 裡表達不了，所以撈回來在 Python 排。
        """
        self.ensure_one()
        if not self.project_id:
            return self.browse()
        # estimate_date 可能是空的（尚未填日期）→ 排在最後，
        # 與 PostgreSQL 的 NULLS LAST 及 _resequence_estimate_no 的行為一致
        far = fields.Date.to_date('9999-12-31')
        ordered = self.search(
            [('project_id', '=', self.project_id.id)]
        ).sorted(key=lambda e: (e.estimate_date or far, e.id))
        before = self.browse()
        for est in ordered:
            if est.id == self.id:
                break
            before |= est
        return before

    def _previous_estimate(self):
        """緊接在本期之前的那一期（沒有就回空）。"""
        self.ensure_one()
        before = self._estimates_before()
        return before[-1] if before else self.browse()

    def _load_extra_items(self):
        """把本工程已定義的非契約工項帶進本估驗單（本次數量歸 0）。

        這就是需求的「可沿用到下一次的估驗計價表」：項目定義存在工程層級
        （payment.estimate.extra.item），每一期只是多一列 extra.line 指向它，
        所以累計靠 extra_item_id 聚合就自然成立，也完全不碰 project.task。

        已存在的列不動（不覆寫使用者已填的數量／金額），只補缺的。回傳新增列數。
        """
        self.ensure_one()
        if not self.project_id:
            return 0
        # 🔴 只帶「上一期實際有的項目」，不是全工程的項目清單。
        #
        # 原本抓全工程 → 在本期刪掉的列，一按這顆按鈕就整批回來，
        # 使用者實測時就是被這個咬到（「被我刪除的那 3 個又都出現了」）。
        # 而且按鈕名稱本來就寫「帶入上期項目」，程式卻做成「帶入全部」，
        # 名實不符。改成名實一致：以「上一期」為準。
        #
        # ⚠️ 「上一期」必須用**與「第N次」完全同一套排序**決定，也就是
        #    `_resequence_estimate_no()` 用的 (estimate_date, id)。
        #    第一版寫成 domain `estimate_date < 本期日期`（**嚴格小於**），
        #    結果**同一天建立的兩期就找不到上一期** —— 使用者實測時兩期都是
        #    當天日期，按鈕回「上一期沒有非契約工項」。
        #    同日多期是完全正常的操作（尤其補建歷史資料時一天建好幾期），
        #    日期本身不足以定序，所以這裡照抄 estimate_no 的排序邏輯，
        #    讓「上一期」＝畫面上顯示的前一次。
        prev = self._previous_estimate()
        if not prev:
            return 0
        items = prev.extra_line_ids.mapped('extra_item_id')
        items = items.sorted(key=lambda i: (i.sequence, i.id))
        if not items:
            return 0
        existing = set(self.extra_line_ids.mapped('extra_item_id').ids)
        ExtraLine = self.env['payment.estimate.extra.line']
        # 單價與計入旗標沿用「同一項目最近一期」的值（見 _prepare_line_vals）——
        # 單價逐期會變，帶入下一期時要跟著最近一期走，不是回頭用定義的原始值。
        new_lines = [
            Command.create(
                ExtraLine._prepare_line_vals(item, self, item.sequence or 10))
            for item in items if item.id not in existing
        ]
        if new_lines:
            self.write({'extra_line_ids': new_lines})
        return len(new_lines)

    def action_open_extra_item_wizard(self):
        """開啟「新增非契約工項」對話框。

        概念與操作方式比照契約變更那一套（契約變更單 ▸ 匯入工程案件精靈 ▸ 工項列表頁籤 ▸
        [新增工項] → form dialog），見 contract_change_wizard.action_add_new_line。
        這類工項在契約工項建立時根本不存在，所以入口必須是「新增」而不是「從清單挑」。
        """
        self.ensure_one()
        if not self.project_id:
            raise UserError('這張估驗單還沒有所屬工程，請先「匯入工程案件」。')
        if self.state not in ('draft', 'pending_approval'):
            raise UserError('只有草稿／待核定的估驗單可以新增非契約工項。')
        return {
            'type': 'ir.actions.act_window',
            'name': '新增非契約工項',
            'res_model': 'estimate.extra.item.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_estimate_id': self.id,
            },
        }

    def action_load_extra_items(self):
        """表頭按鈕：帶入本工程的非契約工項（本次數量歸 0，逐列自行填）"""
        self.ensure_one()
        if self.state not in ('draft', 'pending_approval'):
            raise UserError('只有草稿／待核定的估驗單可以帶入非契約工項。')
        added = self._load_extra_items()
        if not added:
            message = ('上一期沒有非契約工項，或上一期有的都已經在本期的清單裡了。\n'
                       '要新增請按「新增非契約工項」。\n'
                       '（本按鈕只帶「上一期實際有的項目」——'
                       '在本期刪掉的列不會被它拉回來。）')
            kind = 'warning'
        else:
            message = (f'已從上一期帶入 {added} 個非契約工項'
                       f'（本次數量為 0，單價與計入旗標沿用最近一期）。')
            kind = 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '帶入非契約工項',
                'message': message,
                'type': kind,
                'sticky': False,
            },
        }


class PaymentEstimateLine(models.Model):
    """
    估驗計價明細

    欄位說明：
    - contract_qty: 原始契約數量（變更前）
    - approved_qty: 變更後核定數量（現行 planned_qty）
    - available_qty: 本次可估驗數量（施工日誌截至估驗日期的累計）
    - estimate_qty: 本次估驗數量（可編輯）
    - estimate_amount: 本次估驗金額（可編輯；手動值優先於 單價 × 本次估驗數量）
    - cumulative_estimate_qty: 累計估驗數量（歷次已核定 + 本次）
    """
    _name = 'payment.estimate.line'
    _description = '估驗計價明細'
    _order = 'sequence, id'

    # === 關聯 ===
    estimate_id = fields.Many2one(
        'payment.estimate',
        '估驗單',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer('序號', default=10)

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task',
        '工項',
        required=True,
        readonly=True
    )
    is_summary_item = fields.Boolean(
        '彙總項',
        related='task_id.is_summary_item',
        store=True,
        readonly=True,
        help='有子項的父工項，於估驗表以「一式」呈現（數量固定為 1、金額為子項小計）'
    )

    # === 工項資訊（readonly）===
    description = fields.Char(
        '項目及說明',
        related='task_id.name',
        store=True,
        readonly=True
    )
    parent_item_name = fields.Char(
        '父工項路徑',
        compute='_compute_parent_item_name',
        store=True,
        readonly=True
    )
    item_no = fields.Char(
        '項目編號',
        related='task_id.item_no',
        store=True,
        readonly=True
    )
    unit = fields.Char(
        '單位',
        related='task_id.unit',
        store=True,
        readonly=True
    )

    # === 數量與單價（readonly，由匯入帶入）===
    contract_qty = fields.Float(
        '原始契約數量',
        digits=(16, 4),
        readonly=True,
        help='原始契約數量（變更前）'
    )
    approved_qty = fields.Float(
        '變更後核定數量',
        digits=(16, 4),
        readonly=True,
        help='經契約變更後的現行數量'
    )
    unit_price = fields.Float(
        '單價',
        digits=(16, 2),
        readonly=True
    )

    # === 估驗數量（可編輯）===
    estimate_qty = fields.Float(
        '本次估驗數量',
        digits=(16, 4),
        help='本次估驗的數量'
    )

    # === 計算欄位 ===
    available_qty = fields.Float(
        '本次可估驗數量',
        digits=(16, 4),
        compute='_compute_available_qty',
        readonly=True,
        help='施工日誌截至估驗日期的累計完成數量（即時計算，日誌更新後自動反映）'
    )
    previous_approved_qty = fields.Float(
        '前期已核定累計數量',
        digits=(16, 4),
        compute='_compute_previous_approved_qty',
        readonly=True,
        help='估驗日期早於本次、且已核定的估驗單，本工項的估驗數量合計。'
             '不依賴本次估驗數量，故本表即時編輯時保持穩定'
    )
    cumulative_estimate_qty = fields.Float(
        '累計估驗數量',
        digits=(16, 4),
        compute='_compute_cumulative',
        readonly=True,
        help='前期已核定累計 + 本次（純算術，即時更新；非儲存以反映他單核定）'
    )
    estimate_amount = fields.Float(
        '本次估驗金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True,
        readonly=False,
        help='預設為 單價 × 本次估驗數量；可直接手動輸入覆寫。'
             '一旦手動輸入，本欄即以手動值為準，不再被系統計算值覆蓋；'
             '取消勾選「金額手動輸入」即還原為系統計算值'
    )
    is_amount_manual = fields.Boolean(
        '金額手動輸入',
        default=False,
        help='本次估驗金額由人工輸入（優先於 單價 × 本次估驗數量）。'
             '取消勾選即還原為系統計算值'
    )
    manual_estimate_amount = fields.Float(
        '手動輸入金額',
        digits=(16, 2),
        help='保存人工輸入的本次估驗金額；計算欄位重算時沿用此值，'
             '避免數量或單價變動把手動值蓋掉'
    )
    cumulative_estimate_amount = fields.Float(
        '累計估驗金額',
        digits=(16, 2),
        compute='_compute_cumulative',
        readonly=True,
        help='單價 × 累計估驗數量（非儲存）'
    )

    # === 備註 ===
    note = fields.Text('備註', readonly=True)

    # === 建立 vals helper ===
    @api.model
    def _prepare_line_vals(self, task, sequence):
        """依工項產生估驗明細 vals（不含 estimate_id）

        彙總項採「一式」慣例：數量固定 1、單價 0（金額由子項加總）。
        葉節點：契約量/核定量/單價由工項帶入，本次估驗量預設 0。
        """
        if task.is_summary_item:
            return {
                'task_id': task.id,
                'sequence': sequence,
                'contract_qty': 1.0,
                'approved_qty': 1.0,
                'unit_price': 0.0,
                'estimate_qty': 1.0,
            }
        contract_qty = task.planned_qty
        if getattr(task, 'original_planned_qty', 0):
            contract_qty = task.original_planned_qty
        return {
            'task_id': task.id,
            'sequence': sequence,
            'contract_qty': contract_qty,
            'approved_qty': task.planned_qty,
            'unit_price': task.unit_price,
            'estimate_qty': 0.0,
        }

    # === 計算方法 ===
    @api.depends('task_id.parent_id', 'task_id.parent_id.full_item_path')
    def _compute_parent_item_name(self):
        """計算父工項路徑"""
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.full_item_path or ''
            else:
                line.parent_item_name = ''

    @api.model
    def _get_cumulative_qty_at(self, task, date):
        """取得某工項截至指定日期的施工日誌累計完成量"""
        if not task or not date:
            return 0.0
        last_log = self.env['daily.log.line'].search([
            ('work_item_id', '=', task.id),
            ('date', '<=', date),
        ], order='date desc, id desc', limit=1)
        return last_log.cumulative_qty if last_log else 0.0

    @api.depends('task_id', 'estimate_id.estimate_date', 'estimate_id.project_id')
    def _compute_available_qty(self):
        """計算本次可估驗數量（本期完成量）

        本期 = 累計到(本次估驗日) − 累計到(前一張估驗單估驗日)
        前一張：同工程、估驗日較早、排除自己，依日期取最近一筆（不論狀態）。
        彙總項採「一式」慣例固定回 1。
        """
        for line in self:
            if line.is_summary_item:
                line.available_qty = 1.0
                continue
            if not line.task_id or not line.estimate_id.estimate_date:
                line.available_qty = 0.0
                continue
            this_date = line.estimate_id.estimate_date
            cumulative_to_date = self._get_cumulative_qty_at(line.task_id, this_date)

            # 🔴 「前一張」要用 _previous_estimate()，不能用 domain 的
            #    `estimate_date <`：同一天可能有好幾期（補建歷史資料時是常態），
            #    嚴格小於在同日時整組落空 → 本期可估量算成「從頭到現在的累計」。
            prev_estimate = line.estimate_id._previous_estimate()
            prev_cumulative = 0.0
            if prev_estimate:
                prev_cumulative = self._get_cumulative_qty_at(
                    line.task_id, prev_estimate.estimate_date
                )
            line.available_qty = cumulative_to_date - prev_cumulative

    def _get_descendant_leaf_lines(self):
        """取得同一估驗單中，屬於本彙總項底下的所有葉節點明細行"""
        self.ensure_one()
        if not self.task_id or not self.estimate_id:
            return self.browse()
        descendant_ids = set(self.env['project.task'].search([
            ('id', 'child_of', self.task_id.id),
        ]).ids)
        return self.estimate_id.line_ids.filtered(
            lambda l: l.task_id.id in descendant_ids and not l.is_summary_item
        )

    def _get_effective_amount(self):
        """本行實際採用的「本次估驗金額」：手動輸入優先於 單價 × 本次估驗數量。

        彙總項不適用手動覆寫（其金額恆為底下葉節點之和），故只看葉節點旗標。
        刻意讀原始欄位（is_amount_manual / manual_estimate_amount / unit_price /
        estimate_qty）而非計算欄位 estimate_amount，避免彙總項計算時讀到葉節點的舊值。
        """
        self.ensure_one()
        if self.is_amount_manual and not self.is_summary_item:
            return self.manual_estimate_amount
        return self.unit_price * self.estimate_qty

    @api.depends('estimate_qty', 'unit_price', 'is_summary_item',
                 'is_amount_manual', 'manual_estimate_amount',
                 'estimate_id.line_ids.estimate_qty',
                 'estimate_id.line_ids.unit_price',
                 'estimate_id.line_ids.is_amount_manual',
                 'estimate_id.line_ids.manual_estimate_amount')
    def _compute_amounts(self):
        """計算本次估驗金額（彙總項加總底下葉節點，避免重複計算）

        葉節點若標記為手動輸入，一律沿用手動值（手動優先於系統計算）。
        """
        for line in self:
            if line.is_summary_item:
                leaf_lines = line._get_descendant_leaf_lines()
                line.estimate_amount = sum(
                    l._get_effective_amount() for l in leaf_lines
                )
            else:
                line.estimate_amount = line._get_effective_amount()

    @api.onchange('estimate_amount')
    def _onchange_estimate_amount(self):
        """使用者在表單／清單直接改金額 → 立即標記為手動並記下該值。

        必須在 onchange 就標記：估驗計價表是 editable list，使用者可能先改金額再改
        數量，若等到存檔才標記，中途的 _compute_amounts 會把剛輸入的金額蓋掉。
        """
        for line in self:
            if line.is_summary_item:
                continue
            # ⚠ 先把使用者輸入的值讀進區域變數再動其他欄位：estimate_amount 的
            #   @api.depends 含 is_amount_manual，一旦先設旗標，下一次讀
            #   estimate_amount 會觸發重算（此時 manual_estimate_amount 還是 0）
            #   而讀回 0，把使用者剛輸入的金額吃掉。
            typed = line.estimate_amount
            auto = line.unit_price * line.estimate_qty
            if float_compare(typed, auto, precision_digits=2) == 0:
                # 與系統計算值相同 → 視為未覆寫（也讓使用者能「改回計算值」而解除手動）
                line.is_amount_manual = False
                line.manual_estimate_amount = 0.0
            else:
                line.manual_estimate_amount = typed
                line.is_amount_manual = True
                line.estimate_amount = typed

    @api.onchange('is_amount_manual')
    def _onchange_is_amount_manual(self):
        """取消勾選「金額手動輸入」→ 即時還原為系統計算值"""
        for line in self:
            if not line.is_amount_manual:
                line.manual_estimate_amount = 0.0
                line.estimate_amount = line.unit_price * line.estimate_qty

    # === CRUD 覆寫：任何寫入 estimate_amount 的路徑都視為手動覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'estimate_amount' in vals and 'is_amount_manual' not in vals:
                vals['is_amount_manual'] = True
                vals['manual_estimate_amount'] = vals['estimate_amount']
        return super().create(vals_list)

    def write(self, vals):
        """手動寫入金額時同步記錄手動值。

        計算欄位由 ORM 直接落庫（不經 write），故此處只會攔到人工／程式的顯式寫入。
        """
        if 'estimate_amount' in vals and 'manual_estimate_amount' not in vals:
            vals = dict(vals)
            vals.setdefault('is_amount_manual', True)
            if vals['is_amount_manual']:
                vals['manual_estimate_amount'] = vals['estimate_amount']
        return super().write(vals)

    @api.depends('task_id', 'is_summary_item',
                 'estimate_id.project_id', 'estimate_id.estimate_date')
    def _compute_previous_approved_qty(self):
        """前期已核定累計數量：估驗日期「早於本次」且已核定的估驗單合計。

        以 estimate_date 作為先後判定（次數是「數量+1」不代表時間先後，日期最保險）。
        本值不依賴本次 estimate_qty，故在估驗表即時編輯時保持穩定，
        累計欄位得以純算術（前期 + 本次）即時重算。非儲存：他單核定後重讀即更新。
        """
        # `_estimates_before()` 每次都要 search 一次工程底下的所有估驗單。
        # 這個 compute 是**逐列**跑的（一張估驗單動輒上百列），不快取的話
        # 一次重算就是上百次相同的查詢。以估驗單為鍵快取，一張單只查一次。
        before_cache = {}
        for line in self:
            est = line.estimate_id
            if (line.is_summary_item or not line.task_id
                    or not est.project_id or not est.estimate_date):
                line.previous_approved_qty = 0.0
                continue
            # 🔴 「前期」用 _estimates_before()（與畫面上的「第N次」同一套排序），
            #    不能用 domain 的 `estimate_date <`：**同一天可能有好幾期**
            #    （補建歷史資料時一天建十幾期是常態），嚴格小於在同日時整組落空
            #    → 前期累計變 0、累計估驗數量與金額跟著錯，而且**不會報任何錯**。
            #    實測：同日兩期各估 30 / 20，第2期累計算成 20（應為 50）。
            # archived 是「已核定後歸檔」，其數量仍為有效核定量，須一併計入前期累計，
            # 否則前期估驗一歸檔，後期累計就會漏掉該期數量。
            if est.id not in before_cache:
                before_cache[est.id] = est._estimates_before().filtered(
                    lambda e: e.state in ('approved', 'archived'))
            before = before_cache[est.id]
            if not before:
                line.previous_approved_qty = 0.0
                continue
            prev_lines = self.search([
                ('task_id', '=', line.task_id.id),
                ('estimate_id', 'in', before.ids),
            ])
            line.previous_approved_qty = sum(prev_lines.mapped('estimate_qty'))

    @api.depends('estimate_qty', 'unit_price', 'previous_approved_qty', 'is_summary_item',
                 'is_amount_manual', 'manual_estimate_amount',
                 'estimate_id.line_ids.estimate_qty',
                 'estimate_id.line_ids.unit_price',
                 'estimate_id.line_ids.previous_approved_qty',
                 'estimate_id.line_ids.is_amount_manual',
                 'estimate_id.line_ids.manual_estimate_amount')
    def _compute_cumulative(self):
        """計算累計估驗數量與金額（純算術，即時更新）

        葉節點：累計數量 = 前期已核定累計 + 本次；
                累計金額 = 單價 × 前期累計數量 + 本次估驗金額
                （本次金額走 _get_effective_amount，故手動金額會反映到累計；
                  未手動時等同舊式 單價 × 累計數量）。
        彙總項：數量採「一式」固定 1；金額 = 底下葉節點同式之和
                （直接讀葉節點原始欄位算術，不讀其計算欄位，避免計算順序造成讀到舊值）。
        """
        for line in self:
            if line.is_summary_item:
                leaf_lines = line._get_descendant_leaf_lines()
                line.cumulative_estimate_qty = 1.0
                line.cumulative_estimate_amount = sum(
                    l.unit_price * l.previous_approved_qty + l._get_effective_amount()
                    for l in leaf_lines
                )
                continue
            line.cumulative_estimate_qty = line.previous_approved_qty + line.estimate_qty
            line.cumulative_estimate_amount = (
                line.unit_price * line.previous_approved_qty
                + line._get_effective_amount()
            )

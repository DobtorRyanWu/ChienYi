# -*- coding: utf-8 -*-
"""新增估驗非契約工項（精靈）

概念與操作方式比照契約變更那一套：
    契約變更單 ▸ 匯入工程案件精靈 ▸ 工項列表頁籤 ▸ [新增工項] 按鈕 → form dialog
    （construction_contract_change/wizards/contract_change_wizard.py:822
      action_add_new_line ＋ contract_change_wizard_views.xml:217 的 dialog）

為什麼**不能**用「在明細列的 Many2one 下拉打字快速建立」：
新專案裡這些工項在契約工項建立時根本不存在，所以流程是「先無中生有地建出來」。
把入口做成 M2O 下拉，等於要使用者先去一個必然是空的清單裡找，找不到才發現可以打字新建 ——
順序是反的，而且完全看不出「這裡可以建彙總層與子項」。

填的欄位與契約變更不同（那邊要處理原值／新值／變更類型，這邊沒有「原值」可言）：
    基本資訊：父項、識別碼、項目編號、項目名稱、單位
    本期量價：計入估驗總額、單價、本次數量、本次金額
"""

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class EstimateExtraItemWizard(models.TransientModel):
    _name = 'estimate.extra.item.wizard'
    _description = '新增估驗非契約工項'

    estimate_id = fields.Many2one(
        'payment.estimate',
        string='估驗單',
        required=True,
        readonly=True,
        ondelete='cascade')

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        related='estimate_id.project_id',
        readonly=True)

    # 比照契約變更的 is_new_group：彙總層是「容器」，本身沒有量價。
    # 這裡不能用 extra.item 的 is_summary_item（那是由「有沒有子項」推導的），
    # 因為建「參 變賣收入項」的當下它還沒有子項。
    is_group = fields.Boolean(
        string='這是彙總項（容器）',
        default=False,
        help='勾選：本項是「參 變賣收入項」這種只用來裝子項的彙總層，本身不填數量與金額\n'
             '（金額自動等於底下子項合計）。建好之後再建子項、把父項指向它。\n'
             '\n'
             '不勾：本項自己就是一個金額列。注意**頂層不一定是彙總層** ——\n'
             '「貳 第N次估驗物價調整累計金額」就是沒有子項的頂層、單位「式」、直接填金額。')

    # 🔴 只能挑「本期估驗單上真的有的」項目當父工項。
    #    原本 domain 是整個工程的項目，於是在本期已經刪掉的列照樣出現在下拉裡
    #    （使用者實測回報）。掛到一個本期沒有的父項也沒有意義 —— 版面上會是孤兒。
    allowed_parent_ids = fields.Many2many(
        'payment.estimate.extra.item',
        string='可選的父工項',
        compute='_compute_allowed_parent_ids')

    parent_item_id = fields.Many2one(
        'payment.estimate.extra.item',
        string='父工項',
        help='留空 ＝ 新增最高層項目（參、貳…）。\n'
             '只列得出**本期估驗單上已經有的**項目 —— 要建子項，'
             '請先把父工項那一列建出來（勾「這是彙總項」），再回來選它。')

    @api.depends('estimate_id')
    def _compute_allowed_parent_ids(self):
        for wiz in self:
            wiz.allowed_parent_ids = wiz.estimate_id.extra_line_ids.mapped(
                'extra_item_id')

    code = fields.Char(
        string='識別碼',
        help='🔴 這是**跨期身分**：「沿用到下一期」與「累計」都認它，不認名稱。\n'
             '留空時由工項名稱自動產生。\n'
             '名稱逐期會變的項目（例：貳 第7次… → 第8次…估驗物價調整累計金額）\n'
             '一定要每期用同一個識別碼，否則累計鏈會斷成每期一筆。\n'
             '建議取穩定的英數鍵，例：SALVAGE、SALVAGE.1、PRICE_ADJ。')

    item_no = fields.Char(
        string='項目編號',
        help='估驗詳細表上印的編號，例：參、1。純顯示用，不參與計算。')

    # 不設 required=True：走「選用已建立的項目」頁籤時不需要填名稱。
    # 兩條路擇一，由 action_add 驗。
    item_name = fields.Char(
        string='項目名稱',
        help='估驗表上要印的名稱。\n'
             '⚠️ 名稱是**每期各存一份**的：這裡填的會同時成為工項定義的名稱與'
             '本期的名稱；之後某一期要印不同的字，直接在該期的清單上改「項目名稱」即可，'
             '不會影響其他期別，也**不要為此另建一個項目**（那會讓累計鏈斷掉）。\n'
             '例：「貳 第8次估驗物價調整累計金額」每期文字都不同，逐期改就好。')

    unit = fields.Char(string='單位')

    # === 本期量價（存在明細列上，只屬於這一期）===
    include_in_subtotal = fields.Boolean(
        string='計入估驗總額',
        default=True,
        help='勾：本項金額加進「本次估驗總金額」（例：貳 物價調整，實務上照樣扣保留款）。\n'
             '不勾：只登錄在估驗表上、不進總額（例：參 變賣收入項 —— 有價廢料變賣的錢\n'
             '　　　另走解繳鏈，不在本期核發金額的算式裡）。\n'
             '\n'
             '⚠️ 本欄只影響「本次估驗總金額」。契約附註另一種收取方式「由工程估驗款\n'
             '內扣抵」（本期應扣金額）本系統目前沒有承載欄位，表達不了，不要用本欄硬湊。')

    unit_price = fields.Float(
        string='本期單價',
        digits=(16, 2),
        help='只屬於這一期。單價逐期變動時（例：第8期 500 → 第11期 600），'
             '各期各填各的，不會回頭改到已核定的舊期。')

    estimate_qty = fields.Float(
        string='本次數量',
        digits=(16, 4))

    estimate_amount = fields.Float(
        string='本次金額',
        digits=(16, 2),
        compute='_compute_estimate_amount',
        store=True,
        readonly=False,
        help='預設為 本期單價 × 本次數量。對不起來時直接改這裡（會被記成手動金額）。\n'
             '🔴 一律填來源估驗詳細表印的**正數** —— 變賣收入雖然是廠商付錢給機關，\n'
             '來源表印的也是正數，方向由「計入估驗總額」表達。')

    @api.depends('unit_price', 'estimate_qty')
    def _compute_estimate_amount(self):
        for wiz in self:
            wiz.estimate_amount = round(wiz.unit_price * wiz.estimate_qty, 2)

    # === 「選用已建立的項目」頁籤 ==========================================
    # 本工程其他期別建過、但**本期還沒有**的項目。這是「誤刪之後加回來」
    # 唯一需要的入口，而且它是**看得見的** ——
    # 1.6.4 用「封存 ＋ 用同一個識別碼復活」來解這件事是錯的方向：
    # 封存＝看不見也改不動的隱藏狀態，實測累積出 5 筆封存定義、3 筆同名、
    # 「預設計入」互相矛盾，使用者完全無從察覺與修正。
    selectable_item_ids = fields.Many2many(
        'payment.estimate.extra.item',
        'estimate_extra_wizard_selectable_rel', 'wizard_id', 'item_id',
        string='本工程已建立的項目',
        compute='_compute_selectable_item_ids')

    existing_item_ids = fields.Many2many(
        'payment.estimate.extra.item',
        'estimate_extra_wizard_pick_rel', 'wizard_id', 'item_id',
        string='選用這些項目',
        help='把本工程其他期別建過的項目加進本期（本次數量 0，'
             '單價與計入旗標沿用最近一期）。')

    @api.depends('estimate_id')
    def _compute_selectable_item_ids(self):
        Item = self.env['payment.estimate.extra.item']
        for wiz in self:
            if not wiz.estimate_id.project_id:
                wiz.selectable_item_ids = Item.browse()
                continue
            used = wiz.estimate_id.extra_line_ids.mapped('extra_item_id').ids
            wiz.selectable_item_ids = Item.search([
                ('project_id', '=', wiz.estimate_id.project_id.id),
                ('id', 'not in', used),
            ])

    @api.onchange('is_group')
    def _onchange_is_group(self):
        """彙總項沒有自己的量價（金額是子項合計）"""
        for wiz in self:
            if wiz.is_group:
                wiz.unit_price = 0.0
                wiz.estimate_qty = 0.0
                wiz.estimate_amount = 0.0
                if not wiz.unit:
                    wiz.unit = '式'

    @api.onchange('parent_item_id')
    def _onchange_parent_item_id(self):
        """挑了父項就沿用它的單位，並**強制繼承彙總項的「計入估驗總額」**。

        計入與否是整個彙總項一起決定的（同一彙總項底下一部分計入、一部分不計入
        在實務上不成立），所以有父項時這一欄不讓填，直接跟著父項走。
        """
        for wiz in self:
            if not wiz.parent_item_id:
                continue
            if not wiz.unit:
                wiz.unit = wiz.parent_item_id.unit
            # 🔴 只認「父工項在本期的那一列」。
            #    下拉本來就只列本期有的項目，所以這一列必然存在。
            #    早期還有一個「找不到就退回工項定義的預設值」的分支 —— 那是錯的：
            #    定義上的旗標只是「建新期別時的預設」，而且使用者看不到它，
            #    於是會發生「我明明關掉了，按下新增卻自動勾起來」（使用者實測回報）。
            parent_line = wiz.estimate_id.extra_line_ids.filtered(
                lambda l: l.extra_item_id == wiz.parent_item_id)
            if parent_line:
                wiz.include_in_subtotal = parent_line[0].include_in_subtotal

    def action_add(self):
        """確認新增：建立工項定義（工程層級）＋ 本期明細列。

        一次建兩筆是刻意的 —— 定義要活在工程層級才沿用得到下一期，
        明細列才是「這一期的量價」。詳見 models/payment_estimate_extra.py 的說明。
        """
        self.ensure_one()
        estimate = self.estimate_id
        if not estimate.project_id:
            raise UserError('這張估驗單還沒有所屬工程，請先「匯入工程案件」。')
        if estimate.state not in ('draft', 'pending_approval'):
            raise UserError('只有草稿／待核定的估驗單可以新增非契約工項。')
        if self.parent_item_id and self.parent_item_id.project_id != estimate.project_id:
            raise UserError('父項屬於別的工程，不能跨工程掛靠。')

        Item = self.env['payment.estimate.extra.item']
        Line = self.env['payment.estimate.extra.line']
        max_seq = max(estimate.extra_line_ids.mapped('sequence') or [0])

        # ── 路徑二：選用本工程已建立的項目（不新建定義）──────────────────
        if self.existing_item_ids:
            if self.item_name:
                raise UserError(
                    '兩種方式只能擇一：\n'
                    '要「選用已建立的項目」，請把「建立新項目」頁籤的項目名稱清空；\n'
                    '要建新的，請把「選用已建立的項目」頁籤的勾選取消。')
            picked = self.existing_item_ids.sorted(key=lambda i: (i.item_level, i.sequence, i.id))
            vals = []
            for offset, item in enumerate(picked):
                vals.append(dict(
                    Line._prepare_line_vals(item, estimate, max_seq + 10 * (offset + 1)),
                    estimate_id=estimate.id))
            Line.create(vals)
            return {'type': 'ir.actions.act_window_close'}

        # ── 路徑一：建立新項目 ────────────────────────────────────────────
        if not self.item_name:
            raise UserError(
                '請填「建立新項目」頁籤的項目名稱，'
                '或在「選用已建立的項目」頁籤挑要加進本期的項目。')
        code = (self.code or '').strip()

        # 🔴 有父工項 → 計入旗標**在這裡**強制繼承父列，不是只靠 onchange。
        #
        # onchange 只在使用者於畫面上操作時才跑；直接呼叫 create()＋action_add()
        # （匯入、測試、任何程式路徑）完全不會經過它，於是 include_in_subtotal
        # 留在欄位預設值 True，接著就撞上 _check_include_matches_parent。
        # 使用者實測回報的「我明明關掉了，按下新增卻自動勾起來 → 驗證錯誤」
        # 就是這一類：真正的權威必須放在寫入端。
        include = self.include_in_subtotal
        if self.parent_item_id:
            parent_line = estimate.extra_line_ids.filtered(
                lambda l: l.extra_item_id == self.parent_item_id)
            if not parent_line:
                raise UserError(
                    f'父工項「{self.parent_item_id.name}」在本期估驗單上沒有對應的列，'
                    f'不能掛在它底下。\n'
                    f'請先把父工項那一列加進本期（新增，或用「選用已建立的項目」）。')
            include = parent_line[0].include_in_subtotal

        item_vals = {
            'project_id': estimate.project_id.id,
            'name': self.item_name,
            'parent_id': self.parent_item_id.id or False,
            'item_no': self.item_no,
            'unit': self.unit,
            # 工項定義上的單價與旗標是「建新期別時的預設值」，實際值存在明細列
            'unit_price': 0.0 if self.is_group else self.unit_price,
            'include_in_subtotal': include,
            'sequence': max_seq + 10,
        }

        # 同識別碼已經有人在用 → 擋（重新新增會讓累計鏈斷成兩筆）。
        # 18.0.1.7.0 起沒有「封存」狀態了，所以這裡不需要再處理「復活」——
        # 沒人用的定義在明細列被刪掉時就一併刪掉了，
        # 「本期想加回別期在用的項目」改走「選用已建立的項目」頁籤。
        if code:
            live = Item.search([('project_id', '=', estimate.project_id.id),
                                ('code', '=', code)], limit=1)
            if live:
                raise UserError(
                    f'識別碼「{code}」在本工程已經有一個非契約工項在用了'
                    f'（{live.name}）。\n'
                    f'如果這一期要沿用同一項，請改用「選用已建立的項目」頁籤，'
                    f'不要重新新增（重新新增會讓累計鏈斷成兩筆）。')

        item = Item.create(dict(item_vals, code=code or False))
        # code 留空時由 create() 依名稱自動產生

        line_vals = {
            'estimate_id': estimate.id,
            'extra_item_id': item.id,
            'sequence': max_seq + 10,
            'name': self.item_name,
            'unit_price': 0.0 if self.is_group else self.unit_price,
            'estimate_qty': 0.0 if self.is_group else self.estimate_qty,
            'include_in_subtotal': include,
        }
        # 金額只在「與 單價 × 數量 對不起來」時才明寫 —— 寫進去就會被記成手動金額
        # （沿用 payment.estimate.line 同一套慣例），整批列都標成手動會讓日後改
        # 數量單價時這些列不跟著動，反而變成錯的。
        if not self.is_group:
            auto = round(self.unit_price * self.estimate_qty, 2)
            if float_compare(self.estimate_amount, auto, precision_digits=2) != 0:
                line_vals['estimate_amount'] = self.estimate_amount
        self.env['payment.estimate.extra.line'].create(line_vals)

        # 關閉對話框；呼叫端的估驗單表單會自動重新載入
        return {'type': 'ir.actions.act_window_close'}

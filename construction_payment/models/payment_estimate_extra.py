# -*- coding: utf-8 -*-
"""估驗計價的「非契約工項」

為什麼要有這兩個模型
--------------------
估驗詳細表的頂層不是只有「壹 發包工程費」（契約工項的加總）。政府工程的估驗表上
固定還會出現契約工項樹裡沒有的項目，實案（士林區通河東街1段排水改善工程 111-20-AEF）
13 期的每一期末頁長這樣：

    壹  發包工程費                    ← 契約工項的加總
    貳  第N次估驗物價調整累計金額  式  ← 不是契約工項，但**要**計入
    總計                              ← 壹 + 貳
    參  變賣收入項                     ← 不是契約工項，**不**計入（另走解繳鏈）

「參 變賣收入項」（有價廢料變賣）在契約詳細價目表裡只寫在附註第 1 條，不是工項列；
第 1／2 次變更明細表也沒有它；但估驗詳細表、計價單封面、結算明細表上都有。
「貳 物價調整」則是依物價指數算出來的工程款調整，照樣扣 5% 保留款。
兩者在同一張表上並存而行為相反，所以「是否計入總額」必須是一個真的可選的欄位。

🔴 為什麼不寫進 project.task
---------------------------
project.task 是契約金額的真相載體。把非契約工項寫進去（哪怕只加一個旗標）會污染
契約總價、契約變更的原金額計算、匯入預檢的契約金額鏈、以及採購法第 22 條的累計變更
比例。而且專案一「開始施工」，契約工項就全面唯讀
（construction_supervision_base/models/project_task.py:620-627 加上 view 裡 15 處
readonly="is_project_approved"，沒有任何 group 例外）—— 走那條路在已開工的專案上
根本寫不進去。所以這裡一律是獨立的新模型。

為什麼要拆成「項目」與「明細」兩層
--------------------------------
payment.estimate.line 是「契約工項 × 期別」的鏡像，它靠 task_id 當跨期身分，
前期累計與累計估驗都是從 task_id 聚合出來的。非契約工項如果只存在於某一期的明細列
上，就沒有跨期身分，累計算不出來、也沿用不了。所以比照同一個形狀拆兩層：

    payment.estimate.extra.item   工程層級的清單（自參照階層，跨期身分＝code）
            ↑ extra_item_id
    payment.estimate.extra.line   某一期對某一項的估驗（本次數量／本次金額）
            ↑ estimate_id
    payment.estimate

🔴 身分鍵是 `code`，不是名稱
---------------------------
「貳」那一列的顯示名稱**每一期都不一樣**（第7次…／第8次…／第11次估驗物價調整累計金額）。
用名稱當跨期身分會變成每期一個新項目、累計鏈直接斷掉。所以名稱是每期可變的顯示值
（存在明細列的 name，每期各存一份），身分另外存在項目的 code 上。
"""

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class PaymentEstimateExtraItem(models.Model):
    """估驗非契約工項（工程層級的定義，跨期共用）"""
    _name = 'payment.estimate.extra.item'
    _description = '估驗非契約工項'
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'name'

    _sql_constraints = [
        ('unique_project_code',
         'UNIQUE (project_id, code)',
         '同一工程的非契約工項識別碼（code）不能重複。'),
    ]

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True)

    # 🔴 跨期身分。顯示名稱逐期會變（第7次… → 第8次…），沿用與累計一律認這一欄。
    code = fields.Char(
        string='識別碼',
        required=True,
        copy=False,
        help='這一項在本工程內的跨期身分鍵（同一工程內唯一）。\n'
             '「沿用到下一期」與「累計」都認這一欄，不認名稱 —— 因為顯示名稱逐期會變\n'
             '（例：貳 第7次估驗物價調整累計金額 → 第8次…）。留空時由名稱自動產生。')

    name = fields.Char(
        string='工項名稱',
        required=True,
        help='這一項的通用名稱。某一期若要印成別的字，在該期明細列填「本期顯示名稱」，\n'
             '不要為了改名而另外建一個項目（那會讓累計鏈斷掉）。')

    parent_id = fields.Many2one(
        'payment.estimate.extra.item',
        string='父工項',
        ondelete='cascade',
        index=True,
        domain="[('project_id', '=', project_id), ('id', '!=', id)]",
        help='彙總項（例：參 變賣收入項）。頂層留空。')

    # _parent_store 的索引欄。不要加 unaccent=False —— Odoo 18 對 Char 不吃這個參數，
    # 只會每次載入都印一行 warning（construction_supervision_base 的
    # supervision.folder.parent_path 就是這樣長年在噴）。
    parent_path = fields.Char(index=True)

    child_ids = fields.One2many(
        'payment.estimate.extra.item',
        'parent_id',
        string='子項')

    sequence = fields.Integer(string='序號', default=10)

    item_no = fields.Char(
        string='項目編號',
        help='估驗詳細表上印的編號，例：參、1。純顯示用，不參與任何計算。')

    unit = fields.Char(string='單位')

    # 🔴 這是「預設單價」，不是每一期實際採用的單價。
    #
    # 為什麼要分開：同一個非契約工項的單價會逐期變動（實例：「XXX回收」第8期 500、
    # 第11期 600，是同一個工項）。若把單價做成明細列 related 到這裡，改第 11 期會
    # 連帶把**已核定的第 8 期**金額重算成 600 × 數量 —— 舊期的錢被靜靜改掉。
    # 所以每一期的實際單價存在該期的明細列上（快照），這裡只提供建新期別時的預設值。
    # 這與契約工項那條路完全同一套規則：payment.estimate.line.unit_price 也是
    # `_prepare_line_vals` 在建列當下從 task 抄一次的快照，契約單價之後再變也不回頭改舊期。
    unit_price = fields.Float(
        string='預設單價',
        digits=(16, 2),
        help='建立新期別明細時帶入的預設單價。\n'
             '⚠️ 每一期實際採用的單價存在該期的明細列上（快照），改這裡**不會**動到已建立的期別。\n'
             '單價逐期變動時（例：第8期 500 → 第11期 600），直接改該期明細列的單價即可；\n'
             '再往下一期「帶入」時會沿用最近一期的單價，不是這裡的值。')

    # 🔴 R3：這個開關必須是真的可選的。同一張估驗詳細表上兩種非契約工項行為相反 ——
    #     「貳 物價調整」計入、「參 變賣收入項」不計入。所以預設值刻意跟一般工項一致
    #     （計入），不要因為變賣收入是「不計入」就把預設寫死成不計入。
    #     與 unit_price 同理，這裡是**預設值**，每一期實際的旗標存在該期明細列上 ——
    #     否則改一次旗標會把所有已核定期別的估驗總金額一起重算。
    include_in_subtotal = fields.Boolean(
        string='預設計入估驗總額',
        default=True,
        help='勾選：本項金額加進估驗單的「本次估驗總金額」（例：貳 物價調整）。\n'
             '不勾：只登錄在估驗表上，不進總額（例：參 變賣收入項 —— 有價廢料變賣\n'
             '　　　的錢另走解繳鏈，不在核發金額的算式裡）。\n'
             '\n'
             '⚠️ 本欄目前只影響「本次估驗總金額」。契約附註常見的另一種收取方式\n'
             '「由工程估驗款內扣抵」（本期應扣金額）在本系統裡還沒有承載的欄位\n'
             '（payment.estimate 上只有 subtotal，沒有保留款／核發金額／應扣金額），\n'
             '所以那一種情境目前表達不了，不要用本欄硬湊。')

    is_summary_item = fields.Boolean(
        string='彙總項',
        compute='_compute_is_summary_item',
        store=True,
        help='有子項的父項。金額為子項合計，不自行填數量與金額。')

    item_level = fields.Integer(
        string='層級',
        compute='_compute_item_level',
        recursive=True,
        store=True,
        help='0＝頂層（參）、1＝子項（參.1）…')

    full_item_path = fields.Char(
        string='完整路徑',
        compute='_compute_full_item_path',
        recursive=True)

    note = fields.Text(string='備註')

    line_ids = fields.One2many(
        'payment.estimate.extra.line',
        'extra_item_id',
        string='各期明細')

    @api.depends('child_ids')
    def _compute_is_summary_item(self):
        for item in self:
            item.is_summary_item = bool(item.child_ids)

    @api.depends('parent_id', 'parent_id.item_level')
    def _compute_item_level(self):
        for item in self:
            item.item_level = (item.parent_id.item_level + 1) if item.parent_id else 0

    @api.depends('name', 'item_no', 'parent_id', 'parent_id.full_item_path')
    def _compute_full_item_path(self):
        for item in self:
            own = ' '.join(x for x in (item.item_no, item.name) if x)
            parent_path = item.parent_id.full_item_path if item.parent_id else ''
            item.full_item_path = f'{parent_path} > {own}' if parent_path else own

    @api.depends('name', 'item_no')
    def _compute_display_name(self):
        for item in self:
            item.display_name = ' '.join(x for x in (item.item_no, item.name) if x)

    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        # Odoo 18 起 _check_recursion() 已 deprecated（會噴 DeprecationWarning），
        # 正確寫法是 not _has_cycle()
        if self._has_cycle():
            raise ValidationError('非契約工項的父項不可形成循環。')

    @api.constrains('item_no', 'parent_id', 'project_id')
    def _check_item_no_unique_among_siblings(self):
        """同一個父項底下，項目編號不可重複。

        使用者實測時建出了兩個頂層「參」。編號是給人看的定位資訊，同層重複就失去意義。
        範圍刻意是「同一父項底下」而不是「整個工程」：
        「參」底下有個「1」、「肆」底下也有個「1」是正常的，不該擋。
        留空不檢查（編號本來就可以不填）。
        已封存的項目不算（search 預設就排除），否則刪掉再建同編號會被自己擋住。
        """
        for item in self:
            if not (item.item_no or '').strip():
                continue
            dup = self.search([
                ('project_id', '=', item.project_id.id),
                ('parent_id', '=', item.parent_id.id or False),
                ('item_no', '=', item.item_no),
                ('id', '!=', item.id),
            ], limit=1)
            if dup:
                where = (f'「{item.parent_id.name}」底下' if item.parent_id
                         else '最高層')
                raise ValidationError(
                    f'{where}已經有一個項目編號「{item.item_no}」了'
                    f'（{dup.name}）。\n\n'
                    f'同一層的項目編號不可以重複。不同層可以 —— '
                    f'例如「參」底下有「1」、「肆」底下也有「1」是正常的。')

    @api.constrains('parent_id', 'project_id')
    def _check_parent_same_project(self):
        for item in self:
            if item.parent_id and item.parent_id.project_id != item.project_id:
                raise ValidationError(
                    f'非契約工項「{item.name}」的父項屬於別的工程，不能跨工程掛靠。')

    @api.model_create_multi
    def create(self, vals_list):
        """code 留空時由名稱自動產生（同一工程內去重）。"""
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self._make_code(vals.get('project_id'),
                                               vals.get('name') or '')
        return super().create(vals_list)

    @api.model
    def _make_code(self, project_id, name):
        """由名稱自動產生識別碼（同一工程內唯一）。

        18.0.1.7.0 起沒有「封存」狀態了（沒人用的定義直接刪掉），所以
        `search_count()` 看到的就是全部，不會再有「ORM 看不到但 UNIQUE 看得到」的落差。
        （1.6.5 那次事故就是這個落差造成的：`_make_code` 產生撞號的 code，
        撞出 `psycopg2.UniqueViolation`，使用者只看到看不懂的原始 SQL 錯誤。）
        """
        base = (name or '').strip() or 'extra'
        code = base
        suffix = 1
        Item = self
        while Item.search_count([('project_id', '=', project_id),
                                 ('code', '=', code)]):
            suffix += 1
            code = f'{base}-{suffix}'
        return code


class PaymentEstimateExtraLine(models.Model):
    """估驗非契約工項明細（某一期對某一項的估驗）"""
    _name = 'payment.estimate.extra.line'
    _description = '估驗非契約工項明細'
    _order = 'sequence, id'

    _sql_constraints = [
        ('unique_estimate_item',
         'UNIQUE (estimate_id, extra_item_id)',
         '同一期估驗單中，同一個非契約工項只能有一列。'),
    ]

    estimate_id = fields.Many2one(
        'payment.estimate',
        string='估驗單',
        required=True,
        ondelete='cascade',
        index=True)

    extra_item_id = fields.Many2one(
        'payment.estimate.extra.item',
        string='非契約工項',
        required=True,
        ondelete='cascade',
        index=True)

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        related='estimate_id.project_id',
        store=True,
        readonly=True)

    sequence = fields.Integer(string='序號', default=10)

    # 🔴 名稱也是「每期各存一份的快照」，與 unit_price 同一套規則。
    #
    # 為什麼不做成「工項名稱 ＋ 本期顯示名稱」兩欄：那等於把內部實作攤給使用者看，
    # 清單上並排兩個名稱欄，沒有人知道哪一個才是對的（使用者實測時直接指出這一點）。
    # 而且那也跟 unit_price 的做法不一致 —— 同樣是「逐期會變的東西」，
    # 不該一個走快照、一個走覆寫。
    #
    # 現在只有這一個名稱欄：
    #   ・建立時從工項定義的名稱帶入
    #   ・「帶入下一期」時沿用**最近一期**的名稱（「第7次…」→ 只要改一個數字）
    #   ・在任一期改它只影響那一期，其他期別與工項定義都不動
    # 跨期身分自始至終是 extra_item_id / code，跟名稱無關，所以逐期改名累計鏈不會斷。
    name = fields.Char(
        string='項目名稱',
        required=True,
        help='本期估驗表上要印的名稱。**只屬於這一期**，改它不會動到其他期別。\n'
             '例：「貳 第8次估驗物價調整累計金額」每期文字都不同，逐期改這一欄即可，'
             '項目本身仍是同一個（累計鏈綁的是識別碼，不是名稱）。')

    # 跨期身分鍵（＝匯入工作簿的 _extra_key）。逐欄反查（M5_檢查_逐欄反查.py）
    # 用它當比對鍵 —— 名稱逐期會變，只有 code 是穩定的。
    extra_item_code = fields.Char(
        string='識別碼',
        related='extra_item_id.code',
        store=True,
        readonly=True)

    # === 工項定義的顯示欄位（related、唯讀）===
    # 這幾欄不影響金額，改了只是顯示，所以跟著定義走、在明細列唯讀。
    # 要改請點「非契約工項」欄的連結進工項本身改。
    item_no = fields.Char(
        string='項目編號',
        related='extra_item_id.item_no',
        readonly=True)
    unit = fields.Char(
        string='單位',
        related='extra_item_id.unit',
        readonly=True)
    # store=True：payment.estimate._compute_subtotal 要靠它判斷「哪些列是本期的根」，
    # stored compute 依賴未儲存的 related 會不可靠。
    parent_item_id = fields.Many2one(
        'payment.estimate.extra.item',
        string='父工項',
        related='extra_item_id.parent_id',
        store=True,
        readonly=True)
    is_summary_item = fields.Boolean(
        string='彙總項',
        related='extra_item_id.is_summary_item',
        store=True,
        readonly=True)
    item_level = fields.Integer(
        string='層級',
        related='extra_item_id.item_level',
        store=True,
        readonly=True)

    # === 🔴 本期快照：單價與計入旗標「每一期各存一份」，不是 related ===
    #
    # 為什麼一定要是快照而不是 related 到工項定義：
    # 同一個非契約工項的單價會逐期變動（實例：「XXX回收」第8期 500、第11期 600，
    # 是同一個工項）。如果做成 related，在第 11 期改成 600 會連帶把**已核定的第 8 期**
    # 金額重算成 600 × 數量 —— 一張已核定估驗單的錢被靜靜改掉，而且不會有任何提示。
    # 計入旗標同理：改一次會把所有期別的「本次估驗總金額」一起重算。
    #
    # 這與契約工項那條路是同一套規則：payment.estimate.line 的
    # contract_qty / approved_qty / unit_price 也都是 `_prepare_line_vals`
    # 在建列當下抄一次的快照，契約之後再變也不回頭改舊期。
    #
    # 累計因此走「金額相加」（前期已核定金額 + 本期金額），不是「累計數量 × 單價」，
    # 所以單價中途變動累計依然正確：各期用各期的價。
    unit_price = fields.Float(
        string='本期單價',
        digits=(16, 2),
        help='本期採用的單價（建列時從工項定義帶入，之後只屬於這一期）。\n'
             '單價逐期變動時直接改這裡，不會影響其他期別。')
    # 🔴 計入與否是「整個彙總項一起決定」的，不是逐個子項各自決定。
    #    同一個彙總項底下有些子項計入、有些不計入在實務上不成立
    #    （「參 變賣收入項」整包都不進總額，不會只有其中一個子項不進）。
    #    所以：
    #      ・總金額只加總「本期的根列」（彙總項的金額已經是子項合計）
    #      ・改彙總項的旗標會自動propagate到底下所有子列
    #      ・子列的旗標與父列不同時，_check_include_matches_parent 直接擋下
    include_in_subtotal = fields.Boolean(
        string='計入估驗總額',
        default=True,
        help='本期這一項要不要加進「本次估驗總金額」。\n'
             '勾：例「貳 物價調整」。不勾：例「參 變賣收入項」（另走解繳鏈）。\n'
             '\n'
             '⚠️ 有父項的子列**跟著彙總項走**，不能單獨設定 —— 同一個彙總項底下\n'
             '一部分計入、一部分不計入在實務上不成立。改彙總項那一列即可，\n'
             '底下的子列會自動跟著改。\n'
             '本欄只影響這一期，改了不會動到其他期別。')

    # === 逐期各自獨立的數量與金額 ===
    # 🔴 正負號：一律存來源估驗詳細表印的正數。「參 變賣收入項」印的是正數
    #    （575 × 96 = 55,200），語意雖然是廠商付錢給機關，但收入／支出的方向由
    #    「計入估驗總額」與項目本身表達，不靠正負號。存負數會與來源表對不起來。
    estimate_qty = fields.Float(
        string='本次數量',
        digits=(16, 4),
        help='本期的數量。彙總項不填（金額為子項合計）。')

    estimate_amount = fields.Float(
        string='本次金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True,
        readonly=False,
        help='預設為 單價 × 本次數量；可直接手動輸入覆寫（沿用估驗明細同一套慣例：'
             '一旦手動輸入即以手動值為準，不再被系統計算值覆蓋）。\n'
             '🔴 一律填來源估驗詳細表印的正數 —— 變賣收入雖然是廠商付錢給機關，'
             '來源表印的也是正數，方向由「計入估驗總額」表達。')

    is_amount_manual = fields.Boolean(
        string='金額手動輸入',
        default=False,
        help='本次金額由人工輸入（優先於 單價 × 本次數量）')

    manual_estimate_amount = fields.Float(
        string='手動輸入金額',
        digits=(16, 2),
        help='保存人工輸入的金額；計算欄位重算時沿用此值，避免數量或單價變動把手動值蓋掉')

    # === 跨期累計（靠 extra_item_id 聚合，與 payment.estimate.line 靠 task_id 同構）===
    previous_approved_qty = fields.Float(
        string='前期已核定累計數量',
        digits=(16, 4),
        compute='_compute_previous_approved',
        readonly=True,
        help='估驗日期早於本次、且已核定（含已歸檔）的估驗單，本項目的數量合計')
    previous_approved_amount = fields.Float(
        string='前期已核定累計金額',
        digits=(16, 2),
        compute='_compute_previous_approved',
        readonly=True)
    cumulative_estimate_qty = fields.Float(
        string='累計數量',
        digits=(16, 4),
        compute='_compute_cumulative',
        readonly=True)
    cumulative_estimate_amount = fields.Float(
        string='累計金額',
        digits=(16, 2),
        compute='_compute_cumulative',
        readonly=True)

    note = fields.Text(string='備註')

    # === 建立 vals helper（比照 payment.estimate.line._prepare_line_vals）===
    @api.model
    def _prepare_line_vals(self, item, estimate, sequence=10):
        """依非契約工項產生本期明細的 vals（不含 estimate_id）。

        🔴 單價與計入旗標**優先沿用「同一項目最近一期」的值**，而不是工項定義的預設值。
        理由：單價會逐期變動（「XXX回收」第8期 500 → 第11期 600）。第 11 期改成 600 之後，
        第 12 期帶入時應該是 600 而不是回到定義裡的 500 —— 定義那份只是「第一次建立時」
        的預設。找不到前期（第一次出現）才回頭用定義的值。
        """
        # 🔴 「最近一期」＝ payment.estimate._estimates_before() 由後往前找到的
        #    第一個有這個項目的期別。**不能用 domain 的 estimate_date <=** ——
        #    同一天可能有好幾期（補建歷史資料時是常態），日期不足以定序，
        #    `<=` 甚至可能撈到排在本期**後面**的同日期別。
        #    這裡與「帶入上期項目」共用同一套排序，兩邊的「上一期」才會一致。
        prev = self.browse()
        for est in reversed(estimate._estimates_before()):
            hit = est.extra_line_ids.filtered(lambda l: l.extra_item_id == item)
            if hit:
                prev = hit[0]
                break
        return {
            'extra_item_id': item.id,
            'sequence': sequence,
            'estimate_qty': 0.0,
            # 名稱沿用最近一期：「貳 第7次…」→ 下一期只要改一個數字，
            # 比回頭用工項定義的通用名稱好用（要重打整串）
            'name': prev.name if prev else item.name,
            'unit_price': prev.unit_price if prev else item.unit_price,
            'include_in_subtotal': (prev.include_in_subtotal if prev
                                    else item.include_in_subtotal),
        }

    # === 計算 ===
    def _get_descendant_leaf_lines(self):
        """同一估驗單中，屬於本彙總項底下的所有葉節點明細列"""
        self.ensure_one()
        if not self.extra_item_id or not self.estimate_id:
            return self.browse()
        descendant_ids = set(self.env['payment.estimate.extra.item'].search([
            ('id', 'child_of', self.extra_item_id.id),
        ]).ids)
        return self.estimate_id.extra_line_ids.filtered(
            lambda l: l.extra_item_id.id in descendant_ids and not l.is_summary_item
        )

    def _get_effective_amount(self):
        """本列實際採用的金額：手動輸入優先於 單價 × 本次數量。

        刻意讀原始欄位而非計算欄位 estimate_amount，避免彙總項計算時讀到葉節點的舊值
        （與 payment.estimate.line._get_effective_amount 同一套寫法）。
        """
        self.ensure_one()
        if self.is_amount_manual and not self.is_summary_item:
            return self.manual_estimate_amount
        return self.unit_price * self.estimate_qty

    @api.depends('estimate_qty', 'unit_price', 'is_summary_item',
                 'is_amount_manual', 'manual_estimate_amount',
                 'estimate_id.extra_line_ids.estimate_qty',
                 'estimate_id.extra_line_ids.unit_price',
                 'estimate_id.extra_line_ids.is_amount_manual',
                 'estimate_id.extra_line_ids.manual_estimate_amount')
    def _compute_amounts(self):
        for line in self:
            if line.is_summary_item:
                line.estimate_amount = sum(
                    l._get_effective_amount()
                    for l in line._get_descendant_leaf_lines())
            else:
                line.estimate_amount = line._get_effective_amount()

    @api.onchange('estimate_amount')
    def _onchange_estimate_amount(self):
        """在 editable list 直接改金額 → 立即標記為手動並記下該值。

        必須在 onchange 就標記，理由與 payment.estimate.line 相同：使用者可能先改金額
        再改數量，等到存檔才標記的話中途的 _compute_amounts 會把剛輸入的金額蓋掉。
        """
        for line in self:
            if line.is_summary_item:
                continue
            typed = line.estimate_amount
            auto = line.unit_price * line.estimate_qty
            if float_compare(typed, auto, precision_digits=2) == 0:
                line.is_amount_manual = False
                line.manual_estimate_amount = 0.0
            else:
                line.manual_estimate_amount = typed
                line.is_amount_manual = True
                line.estimate_amount = typed

    @api.onchange('is_amount_manual')
    def _onchange_is_amount_manual(self):
        for line in self:
            if not line.is_amount_manual:
                line.manual_estimate_amount = 0.0
                line.estimate_amount = line.unit_price * line.estimate_qty

    @api.model_create_multi
    def create(self, vals_list):
        Item = self.env['payment.estimate.extra.item']
        for vals in vals_list:
            if 'estimate_amount' in vals and 'is_amount_manual' not in vals:
                vals['is_amount_manual'] = True
                vals['manual_estimate_amount'] = vals['estimate_amount']
            # name 是 required：沒給就從工項定義帶入，而不是讓它撞 NOT NULL
            # 丟出 psycopg2.NotNullViolation（那種錯誤訊息完全看不出是缺什麼）。
            # 正常路徑（精靈／帶入上期／匯入步驟 14b）都會給，這是防呆。
            if not vals.get('name') and vals.get('extra_item_id'):
                item = Item.browse(vals['extra_item_id'])
                vals['name'] = item.name or item.code or '（未命名）'
        return super().create(vals_list)

    def write(self, vals):
        if 'estimate_amount' in vals and 'manual_estimate_amount' not in vals:
            vals = dict(vals)
            vals.setdefault('is_amount_manual', True)
            if vals['is_amount_manual']:
                vals['manual_estimate_amount'] = vals['estimate_amount']
        res = super().write(vals)
        # 改了彙總項的「計入」旗標 → 底下所有子列跟著改（見欄位說明）
        if ('include_in_subtotal' in vals
                and not self.env.context.get('_skip_include_propagate')):
            for line in self:
                line._propagate_include_to_children()
        return res

    def _propagate_include_to_children(self):
        """把本列的「計入估驗總額」推給同一期底下的所有子列。

        為什麼要推而不是讓子列自己算：`include_in_subtotal` 是**每期一份的快照**
        （單價逐期會變的那個理由），不能做成 related；所以父子一致要靠寫入時同步，
        再加上 `_check_include_matches_parent` 這道約束當守門。
        """
        self.ensure_one()
        if not self.extra_item_id or not self.estimate_id:
            return
        descendants = self.env['payment.estimate.extra.item'].search([
            ('id', 'child_of', self.extra_item_id.id),
        ]).ids
        descendant_ids = set(descendants) - {self.extra_item_id.id}
        if not descendant_ids:
            return
        targets = self.estimate_id.extra_line_ids.filtered(
            lambda l: l.extra_item_id.id in descendant_ids
            and l.include_in_subtotal != self.include_in_subtotal)
        if targets:
            targets.with_context(_skip_include_propagate=True).write(
                {'include_in_subtotal': self.include_in_subtotal})

    @api.constrains('include_in_subtotal', 'extra_item_id', 'estimate_id')
    def _check_include_matches_parent(self):
        """子列的「計入估驗總額」必須與同一期的父列相同。

        使用者指出的問題：同一個彙總項底下一部分子項計入、一部分不計入，
        在實務上不成立（「參 變賣收入項」整包都不進總額）。而且那種狀態下
        「勾彙總項沒反應、勾子項才有反應」對操作的人是完全反直覺的。
        """
        for line in self:
            parent_item = line.parent_item_id
            if not parent_item or not line.estimate_id:
                continue
            parent_line = line.estimate_id.extra_line_ids.filtered(
                lambda l: l.extra_item_id.id == parent_item.id)
            if not parent_line:
                continue
            if parent_line[0].include_in_subtotal != line.include_in_subtotal:
                raise ValidationError(
                    f'非契約工項「{line.name}」的「計入估驗總額」'
                    f'必須與它的彙總項「{parent_item.name}」相同。\n\n'
                    f'同一個彙總項底下不能一部分計入、一部分不計入 —— '
                    f'請改彙總項那一列，底下的子列會自動跟著改。')

    # 「式」計價：一式就是整批，數量填不到 1 以上
    LUMP_SUM_UNIT = '式'

    @api.constrains('estimate_qty', 'unit', 'is_summary_item')
    def _check_lump_sum_qty(self):
        """「式」工項的本次數量不得超過 1。

        比照 construction_daily_log.daily_log_line._check_lump_sum_not_over_contract：
        只擋「式」，不擋其他單位（超挖／超做是常態，硬擋會讓人填不了）。

        ⚠️ 與日誌那一支的差別：那邊是「累計不得超過**契約量**」，
        這邊沒有契約量可比（非契約工項本來就不在契約裡），所以判準是**逐期 ≤ 1**。
        刻意**不做**跨期累計 ≤ 1 —— 實案「貳 第N次估驗物價調整累計金額」每一期都印
        數量 1（通河東街 111-20-AEF 有 11 期），那不是「一式的工程分期完成」，
        而是每期各自獨立的一筆金額，累計限制套上去會把真實資料整批擋掉。
        """
        for line in self:
            if line.is_summary_item:
                continue                      # 彙總項數量恆為 0，由子項合計
            if (line.unit or '').strip() != line.LUMP_SUM_UNIT:
                continue
            if float_compare(line.estimate_qty, 1.0, precision_digits=4) > 0:
                raise ValidationError(
                    f'非契約工項「{line.name}」的單位是'
                    f'「{line.LUMP_SUM_UNIT}」，本次數量不可超過 1。\n\n'
                    f'目前填的是：{line.estimate_qty}\n\n'
                    f'一式計價請填「本期完成的比例」（例如分 4 期就每期填 0.25），'
                    f'或把數量填 1、直接在「本次金額」填該期的金額。')

    @api.depends('extra_item_id', 'is_summary_item',
                 'estimate_id.project_id', 'estimate_id.estimate_date')
    def _compute_previous_approved(self):
        """前期已核定累計：估驗日期早於本次、且已核定／已歸檔的估驗單合計。

        🔴 聚合的鍵是 extra_item_id，不是名稱 —— 「貳」那一列每期顯示名稱都不同，
        用名稱聚合會讓每一期都變成獨立項目，累計鏈直接斷掉。
        archived 是「已核定後歸檔」，其金額仍為有效核定值，須一併計入（與
        payment.estimate.line._compute_previous_approved_qty 同一個理由）。
        """
        # 與 payment.estimate.line 同理：逐列跑的 compute 不要重複 search
        before_cache = {}
        for line in self:
            est = line.estimate_id
            if (line.is_summary_item or not line.extra_item_id
                    or not est.project_id or not est.estimate_date):
                line.previous_approved_qty = 0.0
                line.previous_approved_amount = 0.0
                continue
            # 🔴 「前期」用 _estimates_before()（與畫面上的「第N次」同一套排序），
            #    不能用 domain 的 `estimate_date <` —— **同一天可能有好幾期**，
            #    嚴格小於在同日時整組落空，累計會靜靜變成 0。
            #    契約工項那條路（payment.estimate.line）原本也有同一個問題，
            #    18.0.1.7.1 一併修掉。
            if est.id not in before_cache:
                before_cache[est.id] = est._estimates_before().filtered(
                    lambda e: e.state in ('approved', 'archived'))
            before = before_cache[est.id]
            if not before:
                line.previous_approved_qty = 0.0
                line.previous_approved_amount = 0.0
                continue
            prev_lines = self.search([
                ('extra_item_id', '=', line.extra_item_id.id),
                ('estimate_id', 'in', before.ids),
            ])
            line.previous_approved_qty = sum(prev_lines.mapped('estimate_qty'))
            line.previous_approved_amount = sum(
                l._get_effective_amount() for l in prev_lines)

    @api.depends('estimate_qty', 'unit_price', 'is_summary_item',
                 'previous_approved_qty', 'previous_approved_amount',
                 'is_amount_manual', 'manual_estimate_amount',
                 'estimate_id.extra_line_ids.estimate_qty',
                 'estimate_id.extra_line_ids.previous_approved_qty',
                 'estimate_id.extra_line_ids.previous_approved_amount',
                 'estimate_id.extra_line_ids.is_amount_manual',
                 'estimate_id.extra_line_ids.manual_estimate_amount')
    def _compute_cumulative(self):
        for line in self:
            if line.is_summary_item:
                leaf_lines = line._get_descendant_leaf_lines()
                line.cumulative_estimate_qty = 0.0
                line.cumulative_estimate_amount = sum(
                    l.previous_approved_amount + l._get_effective_amount()
                    for l in leaf_lines)
                continue
            line.cumulative_estimate_qty = (
                line.previous_approved_qty + line.estimate_qty)
            line.cumulative_estimate_amount = (
                line.previous_approved_amount + line._get_effective_amount())

    def unlink(self):
        """刪掉明細列之後，把「已經沒有任何期別在用」的工項定義**一併刪掉**。

        為什麼是刪掉而不是封存（18.0.1.7.0 改）
        --------------------------------------
        1.6.4 曾經改成「封存」，想留一條誤刪的回頭路。實測下來那是錯的方向：
        封存 ＝ **看不見也改不動的隱藏狀態**，而隱藏狀態配上
        `UNIQUE (project_id, code)` 連續製造了兩次事故 ——
          ・1.6.5：`_make_code()` 看不到封存列 → 產生撞號的 code → 原始 SQL 錯誤
          ・使用者實測：同一個工程累積出 5 筆封存定義、3 筆都叫「廢料變賣」，
            「預設計入」還互相矛盾；新增子項時繼承到哪一筆完全看不出來，
            而且使用者在畫面上一個都看不到、也修不了。

        改成直接刪掉之後**沒有東西會遺失**：定義只在「零明細列」時才會被清掉，
        那時本來就沒有任何金額或累計歷史可言。
        「誤刪之後加回來」改由兩個**看得見**的入口處理：
          ・別的期別還在用 → 精靈的「選用已建立的項目」頁籤，或「帶入上期項目」
          ・所有期別都不用了 → 定義真的沒了，用精靈重新建一個（等價於全新建立）

        別的期別還在用的一律不動 —— 那正是定義要活在工程層級的理由。
        """
        # 連同所有祖先一起納入檢查：子項被移除後，空掉的彙總項也該跟著清掉
        candidates = self.mapped('extra_item_id')
        node = candidates.mapped('parent_id')
        while node:
            candidates |= node
            node = node.mapped('parent_id')

        res = super().unlink()

        # ⚠️ 必須**由下往上逐層**做，不能一次 filtered 完事：
        #   彙總項在子項還沒被刪掉之前 child_ids 還是非空的，
        #   會被判定成「還有人用」而跳過（1.6.4 實測「3 個定義只處理了 2 個」）。
        #   階層最多兩三層，這裡給 10 圈綽綽有餘。
        for _ in range(10):
            orphan = candidates.filtered(
                lambda i: i.exists() and not i.line_ids and not i.child_ids)
            if not orphan:
                break
            orphan.unlink()
            candidates.invalidate_recordset(['child_ids'])
        return res

    @api.constrains('extra_item_id', 'estimate_id')
    def _check_item_same_project(self):
        """非契約工項必須屬於本估驗單的工程。"""
        for line in self:
            est_project = line.estimate_id.project_id
            if (est_project and line.extra_item_id.project_id
                    and line.extra_item_id.project_id != est_project):
                raise ValidationError(
                    f'非契約工項「{line.extra_item_id.name}」屬於別的工程，'
                    f'不能掛到本估驗單。')

    @api.onchange('extra_item_id')
    def _onchange_extra_item_id(self):
        """挑了項目就把該項目在本工程的預設序號帶進來（純顯示排序）。"""
        for line in self:
            if line.extra_item_id and not line.sequence:
                line.sequence = line.extra_item_id.sequence

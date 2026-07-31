# -*- coding: utf-8 -*-

import re

from odoo import models, fields, api, Command
from odoo.osv import expression
from odoo.exceptions import UserError, ValidationError


class ProjectTask(models.Model):
    """
    契約工項擴展

    擴展 project.task 支援：
    - 廠商分配 (assigned_company_id)
    - 預算追蹤 (planned_qty, unit_price, planned_amount)
    - 時間計畫 (planned_date_start, planned_date_end)
    - 實際執行追蹤 (actual_qty, actual_amount, completion_rate)
    """
    _inherit = 'project.task'

    # === 排序欄位 ===
    # 注意: active 欄位由 Odoo 標準 project.task 提供，無需定義
    # active=False 的工項會自動從列表中隱藏
    
    sequence = fields.Integer(
        string='排序',
        default=10,
        index=True,
        help='工項顯示順序，數字越小越前面')

    # === 工項編號 ===
    item_no = fields.Char(
        string='工項編號', index=True, copy=False, required=True,
        help='契約工項編號，自動產生但可手動修改')

    # === 階層結構 ===
    item_level = fields.Integer(
        string='項次層級',
        compute='_compute_item_level',
        store=True,
        recursive=True,
        help='0=大項次, 1=次項次, 2=小項次...')

    @api.depends('parent_id', 'parent_id.item_level')
    def _compute_item_level(self):
        for task in self:
            task.item_level = (task.parent_id.item_level + 1) if task.parent_id else 0

    ref_item_code = fields.Char(
        string='參考工項代碼',
        index=True,
        help='標單中的 refItemCode，用於對應價格庫')

    is_summary_item = fields.Boolean(
        string='彙總項目',
        compute='_compute_is_summary_item',
        store=True,
        help='標示此項次是否為彙總項(有子項次)')

    @api.depends('child_ids')
    def _compute_is_summary_item(self):
        for task in self:
            task.is_summary_item = bool(task.child_ids)

    # === 項次顯示 ===
    display_item_no = fields.Char(
        string='顯示項次',
        compute='_compute_display_item_no',
        store=True,
        help='葉節點只顯示末段數字（如 1），非葉節點顯示完整項次（如 (一)、1.1）')

    @api.depends('item_no', 'is_summary_item')
    def _compute_display_item_no(self):
        for task in self:
            if not task.item_no:
                task.display_item_no = ''
            elif task.is_summary_item or '.' not in task.item_no:
                # 非葉節點或無點號（中文項次）→ 原樣顯示
                task.display_item_no = task.item_no
            else:
                # 葉節點（數字點分格式，如 1.1.3）→ 只取最後一段
                task.display_item_no = task.item_no.split('.')[-1]

    item_no_path = fields.Char(
        string='項次路徑',
        compute='_compute_item_no_path',
        store=True,
        recursive=True,
        help='點分隔的完整項次路徑，如：壹.一.(一).1.1.1')

    @api.depends('item_no', 'parent_id', 'parent_id.item_no_path')
    def _compute_item_no_path(self):
        for task in self:
            if task.parent_id and task.parent_id.item_no_path:
                task.item_no_path = f"{task.parent_id.item_no_path}.{task.item_no}"
            else:
                task.item_no_path = task.item_no or ''

    full_item_path = fields.Char(
        string='完整項次路徑',
        compute='_compute_full_item_path',
        store=True,
        help='項次編號 + 名稱，如：(一) 整備工程')

    @api.depends('item_no', 'name')
    def _compute_full_item_path(self):
        for task in self:
            item_no = task.item_no or ''
            name = task.name or ''
            if item_no and name:
                task.full_item_path = f"{item_no} {name}"
            else:
                task.full_item_path = name or item_no

    # === 完整項次（資料驅動，從階層計算）===
    # 各專案 XML 的 item_no 存法不一（B標葉節點存「1.1.19」、通河東街只存「23」），
    # 直接顯示 item_no 會導致同專案新舊工項格式不一致。改用本欄位：不論 item_no 怎麼存，
    # 一律從階層即時計算「排除最頂層(發包工程費)，L1 起每層項次號轉阿拉伯數字以『.』串接」。
    full_item_no = fields.Char(
        string='完整項次',
        compute='_compute_full_item_no',
        store=True,
        recursive=True,
        index=True,
        help='從階層計算的完整項次：排除最頂層(發包工程費)，自第二層起每層項次號轉阿拉伯'
             '數字，以「.」串接（如 1.1.19）。不論各專案 item_no 存法為何，皆呈現一致格式。')

    @api.depends('display_item_no', 'item_no', 'item_level',
                 'parent_id', 'parent_id.full_item_no')
    def _compute_full_item_no(self):
        for task in self:
            if task.item_level <= 0:
                # 最頂層（發包工程費）排除，不計入路徑
                task.full_item_no = ''
                continue
            seg = task._seg_to_arabic(task.display_item_no or task.item_no)
            parent_path = task.parent_id.full_item_no if task.parent_id else ''
            task.full_item_no = f"{parent_path}.{seg}" if parent_path else seg

    # 單一中文數字字元 → 阿拉伯（供 _seg_to_arabic 逐字映射，處理「一０」這類混寫）
    _CN_SINGLE_DIGIT = {
        '〇': '0', '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
        '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
    }

    def _seg_to_arabic(self, label):
        """把單一層的項次標籤轉成阿拉伯數字字串。
        支援：阿拉伯('19')、全形('１９')、中文('一'、'十一'、'拾壹')、混寫('一０'=10)、
        括號('(一)'→'1')、點分式取末段('1.1.19'→'19')。無法解析時原樣回傳。"""
        s = (label or '').strip()
        if not s:
            return ''
        if '.' in s:
            s = s.split('.')[-1]
        s = s.strip('()（）').strip()
        # 全形數字 → 半形
        s = s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        if re.fullmatch(r'\d+', s):
            return str(int(s))
        # 標準中文數字（含 十/拾 進位）
        n = self._chinese_to_number(s)
        if n:
            return str(n)
        # 逐字映射（處理「一０」這類單字元混寫）
        digits = ''
        for ch in s:
            if ch.isdigit():
                digits += ch
            elif ch in self._CN_SINGLE_DIGIT:
                digits += self._CN_SINGLE_DIGIT[ch]
            else:
                return s  # 含無法辨識字元 → 原樣回傳，不硬湊
        return str(int(digits)) if digits else s

    # === 工項名稱搜尋（CJK 友善 + 工項編號/項次路徑）===
    # 問題：Odoo 預設 name_search 用「連續子字串」ilike，CJK 部分關鍵字（如「預力基樁」）
    #       無法命中「預力混凝土基樁，D=400mm」（中間夾了「混凝土」）。
    # 解法：對 name 改用「逐字 %」比對（'預力基樁' → '%預%力%基%樁%'），並同時搜尋
    #       工項編號(item_no) 與項次路徑(item_no_path)。以空白分隔的多關鍵字需全部命中。
    # 影響：所有指向 project.task 的選擇器（施工日誌、施工排程、契約變更、估驗、自主檢查…）
    #       的下拉自動完成（m2o autocomplete）。
    # Odoo 18 已移除 _name_search；name_search 改走 display_name 欄位搜尋，
    # 對應 hook 為 _search_display_name(operator, value)（回傳 domain）。
    _rec_names_search = ['name', 'item_no', 'item_no_path']

    @api.model
    def _search_display_name(self, operator, value):
        if value and operator in ('ilike', 'like', '=ilike', '=like'):
            # 以空白分隔的多個關鍵字需全部命中；每個關鍵字對 name 做「逐字 %」比對
            terms = [t.strip() for t in value.split() if t.strip()]
            if terms:
                name_clauses = [
                    [('name', operator, '%' + '%'.join(list(t)) + '%')]
                    for t in terms
                ]
                return expression.OR([
                    expression.AND(name_clauses),
                    [('item_no', operator, value)],
                    [('item_no_path', operator, value)],
                ])
        return super()._search_display_name(operator, value)

    # === 廠商分配 ===
    assigned_company_id = fields.Many2one(
        'res.company', string='承包廠商', index=True,
        domain="[('company_type', '=', 'contractor')]",
        tracking=True,
        help='此工項分配給哪家施工廠商執行')

    assignment_date = fields.Date(
        string='分配日期',
        help='工項分配給廠商的日期')

    assigned_by_id = fields.Many2one(
        'res.users', string='分配人',
        help='執行分配操作的使用者')

    # === 分配狀態 ===
    assignment_state = fields.Selection([
        ('unassigned', '未分配'),
        ('assigned', '已分配'),
        ('in_progress', '執行中'),
        ('completed', '已完成'),
        ('accepted', '已驗收'),
    ], string='分配狀態', default='unassigned',
       compute='_compute_assignment_state', store=True, tracking=True)

    @api.depends('assigned_company_id', 'stage_id', 'stage_id.is_acceptance_stage')
    def _compute_assignment_state(self):
        for task in self:
            if not task.assigned_company_id:
                task.assignment_state = 'unassigned'
            elif task.stage_id and task.stage_id.is_acceptance_stage:
                task.assignment_state = 'accepted'
            elif task.actual_date_end:
                task.assignment_state = 'completed'
            elif task.actual_date_start:
                task.assignment_state = 'in_progress'
            else:
                task.assignment_state = 'assigned'

    # === 預算欄位 (契約價量) ===
    planned_qty = fields.Float(
        string='契約數量', digits=(16, 4), required=True,
        help='契約預估數量 (預算)')

    unit = fields.Char(
        string='單位', required=True,
        help='計量單位，如：M, M2, M3, 式')

    product_id = fields.Many2one(
        'product.product', string='標準工項',
        ondelete='restrict',
        help='關聯標準工項產品，提供單位標準化並支援未來成本/開票整合')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and self.product_id.uom_id:
            self.unit_id = self.product_id.uom_id
            self.unit = self.product_id.uom_id.name

    unit_id = fields.Many2one(
        'uom.uom', string='單位（標準）',
        help='選填，過渡期與 unit Char 並存。填入後可提升成本比對準確率')

    # ── 共用單位標準化（供標單匯入／契約變更／成本分析共用，確保全系統一致）──
    # 別名表：去空白+小寫後的鍵 → Odoo UoM 標準名稱
    _UNIT_ALIAS = {
        'b.m³': 'm³', 'c.m³': 'm³', 'b.m3': 'm³', 'c.m3': 'm³',
        'b.m²': 'm²', 'c.m²': 'm²', 'b.m2': 'm²', 'c.m2': 'm²',
        'm²/月': 'm²', 'm³/月': 'm³',
    }

    # 整詞單位對照（工程／日常常用；鍵為去頭尾空白後的小寫）。命中即回。
    _UNIT_EXACT = {
        # 長度
        'm': 'm', 'cm': 'cm', 'mm': 'mm', 'km': 'km',
        '公尺': 'm', '米': 'm', '公分': 'cm', '公釐': 'mm', '公厘': 'mm', '公里': 'km',
        # 面積
        'm2': 'm²', 'cm2': 'cm²', 'mm2': 'mm²', 'km2': 'km²',
        '平方公尺': 'm²', '平方米': 'm²', '平方公分': 'cm²', '平方公里': 'km²',
        'ha': 'ha', '公頃': 'ha',
        # 體積
        'm3': 'm³', 'cm3': 'cm³', 'mm3': 'mm³', 'km3': 'km³',
        '立方公尺': 'm³', '立方米': 'm³', '立方公分': 'cm³',
        # 容量
        'l': 'L', 'ml': 'mL', 'cc': 'cc', '公升': 'L', '毫升': 'mL',
        # 重量
        'kg': 'kg', 'g': 'g', 'mg': 'mg', 't': 't', 'ton': 't',
        '公斤': 'kg', '公克': 'g', '毫克': 'mg', '公噸': 't', '噸': 't',
    }

    @api.model
    def _normalize_unit_display(self, s):
        """標準化單位顯示格式（工程／日常常用，大小寫不拘）。
        - 長度/面積/體積：M/CM/MM/KM(+2/3) → m/cm/mm/km(+²/³)，保留 B./C. 前綴與 /月 等後綴
        - 重量 KG/G/MG/T(ON)→kg/g/mg/t；容量 L/ML/CC→L/mL/cc；面積 HA→ha
        - 常用中文計量名（公尺/公分/公斤/公升…）對應符號
        - 其餘中文單位（式/坪/才/個/組…）原樣保留（由 _resolve_uom_id 自動建立 uom）。"""
        if not s:
            return s
        t = s.strip()
        # 1) 整詞對照（最常見、最明確）
        exact = self._UNIT_EXACT.get(t.lower())
        if exact:
            return exact
        # 2) 含材料前綴/複合後綴者，用 regex 轉次方（KM/CM/MM 先於 M）
        #    例：B.M3→B.m³、C.M2→C.m²、M2/月→m²/月、CM3/月→cm³/月
        for up, lo in (('KM', 'km'), ('CM', 'cm'), ('MM', 'mm'), ('M', 'm')):
            t = re.sub(rf'(?<![A-Za-z]){up}3(?![A-Za-z0-9²³])', lo + '³', t, flags=re.IGNORECASE)
            t = re.sub(rf'(?<![A-Za-z]){up}2(?![A-Za-z0-9²³])', lo + '²', t, flags=re.IGNORECASE)
        for up, lo in (('KM', 'km'), ('CM', 'cm'), ('MM', 'mm'), ('M', 'm')):
            t = re.sub(rf'(?<![A-Za-z]){up}(?![A-Za-z0-9²³])', lo, t, flags=re.IGNORECASE)
        return t

    @api.model
    def _resolve_uom_id(self, display_unit):
        """依（已正規化的）單位字串解析 uom.uom：精確→別名→正規化模糊→自動建立。
        ⚠️ 一律依單位字串解析，不採 product 的 uom（避免 ref_item_code 不可靠污染 unit_id）。
        回傳 uom_id 或 False。"""
        if not display_unit:
            return False
        Uom = self.env['uom.uom']
        norm_key = lambda x: re.sub(r'\s+', '', (x or '').lower())
        # 1. 精確比對
        uom = Uom.search([('name', '=', display_unit)], limit=1)
        if uom:
            return uom.id
        nk = norm_key(display_unit)
        # 2. 別名比對
        std_name = self._UNIT_ALIAS.get(nk)
        if std_name:
            uom = Uom.search([('name', '=', std_name)], limit=1)
            if uom:
                return uom.id
        # 3. 正規化模糊比對（去空白+小寫；uom 數量少，逐筆比對成本可接受）
        for u in Uom.search([]):
            if norm_key(u.name) == nk:
                return u.id
        # 4. 自動建立（政府採購特殊中文單位彼此不可換算，各自獨立類別）
        # sudo：uom 為全域參照資料。原本無 sudo 會要求「Administration/Settings」群組，
        # 導致非管理員（如代操帳號）建含新單位的工項或套用引進新單位的契約變更時 AccessError。
        category = self.env['uom.category'].sudo().create({'name': display_unit})
        new_uom = Uom.sudo().create({
            'name': display_unit,
            'category_id': category.id,
            'uom_type': 'reference',
            'rounding': 1.0,
        })
        return new_uom.id

    unit_price = fields.Float(
        string='契約單價', digits=(16, 2), required=True,
        help='契約預估單價')

    xml_amount = fields.Float(
        string='XML 原始複價',
        digits=(16, 2),
        help='匯入標單 XML 時保留的 Amount 原始值（供無單價項目及彙總項使用）')

    tax_misc_rate = fields.Float(
        string='稅什費比例',
        digits=(12, 8),
        help='稅什費工項的計算比例（%），由 XML 匯入時自動計算：\n'
             '= 稅什費 XML Amount ÷ 同層前置分類複價總和 × 100\n'
             '精確到小數點後 8 位')

    planned_amount = fields.Float(
        string='契約金額',
        compute='_compute_planned_amount', store=True, recursive=True,
        help='計算規則：\n'
             '・彙總項（有子工項）：子工項契約金額總和\n'
             '・一般葉節點（有單價）：數量 × 單價\n'
             '・無單價葉節點（稅什費等）：XML 原始複價')

    @api.depends('planned_qty', 'unit_price',
                 'child_ids', 'child_ids.planned_amount',
                 'xml_amount', 'tax_misc_rate', 'sequence',
                 'parent_id', 'parent_id.child_ids.planned_amount')
    def _compute_planned_amount(self):
        for task in self:
            if task.child_ids:
                # 彙總項：累加子工項（Odoo 鏈式觸發，多層級自動向上滾動）
                task.planned_amount = sum(
                    child.planned_amount for child in task.child_ids)
            elif task.tax_misc_rate and task.parent_id:
                # 稅什費（無子項、設有比例）：比例 × 同層「前置」兄弟項契約金額加總
                # 與 contract_change_wizard._compute_amounts 一致；只取 sequence 在其之前
                # 者（不含自身），故工程量變動時稅什費連動重算，且不形成數值循環。
                preceding = task.parent_id.child_ids.filtered(
                    lambda s: s.id != task.id and s.sequence < task.sequence)
                task.planned_amount = round(
                    sum(preceding.mapped('planned_amount'))
                    * task.tax_misc_rate / 100.0, 2)
            elif task.unit_price:
                # 一般葉節點：數量 × 單價
                task.planned_amount = task.planned_qty * task.unit_price
            else:
                # 其他無單價葉節點：使用 XML 原始複價
                task.planned_amount = task.xml_amount

    # === 實際執行欄位 ===
    actual_qty = fields.Float(
        string='實際完成數量', digits=(16, 4), readonly=True,
        help='已核定的估驗數量彙總，由施工日誌自動計算')

    actual_amount = fields.Float(
        string='實際請款金額',
        compute='_compute_actual_amount', store=True,
        help='actual_qty x unit_price')

    @api.depends('actual_qty', 'unit_price')
    def _compute_actual_amount(self):
        for task in self:
            task.actual_amount = task.actual_qty * task.unit_price

    # === 對比分析 ===
    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate', store=True,
        help='actual_amount / planned_amount x 100')

    qty_remaining = fields.Float(
        string='剩餘數量',
        compute='_compute_completion_rate', store=True,
        help='planned_qty - actual_qty')

    budget_status = fields.Selection([
        ('under', '低於預算'),
        ('on_budget', '符合預算'),
        ('over', '超出預算'),
    ], string='預算狀態',
       compute='_compute_completion_rate', store=True)

    @api.depends('planned_qty', 'planned_amount', 'actual_qty', 'actual_amount')
    def _compute_completion_rate(self):
        for task in self:
            task.qty_remaining = task.planned_qty - task.actual_qty

            if task.planned_amount:
                task.completion_rate = (task.actual_amount / task.planned_amount) * 100
                if task.completion_rate < 95:
                    task.budget_status = 'under'
                elif task.completion_rate <= 100:
                    task.budget_status = 'on_budget'
                else:
                    task.budget_status = 'over'
            else:
                task.completion_rate = 0.0
                task.budget_status = False

    # === 時間計畫欄位 ===
    planned_date_start = fields.Datetime(
        string='預定開始時間', tracking=True,
        help='工項預定開始時間')

    planned_date_end = fields.Datetime(
        string='預定完成時間', tracking=True,
        help='工項預定完成時間')

    planned_duration = fields.Float(
        string='預定工期(天)',
        compute='_compute_planned_duration', store=True)

    @api.depends('planned_date_start', 'planned_date_end')
    def _compute_planned_duration(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                delta = task.planned_date_end - task.planned_date_start
                task.planned_duration = delta.total_seconds() / 86400  # 轉換為天數
            else:
                task.planned_duration = 0.0

    # === 實際執行時間 ===
    actual_date_start = fields.Datetime(
        string='實際開始時間', tracking=True)

    actual_date_end = fields.Datetime(
        string='實際完成時間', tracking=True)

    actual_duration = fields.Float(
        string='實際工期(天)',
        compute='_compute_actual_duration', store=True)

    @api.depends('actual_date_start', 'actual_date_end')
    def _compute_actual_duration(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                delta = task.actual_date_end - task.actual_date_start
                task.actual_duration = delta.total_seconds() / 86400
            else:
                task.actual_duration = 0.0

    # === 時程對比分析 ===
    schedule_variance = fields.Float(
        string='時程差異(天)',
        compute='_compute_schedule_variance', store=True,
        help='負值=超前, 正值=落後')

    schedule_status = fields.Selection([
        ('ahead', '超前'),
        ('on_schedule', '正常'),
        ('delayed', '落後'),
    ], string='時程狀態',
       compute='_compute_schedule_variance', store=True)

    @api.depends('planned_date_end', 'actual_date_end', 'assignment_state')
    def _compute_schedule_variance(self):
        for task in self:
            if task.planned_date_end and task.actual_date_end:
                delta = (task.actual_date_end - task.planned_date_end).days
                task.schedule_variance = delta
                if delta < -1:
                    task.schedule_status = 'ahead'
                elif delta <= 1:
                    task.schedule_status = 'on_schedule'
                else:
                    task.schedule_status = 'delayed'
            elif task.planned_date_end and task.assignment_state == 'in_progress':
                # 執行中：與現在時間比較
                now = fields.Datetime.now()
                delta = (now - task.planned_date_end).days
                task.schedule_variance = delta if delta > 0 else 0
                task.schedule_status = 'delayed' if delta > 0 else 'on_schedule'
            else:
                task.schedule_variance = 0.0
                task.schedule_status = False

    # === 工程相關 ===
    # 合併後工項所屬 project.project 即工程案件本身，直接 related 到 project_id
    # （欄位名保留，供既有 view/domain/depends 續用）
    supervision_project_id = fields.Many2one(
        'project.project', string='工程案件',
        related='project_id', store=True,
        help='關聯的工程案件主檔（即本工項所屬 project.project）')
    
    # === 工程案件狀態 ===
    project_state = fields.Selection(
        related='supervision_project_id.state',
        string='工程狀態',
        store=True,
        help='從工程案件繼承的狀態，用於控制欄位唯讀')
    
    is_project_approved = fields.Boolean(
        string='工程已核定',
        compute='_compute_is_project_approved',
        store=True,
        help='工程案件已核定，工項資料變為唯讀')
    
    @api.depends('supervision_project_id.state')
    def _compute_is_project_approved(self):
        for task in self:
            if task.supervision_project_id:
                task.is_project_approved = task.supervision_project_id.state in (
                    'construction', 'completion', 'acceptance', 'closed', 'suspended', 'terminated'
                )
            else:
                task.is_project_approved = False

    # === 版本紀錄 ===
    version_ids = fields.One2many(
        'project.task.version', 'task_id',
        string='版本紀錄',
        help='歷次契約變更的數量/單價版本，v1 於工項建立時自動建立')

    # === 備註 ===
    construction_notes = fields.Text(
        string='施工說明',
        help='工項施工注意事項或說明')

    specification = fields.Text(
        string='規格說明',
        help='工項規格或技術要求')

    # === 約束 ===
    @api.constrains('planned_date_start', 'planned_date_end')
    def _check_planned_dates(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                if task.planned_date_end < task.planned_date_start:
                    raise ValidationError('預定完成時間必須晚於預定開始時間')

    @api.constrains('actual_date_start', 'actual_date_end')
    def _check_actual_dates(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                if task.actual_date_end < task.actual_date_start:
                    raise ValidationError('實際完成時間必須晚於實際開始時間')

    @api.constrains('planned_qty', 'unit_price')
    def _check_positive_values(self):
        for task in self:
            if task.planned_qty < 0:
                raise ValidationError('契約數量不可為負數')
            if task.unit_price < 0:
                raise ValidationError('契約單價不可為負數')

    # === 動作方法 ===
    def action_assign_to_contractor(self):
        """開啟分配廠商精靈"""
        self.ensure_one()
        if not self.supervision_project_id:
            raise UserError('此工項未關聯工程案件，無法分配廠商')

        return {
            'type': 'ir.actions.act_window',
            'name': '分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': self.supervision_project_id.id,
            },
        }

    def action_start_work(self):
        """開始施工"""
        for task in self:
            if not task.assigned_company_id:
                raise UserError('請先分配廠商才能開始施工')
            if not task.actual_date_start:
                task.actual_date_start = fields.Datetime.now()

    def action_complete_work(self):
        """完成施工"""
        for task in self:
            if not task.actual_date_start:
                raise UserError('尚未開始施工，無法標記完成')
            if not task.actual_date_end:
                task.actual_date_end = fields.Datetime.now()

    def action_batch_assign(self):
        """批次分配工項"""
        if not self:
            raise UserError('請先選擇要分配的工項')

        # 檢查是否都屬於同一個專案
        projects = self.mapped('supervision_project_id')
        if len(projects) > 1:
            raise UserError('批次分配的工項必須屬於同一個工程案件')
        if not projects:
            raise UserError('選取的工項未關聯工程案件')

        return {
            'type': 'ir.actions.act_window',
            'name': '批次分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': projects[0].id,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        """覆寫建立方法以自動產生工項編號"""
        for vals in vals_list:
            # 如果沒有提供 item_no，自動產生
            if not vals.get('item_no'):
                vals['item_no'] = self._generate_item_no(
                    vals.get('parent_id'),
                    vals.get('project_id')
                )
            
            # 如果沒有提供 sequence，自動計算
            if not vals.get('sequence'):
                vals['sequence'] = self._calculate_sequence(
                    vals.get('parent_id'),
                    vals.get('project_id')
                )
        
        return super().create(vals_list)
    
    def _generate_item_no(self, parent_id, project_id):
        """自動產生工項編號（資料驅動：依該專案現有同層工項的編號格式骨架產生，
        不寫死層級格式）。"""
        if not project_id:
            return '1'
        if parent_id:
            parent = self.browse(parent_id)
            target_level = parent.item_level + 1
            sibling_nos = parent.child_ids.mapped('display_item_no')
            parent_item_no = parent.item_no or ''
        else:
            target_level = 0
            tops = self.search([('project_id', '=', project_id),
                                ('parent_id', '=', False)])
            sibling_nos = tops.mapped('display_item_no')
            parent_item_no = ''
        level_nos = self.search([('project_id', '=', project_id),
                                 ('item_level', '=', target_level)]).mapped('display_item_no')
        return self._gen_item_no(sibling_nos, level_nos, parent_item_no)

    # ── 資料驅動編號核心（pattern 偵測，供 task 與 wizard 共用）──────────
    _CN_UPPER_SET = '壹貳參肆伍陸柒捌玖拾'
    _CN_LOWER_SET = '一二三四五六七八九十'

    def _parse_item_no_skeleton(self, s):
        """把編號解析成 (前綴, 風格, 數值, 後綴)；風格∈upper_cn/lower_cn/arabic。
        取「最後一段數字」，故點分式如「(一).1」prefix='(一).'、arabic、n=1。失敗回 None。"""
        import re
        s = (s or '').strip()
        if not s:
            return None
        m = re.search(
            r'(?P<num>[0-9０-９]+|[壹貳參肆伍陸柒捌玖拾]+|[一二三四五六七八九十]+)'
            r'(?P<suf>[^0-9０-９壹貳參肆伍陸柒捌玖拾一二三四五六七八九十]*)$', s)
        if not m:
            return None
        num_s, suf = m.group('num'), m.group('suf')
        pre = s[:m.start('num')]
        if re.match(r'^[0-9０-９]+$', num_s):
            n = int(num_s.translate(str.maketrans('０１２３４５６７８９', '0123456789')))
            style = 'arabic'
        elif any(c in self._CN_UPPER_SET for c in num_s):
            n, style = self._chinese_to_number(num_s), 'upper_cn'
        else:
            n, style = self._chinese_to_number(num_s), 'lower_cn'
        return (pre, style, n, suf) if n and n > 0 else None

    def _format_item_no_skeleton(self, skel, n):
        pre, style, suf = skel
        if style == 'arabic':
            core = str(n)
        elif style == 'upper_cn':
            core = self._number_to_chinese(n, 0)
        else:
            core = self._number_to_chinese(n, 1)
        return f"{pre}{core}{suf}"

    def _gen_item_no(self, sibling_nos, level_nos, parent_item_no=''):
        """依現有同層編號格式產生下一個編號。
        序號＝同父兄弟最大+1；格式＝同父兄弟骨架(無則同層級骨架)；都無則保底「父.序號」。
        因每次都讀現有同層，使用者手改格式後，後續同層會自動沿用其格式。"""
        from collections import Counter
        sib = [p for p in (self._parse_item_no_skeleton(x) for x in (sibling_nos or [])) if p]
        next_n = (max(p[2] for p in sib) + 1) if sib else 1
        fmt_src = sib or [p for p in
                          (self._parse_item_no_skeleton(x) for x in (level_nos or [])) if p]
        if fmt_src:
            pre, style, suf = Counter((p[0], p[1], p[3]) for p in fmt_src).most_common(1)[0][0]
            # 借用其他父項的「點分式」前綴時，換成本項父編號
            if not sib and pre.endswith('.'):
                pre = (parent_item_no + '.') if parent_item_no else ''
            return self._format_item_no_skeleton((pre, style, suf), next_n)
        # 保底：父.序號（明確階層、不猜風格）
        return (parent_item_no + '.' if parent_item_no else '') + str(next_n)
    
    def _parse_and_increment(self, item_no):
        """從工項編號解析數字並遞增"""
        if not item_no:
            return 1
        
        # 嘗試轉換中文數字
        num = self._chinese_to_number(item_no)
        if num > 0:
            return num + 1
        
        # 嘗試解析阿拉伯數字
        import re
        match = re.search(r'\d+', item_no)
        if match:
            return int(match.group()) + 1
        
        return 1
    
    def _number_to_chinese(self, num, level):
        """數字轉中文"""
        if level == 0:
            # 第一層：壹貳參...
            chinese_upper = ['', '壹', '貳', '參', '肆', '伍', '陸', '柒', '捌', '玖', '拾']
            if num <= 10:
                return chinese_upper[num]
            else:
                # 超過10的話，用組合方式
                if num < 20:
                    return '拾' + (chinese_upper[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_upper[tens] + '拾' + (chinese_upper[ones] if ones else '')
        elif level == 1:
            # 第二層：一二三...
            chinese_lower = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
            if num <= 10:
                return chinese_lower[num]
            else:
                if num < 20:
                    return '十' + (chinese_lower[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_lower[tens] + '十' + (chinese_lower[ones] if ones else '')
        else:
            # 第三層及以下：1, 2, 3...
            return str(num)
    
    def _chinese_to_number(self, chinese_str):
        """中文轉數字"""
        if not chinese_str:
            return 0
        
        # 大寫數字對應
        upper_map = {
            '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5,
            '陸': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10
        }
        # 小寫數字對應
        lower_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        # 嘗試直接對應
        if chinese_str in upper_map:
            return upper_map[chinese_str]
        if chinese_str in lower_map:
            return lower_map[chinese_str]
        
        # 嘗試解析組合（如：拾壹、十一）
        result = 0
        if '拾' in chinese_str or '十' in chinese_str:
            parts = chinese_str.replace('拾', '|').replace('十', '|').split('|')
            if len(parts) == 2:
                tens_str, ones_str = parts
                tens = upper_map.get(tens_str, lower_map.get(tens_str, 1 if not tens_str else 0))
                ones = upper_map.get(ones_str, lower_map.get(ones_str, 0))
                result = tens * 10 + ones
        
        return result
    
    def _calculate_sequence(self, parent_id, project_id):
        """計算 sequence 值"""
        if not project_id:
            return 10
        
        # 取得同父項下的最大 sequence
        domain = [('project_id', '=', project_id)]
        if parent_id:
            domain.append(('parent_id', '=', parent_id))
        else:
            domain.append(('parent_id', '=', False))
        
        siblings = self.search(domain, order='sequence desc', limit=1)

        if not siblings:
            return 10

        return siblings[0].sequence + 10

    def _resequence_project_sequence(self, project_id):
        """以樹狀 DFS 前序，整個專案重編 sequence（每節點間隔 10）。

        sequence 是扁平的全域整數，畫面與各處查詢都用 order='sequence, item_no' 排序；
        新增工項時只在同父兄弟取 max+10，多筆新增會跨越「下一個彙總項」的序號區間造成亂序。
        本方法走訪整棵樹（每層依現有 sequence, item_no 排序），重新發號，
        確保「父 < 其所有子孫 < 下一個兄弟」，徹底消除跨彙總項撞號。
        """
        if not project_id:
            return
        Task = self.env['project.task']
        counter = [0]

        def walk(nodes):
            for node in nodes.sorted(key=lambda t: (t.sequence, t.item_no or '', t.id)):
                counter[0] += 10
                if node.sequence != counter[0]:
                    node.sequence = counter[0]
                if node.child_ids:
                    walk(node.child_ids)

        tops = Task.search([
            ('project_id', '=', project_id),
            ('parent_id', '=', False),
        ], order='sequence, item_no')
        walk(tops)

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        version_vals = []
        for task, vals in zip(tasks, vals_list):
            qty = vals.get('planned_qty', 0) or 0
            price = vals.get('unit_price', 0) or 0
            # 僅對有數量或單價的非彙總工項建立 v1（彙總項的金額由子項加總）
            if (qty or price) and not task.is_summary_item:
                version_vals.append({
                    'task_id': task.id,
                    'version': 1,
                    'planned_qty': qty,
                    'unit_price': price,
                    'change_date': fields.Date.context_today(self),
                    'change_reason': '原始契約',
                })
        if version_vals:
            self.env['project.task.version'].create(version_vals)
        return tasks

    def write(self, vals):
        """覆寫寫入方法以記錄分配資訊"""
        if 'assigned_company_id' in vals:
            if vals['assigned_company_id']:
                vals['assignment_date'] = fields.Date.today()
                vals['assigned_by_id'] = self.env.uid
            else:
                vals['assignment_date'] = False
                vals['assigned_by_id'] = False
        return super().write(vals)


class ProjectTaskType(models.Model):
    """專案階段擴展 - 增加工程相關屬性"""
    _inherit = 'project.task.type'

    is_construction_stage = fields.Boolean(
        string='施工階段',
        help='標記此階段為施工執行階段')

    is_acceptance_stage = fields.Boolean(
        string='驗收階段',
        help='標記此階段為驗收完成階段')

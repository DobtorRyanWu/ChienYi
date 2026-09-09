# -*- coding: utf-8 -*-
"""自主檢查的「表尾量測區」。

紙本上這是檢查項目表格**外面、下方**的一段，長這樣：

    鋼筋組立抽查情形(檢附抽查照片)
    1  丈量___位置，長___cm，有#___鋼筋___支，平均間距___cm，搭接長度___cm，保護層___cm  □合格□不合格
    2  （同一句型，空白）
    3  （同一句型，空白）
    4  （同一句型，空白）

不變式（掃 797 份自主檢查原生檔得到）：
  · 一個區塊標題 ＋ N 列**同一個句型**重複 ＋ 每列一個「合格／不合格」
  · 只有兩態，與檢查項目的 ○╳／三態不同
  · 空列 ＝ 沒有記錄（紙本預印 4 列、實填 2 列 ＝ 2 筆）

🔴 為什麼標題／句型／列數三個都是資料而不是寫死：
  同一種鋼筋表，三個案子三種寫法 ——
    北投等 15 案：鋼筋組立**抽查**情形(**檢**附抽查照片)、4 列
    淡五號 111-23-AEF：鋼筋組立**抽查**情形(**請**附抽查照片)、**3 列**
    使用者截圖那份：鋼筋組立**檢查**情形(檢附**檢查**照片)、4 列
  句型也有差（`長___cm，有#` vs `長___cm有#`）。列印報表要原樣還原紙本。
"""
import re

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

# 空格 ＝ 連續兩個以上的底線。實案寫法從 `___` 到 `_______` 都有，
# 底線數量只是版面，不代表不同的空格。
BLANK_RE = re.compile(r'_{2,}')

# 未填的空格在 rendered 字串裡的長相（保留「這裡有個空格」的形狀）
BLANK_MARK = '＿＿'

# values_text 的分隔符。刻意用「｜」而不是逗號 —— 量測值本身就可能含逗號。
VALUES_SEP = '｜'


def split_template(template):
    """句型依空格切成文字段。N 個空格 → N+1 段。"""
    return BLANK_RE.split(template or '')


def count_blanks(template):
    return len(BLANK_RE.findall(template or ''))


def render_template(template, values):
    """句型 ＋ 各空格的值 → 填好的整句。"""
    segments = split_template(template)
    vals = list(values or [])
    out = []
    for idx, seg in enumerate(segments):
        out.append(seg)
        if idx < len(segments) - 1:
            one = vals[idx] if idx < len(vals) else ''
            out.append(str(one) if str(one).strip() else BLANK_MARK)
    return ''.join(out)


class SelfInspectionTypeMeasure(models.Model):
    """自主檢查類型的量測區塊（定義層）。

    掛在檢查類型底下、可以有多個 —— 與查驗段落、檢查時機同一個形狀。
    做成模型而不是「檢查類型上的三個欄位」，是因為欄位一筆記錄只能放一個值；
    而且匯入契約（【量測區塊】分頁）是這裡最貴的東西，一開始就做成一列一個區塊，
    日後真的出現第二個區塊時不必再改契約。
    """
    _name = 'self.inspection.type.measure'
    _description = '自主檢查類型量測區塊'
    _order = 'sequence, id'

    type_id = fields.Many2one(
        'self.inspection.type',
        string='檢查類型',
        required=True,
        ondelete='cascade',
        index=True)

    name = fields.Char(
        string='區塊標題',
        required=True,
        help='原樣照紙本印的字，例如：鋼筋組立抽查情形(檢附抽查照片)。'
             '各家表格用字不同，列印報表會照這裡的字還原')

    template = fields.Char(
        string='句型',
        required=True,
        help='用連續兩個以上的底線標出要填的空格，例如：'
             '丈量___位置，長___cm，有#___鋼筋___支')

    row_count = fields.Integer(
        string='預印列數',
        default=4,
        help='紙本上印了幾列。只用來提示填表的人，實際存幾列由實填的內容決定'
             '（空列＝沒有記錄，不建列）')

    sequence = fields.Integer(string='排序', default=10)

    blank_count = fields.Integer(
        string='空格數',
        compute='_compute_blank_count',
        help='由句型自動數出來，不必自己填')

    @api.depends('template')
    def _compute_blank_count(self):
        for block in self:
            block.blank_count = count_blanks(block.template)

    @api.constrains('template')
    def _check_template_has_blank(self):
        """句型至少要有一個空格 —— 沒有空格的話這一列沒有東西可填，
        那就不是量測區塊，應該用檢查項目。"""
        for block in self:
            if not count_blanks(block.template):
                raise ValidationError(
                    '量測區塊「%s」的句型沒有任何空格。'
                    '請用連續兩個以上的底線標出要填的位置，例如「長___cm」。'
                    % (block.name or ''))

    _sql_constraints = [
        ('name_type_uniq', 'UNIQUE(type_id, name)',
         '同一檢查類型內的量測區塊標題不可重複！'),
    ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_use(self):
        """已經有量測列指過來就不可刪。

        與 stage / timing 同樣用 @api.ondelete 而非 FK restrict：刪整個檢查類型時
        DB 會 cascade 掉本表、不走 ORM unlink，故此守門不會誤觸發。
        """
        for model in ('general.self.inspection.measure.line',
                      'reservation.self.inspection.measure.line'):
            Model = self.env.get(model)
            if Model is None:
                continue
            count = Model.sudo().search_count([('block_id', 'in', self.ids)])
            if count:
                raise UserError(
                    '此量測區塊已被 %s 筆「%s」使用，請先刪除那些量測列再刪除區塊。'
                    % (count, Model._description))


class SelfInspectionMeasureLineMixin(models.AbstractModel):
    """自主檢查量測列（值層）—— 一般式與預約式共用。

    兩式各有自己的具體模型（比照 general/reservation.self.inspection.item），
    差別只有 inspection_id 指向誰，其餘全部在這裡。
    """
    _name = 'self.inspection.measure.line.mixin'
    _description = '自主檢查量測列共用 Mixin'
    _order = 'sequence, id'

    block_id = fields.Many2one(
        'self.inspection.type.measure',
        string='量測區塊',
        required=True,
        ondelete='restrict',
        index=True)

    sequence = fields.Integer(string='序號', default=10)

    # 🔴 建立當下的句型快照。
    # 不 related 到 block_id.template 的理由與 payment.estimate.extra.line.unit_price
    # 每期存一份快照相同：日後有人在句型中間多插一個空格，values 是**位置對應**的，
    # 所有舊資料的欄位對應會整批位移**而且不會報錯**。存快照之後，改句型只影響新列。
    template = fields.Char(
        string='句型（快照）',
        required=True,
        help='建立這一列時該區塊的句型。日後區塊改句型不會動到已填好的列')

    values = fields.Json(
        string='各空格的值',
        help='依句型空格順序排列的清單')

    values_text = fields.Char(
        string='各空格的值（文字）',
        compute='_compute_values_text',
        inverse='_inverse_values_text',
        help='以「%s」分隔，順序同句型的空格。'
             '這是不靠自訂元件也能編輯的入口' % VALUES_SEP)

    # 🔴 必填且刻意沒有預設值。
    # 檢查項目的 check_result 預設 pass 已經在這個系統上製造過
    # 「讀不到 ＝ 全部合格」的假性合格，不要在新功能上重演。
    result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
    ], string='檢查結果', required=True)

    rendered = fields.Char(
        string='填寫內容',
        compute='_compute_rendered',
        store=True,
        help='句型填上各空格的值之後的整句，供清單、搜尋與列印使用')

    @api.onchange('block_id')
    def _onchange_block_id(self):
        """選了量測區塊就把句型抄過來，並把值的格數對齊。

        ⚠️ 只寫 onchange 是不夠的（onchange 只在畫面操作時跑），
        權威放在 create()／write()，這裡只是讓畫面即時看到。
        """
        for line in self:
            if line.block_id:
                line.template = line.block_id.template
                want = count_blanks(line.template)
                current = list(line.values or [])
                line.values = (current + [''] * want)[:want]

    @api.model_create_multi
    def create(self, vals_list):
        """句型快照的權威在寫入端 —— 沒給就從區塊帶。

        不做這件事的話，後台清單新增一列會直接撞
        「未設置必填欄位 template」的驗證錯誤（實測回報）。
        """
        Block = self.env['self.inspection.type.measure']
        for vals in vals_list:
            if not vals.get('template') and vals.get('block_id'):
                block = Block.browse(vals['block_id'])
                vals['template'] = block.template or ''
            if vals.get('template') and 'values' not in vals:
                vals['values'] = [''] * count_blanks(vals['template'])
        return super().create(vals_list)

    def write(self, vals):
        """換了區塊就換句型，**而且值要跟著對齊格數**。

        只換句型不動 values 會直接撞 _check_values_length（實測：2 格的值
        配上 3 格的新句型 → 存不進去）。對齊規則與 onchange 一致：
        依位置保留、不足補空、超過截掉 —— 換句型是使用者主動的動作，
        畫面上 rendered 會立刻反映，不是靜默改值。
        """
        if vals.get('block_id') and 'template' not in vals:
            block = self.env['self.inspection.type.measure'].browse(vals['block_id'])
            vals['template'] = block.template or ''
        if 'template' in vals and 'values' not in vals:
            want = count_blanks(vals['template'])
            for line in self:
                current = list(line.values or [])
                super(SelfInspectionMeasureLineMixin, line).write(
                    dict(vals, values=(current + [''] * want)[:want]))
            return True
        return super().write(vals)

    @api.depends('template', 'values')
    def _compute_rendered(self):
        for line in self:
            line.rendered = render_template(line.template, line.values)

    @api.depends('values')
    def _compute_values_text(self):
        for line in self:
            line.values_text = VALUES_SEP.join(
                str(v if v is not None else '') for v in (line.values or []))

    def _inverse_values_text(self):
        """畫面輸入的容錯：**不足補空、超過擋下**。

        補空是安全的 —— 位置由左到右對齊，只是把後面沒填的格子補成空字串，
        不會讓任何一個值跑到別的格子。超過就是使用者數錯了，必須擋
        （`_check_values_length` 會接手報錯）。
        匯入那條路直接寫 `values`，不經過這裡，維持嚴格比對。
        """
        for line in self:
            raw = line.values_text or ''
            parts = [p.strip() for p in raw.split(VALUES_SEP)] if raw else []
            want = count_blanks(line.template)
            if want and len(parts) < want:
                parts = parts + [''] * (want - len(parts))
            line.values = parts

    @api.constrains('template', 'values')
    def _check_values_length(self):
        """值的個數必須等於句型的空格數。

        少一個或多一個都代表**位置對錯了** —— 而位置一錯，
        「長」欄的數字會被印在「保護層」那格，畫面上完全看不出來。
        未填的空格請留空字串，不要少給。
        """
        for line in self:
            want = count_blanks(line.template)
            got = len(line.values or [])
            if want != got:
                raise ValidationError(
                    '量測列第 %s 列的值有 %s 個，但句型有 %s 個空格 —— '
                    '個數不符代表位置對錯了。未填的空格請留空，不要少給。\n句型：%s'
                    % (line.sequence, got, want, line.template))

    def _render_parts(self):
        """給列印報表用：[(文字段, 該段後面那個空格的值)]，最後一段的值為 None。"""
        self.ensure_one()
        segments = split_template(self.template)
        vals = list(self.values or [])
        parts = []
        for idx, seg in enumerate(segments):
            one = None
            if idx < len(segments) - 1:
                one = str(vals[idx]) if idx < len(vals) else ''
            parts.append({'text': seg, 'value': one})
        return parts

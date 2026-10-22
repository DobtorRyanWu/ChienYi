"""屆次（理監事的任期單位）。

**為什麼需要一個模型，而不是在選舉上放一個整數欄位。**
人民團體選舉罷免辦法 §6 I 要求選舉票「應載明團體名稱、**選舉屆次**、職稱及
年月日等」——紙本與電子票都一樣，不是只有紙本。屆次因此是每一場選舉都要有的
資料，而同一屆通常有好幾場選舉（改選、補選、之後的理事長互選），散在各場各填
一個整數必然會長出兩個互相矛盾的「第 12 屆」。`unique(company_id, term_no)`
是這件事唯一擋得住的地方。

任期長度：技師法 §31 規定省（市）技師公會理監事任期 3 年；人民團體法 §20 的
上限是 4 年，取嚴者 3 年。這裡**只拿來當 `date_to` 的預設值，不做驗證**——
系統不知道各公會章程怎麼寫，而擋錯了會發生在理監事會當場。
"""

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from ..tools import term_label

# 技師法 §31：省（市）技師公會理監事任期 3 年（人民團體法 §20 上限 4 年，取嚴者）
DEFAULT_TERM_YEARS = 3


class AssocTerm(models.Model):
    _name = 'assoc.term'
    _description = '理監事屆次'
    # 屆次是治理紀錄：誰在什麼時候把任期起訖改掉要留得下來。
    # 沒被任何選舉引用的屆次刪得掉（ACL 給 admin unlink），chatter 是唯一的痕跡。
    _inherit = ['mail.thread']
    _order = 'company_id, term_no desc'

    name = fields.Char(string='屆次', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, index=True,
        default=lambda self: self.env.company)
    term_no = fields.Integer(string='第幾屆', required=True, tracking=True)
    date_from = fields.Date(string='任期起日', required=True, tracking=True)
    date_to = fields.Date(
        string='任期迄日', tracking=True,
        help='預設為起日加 %s 年（技師法 §31）。各公會章程若另有規定，直接改這裡；'
             '系統不驗證任期長度。' % DEFAULT_TERM_YEARS)
    # **這一階段沒有任何程式讀 `state`**（grep：沒有 domain／compute／filter／
    # 報表／前台讀它，只有三支測試的 fixture 傳 `current`）。它是給
    # M13 第二階段的理監事名冊、遞補與補選用的，留在這裡是為了讓屆次一建立
    # 就有狀態可記（它有 tracking，chatter 會留下誰在什麼時候改的）。
    # 它與 `date_from`／`date_to` **刻意不互相驗證**：「`state='current'` 而
    # 任期迄日已過」不會有任何東西紅——任期長度只警告不擋是計畫裡的裁決
    # （系統不知道各公會章程，提前改選與延任都表達得出來才對）。
    # 寫在這裡是因為下一個人會在這裡問「這個欄位有人用嗎」（L9）。
    state = fields.Selection([
        ('draft', '籌備中'),
        ('current', '現任'),
        ('closed', '已卸任'),
    ], string='狀態', default='draft', required=True, tracking=True)
    note = fields.Char(string='備註')
    # `election_ids` 與「被選舉凍結後不可改屆次」那道守衛在 `assoc_election`
    # 裡以 `_inherit` 補上：`assoc.election` 定義在相依本模組的模組裡，
    # 在這裡寫 One2many 會讓「只裝 assoc_base」的環境在 registry 階段就炸。

    _sql_constraints = [
        ('term_no_unique', 'unique(company_id, term_no)',
         '同一個公會的屆次不可以重複。'),
        # 選票上印「第 0 屆」是沒有意義的；`action_ready` 另有一道要求 > 0 的閘，
        # 這裡是資料庫層的最後防線（Python 約束在併發下有 write skew）。
        ('term_no_positive', 'CHECK(term_no > 0)', '屆次必須大於 0。'),
    ]

    @api.depends('term_no')
    def _compute_name(self):
        for term in self:
            term.name = term_label(term.term_no) if term.term_no else ''

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """只填空白的迄日，不覆寫已經填好的值。

        做成 onchange 而不是 compute store：任期迄日是**可手填**的初始值，
        併進唯讀 compute store 會在 create 當下被重算清空（§16 通則 7，
        M8 的 `fee_paid_until` 踩過同一個坑）。
        """
        for term in self:
            if term.date_from and not term.date_to:
                term.date_to = term.date_from + relativedelta(
                    years=DEFAULT_TERM_YEARS, days=-1)

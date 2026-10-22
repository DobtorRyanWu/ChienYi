import random
import uuid as uuid_lib
from collections import Counter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.assoc_base.tools import (ASSOC_TZ, GUARD, check_created, check_guild_admin,
                                           guarded, term_label, with_guard)

from .. import verify_core
from ..tools import AssocVoteError, escape_like, sha256_hex, utc_iso

OFFICES = [('director', '理事'), ('supervisor', '監事')]
OFFICE_LABELS = dict(OFFICES)
OFFICER_GROUP = 'assoc_election.group_election_officer'
ADMIN_GROUP = 'assoc_base.group_assoc_admin'

GUARD_STATE = 'assoc_state_machine'
GUARD_BOX = 'assoc_ballot_box'

# 可以取消的狀態
EDITABLE_STATES = ('draft', 'ballot_ready')
# 名冊凍結後、開始投票前唯一可改的欄位（規則與名額在凍結時已寫入稽核鏈，不能再動）
BALLOT_READY_WRITABLE_FIELDS = frozenset({'observer_user_ids'})
VOTING_STATES = ('open', 'closing')
# 系統欄位：任何狀態都只能經由狀態機寫入
SYSTEM_FIELDS = frozenset({
    'state', 'uuid', 'close_xid', 'closed_at', 'counted_at', 'published_at',
    'ballots_digest', 'roster_final_digest', 'result_json', 'result_digest',
    'archive_sha256', 'archive_built_at',
    # `term_no` 是凍結名冊當下從 `term_id` 抄下來的快照，同時進稽核鏈與選票。
    # 它必須與 `member_no`／`member_name` 一樣只能由狀態機寫：可以用 RPC 改的話，
    # 選票上印的屆次就與鏈上那一筆對不起來，而 §6 的要件正是「選票載明屆次」。
    'term_no',
})
# create 當下必須長這樣（§16 通則 1：驗結果不驗輸入）。
# 少了這張表，有建立權的選務可以一次 `create({'state': 'published', 'result_json': …})`
# 生出一場憑空的「已公告選舉」——它沒有選票、沒有稽核鏈，卻會被**匿名**的
# 大螢幕與跑馬燈當成真的結果播出去（red-team 實跑複現）。
CREATED_INITIAL = {
    'state': 'draft',
    'close_xid': False, 'closed_at': False, 'counted_at': False, 'published_at': False,
    'ballots_digest': False, 'roster_final_digest': False,
    'result_json': False, 'result_digest': False,
    'archive_sha256': False, 'archive_built_at': False,
    'term_no': 0,
}
# 公告後唯一可改的欄位：要不要出現在跑馬燈（不影響任何已入鏈的內容）
PUBLISHED_WRITABLE_FIELDS = frozenset({'show_on_ticker'})
# 關票後、開票前唯一可寫的欄位：監票員登錄同票抽籤亂數（開票時寫入稽核鏈）
# `seal_void_reason` 要在 `closed` 狀態寫得進去——它是作廢封箱的原因，
# 而作廢只發生在 closed。值本身不影響任何判定，真正的紀錄在鏈上那一筆。
CLOSED_WRITABLE_FIELDS = frozenset({'tie_entropy', 'seal_void_reason'})
# 技師法 §31：省（市）技師公會理事 3–15 人、監事 1–5 人（0＝本場不選該職位）
MAX_DIRECTOR_SEATS = 15
MAX_SUPERVISOR_SEATS = 5
# 領票台一次最多關注的選舉人數（輪詢參數上限）
MAX_WATCHED_VOTERS = 10
# 跑馬燈一次最多幾場（避免有人用 c= 參數把整個資料庫拉出來）
TICKER_LIMIT = 20
# 鏈頭顯示長度：夠讓監票員抄在紙上比對，又不會佔滿螢幕
CHAIN_HEAD_DISPLAY = 16


class AssocElection(models.Model):
    _name = 'assoc.election'
    _description = '理監事選舉'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string='選舉名稱', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, tracking=True,
        default=lambda self: self.env.company)
    meeting_id = fields.Many2one(
        'assoc.meeting', string='會員大會', required=True, ondelete='restrict', tracking=True,
        domain="[('company_id', '=', company_id)]")
    # 選罷辦法 §6 I：選舉票（紙本或電子，**兩種都一樣**）應載明團體名稱、
    # 選舉屆次、職稱及年月日。`term_id` 是這場選舉產生（或補選）哪一屆，
    # `term_no` 是凍結名冊當下抄下來的那個數字——印在票上、同時進稽核鏈。
    # 分成兩個欄位的理由與 `candidate.member_no` 一樣：關聯會被改，快照不會。
    term_id = fields.Many2one(
        'assoc.term', string='屆次', ondelete='restrict', tracking=True,
        domain="[('company_id', '=', company_id)]",
        help='選罷辦法 §6 要求選票載明選舉屆次。凍結名冊時會把屆次數字抄進稽核鏈。')
    term_no = fields.Integer(
        string='屆次（凍結時）', readonly=True, copy=False,
        help='凍結名冊當下從屆次抄下來的快照，印在選票上。之後改屆次資料不會動到它。')
    uuid = fields.Char(
        string='選舉識別碼', required=True, readonly=True, copy=False, index=True,
        default=lambda self: str(uuid_lib.uuid4()))
    state = fields.Selection([
        ('draft', '草稿'),
        ('ballot_ready', '名冊已凍結'),
        ('open', '投票中'),
        ('closing', '停止領票'),
        ('closed', '已關票'),
        ('counted', '已開票'),
        ('published', '已公告'),
        ('cancelled', '已取消'),
    ], string='狀態', default='draft', required=True, readonly=True, copy=False, tracking=True)

    director_seats = fields.Integer(string='理事應選名額', default=15)
    director_alt = fields.Integer(string='候補理事名額', default=5)
    supervisor_seats = fields.Integer(string='監事應選名額', default=5)
    supervisor_alt = fields.Integer(string='候補監事名額', default=1)
    mark_limit_mode = fields.Selection([
        ('full', '連記法（可圈選至應選名額）'),
        ('half_floor', '限制連記法（應選名額之半）'),
    ], string='圈選上限', default='full', required=True)
    limit_resolution_note = fields.Char(
        string='限制連記決議',
        help='人民團體選舉罷免辦法 §4：限制連記法須經出席人數三分之一以上同意。請登錄決議內容。')
    tie_entropy = fields.Char(
        string='同票抽籤亂數',
        help='開票遇到同票跨越當選／候補界線時，由監票員現場擲骰或抽籤後填入，再按開票。')
    draw_entropy = fields.Char(
        string='號次抽籤亂數',
        help='監票員現場擲骰或抽籤後由選務填入；凍結名冊時由系統據此決定號次，'
             '任何人都能用同一條公式重算驗證。留空則不編號（或沿用手填的號次）。')
    observer_user_ids = fields.Many2many(
        'res.users', 'assoc_election_observer_rel', 'election_id', 'user_id', string='監票員',
        help='開始投票時快照寫入稽核鏈，之後不可變更。')

    close_xid = fields.Char(string='關票交易編號', readonly=True, copy=False)
    closed_at = fields.Datetime(string='關票時間', readonly=True, copy=False)
    counted_at = fields.Datetime(string='開票時間', readonly=True, copy=False)
    published_at = fields.Datetime(string='公告時間', readonly=True, copy=False)
    ballots_digest = fields.Char(string='選票摘要', readonly=True, copy=False)
    roster_final_digest = fields.Char(string='名冊摘要', readonly=True, copy=False)
    result_json = fields.Json(string='開票結果', readonly=True, copy=False)
    result_digest = fields.Char(string='結果摘要', readonly=True, copy=False)
    seal_void_reason = fields.Char(
        string='作廢封箱原因', groups=ADMIN_GROUP,
        help='封箱之後票匭與封存當下不符時，公會管理員在這裡寫下原因再按「作廢封箱」。'
             '這一句會永久留在稽核鏈上，監票員的離線驗算會把它印出來。')
    show_on_ticker = fields.Boolean(
        string='在跑馬燈顯示', default=True,
        help='公告後是否出現在公開跑馬燈。只顯示公會名、選舉名、公告日與當選／候補名單。')
    # 封存包本體在 `assoc.election.archive`（無 ACL），不是這裡的欄位：
    # 理由見 `assoc_election_archive.py` 檔頭。這裡只留不敏感的指紋與時間。
    archive_sha256 = fields.Char(string='封存包指紋', readonly=True, copy=False)
    archive_built_at = fields.Datetime(string='封存時間', readonly=True, copy=False)

    candidate_ids = fields.One2many('assoc.election.candidate', 'election_id', string='候選人')
    voter_ids = fields.One2many('assoc.election.voter', 'election_id', string='選舉人名冊')
    log_ids = fields.One2many('assoc.election.log', 'election_id', string='稽核鏈')

    voter_count = fields.Integer(string='名冊人數', compute='_compute_voter_stats')
    unissued_count = fields.Integer(string='未領票', compute='_compute_voter_stats')
    issued_count = fields.Integer(string='已領未投', compute='_compute_voter_stats')
    voted_count = fields.Integer(string='已投票', compute='_compute_voter_stats')
    claimed_unarmed_count = fields.Integer(string='已領取未配對', compute='_compute_voter_stats')
    conflict_count = fields.Integer(string='領取衝突', compute='_compute_voter_stats')
    regenerate_count = fields.Integer(string='重新產生／重發次數', compute='_compute_voter_stats')
    chain_seq = fields.Integer(string='鏈長', compute='_compute_chain')
    chain_head = fields.Char(string='鏈頭', compute='_compute_chain')
    chain_verified = fields.Boolean(string='稽核鏈驗證通過', compute='_compute_chain')

    _sql_constraints = [
        ('uuid_uniq', 'unique(uuid)', '選舉識別碼重複'),
        ('director_seats_range', f'CHECK(director_seats BETWEEN 0 AND {MAX_DIRECTOR_SEATS})',
         f'理事應選名額須介於 0 到 {MAX_DIRECTOR_SEATS}'),
        ('supervisor_seats_range', f'CHECK(supervisor_seats BETWEEN 0 AND {MAX_SUPERVISOR_SEATS})',
         f'監事應選名額須介於 0 到 {MAX_SUPERVISOR_SEATS}'),
        ('alternates_non_negative', 'CHECK(director_alt >= 0 AND supervisor_alt >= 0)', '候補名額不可為負'),
    ]

    # ------------------------------------------------------------------
    # 計算欄位
    # ------------------------------------------------------------------
    def _compute_voter_stats(self):
        stats = {}
        real_ids = [e.id for e in self if isinstance(e.id, int)]
        if real_ids:
            self.env['assoc.election.voter'].flush_model()
            self.env.cr.execute("""
                SELECT election_id,
                       count(*),
                       count(*) FILTER (WHERE state IN ('eligible', 'voided')),
                       count(*) FILTER (WHERE state = 'issued'),
                       count(*) FILTER (WHERE state = 'voted'),
                       count(*) FILTER (WHERE state = 'issued' AND session_nonce IS NOT NULL AND armed_at IS NULL),
                       count(*) FILTER (WHERE claim_conflict),
                       COALESCE(sum(GREATEST(issue_count - 1, 0)), 0)
                  FROM assoc_election_voter
                 WHERE election_id IN %s
              GROUP BY election_id
            """, [tuple(real_ids)])
            stats = {row[0]: row[1:] for row in self.env.cr.fetchall()}
        for election in self:
            (election.voter_count, election.unissued_count, election.issued_count, election.voted_count,
             election.claimed_unarmed_count, election.conflict_count, election.regenerate_count
             ) = stats.get(election.id, (0, 0, 0, 0, 0, 0, 0))

    def _compute_chain(self):
        Log = self.env['assoc.election.log'].sudo()
        for election in self:
            if not isinstance(election.id, int):
                election.chain_seq, election.chain_head, election.chain_verified = 0, '', False
                continue
            head = Log.search([('election_id', '=', election.id)], order='seq desc', limit=1)
            election.chain_seq = head.seq
            election.chain_head = (head.entry_hash or '')[:16]
            election.chain_verified = election._verify_chain()

    # ------------------------------------------------------------------
    # 寫入守衛（安全帶，不是防線：帶 context 的呼叫者一行就能繞過）
    # ------------------------------------------------------------------
    @api.constrains('meeting_id', 'company_id')
    def _check_meeting_company(self):
        for election in self:
            if election.meeting_id.company_id != election.company_id:
                raise ValidationError(_('會員大會必須屬於同一公會'))

    @api.model_create_multi
    def create(self, vals_list):
        if not guarded(self.env, GUARD_STATE):
            # 識別碼同時是大螢幕的公開網址（`/assoc/screen/<uuid>`，auth='public'）。
            # **不驗輸入、直接重發**：從產出的值看不出來它是隨機的還是挑的
            # ——version 4 的格式誰都寫得出來——所以唯一可靠的做法是
            # 讓呼叫端根本影響不了它。明寫在 vals 裡也會蓋掉 `default_uuid`。
            vals_list = [dict(vals, uuid=str(uuid_lib.uuid4())) for vals in vals_list]
        elections = super().create(vals_list)
        check_created(elections, CREATED_INITIAL, GUARD_STATE)
        return elections

    def write(self, vals):
        if not guarded(self.env, GUARD_STATE):
            business = set(vals) - set(self.env['mail.thread']._fields)
            if business & SYSTEM_FIELDS:
                raise UserError(_('選舉狀態與開票結果只能經由選務按鈕變更'))
            for election in self:
                if not business or election.state == 'draft':
                    continue
                if election.state == 'ballot_ready' and business <= BALLOT_READY_WRITABLE_FIELDS:
                    continue
                if election.state == 'closed' and business <= CLOSED_WRITABLE_FIELDS:
                    continue
                if election.state == 'published' and business <= PUBLISHED_WRITABLE_FIELDS:
                    continue
                raise UserError(_('「%(name)s」已開始投票，設定不可再變更', name=election.name))
        return super().write(vals)

    def unlink(self):
        if any(e.state not in ('draft', 'cancelled') for e in self):
            raise UserError(_('只有草稿或已取消的選舉可以刪除'))
        return super().unlink()

    # ------------------------------------------------------------------
    # 規則參數
    # ------------------------------------------------------------------
    def _seat_counts(self, office):
        self.ensure_one()
        if office == 'director':
            return self.director_seats, self.director_alt
        return self.supervisor_seats, self.supervisor_alt

    def _active_offices(self):
        self.ensure_one()
        return [code for code, _label in OFFICES if self._seat_counts(code)[0] > 0]

    def _max_marks(self, office):
        """§4：應選 1 名為單記法；2 名以上連記法；限制連記法為應選名額之半（至少 1）。"""
        seats = self._seat_counts(office)[0]
        if seats <= 1:
            return seats
        if self.mark_limit_mode == 'half_floor':
            return max(1, seats // 2)
        return seats

    def _roster_snapshot(self):
        """凍結名冊快照：{會員 id: (會員編號, 姓名)}。可被圈選的會員就是這些人。"""
        self.ensure_one()
        self.env['assoc.election.voter'].flush_model(['election_id', 'member_id', 'member_no', 'member_name'])
        self.env.cr.execute(
            "SELECT member_id, member_no, member_name FROM assoc_election_voter WHERE election_id = %s", [self.id])
        return {member_id: (member_no, name) for member_id, member_no, name in self.env.cr.fetchall()}

    def _electable_member_ids(self):
        return list(self._roster_snapshot())

    def _search_roster(self, query, limit):
        """名單外搜尋：只搜凍結名冊快照的姓名，萬用字元先跳脫。"""
        self.ensure_one()
        pattern = f'%{escape_like(query)}%'
        return self.env['assoc.election.voter'].sudo().search(
            [('election_id', '=', self.id), ('member_name', '=ilike', pattern)], limit=limit)

    def _ballot_header(self):
        """選罷辦法 §6 I 要求選舉票載明的要件裡，**這一支給的是屆次與年月日**。

        另外兩個不在這裡：「職稱」是逐區塊的（`_ballot_offices()` 的 `label`），
        「團體名稱」由共用版型的 heading 印——領取頁與錯誤頁也要印它，所以它
        不經這一支。原本這裡還回一個 `organization`，而**沒有任何呼叫端讀它**
        （樣板印的是 `election.company_id.name`），於是這段 docstring 宣稱的
        「§6 的要件只能有一個來源」對團體名稱一開始就不成立，而守它的測試
        `assertIn(self.company.name, html)` 由版型那一行滿足、對那個鍵恆真
        （第二輪 simplifier 與 red-team 各自指到這裡）。

        **目前只有電子選票頁一個呼叫端**（`controllers/vote.py`）；紙本選票 PDF
        （M12）還不存在，它落地時要呼叫這一支而不是自己再算一次——§6 的要件
        只能有一個來源，兩個地方各寫一次就是還沒修好（L9）。
        （原本這段寫成「兩者共用」，那是把計畫寫成現況，L5③。）

        **年月日取大會日，不是列印日**——同一場選舉重印選票不可以換日期；
        而且電子票與紙本票必須印出同一個日期，否則 §6 的「擇一」會變成
        兩種媒介各說各話。
        **但「不會換」只在大會離開草稿之後才成立**：`LOCKED_AFTER_DRAFT` 要到
        那時才生效，而選舉的狀態機完全不看大會的狀態。大會還在草稿時改
        `date_begin`，鏈上是凍結當下的快照、這一支回的是每次請求重算的即時值
        ——兩者就此不一致，而沒有任何東西會紅（第二輪 red-team；離線驗算把
        鏈上那個值印出來就是為了讓人看得出這件事）。
        """
        self.ensure_one()
        begin = self.meeting_id.date_begin
        local = (fields.Datetime.context_timestamp(self.with_context(tz=ASSOC_TZ), begin)
                 if begin else None)
        # `term_no` 與 `organization` 的原始值**刻意不回**：樣板要印的是
        # 「第 N 屆」，公會名由版型印——多回沒人讀的鍵只會讓下一個人以為它
        # 有用，而「§6 單一來源」那句話也就名不副實（第二輪 simplifier）。
        return {
            'term_label': term_label(self.term_no) if self.term_no else '',
            'date_label': local.strftime('%Y-%m-%d') if local else '',
        }

    def _ballot_offices(self):
        """投票頁用的職位與參考名單。"""
        self.ensure_one()
        offices = []
        for code in self._active_offices():
            candidates = self.candidate_ids.filtered(
                lambda c: c.office == code and c.state == 'confirmed')
            # **有號次就依號次排**（計畫 §10）：號次的意義就是印在選票上、
            # 讓會員照號碼找人。抽了號次卻不顯示，等於只是在資料庫裡記一個沒人看得到的數字。
            # 沒有號次時沿用既有排序（`_order` 是 sequence, member_no）。
            if all(c.ballot_number for c in candidates):
                candidates = candidates.sorted('ballot_number')
            offices.append({
                'code': code,
                'label': OFFICE_LABELS[code],
                'seats': self._seat_counts(code)[0],
                'max_marks': self._max_marks(code),
                'candidates': [{'member_id': c.member_id.id, 'member_no': c.member_no,
                                'name': c.member_name, 'ballot_number': c.ballot_number}
                               for c in candidates],
            })
        return offices

    def _prepare_ballots(self, choices_by_office):
        """投票時驗證並整理選票。任何不合法都在寫入前 raise AssocVoteError。

        §11：同一被選舉人圈兩次以一票計，所以先去重再檢查上限。
        """
        self.ensure_one()
        offices = self._active_offices()
        if not isinstance(choices_by_office, dict) or set(choices_by_office) != set(offices):
            raise AssocVoteError('invalid_choice', _('選票格式錯誤，請重新整理後再投'))
        electable = set(self._electable_member_ids())
        vals_list = []
        for office in offices:
            raw = choices_by_office[office]
            if not isinstance(raw, (list, tuple)):
                raise AssocVoteError('invalid_choice', _('選票格式錯誤，請重新整理後再投'))
            try:
                member_ids = {int(value) for value in raw}
            except (TypeError, ValueError):
                raise AssocVoteError('invalid_choice', _('選票內容無效，請重新圈選'))
            if len(member_ids) > self._max_marks(office):
                raise AssocVoteError('over_mark', _('%(office)s最多只能圈選 %(max)s 名',
                                                    office=OFFICE_LABELS[office], max=self._max_marks(office)))
            if not member_ids <= electable:
                raise AssocVoteError('invalid_choice', _('選票內容無效，請重新圈選'))
            choices = sorted(member_ids)
            vals_list.append({
                'election_id': self.id,
                'office': office,
                'choices': choices,
                'status': 'valid' if choices else 'invalid',
                'invalid_reason': False if choices else 'blank',
            })
        return vals_list

    # ------------------------------------------------------------------
    # 狀態機
    # ------------------------------------------------------------------
    def _check_officer(self):
        if not (self.env.su or self.env.user.has_group(OFFICER_GROUP)):
            raise AccessError(_('權限不足：此操作限選務人員'))

    def _check_guild_admin(self):
        """限公會管理員。**與 `_check_officer` 刻意分開**：

        作廢封箱是「承辦說票匭有問題」的例外出口，理由該由辦選舉以外的人記錄。
        **光有這道是不夠的**：第十二輪 skeptic 實跑指出，被把關的只有「那一下點擊」，
        而 `seal_void_reason` 原本是一般欄位、officer 對 `assoc.election` 有寫權，
        於是鏈上掛著管理員名字的那句話可以是承辦打的——歸因本身在說謊。
        所以那個欄位也上了 `groups=ADMIN_GROUP`，並在作廢後清空。
        身兼兩職的人當然兩道都過——這裡買到的是工位分離的可能性，不是保證。

        第十三輪起改走共用的 `check_guild_admin`：它**同時**驗公會。
        原本只驗群組，而作廢封箱之後整條走 sudo，於是別家公會的管理員
        也作廢得了這一場的封箱（同一根因見 `tools.assert_own_company`）。
        """
        check_guild_admin(self, _('權限不足：此操作限公會管理員'))

    def _transition(self, to_state, from_states, extra_vals=None, payload=None):
        self.ensure_one()
        if self.state not in from_states:
            raise UserError(_('「%(name)s」目前狀態不能執行此動作', name=self.name))
        from_state = self.state
        self.with_context(**{GUARD_STATE: GUARD}).write({'state': to_state, **(extra_vals or {})})
        self.env['assoc.election.log']._append(
            self, 'state_change', {'from': from_state, 'to': to_state, **(payload or {})})

    def action_ready(self):
        """凍結名冊：確認候選人、依會籍與會費快照建立選舉人名冊（§5 名冊審定）。"""
        self._check_officer()
        Voter = with_guard(self.env['assoc.election.voter'].sudo(), GUARD_BOX)
        for election in self:
            if election.state != 'draft':
                raise UserError(_('只有草稿可以凍結名冊'))
            offices = election._active_offices()
            if not offices:
                raise UserError(_('理事與監事至少一個職位的應選名額要大於 0'))
            if election.mark_limit_mode == 'half_floor' and not (election.limit_resolution_note or '').strip():
                raise UserError(_('採限制連記法須先登錄出席人數三分之一以上同意的決議'))
            # 選罷辦法 §6 I 要求選舉票載明選舉屆次——**紙本與電子票都一樣**，
            # 不是只有紙本。閘放在凍結名冊這一步而不是建檔：建檔當下屆次可能還
            # 沒成立（新公會第一屆、補選要等出缺），但凍結之後就要印票了。
            if not election.term_id:
                raise UserError(_(
                    '請先指定「%(name)s」的屆次：選罷辦法 §6 要求選舉票載明選舉屆次。',
                    name=election.name))
            # **寫一下這一屆再讀它的號次**（no-op UPDATE，不是只鎖）：改屆次與凍結名冊
            # 寫的是不同列，Python 層的守衛擋不住兩者同時成立（write skew，第三輪
            # red-team）。兩邊都寫屆次這一列，REPEATABLE READ 下誰後到誰吃 40001、
            # 整個請求重跑，重跑時看得到對方。第四輪寫的是 `SELECT … FOR UPDATE`、
            # 註解說「對方會重讀」——那是 READ COMMITTED 的行為；RR 下只鎖不改，
            # 「凍結先提交」那個順序的後到者沿用舊快照、守衛放行（第五輪 skeptic，
            # 兩條真連線實測；兩種順序都在 `test_term_concurrency.py`）。
            election.term_id.flush_recordset()
            self.env.cr.execute(
                'UPDATE assoc_term SET write_date = write_date WHERE id = %s',
                (election.term_id.id,))
            # 同公會：`domain` 只管前台表單，RPC 直接寫 `term_id` 繞得過去，
            # 而屆次是跨公會可見的 m2o（record rule 擋讀取，擋不了「寫一個看不到
            # 的 id 進來」）。fail-closed。
            if election.term_id.company_id != election.company_id:
                raise UserError(_('屆次與選舉必須屬於同一個公會。'))
            # fail-closed 的保險帶，**沒有對應的 mutant**：`assoc.term` 有
            # `CHECK(term_no > 0)`，所以正常情況下這一行打不到，隔離不出來的
            # mutant 會假存活。
            # 留著的理由**不是**「Odoo 對加不上的約束只記 warning」——那個情境
            # 是對**既有資料**加約束，而 `assoc.term` 是新建的空表，約束一定加
            # 得上，所以那個狀態在這個 schema 構造不出來（第二輪 simplifier
            # 指出這個理由寫錯）。真實的殘餘風險只有「有人直接下 SQL 把約束
            # DROP 掉」或「日後改 schema 時把它弄掉」——選票不可以印出
            # 「第 0 屆」，所以這一行留著。
            # （L2⑯：不要為了讓 mutation 好看就刪掉縱深，但要說清楚為什麼沒有。）
            if election.term_id.term_no <= 0:
                raise UserError(_('屆次必須大於 0 才能印在選票上。'))
            members = self.env['assoc.member'].search(
                [('company_id', '=', election.company_id.id)]).filtered('is_voter_eligible')
            active_candidates = election.candidate_ids.filtered(lambda c: c.state != 'withdrawn')
            ineligible = active_candidates.filtered(lambda c: c.member_id not in members)
            if ineligible:
                raise UserError(_('下列候選人不具選舉權（停權或會費未繳）：%s',
                                  '、'.join(ineligible.mapped('member_id.display_name'))))
            stray = active_candidates.filtered(lambda c: c.office not in offices)
            if stray:
                raise UserError(_('下列候選人登記的職位本場不選：%s', '、'.join(stray.mapped('member_id.display_name'))))
            for candidate in active_candidates:
                candidate.with_context(**{GUARD_STATE: GUARD}).write({
                    'state': 'confirmed',
                    'member_no': candidate.member_id.member_no,
                    'member_name': candidate.member_id.name,
                })
            draw_method = election._assign_ballot_numbers(active_candidates, offices)
            Voter.create([{'election_id': election.id, 'member_id': member.id,
                           'member_no': member.member_no, 'member_name': member.name} for member in members])
            election._transition('ballot_ready', ('draft',), extra_vals={
                # 快照：之後改屆次資料（或改 `term_id`）都不會動到選票上印的數字
                'term_no': election.term_id.term_no,
            }, payload={
                'roster_count': len(members),
                # §6 的「選舉屆次」要件。進 `ballot_ready` 而不是 `counted`：
                # 它必須在**第一張票發出去之前**就定下來，承諾的時點才對得上
                # 監票員手上那張票（L1⑫）。
                'term_no': election.term_id.term_no,
                # §6 的「年月日」要件。它讀的是 `meeting_id.date_begin`，而
                # **選舉的狀態機完全不檢查大會狀態**——大會還在草稿時那個日期
                # 改得動，改了票面就換日期而且沒有任何東西會紅（抗辯實查）。
                # 擋它的 `LOCKED_AFTER_DRAFT` 在另一個模組、只在大會離開草稿後
                # 才生效，所以這裡自己留一個錨點：離線驗算把它印出來，監票員
                # 拿票面對得到。**只印不判**——包裡沒有別的東西可以跟它互比，
                # 判了就是一道永遠不會 FAIL 的閘（L1①）。
                'meeting_date': election._ballot_header()['date_label'],
                'offices': {code: {'seats': election._seat_counts(code)[0],
                                   'alternates': election._seat_counts(code)[1],
                                   'max_marks': election._max_marks(code)} for code in offices},
                # 這兩個鍵**線上離線都沒有任何讀者**，是純存證（§4 的限制連記
                # 決議要留痕）：`max_marks` 本身已經被 `seats_match_frozen_roster`
                # 綁回鏈，所以它們不當任何檢查的基準。寫明是因為第二輪抓到過
                # `roster_count` 是「寫進鏈卻沒人讀」而被誤認為有防線在守
                # （第四輪 simplifier 指出這兩個是同一類，只是無害）。
                'mark_limit_mode': election.mark_limit_mode,
                'limit_resolution_note': election.limit_resolution_note or '',
                'candidates': sorted(f'{c.office}:{c.member_no}:{c.member_name}' for c in active_candidates),
                'roster_digest': election._compute_roster_digest(),
                # 號次併入既有的 ballot_ready payload（P19）：不新增 log action、
                # 也不動 `_verify_chain`——那支只看 state_change，安全關鍵不要為了功能改
                'draw_method': draw_method,
                'draw_entropy': election.draw_entropy or '',
                'ballot_numbers': sorted(
                    f'{c.office}:{c.ballot_number}:{c.member_no}' for c in active_candidates),
            })
        return True

    def _assign_ballot_numbers(self, candidates, offices):
        """決定號次，回傳採用的方法（system／manual／none）。

        三條路（計畫 §10）：
        - 填了 `draw_entropy`：**系統抽籤**。種子只由公開資訊組成，任何人拿到封存包
          都能用同一條公式重算，驗得出承辦沒有動手腳。
        - 沒有亂數但每個職位的號次都手填齊了：**實體抽籤**的結果，只驗 1..n 不重複。
        - 兩者皆無：不編號，選票依會員編號排序。

        亂數本身由監票員現場擲骰產生——系統只負責「用它算出一個可重算的結果」，
        不負責產生隨機性（自己產生的話，沒有人能驗證它不是挑出來的）。
        """
        self.ensure_one()
        entropy = (self.draw_entropy or '').strip()
        by_office = {code: candidates.filtered(lambda c: c.office == code).sorted('member_no')
                     for code in offices}
        if entropy:
            for code, group in by_office.items():
                seed = verify_core.draw_seed(self.uuid, code, entropy, group.mapped('member_no'))
                order = list(group)
                random.Random(seed).shuffle(order)
                for index, candidate in enumerate(order, start=1):
                    candidate.with_context(**{GUARD_STATE: GUARD}).ballot_number = index
            return 'system'

        numbered = [c for c in candidates if c.ballot_number]
        if not numbered:
            return 'none'
        for code, group in by_office.items():
            if not group:
                continue
            numbers = sorted(group.mapped('ballot_number'))
            if numbers != list(range(1, len(group) + 1)):
                # 最常見的成因是**有人退選**：號次是退選前編的，少掉中間某一號。
                # 不講這件事的話，承辦看到「必須是 1 到 4」會以為是自己打錯字。
                withdrawn = self.candidate_ids.filtered(
                    lambda c, code=code: c.office == code and c.state == 'withdrawn')
                hint = _('有 %(n)s 位候選人已退選，請把剩下的 %(count)s 位重新編成 '
                         '1 到 %(count)s。', n=len(withdrawn), count=len(group)
                         ) if withdrawn else _('要改由系統抽籤請填「號次抽籤亂數」。')
                raise UserError(_(
                    '「%(office)s」的號次必須是 1 到 %(count)s 且不重複（目前：%(got)s）。%(hint)s',
                    office=dict(OFFICES)[code], count=len(group),
                    got='、'.join(str(n) for n in numbers), hint=hint))
        return 'manual'

    def action_open(self):
        """開始投票：監票員名單快照入鏈並鎖定。"""
        self._check_officer()
        for election in self:
            if not election.voter_ids:
                raise UserError(_('選舉人名冊是空的'))
            observers = [{'uid': user.id, 'login': user.login, 'user_created': utc_iso(user.create_date)}
                         for user in election.observer_user_ids.sorted('id')]
            election._transition('open', ('ballot_ready',), payload={'observers': observers})
        return True

    def action_start_closing(self):
        """停止領票：不再產生新 QR、不再接受領取；已領取者仍可配對與投出。"""
        self._check_officer()
        for election in self:
            election._transition('closing', ('open',))
        return True

    def action_close(self):
        """關票。記下本交易的 xid，開票時用來確認開票快照涵蓋所有在關票前 commit 的選票。

        這個 UPDATE 會等在途投票交易釋放 election 列上的 FOR SHARE 鎖；之後才到的投票交易
        在 REPEATABLE READ 下收到 40001，重跑時看到 closed 而被拒。
        """
        self.ensure_one()
        self._check_officer()
        self.env.cr.execute("SELECT pg_current_xact_id()::text")
        xid = self.env.cr.fetchone()[0]
        # ------------------------------------------------------------------
        # **這裡曾經放過一個票匭摘要，第九輪撤回了。不要再加回來。**
        #
        # 第八輪為了縮短「關票完成 → 按下開票」之間那段沒有承諾的空窗，
        # 把 `ballots_digest` 寫進這一筆的 payload。兩個獨立的鏡頭各自實跑證明它是錯的：
        #
        # ①**它看不到在途選票。** Python 先求值引數，所以摘要在 state 的 UPDATE
        #   之前就算完；而 Odoo 的 cursor 是 REPEATABLE READ，快照在**整個請求的
        #   第一句 SQL** 就固定了。上面那句 docstring 說「UPDATE 會等在途投票交易
        #   釋放 FOR SHARE」——等鎖保證的是「UPDATE 排在在途票之後」，
        #   而需要保證的是「**快照**排在它之後」，方向相反。於是被設計明文允許、
        #   會被收下的那些票，進了票匭卻不在摘要裡。
        # ②**於是它反過來替舞弊背書。** 承辦自己從 psql 握住本列的 FOR SHARE 不放，
        #   按下關票讓 UPDATE 排隊（卡多久由他決定，實測 6.37 秒），這段時間投票
        #   完全不受影響（在途投票取 FOR SHARE 只要 0.002 秒）；那些票因此落在承諾之外。
        #   事後把它們刪掉、砍掉 counted 那一筆、退回 closed 重跑——離線驗算 32 項全 OK、
        #   退出碼 0，而關票鏈頭與監票員當場抄的逐字元相同。
        #   **「票不見了」被這一項認證成「票匭沒被動過」。**
        # ③附帶：它是必要欄位，於是追溯把 26 場既有的誠實選舉判成驗鏈失敗
        #   （欄位已進雜湊、補不回來），後台對乾淨資料喊「請通報監票員」。
        #   而一場完全乾淨的選舉只要有人在關票同時投出在途票，就會永久卡在 counted。
        #
        # 真正的結論是：**任何由承辦自己觸發的承諾，都可以在觸發前先竄改**；
        # 關票到開票之間的空窗擋不住，那是流程控制（監票員在場、當場開票）的事。
        # 這件事現在誠實寫在離線驗算腳本的【程式驗不到的部分】裡，不用技術假象蓋過去。
        # ------------------------------------------------------------------
        self._transition('closed', ('closing',),
                         extra_vals={'close_xid': xid, 'closed_at': self.env.cr.now()},
                         payload={'close_xid': xid})
        return True

    def action_cancel(self):
        self._check_officer()
        for election in self:
            election._transition('cancelled', EDITABLE_STATES)
        return True

    def action_seal_ballots(self):
        """封存票匭：把當下的票匭摘要記進稽核鏈。**關票之後、開票之前按，當場按。**

        為什麼需要這一步，以及為什麼它必須是**獨立的一個請求**：

        關票到開票之間是承辦一個人的時間。第十輪抗辯實跑：這段時間下一句
        `UPDATE assoc_election_ballot SET choices = …`（每職位張數與 status 全不動，
        所以 `_assert_ballot_count` 擋不到），再照正常按鈕開票公告產包——
        稽核鏈一個位元都沒偽造、`_verify_chain()` 回 True、離線驗算 31 項全 OK
        退出碼 0，而當選名單整組換掉。

        第八輪試過把摘要寫進**關票那一筆**，錯在兩個地方（見 `action_close` 的長註解）：
        它在關票的請求裡算，而 Odoo 的 cursor 是 REPEATABLE READ、快照在請求的第一句
        SQL 就固定，所以**看不到 `closing` 期間被設計明文允許收下的在途票**。

        這一步不同：它是**自己的請求**，快照晚於關票的 commit，所以看得到每一張票
        （`_assert_snapshot` 用的就是這個性質）。因此它可以承諾**相等**，
        而不必退而求其次去比對子集——後者會讓「哪幾張是在途票」變得可辨識，
        配上名冊到分鐘的 `voted_at` 就能指認那位投票人，直接傷到 D1 的無記名。

        **只能封一次。** 允許重封等於允許「改完再封」，這道防線就沒了。

        殘餘：關票到封箱之間仍然是空窗。擋它的不是程式，是「當場封、監票員在場、
        鏈上那兩筆的時間差看得見」——離線驗算會把那個時間差印出來給監票員判斷。
        """
        self.ensure_one()
        self._check_officer()
        if self.state != 'closed':
            raise UserError(_('只有關票之後、開票之前可以封存票匭'))
        # **「必須是自己的請求」原本只寫在 docstring 裡，沒有任何程式在守**
        # （第十一輪 skeptic）：整段設計的前提是「封箱的快照晚於關票 commit，
        # 所以看得到每一張在途票」，而把 close 與 seal 寫進同一個請求
        # （便利按鈕、server action、腳本）會靜默退回第八輪被否決的那個版本
        # ——摘要漏掉在途票，誠實的選舉在開票時卡死。
        # `_assert_snapshot()` 問的正是「關票那一筆在我現在的快照裡看得見嗎」，
        # 同一句話對封箱成立，所以直接用它。
        # 附帶效果：全部用 TransactionCase 的測試會因此紅——那正是問題所在
        # （L2⑫：測試釘死了唯一能讓前提為假的那種幾何）。
        self._assert_snapshot()
        # 重封守衛要問「鏈上有沒有封箱那一筆」，**不能問 `_sealed_entry()`**：
        # 後者在「超過一筆」時回 None（那是它對開票的正確語意），於是鏈上已經有
        # 兩筆時第三次按封箱不會被擋，操作者收到「成功」而選舉其實永久開不了票
        # （第十一輪 skeptic 實跑）。
        # 重封守衛要問「**現行**有沒有一筆有效的封箱」。
        # 不可以問 `_sealed_entry()`：它在「結構有問題」時也回 None（那是它對開票的
        # 正確語意），於是鏈上已經有兩筆時第三次封箱不會被擋，操作者收到「成功」
        # 而選舉其實永久開不了票（第十一輪 skeptic 實跑）。
        # 也不可以問「鏈上有沒有出現過 ballots_sealed」：那會讓合法的
        # 「作廢後重封」永遠封不了。
        seq, _payload, _voids, problem = verify_core.live_seal(self._chain_entries())
        if problem:
            raise UserError(_('稽核鏈上的封箱紀錄有問題（%s），請通報監票員', problem))
        if seq is not None:
            raise UserError(_('票匭已經封存過了，不能重封'
                              '（真的需要重封時，請由公會管理員寫下原因後作廢）'))
        self.env['assoc.election.log']._append(self, 'ballots_sealed', {
            'ballots_digest': self._compute_ballots_digest(),
            'ballot_count': self._assert_ballot_count(),
        })
        return True

    ballots_sealed = fields.Boolean(
        string='票匭已封存', compute='_compute_ballots_sealed',
        help='關票之後、開票之前按「封存票匭」才會是 True；封箱那一筆記在稽核鏈上。')

    @api.depends('log_ids')
    def _compute_ballots_sealed(self):
        for election in self:
            election.ballots_sealed = bool(election._sealed_entry())

    def _chain_entries(self):
        """鏈上每一筆的精簡形狀，給 `verify_core` 的公式用（線上線下同一支）。"""
        self.ensure_one()
        return [{'seq': log.seq, 'action': log.action, 'payload': log.payload or {}}
                for log in self.log_ids.sorted('seq')]

    def _sealed_entry(self):
        """**現行**那一筆封箱的 payload；沒有、有問題、或不只一筆有效都回 None。

        「現行」用排除法決定（被作廢紀錄指名的不算），公式在
        `verify_core.live_seal()`——線上與離線共用同一支，否則兩邊對同一條鏈
        算出不同的基準時沒有人知道哪邊錯（第四輪的教訓）。
        """
        self.ensure_one()
        _seq, payload, _voids, problem = verify_core.live_seal(self._chain_entries())
        return None if problem else payload

    def action_void_seal(self):
        """作廢現行的封箱，讓這場選舉可以重新封箱。**入鏈、要原因、限公會管理員。**

        為什麼要有這條出口：封箱之後票匭一旦與封存當下不符（還原備份、修復腳本、
        或真的有人動過），原本這場選舉就卡死了——不能開票、不能重封、
        `action_cancel` 不吃 `closed`、也刪不掉。對一場誠實但資料被動到的選舉，
        唯一的復原手段是下 SQL，而那完全無痕（第十一輪紅隊 medium）。

        為什麼它不是繞過防線：作廢與隨後的重封各自都是鏈上的一筆，
        所以「封箱 → 改票 → 作廢 → 再封箱」會在鏈上留下兩筆多出來的紀錄，
        而監票員在第一次封箱抄下的鏈頭從此不再是鏈頭。擋不住，但看得見
        ——這正是本專案對「持後台權限者」一貫的定調。
        離線驗算會把每一筆作廢紀錄與原因印出來要求監票員判斷。

        **限公會管理員、不是承辦**：作廢的理由該由辦選舉以外的人記錄。
        """
        self.ensure_one()
        self._check_guild_admin()
        if self.state != 'closed':
            raise UserError(_('只有在關票之後、開票之前可以作廢封箱'))
        seq, _payload, _voids, problem = verify_core.live_seal(self._chain_entries())
        if problem:
            raise UserError(_('稽核鏈上的封箱紀錄本身有問題（%s），請通報監票員', problem))
        if seq is None:
            raise UserError(_('這場選舉還沒有封箱，沒有東西可以作廢'))
        reason = (self.seal_void_reason or '').strip()
        if not reason:
            raise UserError(_('請先在「作廢封箱原因」寫下原因——這一句會永久留在稽核鏈上'))
        self.env['assoc.election.log']._append(self, 'ballots_seal_voided', {
            'voided_seq': seq,
            'reason': reason,
            # 作廢當下的票匭摘要：與被作廢那一筆一比，差異就永久留在鏈上
            'ballots_digest_now': self._compute_ballots_digest(),
        })
        # **用完要清掉。** 不清的話這場選舉的 `seal_void_reason` 永遠不空，
        # 於是「請先寫下原因」那道閘第二次以後永遠不會 FAIL——下一次作廢會掛著
        # **上一次**的說明，而管理員什麼都沒寫（第十二輪 skeptic + simplifier）。
        # 順帶消掉「畫面上那一句與鏈上那一句不一致」的窗口：鏈是權威，
        # 欄位只是輸入格，用完就該空著。
        self.seal_void_reason = False
        return True

    def action_count(self):
        """開票。必須與關票是不同的請求（開票交易的快照要晚於關票 commit）。"""
        self.ensure_one()
        self._check_officer()
        self._assert_snapshot()
        # **封箱之後票匭就不准再變。** 沒封箱不給開票：否則這道防線靠的是
        # 「承辦記得按」，而那等於沒有防線。
        _seq, sealed, _voids, problem = verify_core.live_seal(self._chain_entries())
        if problem:
            # 「還沒封箱」與「鏈上的封箱紀錄本身有問題」的處置完全不同，
            # 混成同一句話會讓承辦去按封箱鈕，然後被另一個訊息擋下來。
            raise UserError(_('稽核鏈上的封箱紀錄有問題（%s），拒絕開票，請通報監票員', problem))
        if sealed is None:
            raise UserError(_('開票之前要先封存票匭（關票後按「封存票匭」，請當著監票員的面按）'))
        if sealed.get('ballots_digest') != self._compute_ballots_digest():
            raise UserError(_('票匭與封存當下不符，拒絕開票，請通報監票員'))
        self._assert_ballot_status()
        ballot_count = self._assert_ballot_count()
        # **摘要相等不代表筆數相等**——摘要是對集合算的，而這裡要的是對帳
        # （L1⑧：凡是對一份集合算摘要，一定要另外對帳筆數，並找獨立來源互相比）。
        # `_assert_ballot_count()` 的來源是選舉人名冊，與摘要的來源是票匭本身，
        # 兩者獨立。原本這個值記進封箱 payload 卻沒有任何人比對，
        # 線上線下都不讀——一道永遠不會 FAIL 的裝飾（第十一輪三個鏡頭都指到）。
        if sealed.get('ballot_count') != ballot_count:
            raise UserError(_('票匭張數與封存當下不符（封存 %(sealed)s、現在 %(now)s），'
                              '拒絕開票，請通報監票員',
                              sealed=sealed.get('ballot_count'), now=ballot_count))
        self._shuffle_ballots(ballot_count)
        self._tally()
        return True

    def action_publish(self):
        self.ensure_one()
        self._check_officer()
        if self.state != 'counted':
            raise UserError(_('尚未開票'))
        # 不信任存下來的結果：從選票重算一次，並核對稽核鏈上開票那筆記錄
        if (self._compute_results()[1] != self.result_digest
                or verify_core.result_digest(self.result_json) != self.result_digest
                or not self._verify_chain()):
            raise UserError(_('開票結果與選票或稽核鏈不符，拒絕公告，請通報監票員'))
        self._transition('published', ('counted',), extra_vals={'published_at': self.env.cr.now()},
                         payload={'result_digest': self.result_digest})
        return True

    # ------------------------------------------------------------------
    # 開票
    # ------------------------------------------------------------------
    def _assert_snapshot(self):
        """開票快照必須看得到關票交易的 commit。

        同一交易內（或 READ COMMITTED 下）這個檢查會失效，所以兩者都要驗。
        不用 pg_snapshot_xmin > close_xid：同叢集任何無關的長交易（含 Odoo cron）都會讓它永遠不成立。
        """
        self.ensure_one()
        if self.state != 'closed' or not self.close_xid:
            raise UserError(_('尚未關票'))
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT current_setting('transaction_isolation'), pg_visible_in_snapshot(%s::xid8, pg_current_snapshot())",
            [self.close_xid])
        isolation, visible = self.env.cr.fetchone()
        if isolation != 'repeatable read' or not visible:
            raise UserError(_('這個動作必須與關票分成兩次獨立的操作'
                              '（封箱與開票都是），請重新整理頁面後再按一次'))

    def _assert_ballot_status(self):
        """每張票**存起來的**有效／無效判定，要與規則重算的結果一致。

        `_compute_results()` 是從 `choices` 重算的，**完全不讀** `status` 與
        `invalid_reason`——所以這兩欄在線上全程沒有人守。而監票員的離線驗算
        （`ballot_status`）會逐張比對它們。組合起來的後果是：關票之後
        某一列的 `invalid_reason` 被寫到（還原備份、修復腳本、或有人動過），
        票照開、公告照發，而**封存包永遠過不了**——而那時已經不可逆
        （第十一輪紅隊 medium）。

        `status` 有進票匭摘要（`ballot_hash` 涵蓋 office/choices/status），
        所以封箱那道會抓到；`invalid_reason` **沒有**，只有這一支抓得到。
        不把 `invalid_reason` 加進雜湊公式，是因為公式一改，既有已公告選舉
        寫進鏈裡的 `ballots_digest` 會全部對不上（L2⑱：加欄位到不可變結構之前，
        先問既有資料沒有它會怎樣）。正解是把**偵測**搬到還救得回來的時點。
        """
        self.ensure_one()
        self.env.flush_all()
        electable = set(self._roster_snapshot())
        self.env.cr.execute(
            "SELECT id, office, choices, status, invalid_reason FROM assoc_election_ballot "
            "WHERE election_id = %s ORDER BY id", [self.id])
        bad = []
        for ballot_id, office, choices, status, reason in self.env.cr.fetchall():
            expected = verify_core.recheck_ballot(
                [] if choices is None else choices, self._max_marks(office), electable)
            want_status = 'invalid' if expected else 'valid'
            if status != want_status or (reason or None) != expected:
                bad.append(ballot_id)
        if bad:
            raise UserError(_(
                '有 %(count)s 張選票存起來的有效／無效判定與規則重算的結果不符，'
                '拒絕開票，請通報監票員。（這代表關票之後有東西動過票匭，'
                '不處理的話票照開，但監票封存包永遠驗不過。）', count=len(bad)))
        return True

    def _assert_ballot_count(self):
        """**每個職位**的選票張數都必須等於已投票人數。

        只驗總和是不夠的：刪掉 N 張監事票、補進 N 張理事票，總數不變就放行，
        而開票會忠實地把灌過的結果寫進稽核鏈——紙本錨點完全吻合、不需要偽造任何一筆
        （第六輪抗辯實跑：監事 5 張變 2 張、理事 5 張變 8 張，照樣通過）。
        每個人在每個職位各投一張，所以每個職位的張數是各自固定的。
        """
        self.ensure_one()
        self.env.flush_all()
        cr = self.env.cr
        cr.execute("""SELECT count(*) FROM assoc_election_voter
                       WHERE election_id = %s AND state = 'voted'""", [self.id])
        voted = cr.fetchone()[0]
        cr.execute("""SELECT office, count(*) FROM assoc_election_ballot
                       WHERE election_id = %s GROUP BY office""", [self.id])
        by_office = dict(cr.fetchall())
        offices = self._active_offices()
        wrong = ['%s %s≠%s' % (OFFICE_LABELS.get(code, code), by_office.get(code, 0), voted)
                 for code in offices if by_office.get(code, 0) != voted]
        # 職位集合也要對：出現本場不選的職位同樣是動過手腳
        stray = sorted(set(by_office) - set(offices))
        if wrong or stray:
            raise UserError(_(
                '選票張數與已投票人數（%(voted)s）不符，停止開票，請通報監票員。'
                '不符的職位：%(wrong)s%(stray)s',
                voted=voted, wrong='、'.join(wrong) or '無',
                stray=('；本場不選的職位卻有票：' + '、'.join(stray)) if stray else ''))
        return voted * len(offices)

    def _shuffle_ballots(self, expected_count=None):
        """整批刪除後依亂序重新插入：所有選票拿到同一個新 xmin 與隨機 id，事後無法以寫入順序關聯選舉人。"""
        self.ensure_one()
        self.env.flush_all()
        cr = self.env.cr
        cr.execute("""
            WITH moved AS (
                DELETE FROM assoc_election_ballot WHERE election_id = %s
                RETURNING election_id, office, choices, status, invalid_reason
            )
            INSERT INTO assoc_election_ballot (election_id, office, choices, status, invalid_reason)
            SELECT election_id, office, choices, status, invalid_reason FROM moved ORDER BY random()
        """, [self.id])
        moved = cr.rowcount
        # xid 型別沒有排序運算子，DISTINCT 必須轉成 text
        cr.execute("SELECT count(DISTINCT xmin::text) FROM assoc_election_ballot WHERE election_id = %s", [self.id])
        distinct_xmin = cr.fetchone()[0]
        if (expected_count is not None and moved != expected_count) or (moved and distinct_xmin != 1):
            raise UserError(_('選票洗牌驗證失敗，停止開票'))
        self.env['assoc.election.ballot'].invalidate_model()
        return moved

    def _compute_ballots_digest(self):
        """與資料列順序無關的選票摘要（保留重複票）。"""
        self.ensure_one()
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT office, choices, status FROM assoc_election_ballot WHERE election_id = %s", [self.id])
        # **先把結果集取回來再碰 self**。Python 由左至右求值，`self.uuid` 若不在
        # 快取裡就會在 `execute` 與 `fetchall` 之間再下一次 ORM 查詢，用的是同一個
        # cursor——選票結果集被洗掉，摘要靜默變成**空票匭**的雜湊，不報錯不拋例外。
        # 目前被 prefetch 遮住（呼叫端先讀過 state），但真的發生時那場選舉會
        # 永久無法公告（`action_publish` 重算對不上已存摘要）。抗辯實測冷快取回 sha256("")。
        rows = self.env.cr.fetchall()
        return verify_core.ballots_digest(self.uuid, rows)

    def _compute_roster_digest(self):
        self.ensure_one()
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT member_id, member_no, member_name, state, voted_at
              FROM assoc_election_voter WHERE election_id = %s
        """, [self.id])
        return verify_core.roster_digest(
            verify_core.roster_line(member_id, no, name, state,
                                    utc_iso(voted_at, verify_core.ROSTER_TIME_FORMAT))
            for member_id, no, name, state, voted_at in self.env.cr.fetchall())

    def _compute_results(self):
        """純計算、不寫入：回傳 (result, result_digest)。"""
        self.ensure_one()
        ballots_digest = self._compute_ballots_digest()
        self.env.cr.execute(
            "SELECT office, choices FROM assoc_election_ballot WHERE election_id = %s ORDER BY id", [self.id])
        rows = self.env.cr.fetchall()
        roster = self._roster_snapshot()
        electable = set(roster)

        offices = {}
        for office in self._active_offices():
            seats, alternates = self._seat_counts(office)
            max_marks = self._max_marks(office)
            votes, invalid = Counter(), Counter()
            valid = 0
            for row_office, choices in rows:
                if row_office != office:
                    continue
                # fields.Json 把空陣列存成 NULL（fields.py convert_to_column: not value → None），空白票讀回來是 None
                reason = verify_core.recheck_ballot([] if choices is None else choices, max_marks, electable)
                if reason:
                    invalid[reason] += 1
                    continue
                valid += 1
                votes.update(choices)
            listed = set(self.candidate_ids.filtered(
                lambda c: c.office == office and c.state in ('confirmed', 'write_in')).member_id.ids) & electable
            entrants = sorted(listed | set(votes), key=lambda member_id: roster[member_id][0])
            ranked, ties = verify_core.rank_office(
                entrants, votes, seats, alternates, ballots_digest,
                office, self.tie_entropy)
            ranking = []
            for rank, member_id in enumerate(ranked, start=1):
                count = votes[member_id]
                outcome = verify_core.outcome_for(rank, count, seats, alternates)
                ranking.append({'member_id': member_id, 'member_no': roster[member_id][0],
                                'name': roster[member_id][1], 'votes': count, 'rank': rank, 'result': outcome})
            offices[office] = {
                'seats': seats, 'alternates': alternates, 'max_marks': max_marks,
                'valid_ballots': valid, 'invalid_ballots': sum(invalid.values()),
                'invalid_reasons': dict(sorted(invalid.items())),
                'boundary_ties': ties, 'ranking': ranking,
            }
        result = {
            'election_uuid': self.uuid,
            'ballots_digest': ballots_digest,
            'tie_entropy': self.tie_entropy or '',
            'offices': offices,
        }
        return result, verify_core.result_digest(result)

    def _tally(self):
        self.ensure_one()
        result, digest = self._compute_results()
        unresolved = [] if self.tie_entropy else [
            tie for data in result['offices'].values() for tie in data['boundary_ties']]
        if unresolved:
            detail = '；'.join(f"{OFFICE_LABELS[t['office']]} {t['votes']} 票 {len(t['member_ids'])} 人" for t in unresolved)
            raise UserError(_('有同票跨越當選／候補界線（%s）。請監票員現場抽籤後填入「同票抽籤亂數」，再按開票。', detail))
        Candidate = with_guard(self.env['assoc.election.candidate'].sudo(), GUARD_STATE)
        for office, data in result['offices'].items():
            existing = {c.member_id.id: c for c in self.candidate_ids.filtered(lambda c: c.office == office)}
            for row in data['ranking']:
                values = {'votes': row['votes'], 'rank': row['rank'], 'result': row['result'],
                          'member_no': row['member_no'], 'member_name': row['name']}
                candidate = existing.get(row['member_id'])
                if not candidate:
                    Candidate.create({'election_id': self.id, 'office': office, 'member_id': row['member_id'],
                                      'state': 'write_in', **values})
                    continue
                if candidate.state == 'withdrawn' and row['votes']:
                    values['state'] = 'write_in'  # 已退選但拿到名單外的票：依 §6 照算，標成名單外得票
                candidate.with_context(**{GUARD_STATE: GUARD}).write(values)
        roster_digest = self._compute_roster_digest()
        self.env.cr.execute(
            "SELECT receipt_code FROM assoc_election_voter "
            "WHERE election_id = %s AND receipt_code IS NOT NULL", [self.id])
        receipts = verify_core.receipts_digest([row[0] for row in self.env.cr.fetchall()])
        self._transition('counted', ('closed',), extra_vals={
            'counted_at': self.env.cr.now(),
            'ballots_digest': result['ballots_digest'],
            'roster_final_digest': roster_digest,
            'result_json': result,
            'result_digest': digest,
        }, payload={
            'ballots_digest': result['ballots_digest'],
            'roster_final_digest': roster_digest,
            'result_digest': digest,
            # 收據碼清單也要有錨點：它是會員唯一能親自核對的東西
            'receipts_digest': receipts,
            'voted': self.voted_count,
            'tie_entropy': self.tie_entropy or '',
            'boundary_ties': [t for data in result['offices'].values() for t in data['boundary_ties']],
        })

    @api.model
    def _ticker_elections(self, companies=None, limit=TICKER_LIMIT):
        """跑馬燈要顯示的場次：**已公告**且有勾選顯示。

        查詢放模型不放 controller：controller 只負責清洗參數與 sudo，
        「哪些場次可以公開」這件事要能被單元測試直接驗。
        """
        domain = [('state', '=', 'published'), ('show_on_ticker', '=', True)]
        if companies:
            domain.append(('company_id', 'in', list(companies)))
        return self.search(domain, order='published_at desc, id desc', limit=limit)

    # ------------------------------------------------------------------
    # 稽核鏈驗證
    # ------------------------------------------------------------------
    def _verify_chain(self):
        self.ensure_one()
        logs = self.env['assoc.election.log'].sudo().search([('election_id', '=', self.id)], order='seq')
        # 鏈的走訪用共用公式：線上與封存包裡的離線腳本跑同一段，
        # 兩邊不可能漂移（`verify_core` 的檔頭就在講這件事）
        if verify_core.verify_chain(
                [{'seq': log.seq, 'ts': log.ts, 'actor_uid': log.actor_uid,
                  'action': log.action, 'payload': log.payload or {},
                  'prev_hash': log.prev_hash, 'hash': log.entry_hash} for log in logs],
                self.uuid) is not None:
            return False
        if not logs:
            return self.state == 'draft'
        heads = logs.filtered('is_head')
        if len(heads) != 1 or heads != logs[-1:]:
            return False
        # 鏈本身自洽還不夠：帶 context 直接改紀錄可以繞過狀態機，所以要跟紀錄目前的值對照
        transitions = [(log.seq, log.payload.get('to'), log.payload)
                       for log in logs if log.action == 'state_change']
        if not transitions or transitions[-1][1] != self.state:
            return False
        # **每個狀態只能出現一次**。原本是 `{狀態: payload}`，天生取最後一筆：
        # 在鏈尾追加一筆重複的 `counted`（配合帶哨兵改欄位）就能讓這支回 True，
        # 於是**系統自己**會蓋章產出一包當選名單造假的封存檔（第四輪抗辯實跑複現）。
        if len({state for _seq, state, _payload in transitions}) != len(transitions):
            return False
        closed = verify_core.unique_transition(transitions, 'closed') or {}
        if self.state in ('closed', 'counted', 'published') and closed.get('close_xid') != self.close_xid:
            return False
        # 第八輪這裡曾經比對 `closed` payload 裡的票匭摘要，第九輪撤回——
        # 理由見 `action_close()` 的長註解（看不到在途票、反過來替舞弊背書、
        # 追溯判死 26 場既有的誠實選舉）。**不要再加回來。**
        if self.state in ('counted', 'published'):
            counted = verify_core.unique_transition(transitions, 'counted') or {}
            if (counted.get('result_digest') != self.result_digest
                    or counted.get('ballots_digest') != self.ballots_digest
                    or counted.get('roster_final_digest') != self.roster_final_digest):
                return False
        return True

    # ------------------------------------------------------------------
    # 報到台
    # ------------------------------------------------------------------
    def _desk_stats(self):
        self.ensure_one()
        return {
            'election_id': self.id, 'name': self.name, 'state': self.state,
            'voter_count': self.voter_count, 'unissued_count': self.unissued_count,
            'issued_count': self.issued_count, 'voted_count': self.voted_count,
            'conflict_count': self.conflict_count,
        }

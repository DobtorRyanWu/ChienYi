import hmac

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import (PAIR_CODE_DIGITS, AssocVoteError, clean_token, new_claim_token, new_nonce, new_pair_code,
                     new_receipt_code, sha256_hex)
from odoo.addons.assoc_base.tools import GUARD, check_created, guarded

from .assoc_election import GUARD_BOX, VOTING_STATES

# 領取 QR 有效秒數：從按下「領票」起算，要涵蓋會員走到螢幕前、開相機、瀏覽器冷啟動
CLAIM_WINDOW_SECONDS = 90
MAX_TOKEN_LENGTH = 64
# 只有系統管理員（等同資料庫擁有者）讀得到的票券欄位：選務人員若能讀 session_nonce 就能冒用手機
TICKET_FIELD_GROUPS = 'base.group_system'
# 重新領票或作廢時要一起清掉的票券欄位（issue 與 reissue 共用，新增票券欄位時只改這裡）
TICKET_RESET = dict.fromkeys((
    'session_nonce', 'pair_code', 'claimed_at', 'claim_device_hash',
    'armed_at', 'armed_by_uid', 'claim_conflict',
), False)


class AssocElectionVoter(models.Model):
    _name = 'assoc.election.voter'
    _description = '選舉人'
    _order = 'election_id, member_no, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    election_id = fields.Many2one('assoc.election', string='選舉', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='election_id.company_id', store=True, index=True)
    member_id = fields.Many2one('assoc.member', check_company=True, string='會員', required=True, ondelete='restrict', index=True)
    # 凍結名冊時的快照：之後會員或聯絡人資料被改，選票、搜尋與開票都不受影響
    member_no = fields.Char(string='會員編號', required=True, readonly=True)
    member_name = fields.Char(string='姓名', required=True, readonly=True)
    state = fields.Selection([
        ('eligible', '未領票'),
        ('issued', '已領票'),
        ('voted', '已投票'),
        ('voided', '已作廢待重發'),
    ], string='狀態', default='eligible', required=True, readonly=True)
    claim_hash = fields.Char(readonly=True, copy=False, groups=TICKET_FIELD_GROUPS)
    issued_at = fields.Datetime(string='領票時間', readonly=True)
    issued_by_uid = fields.Many2one('res.users', string='領票經手人', readonly=True)
    issue_count = fields.Integer(string='產生 QR 次數', readonly=True)
    session_nonce = fields.Char(readonly=True, copy=False, groups=TICKET_FIELD_GROUPS)
    claim_device_hash = fields.Char(readonly=True, copy=False, groups=TICKET_FIELD_GROUPS)
    pair_code = fields.Char(readonly=True, copy=False, groups=TICKET_FIELD_GROUPS)
    claimed_at = fields.Datetime(string='手機領取時間', readonly=True)
    armed_at = fields.Datetime(string='配對確認時間', readonly=True)
    armed_by_uid = fields.Many2one('res.users', string='配對經手人', readonly=True)
    claim_conflict = fields.Boolean(string='領取衝突', readonly=True, default=False)
    voted_at = fields.Datetime(string='投票時間', readonly=True)
    receipt_code = fields.Char(string='收據碼', readonly=True, copy=False, groups=TICKET_FIELD_GROUPS)

    _sql_constraints = [
        ('election_member_uniq', 'unique(election_id, member_id)', '同一會員在同一場選舉只能有一筆名冊紀錄'),
        ('session_nonce_uniq', 'unique(session_nonce)', '票券識別碼重複'),
        ('election_claim_hash_uniq', 'unique(election_id, claim_hash)', '領取碼重複'),
    ]

    # ------------------------------------------------------------------
    # 安全帶：名冊只能經由選務流程變更
    # ------------------------------------------------------------------
    def write(self, vals):
        if not guarded(self.env, GUARD_BOX):
            raise UserError(_('選舉人名冊只能經由選務流程變更'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 驗結果不驗輸入（§16 通則 1）：名冊是在 `action_ready` 建的，
        # 帶 `default_state='voted'` 的 context 就能建出「已投票」的名冊列——
        # 那個人從此領不到票，而對帳時「已投數」也對不上。
        check_created(records, {
            'state': 'eligible', 'claim_hash': False, 'session_nonce': False,
            'pair_code': False, 'armed_at': False, 'voted_at': False,
            'receipt_code': False, 'claim_conflict': False, 'issue_count': 0,
        }, GUARD_BOX)
        return records

    def unlink(self):
        if not guarded(self.env, GUARD_BOX):
            raise UserError(_('選舉人名冊不可刪除'))
        return super().unlink()

    # ------------------------------------------------------------------
    # 報到台：領票、配對、作廢重發（呼叫端以 sudo 執行，守衛在本方法與控制器）
    # ------------------------------------------------------------------
    def _issue(self):
        """產生一次性領取碼。明碼只回傳這一次，資料庫只存雜湊。

        已產生 QR 但還沒被手機領取時允許重新產生（QR 過期、會員沒掃到），舊的 QR 立即失效。
        """
        self.ensure_one()
        election = self.election_id
        if election.state != 'open':
            raise AssocVoteError('not_open', _('目前不是領票時段'))
        if self.state == 'voted':
            raise AssocVoteError('voted', _('此會員已投票'))
        if self.state == 'issued' and self.session_nonce:
            raise AssocVoteError('claimed', _('此會員的選票已被手機領取；若非本人領取，請由選務人員作廢重發'))
        attendance = self.env['assoc.meeting.attendance'].sudo().search(
            [('meeting_id', '=', election.meeting_id.id), ('member_id', '=', self.member_id.id)], limit=1)
        if attendance.state != 'present':
            raise AssocVoteError('absent', _('此會員尚未報到，不能領票'))
        token = new_claim_token()
        self.with_context(**{GUARD_BOX: GUARD}).write({
            **TICKET_RESET,
            'state': 'issued',
            'claim_hash': sha256_hex(token),
            'issued_at': self.env.cr.now(),
            'issued_by_uid': self.env.uid,
            'issue_count': self.issue_count + 1,
        })
        return token

    @api.model
    def _claim(self, election, token, cookie_nonce, device=None):
        """手機領取。回傳 {'status': claimed|already_mine|conflict|invalid, ...}。

        - 成功時不清 claim_hash：本人再送一次要能被認出來走冪等分支，別的裝置先領走要能偵測成衝突。
          單次領取的互斥條件是 session_nonce IS NULL。
        - device 是領取頁 GET 時發給這支手機的 HttpOnly cookie：第一個 POST 其實成功了、但回應沒送達
          （使用者在網路慢時又按了一次）時，同一裝置重送會補發原本的票券，而不是被當成衝突。
        - 所有時間比較一律 (now() AT TIME ZONE 'UTC')：Odoo 的 Datetime 是 naive UTC，
          而連線時區不固定（正式站可能是 Asia/Taipei），裸 now() 會差 8 小時。
        """
        token = clean_token(token, MAX_TOKEN_LENGTH)
        cookie_nonce = clean_token(cookie_nonce, MAX_TOKEN_LENGTH)
        device = clean_token(device, MAX_TOKEN_LENGTH)
        if not token:
            return {'status': 'invalid'}
        claim_hash = sha256_hex(token)
        device_hash = sha256_hex(device) if device else None
        nonce, pair = new_nonce(), new_pair_code()
        cr = self.env.cr
        self.env.flush_all()
        cr.execute("""
            UPDATE assoc_election_voter v
               SET session_nonce = %s, pair_code = %s, claim_device_hash = %s,
                   claimed_at = (now() AT TIME ZONE 'UTC')
             WHERE v.election_id = %s AND v.claim_hash = %s AND v.state = 'issued'
               AND v.session_nonce IS NULL
               AND v.issued_at > (now() AT TIME ZONE 'UTC') - make_interval(secs => %s)
               AND EXISTS (SELECT 1 FROM assoc_election e WHERE e.id = v.election_id AND e.state = 'open')
         RETURNING v.id
        """, [nonce, pair, device_hash, election.id, claim_hash, CLAIM_WINDOW_SECONDS])
        row = cr.fetchone()
        if row:
            self.invalidate_model()
            return {'status': 'claimed', 'voter': self.browse(row[0]), 'nonce': nonce}

        cr.execute("""
            SELECT id, state, session_nonce, claim_device_hash,
                   issued_at > (now() AT TIME ZONE 'UTC') - make_interval(secs => %s)
              FROM assoc_election_voter
             WHERE election_id = %s AND claim_hash = %s
        """, [CLAIM_WINDOW_SECONDS, election.id, claim_hash])
        row = cr.fetchone()
        if not row:
            return {'status': 'invalid'}
        voter_id, state, current_nonce, current_device, in_window = row
        if current_nonce and cookie_nonce and hmac.compare_digest(current_nonce, cookie_nonce):
            return {'status': 'already_mine', 'voter': self.browse(voter_id)}
        if (current_nonce and device_hash and current_device and state in ('issued', 'voted')
                and hmac.compare_digest(current_device, device_hash)):
            return {'status': 'already_mine', 'voter': self.browse(voter_id), 'nonce': current_nonce}
        if state == 'issued' and in_window and current_nonce:
            # 只有「90 秒窗內、別的裝置已領走」才算衝突；過期網址重放不污染對帳訊號
            cr.execute("UPDATE assoc_election_voter SET claim_conflict = true WHERE id = %s", [voter_id])
            self.invalidate_model()
            return {'status': 'conflict'}
        return {'status': 'invalid'}

    def _arm(self, pair_code):
        """選務輸入會員手機上顯示的配對碼。所有前置條件寫在同一個 UPDATE 裡。"""
        self.ensure_one()
        pair_code = (pair_code or '').strip()
        if len(pair_code) != PAIR_CODE_DIGITS or not pair_code.isdigit():
            return False
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE assoc_election_voter v
               SET armed_at = (now() AT TIME ZONE 'UTC'), armed_by_uid = %s
             WHERE v.id = %s AND v.state = 'issued' AND v.session_nonce IS NOT NULL
               AND NOT COALESCE(v.claim_conflict, false) AND v.pair_code = %s AND v.armed_at IS NULL
               AND EXISTS (SELECT 1 FROM assoc_election e WHERE e.id = v.election_id AND e.state IN %s)
         RETURNING v.id
        """, [self.env.uid, self.id, pair_code, VOTING_STATES])
        armed = bool(self.env.cr.fetchone())
        self.invalidate_recordset()
        return armed

    def _reissue(self, reason):
        """作廢重發：手機遺失或遭他人領取。停在 voided，必須回報到台重新領票。"""
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise AssocVoteError('reason', _('作廢重發必須填寫原因'))
        if self.election_id.state != 'open':
            raise AssocVoteError('not_open', _('只有投票中可以作廢重發'))
        if self.state != 'issued':
            raise AssocVoteError('state', _('只有已領票、尚未投票者可以作廢重發'))
        self.with_context(**{GUARD_BOX: GUARD}).write({
            **TICKET_RESET,
            'state': 'voided',
            'claim_hash': False,
            'issued_at': False,
        })
        self.env['assoc.election.log']._append(
            self.election_id, 'reissue', {'member_no': self.member_no, 'reason': reason})

    # ------------------------------------------------------------------
    # 投票
    # ------------------------------------------------------------------
    def _cast(self, choices_by_office):
        """投出選票。呼叫端必須包在 savepoint 內，並且只攔 AssocVoteError。

        40001（SerializationFailure）必須往外拋，讓 Odoo 的 retrying 用新快照重跑整個請求。
        """
        self.ensure_one()
        election = self.election_id
        cr = self.env.cr
        self.env.flush_all()
        cr.execute("SELECT state FROM assoc_election WHERE id = %s FOR SHARE", [election.id])
        if cr.fetchone()[0] not in VOTING_STATES:
            raise AssocVoteError('closed', _('投票時間已結束'))
        cr.execute("""SELECT state, armed_at FROM assoc_election_voter
                       WHERE id = %s AND election_id = %s FOR UPDATE""", [self.id, election.id])
        row = cr.fetchone()
        if not row or row[0] != 'issued':
            raise AssocVoteError('ticket', _('此票券無法投票'))
        if not row[1]:
            raise AssocVoteError('not_armed', _('尚未完成配對，請把手機出示給報到台人員'))
        ballot_vals = election._prepare_ballots(choices_by_office)
        receipt = new_receipt_code()
        self.env['assoc.election.ballot'].sudo().create(ballot_vals)
        self.env.flush_all()
        cr.execute("""
            UPDATE assoc_election_voter
               SET state = 'voted', voted_at = (now() AT TIME ZONE 'UTC'), receipt_code = %s
             WHERE id = %s AND state = 'issued'
         RETURNING id
        """, [receipt, self.id])
        if not cr.fetchone():
            raise UserError(_('投票狀態已變更，請重新整理'))
        self.invalidate_recordset()
        return receipt

    def _desk_card(self):
        """報到台顯示用。不含 nonce、配對碼、收據碼。"""
        self.ensure_one()
        election = self.election_id
        return {
            'voter_id': self.id,
            'election_id': election.id,
            'election_name': election.name,
            'election_state': election.state,
            'member_no': self.member_no,
            'name': self.member_name,
            'state': self.state,
            'claimed': bool(self.session_nonce),
            'armed': bool(self.armed_at),
            'conflict': self.claim_conflict,
        }

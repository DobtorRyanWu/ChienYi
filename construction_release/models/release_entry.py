# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .module_version import VERSION_EXAMPLE, custom_module_names, parse_version

ENTRY_TYPE_SELECTION = [
    ('fix', '修正'),
    ('feature', '新功能'),
    ('change', '調整'),
    ('remove', '移除'),
    ('refactor', '重構'),
]
ANNOUNCE_SELECTION = [
    ('yes', '要公告'),
    ('no', '不公告'),
]
TITLE_MAX_LEN = 20
# commit 短碼：7～40 碼十六進位；多個以空白、逗號或頓號分隔
COMMIT_RE = re.compile(r'^[0-9a-fA-F]{7,40}$')
COMMIT_SPLIT_RE = re.compile(r'[\s,，、;；]+')


class ConstructionReleaseEntry(models.Model):
    _name = 'construction.release.entry'
    _description = '更新紀錄'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _rec_names_search = ['name', 'title']

    name = fields.Char(string='編號', required=True, readonly=True, copy=False, default='/')
    date = fields.Date(
        string='日期', required=True, default=fields.Date.context_today, tracking=True,
        help='推送到主分支的日期')
    user_id = fields.Many2one(
        'res.users', string='登記人', required=True, default=lambda self: self.env.user,
        tracking=True, help='負責審查並推送的人（不是工具）')
    entry_type = fields.Selection(ENTRY_TYPE_SELECTION, string='類型', required=True, tracking=True)
    title = fields.Char(string='標題', required=True, tracking=True, help='一句話概括，20 字內')
    reason = fields.Text(
        string='原因', required=True, tracking=True,
        help='為什麼要改？在什麼情況下、發生什麼結果（會不會報錯也要寫）')
    change = fields.Text(
        string='改變', required=True, tracking=True,
        help='改完之後有什麼不同？用使用者看得到的結果描述。「要公告」的紀錄會拿這一欄寫對外公告')
    method = fields.Text(
        string='做法', required=True, tracking=True, help='怎麼改的？給工程師看的技術說明')
    notes = fields.Text(
        string='注意事項', tracking=True,
        help='升級或接手時會踩到的事：要跑 migration、舊資料不會自動更正、要清 asset bundle……')
    commits = fields.Char(
        string='commit', required=True, tracking=True,
        help='本次包含的 commit 短碼，多個以空白或逗號分隔')
    line_ids = fields.One2many(
        'construction.release.entry.line', 'entry_id', string='受影響模組', copy=True)
    modules_summary = fields.Char(string='受影響模組摘要', compute='_compute_modules_summary')
    # 刻意沒有預設值：沒想過就落到某一邊，比沒填更糟
    announce = fields.Selection(ANNOUNCE_SELECTION, string='是否公告', required=True, tracking=True)
    problem_ids = fields.Many2many(
        'construction.problem', 'construction_release_entry_problem_rel',
        'entry_id', 'problem_id', string='關聯問題單')
    has_continuity_warning = fields.Boolean(
        string='版號不連續', compute='_compute_modules_summary')
    # 系統自動填：登記時放進目前的草稿版本；草稿裡可移出／帶入
    release_id = fields.Many2one(
        'construction.release', string='所屬系統版本', readonly=True, copy=False, index=True,
        ondelete='set null', tracking=True)
    release_state = fields.Selection(related='release_id.state', string='版本狀態')
    is_locked = fields.Boolean(string='已鎖定', compute='_compute_is_locked',
                               help='所屬版本已確認或已發布：內容定案，要改只能把版本退回草稿')

    @api.depends('release_id.state')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = rec.release_id.state in ('confirmed', 'published')

    def _check_not_locked(self):
        locked = self.filtered('is_locked')
        if locked:
            raise UserError(_(
                '%s 所屬的系統版本已確認或已發布，內容已定案不能修改。\n'
                '要修改請先把版本「退回草稿」（已發布的版本不能退回）。',
                '、'.join(locked.mapped('name'))))

    @api.depends('line_ids.module_name', 'line_ids.version_before', 'line_ids.version_after',
                 'line_ids.continuity_warning')
    def _compute_modules_summary(self):
        for rec in self:
            rec.modules_summary = '、'.join(
                '%s %s→%s' % (l.module_name, l.version_before or '?', l.version_after or '?')
                for l in rec.line_ids)
            rec.has_continuity_warning = any(rec.line_ids.mapped('continuity_warning'))

    @api.model_create_multi
    def create(self, vals_list):
        Seq = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = Seq.next_by_code('construction.release.entry') or '/'
            # 有草稿版本就自動放進去（問題單才查得到預計發布日）；沒有草稿就維持「未排入」
            if 'release_id' not in vals:
                draft = self.env['construction.release']._get_draft()
                if draft:
                    vals['release_id'] = draft.id
        return super().create(vals_list)

    def write(self, vals):
        # message_main_attachment_id：chatter 上傳附件時 mail.thread 自己會寫，不算修改內容
        if not self.env.context.get('release_system_write') and set(vals) - {'message_main_attachment_id'}:
            self._check_not_locked()
            if 'release_id' in vals:
                raise UserError(_('所屬系統版本由系統處理：請在系統版本草稿裡按「帶入」或「移出」。'))
        return super().write(vals)

    def unlink(self):
        self._check_not_locked()
        return super().unlink()

    def action_remove_from_release(self):
        """從草稿版本移出，回到「未排入」，等下一版。"""
        for rec in self:
            if rec.release_id.state != 'draft':
                raise UserError(_('只能從草稿版本移出。'))
        self.with_context(release_system_write=True).write({'release_id': False})
        return True

    # ------------------------------------------------------------------
    # 檢查
    # ------------------------------------------------------------------
    @api.constrains('title')
    def _check_title(self):
        for rec in self:
            if len((rec.title or '').strip()) > TITLE_MAX_LEN:
                raise ValidationError(_(
                    '標題請控制在 %(max)s 字內（目前 %(n)s 字）。詳細內容寫在「原因／改變／做法」。',
                    max=TITLE_MAX_LEN, n=len(rec.title.strip())))

    @api.constrains('reason', 'change', 'method')
    def _check_three_fields(self):
        # required 只擋 NULL；只打空白也要擋
        labels = {'reason': '原因', 'change': '改變', 'method': '做法'}
        for rec in self:
            empty = [labels[f] for f in labels if not (rec[f] or '').strip()]
            if empty:
                raise ValidationError(_('「%s」不可空白。三欄各回答一個問題，缺一不可。', '」「'.join(empty)))

    @api.constrains('commits')
    def _check_commits(self):
        for rec in self:
            tokens = [t for t in COMMIT_SPLIT_RE.split(rec.commits or '') if t]
            if not tokens:
                raise ValidationError(_('commit 不可空白。'))
            bad = [t for t in tokens if not COMMIT_RE.match(t)]
            if bad:
                raise ValidationError(_(
                    'commit 格式不對：%s\n請填 commit 短碼（7～40 碼英數，例如 07258fb），多個以空白或逗號分隔。',
                    '、'.join(bad)))

    # title 每次 create 都一定在 vals 裡 → 保證新建時一定會跑到這一支
    @api.constrains('line_ids', 'title')
    def _check_has_lines(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_(
                    '%s 沒有列出受影響模組。版號未更新就不得登記——至少要有一個模組的版號改過。',
                    rec.name))


class ConstructionReleaseEntryLine(models.Model):
    _name = 'construction.release.entry.line'
    _description = '更新紀錄：受影響模組'
    _order = 'entry_id, id'

    entry_id = fields.Many2one(
        'construction.release.entry', string='更新紀錄', required=True, ondelete='cascade', index=True)
    # 排序「上一筆」用；related 存起來才能拿來 order
    entry_date = fields.Date(related='entry_id.date', store=True, string='紀錄日期')
    # ir.module.module 不支援 ondelete='restrict'；真相放在 module_name（文字），
    # 模組紀錄日後消失（例如換目錄後 update_list），歷史紀錄仍讀得到
    module_id = fields.Many2one(
        'ir.module.module', string='模組', ondelete='set null',
        domain=lambda self: [('name', 'in', custom_module_names())])
    module_name = fields.Char(
        string='模組名稱', compute='_compute_module_name', store=True, readonly=False,
        required=True, index=True)
    version_before = fields.Char(string='改前版號', help='預設帶該模組上一筆紀錄的改後版號')
    version_after = fields.Char(string='改後版號', help='預設帶模組 __manifest__.py 目前寫的版號')
    continuity_warning = fields.Char(string='提醒', compute='_compute_continuity_warning')

    _sql_constraints = [
        ('entry_module_uniq', 'unique(entry_id, module_name)', '同一筆更新紀錄裡，同一個模組只能列一次。'),
    ]

    # ------------------------------------------------------------------
    # 預設版號
    # ------------------------------------------------------------------
    @api.depends('module_id')
    def _compute_module_name(self):
        for rec in self:
            if rec.module_id:
                rec.module_name = rec.module_id.name

    def _previous_line(self, module_name, entry=None):
        """同模組「上一筆」紀錄的明細：日期較早，同日則編號（id）較小；entry 為空＝取最新一筆。"""
        domain = [('module_name', '=', module_name)]
        if entry and entry.id:
            domain += [('entry_id', '!=', entry.id), '|',
                       ('entry_date', '<', entry.date),
                       '&', ('entry_date', '=', entry.date), ('entry_id', '<', entry.id)]
        # ⚠️ 不能寫 order='entry_id desc'：對 m2o 排序會套用對方的 _order（date desc, id desc）
        #    再整個反轉，同一天的紀錄會變成 id 小的在前。同模組的明細筆數很少，直接在 Python 排
        lines = self.search(domain)
        if not lines:
            return lines
        return max(lines, key=lambda l: (l.entry_date, l.entry_id.id, l.id))

    def _default_version_before(self, module, entry=None):
        """改前版號預設：上一筆紀錄的改後 → 最近一版版本清單 → 資料庫實際安裝的版號。

        不直接用資料庫版號：推送前開發庫通常已經 -u 過，資料庫已是新版，
        拿它當預設會讓改前＝改後。
        """
        prev = self._previous_line(module.name, entry)
        if prev and prev.version_after:
            return prev.version_after
        from_release = self._version_from_last_release(module.name)
        if from_release:
            return from_release
        return module.latest_version or False

    def _version_from_last_release(self, module_name):
        """最近一次確認（含已發布）的版本清單裡，這個模組的版號。"""
        line = self.env['construction.release.manifest.line'].sudo().search([
            ('module_name', '=', module_name), ('is_core', '=', False),
            ('release_id.state', 'in', ('confirmed', 'published')),
        ], order='release_id desc', limit=1)
        return line.version or False

    @api.onchange('module_id')
    def _onchange_module_id(self):
        if self.module_id:
            self.version_before = self._default_version_before(self.module_id, self.entry_id._origin)
            # installed_version ＝ 磁碟 manifest（見 module_version.py 開頭說明）
            self.version_after = self.module_id.installed_version

    def write(self, vals):
        self.entry_id._check_not_locked()
        return super().write(vals)

    def unlink(self):
        self.entry_id._check_not_locked()
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        # 程式路徑（RPC／shell）不會跑 onchange；預設值在寫入端補
        Module = self.env['ir.module.module']
        Entry = self.env['construction.release.entry']
        for vals in vals_list:
            if vals.get('module_id') and not vals.get('module_name'):
                vals['module_name'] = Module.browse(vals['module_id']).name
            if vals.get('module_id') and (not vals.get('version_before') or not vals.get('version_after')):
                module = Module.browse(vals['module_id'])
                entry = Entry.browse(vals['entry_id']) if vals.get('entry_id') else None
                if not vals.get('version_before'):
                    vals['version_before'] = self._default_version_before(module, entry)
                if not vals.get('version_after'):
                    vals['version_after'] = module.installed_version
        lines = super().create(vals_list)
        lines.entry_id._check_not_locked()
        return lines

    # ------------------------------------------------------------------
    # 檢查
    # ------------------------------------------------------------------
    @api.constrains('module_name')
    def _check_module_is_custom(self):
        names = set(custom_module_names())
        for rec in self:
            if rec.module_name not in names:
                raise ValidationError(_(
                    '「%s」不是自有或第三方目錄底下的模組（Odoo 內建模組不需要登記）。', rec.module_name))

    @api.constrains('version_before', 'version_after')
    def _check_versions(self):
        for rec in self:
            name = rec.module_name
            before, after = parse_version(rec.version_before), parse_version(rec.version_after)
            if not before:
                raise ValidationError(_(
                    '%(m)s 的改前版號「%(v)s」格式不對，應為 %(ex)s 這種格式。',
                    m=name, v=rec.version_before or '', ex=VERSION_EXAMPLE))
            if not after:
                raise ValidationError(_(
                    '%(m)s 的改後版號「%(v)s」格式不對，應為 %(ex)s 這種格式。',
                    m=name, v=rec.version_after or '', ex=VERSION_EXAMPLE))
            if after <= before:
                raise ValidationError(_(
                    '%(m)s 的版號沒有更新（改前 %(b)s、改後 %(a)s）。\n'
                    '版號未更新即不得登記：請先修改 __manifest__.py 的 version。\n'
                    '（X 結構／需 migration、Y 功能、Z 修正；加高位時低位歸零）',
                    m=name, b=rec.version_before, a=rec.version_after))

    @api.depends('module_name', 'version_before', 'entry_id.date')
    def _compute_continuity_warning(self):
        for rec in self:
            rec.continuity_warning = False
            if not rec.module_name or not rec.version_before:
                continue
            prev = rec._previous_line(rec.module_name, rec.entry_id._origin or rec.entry_id)
            if prev and prev.version_after and prev.version_after != rec.version_before:
                rec.continuity_warning = _(
                    '上一筆（%(e)s）的改後是 %(v)s，中間可能有一次更新沒登記',
                    e=prev.entry_id.name, v=prev.version_after)

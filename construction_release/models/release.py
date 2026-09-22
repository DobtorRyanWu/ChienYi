# -*- coding: utf-8 -*-
import re

import pytz

from odoo import _, api, fields, models, release
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_manifest

from .module_version import custom_module_names

RELEASE_STATE_SELECTION = [
    ('draft', '草稿'),
    ('confirmed', '已確認'),
    ('published', '已發布'),
]
MAINT_STATE_SELECTION = [
    ('none', '未發布'),
    ('announced', '已發布預告'),
    ('cancelled', '已取消'),
]
# 系統版本號 vX.Y.Z：X 大版本（要重新學）、Y 中版本（多了功能）、Z 小版本（只有修正）
VERSION_NAME_RE = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')
FIRST_VERSION_NAME = 'v1.0.0'
BUMP_SELECTION = [
    ('major', '大版本（整體改版、流程或畫面大幅改變，客戶要重新學或要配合做什麼）'),
    ('minor', '中版本（新增功能、新頁面、新報表，既有操作方式不變）'),
    ('patch', '小版本（只有修正錯誤與微調，操作方式不變）'),
]
DEFAULT_MAINT_MESSAGE = ('系統將於上述時間進行更新，期間系統會重新啟動，'
                         '使用上可能會遇到些許障礙，屬正常現象。')
CORE_MODULE_NAME = 'Odoo 本體'


class ConstructionRelease(models.Model):
    _name = 'construction.release'
    _description = '系統版本'
    _inherit = ['mail.thread']
    _order = 'id desc'

    # 草稿沒有版號（出版月份還不確定）；按「確認」時才編
    name = fields.Char(string='版號', readonly=True, copy=False, tracking=True, index=True)
    state = fields.Selection(
        RELEASE_STATE_SELECTION, string='狀態', required=True, default='draft', readonly=True,
        copy=False, tracking=True)
    planned_date = fields.Date(string='預計發布日', tracking=True, help='只給內部看；延期就改這裡')
    entry_ids = fields.One2many(
        'construction.release.entry', 'release_id', string='包含的更新紀錄',
        groups='base.group_system')
    entry_count = fields.Integer(string='更新紀錄數', compute='_compute_entry_count',
                                 groups='base.group_system')
    manifest_line_ids = fields.One2many(
        'construction.release.manifest.line', 'release_id', string='版本清單', copy=False,
        groups='base.group_system')
    deployment_ids = fields.One2many(
        'construction.deployment', 'release_id', string='部署紀錄', copy=False,
        groups='base.group_system')
    confirm_user_id = fields.Many2one('res.users', string='確認人', readonly=True, copy=False,
                                      groups='base.group_system')
    confirm_datetime = fields.Datetime(string='確認時間', readonly=True, copy=False,
                                       groups='base.group_system')
    # 第幾次確認：部署檢查記下當時的值，退回草稿再確認後舊的檢查就不算數。
    # 不用時間比較——Datetime 只存到秒，同一秒內會誤判
    confirm_serial = fields.Integer(string='確認次數', readonly=True, copy=False, default=0,
                                    groups='base.group_system')
    publish_datetime = fields.Datetime(string='發布時間', readonly=True, copy=False, tracking=True)
    announce_title = fields.Char(string='公告標題', tracking=True)
    announce_body = fields.Text(string='公告內容', tracking=True)
    read_user_ids = fields.Many2many(
        'res.users', 'construction_release_read_user_rel', 'release_id', 'user_id',
        string='已讀使用者', copy=False, groups='base.group_system')
    # 維護預告（橫幅在第三、四階段顯示）
    maint_start = fields.Datetime(string='維護開始時間', tracking=True)
    maint_end = fields.Datetime(string='維護結束時間', tracking=True)
    maint_message = fields.Text(string='預告內容', default=DEFAULT_MAINT_MESSAGE, tracking=True)
    maint_state = fields.Selection(
        MAINT_STATE_SELECTION, string='維護預告', required=True, default='none', readonly=True,
        copy=False, tracking=True)
    # 發布預告當下的時區：橫幅要給「還沒登入的人」看，那時候沒有使用者時區可用，
    # 用瀏覽器 cookie 也不可靠（第一次進來還沒有）→ 發布當下把時區存下來，
    # 所有人看到的都是同一個牆上時間（單一客戶＝單一時區）
    maint_tz = fields.Char(string='預告時區', readonly=True, copy=False)
    has_matching_deployment = fields.Boolean(
        string='已有相符的部署紀錄', compute='_compute_has_matching_deployment', compute_sudo=True)

    @api.depends('name', 'state', 'planned_date')
    def _compute_display_name(self):
        for rec in self:
            if rec.name:
                rec.display_name = rec.name
            elif rec.planned_date:
                rec.display_name = _('下一版（預計 %s）', rec.planned_date.strftime('%m/%d'))
            else:
                rec.display_name = _('下一版（未定預計發布日）')

    @api.depends('entry_ids')
    def _compute_entry_count(self):
        for rec in self:
            rec.entry_count = len(rec.entry_ids)

    @api.depends('deployment_ids.result', 'deployment_ids.confirm_serial', 'confirm_serial', 'state')
    def _compute_has_matching_deployment(self):
        for rec in self:
            rec.has_matching_deployment = bool(rec._matching_deployments())

    def _matching_deployments(self):
        """確認之後做的、結果相符的部署紀錄（退回草稿再確認後，舊的檢查不算數）。"""
        self.ensure_one()
        return self.deployment_ids.filtered(
            lambda d: d.result == 'match' and self.state != 'draft'
            and d.confirm_serial == self.confirm_serial)

    # ------------------------------------------------------------------
    # 約束
    # ------------------------------------------------------------------
    _sql_constraints = [
        # PostgreSQL 的 UNIQUE 允許多個 NULL → 多個沒有版號的紀錄不會互撞
        ('name_uniq', 'unique(name)', '版號不可重複。'),
    ]

    @api.constrains('state')
    def _check_single_draft(self):
        if self.search_count([('state', '=', 'draft')]) > 1:
            raise ValidationError(_(
                '同一時間只能有一個草稿版本。請先把現有的草稿確認，或在現有草稿裡調整內容。'))

    @api.constrains('name')
    def _check_name_format(self):
        for rec in self:
            if rec.name and not VERSION_NAME_RE.match(rec.name):
                raise ValidationError(_('版號「%s」格式不對，應為 vX.Y.Z，例如 v1.5.0。', rec.name))

    @api.constrains('maint_start', 'maint_end')
    def _check_maint_range(self):
        for rec in self:
            if rec.maint_start and rec.maint_end and rec.maint_end <= rec.maint_start:
                raise ValidationError(_('維護結束時間必須晚於開始時間。'))

    def write(self, vals):
        # 已發布的版本：內容定案，只剩系統自己寫的欄位
        locked = {'planned_date', 'announce_title', 'announce_body'}
        if locked & set(vals) and any(r.state == 'published' for r in self):
            raise UserError(_('已發布的版本不能再修改公告或預計發布日。'))
        return super().write(vals)

    def unlink(self):
        if any(r.state != 'draft' for r in self):
            raise UserError(_('只有草稿版本可以刪除。已確認或已發布的版本是部署與公告的依據。'))
        # 草稿裡的紀錄回到「未排入」
        self.sudo().entry_ids.with_context(release_system_write=True).write({'release_id': False})
        return super().unlink()

    # ------------------------------------------------------------------
    # 草稿
    # ------------------------------------------------------------------
    @api.model
    def _get_draft(self):
        return self.sudo().search([('state', '=', 'draft')], limit=1)

    @api.model
    def _ensure_next_draft(self):
        draft = self._get_draft()
        if not draft:
            draft = self.sudo().create({})
            draft.action_pull_entries()
        return draft

    def action_pull_entries(self):
        """帶入所有「未排入」的更新紀錄。"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿可以帶入更新紀錄。'))
        entries = self.env['construction.release.entry'].sudo().search([('release_id', '=', False)])
        entries.with_context(release_system_write=True).write({'release_id': self.id})
        return True

    def action_generate_announcement(self):
        """由「要公告」的紀錄的「改變」欄組成公告草稿（會覆蓋目前內容）。"""
        self.ensure_one()
        if self.state == 'published':
            raise UserError(_('已發布的版本不能再修改公告。'))
        entries = self.sudo().entry_ids.filtered(lambda e: e.announce == 'yes').sorted(
            lambda e: (e.date, e.id))
        self.write({
            'announce_title': _('系統更新公告 %s', self.name) if self.name else _('系統更新公告'),
            'announce_body': '\n'.join('・%s' % e.change.strip() for e in entries) or False,
        })
        return True

    # ------------------------------------------------------------------
    # 確認
    # ------------------------------------------------------------------
    @api.model
    def _last_version_numbers(self):
        """目前最新的版號 (X, Y, Z)；一次都還沒發過回 None。"""
        for rel in self.sudo().search([('name', '!=', False)], order='id desc'):
            m = VERSION_NAME_RE.match(rel.name)
            if m:
                return tuple(int(x) for x in m.groups())
        return None

    def _candidate_names(self):
        """三種跳法各自的版號：{'major': 'v2.0.0', 'minor': 'v1.5.0', 'patch': 'v1.4.3'}。"""
        self.ensure_one()
        last = self._last_version_numbers()
        if not last:
            # 第一版一律 v1.0.0，三種跳法都指向它
            return dict.fromkeys(('major', 'minor', 'patch'), FIRST_VERSION_NAME)
        x, y, z = last
        return {'major': 'v%d.0.0' % (x + 1), 'minor': 'v%d.%d.0' % (x, y + 1),
                'patch': 'v%d.%d.%d' % (x, y, z + 1)}

    def _suggest_bump(self):
        """建議跳哪一段：有「新功能」→ 中版本，其餘 → 小版本。

        🔴 大版本永遠不自動建議——「客戶要不要重新學」沒有任何欄位表達得出來，
           只能由確認的人自己判斷。
        """
        self.ensure_one()
        if any(e.entry_type == 'feature' for e in self.sudo().entry_ids):
            return 'minor'
        return 'patch'

    def _suggest_name(self):
        self.ensure_one()
        return self._candidate_names()[self._suggest_bump()]

    def _manifest_snapshot(self):
        """拍版本清單：自有＋第三方目錄的所有模組（含未安裝）取程式檔版號，另加 Odoo 本體一行。"""
        Module = self.env['ir.module.module'].sudo()
        by_name = {m.name: m for m in Module.search([('name', 'in', custom_module_names())])}
        rows, disk_vs_db = [], []
        for name in custom_module_names():
            mod = by_name.get(name)
            # installed_version ＝ 磁碟 manifest（名字與意義相反，見 module_version.py）
            if mod:
                version = mod.installed_version
                if mod.state == 'installed' and mod.latest_version and mod.latest_version != version:
                    disk_vs_db.append('%s：程式檔 %s／資料庫 %s' % (name, version, mod.latest_version))
            else:
                version = (get_manifest(name) or {}).get('version') or ''
            rows.append({'module_name': name, 'version': version or '', 'is_core': False})
        rows.append({'module_name': CORE_MODULE_NAME, 'version': release.version, 'is_core': True})
        return rows, disk_vs_db

    def _do_confirm(self, name):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿可以確認。'))
        rows, _warn = self._manifest_snapshot()
        self.sudo().manifest_line_ids.unlink()
        self.write({
            'name': name,
            'state': 'confirmed',
            'confirm_user_id': self.env.user.id,
            'confirm_datetime': fields.Datetime.now(),
            'confirm_serial': self.confirm_serial + 1,
            'manifest_line_ids': [(0, 0, r) for r in rows],
        })
        return True

    def action_open_confirm_wizard(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿可以確認。'))
        _rows, disk_vs_db = self._manifest_snapshot()
        bump = self._suggest_bump()
        last = self._last_version_numbers()
        wiz = self.env['construction.release.confirm.wizard'].create({
            'release_id': self.id,
            'bump': bump,
            'version_name': self._candidate_names()[bump],
            'last_version': ('v%d.%d.%d' % last) if last else _('還沒發布過任何版本'),
            'suggest_note': (_('這一版有「新功能」類型的更新紀錄 → 建議中版本')
                             if bump == 'minor' else
                             _('這一版全是修正／調整／移除／重構 → 建議小版本')),
            'warning': '\n'.join(disk_vs_db) or False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('確認系統版本'),
            'res_model': 'construction.release.confirm.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back_to_draft(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('只有「已確認」的版本可以退回草稿。'))
        if self.maint_state == 'announced':
            raise UserError(_('已發布維護預告，請先按「取消維護預告」再退回草稿。'))
        self.sudo().manifest_line_ids.unlink()
        # 先改狀態再檢查單一草稿（約束在 write 時跑）
        self.write({'state': 'draft', 'name': False, 'confirm_user_id': False,
                    'confirm_datetime': False})
        return True

    # ------------------------------------------------------------------
    # 維護預告
    # ------------------------------------------------------------------
    def _reload_action(self):
        """重新整理畫面：橫幅是在頁面載入時渲染的，不重整不會自己消失或出現。"""
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_maint_announce(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('確認之後才能發布維護預告。'))
        if not self.maint_start or not self.maint_end or not (self.maint_message or '').strip():
            raise UserError(_('請先填好維護開始時間、結束時間與預告內容。'))
        self.write({'maint_state': 'announced', 'maint_tz': self._display_tz()})
        return self._reload_action()

    @api.model
    def _display_tz(self):
        """顯示用時區：目前使用者 → context → 公司 → UTC。"""
        return (self.env.user.tz or self.env.context.get('tz')
                or self.env.company.partner_id.tz or 'UTC')

    def action_maint_cancel(self):
        self.ensure_one()
        if self.maint_state != 'announced':
            raise UserError(_('目前沒有已發布的維護預告。'))
        self.maint_state = 'cancelled'
        return self._reload_action()

    # ------------------------------------------------------------------
    # 部署檢查與發布
    # ------------------------------------------------------------------
    def action_check_deployment(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_('確認之後才有版本清單可以比對。'))
        dep = self.env['construction.deployment']._run_check(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('部署紀錄'),
            'res_model': 'construction.deployment',
            'res_id': dep.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_publish(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('只有「已確認」的版本可以發布。'))
        if not self._matching_deployments():
            raise UserError(_(
                '還沒有「相符」的部署紀錄，不能發布。\n'
                '請先在主機上升級資料庫並重新啟動，再按「檢查部署」，結果相符才能發布。'))
        if any(e.announce == 'yes' for e in self.sudo().entry_ids) and not (
                (self.announce_title or '').strip() and (self.announce_body or '').strip()):
            raise UserError(_('這一版有「要公告」的更新紀錄，但公告標題或內容是空的。'
                              '可按「產生公告草稿」再編修。'))
        self.write({'state': 'published', 'publish_datetime': fields.Datetime.now()})
        # 發布後自動建立下一版草稿，之後登記的紀錄自動放進去
        self._ensure_next_draft()
        return self._reload_action()

    # ------------------------------------------------------------------
    # 公告與維護橫幅（後台、前台、登入頁共用）
    # ------------------------------------------------------------------
    @api.model
    def _unread_announcements(self, user=None):
        """這個使用者還沒看過的已發布公告。

        只取**帳號建立之後**才發布的版本：新帳號第一次登入不該被歷次公告一路跳完。
        """
        user = user or self.env.user
        if not user or user._is_public():
            return self.browse()
        return self.sudo().search([
            ('state', '=', 'published'),
            ('announce_title', '!=', False),
            ('publish_datetime', '>=', user.create_date),
            ('read_user_ids', 'not in', user.id),
        ], order='publish_datetime asc, id asc')

    @api.model
    def _announcement_payload(self, releases):
        return [{
            'id': rel.id,
            'version': rel.name or '',
            'title': rel.announce_title or '',
            'body': rel.announce_body or '',
            'publish_date': fields.Datetime.context_timestamp(
                rel, rel.publish_datetime).strftime('%Y-%m-%d') if rel.publish_datetime else '',
        } for rel in releases]

    @api.model
    def _active_maintenance(self):
        """目前要顯示的維護預告；沒有就回 None。

        收起的條件（依裁示）：按「發布」或「取消維護預告」立刻收；
        **過了預計結束時間但還沒發布也沒取消 → 繼續顯示**，只是換句話說。
        """
        rel = self.sudo().search([
            ('maint_state', '=', 'announced'), ('state', '!=', 'published'),
        ], order='maint_start asc, id asc', limit=1)
        if not rel:
            return None
        # ⚠️ 不能用 context_timestamp：登入頁是未登入的 public 使用者，context 沒有時區 → 會顯示 UTC
        tz = pytz.timezone(rel.maint_tz or rel._display_tz() or 'UTC')
        to_local = lambda dt: pytz.utc.localize(dt).astimezone(tz).strftime('%Y-%m-%d %H:%M')
        overrun = bool(rel.maint_end and fields.Datetime.now() > rel.maint_end)
        return {
            'id': rel.id,
            'start': to_local(rel.maint_start) if rel.maint_start else '',
            'end': to_local(rel.maint_end) if rel.maint_end else '',
            'message': rel.maint_message or '',
            'overrun': overrun,
            'headline': (_('系統維護作業仍在進行中，完成後將另行公告') if overrun
                         else _('系統維護預告：%(s)s ～ %(e)s',
                                s=to_local(rel.maint_start) if rel.maint_start else '',
                                e=to_local(rel.maint_end) if rel.maint_end else '')),
        }

    @api.model
    def get_startup_notices(self):
        """後台 web client 啟動時叫一次：要跳的公告 ＋ 要掛的維護橫幅。"""
        return {
            'announcements': self._announcement_payload(self._unread_announcements()),
            'maintenance': self._active_maintenance(),
        }

    @api.model
    def mark_announcements_read(self, release_ids):
        """按「知道了」才算已讀——只是開起來看到不算，下次登入還會再跳。"""
        user = self.env.user
        if not release_ids or user._is_public():
            return False
        self.sudo().browse(release_ids).write({'read_user_ids': [(4, user.id)]})
        return True

    @api.model
    def _published_announcements(self, limit=None):
        """公告回查頁：所有已發布且有公告內容的版本（不限帳號建立日）。"""
        return self.sudo().search([
            ('state', '=', 'published'), ('announce_title', '!=', False),
        ], order='publish_datetime desc, id desc', limit=limit)


class ConstructionReleaseManifestLine(models.Model):
    _name = 'construction.release.manifest.line'
    _description = '系統版本：版本清單'
    _order = 'release_id, is_core desc, module_name'

    release_id = fields.Many2one(
        'construction.release', string='系統版本', required=True, ondelete='cascade', index=True)
    # 刻意用文字、不用 m2o：清單屬於版本，日後要帶到沒有這些模組紀錄的客戶庫
    module_name = fields.Char(string='模組', required=True)
    version = fields.Char(string='版號')
    is_core = fields.Boolean(string='Odoo 本體')

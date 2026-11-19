# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json
from datetime import timedelta

from odoo import api, fields, models

# 每份試算表保留的自動版本筆數（手動版本不受限）
AUTO_VERSION_KEEP = 20
# 同一個人在這段時間內的連續自動儲存併成一筆（前台編輯器每 2 秒存一次，不併會把歷史洗掉）
AUTO_VERSION_MERGE_MINUTES = 10
AUTO_VERSION_MESSAGE = '自動儲存'
BLANK_SPREADSHEET_NAME = '未命名試算表'
# 有這個 context 就不自動存版本（批次匯入、資料修正腳本用）
SKIP_AUTO_VERSION_KEY = 'spreadsheet_workspace_skip_auto_version'
# 底稿裡這個鍵只是協作序號，內容沒變它也可能變，算雜湊時排除
RAW_REVISION_KEY = 'revisionId'


class SpreadsheetSpreadsheet(models.Model):
    _inherit = 'spreadsheet.spreadsheet'
    # 模型顯示名稱（聊天區「○○ 建立」、權限錯誤訊息會用到）
    _description = '試算表'

    # ── OCA 既有欄位：只改繁中標籤，其餘屬性不動 ──
    name = fields.Char(string='名稱')
    active = fields.Boolean(string='啟用')
    badge_image = fields.Image(string='封面圖')
    owner_id = fields.Many2one(string='擁有者')
    contributor_ids = fields.Many2many(string='可編輯使用者')
    contributor_group_ids = fields.Many2many(string='可編輯群組')
    reader_ids = fields.Many2many(string='唯讀使用者')
    reader_group_ids = fields.Many2many(string='唯讀群組')
    company_id = fields.Many2one(string='公司')
    spreadsheet_tag_ids = fields.Many2many(string='標籤')

    # ── 工作區欄位 ──
    folder_id = fields.Many2one(
        comodel_name='spreadsheet.workspace.folder',
        string='資料夾',
        ondelete='set null',
        index=True,
    )
    period_label = fields.Char(
        string='期間標籤',
        help='這份試算表對應的期間，例如「115年11月」「第13期」，方便在清單上辨識與搜尋。',
    )
    is_template_candidate = fields.Boolean(
        string='可作為模板',
        help='勾選後表單會出現「另存為模板」按鈕。',
    )
    source_template_id = fields.Many2one(
        comodel_name='spreadsheet.workspace.template',
        string='來源模板',
        ondelete='set null',
        readonly=True,
        copy=False,
    )
    version_ids = fields.One2many(
        comodel_name='spreadsheet.workspace.version',
        inverse_name='spreadsheet_id',
        string='版本紀錄',
    )
    version_count = fields.Integer(string='版本數', compute='_compute_version_count')

    @api.depends('version_ids')
    def _compute_version_count(self):
        groups = self.env['spreadsheet.workspace.version']._read_group(
            [('spreadsheet_id', 'in', self.ids)], ['spreadsheet_id'], ['__count'],
        )
        counts = {spreadsheet.id: count for spreadsheet, count in groups}
        for spreadsheet in self:
            spreadsheet.version_count = counts.get(spreadsheet.id, 0)

    # ── 清單／表單操作 ──
    @api.model
    def action_create_blank(self):
        """「新增」：直接建立空白試算表並開啟編輯器（資料夾由 context 的 default_folder_id 帶入）。"""
        spreadsheet = self.create({'name': BLANK_SPREADSHEET_NAME})
        return spreadsheet.open_spreadsheet()

    def action_edit_metadata(self):
        """清單列尾齒輪：開「試算表資訊」小視窗，只改資料夾／標籤／共用，不進編輯器。"""
        self.ensure_one()
        view = self.env.ref('spreadsheet_workspace.spreadsheet_spreadsheet_metadata_form_view')
        return {
            'type': 'ir.actions.act_window',
            'name': '試算表資訊',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
        }

    def action_export_xlsx(self):
        """下載 XLSX：交給核心的下載動作，它會在瀏覽器端用「底稿＋未合併操作」算出內容再匯出。"""
        self.ensure_one()
        self.check_access('read')
        raw, revisions = self._workspace_content_snapshot()
        return {
            'type': 'ir.actions.client',
            'tag': 'action_download_spreadsheet',
            'params': {
                'name': self.name,
                'data': raw,
                'stateUpdateMessages': revisions,
            },
        }

    def action_view_versions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'spreadsheet_workspace.action_spreadsheet_version'
        )
        action['domain'] = [('spreadsheet_id', '=', self.id)]
        action['context'] = {'default_spreadsheet_id': self.id}
        return action

    def get_spreadsheet_data(self):
        """多回一個鍵給編輯器上方列的「存成版本」按鈕判斷要不要出現。"""
        data = super().get_spreadsheet_data()
        data['workspace_version'] = {
            'spreadsheet_id': self.id,
            'can_save': data.get('mode') != 'readonly',
        }
        return data

    # ── 模板 ──
    def action_promote_to_template(self):
        """另存為模板：把目前內容複製成一份模板，開啟該模板的表單。"""
        self.ensure_one()
        self.check_access('read')
        raw, _revisions = self._workspace_content_snapshot()
        template = self.env['spreadsheet.workspace.template'].create({
            'name': self.name,
            'category': self.env.context.get('category') or 'custom',
            'spreadsheet_binary_data': self._workspace_binary_from_raw(raw),
        })
        self._workspace_copy_revisions_to(template)
        return {
            'type': 'ir.actions.act_window',
            'name': '試算表模板',
            'res_model': template._name,
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── 版本 ──
    def _workspace_snapshot_vals(self):
        """把目前內容整理成版本列的欄位值（快照兩欄＋內容雜湊）。

        以 sudo 讀內容：呼叫端都已經先確認過使用者對這份試算表有寫入權
        （action_save_version 的 check_access、write 本身），而前台帳號對
        協作操作列（spreadsheet.oca.revision）沒有讀取權，不 sudo 會讀不到。
        """
        self.ensure_one()
        raw, revisions = self.sudo()._workspace_content_snapshot()
        revisions_json = json.dumps(revisions, sort_keys=True)
        comparable = {key: value for key, value in raw.items() if key != RAW_REVISION_KEY}
        digest = hashlib.sha256(
            (json.dumps(comparable, sort_keys=True) + '\n' + revisions_json).encode('utf-8')
        ).hexdigest()
        return {
            'snapshot_raw': json.dumps(raw),
            'snapshot_revisions': revisions_json,
            'content_hash': digest,
        }

    def _workspace_last_version(self):
        self.ensure_one()
        return self.env['spreadsheet.workspace.version'].sudo().search(
            [('spreadsheet_id', '=', self.id)], limit=1,
        )

    def action_open_save_version(self):
        """表單／編輯器的「存成版本」：開小視窗填說明。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '存成版本',
            'res_model': 'spreadsheet.workspace.version.save',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_spreadsheet_id': self.id},
        }

    def action_save_version(self, commit_message=None):
        """手動存一個版本。要對試算表有寫入權；版本列一律以 sudo 建立（使用者對版本只有讀取權）。"""
        self.ensure_one()
        self.check_access('write')
        last = self._workspace_last_version()
        vals = self._workspace_snapshot_vals()
        vals.update({
            'spreadsheet_id': self.id,
            'user_id': self.env.uid,
            'version_date': fields.Datetime.now(),
            'commit_message': (commit_message or '').strip() or False,
            'is_auto': False,
            'parent_version_id': last.id,
        })
        return self.env['spreadsheet.workspace.version'].sudo().create(vals)

    def _workspace_auto_version(self):
        """存檔後自動存版本：內容跟上一版相同就跳過；同一人短時間內的連續自動儲存併成一筆。"""
        self.ensure_one()
        Version = self.env['spreadsheet.workspace.version'].sudo()
        last = self._workspace_last_version()
        vals = self._workspace_snapshot_vals()
        if last and last.content_hash == vals['content_hash']:
            return
        now = fields.Datetime.now()
        merge_after = now - timedelta(minutes=AUTO_VERSION_MERGE_MINUTES)
        if (
            last
            and last.is_auto
            and last.user_id.id == self.env.uid
            and last.version_date >= merge_after
        ):
            last.write(dict(vals, version_date=now))
            return
        Version.create(dict(
            vals,
            spreadsheet_id=self.id,
            user_id=self.env.uid,
            version_date=now,
            commit_message=AUTO_VERSION_MESSAGE,
            is_auto=True,
            parent_version_id=last.id,
        ))
        # 只清自動版本，手動版本永遠留著
        Version.search(
            [('spreadsheet_id', '=', self.id), ('is_auto', '=', True)],
            offset=AUTO_VERSION_KEEP,
        ).unlink()

    def write(self, vals):
        res = super().write(vals)
        # 編輯器存檔就是 write({'spreadsheet_raw': …})；這時 OCA 已把未合併操作清掉、內容都在底稿裡。
        # 寫入權在上面的 super().write() 已經檢查過，所以版本列用 sudo 建
        # （前台帳號也會走到這裡存檔，它們對版本模型沒有任何權限）。
        if 'spreadsheet_raw' in vals and not self.env.context.get(SKIP_AUTO_VERSION_KEY):
            for spreadsheet in self:
                spreadsheet._workspace_auto_version()
        return res

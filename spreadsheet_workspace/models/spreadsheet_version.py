# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json

from odoo import api, fields, models

DATETIME_DISPLAY_FORMAT = '%Y-%m-%d %H:%M:%S'
COMPARE_ACTION_TAG = 'spreadsheet_workspace.version_compare'


class SpreadsheetWorkspaceVersion(models.Model):
    """試算表版本紀錄：某個時間點的完整內容快照。

    一律由 spreadsheet.spreadsheet 的 ``action_save_version``（手動）與 ``write``
    （自動）以 sudo 建立；一般使用者對本模型只有讀取權，
    而且看得到的範圍由 security.xml 的規則綁在「所屬試算表看得到」上。
    """

    _name = 'spreadsheet.workspace.version'
    _description = '試算表版本紀錄'
    _order = 'version_date desc, id desc'

    spreadsheet_id = fields.Many2one(
        comodel_name='spreadsheet.spreadsheet',
        string='試算表',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='提交者',
        ondelete='set null',
        default=lambda self: self.env.uid,
    )
    version_date = fields.Datetime(
        string='時間',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    commit_message = fields.Char(string='提交說明')
    is_auto = fields.Boolean(
        string='自動儲存',
        help='存檔時自動產生的版本；每份試算表只保留最近幾筆，手動版本不會被清掉。',
    )
    parent_version_id = fields.Many2one(
        comodel_name='spreadsheet.workspace.version',
        string='前一版本',
        ondelete='set null',
    )
    # 兩個大欄位不預先載入：清單與表單都不需要，只有對比時才讀
    snapshot_raw = fields.Text(string='底稿快照（JSON）', prefetch=False)
    snapshot_revisions = fields.Text(string='未合併操作（JSON）', prefetch=False)
    content_hash = fields.Char(string='內容雜湊', help='用來判斷內容跟上一版是否相同。')

    @api.depends('version_date', 'commit_message')
    def _compute_display_name(self):
        for version in self:
            when = version._workspace_format_datetime(version.version_date)
            version.display_name = ' '.join(filter(None, [when, version.commit_message]))

    def _workspace_format_datetime(self, value):
        """轉成使用者時區的字串（給對比畫面與顯示名稱用）。"""
        if not value:
            return ''
        return fields.Datetime.context_timestamp(self, value).strftime(DATETIME_DISPLAY_FORMAT)

    def action_compare_with_latest(self):
        """開啟版本對比：本版本 vs 試算表目前內容。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': COMPARE_ACTION_TAG,
            'name': '版本對比',
            'params': {'version_id': self.id},
        }

    def get_compare_payload(self):
        """給版本對比畫面的資料：兩邊各一份「底稿＋未合併操作」，由瀏覽器端算成實際內容再比。"""
        self.ensure_one()
        self.check_access('read')
        spreadsheet = self.spreadsheet_id
        # 版本看得到不代表可以略過試算表本身的權限：兩邊都要過
        spreadsheet.check_access('read')
        current_raw, current_revisions = spreadsheet._workspace_content_snapshot()
        return {
            'spreadsheet_name': spreadsheet.name,
            'from': {
                'date': self._workspace_format_datetime(self.version_date),
                'user': self.user_id.name or '',
                'message': self.commit_message or '',
                'data': json.loads(self.snapshot_raw or '{}'),
                'revisions': json.loads(self.snapshot_revisions or '[]'),
            },
            'to': {
                'date': self._workspace_format_datetime(spreadsheet.write_date),
                'user': spreadsheet.write_uid.name or '',
                'message': '目前內容',
                'data': current_raw,
                'revisions': current_revisions,
            },
        }

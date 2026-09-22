# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, release
from odoo.exceptions import UserError

from .module_version import custom_module_names

RESULT_SELECTION = [
    ('match', '相符'),
    ('mismatch', '不相符'),
]
LINE_RESULT_SELECTION = [
    ('match', '相符'),
    ('mismatch', '不相符'),
    ('not_installed', '本庫未安裝'),
    ('half', '升到一半'),
    ('extra', '清單沒有'),
]
# 這三種以外的狀態（to upgrade／to install／to remove）＝升級沒跑完
SETTLED_STATES = ('installed', 'uninstalled', 'uninstallable')
LINE_RESULT_ORDER = {'half': 0, 'mismatch': 1, 'extra': 2, 'match': 3, 'not_installed': 4}


class ConstructionDeployment(models.Model):
    _name = 'construction.deployment'
    _description = '部署紀錄'
    _order = 'check_datetime desc, id desc'

    release_id = fields.Many2one(
        'construction.release', string='系統版本', required=True, readonly=True, ondelete='restrict',
        index=True)
    db_name = fields.Char(string='資料庫', required=True, readonly=True)
    check_datetime = fields.Datetime(string='檢查時間', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='檢查人', required=True, readonly=True)
    result = fields.Selection(RESULT_SELECTION, string='結果', required=True, readonly=True)
    mismatch_count = fields.Integer(string='不相符的模組數', readonly=True)
    half_count = fields.Integer(string='升到一半的模組數', readonly=True)
    line_ids = fields.One2many('construction.deployment.line', 'deployment_id', string='明細',
                               readonly=True)
    note = fields.Text(string='備註', help='失敗原因、是否回滾、實際花了多少時間……')
    # 檢查當下版本是第幾次確認（見 construction.release.confirm_serial）
    confirm_serial = fields.Integer(string='版本確認次數', readonly=True)

    @api.depends('release_id', 'db_name', 'check_datetime')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s／%s' % (rec.release_id.display_name or '', rec.db_name or '')

    def unlink(self):
        raise UserError(_('部署紀錄不可刪除。檢查結果不符就修好後再檢查一次，舊紀錄留著當作經過。'))

    @api.model
    def _run_check(self, rel):
        """依規範 5-3：讀本庫實際安裝版號 → 找升到一半的 → 與版本清單逐一比對。

        ⚠️ 實際版號取 latest_version（標籤 Installed Version）＝資料庫；
           不是 installed_version（標籤 Latest Version）＝磁碟 manifest。
        """
        Module = self.env['ir.module.module'].sudo()
        lines = []
        # 1) 升到一半：全部模組（含 Odoo 內建）
        for mod in Module.search([('state', 'not in', SETTLED_STATES)]):
            lines.append({'module_name': mod.name, 'expected': '', 'actual': mod.latest_version or '',
                          'db_state': mod.state, 'result': 'half'})
        half_names = {l['module_name'] for l in lines}

        # 2) 與清單逐一比對
        manifest = rel.sudo().manifest_line_ids
        listed = set()
        for ml in manifest:
            if ml.is_core:
                actual = release.version
                lines.append({'module_name': ml.module_name, 'expected': ml.version, 'actual': actual,
                              'db_state': '', 'result': 'match' if actual == ml.version else 'mismatch'})
                continue
            listed.add(ml.module_name)
            if ml.module_name in half_names:
                continue
            mod = Module.search([('name', '=', ml.module_name)], limit=1)
            if not mod or mod.state != 'installed':
                res = 'not_installed'
            else:
                res = 'match' if mod.latest_version == ml.version else 'mismatch'
            lines.append({'module_name': ml.module_name, 'expected': ml.version,
                          'actual': mod.latest_version or '' if mod else '',
                          'db_state': mod.state if mod else '', 'result': res})

        # 3) 本庫有安裝、清單卻沒有的自有／第三方模組
        for mod in Module.search([('name', 'in', custom_module_names()), ('state', '=', 'installed')]):
            if mod.name not in listed and mod.name not in half_names:
                lines.append({'module_name': mod.name, 'expected': '', 'actual': mod.latest_version or '',
                              'db_state': mod.state, 'result': 'extra'})

        lines.sort(key=lambda l: (LINE_RESULT_ORDER[l['result']], l['module_name']))
        half = sum(1 for l in lines if l['result'] == 'half')
        mismatch = sum(1 for l in lines if l['result'] in ('mismatch', 'extra'))
        return self.sudo().create({
            'release_id': rel.id,
            'db_name': self.env.cr.dbname,
            'check_datetime': fields.Datetime.now(),
            'user_id': self.env.user.id,
            'result': 'match' if not half and not mismatch else 'mismatch',
            'confirm_serial': rel.sudo().confirm_serial,
            'mismatch_count': mismatch,
            'half_count': half,
            'line_ids': [(0, 0, l) for l in lines],
        })


class ConstructionDeploymentLine(models.Model):
    _name = 'construction.deployment.line'
    _description = '部署紀錄：明細'
    _order = 'deployment_id, id'

    deployment_id = fields.Many2one(
        'construction.deployment', string='部署紀錄', required=True, ondelete='cascade', index=True)
    module_name = fields.Char(string='模組', required=True)
    expected = fields.Char(string='清單版號')
    actual = fields.Char(string='本庫實際版號')
    db_state = fields.Char(string='本庫狀態')
    result = fields.Selection(LINE_RESULT_SELECTION, string='結果', required=True)

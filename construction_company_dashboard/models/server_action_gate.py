# -*- coding: utf-8 -*-
"""自訂方法閘門的第四條路：伺服器動作（合約 §0b-24；線 I 讀碼時發現，不在派工單的三條路徑內）。

`/web/action/run`（web/controllers/action.py）與 call_kw 的 `ir.actions.server.run`（官方方法，閘門放行）都會執行
伺服器動作的程式碼。核心對「沒設群組」的動作只查「對動作模型有沒有寫入 ACL」（base/models/ir_actions.py run：
`check_access('write')` 對空 recordset 只看 ACL、不看規則），受限帳號隱含 base.group_user，ACL 幾乎都有——
於是任何自訂模組的伺服器動作（含排程的動作：ir.cron 以 _inherits 掛在 ir.actions.server 上，dev 複本裡
water_level_core、uptime_monitor、dobtor 等十幾個都沒設群組）都能由受限帳號觸發，程式碼裡呼叫的自訂方法（含底線開頭的）
完全繞過閘門。

規則：受限帳號（非 sudo）執行伺服器動作時，動作必須是 Odoo 官方模組定義的（xmlid 的模組來源在官方 addons 目錄）；
自訂模組定義的、沒有 xmlid 的（使用者在畫面上建的）、匯出產生的（__export__）一律拒。系統內部以 sudo 執行的不受影響
（本庫沒有裝 base_automation）。監造方與其他帳號照核心。
"""
import logging

from odoo import models
from odoo.exceptions import AccessError

from .method_gate import GATE_NOTE, is_custom_module

_logger = logging.getLogger(__name__)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def _dash_non_core_actions(self):
        """self 之中不是官方模組定義的伺服器動作。"""
        xmlids = self.sudo().get_external_id()
        return self.filtered(lambda action: not xmlids.get(action.id)
                             or is_custom_module(xmlids[action.id].split('.', 1)[0]))

    def run(self):
        if not self.env.su and self.env.user and self.env.user._dash_is_restricted():
            blocked = self._dash_non_core_actions()
            if blocked:
                user = self.env.user
                _logger.warning('%s擋下：帳號 %s（id %s）執行伺服器動作 %s（不是官方模組定義的）',
                                GATE_NOTE, user.login, user.id, blocked.ids)
                names = '、'.join(blocked.sudo().mapped('name'))
                if user._is_role_account():
                    # 後台角色帳號（含監造方老闆、主管）：不能叫他們「洽監造單位」（fix1-I）
                    raise AccessError(f'{GATE_NOTE}：您的帳號是後台唯讀帳號，不能執行這個伺服器動作（{names}）。')
                raise AccessError(
                    f'{GATE_NOTE}：您的帳號是唯讀的營造廠／控台讀取帳號，不能執行這個伺服器動作'
                    f'（{names}）。這個操作限監造單位使用，如有需要請洽監造單位。')
        return super().run()

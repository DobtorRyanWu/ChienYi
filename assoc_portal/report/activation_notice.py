"""開通通知單（計畫 P5）。

兩個硬規則：
1. **報表只讀 data 裡的 token，自己不產生任何東西、也不寫入。**
   核心的 `/report/pdf/<報表>/<id>` 是 auth=user 且不驗 docids，
   nonce 若在報表裡產生，任何內部使用者打那條網址就能拿到別人的開通碼，
   而且 GET 還會順手把已印出的通知單作廢。
2. **只走 PDF。** wkhtmltopdf 狀態不正常時前端會退回
   `GET /report/html/<報表>?options={...}`，token 就進了 access log。
"""

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.assoc_base.tools import qr_data_uri

QR_SIZE_PX = 320
REPORT_NAME = 'assoc_portal.report_activation_notice'


class ActivationNoticeReport(models.AbstractModel):
    _name = 'report.assoc_portal.report_activation_notice'
    _description = '開通／重設密碼通知單'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        member, user, _nonce = self.env['assoc.member'].sudo()._member_from_token(
            data.get('token') or '')
        if not member:
            # 沒有有效的 token 就印不出來（直接 GET /report/pdf/<報表>/<id> 會走到這裡）
            raise UserError(_('請從會員表單按「列印開通通知單」。'))
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        activate_url = '%s/assoc/activate#t=%s' % (base_url.rstrip('/'), data['token'])
        from .. models.assoc_member import ACTIVATION_HOURS
        return {
            'doc_ids': member.ids,
            'doc_model': 'assoc.member',
            'docs': member,
            'member': member,
            'login': user.login,
            'title': _('重設密碼通知單') if data.get('is_reset') else _('帳號開通通知單'),
            'expires_hours': ACTIVATION_HOURS,
            # QR 一律用 data URI：走 /report/barcode?value= 的話，
            # wkhtmltopdf 會回呼那條網址，token 就進了 access log
            'qr': qr_data_uri(self.env, activate_url, QR_SIZE_PX),
        }


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """通知單只能是 PDF。

        **不能覆寫 `_render_qweb_html`**：核心產 PDF 的路徑自己就會呼叫它
        （`ir_actions_report.py:863`），擋掉等於連 PDF 都印不出來。
        要擋的是「輸出成 HTML」這件事，有兩條路：
        - 核心在測試模式或 wkhtmltopdf 不可用時，`_pre_render_qweb_pdf` 會直接回 HTML（:1011-1012）
        - `/report/html/<報表>` 路由（見 controllers/report_guard.py）
        """
        # `_get_report` 對認不出來的名字會丟例外：這個覆寫只關心通知單，
        # 不能因為別的報表（例如 M8 的收據）而讓整條路徑爆掉
        try:
            report_name = self._get_report(report_ref).report_name
        except Exception:      # noqa: BLE001
            report_name = None
        if report_name == REPORT_NAME:
            state = self.get_wkhtmltopdf_state()
            if state not in ('ok', 'upgrade'):
                raise UserError(_('PDF 產生器目前不可用，無法列印通知單。'))
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

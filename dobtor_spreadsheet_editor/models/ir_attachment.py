# -*- coding: utf-8 -*-
"""xlsx 附件在瀏覽器唯讀預覽（2026-11-08）。

使用者看產出的表單、資料夾裡的 Excel 都得先下載——這裡讓 xlsx 附件直接用 OCA
試算表的 client action（action_spreadsheet_oca）打開。

設計：
- **不建 spreadsheet.spreadsheet 記錄**。那個 client action 呼叫的是
  `params.model` 的 `get_spreadsheet_data()`，所以讓 ir.attachment 自己提供：
  每次開都從原檔現轉，不留副本，也就沒有「原檔更新了預覽還是舊的」「副本權限
  要怎麼給」的問題（jt 只有 2 個帳號在試算表群組裡，副本走不通）。
- **權限＝附件本身的讀取權**：`check('read')` 依附件掛的單據判斷，看得到檔才看得到
  預覽；前台帳號一律擋（核心 ir.attachment.check 的規則）。
- **一律唯讀**（mode=readonly）：預覽上改了也存不回原檔，不讓人以為改到了檔案。
  要改請下載原檔，或在樣板設定用「用編輯器開啟」。
- 圖片：預覽不顯示（注入圖片的 patch 只認 spreadsheet.spreadsheet 記錄，且唯讀
  模式不能下指令）；檔內有圖時在上方明講張數、請下載原檔，不讓它看起來完整。
"""
import logging

from odoo import _, models
from odoo.exceptions import UserError

from .xlsx_to_workbook import XlsxTooLarge, convert_isolated

_logger = logging.getLogger(__name__)

XLSX_MIMETYPE = ('application/vnd.openxmlformats-officedocument'
                 '.spreadsheetml.sheet')
# 比這大的檔不轉（父程序要把整份檔交給子程序）。jt 11-08 實測最大的 xlsx 11.9 MB（多半是圖）。
# 解壓後的量、記憶體、CPU、時間的上限在 xlsx_to_workbook（convert_isolated）。
PREVIEW_MAX_BYTES = 20 * 1024 * 1024
MSG_TOO_LARGE = '這個檔案太大或太複雜，無法在瀏覽器預覽，請按上方「下載原檔」用 Excel 開啟。'
MSG_BROKEN = '這個檔案無法在瀏覽器預覽（可能是加密或格式不相容），請按上方「下載原檔」用 Excel 開啟。'


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _dobtor_is_xlsx(self):
        self.ensure_one()
        return (self.mimetype == XLSX_MIMETYPE
                or (self.name or '').lower().endswith('.xlsx'))

    def _dobtor_check_previewable(self):
        """權限與檔案類型；不符就丟例外（AccessError／UserError）。

        大小、壞檔不在這裡擋：那些情況照樣打開預覽、顯示說明，讓上方的「下載原檔」
        還按得到（紅隊：原本在這裡丟 UserError，產出表單太大時連檔都拿不到）。
        """
        self.ensure_one()
        self.check('read')          # 依附件掛的單據判斷讀取權；前台帳號一律擋
        self.check_access('read')   # 再走一次 ACL＋record rule
        if not self._dobtor_is_xlsx():
            raise UserError(_('只有 .xlsx 檔可以在瀏覽器預覽，請下載後開啟。'))

    def action_open_spreadsheet_preview(self):
        """在瀏覽器以唯讀試算表開啟本 xlsx 附件。"""
        self._dobtor_check_previewable()
        return {
            'type': 'ir.actions.client',
            'tag': 'action_spreadsheet_oca',
            'name': self.name,
            'params': {'spreadsheet_id': self.id, 'model': self._name},
        }

    def send_spreadsheet_message(self, message, access_token=None):
        """預覽不協作：o-spreadsheet 唯讀模式照樣會送「有人加入／游標移動」等訊息
        （transport 呼叫 params.model 的這個方法），沒有它整頁會跳伺服器錯誤框
        （2026-11-08 E2E 實測）。一律回 False＝不接受，不寫任何東西、不廣播。"""
        return False

    def _dobtor_convert_for_preview(self, base):
        """回 (workbook_data, image_count, error_message)；失敗時 data 是一張寫著說明的表。"""
        if (self.file_size or 0) > PREVIEW_MAX_BYTES:
            return self._dobtor_message_workbook(base, _(MSG_TOO_LARGE)), 0, _(MSG_TOO_LARGE)
        try:
            data, _log, image_count = convert_isolated(self.raw or b'', base)
            return data, image_count, False
        except XlsxTooLarge as e:
            _logger.warning('xlsx 預覽拒轉（太大／太複雜）：ir.attachment#%s %s：%s', self.id, self.name, e)
            msg = _(MSG_TOO_LARGE)
        except Exception:
            # 壞檔／加密檔／其實是 xls 改副檔名：細節留在 log，畫面給能照做的說明
            _logger.exception('xlsx 預覽轉換失敗：ir.attachment#%s %s', self.id, self.name)
            msg = _(MSG_BROKEN)
        return self._dobtor_message_workbook(base, msg), 0, msg

    @staticmethod
    def _dobtor_message_workbook(base, message):
        data = dict(base or {})
        data['sheets'] = [{
            'id': 'sheet1', 'name': '預覽', 'colNumber': 26, 'rowNumber': 100,
            'cells': {'A1': {'content': message}}, 'merges': [], 'cols': {}, 'rows': {},
            'conditionalFormats': [], 'dataValidationRules': [], 'tables': [],
            'figures': [], 'areGridLinesVisible': True,
        }]
        data.update(styles={}, formats={}, borders={})
        return data

    def get_spreadsheet_data(self):
        """供 action_spreadsheet_oca 載入（格式同 spreadsheet.abstract.get_spreadsheet_data）。"""
        self._dobtor_check_previewable()
        base = self.env['spreadsheet.spreadsheet']._empty_spreadsheet_data()  # OCA 底稿（locale／version）
        data, image_count, error = self._dobtor_convert_for_preview(base)
        return {
            'name': self.name,
            'spreadsheet_raw': data,
            'revisions': [],
            'mode': 'readonly',
            'default_currency': self.env['res.currency'].get_company_currency_for_spreadsheet(),
            'user_locale': self.env['res.lang']._get_user_spreadsheet_locale(),
            # 給控制列上的「下載原檔」、圖片提示、轉換失敗說明用（static/src/attachment_preview/）
            'dobtor_preview': {
                'download_url': '/web/content/%d?download=true' % self.id,
                'image_count': image_count,
                'error': error,
            },
        }

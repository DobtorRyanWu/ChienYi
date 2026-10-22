"""個資存取軌跡（計畫 §11）。

《內政部指定合作及人民團體類非公務機關個人資料檔案安全維護管理辦法》§18 要求
軌跡資料至少保存 5 年。Odoo 沒有讀取紀錄，`res.users.log` 只記登入而且會被 GC 清掉，
所以自建這張表：**不做 GC、不可改、不可刪**。

擋不住的：持 DB 或 system 權限者可以整張改寫（與 v8 D6 同級的殘餘風險）。
偵測靠每日備份異地保存後比對——不做雜湊鏈是刻意的：鏈頭要序列化，
會場尖峰的登入會互相 40001。
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

RES_IDS_MAX_LEN = 200

ACTIONS = [
    ('login_ok', '登入成功'),
    ('reveal_pii', '顯示身分證明文'),
    ('export_pii', '匯出含身分證資料'),
    ('clear_national_id', '清除身分證'),
    ('member_import', '匯入會員'),
    ('doc_review', '審核會員文件'),
    ('print_activation', '列印開通通知單'),
    ('activate_ok', '會員以通知單設定密碼'),
    ('print_reset', '列印重設密碼通知單'),
    ('grant_portal', '開通會員帳號'),
    ('grant_conflict', '開通衝突'),
    ('revoke_portal', '停用會員帳號'),
    ('credit_override', '人工調整積分'),
    ('credit_export', '匯出積分名冊'),
    ('proxy_activate', '委託生效'),
    ('proxy_cancel', '委託取消'),
    ('proxy_paper_received', '確認收到書面委託書'),
    ('proxy_form_print', '列印委託書'),
    ('dues_waive', '應繳免繳'),
    ('receipt_post', '收據過帳'),
    ('receipt_void', '收據作廢'),
    ('gift_manual_claim', '禮品手動領取'),
    ('gift_export', '禮品名單匯出'),
    ('gift_revert', '禮品名單還原'),
    ('archive_build', '產生封存包'),
    ('archive_download', '下載封存包'),
    ('candidate_self_register', '會員自助登記參選'),
    ('candidate_self_withdraw', '會員自助退選'),
]


class AssocAuditLog(models.Model):
    _name = 'assoc.audit.log'
    _description = '公會存取軌跡'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', string='公會', required=True, index=True)
    action = fields.Selection(ACTIONS, string='動作', required=True, index=True)
    res_model = fields.Char(string='模型')
    res_ids_text = fields.Char(string='紀錄 ID')
    record_count = fields.Integer(string='筆數')
    detail = fields.Json(string='細節')
    ip = fields.Char(string='來源 IP')

    def write(self, vals):
        raise UserError(_('存取軌跡不可修改。'))

    def unlink(self):
        raise UserError(_('存取軌跡不可刪除（法規要求保存 5 年）。'))

    @api.model
    def _log_independent(self, action, company, detail=None, res_model=None, res_ids=None):
        """在**獨立交易**寫軌跡：呼叫端接著要 raise，主交易會整個回滾。

        「開通衝突」這種「因為擋下來所以要留紀錄」的事件，寫在主交易裡等於沒寫：
        UserError 一拋，http 層就把交易回滾掉（測試裡的 assertRaises 也包 savepoint，
        正好把這個問題照出來）。
        這是本系統唯一自己開 cursor 並 commit 的地方。
        """
        values = {
            'company_id': company.id,
            'action': action,
            'res_model': res_model,
            'res_ids_text': (','.join(str(i) for i in (res_ids or [])))[:RES_IDS_MAX_LEN],
            'record_count': len(res_ids or []),
            'detail': detail or {},
            'ip': request.httprequest.remote_addr if request else False,
        }
        try:
            with self.env.registry.cursor() as cr:
                self.env(cr=cr, su=True)['assoc.audit.log'].create(values)
        except Exception:      # noqa: BLE001
            # 獨立交易看不到尚未 commit 的資料（測試、或同一交易剛建立的公司）。
            # 寧可記在主交易也不要沒有紀錄——但要留 warning，避免「以為有寫其實沒寫」。
            _logger.warning('assoc audit: 獨立交易寫入失敗，改寫在主交易（action=%s）', action,
                            exc_info=True)
            self.sudo().create(values)
        return True

    @api.model
    def _log(self, action, records=None, detail=None, company=None, count=None):
        """寫一筆軌跡。

        detail 只放「做了什麼」，**不得放個資值**（身分證、開通 token、
        選舉的個人收據碼——那是能反推投票行為的秘密）。
        會費收據的號碼（`receipt_no`）不在此列：它是對外的憑證編號，
        本來就印在收據上，軌跡要能對得上那張收據才有用。
        呼叫端權限不足也要寫得進來，所以固定 sudo：這張表沒有寫入 ACL。
        """
        company = company or (records and records[:1].company_id) or self.env.company
        ids = records.ids if records else []
        values = {
            'company_id': company.id,
            'action': action,
            'res_model': records._name if records else False,
            'res_ids_text': (','.join(str(i) for i in ids))[:RES_IDS_MAX_LEN],
            'record_count': count if count is not None else len(ids),
            'detail': detail or {},
            'ip': request.httprequest.remote_addr if request else False,
        }
        return self.sudo().create(values)
